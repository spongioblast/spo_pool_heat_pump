from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from spo_pool_heat_pump.modbus_rtu import encode_fc16, parse_frame
from spo_pool_heat_pump.transport.tcp import TcpRtuClient


async def _serve_once(payload: bytes, port_holder: list[int]) -> asyncio.AbstractServer:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"\xde\xad")
        await writer.drain()
        await asyncio.sleep(0.03)
        writer.write(payload)
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    port_holder.append(server.sockets[0].getsockname()[1])
    return server


def test_idle_framing_drops_noise() -> None:
    async def run() -> None:
        ports: list[int] = []
        frame = encode_fc16(99, 1011, [1])
        server = await _serve_once(frame, ports)
        got: list[bytes] = []

        async def on_frame(blob: bytes) -> None:
            got.append(blob)

        client = TcpRtuClient("127.0.0.1", ports[0], idle_s=0.02)
        await client.start(on_frame)
        await asyncio.sleep(0.25)
        await client.stop()
        server.close()
        await server.wait_closed()
        parsed = [parse_frame(b) for b in got]
        starts = [p.start for p in parsed if p]
        assert 1011 in starts

    asyncio.run(run())


def test_send_reconnects() -> None:
    async def run() -> None:
        received = asyncio.Event()

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await reader.read(32)
            received.set()
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        client = TcpRtuClient("127.0.0.1", port, idle_s=0.01)

        async def on_frame(_blob: bytes) -> None:
            return None

        await client.start(on_frame)
        await client.send(encode_fc16(99, 1011, [1]))
        await asyncio.wait_for(received.wait(), timeout=1.0)
        await client.stop()
        server.close()
        await server.wait_closed()

    asyncio.run(run())


def test_send_enforces_idle_after_tx() -> None:
    async def run() -> None:
        times: list[float] = []

        async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            while True:
                chunk = await reader.read(32)
                if not chunk:
                    break
                times.append(asyncio.get_running_loop().time())
            writer.close()

        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        client = TcpRtuClient("127.0.0.1", port, idle_s=0.03)

        async def on_frame(_blob: bytes) -> None:
            return None

        await client.start(on_frame)
        await client.send(encode_fc16(99, 1011, [1]))
        await client.send(encode_fc16(99, 1012, [1]))
        await asyncio.sleep(0.05)
        await client.stop()
        server.close()
        await server.wait_closed()
        assert len(times) >= 2
        assert times[1] - times[0] >= 0.025

    asyncio.run(run())


class _FakeWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self._closing = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self._closing = True

    def is_closing(self) -> bool:
        return self._closing

    async def wait_closed(self) -> None:
        return None


def test_idle_read_blocks_without_timeout_when_buffer_empty() -> None:
    async def run() -> None:
        reads = 0
        started = asyncio.Event()
        hold = asyncio.Event()

        class FakeReader:
            async def read(self, _n: int) -> bytes:
                nonlocal reads
                reads += 1
                started.set()
                await hold.wait()
                return b""

            def at_eof(self) -> bool:
                return False

        client = TcpRtuClient("127.0.0.1", 8899, idle_s=0.02)
        client._reader = FakeReader()  # type: ignore[assignment]
        client._writer = _FakeWriter()  # type: ignore[assignment]
        client._ready.set()
        client._on_frame = lambda _blob: None
        client._task = asyncio.create_task(client._read_loop(), name="tcp-idle-test")
        await asyncio.wait_for(started.wait(), timeout=1.0)
        await asyncio.sleep(0.08)
        assert reads == 1
        await client.stop()
        assert reads == 1

    asyncio.run(run())


def test_probe_times_out() -> None:
    async def run() -> None:
        async def fake_open(host: str, port: int):
            await asyncio.sleep(1)
            raise AssertionError("should have timed out")

        with patch("spo_pool_heat_pump.transport.tcp.asyncio.open_connection", fake_open):
            with pytest.raises(OSError, match="timed out"):
                await TcpRtuClient.probe("10.0.0.8", 8899, timeout=0.05)

    asyncio.run(run())


def test_tcp_logs_unavailable_once() -> None:
    client = TcpRtuClient("10.0.0.8", 8899)
    seen: list[bool] = []
    client._on_connection = seen.append
    with patch("spo_pool_heat_pump.transport.tcp._LOGGER") as log:
        client._note_unavailable(ConnectionError("peer closed"))
        client._note_unavailable(ConnectionError("again"))
        client._note_reconnected()
        client._note_reconnected()
    assert [c.args[0] for c in log.info.call_args_list] == [
        "DR164 at %s:%s unavailable: %s",
        "DR164 at %s:%s reconnected",
    ]
    assert log.warning.call_count == 0
    assert seen == [False, True]


def test_send_does_not_connect_while_reader_reconnects() -> None:
    async def run() -> None:
        opens = 0
        gate = asyncio.Event()

        async def fake_open(host: str, port: int):
            nonlocal opens
            opens += 1
            if opens >= 2:
                await gate.wait()
            return asyncio.StreamReader(), _FakeWriter()

        client = TcpRtuClient("127.0.0.1", 8899, idle_s=0.0)
        from unittest.mock import patch

        with patch("spo_pool_heat_pump.transport.tcp.asyncio.open_connection", fake_open):
            await client._connect()
            assert opens == 1
            await client._close()
            reconnect = asyncio.create_task(client._connect())
            await asyncio.sleep(0.02)
            send_task = asyncio.create_task(client.send(encode_fc16(99, 1011, [1])))
            await asyncio.sleep(0.02)
            assert opens == 2
            gate.set()
            await reconnect
            await send_task
            assert opens == 2
            assert client.connected

    asyncio.run(run())
