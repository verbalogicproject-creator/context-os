#!/usr/bin/env python3
"""Scaffold a portable session snapshot (`snapshot.ngf.md`) for cold-resume.

A snapshot is the episodic sibling of a map: it captures WHERE a work session is — a
compacted summary plus the decisions and next-steps as a small work-state graph — so
the session can resume cold on another machine or another model. Unlike a map it is
not drift-checked; it is a point-in-time capture, versioned by archiving the previous
one under `.context-os/snapshots/`.

This helper does the MECHANICAL parts only. The summary itself must be written by the
agent that holds the conversation (a subagent cannot see the parent session), so this
script records the git state and each map's `structural_hash` AT CAPTURE (so a cold
reader can tell whether code moved since), archives any previous snapshot, and writes
a scaffold the calling agent then fills in.

Usage:
    python3 snapshot.py scaffold <root> [--goal "one line"] [--now 2026-07-22T14:00:00Z]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ctx_staleness import fm_get  # noqa: E402  (reuse the frontmatter reader)


def _git(root: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def git_state(root: Path) -> dict:
    return {
        "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "(no git)",
        "head": _git(root, "rev-parse", "--short", "HEAD") or "(none)",
        "dirty": bool(_git(root, "status", "--porcelain")),
    }


def map_hashes(root: Path) -> list:
    rows = []
    for map_path in sorted(root.glob("**/map-*.ngf.md")):
        text = map_path.read_text()
        rows.append(
            (
                map_path.relative_to(root).as_posix(),
                fm_get(text, "structural_hash") or "unstamped",
                fm_get(text, "staleness") or "?",
            )
        )
    return rows


def scaffold(root: Path, goal: str, now: str):
    snap = root / "snapshot.ngf.md"
    archived = None
    if snap.exists():
        archive_dir = root / ".context-os" / "snapshots"
        archive_dir.mkdir(parents=True, exist_ok=True)
        stamp = now.replace(":", "").replace("-", "")
        archived = archive_dir / f"{stamp}.ngf.md"
        archived.write_text(snap.read_text())

    g = git_state(root)
    lines = [
        "---",
        "id: snapshot",
        "kind: snapshot",
        f"created: {now}",
        f'goal: "{goal}"',
        f"git_branch: {g['branch']}",
        f"git_head: {g['head']}",
        f"git_dirty: {str(g['dirty']).lower()}",
        "maps_at_capture:",
    ]
    for rel, structural_hash, staleness in map_hashes(root):
        lines.append(f"  - {{path: {rel}, structural_hash: {structural_hash}, staleness: {staleness}}}")
    lines += [
        "re_establish:",
        '  - "(agent: what a fresh machine must set up — install deps, env vars, running services)"',
        "---",
        "",
        "## summary",
        "",
        "<!-- agent: replace this with a compacted narrative of THIS session — what was",
        "     discussed, decided, tried, and rejected, and WHY. Relative paths only; no",
        "     machine-specific absolute paths or running-server assumptions. -->",
        "",
        "```ctx",
        "# work-state — decisions, artifacts, and what is next",
        "# format: ctx/1.1",
        "# node types: [decision] [task] [open] [artifact] [next]",
        "# edges: -> leads-to | ~> depends-on | => supersedes",
        "## state",
        "  # agent: fill with the real work-state, e.g.:",
        "  #   d1 : chose X over Y because Z [decision]",
        "  #   a1 : the artifact built so far [artifact] -> n1",
        "  #   n1 : the very next action [next]",
        "  #   o1 : still-open question [open]",
        "  # code pointers use file:symbol (robust to line drift), e.g. scan.py:to_per_folder_ngf",
        "```",
        "",
    ]
    snap.write_text("\n".join(lines))
    return snap, archived


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold a portable session snapshot.")
    sub = parser.add_subparsers(dest="mode", required=True)
    sc = sub.add_parser("scaffold", help="Write a snapshot.ngf.md scaffold (archives the previous one)")
    sc.add_argument("root", type=Path)
    sc.add_argument("--goal", default="(agent: one-line goal of this session)")
    sc.add_argument("--now", default=None, help="ISO8601 timestamp (default: now, UTC)")
    args = parser.parse_args(argv)

    now = args.now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snap, archived = scaffold(args.root.resolve(), args.goal, now)
    print(f"scaffolded {snap}")
    if archived:
        print(f"archived previous -> {archived}")
    print("Next: fill in ## summary and the work-state ```ctx block from the conversation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
