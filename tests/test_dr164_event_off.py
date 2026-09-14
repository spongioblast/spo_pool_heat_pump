"""USR-DR164 network-AT helper — handshake bytes, no live module."""

from __future__ import annotations

import socket
from unittest.mock import Mock

from tools.dr164_event_off import (
    ACK,
    PORT,
    SEARCH,
    Dr164At,
    event_from_reply,
    main,
    set_event_off,
)


def test_event_from_reply() -> None:
    assert event_from_reply("+ok=off\r\n") == "off"
    assert event_from_reply("+ok=on") == "on"
    assert event_from_reply("+ERR=-1") is None


def test_handshake_is_search_then_plus_ok_without_crlf() -> None:
    sock = Mock()
    sock.recvfrom.return_value = (b"192.168.80.187,AABBCCDDEEFF,USR-DR164", ("192.168.80.187", PORT))
    session = Dr164At("192.168.80.187", sock, sleep=lambda _s: None)
    banner = session.handshake()
    assert banner.startswith("192.168.80.187")
    assert sock.sendto.call_args_list[0].args == (SEARCH, ("192.168.80.187", PORT))
    assert sock.sendto.call_args_list[1].args == (ACK, ("192.168.80.187", PORT))
    assert ACK == b"+ok"


def test_at_command_sends_crlf() -> None:
    sock = Mock()
    sock.recvfrom.side_effect = [
        (b"+ok=off\r\n", ("192.168.80.187", PORT)),
        TimeoutError,
    ]
    session = Dr164At("192.168.80.187", sock, sleep=lambda _s: None)
    assert session.command("AT+EVENT").startswith("+ok=off")
    sock.sendto.assert_called_once_with(b"AT+EVENT\r\n", ("192.168.80.187", PORT))


def _session_replies(banner: bytes, *replies: bytes) -> Mock:
    sock = Mock()
    addr = ("192.168.80.187", PORT)
    steps: list[object] = [(banner, addr)]
    for payload in replies:
        steps.append((payload, addr))
        steps.append(TimeoutError)

    def recvfrom(_n: int) -> tuple[bytes, tuple[str, int]]:
        if not steps:
            raise TimeoutError
        item = steps.pop(0)
        if item is TimeoutError:
            raise TimeoutError
        assert isinstance(item, tuple)
        return item

    sock.recvfrom.side_effect = recvfrom
    return sock


def test_set_event_off_skips_restart_when_already_off() -> None:
    sock = _session_replies(
        b"192.168.80.187,AABBCCDDEEFF,USR-DR164",
        b"+ok=off\r\n",
        b"+ok=Strong,80%\r\n",
    )
    sent: list[bytes] = []
    sock.sendto.side_effect = lambda data, _addr: sent.append(data)
    state = set_event_off(
        "192.168.80.187",
        sock=sock,
        sleep=lambda _s: None,
        log=lambda *_a, **_k: None,
    )
    assert state == "off"
    assert b"AT+EVENT=off\r\n" not in sent
    assert b"AT+Z\r\n" not in sent


def test_set_event_off_writes_then_restarts() -> None:
    sock = _session_replies(
        b"192.168.80.187,AABBCCDDEEFF,USR-DR164",
        b"+ok=on\r\n",
        b"+ok=Weak,30%\r\n",
        b"+ERR=-1\r\n+ok\r\n",
        b"+ok=off\r\n",
        b"+ok\r\n",
    )
    sent: list[bytes] = []
    sock.sendto.side_effect = lambda data, _addr: sent.append(data)

    class AfterReboot:
        def __init__(self, *_a, **_k) -> None:
            pass

        def __enter__(self) -> AfterReboot:
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def handshake(self) -> str:
            return "192.168.80.187,AABBCCDDEEFF,USR-DR164"

        def query_event(self) -> tuple[str, str]:
            return "off", "+ok=off\r\n"

    def open_session(host: str, sock=None, sleep=None):  # noqa: ANN001
        if sock is not None:
            return Dr164At(host, sock, sleep=sleep or (lambda _s: None))
        return AfterReboot()

    state = set_event_off(
        "192.168.80.187",
        sock=sock,
        wait_reboot_s=0.0,
        sleep=lambda _s: None,
        log=lambda *_a, **_k: None,
        open_session=open_session,
    )
    assert state == "off"
    assert SEARCH in sent
    assert ACK in sent
    assert b"AT+EVENT=off\r\n" in sent
    assert b"AT+Z\r\n" in sent
    assert sent.index(b"AT+EVENT=off\r\n") < sent.index(b"AT+Z\r\n")


def test_check_only_does_not_write() -> None:
    sock = _session_replies(
        b"192.168.80.187,AABBCCDDEEFF,USR-DR164",
        b"+ok=on\r\n",
        b"+ok=Weak,30%\r\n",
    )
    sent: list[bytes] = []
    sock.sendto.side_effect = lambda data, _addr: sent.append(data)
    state = set_event_off(
        "192.168.80.187",
        check_only=True,
        sock=sock,
        sleep=lambda _s: None,
        log=lambda *_a, **_k: None,
    )
    assert state == "on"
    assert b"AT+EVENT=off\r\n" not in sent


def test_main_discover_prints_hits(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("tools.dr164_event_off.discover", lambda: [("192.168.80.187", "192.168.80.187,AA,USR-DR164")])
    assert main([]) == 0
    assert "192.168.80.187" in capsys.readouterr().out


def test_open_udp_is_datagram() -> None:
    sock = __import__("tools.dr164_event_off", fromlist=["open_udp"]).open_udp()
    try:
        assert sock.type == socket.SOCK_DGRAM
    finally:
        sock.close()
