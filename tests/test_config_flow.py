"""Mocked config-flow coverage. Skip if HA cannot import."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ha = pytest.importorskip("homeassistant")

import voluptuous as vol  # noqa: E402
from homeassistant.const import CONF_HOST  # noqa: E402
from homeassistant.data_entry_flow import AbortFlow  # noqa: E402

from spo_pool_heat_pump.config_flow import PoolHeatPumpConfigFlow  # noqa: E402
from spo_pool_heat_pump.const import (  # noqa: E402
    CONF_NAME,
    CONF_POLL_INTERVAL,
    CONF_POLL_SLAVE,
    CONF_PORT,
    CONF_PROFILE,
    CONF_SERVICE_MENU_WRITES,
    CONF_WRITE_PATH,
)


def _hass() -> MagicMock:
    hass = MagicMock()

    async def run_job(func, *args):
        return func(*args)

    hass.async_add_executor_job = run_job
    return hass


def _flow() -> PoolHeatPumpConfigFlow:
    flow = PoolHeatPumpConfigFlow()
    flow.hass = _hass()
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


def test_cannot_connect_returns_user_form() -> None:
    async def run() -> None:
        flow = _flow()
        with (
            patch("spo_pool_heat_pump.config_flow.TcpRtuClient"),
            patch(
                "spo_pool_heat_pump.config_flow.detect_profile",
                AsyncMock(side_effect=OSError("down")),
            ),
        ):
            result = await flow.async_step_user({CONF_HOST: "10.0.0.8", CONF_PORT: 8899})
        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert result["errors"] == {"base": "cannot_connect"}

    asyncio.run(run())


def test_cosma_create_puts_settings_in_options() -> None:
    async def run() -> None:
        flow = _flow()
        flow._host = "10.0.0.8"
        flow._port = 8899
        flow._profile = "mida_cosma_pc1002"
        flow._detect_extra = {"slave99": True}
        result = await flow.async_step_options_setup(
            {
                CONF_NAME: "Pool",
                CONF_WRITE_PATH: "dtu_99",
                CONF_SERVICE_MENU_WRITES: False,
            }
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "Pool"
        assert result["data"] == {CONF_HOST: "10.0.0.8", CONF_PORT: 8899}
        assert result["options"][CONF_PROFILE] == "mida_cosma_pc1002"
        assert result["options"][CONF_WRITE_PATH] == "dtu_99"
        assert result["options"][CONF_SERVICE_MENU_WRITES] is False
        assert CONF_NAME not in result["data"]
        assert CONF_PROFILE not in result["data"]
        flow.async_set_unique_id.assert_awaited_once_with("10.0.0.8:8899")

    asyncio.run(run())


def test_cosma_form_defaults_to_dtu_even_when_slave99_not_heard() -> None:
    async def run() -> None:
        flow = _flow()
        flow._host = "10.0.0.8"
        flow._port = 8899
        flow._profile = "mida_cosma_pc1002"
        flow._detect_extra = {"broadcast": {}, "fw_display": 713}
        form = await flow.async_step_options_setup()
        assert form["type"] == "form"
        defaults = {key.schema: key.default() for key in form["data_schema"].schema if key.default is not vol.UNDEFINED}
        assert defaults[CONF_WRITE_PATH] == "dtu_99"
        note = form["description_placeholders"]["bus_note"]
        assert "does not prove" in note
        assert "slave 2" not in note.lower()

        flow._detect_extra = {"broadcast": {}, "fw_display": 713, "slave99": True}
        form = await flow.async_step_options_setup()
        assert "Heard" in form["description_placeholders"]["bus_note"]

    asyncio.run(run())


def test_dump_only_create_omits_write_path() -> None:
    async def run() -> None:
        flow = _flow()
        flow._host = "10.0.0.8"
        flow._port = 8899
        flow._profile = "unknown_dump_only"
        flow._detect_extra = {"dump_only": True}
        form = await flow.async_step_options_setup()
        assert form["type"] == "form"
        names = [key.schema for key in form["data_schema"].schema]
        assert CONF_NAME in names
        assert CONF_WRITE_PATH not in names
        assert CONF_SERVICE_MENU_WRITES not in names
        result = await flow.async_step_options_setup({CONF_NAME: "Unknown"})
        assert result["type"] == "create_entry"
        assert result["data"] == {CONF_HOST: "10.0.0.8", CONF_PORT: 8899}
        assert result["options"] == {CONF_PROFILE: "unknown_dump_only"}
        assert CONF_WRITE_PATH not in result["options"]
        assert CONF_SERVICE_MENU_WRITES not in result["options"]

    asyncio.run(run())


def test_cn13_create_stores_poll_in_options() -> None:
    async def run() -> None:
        flow = _flow()
        flow._host = "10.0.0.8"
        flow._port = 8899
        flow._profile = "fairland_pc1004_cn13"
        flow._detect_extra = {"slave50": True}
        result = await flow.async_step_options_setup(
            {
                CONF_NAME: "CN13",
                CONF_POLL_INTERVAL: 12,
                CONF_POLL_SLAVE: 50,
                CONF_SERVICE_MENU_WRITES: False,
            }
        )
        assert result["type"] == "create_entry"
        assert result["data"] == {CONF_HOST: "10.0.0.8", CONF_PORT: 8899}
        assert result["options"][CONF_POLL_SLAVE] == 50
        assert result["options"][CONF_POLL_INTERVAL] == 12
        assert CONF_WRITE_PATH not in result["options"]

    asyncio.run(run())


def test_unique_id_abort() -> None:
    async def run() -> None:
        flow = _flow()
        flow._host = "10.0.0.8"
        flow._port = 8899
        flow._profile = "mida_cosma_pc1002"
        flow._detect_extra = {}
        flow._abort_if_unique_id_configured = MagicMock(side_effect=AbortFlow("already_configured"))
        with pytest.raises(AbortFlow, match="already_configured"):
            await flow.async_step_options_setup(
                {CONF_NAME: "Pool", CONF_WRITE_PATH: "dtu_99", CONF_SERVICE_MENU_WRITES: False}
            )

    asyncio.run(run())


def test_reconfigure_updates_host() -> None:
    async def run() -> None:
        flow = _flow()
        entry = MagicMock()
        entry.data = {CONF_HOST: "10.0.0.8", CONF_PORT: 8899}
        entry.unique_id = "10.0.0.8:8899"
        flow._get_reconfigure_entry = MagicMock(return_value=entry)
        flow.async_update_and_abort = MagicMock(
            return_value={"type": "abort", "reason": "reconfigure_successful"}
        )
        form = await flow.async_step_reconfigure()
        assert form["type"] == "form"
        assert form["step_id"] == "reconfigure"
        with patch("spo_pool_heat_pump.config_flow.TcpRtuClient.probe", AsyncMock()):
            result = await flow.async_step_reconfigure({CONF_HOST: "10.0.0.9", CONF_PORT: 8899})
        assert result["reason"] == "reconfigure_successful"
        flow.async_update_and_abort.assert_called_once()
        kwargs = flow.async_update_and_abort.call_args
        assert kwargs.args[0] is entry
        assert kwargs.kwargs["data_updates"] == {CONF_HOST: "10.0.0.9", CONF_PORT: 8899}
        assert kwargs.kwargs["unique_id"] == "10.0.0.9:8899"

    asyncio.run(run())


def test_reconfigure_serial_unique_id_unchanged() -> None:
    async def run() -> None:
        flow = _flow()
        entry = MagicMock()
        entry.data = {CONF_HOST: "10.0.0.8", CONF_PORT: 8899}
        entry.unique_id = "B992604135232"
        flow._get_reconfigure_entry = MagicMock(return_value=entry)
        flow.async_update_and_abort = MagicMock(
            return_value={"type": "abort", "reason": "reconfigure_successful"}
        )
        with patch("spo_pool_heat_pump.config_flow.TcpRtuClient.probe", AsyncMock()):
            await flow.async_step_reconfigure({CONF_HOST: "10.0.0.9", CONF_PORT: 8899})
        kwargs = flow.async_update_and_abort.call_args.kwargs
        assert "unique_id" not in kwargs
        assert kwargs["data_updates"] == {CONF_HOST: "10.0.0.9", CONF_PORT: 8899}

    asyncio.run(run())


def test_suggested_object_id_is_suffix_only() -> None:
    from spo_pool_heat_pump.entity import suggested_object_id

    assert suggested_object_id("inlet") == "inlet"
    assert suggested_object_id("quiet") == "quiet"
    assert suggested_object_id() == "pool_heat_pump"


def test_reconfigure_cannot_connect() -> None:
    async def run() -> None:
        flow = _flow()
        entry = MagicMock()
        entry.data = {CONF_HOST: "10.0.0.8", CONF_PORT: 8899}
        flow._get_reconfigure_entry = MagicMock(return_value=entry)
        with patch(
            "spo_pool_heat_pump.config_flow.TcpRtuClient.probe",
            AsyncMock(side_effect=OSError("down")),
        ):
            result = await flow.async_step_reconfigure({CONF_HOST: "10.0.0.9", CONF_PORT: 8899})
        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure"
        assert result["errors"] == {"base": "cannot_connect"}

    asyncio.run(run())
