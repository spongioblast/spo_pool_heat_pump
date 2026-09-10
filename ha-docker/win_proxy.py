"""TCP proxy: Windows localhost -> WSL -> Home Assistant in Docker.

WSL forwards ordinary listeners to Windows. Docker's published ports on this
machine often do not, so the UI looks down even while HA is healthy in WSL.
"""

from __future__ import annotations

import argparse
import asyncio
import sys


async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await src.read(65536)
            if not chunk:
                break
            dst.write(chunk)
            await dst.drain()
    except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
        pass
    finally:
        try:
            dst.close()
        except Exception:
            pass


async def _handle(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    target_host: str,
    target_port: int,
) -> None:
    try:
        upstream_r, upstream_w = await asyncio.open_connection(target_host, target_port)
    except OSError:
        writer.close()
        await writer.wait_closed()
        return
    await asyncio.gather(
        _pipe(reader, upstream_w),
        _pipe(upstream_r, writer),
        return_exceptions=True,
    )


async def _main(listen_port: int, target_host: str, target_port: int) -> None:
    server = await asyncio.start_server(
        lambda r, w: _handle(r, w, target_host, target_port),
        host="0.0.0.0",
        port=listen_port,
    )
    print(f"proxy 0.0.0.0:{listen_port} -> {target_host}:{target_port}", flush=True)
    async with server:
        await server.serve_forever()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--listen", type=int, default=8124)
    p.add_argument("--target-host", default="127.0.0.1")
    p.add_argument("--target-port", type=int, default=18123)
    args = p.parse_args()
    try:
        asyncio.run(_main(args.listen, args.target_host, args.target_port))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
