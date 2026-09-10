"""Multi-step config flow: transport → detect → profile → options."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST
from homeassistant.core import callback

from .const import (
    CONF_MANUAL_COP_FLOW,
    CONF_NAME,
    CONF_POLL_INTERVAL,
    CONF_POLL_SLAVE,
    CONF_PORT,
    CONF_PROFILE,
    CONF_SERVICE_MENU_WRITES,
    CONF_WATER_FLOW_M3H,
    CONF_WRITE_PATH,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DOMAIN,
    WATER_FLOW_MAX,
    WRITE_PATH_DTU,
    merge_entry_options,
    suggested_write_path,
    write_path_choices,
)
from .drivers.detect import DetectFailed, detect_profile, detect_reason
from .profiles import choice_map, resolve_profile_id
from .transport.tcp import TcpRtuClient


def _profile_choices() -> dict[str, str]:
    return choice_map()


class PoolHeatPumpConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._suggested: str | None = None
        self._profile: str = "mida_cosma_pc1002"
        self._detect_extra: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input:
            self._host = user_input[CONF_HOST]
            self._port = int(user_input[CONF_PORT])
            return await self.async_step_detect()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                }
            ),
            errors=errors,
        )

    async def async_step_detect(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._host is not None
        client = TcpRtuClient(self._host, self._port)
        try:
            suggested, extra = await detect_profile(client)
        except (OSError, DetectFailed):
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_HOST, default=self._host): str,
                        vol.Required(CONF_PORT, default=self._port): int,
                    }
                ),
                errors={"base": "cannot_connect"},
            )
        self._suggested = suggested
        self._detect_extra = extra
        return await self.async_step_profile()

    async def async_step_profile(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input:
            self._profile = user_input[CONF_PROFILE]
            return await self.async_step_options_setup()
        return self.async_show_form(
            step_id="profile",
            data_schema=vol.Schema(
                {vol.Required(CONF_PROFILE, default=self._suggested): vol.In(_profile_choices())}
            ),
            description_placeholders={
                "detect_note": detect_reason(self._suggested, self._detect_extra),
            },
        )

    async def async_step_options_setup(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        from .profiles import load_profile

        profile = load_profile(self._profile)
        driver = profile["driver"]["type"]
        if user_input:
            serial = None
            regs = self._detect_extra.get("broadcast") or {}
            if regs:
                from .profiles import decode_serial

                serial = decode_serial([regs.get(2001 + i, 0) for i in range(7)])
            unique = serial or f"{self._host}:{self._port}"
            await self.async_set_unique_id(unique)
            self._abort_if_unique_id_configured()
            data = {
                CONF_HOST: self._host,
                CONF_PORT: self._port,
            }
            options: dict[str, Any] = {CONF_PROFILE: self._profile}
            if CONF_WRITE_PATH in user_input:
                options[CONF_WRITE_PATH] = user_input[CONF_WRITE_PATH]
            if CONF_POLL_INTERVAL in user_input:
                options[CONF_POLL_INTERVAL] = user_input[CONF_POLL_INTERVAL]
            if CONF_POLL_SLAVE in user_input:
                options[CONF_POLL_SLAVE] = user_input[CONF_POLL_SLAVE]
            if CONF_SERVICE_MENU_WRITES in user_input:
                options[CONF_SERVICE_MENU_WRITES] = bool(user_input[CONF_SERVICE_MENU_WRITES])
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, DEFAULT_NAME),
                data=data,
                options=options,
            )

        schema: dict[Any, Any] = {vol.Required(CONF_NAME, default=DEFAULT_NAME): str}
        if driver == "pc1002_bus":
            paths = write_path_choices(profile)
            default_path = suggested_write_path(driver, self._detect_extra)
            if default_path not in paths:
                default_path = next(iter(paths), WRITE_PATH_DTU)
            schema[vol.Required(CONF_WRITE_PATH, default=default_path)] = vol.In(paths)
        elif driver == "poll_master":
            schema[vol.Required(CONF_POLL_INTERVAL, default=int(profile["driver"].get("poll_interval", 10)))] = int
            schema[vol.Required(CONF_POLL_SLAVE, default=int(profile["driver"].get("poll_slave", 1)))] = vol.All(
                int, vol.Range(min=1, max=247)
            )
        if driver != "listen_only":
            schema[vol.Required(CONF_SERVICE_MENU_WRITES, default=False)] = bool
        if driver == "listen_only":
            note = "Dump-only does not write or decode. Open the card Settings → Bus dump, then switch to a real profile."
        elif not self._detect_extra.get("slave99") and driver == "pc1002_bus":
            note = "No AquaTemp DTU on the bus — default write path is slave 2."
        else:
            note = ""
        return self.async_show_form(
            step_id="options_setup",
            data_schema=vol.Schema(schema),
            description_placeholders={"bus_note": note},
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input:
            host = user_input[CONF_HOST]
            port = int(user_input[CONF_PORT])
            try:
                await TcpRtuClient.probe(host, port)
            except OSError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_HOST: host, CONF_PORT: port},
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                    vol.Required(CONF_PORT, default=int(entry.data[CONF_PORT])): int,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PoolHeatPumpOptionsFlow()


class PoolHeatPumpOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        from .profiles import load_profile

        entry = self.config_entry
        if user_input:
            return self.async_create_entry(title="", data=merge_entry_options(entry.data, entry.options, user_input))
        current = resolve_profile_id(entry.options.get(CONF_PROFILE, entry.data.get(CONF_PROFILE)))
        profile = load_profile(current)
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_PROFILE,
                default=current,
            ): vol.In(_profile_choices())
        }
        driver = profile["driver"]["type"]
        if driver == "pc1002_bus":
            paths = write_path_choices(profile, short=True)
            default_path = entry.options.get(
                CONF_WRITE_PATH, entry.data.get(CONF_WRITE_PATH, WRITE_PATH_DTU)
            )
            if default_path not in paths:
                default_path = next(iter(paths), WRITE_PATH_DTU)
            schema[vol.Required(CONF_WRITE_PATH, default=default_path)] = vol.In(paths)
        elif driver == "poll_master":
            schema[
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=entry.options.get(CONF_POLL_INTERVAL, entry.data.get(CONF_POLL_INTERVAL, 10)),
                )
            ] = int
            schema[
                vol.Required(
                    CONF_POLL_SLAVE,
                    default=entry.options.get(
                        CONF_POLL_SLAVE,
                        entry.data.get(CONF_POLL_SLAVE, int(profile["driver"].get("poll_slave", 1))),
                    ),
                )
            ] = vol.All(int, vol.Range(min=1, max=247))
        if driver != "listen_only":
            schema[vol.Required(
                CONF_SERVICE_MENU_WRITES,
                default=entry.options.get(CONF_SERVICE_MENU_WRITES, entry.data.get(CONF_SERVICE_MENU_WRITES, False)),
            )] = bool
            schema[vol.Required(
                CONF_MANUAL_COP_FLOW,
                default=entry.options.get(CONF_MANUAL_COP_FLOW, entry.data.get(CONF_MANUAL_COP_FLOW, False)),
            )] = bool
            schema[vol.Required(
                CONF_WATER_FLOW_M3H,
                default=entry.options.get(CONF_WATER_FLOW_M3H, entry.data.get(CONF_WATER_FLOW_M3H, 0)),
            )] = vol.All(vol.Coerce(float), vol.Range(min=0, max=WATER_FLOW_MAX))
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
