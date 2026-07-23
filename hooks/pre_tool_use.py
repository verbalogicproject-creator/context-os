#!/usr/bin/env python3
"""context-os PreToolUse — keep a map's drift flag honest, log map-vs-source use, gently nudge.

Wired via `hooks/hooks.json` on the `Read|Grep|Glob` matcher. It does three things, none of
which ever block a tool call (exit 0 always):

1. Read of a `map-*.ngf.md`: recompute its staleness flag first, so the read reflects truth
   even for out-of-band changes (a `git pull`, a branch switch, an edit from another tool).
2. Log the call to the per-session ledger (`session_log.py`) — a map read, a source read in a
   mapped folder, or a grep/glob fan-out over a mapped folder — so `measure.py` can report what
   the session actually did instead of an artifact-size guess.
3. Once per folder, if the session reaches for source (or fans out) in a folder whose map it
   has not read, emit a one-line informational nudge that the map is there. `systemMessage`
   only — never a permission decision.
"""

from __future__ import annotations

import sys
from pathlib import Path

from _common import bootstrap_import, emit, read_hook_input, repo_root_from

bootstrap_import()

import session_log  # noqa: E402
from ctx_staleness import _is_map_file, flip  # noqa: E402

WATCHED_TOOLS = frozenset({"Read", "Grep", "Glob"})


def _first_source_touch(root: Path, session_id: str, owner_rel: str) -> bool:
    """True iff exactly one ledger entry so far owns `owner_rel` (this one) — i.e. first touch."""
    same = [e for e in session_log.reads(root, session_id) if e.get("owner") == owner_rel]
    return len(same) == 1


def main() -> int:
    hook_input = read_hook_input()
    tool_name = hook_input.get("tool_name", "")
    if tool_name not in WATCHED_TOOLS:
        emit({})
        return 0

    tool_input = hook_input.get("tool_input") or {}
    raw_path = str(tool_input.get("file_path") or tool_input.get("path") or "")
    if not raw_path:
        emit({})  # a repo-wide grep/glob names no folder — nothing to attribute
        return 0

    root = repo_root_from(hook_input)
    session_id = str(hook_input.get("session_id", "unknown"))
    target = Path(raw_path)
    resolved = target if target.is_absolute() else (root / target)

    nudge = None
    try:
        if tool_name == "Read":
            if _is_map_file(resolved) and resolved.is_file():
                try:
                    flip(resolved)  # keep drift honest before the read
                except Exception:
                    pass
            entry = session_log.record_read(root, session_id, tool_name, resolved)
            if entry and entry["kind"] == session_log.KIND_SOURCE_MAPPED and entry.get("owner"):
                owner_rel = entry["owner"]
                if not session_log.map_read_this_session(root, session_id, root / owner_rel) \
                        and _first_source_touch(root, session_id, owner_rel):
                    nudge = (f"context-os: {owner_rel} maps this folder — reading that small map "
                             "is cheaper than re-reading its source here.")
        else:  # Grep / Glob over a folder
            entry = session_log.record_explore(root, session_id, tool_name, resolved)
            if entry and entry.get("owner"):
                owner_rel = entry["owner"]
                if not session_log.map_read_this_session(root, session_id, root / owner_rel) \
                        and _first_source_touch(root, session_id, owner_rel):
                    nudge = (f"context-os: {owner_rel} already maps this folder — reading it is "
                             "cheaper than exploring the source.")
    except Exception:
        nudge = None  # telemetry/nudge must never break a tool call

    emit({"systemMessage": nudge} if nudge else {})
    return 0


if __name__ == "__main__":
    sys.exit(main())
