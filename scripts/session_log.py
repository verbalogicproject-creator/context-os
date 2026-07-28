#!/usr/bin/env python3
"""Per-session read ledger — the behavioral ground truth for "did the agent read the map?".

context-os's savings claim rests on one assumption: that a session reads the small map
instead of re-reading (or re-exploring) a folder's full source. The static `audit.py savings`
number is a *ceiling* (map bytes vs source bytes); it says nothing about what a session
actually did. This ledger records exactly that — each Read/Grep/Glob the session makes,
classified as a map read, a source read in a mapped folder, a source read with no map, or
other — to `.context-os/reads-<session>.jsonl`.

`measure.py` turns that ledger into a *delivered* number, so the claim is measured per real
session instead of asserted from artifact size. Stdlib only, offline, append-only. The
pattern (a per-session JSON ledger consulted from a PreToolUse hook) is the one Vouch already
proved live in this environment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Tuple

import ctx_staleness

KIND_MAP = "map"
KIND_SOURCE_MAPPED = "source_mapped"
KIND_SOURCE_UNMAPPED = "source_unmapped"
KIND_EXPLORE = "explore_mapped"  # a Grep/Glob over a folder that has a map (the fan-out the map exists to avoid)
KIND_OTHER = "other"


def log_dir(root: Path) -> Path:
    return root / ".context-os"


#: Everything context-os writes into `.context-os/` is local: the per-session read ledger, the
#: relay, and the scanner's regenerable digests (which are docstrings and signatures copied out
#: of the project's own source — noise in a commit, and stale the moment the code moves). The
#: maps themselves live beside the code and ARE meant to be committed.
#:
#: So the tool ignores its own artifacts from inside its own directory rather than editing the
#: project's root `.gitignore` — someone else's file, with its own conventions and its own
#: history. git honors a nested ignore file identically.
LOCAL_IGNORE_TEXT = """\
# context-os local artifacts — regenerable or session-scoped, never history.
# (Your maps, `map-*.ngf.md`, live beside your code and ARE meant to be committed.)
digests/
reads-*.jsonl
relay.ngf.md
"""


def ensure_log_dir(root: Path) -> Path:
    """Create `.context-os/` and, once, the ignore file that keeps its contents out of git.

    Never overwrites an existing ignore file. Committing a relay is a supported, deliberate
    per-case choice, so a project may have edited this file to allow one — silently reverting
    that would be the tool overruling the user inside their own repo.
    """
    directory = log_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    ignore = directory / ".gitignore"
    if not ignore.exists():
        try:
            ignore.write_text(LOCAL_IGNORE_TEXT)
        except OSError:
            pass  # an unwritable ignore file must never break the thing that needed the dir
    return directory


def _safe(session_id: str) -> str:
    return "".join(c for c in session_id if c.isalnum() or c in "-_") or "unknown"


def ledger_path(root: Path, session_id: str) -> Path:
    return log_dir(root) / f"reads-{_safe(session_id)}.jsonl"


def _rel(root: Path, resolved: Path) -> Optional[str]:
    """Repo-relative path, or None if `resolved` is OUTSIDE `root`.

    Returning None rather than the absolute path is the whole correctness of the ledger. This
    used to fall back to `str(resolved)`, and a session whose cwd is repo A while it reads files
    in repo B logged B's reads into A's ledger — where `owning_map` then looked for B's maps
    under A, found none, and scored them `source_unmapped`. Measured on one real session: 57 of
    80 entries were foreign-root, 36 of them scored "no map existed" for files that have one.
    A meter that under-reports map use is worse than no meter, because the number looks usable.
    """
    try:
        return str(resolved.resolve().relative_to(root.resolve()))
    except ValueError:
        return None


def contains(root: Path, resolved: Path) -> bool:
    """True if `resolved` lives inside `root` — the precondition for logging it at all."""
    return _rel(root, resolved) is not None


def classify(root: Path, resolved: Path) -> Tuple[str, Optional[Path]]:
    """Classify a path as (kind, owning_map). owning_map is set only for source_mapped.

    A path outside `root` is KIND_OTHER: this ledger cannot say anything true about it, and
    guessing is how the foreign-root defect scored mapped files as unmapped.
    """
    if not contains(root, resolved):
        return KIND_OTHER, None
    if ctx_staleness._is_map_file(resolved):
        return KIND_MAP, None
    if resolved.suffix in ctx_staleness.SRC_EXT:
        owner = ctx_staleness.owning_map(root, resolved)
        if owner is not None:
            return KIND_SOURCE_MAPPED, owner
        return KIND_SOURCE_UNMAPPED, None
    return KIND_OTHER, None


def record_read(root: Path, session_id: str, tool_name: str, resolved: Path) -> Optional[dict]:
    """Append one classified read entry to the session ledger. Returns the entry, or None.

    `other`-kind reads are not logged — they carry no signal about map use and would only
    bloat the ledger (and cost a write on a filesystem this environment flags as slow).
    """
    kind, owner = classify(root, resolved)
    if kind == KIND_OTHER:
        return None  # includes every path outside `root` — not this ledger's to describe
    rel = _rel(root, resolved)
    if rel is None:
        return None
    try:
        size = resolved.stat().st_size if resolved.is_file() else 0
    except OSError:
        size = 0
    entry = {
        "tool": tool_name,
        "path": rel,
        "kind": kind,
        "bytes": size,
        "owner": _rel(root, owner) if owner is not None else None,
    }
    try:
        ensure_log_dir(root)
        with open(ledger_path(root, session_id), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        return None
    return entry


def record_explore(root: Path, session_id: str, tool_name: str, resolved_dir: Path) -> Optional[dict]:
    """Log a Grep/Glob over a folder that has a map (kind=explore_mapped), else no-op.

    This is the fan-out exploration the map exists to replace — measuring it is how we learn
    whether the pointer block is actually changing behavior. Returns the entry, or None if
    the searched folder has no map.
    """
    rel = _rel(root, resolved_dir)
    if rel is None:
        return None  # a Grep in another repo says nothing about this one's maps
    owner = ctx_staleness.owning_map(root, resolved_dir)
    if owner is None:
        return None
    entry = {
        "tool": tool_name,
        "path": rel,
        "kind": KIND_EXPLORE,
        "bytes": 0,
        "owner": _rel(root, owner),
    }
    try:
        ensure_log_dir(root)
        with open(ledger_path(root, session_id), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        return None
    return entry


def reads(root: Path, session_id: str) -> List[dict]:
    """Load this session's ledger entries (empty list if missing/corrupt — never raises)."""
    path = ledger_path(root, session_id)
    if not path.is_file():
        return []
    out: List[dict] = []
    try:
        raw = path.read_text(errors="ignore")
    except OSError:
        return []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out


def map_read_this_session(root: Path, session_id: str, owner_map: Path) -> bool:
    """True if this session already read the map file `owner_map`."""
    target = _rel(root, owner_map)
    return any(e.get("kind") == KIND_MAP and e.get("path") == target for e in reads(root, session_id))


def folder_touched_before(root: Path, session_id: str, owner_rel: str) -> bool:
    """True if this session already logged a read whose owning map is `owner_rel`.

    Used to fire the "there's a map for this folder" nudge at most once per folder.
    """
    for entry in reads(root, session_id):
        if entry.get("path") == owner_rel or entry.get("owner") == owner_rel:
            return True
    return False


def latest_session_id(root: Path) -> Optional[str]:
    """Best-effort: the session id of the most recently written ledger (for the CLI)."""
    directory = log_dir(root)
    if not directory.is_dir():
        return None
    cands = sorted(directory.glob("reads-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0].name[len("reads-"):-len(".jsonl")] if cands else None
