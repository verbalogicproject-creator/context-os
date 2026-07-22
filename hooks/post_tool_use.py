#!/usr/bin/env python3
"""context-os PostToolUse — flip the owning map's staleness when source changes.

Wired via `hooks/hooks.json` on the `Edit|Write|MultiEdit` matcher. On a *successful*
edit to a source file, resolve the `map-*.ngf.md` that documents that file's folder and
recompute its staleness flag. The warning lives inside the map file (portable to any
tool), so this hook only rewrites that flag — it exits 0 silently, never blocks, never
speaks.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _common import bootstrap_import, emit, read_hook_input, repo_root_from, tool_failed

bootstrap_import()

from ctx_staleness import SRC_EXT, flip, owning_map  # noqa: E402

WATCHED_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})


def main() -> int:
    hook_input = read_hook_input()
    if hook_input.get("tool_name", "") not in WATCHED_TOOLS or tool_failed(hook_input):
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

    # Only a source file can move a folder's structural signature. (Editing a map's own
    # descriptions must NOT drift it — the signature is of the source, not the map.)
    if resolved.suffix not in SRC_EXT:
        emit({})
        return 0

    try:
        owner = owning_map(root, resolved)
        if owner is not None:
            flip(owner)
    except Exception:
        pass  # drift bookkeeping must never break a tool call

    emit({})
    return 0


if __name__ == "__main__":
    sys.exit(main())
