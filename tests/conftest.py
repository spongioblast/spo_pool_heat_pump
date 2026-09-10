"""Unit-test path: integration modules import as spo_pool_heat_pump.* via pythonpath."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HA_ROOT = Path(__file__).resolve().parents[1]
ROOT = HA_ROOT
WORKSPACE = HA_ROOT.parent
PROTOCOL_ANALYSIS = WORKSPACE / "protocol-analysis"
DUMPS = PROTOCOL_ANALYSIS / "dumps"
PROTOCOL = PROTOCOL_ANALYSIS / "protocol.json"
REPLAY_SERVER = PROTOCOL_ANALYSIS / "dump_replay_server.py"
HAS_PROTOCOL = PROTOCOL.is_file()
HAS_DUMPS = (DUMPS / "20260906_104432.log").is_file()
HAS_REPLAY = REPLAY_SERVER.is_file()
HAS_LAB = HAS_PROTOCOL and HAS_DUMPS
_LAB = "lab protocol-analysis/ not present (standalone clone)"

requires_lab = pytest.mark.skipif(not HAS_LAB, reason=_LAB)
requires_protocol = pytest.mark.skipif(not HAS_PROTOCOL, reason=_LAB)
requires_dumps = pytest.mark.skipif(not HAS_DUMPS, reason=_LAB)
requires_replay = pytest.mark.skipif(not HAS_REPLAY, reason=_LAB)

if str(HA_ROOT) not in sys.path:
    sys.path.insert(0, str(HA_ROOT))
