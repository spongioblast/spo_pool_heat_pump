"""Persistent settings overlay (write-only 10xx / sniffed 1001+1091+1181+3001).

FC03 replies have no start address in the PDU. The cache therefore arms a
pending (slave, start, qty) from the request (or from expect_reply) and only
absorbs a later reply whose slave matches and whose value count equals qty.
A board 3001 poll between our 1001 request and reply must not land in page_3001.
"""

from __future__ import annotations

from ..modbus_rtu import RtuFrame, parse_frame

SETTINGS_PAGES = (1001, 1091, 1181, 3001)


class SettingsCache:
    """Register values that do not live on the 2001 status page."""

    def __init__(self, broadcast_start: int = 2001) -> None:
        self.regs: dict[int, int] = {}
        self._pending: tuple[int | None, int, int | None] | None = None
        self.page_3001: list[int] | None = None
        self._matched: tuple[int, list[int]] | None = None
        self._broadcast_start = broadcast_start

    def put(self, register: int, value: int) -> bool:
        value = int(value) & 0xFFFF
        if self.regs.get(register) == value:
            return False
        self.regs[register] = value
        return True

    def expect_reply(self, start: int, slave: int | None = None, qty: int | None = None) -> None:
        self._pending = (slave, start, qty)
        self._matched = None

    def take_page(self) -> tuple[int, list[int]] | None:
        matched = self._matched
        self._matched = None
        return matched

    def absorb_fc16(self, frame: bytes) -> bool:
        parsed = parse_frame(frame)
        return self.absorb_frame(parsed) if parsed else False

    def absorb_fc03_reply(self, start: int, values: list[int]) -> bool:
        if start == 3001:
            self.page_3001 = list(values)
        changed = False
        for i, val in enumerate(values):
            if self.put(start + i, val):
                changed = True
        return changed

    def absorb_frame(self, parsed: RtuFrame) -> bool:
        if parsed.function == 16 and parsed.start is not None and parsed.values:
            if parsed.slave == 0 and parsed.start == self._broadcast_start:
                return False
            return self.absorb_fc03_reply(parsed.start, parsed.values)
        if parsed.function == 6 and parsed.start is not None and parsed.values:
            return self.put(parsed.start, parsed.values[0])
        if parsed.function == 3 and parsed.kind == "request" and parsed.start in SETTINGS_PAGES:
            self._pending = (parsed.slave, parsed.start, parsed.qty)
            return False
        if parsed.function == 3 and parsed.kind == "reply" and self._pending is not None:
            slave, start, qty = self._pending
            if slave is not None and parsed.slave != slave:
                return False
            if qty is not None and len(parsed.values) != qty:
                return False
            self._pending = None
            values = list(parsed.values)
            self._matched = (start, values)
            return self.absorb_fc03_reply(start, values)
        return False
