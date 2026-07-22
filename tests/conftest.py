"""Put `scripts/` on sys.path so tests import scan / audit / claudemd_splice / ctx_staleness
as plain modules — no packaging step, mirroring how Claude Code invokes them at runtime."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
