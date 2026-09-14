#!/usr/bin/env python3
"""Turn USR-DR164 Event off over network AT (UDP 48899).

The web UI has no Event switch. With Event on the module writes
``+EVENT=SOCKA_ON`` / ``SOCKA_OFF`` onto the RS-485 bus on every TCP
connect. This is the same handshake as the README: ``www.usr.cn``,
then ``+ok`` with no line ending, then ``AT+EVENT=off`` and ``AT+Z``.

Python 3, stdlib only. Same LAN as the DR164.

    python tools/dr164_event_off.py 192.168.x.x
    python tools/dr164_event_off.py --check 192.168.x.x
    python tools/dr164_event_off.py          # broadcast search
"""

from __future__ import annotations

import argparse
import socket
import sys
import time

PORT = 48899
SEARCH = b"www.usr.cn"
ACK = b"+ok"  # no line ending — the module ignores AT until this
AT_WAIT_S = 2.0
ACK_PAUSE_S = 0.3
CMD_PAUSE_S = 0.2
REBOOT_S = 20.0


class AtError(Exception):
    """Handshake or AT command failed."""


def event_from_reply(text: str) -> str | None:
    compact = text.lower().replace(" ", "")
    if "+ok=off" in compact:
        return "off"
    if "+ok=on" in compact:
        return "on"
    return None


def open_udp(*, timeout: float = 3.0, broadcast: bool = False) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    if broadcast:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    return sock


class Dr164At:
    """One UDP session: search, ``+ok``, then AT commands for ~30 s."""

    def __init__(self, host: str, sock: socket.socket | None = None, *, sleep=time.sleep) -> None:
        self.host = host
        self.sock = sock if sock is not None else open_udp()
        self._sleep = sleep
        self._owns = sock is None

    def close(self) -> None:
        if self._owns:
            self.sock.close()

    def __enter__(self) -> Dr164At:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def handshake(self) -> str:
        self.sock.sendto(SEARCH, (self.host, PORT))
        try:
            data, _addr = self.sock.recvfrom(2048)
        except (TimeoutError, socket.timeout) as err:
            raise AtError(
                f"no reply to www.usr.cn at {self.host}:{PORT} — same LAN, reserved IP, UDP not blocked"
            ) from err
        self.sock.sendto(ACK, (self.host, PORT))
        self._sleep(ACK_PAUSE_S)
        return data.decode("ascii", errors="replace").strip()

    def command(self, cmd: str, wait_s: float = AT_WAIT_S) -> str:
        self.sock.sendto(f"{cmd}\r\n".encode("ascii"), (self.host, PORT))
        chunks: list[str] = []
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            try:
                data, _addr = self.sock.recvfrom(2048)
            except (TimeoutError, socket.timeout):
                break
            chunks.append(data.decode("ascii", errors="replace"))
        self._sleep(CMD_PAUSE_S)
        return "".join(chunks)

    def query_event(self) -> tuple[str | None, str]:
        reply = self.command("AT+EVENT")
        return event_from_reply(reply), reply


def discover(timeout: float = 2.0, sock: socket.socket | None = None) -> list[tuple[str, str]]:
    """Broadcast ``www.usr.cn`` and return ``(ip, search-reply)`` hits."""
    own = sock is None
    sock = sock if sock is not None else open_udp(timeout=timeout, broadcast=True)
    try:
        sock.sendto(SEARCH, ("255.255.255.255", PORT))
        hits: list[tuple[str, str]] = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                data, addr = sock.recvfrom(2048)
            except (TimeoutError, socket.timeout):
                break
            hits.append((addr[0], data.decode("ascii", errors="replace").strip()))
        return hits
    finally:
        if own:
            sock.close()


def set_event_off(
    host: str,
    *,
    check_only: bool = False,
    restart: bool = True,
    wait_reboot_s: float = REBOOT_S,
    sock: socket.socket | None = None,
    sleep=time.sleep,
    log=print,
    open_session=Dr164At,
) -> str:
    """Handshake, optionally turn Event off, return ``off`` or raise ``AtError``."""
    session = open_session(host, sock, sleep=sleep)
    try:
        banner = session.handshake()
        log(f"search: {banner}")
        state, reply = session.query_event()
        log(f"AT+EVENT -> {reply.strip() or 'no reply'}")
        rssi = session.command("AT+WSLQ").strip()
        if rssi:
            log(f"AT+WSLQ -> {rssi}")
        if state is None:
            raise AtError("AT+EVENT did not return +ok=on or +ok=off (handshake +ok missing?)")
        if check_only:
            return state
        if state == "off":
            log("Event is already off")
            return state
        set_reply = session.command("AT+EVENT=off")
        log(f"AT+EVENT=off -> {set_reply.strip() or 'no reply'}")
        state, reply = session.query_event()
        log(f"AT+EVENT -> {reply.strip() or 'no reply'}")
        if state != "off":
            raise AtError("Event is still on after AT+EVENT=off")
        if not restart:
            return state
        z_reply = session.command("AT+Z", wait_s=1.0)
        log(f"AT+Z -> {z_reply.strip() or 'restarting'}")
    finally:
        if sock is None:
            session.close()

    log(f"waiting {wait_reboot_s:.0f}s for the module to come back")
    sleep(wait_reboot_s)
    with open_session(host, sleep=sleep) as again:
        banner = again.handshake()
        log(f"search: {banner}")
        state, reply = again.query_event()
        log(f"AT+EVENT -> {reply.strip() or 'no reply'}")
        if state != "off":
            raise AtError("Event did not stay off after AT+Z")
    return state


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Turn USR-DR164 Event off (UDP 48899). Same handshake as the README."
    )
    parser.add_argument("host", nargs="?", help="Reserved LAN IP of the DR164")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Query Event (and WiFi signal) only; do not change it",
    )
    parser.add_argument(
        "--no-restart",
        action="store_true",
        help="Set Event off but skip AT+Z",
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=REBOOT_S,
        metavar="SEC",
        help=f"Seconds to wait after AT+Z before re-checking (default {REBOOT_S:.0f})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.host:
        hits = discover()
        if not hits:
            print("no DR164 answered a broadcast to UDP 48899 — pass the reserved IP", file=sys.stderr)
            return 1
        for ip, banner in hits:
            print(f"{ip}  {banner}")
        print("re-run with that IP to turn Event off", file=sys.stderr)
        return 0
    try:
        state = set_event_off(
            args.host,
            check_only=args.check,
            restart=not args.no_restart,
            wait_reboot_s=args.wait,
        )
    except AtError as err:
        print(err, file=sys.stderr)
        return 1
    if args.check:
        print(f"Event is {state}")
        return 0 if state == "off" else 2
    print(f"Event is {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
