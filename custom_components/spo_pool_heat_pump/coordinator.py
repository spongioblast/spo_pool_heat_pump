"""Push coordinator. 2001 broadcasts call async_set_updated_data."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_POLL_INTERVAL,
    CONF_PROFILE,
    CONF_WRITE_PATH,
    DOMAIN,
    STALE_SECONDS,
    WRITE_PATH_DTU,
    apply_runtime_overrides,
    reload_option_fingerprint,
    service_menu_writes_enabled,
)
from .cop import cop_options
from .drivers import HeatPumpDriver, HeatPumpState, build_driver
from .dump import (
    DUMP_DIR_NAME,
    DumpAlreadyRunning,
    DumpNotRunning,
    DumpRecorder,
    delete_dump_file,
    dumps_dir,
    status_payload,
)
from .energy import EnergyIntegrator
from .publish import DiscreteFingerprint, next_force_seq
from .profiles import load_profile, profile_polls
from .transport.tcp import TcpRtuClient

_LOGGER = logging.getLogger(__name__)


class PoolHeatPumpCoordinator(DataUpdateCoordinator[HeatPumpState]):
    @staticmethod
    def _matches(
        hass: HomeAssistant,
        *,
        entry_id: str | None = None,
        entity_id: str | None = None,
        device_id: str | None = None,
    ) -> list[ConfigEntry]:
        entries = [
            entry
            for entry in hass.config_entries.async_entries(DOMAIN)
            if getattr(entry, "runtime_data", None)
        ]
        if device_id:
            from homeassistant.helpers import device_registry as dr

            device = dr.async_get(hass).async_get(device_id)
            if not device:
                return []
            ids = {ident[1] for ident in device.identifiers if ident[0] == DOMAIN}
            entries = [
                entry
                for entry in entries
                if entry.runtime_data.unique_id in ids or entry.entry_id in ids
            ]
        if entry_id:
            return [entry for entry in entries if entry.entry_id == entry_id]
        if entity_id:
            from homeassistant.helpers import entity_registry as er

            entity = er.async_get(hass).async_get(entity_id)
            matched: list[ConfigEntry] = []
            if entity and entity.config_entry_id:
                matched = [entry for entry in entries if entry.entry_id == entity.config_entry_id]
            if not matched and entity and entity.unique_id:
                for entry in entries:
                    uid = entry.runtime_data.unique_id
                    if entity.unique_id == uid or entity.unique_id.startswith(f"{uid}_"):
                        matched.append(entry)
            return matched
        return entries

    @staticmethod
    def resolve(
        hass: HomeAssistant,
        *,
        entry_id: str | None = None,
        entity_id: str | None = None,
        device_id: str | None = None,
    ) -> PoolHeatPumpCoordinator | None:
        found = PoolHeatPumpCoordinator._matches(
            hass, entry_id=entry_id, entity_id=entity_id, device_id=device_id
        )
        return found[0].runtime_data if len(found) == 1 else None

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: TcpRtuClient,
        profile: dict | None = None,
    ) -> None:
        profile_id = entry.options.get(CONF_PROFILE, entry.data.get(CONF_PROFILE))
        interval = entry.options.get(CONF_POLL_INTERVAL, entry.data.get(CONF_POLL_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=None if interval is None else timedelta(seconds=int(interval)),
        )
        self.entry = entry
        self.client = client
        loaded = profile if profile is not None else load_profile(profile_id)
        self.profile = apply_runtime_overrides(loaded, entry.data, entry.options)
        self.device_name = entry.title or self.profile["identity"]["model"]
        self.unique_id = entry.unique_id or f"{entry.data.get('host')}:{profile_id}"
        self.energy = EnergyIntegrator()
        write_path = entry.options.get(CONF_WRITE_PATH, entry.data.get(CONF_WRITE_PATH, WRITE_PATH_DTU))
        self.driver: HeatPumpDriver = build_driver(
            self.profile, client.send, write_path, self._push
        )
        self.driver.service_menu_writes = service_menu_writes_enabled(entry.data, entry.options)
        if not self.driver.is_push and self.update_interval is None:
            self.update_interval = timedelta(seconds=int(self.profile["driver"].get("poll_interval", 10)))
        self._stale_handle: asyncio.TimerHandle | None = None
        self._settings_refresh_once = False
        self.reload_fingerprint = reload_option_fingerprint(entry.data, entry.options)
        self.force_seq = 0
        self._discrete_fp: DiscreteFingerprint | None = None
        self.dump: DumpRecorder | None = None
        self._dump_task: asyncio.Task[None] | None = None
        self._flag_tasks: set[asyncio.Task] = set()

    @property
    def service_menu_writes(self) -> bool:
        return service_menu_writes_enabled(self.entry.data, self.entry.options)

    @property
    def cop_options(self) -> dict:
        return cop_options(self.entry.data, self.entry.options)

    @property
    def is_polling(self) -> bool:
        return not self.driver.is_push

    def dumps_path(self) -> Path:
        if isinstance(self.hass, HomeAssistant):
            return Path(self.hass.config.path(DUMP_DIR_NAME))
        return dumps_dir(Path("."))

    def dump_status(self) -> dict[str, Any]:
        return status_payload(self.dumps_path(), self.dump)

    def delete_dump(self, name: str) -> dict[str, Any]:
        if self.dump is not None and self.dump.running:
            stem = Path(name).stem
            if stem == self.dump.stamp or stem.startswith(f"{self.dump.stamp}_"):
                raise DumpAlreadyRunning
        delete_dump_file(self.dumps_path(), name)
        return self.dump_status()

    async def async_dump_status(self) -> dict[str, Any]:
        if isinstance(self.hass, HomeAssistant):
            return await self.hass.async_add_executor_job(self.dump_status)
        return self.dump_status()

    async def async_delete_dump(self, name: str) -> dict[str, Any]:
        if isinstance(self.hass, HomeAssistant):
            return await self.hass.async_add_executor_job(self.delete_dump, name)
        return self.delete_dump(name)

    async def start_dump(
        self,
        duration_s: int = 900,
        note: str = "",
        include_writes: bool = True,
    ) -> dict[str, Any]:
        if self.dump is not None and self.dump.running:
            raise DumpAlreadyRunning
        host = self.entry.data.get("host", "")
        port = self.entry.data.get("port", "")
        recorder = DumpRecorder(
            self.dumps_path(),
            source=f"dr164 {host}:{port}",
            profile=str(self.profile["identity"]["id"]),
            note=note,
            include_writes=include_writes,
            duration_s=duration_s,
        )
        if isinstance(self.hass, HomeAssistant):
            await self.hass.async_add_executor_job(recorder.start)
        else:
            recorder.start()
        self.dump = recorder
        self.client.recorder = recorder
        self._start_dump_task()
        return await self.async_dump_status()

    async def stop_dump(self) -> dict[str, Any]:
        recorder = self.dump
        if recorder is None or not recorder.running:
            raise DumpNotRunning
        self.client.recorder = None
        if isinstance(self.hass, HomeAssistant):
            await self.hass.async_add_executor_job(recorder.stop, "stop")
        else:
            recorder.stop("stop")
        await self._cancel_dump_task()
        return await self.async_dump_status()

    def _start_dump_task(self) -> None:
        if self._dump_task and not self._dump_task.done():
            return
        if isinstance(self.hass, HomeAssistant):
            self._dump_task = self.hass.async_create_task(self._dump_flush_loop(), name="spo_pool_heat_pump_dump")
        else:
            self._dump_task = asyncio.create_task(self._dump_flush_loop(), name="spo_pool_heat_pump_dump")

    async def _cancel_dump_task(self) -> None:
        task = self._dump_task
        self._dump_task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _dump_flush_loop(self) -> None:
        try:
            while self.dump is not None and self.dump.running:
                await asyncio.sleep(1.0)
                recorder = self.dump
                if recorder is None:
                    return
                if isinstance(self.hass, HomeAssistant):
                    await self.hass.async_add_executor_job(recorder.flush)
                else:
                    recorder.flush()
                if recorder.running:
                    continue
                self.client.recorder = None
                return
        except asyncio.CancelledError:
            raise

    async def _stop_dump_quiet(self) -> None:
        if self.dump is None or not self.dump.running:
            await self._cancel_dump_task()
            return
        self.client.recorder = None
        try:
            self.dump.stop("unload")
        except Exception:  # noqa: BLE001
            _LOGGER.debug("dump stop on unload failed", exc_info=True)
        await self._cancel_dump_task()

    @property
    def state(self) -> HeatPumpState:
        return self.data if self.data is not None else HeatPumpState()

    def _push(self, state: HeatPumpState) -> None:
        state.energy_total_kwh = self.energy.update(state.power_kw, time.monotonic())
        self.force_seq, self._discrete_fp = next_force_seq(self._discrete_fp, state, self.force_seq)
        self.async_set_updated_data(state)
        self._arm_stale()
        self._schedule_settings_refresh()

    def _schedule_settings_refresh(self) -> None:
        if self._settings_refresh_once:
            return
        self._settings_refresh_once = True
        if not isinstance(self.hass, HomeAssistant):
            return
        self.hass.async_create_task(self._async_refresh_settings_once())

    async def _async_refresh_settings_once(self) -> None:
        try:
            await self.driver.refresh_settings()
        except Exception:  # noqa: BLE001
            _LOGGER.debug("startup settings refresh failed", exc_info=True)

    def _arm_stale(self) -> None:
        if self.profile.get("driver", {}).get("type") == "listen_only":
            return
        loop = self.hass.loop
        if self._stale_handle:
            self._stale_handle.cancel()
        self._stale_handle = loop.call_later(STALE_SECONDS, self._mark_stale)

    def _mark_stale(self) -> None:
        """No fresh frame for STALE_SECONDS — mark unavailable.

        Push profiles wait for the 2001 broadcast; poll profiles wait for a poll cycle.
        """
        current = self.state
        current.available = False
        reason = "Poll timed out" if self.is_polling else "No 2001 broadcast"
        self.async_set_update_error(UpdateFailed(reason))

    async def _async_update_data(self) -> HeatPumpState:
        if self.is_polling:
            polls = len(profile_polls(self.profile) or [1])
            for _ in range(polls):
                await self.driver.poll_once()
            return self.driver.state
        if self.data is None:
            raise UpdateFailed("Waiting for broadcast")
        return self.data

    def _create_task(self, coro, name: str) -> asyncio.Task:
        if isinstance(self.hass, HomeAssistant):
            task = self.hass.async_create_task(coro, name=name)
        else:
            task = asyncio.create_task(coro, name=name)
        if name == "spo_pool_heat_pump_flag_refresh":
            self._flag_tasks.add(task)
            task.add_done_callback(self._flag_tasks.discard)
        return task

    async def _cancel_flag_tasks(self) -> None:
        tasks = list(self._flag_tasks)
        self._flag_tasks.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _async_flag_refresh(self, pages: list[int] | str) -> None:
        try:
            if pages == "all":
                await self.driver.refresh_settings()
            else:
                await self.driver.refresh_settings(only=list(pages))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            _LOGGER.debug("flag settings refresh failed", exc_info=True)

    async def async_on_frame(self, frame: bytes) -> None:
        reply = self.driver.handle_frame(frame)
        if reply:
            await self.client.send(reply)
        pages = await self.driver.after_frame()
        if pages:
            self._create_task(self._async_flag_refresh(pages), "spo_pool_heat_pump_flag_refresh")

    def _on_tcp_connection(self, connected: bool) -> None:
        if self.profile.get("driver", {}).get("type") != "listen_only":
            return
        setter = getattr(self.driver, "set_available", None)
        if setter:
            setter(connected)

    async def async_start(self) -> None:
        await self.client.start(self.async_on_frame, on_connection=self._on_tcp_connection)
        await self.driver.async_start()
        # listen_only async_start publishes available=True; sync to the live socket.
        self._on_tcp_connection(self.client.connected)

    async def async_stop(self) -> None:
        if self._stale_handle:
            self._stale_handle.cancel()
        await self._cancel_flag_tasks()
        await self._stop_dump_quiet()
        await self.driver.async_stop()
        await self.client.stop()


PoolHeatPumpConfigEntry = ConfigEntry[PoolHeatPumpCoordinator]
