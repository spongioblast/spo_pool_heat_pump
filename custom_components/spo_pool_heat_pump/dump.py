"""RS-485 dump in the rs485_dump.py text format."""

from __future__ import annotations

import re
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from .const import IDLE_FRAME_S

DUMP_DIR_NAME = "spo_pool_heat_pump_dumps"
ROTATE_BYTES = 8 * 1024 * 1024
KEEP_FILES = 5
SESSION_CAP_BYTES = ROTATE_BYTES * KEEP_FILES
DIR_CAP_BYTES = 200 * 1024 * 1024
MAX_DURATION_S = 7200
MIN_DURATION_S = 0
NOTE_MAX = 200
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.(log|bin)$")


class DumpError(Exception):
    key = "dump_failed"


class DumpAlreadyRunning(DumpError):
    key = "dump_already_running"


class DumpNotRunning(DumpError):
    key = "dump_not_running"


class DumpDirFull(DumpError):
    key = "dump_dir_full"


class DumpInvalidDuration(DumpError):
    key = "dump_invalid_duration"


class DumpInvalidName(DumpError):
    key = "dump_invalid_name"


def hex_ascii(data: bytes, width: int = 16) -> list[str]:
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"  {hex_part:<{width * 3}} | {ascii_part}")
    return lines


def dumps_dir(config_path: Path) -> Path:
    return Path(config_path) / DUMP_DIR_NAME


def dir_used_bytes(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(p.stat().st_size for p in directory.iterdir() if p.is_file())


def limits_payload(directory: Path | None = None) -> dict[str, int]:
    used = dir_used_bytes(directory) if directory is not None else 0
    return {
        "rotate_bytes": ROTATE_BYTES,
        "keep_files": KEEP_FILES,
        "session_cap_bytes": SESSION_CAP_BYTES,
        "dir_cap_bytes": DIR_CAP_BYTES,
        "max_duration_s": MAX_DURATION_S,
        "dir_used": used,
        "dir_remaining": max(0, DIR_CAP_BYTES - used),
    }


def validate_duration_s(duration_s: int) -> int:
    try:
        value = int(duration_s)
    except (TypeError, ValueError) as err:
        raise DumpInvalidDuration from err
    if value < MIN_DURATION_S or value > MAX_DURATION_S:
        raise DumpInvalidDuration
    return value


def safe_dump_name(name: str) -> str:
    if not isinstance(name, str) or not SAFE_NAME.match(name):
        raise DumpInvalidName
    return name


def dump_path(directory: Path, name: str) -> Path:
    path = (directory / safe_dump_name(name)).resolve()
    root = directory.resolve()
    if path.parent != root:
        raise DumpInvalidName
    return path


def sibling_pair(path: Path) -> list[Path]:
    other = path.with_suffix(".bin" if path.suffix == ".log" else ".log")
    return [path, other]


def _header_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for _ in range(16):
                line = handle.readline()
                if not line or not line.startswith("#"):
                    break
                if "=" in line:
                    key, _, value = line[1:].partition("=")
                    fields[key.strip()] = value.strip()
    except OSError:
        return fields
    return fields


def list_dump_files(directory: Path) -> list[dict[str, Any]]:
    if not directory.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for log in sorted(directory.glob("*.log")):
        bin_path = log.with_suffix(".bin")
        size = log.stat().st_size + (bin_path.stat().st_size if bin_path.exists() else 0)
        meta = _header_fields(log)
        rows.append(
            {
                "name": log.name,
                "bin": bin_path.name if bin_path.exists() else None,
                "size": size,
                "started": meta.get("started"),
                "note": meta.get("note") or "",
                "kind": "log",
            }
        )
    return rows


def delete_dump_file(directory: Path, name: str) -> None:
    path = dump_path(directory, name)
    if not path.exists():
        raise DumpInvalidName
    for item in sibling_pair(path):
        if item.exists():
            item.unlink()


def status_payload(directory: Path, recorder: DumpRecorder | None = None) -> dict[str, Any]:
    payload = {
        "running": bool(recorder and recorder.running),
        "started": recorder.started_iso if recorder else None,
        "bytes": recorder.session_bytes if recorder else 0,
        "elapsed_s": recorder.elapsed_s if recorder else 0,
        "remaining_s": recorder.remaining_s if recorder else None,
        "duration_s": recorder.duration_s if recorder else None,
        "note": recorder.note if recorder else "",
        "include_writes": recorder.include_writes if recorder else True,
        "stop_reason": recorder.stop_reason if recorder else None,
        "files": list_dump_files(directory),
        "limits": limits_payload(directory),
    }
    return payload


class DumpRecorder:
    """Queue-only on the bus thread; flush() writes the rs485_dump dialect."""

    def __init__(
        self,
        directory: Path,
        *,
        source: str,
        profile: str,
        note: str = "",
        include_writes: bool = True,
        duration_s: int = 900,
        idle_s: float = IDLE_FRAME_S,
        rotate_bytes: int = ROTATE_BYTES,
        keep_files: int = KEEP_FILES,
        clock: datetime | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.source = source
        self.profile = profile
        self.note = str(note).strip()[:NOTE_MAX]
        self.include_writes = bool(include_writes)
        self.duration_s = validate_duration_s(duration_s)
        self.idle_s = idle_s
        self.rotate_bytes = rotate_bytes
        self.keep_files = keep_files
        self.running = False
        self.stop_reason: str | None = None
        self.started_iso: str | None = None
        self.session_bytes = 0
        self.stamp = ""
        self._queue: deque[tuple[bool, bytes, float]] = deque()
        self._t0 = 0.0
        self._last_t: float | None = None
        self._part = 1
        self._part_bytes = 0
        self._log: TextIO | None = None
        self._bin: Any = None
        self._clock = clock

    @property
    def elapsed_s(self) -> float:
        if not self._t0:
            return 0.0
        return max(0.0, time.monotonic() - self._t0)

    @property
    def remaining_s(self) -> float | None:
        if not self.running or not self.duration_s:
            return None
        return max(0.0, self.duration_s - self.elapsed_s)

    def start(self) -> None:
        if self.running:
            raise DumpAlreadyRunning
        self.directory.mkdir(parents=True, exist_ok=True)
        if dir_used_bytes(self.directory) >= DIR_CAP_BYTES:
            raise DumpDirFull
        wall = self._clock or datetime.now()
        self.stamp = wall.strftime("%Y%m%d_%H%M%S")
        self.started_iso = wall.isoformat(timespec="milliseconds")
        self._t0 = time.monotonic()
        self._last_t = None
        self._part = 1
        self.session_bytes = 0
        self.stop_reason = None
        self.running = True
        self._open_part()

    def rx(self, data: bytes) -> None:
        if self.running and data:
            self._queue.append((False, bytes(data), time.monotonic()))

    def tx(self, data: bytes) -> None:
        if self.running and self.include_writes and data:
            self._queue.append((True, bytes(data), time.monotonic()))

    def flush(self) -> None:
        if not self.running:
            return
        self._write_queued()
        if self.running and self.duration_s and self.elapsed_s >= self.duration_s:
            self.stop("duration")

    def stop(self, reason: str = "stop") -> None:
        if not self.running and self._log is None:
            return
        self.running = False
        self._write_queued()
        self._close_part()
        self.stop_reason = reason
        self._queue.clear()

    def _write_queued(self) -> None:
        while self._queue:
            if not self.running and self._log is None:
                return
            tx, data, when = self._queue.popleft()
            self._write_blob(tx, data, when)
            if self.running and self._part_bytes >= self.rotate_bytes:
                self._rotate_or_stop()
                if not self.running:
                    return

    def _open_part(self) -> None:
        stem = self.stamp if self._part == 1 else f"{self.stamp}_{self._part}"
        log_path = self.directory / f"{stem}.log"
        bin_path = self.directory / f"{stem}.bin"
        self._log = log_path.open("w", encoding="utf-8", newline="\n")
        self._bin = bin_path.open("wb")
        self._part_bytes = 0
        header = (
            "# raw RS-485 dump\n"
            f"# source={self.source}\n"
            f"# profile={self.profile}\n"
            f"# started={self.started_iso}\n"
            f"# gap_s={self.idle_s}\n"
        )
        if self.note:
            header += f"# note={self.note}\n"
        header += "\n"
        self._log.write(header)
        self._log.flush()
        self._part_bytes += len(header.encode())
        self.session_bytes += len(header.encode())

    def _close_part(self) -> None:
        if self._log is not None:
            self._log.close()
            self._log = None
        if self._bin is not None:
            self._bin.close()
            self._bin = None

    def _rotate_or_stop(self) -> None:
        if self._part >= self.keep_files:
            self.running = False
            self.stop_reason = "session_cap"
            self._close_part()
            self._queue.clear()
            return
        self._close_part()
        self._part += 1
        self._open_part()

    def _write_blob(self, tx: bool, data: bytes, when: float) -> None:
        if self._log is None:
            return
        if self._last_t is not None:
            idle = (when - self._last_t) * 1000
            line = f"# idle {idle:.1f} ms\n"
            self._log.write(line)
            encoded = line.encode()
            self._part_bytes += len(encoded)
            self.session_bytes += len(encoded)
        self._last_t = when
        if tx:
            self._log.write("# dir=tx\n")
            extra = b"# dir=tx\n"
            self._part_bytes += len(extra)
            self.session_bytes += len(extra)
        else:
            self._bin.write(data)
            self._bin.flush()
            self._part_bytes += len(data)
            self.session_bytes += len(data)
        wall = (self._clock or datetime.now()).isoformat(timespec="milliseconds")
        rel = when - self._t0
        lines = [f"[{wall}] t+{rel:9.3f}s  {len(data)} bytes", *hex_ascii(data), ""]
        text = "\n".join(lines) + "\n"
        self._log.write(text)
        self._log.flush()
        encoded = text.encode()
        self._part_bytes += len(encoded)
        self.session_bytes += len(encoded)
