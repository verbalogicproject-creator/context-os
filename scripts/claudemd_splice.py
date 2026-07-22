#!/usr/bin/env python3
"""The ONLY tool allowed to mutate a managed CLAUDE.md block or the architecture.ctx changelog.

This implements the **augment-don't-clobber** boundary. An LLM agent (`ctx-scout` /
`ctx-updater`) never edits CLAUDE.md or the in-file ``# changelog:`` block directly —
it only produces the *text* that belongs inside the managed span. This module is the
deterministic helper that actually writes it, and it:

1. Writes a timestamped ``.bak`` of the target file before touching it (if it exists).
2. Locates the marker pair and replaces ONLY the bytes between them — appending the
   block at end-of-file if the markers are entirely absent — leaving every other byte
   of the file untouched.
3. REFUSES (raises / returns a refused result, never guesses) if the markers are
   malformed: exactly one of the pair present, duplicated pairs, or an end marker
   that appears before its start marker (e.g. a user hand-edited them).

Usage:
    python3 scripts/claudemd_splice.py claudemd CLAUDE.md --orientation orientation.txt
    python3 scripts/claudemd_splice.py changelog architecture.ctx --entry "2026-07-10 initial map"
    python3 scripts/claudemd_splice.py strip CLAUDE.md --markers claudemd
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

CLAUDE_START = "<!-- context-os:start -->"
CLAUDE_END = "<!-- context-os:end -->"
CHANGELOG_START = "# context-os:changelog:start"
CHANGELOG_END = "# context-os:changelog:end"


class MalformedMarkersError(Exception):
    """Raised when a marker pair exists but is malformed. Never guess — refuse and report."""


@dataclass(frozen=True)
class MarkerSpan:
    """A located, well-formed marker span. `end` is exclusive (past a consumed trailing newline)."""

    start: int
    end: int


def _find_markers(text: str, start_marker: str, end_marker: str) -> Optional[MarkerSpan]:
    """Locate a single well-formed marker span.

    Returns None if both markers are entirely absent (nothing to replace — append case).
    Raises MalformedMarkersError if the pair is malformed in any way.
    """
    start_count = text.count(start_marker)
    end_count = text.count(end_marker)

    if start_count == 0 and end_count == 0:
        return None
    if start_count != 1 or end_count != 1:
        raise MalformedMarkersError(
            f"expected exactly one {start_marker!r}/{end_marker!r} pair, "
            f"found {start_count} start marker(s) and {end_count} end marker(s)"
        )

    start_idx = text.index(start_marker)
    end_idx = text.index(end_marker)
    if end_idx < start_idx:
        raise MalformedMarkersError(
            f"{end_marker!r} appears before {start_marker!r} — markers are out of order"
        )

    span_end = end_idx + len(end_marker)
    if span_end < len(text) and text[span_end] == "\n":
        span_end += 1
    return MarkerSpan(start=start_idx, end=span_end)


def strip_block(text: str, start_marker: str, end_marker: str) -> str:
    """Return `text` with the managed block, AND its own separating blank lines, removed.

    Used to prove the augment-don't-clobber invariant: strip the block from a file
    before and after a splice — the remainder must be byte-identical. Blank lines
    immediately touching the marker span are treated as the block's own formatting
    (the separator `replace_block` inserts the first time it appends a block), not
    user content, so they are swallowed symmetrically on both sides before comparing.
    """
    span = _find_markers(text, start_marker, end_marker)
    if span is None:
        return text
    start, end = span.start, span.end
    while start >= 2 and text[start - 1] == "\n" and text[start - 2] == "\n":
        start -= 1
    while end + 1 < len(text) and text[end] == "\n" and text[end + 1] == "\n":
        end += 1
    return text[:start] + text[end:]


def replace_block(text: str, start_marker: str, end_marker: str, new_block: str) -> str:
    """Replace ONLY the bytes between the marker pair with `new_block`.

    If the markers are absent, `new_block` is appended at end-of-file (separated by
    a blank line). If the markers are malformed, raises MalformedMarkersError.
    """
    span = _find_markers(text, start_marker, end_marker)
    if span is None:
        prefix = text
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix and not prefix.endswith("\n\n"):
            prefix += "\n"
        return prefix + new_block
    return text[: span.start] + new_block + text[span.end :]


def _timestamped_backup(path: Path) -> Optional[Path]:
    """Write a timestamped `.bak` copy of `path` (if it exists) and return its path."""
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.{stamp}.bak")
    backup_path.write_bytes(path.read_bytes())
    return backup_path


@dataclass
class SpliceResult:
    """Outcome of a splice attempt."""

    path: Path
    backup_path: Optional[Path]
    refused: bool
    reason: Optional[str]
    changed: bool


def splice(
    path: Path,
    new_block: str,
    *,
    start_marker: str,
    end_marker: str,
    dry_run: bool = False,
) -> SpliceResult:
    """Splice `new_block` into `path` between the marker pair.

    This is the single low-level primitive both `splice_claudemd` and
    `splice_changelog_entry` funnel through — the ONLY code path that ever
    writes bytes into a managed marker span.
    """
    original = path.read_text() if path.exists() else ""
    try:
        updated = replace_block(original, start_marker, end_marker, new_block)
    except MalformedMarkersError as exc:
        return SpliceResult(path=path, backup_path=None, refused=True, reason=str(exc), changed=False)

    if updated == original:
        return SpliceResult(path=path, backup_path=None, refused=False, reason=None, changed=False)

    if dry_run:
        return SpliceResult(path=path, backup_path=None, refused=False, reason=None, changed=True)

    backup_path = _timestamped_backup(path)
    path.write_text(updated)
    return SpliceResult(path=path, backup_path=backup_path, refused=False, reason=None, changed=True)


# ---------------------------------------------------------------------------
# CLAUDE.md managed block
# ---------------------------------------------------------------------------


def build_claudemd_block(index_filename: str = "index.ngf.md") -> str:
    """Build the context-os pointer block (markers included).

    The same text works in CLAUDE.md and AGENTS.md — it is model-neutral, so a fresh
    Claude, Codex, or Gemini session reads it the same way. The load-bearing line is the
    one that stops the reflex to fan out exploration agents (the whole cost this removes).
    """
    return (
        f"{CLAUDE_START}\n"
        "## Architecture map — read before exploring\n"
        "This repo is mapped for cheap, cold orientation. Before reading source files or\n"
        "launching explore/search agents to understand how the code fits together, read the\n"
        "map — it is the architecture at a fraction of the tokens.\n"
        "\n"
        f"1. Start at `{index_filename}` (repo root) — it routes you to the folder you need.\n"
        "2. Read that folder's `map-*.ngf.md` for its graph (`->` calls, `~>` reads, `=>` HTTP).\n"
        "3. Before you EDIT, check that map's frontmatter `risk_areas` / `safe_edit_points`.\n"
        "\n"
        "Do NOT fan out exploration agents to reconstruct architecture the maps already document.\n"
        "If a map's frontmatter says `staleness: DRIFTED`, trust that folder loosely and verify\n"
        "against source — for that folder only.\n"
        f"{CLAUDE_END}\n"
    )


def splice_claudemd(path: Path, *, index_filename: str = "index.ngf.md", dry_run: bool = False) -> SpliceResult:
    """Insert or refresh ONLY the context-os block in CLAUDE.md / AGENTS.md. Never touches other content."""
    block = build_claudemd_block(index_filename)
    return splice(path, block, start_marker=CLAUDE_START, end_marker=CLAUDE_END, dry_run=dry_run)


# ---------------------------------------------------------------------------
# architecture.ctx `# changelog:` block (append-only)
# ---------------------------------------------------------------------------


def build_changelog_block(entries: List[str]) -> str:
    """Build the `# changelog:` block text (markers + header + one `#`-comment line per entry)."""
    lines = [CHANGELOG_START, "# changelog:"]
    lines += [f"#   {entry}" for entry in entries]
    lines.append(CHANGELOG_END)
    return "\n".join(lines) + "\n"


def _read_existing_changelog_entries(text: str) -> List[str]:
    """Read prior dated entries out of an existing changelog block, if any. Never drops them."""
    span = _find_markers(text, CHANGELOG_START, CHANGELOG_END)
    if span is None:
        return []
    inner = text[span.start : span.end]
    entries = []
    for line in inner.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        if stripped in (CHANGELOG_START, CHANGELOG_END, "# changelog:"):
            continue
        entries.append(stripped.lstrip("#").strip())
    return entries


def splice_changelog_entry(path: Path, new_entry: str, *, dry_run: bool = False) -> SpliceResult:
    """Append one dated entry inside architecture.ctx's managed changelog block.

    Reads the existing block's entries first (if any) so a refresh never silently
    drops the file's own history — this is how the file "documents its own evolution".
    """
    original = path.read_text() if path.exists() else ""
    try:
        prior_entries = _read_existing_changelog_entries(original)
    except MalformedMarkersError as exc:
        return SpliceResult(path=path, backup_path=None, refused=True, reason=str(exc), changed=False)

    block = build_changelog_block(prior_entries + [new_entry])
    return splice(path, block, start_marker=CHANGELOG_START, end_marker=CHANGELOG_END, dry_run=dry_run)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _report(result: SpliceResult, *, dry_run: bool) -> int:
    if result.refused:
        print(f"REFUSED: {result.reason}", file=sys.stderr)
        return 1
    if not result.changed:
        print(f"no change needed: {result.path}")
        return 0
    if result.backup_path:
        print(f"backed up -> {result.backup_path}")
    suffix = " (dry-run, not written)" if dry_run else ""
    print(f"spliced -> {result.path}{suffix}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for the three splice operations: claudemd, changelog, strip."""
    parser = argparse.ArgumentParser(
        description="The ONLY tool allowed to mutate a managed CLAUDE.md block or architecture.ctx changelog."
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    claudemd_p = sub.add_parser(
        "claudemd", help="Insert/refresh the context-os pointer block in CLAUDE.md or AGENTS.md"
    )
    claudemd_p.add_argument("path", type=Path)
    claudemd_p.add_argument("--index-filename", default="index.ngf.md")
    claudemd_p.add_argument("--dry-run", action="store_true")

    changelog_p = sub.add_parser("changelog", help="Append one dated entry to architecture.ctx's changelog block")
    changelog_p.add_argument("path", type=Path)
    changelog_p.add_argument("--entry", required=True, help='e.g. "2026-07-10 initial map (12 nodes, 8 edges)"')
    changelog_p.add_argument("--dry-run", action="store_true")

    strip_p = sub.add_parser("strip", help="Print a file with its managed block removed (audit helper)")
    strip_p.add_argument("path", type=Path)
    strip_p.add_argument("--markers", choices=["claudemd", "changelog"], default="claudemd")

    args = parser.parse_args(argv)

    if args.mode == "claudemd":
        result = splice_claudemd(args.path, index_filename=args.index_filename, dry_run=args.dry_run)
        return _report(result, dry_run=args.dry_run)

    if args.mode == "changelog":
        result = splice_changelog_entry(args.path, args.entry, dry_run=args.dry_run)
        return _report(result, dry_run=args.dry_run)

    # strip
    markers: Tuple[str, str] = (
        (CLAUDE_START, CLAUDE_END) if args.markers == "claudemd" else (CHANGELOG_START, CHANGELOG_END)
    )
    text = args.path.read_text() if args.path.exists() else ""
    try:
        print(strip_block(text, *markers), end="")
    except MalformedMarkersError as exc:
        print(f"error: malformed markers: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
