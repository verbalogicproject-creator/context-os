"""Put `scripts/` and `hooks/` on sys.path so tests import scan / audit / claudemd_splice /
ctx_staleness / _common as plain modules — no packaging step, mirroring how Claude Code invokes
them at runtime."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))
sys.path.insert(0, str(_ROOT / "hooks"))
