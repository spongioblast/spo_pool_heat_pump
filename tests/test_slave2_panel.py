"""Home Assistant as the second display panel (slave 2) on a board-master PC1002 bus.

Shapes taken from the live capture 2026-09-14 10:33 (MIDA Cosma, no WiFi module):
per cycle the board polls 66/1/2 for 3001×30, pushes 1001/1091/1181 ×90 and
3001×11 to slave 2, then broadcasts 2001×90. The wired display raises 3011 =
0x0004 / 0x0020 and the board reads the page back ~0.35 s later.
"""

from __future__ import annotations

import asyncio

import pytest
from spo_pool_heat_pump.const import (
    WRITE_PATH_SLAVE2,
    suggested_write_path,
    write_path_choices,
)
from spo_pool_heat_pump.drivers import slave2 as slave2_mod
from spo_pool_heat_pump.drivers.pc1002_bus import Pc1002BusDriver
from spo_pool_heat_pump.drivers.slave2 import (
    FLAG_HEAT_SP,
    FLAG_READ_1001,
    FLAG_READ_1091,
    OVERLAY_TTL_S,
)
from spo_pool_heat_pump.modbus_rtu import (
    encode_fc03,
    encode_fc03_reply,
    encode_fc16,
    parse_frame,
)
from spo_pool_heat_pump.profiles import load_profile

SERIAL = [
    0x4239,
    0x3932,
    0x3630,
    0x3431,
    0x3335,
    0x3233,
    0x3200,
    0x0000,
    0x0101,
    0x0BB9,
]


def page_1001(**regs: int) -> list[int]:
    values = [0] * 90
    values[1011 - 1001] = 1  # power on
    values[1012 - 1001] = 1  # heat
    values[1013 - 1001] = 295
    for reg, val in regs.items():
        values[int(reg[1:]) - 1001] = val
    return values


def broadcast(**regs: int) -> bytes:
    values = [0] * 90
    values[0:10] = SERIAL
    values[2011 - 2001] = 1
    values[2012 - 2001] = 1
    values[2013 - 2001] = 295
    values[2046 - 2001] = 290
    for reg, val in regs.items():
        values[int(reg[1:]) - 2001] = val
    return encode_fc16(0, 2001, values)


def board_cycle(
    driver: Pc1002BusDriver, p1001: list[int], flags_word: int = 0
) -> dict[str, list[bytes]]:
    """Feed one board cycle; return every reply HA produced, keyed by what triggered it."""
    out: dict[str, list[bytes]] = {}

    def feed(key: str, frame: bytes) -> None:
        reply = driver.handle_frame(frame)
        if reply:
            out.setdefault(key, []).append(reply)

    feed("poll66", encode_fc03(66, 1, 100))
    feed("poll1", encode_fc03(1, 3001, 30))
    feed("reply1", encode_fc03_reply(1, SERIAL + [0, 0, 0xF500] + [0] * 17))
    feed("poll2", encode_fc03(2, 3001, 30))
    for start, page in ((1001, p1001), (1091, [5] * 90), (1181, [6] * 90)):
        feed(f"push{start}", encode_fc16(2, start, page))
        feed(f"push{start}", encode_fc16(2, start, page))
    sync = SERIAL + [flags_word]
    feed("push3001", encode_fc16(2, 3001, sync))
    feed("push3001", encode_fc16(2, 3001, sync))
    feed("broadcast", broadcast())
    return out


def make_driver() -> tuple[Pc1002BusDriver, list[bytes]]:
    sent: list[bytes] = []

    async def send(frame: bytes) -> None:
        sent.append(frame)

    driver = Pc1002BusDriver(load_profile("mida_cosma_pc1002"), send, WRITE_PATH_SLAVE2)
    return driver, sent


def test_board_page_pushes_are_acked_like_a_real_panel() -> None:
    driver, _ = make_driver()
    replies = board_cycle(driver, page_1001())
    for start, qty in ((1001, 90), (1091, 90), (1181, 90), (3001, 11)):
        acks = replies[f"push{start}"]
        assert len(acks) == 2, f"both pushes of {start} must be acked"
        for ack in acks:
            parsed = parse_frame(ack)
            assert parsed is not None
            assert (parsed.slave, parsed.function, parsed.start, parsed.qty) == (
                2,
                16,
                start,
                qty,
            )
            assert parsed.values == []  # FC16 echo carries no data
    # The broadcast (slave 0) and the slave-1 poll are not ours to answer.
    assert "broadcast" not in replies
    assert "poll1" not in replies
    assert "reply1" not in replies
    assert "poll66" not in replies


def test_slave2_poll_is_answered_with_serial_and_zero_flags() -> None:
    driver, _ = make_driver()
    replies = board_cycle(driver, page_1001())
    parsed = parse_frame(replies["poll2"][0])
    assert parsed is not None and parsed.slave == 2 and parsed.kind == "reply"
    assert parsed.values[0:10] == SERIAL
    assert parsed.values[10] == 0, "no change queued → no flag"


def test_write_raises_exact_display_flag_and_survives_old_page_push() -> None:
    driver, _ = make_driver()
    board_cycle(driver, page_1001())
    asyncio.run(driver.set_silent(True))  # 1076 lives in page 1001

    # Cycle 1: board polls us → flag 0x0004, nothing else set (0x8000 never).
    poll = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
    assert poll.values[10] == FLAG_READ_1001 == 0x0004

    # Board reads the page back: our value is in it, flag drops (like the display).
    page = parse_frame(driver.handle_frame(encode_fc03(2, 1001, 90)))
    assert page is not None and page.values[1076 - 1001] == 1
    assert driver.slave2.flags_3011 == 0
    driver.handle_frame(encode_fc16(2, 3001, SERIAL + [0]))  # board: got it
    poll = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
    assert poll.values[10] == 0

    # Board is still pushing the OLD page this cycle — must not wipe the queued value.
    driver.handle_frame(encode_fc16(2, 1001, page_1001(r1076=0)))
    assert driver.slave2.block_1001[1076 - 1001] == 1
    assert driver.slave2.pending_registers == [1076]
    assert driver.state.silent is True  # optimistic, pending

    # Board applied it: pushes the page with our value → overlay confirmed and gone.
    driver.handle_frame(encode_fc16(2, 1001, page_1001(r1076=1)))
    assert driver.slave2.pending_registers == []
    driver.handle_frame(broadcast(r2064=1))
    assert driver.state.silent is True
    assert driver.state.pending == []


def test_page_1091_writes_use_0x0020_and_setpoint_heat_0x0040() -> None:
    driver, _ = make_driver()
    board_cycle(driver, page_1001())
    driver.slave2.queue_write(1150, 7)
    assert driver.slave2.flags_3011 == FLAG_READ_1091 == 0x0020
    driver.slave2.queue_write(1136, 300)
    assert driver.slave2.flags_3011 == FLAG_READ_1091 | FLAG_HEAT_SP
    assert driver.slave2.flags_3011 & 0x8000 == 0
    page = parse_frame(driver.handle_frame(encode_fc03(2, 1091, 90)))
    assert page.values[1150 - 1091] == 7
    assert page.values[1136 - 1091] == 300
    assert driver.slave2.flags_3011 == 0


def test_board_echoing_our_bit_after_the_read_triggers_one_retry() -> None:
    """Live captures 2026-09-14 11:51 / 12:24: when the board's read of our page did
    not get through, its 3001 sync 0.02–0.34 s later echoes our bit instead of 0 and it
    falls back to the wired display's page. Raise the bit again at the next poll."""
    driver, _ = make_driver()
    board_cycle(driver, page_1001())
    asyncio.run(driver.set_mode("auto"))
    driver.handle_frame(encode_fc03(2, 3001, 30))
    driver.handle_frame(encode_fc03(2, 1001, 90))  # our reply is lost on the way
    assert driver.slave2.flags_3011 == 0, "dropped on send, like the display"
    driver.handle_frame(encode_fc16(2, 3001, SERIAL + [FLAG_READ_1001]))  # echo
    poll = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
    assert poll.values[10] == FLAG_READ_1001, "asking to be read again"
    page = parse_frame(driver.handle_frame(encode_fc03(2, 1001, 90)))
    assert page.values[1012 - 1001] == 2
    assert driver.slave2.flags_3011 == 0
    driver.handle_frame(encode_fc16(2, 3001, SERIAL + [0]))  # board: got it this time
    poll = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
    assert poll.values[10] == 0


def test_no_parsable_sync_after_the_read_also_triggers_a_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live 2026-09-14 15:13: the board's sync after a failed read arrived truncated
    (28 of 31 B) and never parsed, so an echo-only trigger missed it."""
    driver, _ = make_driver()
    board_cycle(driver, page_1001())
    now = [100.0]
    monkeypatch.setattr(slave2_mod.time, "monotonic", lambda: now[0])
    driver.slave2.queue_write(1076, 1)
    driver.handle_frame(encode_fc03(2, 3001, 30))
    driver.handle_frame(encode_fc03(2, 1001, 90))
    now[0] += 0.5  # a poll this early is not conclusive yet
    poll = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
    assert poll.values[10] == 0
    now[0] += 0.7  # next poll, 1.2 s after the read, still no sync
    poll = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
    assert poll.values[10] == FLAG_READ_1001
    driver.handle_frame(encode_fc03(2, 1001, 90))
    now[0] += 0.85
    driver.handle_frame(encode_fc16(2, 3001, SERIAL + [0]))  # clean ack this time
    now[0] += 5
    poll = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
    assert poll.values[10] == 0


def test_read_retries_are_bounded() -> None:
    driver, _ = make_driver()
    board_cycle(driver, page_1001())
    driver.slave2.queue_write(1076, 1)
    raised = 0
    for _ in range(5):
        poll = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
        if poll.values[10] & FLAG_READ_1001:
            raised += 1
        driver.handle_frame(encode_fc03(2, 1001, 90))
        driver.handle_frame(encode_fc16(2, 3001, SERIAL + [FLAG_READ_1001]))
    assert raised == 1 + slave2_mod.MAX_READ_RETRIES
    assert driver.slave2.pending_registers == [1076], "value still overlaid until TTL"


def test_successful_sync_does_not_cause_a_retry() -> None:
    driver, _ = make_driver()
    board_cycle(driver, page_1001())
    driver.slave2.queue_write(1076, 1)
    driver.handle_frame(encode_fc03(2, 3001, 30))
    driver.handle_frame(encode_fc03(2, 1001, 90))
    driver.handle_frame(encode_fc16(2, 3001, SERIAL + [0]))
    for _ in range(3):
        poll = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
        assert poll.values[10] == 0


def test_expired_or_confirmed_overlay_drops_a_pending_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver, _ = make_driver()
    board_cycle(driver, page_1001())
    now = [100.0]
    monkeypatch.setattr(slave2_mod.time, "monotonic", lambda: now[0])
    driver.slave2.queue_write(1076, 1)
    driver.handle_frame(encode_fc03(2, 1001, 90))
    driver.handle_frame(encode_fc16(2, 3001, SERIAL + [FLAG_READ_1001]))  # echo
    now[0] += OVERLAY_TTL_S + 1
    poll = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
    assert poll.values[10] == 0, "expired write must not be retried"
    # Confirmation by page push also cancels a retry.
    driver.slave2.queue_write(1076, 1)
    driver.handle_frame(encode_fc03(2, 1001, 90))
    driver.handle_frame(encode_fc16(2, 3001, SERIAL + [FLAG_READ_1001]))
    driver.handle_frame(encode_fc16(2, 1001, page_1001(r1076=1)))
    poll = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
    assert poll.values[10] == 0


def test_second_panel_never_reads_the_display_on_its_own() -> None:
    """The board's 3001 sync to us echoes our flags; it must not look like a display
    change and trigger a FC03 from HA (a second master on the board's bus)."""
    driver, sent = make_driver()
    board_cycle(driver, page_1001())
    driver.slave2.queue_write(1076, 1)
    driver.handle_frame(encode_fc03(2, 1001, 90))
    driver.handle_frame(encode_fc16(2, 3001, SERIAL + [FLAG_READ_1001]))
    assert asyncio.run(driver.after_frame()) is None
    # Even a real display flag change is not re-read on this path: the board pushes pages.
    driver.handle_frame(encode_fc03(1, 3001, 30))
    driver.handle_frame(
        encode_fc03_reply(1, SERIAL + [FLAG_READ_1001, 0, 0xF500] + [0] * 17)
    )
    driver.handle_frame(encode_fc03(1, 3001, 30))
    driver.handle_frame(encode_fc03_reply(1, SERIAL + [0, 0, 0xF500] + [0] * 17))
    assert asyncio.run(driver.after_frame()) is None
    assert sent == []


def test_rejected_write_expires_from_our_page(monkeypatch: pytest.MonkeyPatch) -> None:
    driver, _ = make_driver()
    board_cycle(driver, page_1001())
    now = [100.0]
    monkeypatch.setattr(slave2_mod.time, "monotonic", lambda: now[0])
    driver.slave2.queue_write(1076, 1)
    now[0] += OVERLAY_TTL_S - 1
    assert driver.slave2.block_1001[1076 - 1001] == 1
    now[0] += 2
    driver.handle_frame(encode_fc16(2, 1001, page_1001(r1076=0)))
    assert driver.slave2.block_1001[1076 - 1001] == 0, (
        "board's value wins after the TTL"
    )
    assert driver.slave2.pending_registers == []


def test_board_3001_sync_does_not_clear_a_flag_it_has_not_served() -> None:
    driver, _ = make_driver()
    board_cycle(driver, page_1001())
    driver.slave2.queue_write(1076, 1)
    # Board writes 3001×11 with flags 0 before it got round to reading our page.
    driver.handle_frame(encode_fc16(2, 3001, SERIAL + [0]))
    poll = parse_frame(driver.handle_frame(encode_fc03(2, 3001, 30)))
    assert poll.values[0:10] == SERIAL
    assert poll.values[10] == FLAG_READ_1001


def test_failed_send_discards_slave2_overlay() -> None:
    async def broken(_frame: bytes) -> None:
        raise OSError("tcp down")

    driver = Pc1002BusDriver(
        load_profile("mida_cosma_pc1002"), broken, WRITE_PATH_SLAVE2
    )
    board_cycle(driver, page_1001())
    # slave2 path never touches the socket in write_register; emulate a later failure path
    driver.slave2.queue_write(1076, 1)
    driver.slave2.discard_write(1076)
    assert driver.slave2.pending_registers == []
    assert driver.slave2.block_1001[1076 - 1001] == 0


def test_second_panel_is_the_default_write_path() -> None:
    for pid in ("mida_cosma_pc1002", "hayward_pc1002", "phnix_mini_pc1002"):
        profile = load_profile(pid)
        assert suggested_write_path("pc1002_bus", {}, profile) == WRITE_PATH_SLAVE2
        assert (
            suggested_write_path("pc1002_bus", {"slave99": True}, profile)
            == WRITE_PATH_SLAVE2
        )
        assert next(iter(write_path_choices(profile))) == WRITE_PATH_SLAVE2
    assert suggested_write_path("pc1002_bus", {}) == WRITE_PATH_SLAVE2
    pinned = {"driver": {"default_write": "dtu_99"}}
    assert suggested_write_path("pc1002_bus", {}, pinned) == "dtu_99"


def _page_1091(heat: int) -> list[int]:
    values = [5] * 90
    values[1135 - 1091] = 245
    values[1136 - 1091] = heat
    values[1137 - 1091] = 300
    return values


def test_setpoint_accepted_by_page_push_does_not_revert_while_2013_lags(monkeypatch) -> None:
    """Live bus 2026-09-14, 36→35: page 1091 pushed back with 1136=35 at +8.6 s,
    broadcast 2013 still 36 until +21 s. The card must not fall back to 36 in
    between, and must stop pulsing once the page proves the board took it."""
    from spo_pool_heat_pump.drivers import pending as pending_mod

    now = [1000.0]
    monkeypatch.setattr(pending_mod.time, "monotonic", lambda: now[0])
    driver, _ = make_driver()
    board_cycle(driver, page_1001())
    driver.handle_frame(encode_fc16(2, 1091, _page_1091(340)))
    driver.handle_frame(broadcast(r2013=340))
    assert driver.state.mode == "heat" and driver.state.setpoint == 34.0

    asyncio.run(driver.set_setpoint(32.0))
    assert driver.state.setpoint == 32.0 and driver.state.pending == ["setpoint"]

    now[0] += 4
    driver.handle_frame(broadcast(r2013=340))  # broadcast has not moved yet
    assert driver.state.setpoint == 32.0 and driver.state.pending == ["setpoint"]

    now[0] += 4.6
    driver.handle_frame(encode_fc16(2, 1091, _page_1091(320)))  # board pushes our value back
    assert driver.state.setpoint_heat == 32.0
    assert driver.state.setpoint == 32.0
    assert driver.state.pending == [], "accepted by the board: stop pulsing"

    now[0] += 5  # 13.6 s after the write: past the old 12 s TTL
    driver.handle_frame(broadcast(r2013=340))  # 2013 still lags
    assert driver.state.setpoint == 32.0, "must not snap back to 34"
    assert driver.state.pending == []

    now[0] += 7.4  # 21 s after the write
    driver.handle_frame(broadcast(r2013=320))
    assert driver.state.setpoint == 32.0 and driver.state.pending == []
    assert len(driver.pending) == 0


def test_setpoint_without_any_echo_still_reverts_and_warns(monkeypatch, caplog) -> None:
    from spo_pool_heat_pump.drivers import pending as pending_mod
    from spo_pool_heat_pump.drivers.pending import PAGE_TTL_S

    now = [1000.0]
    monkeypatch.setattr(pending_mod.time, "monotonic", lambda: now[0])
    driver, _ = make_driver()
    board_cycle(driver, page_1001())
    driver.handle_frame(encode_fc16(2, 1091, _page_1091(340)))
    driver.handle_frame(broadcast(r2013=340))
    asyncio.run(driver.set_setpoint(32.0))

    now[0] += PAGE_TTL_S - 1
    driver.handle_frame(broadcast(r2013=340))
    assert driver.state.setpoint == 32.0, "page window not over yet"
    now[0] += 2
    with caplog.at_level("WARNING"):
        driver.handle_frame(broadcast(r2013=340))
    assert driver.state.setpoint == 34.0 and driver.state.pending == []
    assert "not confirmed" in caplog.text


def test_setpoint_accepted_but_2013_never_follows_lets_go_quietly(monkeypatch, caplog) -> None:
    from spo_pool_heat_pump.drivers import pending as pending_mod
    from spo_pool_heat_pump.drivers.pending import PAGE_TTL_S

    now = [1000.0]
    monkeypatch.setattr(pending_mod.time, "monotonic", lambda: now[0])
    driver, _ = make_driver()
    board_cycle(driver, page_1001())
    driver.handle_frame(encode_fc16(2, 1091, _page_1091(340)))
    driver.handle_frame(broadcast(r2013=340))
    asyncio.run(driver.set_setpoint(32.0))
    now[0] += 8
    driver.handle_frame(encode_fc16(2, 1091, _page_1091(320)))
    assert driver.state.pending == []
    now[0] += PAGE_TTL_S + 1
    with caplog.at_level("WARNING"):
        driver.handle_frame(broadcast(r2013=340))
    assert driver.state.setpoint == 34.0
    assert "not confirmed" not in caplog.text
