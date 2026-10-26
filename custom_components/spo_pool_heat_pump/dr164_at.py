"""Network-AT for the USR-DR164. UDP 48899; does not touch RS-485.

The module has no AT command for its RS-485 driver-enable pin. After a UART
TX the auto-DE can stay asserted and hold A/B so the outdoor board, the
wired display, and the factory DTU all go quiet. TCP :8899 and WiFi stay
up (``AT+TCPLK=on``). Live Cosma 2026-09-17: three multi-hour holes on the
slave-2 write path; ``AT+Z`` alone (no Modbus) released the bus. The same
weekend on slave 99 (Home Assistant silent) had only 15 s radio flickers.

``+++`` serial AT is unusable here — the bus is never idle long enough.
Do not send Event, heartbeat-to-COM, or FC03 from this module. Event stays
whatever the user set. FC03 also woke the bus, but only because it cycled
DE; it is a write onto a jammed line.
"""

from __future__ import annotations

import asyncio
import logging

_LOGGER = logging.getLogger(__name__)

AT_PORT = 48899
SEARCH = b"www.usr.cn"
# No CR/LF. The module ignores every AT until it sees this exact ack.
ACK = b"+ok"
AT_Z = b"AT+Z\r\n"


class Dr164AtError(Exception):
    """Handshake or AT command failed (module down, or +ok not sent)."""


class Dr164NoSearchReply(Dr164AtError):
    """Nothing answered ``www.usr.cn``. With TCP up this is usually a non-USR
    gateway (Waveshare and other transparent TCP servers have no USR AT)."""


class _QueueProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.queue: asyncio.Queue[bytes] = asyncio.Queue()

    def datagram_received(self, data: bytes, _addr: tuple) -> None:
        self.queue.put_nowait(data)


async def reboot_dr164(
    host: str,
    *,
    port: int = AT_PORT,
    timeout_s: float = 2.0,
    ack_pause_s: float = 0.3,
) -> str:
    """Handshake then ``AT+Z``. Returns the search banner. Does not wait for boot.

    Sequence (same as ``tools/dr164_event_off.py`` / the README Event-off
    recipe, minus Event): ``www.usr.cn`` → banner ``IP,MAC,USR-DR164`` →
    ``+ok`` with no line ending → ``AT+Z\\r\\n``. The module drops TCP
    :8899 for ~20 s; Home Assistant already redials a silent socket.
    """
    loop = asyncio.get_running_loop()
    transport, proto = await loop.create_datagram_endpoint(
        _QueueProtocol,
        remote_addr=(host, port),
    )
    try:
        transport.sendto(SEARCH)
        try:
            banner = await asyncio.wait_for(proto.queue.get(), timeout_s)
        except TimeoutError as err:
            raise Dr164NoSearchReply(
                f"no reply to www.usr.cn at {host}:{port} — same LAN, UDP 48899"
            ) from err
        transport.sendto(ACK)
        await asyncio.sleep(ack_pause_s)
        transport.sendto(AT_Z)
        try:
            await asyncio.wait_for(proto.queue.get(), timeout_s)
        except TimeoutError:
            pass
        return banner.decode("ascii", errors="replace").strip()
    finally:
        transport.close()
