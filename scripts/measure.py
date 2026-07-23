#!/usr/bin/env python3
"""Measure what a session DELIVERED — map reads vs source re-reads — not artifact size.

`audit.py savings` reports a *ceiling*: how much smaller the maps are than the full source
(map bytes vs source bytes). That is honest as a ceiling but says nothing about a real
session. This reads the per-session ledger `session_log.py` writes and reports what the
agent actually did:

  - how many maps it read (the cheap consult the maps exist for),
  - how many source files it re-read *in folders that have a map* (the ceiling not realized),
  - the map-consultation rate across the mapped folders it touched.

That is the delivered signal — measured, per session, from behavior. Optionally, `--transcript
<path>` reads a Claude Code session `.jsonl` directly and counts its Read/Grep/Glob tool calls
the same way (best-effort: the transcript format is not a stable contract).

Usage:
    python3 measure.py session <root> [--session ID]      # from the .context-os ledger
    python3 measure.py session <root> --json
    python3 measure.py transcript <root> <session.jsonl>   # best-effort, from CC's own log
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

import session_log


def _tok(num_bytes: int) -> int:
    """~4 bytes/token — the same order-of-magnitude heuristic audit.py uses. An estimate."""
    return round(num_bytes / 4)


def summarize(root: Path, session_id: str) -> dict:
    """Aggregate one session's ledger into a delivered-savings summary dict."""
    entries = session_log.reads(root, session_id)

    maps_read = {e["path"] for e in entries if e.get("kind") == session_log.KIND_MAP}
    map_bytes = sum(e.get("bytes", 0) for e in entries if e.get("kind") == session_log.KIND_MAP)

    src_mapped = [e for e in entries if e.get("kind") == session_log.KIND_SOURCE_MAPPED]
    src_mapped_bytes = sum(e.get("bytes", 0) for e in src_mapped)
    src_unmapped = [e for e in entries if e.get("kind") == session_log.KIND_SOURCE_UNMAPPED]
    explore = [e for e in entries if e.get("kind") == session_log.KIND_EXPLORE]

    # A "touched mapped folder" is one whose map the session read, whose source it re-read,
    # or which it fanned out to explore (grep/glob). Consulted = its map was read.
    touched_owners = {e["owner"] for e in src_mapped + explore if e.get("owner")} | maps_read
    consulted = {owner for owner in touched_owners if owner in maps_read}
    rate = (len(consulted) / len(touched_owners)) if touched_owners else None

    return {
        "session": session_id,
        "maps_read": len(maps_read),
        "map_tokens_est": _tok(map_bytes),
        "source_in_mapped_dirs": len(src_mapped),
        "source_in_mapped_tokens_est": _tok(src_mapped_bytes),
        "source_no_map": len(src_unmapped),
        "explored_mapped_dirs": len(explore),
        "mapped_folders_touched": len(touched_owners),
        "mapped_folders_consulted": len(consulted),
        "consultation_rate": None if rate is None else round(rate, 2),
        "total_reads_logged": len(entries),
    }


def format_report(s: dict) -> str:
    lines = [
        f"context-os — delivered this session ({s['session']}):",
        f"  maps read:             {s['maps_read']:>4}  (~{s['map_tokens_est']} tok — the cheap consult)",
        f"  source in mapped dirs: {s['source_in_mapped_dirs']:>4}  (~{s['source_in_mapped_tokens_est']} tok — re-read despite a map)",
        f"  explored mapped dirs:  {s['explored_mapped_dirs']:>4}  (grep/glob fan-out the map exists to avoid)",
        f"  source, no map:        {s['source_no_map']:>4}",
    ]
    if s["consultation_rate"] is None:
        lines.append("  map-consultation rate: n/a (no mapped folder touched this session yet)")
    else:
        pct = round(s["consultation_rate"] * 100)
        lines.append(
            f"  map-consultation rate: {s['mapped_folders_consulted']}/{s['mapped_folders_touched']} "
            f"mapped folders ({pct}%) had their map read"
        )
    lines.append(
        "Delivered != ceiling: `audit.py savings` is the ceiling (artifact size); this is what the "
        "session actually did. The ceiling is realized only where a map read replaced a source re-read."
    )
    return "\n".join(lines)


# --- best-effort: read Claude Code's own session transcript ----------------------------

_READ_TOOLS = {"Read", "Grep", "Glob"}


def _iter_tool_paths(transcript_text: str):
    """Yield (tool_name, path_str) for Read/Grep/Glob tool_use entries in a CC .jsonl.

    Best-effort: tolerates unknown shapes, skips anything it can't parse. The transcript
    format is not a stable contract, so this is a corroborating view, not the source of truth.
    """
    for line in transcript_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = obj.get("message") if isinstance(obj, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name")
            if name not in _READ_TOOLS:
                continue
            tool_input = block.get("input") or {}
            path = tool_input.get("file_path") or tool_input.get("path")
            if path:
                yield name, str(path)


def summarize_transcript(root: Path, transcript: Path) -> dict:
    counts = {session_log.KIND_MAP: 0, session_log.KIND_SOURCE_MAPPED: 0,
              session_log.KIND_SOURCE_UNMAPPED: 0, session_log.KIND_OTHER: 0}
    try:
        text = transcript.read_text(errors="ignore")
    except OSError as exc:
        return {"error": str(exc)}
    for _tool, path in _iter_tool_paths(text):
        p = Path(path)
        resolved = p if p.is_absolute() else (root / p)
        kind, _owner = session_log.classify(root, resolved)
        counts[kind] = counts.get(kind, 0) + 1
    return {
        "transcript": str(transcript),
        "map_reads": counts[session_log.KIND_MAP],
        "source_in_mapped_dirs": counts[session_log.KIND_SOURCE_MAPPED],
        "source_no_map": counts[session_log.KIND_SOURCE_UNMAPPED],
        "other": counts[session_log.KIND_OTHER],
        "note": "best-effort — the Claude Code transcript format is not a stable contract",
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Measure delivered map use per session.")
    sub = parser.add_subparsers(dest="mode", required=True)

    sess = sub.add_parser("session", help="Summarize the .context-os ledger for a session")
    sess.add_argument("root", type=Path)
    sess.add_argument("--session", default=None, help="session id (default: most recent ledger)")
    sess.add_argument("--json", action="store_true")

    tr = sub.add_parser("transcript", help="Best-effort: count reads in a Claude Code .jsonl transcript")
    tr.add_argument("root", type=Path)
    tr.add_argument("transcript", type=Path)
    tr.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.mode == "session":
        session_id = args.session or session_log.latest_session_id(args.root)
        if not session_id:
            print("no session ledger found under .context-os/ (nothing read yet this session)",
                  file=sys.stderr)
            return 1
        summary = summarize(args.root, session_id)
        print(json.dumps(summary, indent=2) if args.json else format_report(summary))
        return 0

    result = summarize_transcript(args.root, args.transcript)
    if "error" in result:
        print(result["error"], file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
