"""Writes show immediately, get confirmed by the broadcast, or revert on timeout."""

from __future__ import annotations

import asyncio

import pytest
from spo_pool_heat_pump.drivers import pending as pending_mod
from spo_pool_heat_pump.drivers.pc1002_bus import PENDING_TTL_S, Pc1002BusDriver
from spo_pool_heat_pump.drivers.poll_master import PollMasterDriver, pending_ttl_for_interval
from spo_pool_heat_pump.modbus_rtu import encode_fc03_reply, encode_fc16, parse_frame
from spo_pool_heat_pump.profiles import load_profile, profile_polls


def broadcast(*, power: int = 1, mode: int = 1, setpoint: int = 280, silent: int = 0) -> bytes:
    values = [0] * 90
    values[2011 - 2001] = power
    values[2012 - 2001] = mode
    values[2013 - 2001] = setpoint
    values[2064 - 2001] = silent
    values[2046 - 2001] = 250  # inlet
    return encode_fc16(0, 2001, values)


def make_driver(send=None) -> tuple[Pc1002BusDriver, list]:
    sent: list[bytes] = []
    published: list = []

    async def _send(frame: bytes) -> None:
        sent.append(frame)

    # dtu_99 sends one frame and needs no seeded pages — the pending overlay is path-agnostic;
    # the slave-2 handshake itself is covered in test_slave2_panel.py.
    driver = Pc1002BusDriver(load_profile("mida_cosma_pc1002"), send or _send, "dtu_99", on_state=published.append)
    driver.handle_frame(broadcast())
    assert driver.state.available
    assert driver.state.silent is False
    published.clear()
    return driver, published


def test_silent_shows_immediately_then_confirms() -> None:
    driver, published = make_driver()
    asyncio.run(driver.set_silent(True))
    # Published right after the write, before any broadcast.
    assert published, "write must republish state"
    assert driver.state.silent is True
    assert driver.state.pending == ["silent"]

    # Device has not caught up yet (old value in the broadcast) — keep optimistic.
    driver.handle_frame(broadcast(silent=0))
    assert driver.state.silent is True
    assert driver.state.pending == ["silent"]

    # Device echoes the write — confirmed, no longer pending.
    driver.handle_frame(broadcast(silent=1))
    assert driver.state.silent is True
    assert driver.state.pending == []


def test_unconfirmed_write_reverts_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    driver, _ = make_driver()
    now = [1000.0]
    monkeypatch.setattr(pending_mod.time, "monotonic", lambda: now[0])
    asyncio.run(driver.set_silent(True))
    assert driver.state.silent is True

    now[0] += PENDING_TTL_S - 1
    driver.handle_frame(broadcast(silent=0))
    assert driver.state.silent is True, "still inside the TTL"

    now[0] += 2
    driver.handle_frame(broadcast(silent=0))
    assert driver.state.silent is False, "device value wins after the TTL"
    assert driver.state.pending == []


def test_page_only_values_get_the_longer_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mode lives in page word 1012 and is confirmed by the board's page push, which
    lands ~8-10 s after the write; it must outlive the 12 s broadcast TTL."""
    from spo_pool_heat_pump.drivers.pending import PAGE_TTL_S

    driver, _ = make_driver()
    now = [1000.0]
    monkeypatch.setattr(pending_mod.time, "monotonic", lambda: now[0])
    asyncio.run(driver.set_mode("auto"))
    assert driver.state.mode == "auto"

    now[0] += PENDING_TTL_S + 1
    driver.handle_frame(broadcast())
    assert driver.state.mode == "auto", "page-confirmed value still inside its TTL"
    assert "mode" in driver.state.pending

    now[0] += PAGE_TTL_S - PENDING_TTL_S
    driver.handle_frame(broadcast())
    assert driver.state.mode == "heat", "device value wins after the page TTL"
    assert driver.state.pending == []


def test_setpoint_and_mode_optimistic() -> None:
    driver, _ = make_driver()
    asyncio.run(driver.set_setpoint(30.0))
    assert driver.state.setpoint == 30.0
    assert "setpoint" in driver.state.pending
    driver.handle_frame(broadcast(setpoint=280))
    assert driver.state.setpoint == 30.0
    driver.handle_frame(broadcast(setpoint=300))
    assert driver.state.setpoint == 30.0
    assert "setpoint" not in driver.state.pending

    asyncio.run(driver.set_power(False))
    assert driver.state.power is False
    driver.handle_frame(broadcast(power=0, setpoint=300))
    assert driver.state.power is False
    assert driver.state.pending == []


def test_failed_send_does_not_show_optimistic_value() -> None:
    async def broken(_frame: bytes) -> None:
        raise OSError("tcp down")

    driver, _ = make_driver(send=broken)
    with pytest.raises(OSError):
        asyncio.run(driver.set_silent(True))
    assert driver.state.silent is False
    assert driver.state.pending == []


def test_accepted_write_keeps_pending_if_extra_register_fails() -> None:
    calls = 0

    async def flaky(_frame: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("tcp down on extra")

    driver, _ = make_driver(send=flaky)
    with pytest.raises(OSError):
        asyncio.run(driver.set_power(False))
    assert driver.state.power is False
    assert "power" in driver.state.pending


def _poll_master_with_state() -> tuple[PollMasterDriver, list, list]:
    """Fairland CN13 driver after one full poll cycle (silent off, power on)."""
    sent: list[bytes] = []
    published: list = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    profile = load_profile("fairland_pc1004_cn13")
    driver = PollMasterDriver(profile, send, on_state=published.append)
    polls = profile_polls(profile)
    for i, spec in enumerate(polls):
        driver._awaiting = i
        qty = int(spec["qty"])
        words = [0] * qty
        if int(spec["start"]) == 2011:
            words[0] = 1  # power on
            words[2013 - 2011] = 280
        driver.handle_frame(encode_fc03_reply(50, words))
    assert driver.state.available
    assert driver.state.silent is False
    published.clear()
    sent.clear()
    return driver, sent, published


def test_poll_master_write_is_optimistic_until_next_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    driver, sent, published = _poll_master_with_state()
    now = [500.0]
    monkeypatch.setattr(pending_mod.time, "monotonic", lambda: now[0])
    asyncio.run(driver.set_silent(True))
    assert [parse_frame(f).start for f in sent] == [1076]
    assert published, "state republished right after the write"
    assert driver.state.silent is True
    assert driver.state.pending == ["silent"]

    # Next poll cycle still reports the old value: hold.
    polls = profile_polls(driver.profile)
    for i, spec in enumerate(polls):
        driver._awaiting = i
        words = [0] * int(spec["qty"])
        if int(spec["start"]) == 2011:
            words[0] = 1
        driver.handle_frame(encode_fc03_reply(50, words))
    assert driver.state.silent is True

    # Cycle that echoes it: confirmed.
    for i, spec in enumerate(polls):
        driver._awaiting = i
        words = [0] * int(spec["qty"])
        if int(spec["start"]) == 2011:
            words[0] = 1
            words[2064 - 2011] = 1
        driver.handle_frame(encode_fc03_reply(50, words))
    assert driver.state.silent is True
    assert driver.state.pending == []


def test_poll_master_ttl_scales_with_interval() -> None:
    assert pending_ttl_for_interval(1) == PENDING_TTL_S
    assert pending_ttl_for_interval(10) == 24.0
    driver, _, _ = _poll_master_with_state()
    assert driver.pending.ttl_s == 24.0  # profile default poll_interval 10
    driver.set_poll_interval(30)
    assert driver.pending.ttl_s == 64.0


def test_write_frame_still_sent_once() -> None:
    driver, _ = make_driver()
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    driver._send = send
    asyncio.run(driver.set_silent(True))
    assert [parse_frame(f).start for f in sent] == [1076]
