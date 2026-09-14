"""Raw Modbus RTU over a transparent TCP socket (USR-DR164 TCP Server)."""

from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Awaitable, Callable
from typing import Protocol

ConnectionCallback = Callable[[bool], None]

from ..const import IDLE_FRAME_S, STALE_REPLY_S
from ..modbus_rtu import complete_frames, find_frames, parse_frame

_LOGGER = logging.getLogger(__name__)

FrameCallback = Callable[[bytes], Awaitable[None] | None]


class BusRecorder(Protocol):
    def rx(self, data: bytes) -> None: ...
    def tx(self, data: bytes) -> None: ...


class TcpRtuClient:
    """One TCP client. Serial bytes are framed by idle (DR164 pack interval), or
    sooner when the buffer is already a complete CRC-valid RTU frame."""

    def __init__(self, host: str, port: int, idle_s: float = IDLE_FRAME_S) -> None:
        self.host = host
        self.port = port
        self.idle_s = idle_s
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task[None] | None = None
        self._on_frame: FrameCallback | None = None
        self._on_connection: ConnectionCallback | None = None
        self._unavailable_logged = False
        self._redial_now = False
        self._stop = asyncio.Event()
        self._last_rx = 0.0
        self._last_tx = 0.0
        self._tx_lock = asyncio.Lock()
        self._conn_lock = asyncio.Lock()
        self._ready = asyncio.Event()
        self.recorder: BusRecorder | None = None

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def start(
        self,
        on_frame: FrameCallback,
        on_connection: ConnectionCallback | None = None,
    ) -> None:
        self._on_frame = on_frame
        self._on_connection = on_connection
        self._stop.clear()
        await self._connect()
        self._task = asyncio.create_task(self._read_loop(), name="spo_pool_heat_pump_tcp")

    @staticmethod
    async def probe(host: str, port: int, timeout: float = 5.0) -> None:
        """Open and close a TCP connection. Raises OSError if the DR164 is down."""
        try:
            _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        except TimeoutError as err:
            raise OSError(f"timed out connecting to {host}:{port}") from err
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass

    def _notify_connection(self, connected: bool) -> None:
        if self._on_connection:
            self._on_connection(connected)

    def _note_unavailable(self, err: BaseException) -> None:
        if self._unavailable_logged:
            _LOGGER.debug("TCP drop (%s); reconnecting", err)
            return
        _LOGGER.info("DR164 at %s:%s unavailable: %s", self.host, self.port, err)
        self._unavailable_logged = True
        self._notify_connection(False)

    def _note_reconnected(self) -> None:
        if self._unavailable_logged:
            _LOGGER.info("DR164 at %s:%s reconnected", self.host, self.port)
            self._unavailable_logged = False
            self._notify_connection(True)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._close()

    async def _connect(self) -> None:
        async with self._conn_lock:
            if self.connected:
                return
            _LOGGER.debug("Connecting to %s:%s", self.host, self.port)
            self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
            self._set_nodelay()
            self._redial_now = False
            self._last_rx = asyncio.get_running_loop().time()
            self._ready.set()
            self._note_reconnected()

    def _set_nodelay(self) -> None:
        writer = self._writer
        extra = getattr(writer, "get_extra_info", None)
        sock = extra("socket") if extra else None
        if sock is None:
            return
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            _LOGGER.debug("TCP_NODELAY not set on %s:%s", self.host, self.port, exc_info=True)

    async def _close(self) -> None:
        async with self._conn_lock:
            await self._close_unlocked()

    async def reconnect(self) -> None:
        """Drop the socket so the read loop opens a fresh one.

        A DR164 reboot or a WiFi drop can leave our side half-open: the peer
        is gone but no FIN/RST ever arrives, so ``read()`` blocks for good and
        slave-2 writes (which only go out when the board polls us) never touch
        the socket either. The coordinator calls this when the bus has been
        silent for STALE_SECONDS.
        """
        if self._stop.is_set() or self._writer is None:
            return
        self._note_unavailable(ConnectionError("bus silent"))
        self._redial_now = True
        await self._close()

    async def _close_unlocked(self) -> None:
        self._ready.clear()
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
        self._reader = None
        self._writer = None

    async def send(self, frame: bytes, *, solicited: bool = False) -> None:
        """Write ``frame``. Unsolicited writes wait one idle gap so they do not
        collide with a broadcast. Solicited slave-2 replies skip that wait (the
        board just addressed us) and are dropped if the request is already too
        old to beat the ~340 ms page-read deadline.
        """
        async with self._tx_lock:
            if not self.connected:
                await asyncio.wait_for(self._ready.wait(), timeout=10.0)
            if not self.connected:
                raise ConnectionError("TCP not connected")
            now = asyncio.get_running_loop().time()
            if solicited:
                age = now - self._last_rx
                if age > STALE_REPLY_S:
                    _LOGGER.debug("dropping late solicited reply (age=%.3fs)", age)
                    return
            else:
                last_bus = max(self._last_rx, self._last_tx)
                wait = self.idle_s - (now - last_bus)
                if wait > 0:
                    await asyncio.sleep(wait)
            assert self._writer is not None
            self._writer.write(frame)
            await self._writer.drain()
            self._last_tx = asyncio.get_running_loop().time()
            if self.recorder is not None:
                self.recorder.tx(frame)

    async def _read_loop(self) -> None:
        buf = bytearray()
        last = asyncio.get_running_loop().time()
        while not self._stop.is_set():
            try:
                if self._reader is None:
                    await self._connect()
                assert self._reader is not None
                try:
                    if buf:
                        chunk = await asyncio.wait_for(self._reader.read(4096), timeout=self.idle_s)
                    else:
                        chunk = await self._reader.read(4096)
                except TimeoutError:
                    chunk = b""
                now = asyncio.get_running_loop().time()
                if chunk:
                    buf.extend(chunk)
                    last = now
                    self._last_rx = now
                    if complete_frames(bytes(buf)) is not None:
                        await self._emit(bytes(buf))
                        buf.clear()
                    continue
                eof = self._reader is not None and self._reader.at_eof()
                if buf and (now - last >= self.idle_s or eof):
                    await self._emit(bytes(buf))
                    buf.clear()
                if eof:
                    raise ConnectionError("peer closed")
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001
                self._note_unavailable(err)
                await self._close()
                buf.clear()
                if self._stop.is_set():
                    return
                if self._redial_now:
                    # We dropped the socket ourselves (reconnect()); dial again at once.
                    self._redial_now = False
                    continue
                await asyncio.sleep(1.0)

    async def _emit(self, blob: bytes) -> None:
        if self.recorder is not None:
            self.recorder.rx(blob)
        frames = find_frames(blob)
        if not frames:
            # Whole blob might still be one well-formed frame (broadcast is 189 B).
            parsed = parse_frame(blob)
            if parsed and self._on_frame:
                result = self._on_frame(blob)
                if asyncio.iscoroutine(result):
                    await result
            return
        if not self._on_frame:
            return
        for fr in frames:
            result = self._on_frame(fr.raw)
            if asyncio.iscoroutine(result):
                await result
