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
    CONF_HOST,
    CONF_POLL_INTERVAL,
    CONF_PROFILE,
    CONF_WRITE_PATH,
    DOMAIN,
    DR164_REBOOT_COOLDOWN_S,
    DR164_SEARCH_MISSES_MAX,
    DR164_SILENCE_REBOOT_S,
    STALE_SECONDS,
    WRITE_PATH_SLAVE2,
    apply_runtime_overrides,
    reboot_dr164_on_silence_enabled,
    reload_option_fingerprint,
    service_menu_writes_enabled,
)
from .dr164_at import Dr164AtError, Dr164NoSearchReply, reboot_dr164
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
        write_path = entry.options.get(CONF_WRITE_PATH, entry.data.get(CONF_WRITE_PATH, WRITE_PATH_SLAVE2))
        self.driver: HeatPumpDriver = build_driver(
            self.profile, client.send, write_path, self._push
        )
        self.driver.service_menu_writes = service_menu_writes_enabled(entry.data, entry.options)
        if not self.driver.is_push and self.update_interval is None:
            self.update_interval = timedelta(seconds=int(self.profile["driver"].get("poll_interval", 10)))
        if self.update_interval is not None and hasattr(self.driver, "set_poll_interval"):
            self.driver.set_poll_interval(self.update_interval.total_seconds())
        self._stale_handle: asyncio.TimerHandle | None = None
        self._last_frame_at: float | None = None
        self._started_at = time.monotonic()
        self._last_dr164_reboot_at: float | None = None
        self._dr164_search_misses = 0
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
        # Runs on every write path, slave 2 included. The board only pushes
        # 1001/1091/1181 to the panels when a page changed; the periodic pushes go
        # to the WiFi module (slave 99). Without this one read after start-up the
        # slave-2 copy of 1091 stays empty until someone touches the panel, and the
        # first setpoint change fails with SettingsUnseeded (live box, 03b4f19).
        # See PAGE_SEED_WAIT_S in drivers/pc1002_bus.py for the dump numbers.
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

    def _has_pending_writes(self) -> bool:
        pending = getattr(self.driver, "pending", None)
        return bool(pending)

    def _kick_transport(self) -> None:
        """Ask the transport for a fresh socket; a silent bus is usually a
        half-open TCP session after a DR164 reboot or WiFi drop."""
        reconnect = getattr(self.client, "reconnect", None)
        if reconnect is None:
            return
        result = reconnect()
        if asyncio.iscoroutine(result):
            self._create_task(result, "spo_pool_heat_pump_stale_reconnect")

    def _note_frame(self) -> None:
        self._last_frame_at = time.monotonic()

    def _bus_is_silent(self) -> bool:
        last = self._last_frame_at
        return last is None or (time.monotonic() - last) >= STALE_SECONDS

    def _silence_s(self) -> float:
        last = self._last_frame_at
        origin = last if last is not None else self._started_at
        return time.monotonic() - origin

    def _should_reboot_dr164(self) -> bool:
        """True when the DR164 is on the LAN but RS-485 has been dead too long.

        TCP still up + no frame is the 2026-09-17 DE-jam picture, not a WiFi
        drop (that loses the socket). The 15 s stale tick already redials TCP;
        this is the next step. Skip listen_only / poll_master. Skip a recent
        AT+Z so we do not loop during the ~20 s boot. A pending write does not
        block this: after 60 s of zero frames the write is already lost.
        """
        if self.profile.get("driver", {}).get("type") != "pc1002_bus":
            return False
        if not reboot_dr164_on_silence_enabled(self.entry.data, self.entry.options):
            return False
        if self._dr164_search_misses >= DR164_SEARCH_MISSES_MAX:
            return False
        if not getattr(self.client, "connected", False):
            return False
        if self._silence_s() < DR164_SILENCE_REBOOT_S:
            return False
        last = self._last_dr164_reboot_at
        if last is not None and (time.monotonic() - last) < DR164_REBOOT_COOLDOWN_S:
            return False
        return True

    def _maybe_reboot_dr164(self) -> None:
        if not self._should_reboot_dr164():
            return
        host = self.entry.data.get(CONF_HOST)
        if not host:
            return
        # Stamp before the await so two stale ticks cannot queue two AT+Z.
        self._last_dr164_reboot_at = time.monotonic()
        _LOGGER.warning(
            "RS-485 silent for %.0fs while TCP to %s is up; rebooting DR164 "
            "(AT+Z over UDP 48899). Slave-2 TX can leave this module's auto-DE "
            "asserted; AT+Z released the live bus on 2026-09-17 with no Modbus. "
            "Do not use FC03 for this.",
            self._silence_s(),
            host,
        )
        self._create_task(self._async_reboot_dr164(str(host)), "spo_pool_heat_pump_dr164_reboot")

    async def _async_reboot_dr164(self, host: str) -> None:
        try:
            banner = await reboot_dr164(host)
        except Dr164NoSearchReply as err:
            self._dr164_search_misses += 1
            if self._dr164_search_misses >= DR164_SEARCH_MISSES_MAX:
                _LOGGER.warning(
                    "Gateway at %s never answered the USR-DR164 search (%d tries); "
                    "silent-bus AT+Z is off until reload. Expected on Waveshare and "
                    "other non-USR gateways — turn off 'Reboot DR164 if the bus "
                    "stays silent' under Configure.",
                    host,
                    self._dr164_search_misses,
                )
            else:
                _LOGGER.warning("DR164 AT+Z handshake failed: %s", err)
        except Dr164AtError as err:
            self._dr164_search_misses = 0
            _LOGGER.warning("DR164 AT+Z handshake failed: %s", err)
        except Exception:  # noqa: BLE001
            _LOGGER.warning("DR164 AT+Z failed", exc_info=True)
        else:
            self._dr164_search_misses = 0
            _LOGGER.info("DR164 AT+Z sent (%s)", banner)

    def _mark_stale(self) -> None:
        """No fresh *broadcast* for STALE_SECONDS — maybe reconnect, maybe unavailable.

        Availability stays tied to the 2001 broadcast (or a poll cycle). The
        reconnect kick is keyed to the last *frame* of any kind: board polls and
        unchanged page pushes keep the TCP socket up through the board's post-commit
        pause, when broadcasts can be 20 s apart while the bus is fully alive.
        """
        if self._bus_is_silent():
            # Decide on AT+Z *before* the TCP kick. hass.async_create_task starts
            # the reconnect coroutine eagerly, so by the time the next statement
            # runs reconnect() has already called writer.close() and
            # client.connected reads False. With the calls the other way round
            # the gate never opened: live box 2026-09-19 15:15 → 09:00, 18 h of
            # "bus silent" redials every 15 s and not one AT+Z.
            self._maybe_reboot_dr164()
            self._kick_transport()
        self._arm_stale()
        if self._has_pending_writes():
            return
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
        from .modbus_rtu import parse_frame

        if parse_frame(frame) is not None:
            self._note_frame()
        reply = self.driver.handle_frame(frame)
        if reply:
            await self.client.send(reply, solicited=True)
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
        # Arm the stale timer now, not on the first frame. _push() is the only
        # other place that arms it, and _push() needs a frame. When Home
        # Assistant starts into a bus that is already jammed (DR164 DE held
        # after a slave-2 reply) no frame ever comes, so neither the 15 s TCP
        # redial nor the 60 s AT+Z could ever run: live box 2026-09-21, bus
        # dead since 06:03, restart at 16:24 onto f1965e0, still grey with no
        # AT+Z warning 5 min later. _silence_s() falls back to _started_at
        # while _last_frame_at is None, so the 60 s gate counts from here.
        self._arm_stale()

    async def async_stop(self) -> None:
        if self._stale_handle:
            self._stale_handle.cancel()
        await self._cancel_flag_tasks()
        await self._stop_dump_quiet()
        await self.driver.async_stop()
        await self.client.stop()


PoolHeatPumpConfigEntry = ConfigEntry[PoolHeatPumpCoordinator]
