#!/usr/bin/env python3
"""context-os PreToolUse — re-check a map's staleness just before it is read.

Wired via `hooks/hooks.json` on the `Read` matcher. If the file about to be read is a
`map-*.ngf.md`, recompute its staleness flag first, so the read reflects the truth even
for *out-of-band* changes the PostToolUse hook never saw (a `git pull`, a branch switch,
an edit from another tool). Never blocks; exit 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _common import bootstrap_import, emit, read_hook_input, repo_root_from

bootstrap_import()

from ctx_staleness import _is_map_file, flip  # noqa: E402


def main() -> int:
    hook_input = read_hook_input()
    if hook_input.get("tool_name", "") != "Read":
        emit({})
        return 0

    tool_input = hook_input.get("tool_input") or {}
    file_path = str(tool_input.get("file_path", ""))
    if not file_path:
        emit({})
        return 0

    root = repo_root_from(hook_input)
    target = Path(file_path)
    resolved = target if target.is_absolute() else (root / target)

    if _is_map_file(resolved) and resolved.is_file():
        try:
            flip(resolved)
        except Exception:
            pass  # never let a drift re-check block a read

    emit({})
    return 0


if __name__ == "__main__":
    sys.exit(main())
