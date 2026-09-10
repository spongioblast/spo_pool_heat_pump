"""Impersonate slave 2: answer FC03 3001 / 1001 / 1091 and raise 3011 flags.

Measured on dump 20260906_104432: slave 1 FC03 3001×30 is answered in ~93 ms.
The board then polls slave 2 and waits ~500 ms with no reply before moving on.
Never answer 1001/1091 until that page is seeded — a zero page would wipe the menu.
"""

from __future__ import annotations

from ..modbus_rtu import RtuFrame, encode_fc03_reply

FLAG_READ_1001 = 4
FLAG_READ_1091 = 16
FLAG_TIMER = 32
FLAG_HEAT_SP = 64
FLAG_REFRESH = 32768

REG_3011 = 3011


class SettingsUnseeded(RuntimeError):
    """Slave-2 would have to invent a settings page."""


class Slave2Responder:
    def __init__(self, broadcast_start: int = 2001) -> None:
        self._broadcast_start = broadcast_start
        self.block_3001 = [0] * 30
        self.block_1001 = [0] * 90
        self.block_1091 = [0] * 90
        self.block_1181 = [0] * 90
        self.flags_3011 = 0
        self.seeded_1001 = False
        self.seeded_1091 = False
        self.seeded_1181 = False

    def observe(self, frame: RtuFrame) -> None:
        if frame.kind == "reply" and frame.function == 3 and len(frame.values) == 30:
            if frame.values[9] in (3001, 0x0BB9) or frame.values[0] > 0:
                self.block_3001 = list(frame.values[:30])
        if frame.function == 16 and frame.start in (1001, 1091, 1181) and frame.values:
            self.seed_page(int(frame.start), list(frame.values))

    def cache_from_broadcast(self, regs: dict[int, int]) -> None:
        serial = [regs.get(self._broadcast_start + i, 0) for i in range(10)]
        if any(serial):
            self.block_3001[0:10] = serial[:10]

    def seed_page(self, start: int, values: list[int]) -> None:
        padded = (list(values) + [0] * 90)[:90]
        if start == 1001:
            self.block_1001 = padded
            self.seeded_1001 = True
        elif start == 1091:
            self.block_1091 = padded
            self.seeded_1091 = True
        elif start == 1181:
            self.block_1181 = padded
            self.seeded_1181 = True

    def page_seeded(self, register: int) -> bool:
        if 1001 <= register <= 1090:
            return self.seeded_1001
        if 1091 <= register <= 1180:
            return self.seeded_1091
        if 1181 <= register <= 1270:
            return self.seeded_1181
        return False

    def queue_write(self, register: int, value: int) -> None:
        """Overlay one register. 3011 bits tell the panel which page to re-read.

        1181+ has no dedicated 3011 bit in the dumps — only FLAG_REFRESH.
        """
        if not self.page_seeded(register):
            raise SettingsUnseeded(f"settings page for {register} is not seeded")
        if 1001 <= register <= 1090:
            self.block_1001[register - 1001] = value & 0xFFFF
            self.flags_3011 |= FLAG_READ_1001
        elif 1091 <= register <= 1180:
            self.block_1091[register - 1091] = value & 0xFFFF
            self.flags_3011 |= FLAG_READ_1091
            if register == 1136:
                self.flags_3011 |= FLAG_HEAT_SP
            if 1150 <= register <= 1161:
                self.flags_3011 |= FLAG_TIMER
        elif 1181 <= register <= 1270:
            self.block_1181[register - 1181] = value & 0xFFFF
        self.flags_3011 |= FLAG_REFRESH

    def reply(self, request: bytes) -> bytes | None:
        from ..modbus_rtu import parse_frame

        parsed = parse_frame(request)
        if parsed is None or parsed.slave != 2 or parsed.kind != "request" or parsed.function != 3:
            return None
        start = parsed.start or 0
        qty = parsed.qty or 0
        if start == 3001:
            values = list(self.block_3001)
            if len(values) > 10:
                values[10] = self.flags_3011
            return encode_fc03_reply(2, values[:qty])
        if start == 1001:
            if not self.seeded_1001:
                return None
            self.flags_3011 &= ~FLAG_READ_1001
            return encode_fc03_reply(2, self.block_1001[:qty])
        if start == 1091:
            if not self.seeded_1091:
                return None
            self.flags_3011 &= ~(FLAG_READ_1091 | FLAG_HEAT_SP | FLAG_TIMER)
            return encode_fc03_reply(2, self.block_1091[:qty])
        if start == 1181:
            if not self.seeded_1181:
                return None
            return encode_fc03_reply(2, self.block_1181[:qty])
        if start == REG_3011:
            return encode_fc03_reply(2, [self.flags_3011])
        return None
