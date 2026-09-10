"""State-model heat-pump simulator."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CC = _ROOT / "custom_components"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_CC) not in sys.path:
    sys.path.insert(0, str(_CC))
