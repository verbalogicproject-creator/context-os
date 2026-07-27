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


# --- real token usage, straight from the transcript ------------------------------------
#
# WHY THIS EXISTS. Every other number in this file is `bytes/4`. That is fine for a ceiling
# and wrong for a delivered figure — it is an estimate of an estimate. Claude Code already
# records the REAL usage on every assistant turn, so the delivered number never had to be a
# guess; nothing was reading it.
#
# WHAT THE REAL NUMBERS SHOWED, measured over three long sessions (5,319 / 2,262 / 1,325
# turns) before this was written:
#
#     cache_read  61-73%   cache_create  10-15%   output  14-25%   raw input  ~0.02%
#
# The dominant cost is not the one-time discovery pass. It is `cache_read` — the accumulated
# prefix, re-processed on EVERY turn. Mean prefix across those sessions was 238k-467k tokens
# per turn.
#
# That changes what a map is worth, and in which direction. A file read is not a one-time
# charge: a 30k-token read admitted at turn 100 of a 5,000-turn window is ~30k of
# cache_create PLUS 30k re-read on each of the ~4,900 turns that follow. Substituting a 3k
# map for it is worth ~132M cache-read tokens, not 27k. The mechanism is far stronger than
# "sessions start cheaper" claims — and "start" is the wrong word for it, because the saving
# accrues across the whole session, not at its beginning.
#
# So the cost model here is an INTEGRAL over turns, and `--at-turn` exists to price a
# decision at the moment it is made rather than in aggregate.

#: Cost of each token class as a multiple of one input token, per Anthropic's published
#: ratios (cache read 0.1x, cache write 1.25x, output 5x). Ratios, not prices — they are
#: what decides where the money goes, and they hold across model tiers.
WEIGHTS = {
    "input_tokens": 1.0,
    "cache_creation_input_tokens": 1.25,
    "cache_read_input_tokens": 0.1,
    "output_tokens": 5.0,
}


def usage_totals(transcript_text: str) -> dict:
    """Sum the real per-turn `usage` blocks in a Claude Code transcript.

    Unlike `_iter_tool_paths` this is not a heuristic over tool arguments — `usage` is
    reported by the API itself. It is still guarded, because the transcript's *envelope*
    (where `usage` sits in the JSON) is not a stable contract even though its contents are.
    """
    totals = {key: 0 for key in WEIGHTS}
    turns = 0
    for line in transcript_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = obj.get("message") if isinstance(obj, dict) else None
        usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict):
            continue
        turns += 1
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int):
                totals[key] += value
    return {"turns": turns, **totals}


def cost_profile(totals: dict) -> dict:
    """Weighted cost share per token class, plus the mean prefix re-processed each turn."""
    weighted = {key: totals.get(key, 0) * weight for key, weight in WEIGHTS.items()}
    grand = sum(weighted.values())
    turns = totals.get("turns", 0)
    return {
        "turns": turns,
        "totals": {key: totals.get(key, 0) for key in WEIGHTS},
        "weighted_share": {
            key: (round(value / grand, 4) if grand else 0.0) for key, value in weighted.items()
        },
        "mean_prefix_tokens": round(totals.get("cache_read_input_tokens", 0) / turns) if turns else 0,
    }


def context_tax(tokens: int, turns_remaining: int) -> dict:
    """What admitting `tokens` into context actually costs over `turns_remaining` turns.

    The number people reason with is `tokens` — the one-time size of the read. The number
    they pay is this one. Kept as a function rather than a comment because the gap between
    the two is the entire argument for a map, and it should be computable, not asserted.
    """
    create = tokens * WEIGHTS["cache_creation_input_tokens"]
    reread = tokens * turns_remaining * WEIGHTS["cache_read_input_tokens"]
    return {
        "tokens": tokens,
        "turns_remaining": turns_remaining,
        "cache_read_tokens": tokens * turns_remaining,
        "weighted_cost": round(create + reread, 1),
        "multiple_of_naive": round((create + reread) / tokens, 2) if tokens else 0.0,
    }


def format_cost(profile: dict) -> str:
    share = profile["weighted_share"]
    totals = profile["totals"]
    lines = [
        f"context-os — real token usage across {profile['turns']} turns:",
        f"  cache read (prefix re-processed each turn) {totals['cache_read_input_tokens']:>15,}"
        f"   {share['cache_read_input_tokens']:>6.1%} of cost",
        f"  cache create (first sight of new content)  {totals['cache_creation_input_tokens']:>15,}"
        f"   {share['cache_creation_input_tokens']:>6.1%}",
        f"  output                                     {totals['output_tokens']:>15,}"
        f"   {share['output_tokens']:>6.1%}",
        f"  raw input (uncached)                       {totals['input_tokens']:>15,}"
        f"   {share['input_tokens']:>6.1%}",
        "",
        f"  mean prefix re-processed per turn: {profile['mean_prefix_tokens']:,} tokens",
        "",
        "Cost is the INTEGRAL of context size over turns, not a startup charge. Anything",
        "admitted early is paid again on every turn that follows — which is why replacing a",
        "source re-read with a map read is worth far more than the size difference suggests.",
    ]
    return "\n".join(lines)


def catchup_targets(root: Path, session_id: str) -> List[str]:
    """Folders touched this session whose map is still skeleton-only (unenriched).

    The lazy flow: `/context-os --skeleton` maps every folder cheaply; the ledger records which
    folders the session actually touched; `/context-os-catchup` enriches exactly those of them
    that are still skeletons — so enrichment cost tracks real use, not the whole repo.
    """
    import audit  # local: only the catch-up path needs the enrichment check

    owners = set()
    for entry in session_log.reads(root, session_id):
        kind = entry.get("kind")
        if kind in (session_log.KIND_SOURCE_MAPPED, session_log.KIND_EXPLORE) and entry.get("owner"):
            owners.add(entry["owner"])
        elif kind == session_log.KIND_MAP and entry.get("path"):
            owners.add(entry["path"])

    targets = []
    for owner_rel in owners:
        map_path = root / owner_rel
        if map_path.is_file() and not audit.map_is_enriched(map_path):
            folder = Path(owner_rel).parent.as_posix()
            targets.append("." if folder in ("", ".") else folder)
    return sorted(set(targets))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Measure delivered map use per session.")
    sub = parser.add_subparsers(dest="mode", required=True)

    sess = sub.add_parser("session", help="Summarize the .context-os ledger for a session")
    sess.add_argument("root", type=Path)
    sess.add_argument("--session", default=None, help="session id (default: most recent ledger)")
    sess.add_argument("--json", action="store_true")

    cu = sub.add_parser("catchup", help="Folders touched this session whose map is still skeleton-only")
    cu.add_argument("root", type=Path)
    cu.add_argument("--session", default=None, help="session id (default: most recent ledger)")
    cu.add_argument("--json", action="store_true")

    tr = sub.add_parser("transcript", help="Best-effort: count reads in a Claude Code .jsonl transcript")
    tr.add_argument("root", type=Path)
    tr.add_argument("transcript", type=Path)
    tr.add_argument("--json", action="store_true")

    cost = sub.add_parser(
        "cost", help="REAL token usage from a Claude Code .jsonl transcript (not an estimate)"
    )
    cost.add_argument("transcript", type=Path)
    cost.add_argument("--json", action="store_true")
    cost.add_argument(
        "--at-turn", type=int, default=None, metavar="N",
        help="Also price admitting --tokens into context at turn N of this session.",
    )
    cost.add_argument("--tokens", type=int, default=30000,
                      help="Token size to price with --at-turn (default 30000, ~5 medium files).")

    args = parser.parse_args(argv)

    if args.mode == "cost":
        try:
            text = args.transcript.read_text(errors="ignore")
        except OSError as exc:
            print(exc, file=sys.stderr)
            return 1
        totals = usage_totals(text)
        if not totals["turns"]:
            print("no usage data in that transcript — wrong file, or the format changed",
                  file=sys.stderr)
            return 1
        profile = cost_profile(totals)
        if args.at_turn is not None:
            profile["context_tax"] = context_tax(
                args.tokens, max(0, profile["turns"] - args.at_turn)
            )
        if args.json:
            print(json.dumps(profile, indent=2))
        else:
            print(format_cost(profile))
            tax = profile.get("context_tax")
            if tax:
                print(
                    f"\n  admitting {tax['tokens']:,} tokens at turn {args.at_turn} costs "
                    f"{tax['multiple_of_naive']}x its apparent size "
                    f"({tax['cache_read_tokens']:,} cache-read tokens over "
                    f"{tax['turns_remaining']} remaining turns)"
                )
        return 0

    if args.mode == "session":
        session_id = args.session or session_log.latest_session_id(args.root)
        if not session_id:
            print("no session ledger found under .context-os/ (nothing read yet this session)",
                  file=sys.stderr)
            return 1
        summary = summarize(args.root, session_id)
        print(json.dumps(summary, indent=2) if args.json else format_report(summary))
        return 0

    if args.mode == "catchup":
        session_id = args.session or session_log.latest_session_id(args.root)
        if not session_id:
            print("no session ledger yet — nothing touched to catch up on", file=sys.stderr)
            return 0
        targets = catchup_targets(args.root, session_id)
        print(json.dumps(targets, indent=2) if args.json else "\n".join(targets))
        return 0

    result = summarize_transcript(args.root, args.transcript)
    if "error" in result:
        print(result["error"], file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
