"""Shared bootstrap for context-os's two drift hooks.

Both hook scripts are invoked directly by Claude Code as
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<name>.py"`, so they must work with zero
setup (no `pip install`). This puts `<plugin_root>/scripts` on `sys.path` before
importing `ctx_staleness`, exactly like the vouch / hookify `PLUGIN_ROOT` pattern.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def bootstrap_import() -> None:
    """Put `<plugin_root>/scripts` on `sys.path` so `import ctx_staleness` works unconditionally."""
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root:
        # Not running under Claude Code (e.g. manual testing) — fall back to hooks/../.
        plugin_root = str(Path(__file__).resolve().parent.parent)
    scripts_dir = str(Path(plugin_root) / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


def read_hook_input() -> dict:
    """Read and JSON-decode the hook input from stdin. Never raises (fail safe on junk)."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def repo_root_from(hook_input: dict) -> Path:
    """The repo root for this call: hook input's `cwd`, else `$CLAUDE_PROJECT_DIR`, else process cwd."""
    cwd = hook_input.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(cwd).resolve() if cwd else Path.cwd()


def tool_failed(hook_input: dict) -> bool:
    """True if the PostToolUse result carries an explicit error (a failed edit teaches nothing)."""
    result = hook_input.get("tool_response")
    if result is None:
        result = hook_input.get("tool_result")
    return isinstance(result, dict) and bool(result.get("error"))


def emit(payload: dict) -> None:
    """Write `payload` as the hook's JSON stdout response."""
    print(json.dumps(payload))
