"""Network-AT AT+Z — local UDP, no live module."""

from __future__ import annotations

import asyncio

import pytest

from spo_pool_heat_pump.dr164_at import ACK, AT_Z, SEARCH, Dr164NoSearchReply, reboot_dr164


class _Echo(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.received: list[bytes] = []
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self._transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self.received.append(data)
        assert self._transport is not None
        if data == SEARCH:
            self._transport.sendto(b"127.0.0.1,AABBCCDDEEFF,USR-DR164", addr)
        elif data == AT_Z:
            self._transport.sendto(b"+ok", addr)


def test_reboot_sends_search_ack_then_atz() -> None:
    async def run() -> None:
        loop = asyncio.get_running_loop()
        transport, proto = await loop.create_datagram_endpoint(_Echo, local_addr=("127.0.0.1", 0))
        port = transport.get_extra_info("sockname")[1]
        try:
            banner = await reboot_dr164("127.0.0.1", port=port, ack_pause_s=0.02)
        finally:
            transport.close()
        assert "USR-DR164" in banner
        assert proto.received[:3] == [SEARCH, ACK, AT_Z]

    asyncio.run(run())


def test_reboot_times_out_without_banner() -> None:
    async def run() -> None:
        with pytest.raises(Dr164NoSearchReply, match="www.usr.cn"):
            await reboot_dr164("127.0.0.1", port=1, timeout_s=0.05, ack_pause_s=0.0)

    asyncio.run(run())
