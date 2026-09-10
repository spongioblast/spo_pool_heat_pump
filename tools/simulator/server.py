"""DR164-shaped TCP simulator plus a JSON control port."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "custom_components"))

from spo_pool_heat_pump.const import BROADCAST_QTY, BROADCAST_START  # noqa: E402
from spo_pool_heat_pump.modbus_rtu import (  # noqa: E402
    encode_fc01_reply,
    encode_fc03_reply,
    encode_fc04_reply,
    encode_fc16_reply,
    find_frames,
)
from spo_pool_heat_pump.profiles import load_profile, profile_polls  # noqa: E402

from .physics import tick  # noqa: E402
from .state import SimUnit  # noqa: E402
from .wire import (  # noqa: E402
    apply_coil_write,
    apply_write,
    block_words,
    coil_bits,
    encode_broadcast_frame,
    encode_broadcast_words,
    encode_maps,
    settings_page,
)

SCENARIOS = (
    "cold_start",
    "heating_to_setpoint",
    "cooling",
    "fault_e03",
    "no_dtu",
    "reduced_profile",
    "service_menu_page_timeout",
)


def apply_scenario(unit: SimUnit, name: str) -> None:
    if name == "cold_start":
        unit.power = False
        unit.t_ambient = 12.0
        unit.t_inlet = 12.0
        unit.t_outlet = 12.0
        return
    if name == "heating_to_setpoint":
        unit.power = True
        unit.mode = "heat"
        unit.setpoint = 28.0
        unit.t_inlet = 16.0
        unit.t_outlet = 16.0
        unit.t_ambient = 14.0
        return
    if name == "cooling":
        unit.power = True
        unit.mode = "cool"
        unit.setpoint = 26.0
        unit.t_inlet = 30.0
        unit.t_outlet = 30.0
        unit.t_ambient = 32.0
        return
    if name == "fault_e03":
        apply_scenario(unit, "heating_to_setpoint")
        unit.inject_fault("E03")
        return
    if name == "no_dtu":
        unit.dtu = False
        apply_scenario(unit, "heating_to_setpoint")
        return
    if name == "reduced_profile":
        unit.power = True
        unit.mode = "heat"
        unit.setpoint = 28.0
        unit.fw_mini = 100
        return
    if name == "service_menu_page_timeout":
        unit.pages_timeout = True
        apply_scenario(unit, "heating_to_setpoint")
        return
    raise SystemExit(f"unknown scenario {name}")


def _settings_starts(unit: SimUnit) -> set[int]:
    pages = (unit.profile.get("service_menu") or {}).get("pages") or []
    return {int(page["start"]) for page in pages}


def _reply_read(unit: SimUnit, slave: int, function: int, start: int, qty: int) -> bytes | None:
    driver = unit.profile["driver"]["type"]
    polls = profile_polls(unit.profile)
    if function == 1:
        return encode_fc01_reply(slave, coil_bits(unit, start, qty))
    if function == 4:
        return encode_fc04_reply(slave, block_words(unit, "input", start, qty))
    if function != 3:
        return None
    settings_starts = _settings_starts(unit)
    if start in settings_starts or start == 3001:
        if unit.pages_timeout:
            return None
        return encode_fc03_reply(slave, settings_page(unit, start, qty))
    if driver == "pc1002_bus" and 1001 <= start <= 1232:
        return encode_fc03_reply(slave, settings_page(unit, start, qty))
    if driver == "poll_master":
        for spec in polls:
            if int(spec.get("fc", 3)) != 3:
                continue
            name = spec.get("name")
            if name:
                return encode_fc03_reply(slave, block_words(unit, str(name), start, qty))
        words = encode_broadcast_words(unit, BROADCAST_START, BROADCAST_QTY)
        if BROADCAST_START <= start < BROADCAST_START + BROADCAST_QTY:
            off = start - BROADCAST_START
            return encode_fc03_reply(slave, words[off : off + qty] or [0] * qty)
        _, _, settings = encode_maps(unit)
        return encode_fc03_reply(slave, [settings.get(start + i, 0) for i in range(qty)])
    return encode_fc03_reply(slave, settings_page(unit, start, qty))


async def _serve_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    unit: SimUnit,
    interval: float,
    lock: asyncio.Lock,
) -> None:
    peer = writer.get_extra_info("peername")
    print(f"client {peer}", flush=True)
    buf = bytearray()
    push = unit.profile["driver"]["type"] == "pc1002_bus"

    async def pump() -> None:
        while True:
            if push:
                async with lock:
                    frame = encode_broadcast_frame(unit)
                writer.write(frame)
                await writer.drain()
            await asyncio.sleep(interval)

    task = asyncio.create_task(pump())
    try:
        while True:
            chunk = await reader.read(4096)
            if not chunk:
                break
            buf.extend(chunk)
            frames = find_frames(bytes(buf))
            if not frames:
                if len(buf) > 4096:
                    del buf[:-256]
                continue
            consumed = sum(len(f.raw) for f in frames)
            del buf[:consumed]
            for frame in frames:
                async with lock:
                    if frame.kind == "write" and frame.start is not None:
                        if frame.function == 5:
                            apply_coil_write(unit, int(frame.start), bool(frame.values and frame.values[0]))
                            writer.write(frame.raw)
                        elif frame.values:
                            apply_write(unit, int(frame.start), list(frame.values))
                            if frame.function == 16:
                                writer.write(encode_fc16_reply(frame.slave, int(frame.start), int(frame.qty or len(frame.values))))
                            else:
                                writer.write(frame.raw)
                        await writer.drain()
                        print(f"write {frame.slave} fc{frame.function:02d} {frame.start}={frame.values}", flush=True)
                        continue
                    if frame.kind != "request" or frame.start is None:
                        continue
                    qty = int(frame.qty or 0)
                    reply = _reply_read(unit, frame.slave, frame.function, int(frame.start), qty)
                    if reply is None:
                        print(f"timeout {frame.slave} fc{frame.function:02d} {frame.start}", flush=True)
                        continue
                    writer.write(reply)
                    await writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        print(f"client {peer} closed", flush=True)


async def _control_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    unit: SimUnit,
    lock: asyncio.Lock,
) -> None:
    try:
        header = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
    except Exception:  # noqa: BLE001
        writer.close()
        return
    lines = header.split(b"\r\n")
    parts = lines[0].decode("ascii", "replace").split()
    method = parts[0] if parts else "GET"
    path = urlparse(parts[1]).path if len(parts) > 1 else "/"
    length = 0
    for line in lines[1:]:
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip() or 0)
    body = await reader.readexactly(length) if length else b""

    status = 200
    payload: Any
    async with lock:
        if method == "GET" and path == "/state":
            payload = unit.as_dict()
        elif method == "POST" and path == "/state":
            try:
                unit.apply_patch(json.loads(body.decode() or "{}"))
                payload = unit.as_dict()
            except Exception as err:  # noqa: BLE001
                status = 400
                payload = {"error": str(err)}
        else:
            status = 404
            payload = {"error": "not found"}
    data = json.dumps(payload).encode()
    writer.write(
        f"HTTP/1.1 {status} {'OK' if status == 200 else 'ERR'}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(data)}\r\n"
        "Connection: close\r\n\r\n".encode()
        + data
    )
    await writer.drain()
    writer.close()


async def _tick_loop(unit: SimUnit, interval: float, lock: asyncio.Lock) -> None:
    while True:
        async with lock:
            tick(unit, interval, unit.profile)
        await asyncio.sleep(interval)


async def run(args: argparse.Namespace) -> None:
    profile_id = args.profile
    if args.scenario == "reduced_profile" and args.profile == "mida_cosma_pc1002":
        profile_id = "phnix_mini_pc1002"
    profile = load_profile(profile_id)
    unit = SimUnit.seed(profile)
    apply_scenario(unit, args.scenario)
    lock = asyncio.Lock()
    print(
        f"simulator profile={profile['identity']['id']} scenario={args.scenario} "
        f"tcp={args.host}:{args.port} control={args.control_port} tick={args.tick}",
        flush=True,
    )

    async def on_modbus(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _serve_client(reader, writer, unit, args.tick, lock)

    async def on_control(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _control_client(reader, writer, unit, lock)

    server = await asyncio.start_server(on_modbus, args.host, args.port)
    control = await asyncio.start_server(on_control, args.host, args.control_port)
    asyncio.create_task(_tick_loop(unit, args.tick, lock))
    async with server, control:
        await asyncio.gather(server.serve_forever(), control.serve_forever())


def main() -> None:
    parser = argparse.ArgumentParser(description="SPO Pool Heat Pump state-model simulator")
    parser.add_argument("--profile", default="mida_cosma_pc1002")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--control-port", type=int, default=8900)
    parser.add_argument("--tick", type=float, default=1.0)
    parser.add_argument("--scenario", default="heating_to_setpoint", choices=SCENARIOS)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
