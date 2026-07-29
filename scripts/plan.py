#!/usr/bin/env python3
"""Rank folders by architectural importance so /context-os maps what matters — not every folder.

Deterministic, LLM-free, computed from the scan graph the scanner already builds. For each folder:
  code_files : source files directly in it
  in_degree  : cross-folder imports INTO it (other folders depend on it — a real dependency)
  out_degree : cross-folder imports OUT of it (it coordinates others — a hub)
  has_entry  : holds a likely entry point (main/app/index/server/page/route/middleware/…)
  score      : code_files + 2*in_degree + 0.5*out_degree + (5 if has_entry)

Tiers (transparent rules, tunable):
  DEEP     : enrich — real substance: meaningful code (≥ deep_min_files) OR a hub (in_degree ≥ hub_in)
  SKELETON : structure-only, no enricher — small / peripheral code
  FOLD     : pure docs/data/config (no code) — folded into the nearest mapped ancestor, never dropped

Tier says how much a folder is worth DESCRIBING. A second, orthogonal decision says whether it is
worth its OWN FILE — `keeps_map`. A map's cost is paid by every session that reads it, so one file
per folder over-fragments a small repo (five folders holding one file each cost five reads and five
headers), while one file for a whole repo makes every session pay for the parts it is not touching.
So a folder MERGES into its nearest map-keeping ancestor when it is too thin to earn a file — no
code at all, or SKELETON, or a thin DEEP folder that is not a hub (≤ merge_max_files and
in_degree < merge_hub_in) — and keeps its own map otherwise. A hub keeps its card however small:
the folders everything imports are exactly the ones worth reading on their own.

An entry point does NOT force DEEP on its own (a repo like Next.js has many thin one-file route
folders): it adds to the score and flags the folder `borderline`, so the agent can promote a
thin-but-critical entry in step (c) — rather than auto-enriching every route.

So a big repo pays for the handful of folders that carry the architecture, not all of them. The
`borderline` flag marks the ambiguous middle — the folders the agent may promote/demote (step (c)).
Nothing is silently dropped: FOLD folders name their `fold_into` parent and still show in the report.

Usage:
    python3 plan.py <root>                          # ranked table
    python3 plan.py <root> --json                    # structured
    python3 plan.py <root> --deep-min-files N --hub-in N
    python3 plan.py <root> --merge-max-files N --merge-hub-in N
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

import scan as scan_module

ENTRY_STEMS = frozenset(
    {
        "main", "__main__", "app", "index", "server", "cli", "run", "manage",
        "wsgi", "asgi", "page", "layout", "route", "middleware",
    }
)

DEFAULT_DEEP_MIN_FILES = 3
DEFAULT_HUB_IN = 2

# Merging CODE folders is OFF by default — measured, not assumed.
#
# The first cut of this rule merged a 17-folder project into 6 maps and looked like a 34.6%
# win on the size of the whole map set. That is the wrong metric: a session does not read the
# set, it reads the one map covering the folder it is in. Measured per folder on the same
# source, 12 of 15 folders cost MORE and none cost less — `services` went 95 → 634 tokens,
# 6.7x — because merging trades fragmentation for DILUTION, and the nine folders absorbed
# into one map averaged 125 tokens each, so the merged map only pays off once a task spans
# ~6 of them. Real tasks span two or three.
#
# So the default is one map per folder for code: zero dilution, which is the safe prior when
# nothing is known about how the folders are actually read together. `merge_max_files=0`
# leaves only the original FOLD behaviour (code-free docs/data folders merge into their
# parent, which was always right — they carry no architecture of their own).
#
# The plan was to EARN merging from the read ledger — folders genuinely read together are the
# ones worth sharing a map. That is now closed, because the cost model says the ledger cannot
# rescue it. Decompose the map set:
#
#     total = N_maps x fixed_cost + content
#
# Merging reduces N_maps. Measured on a real 17-map project: the fixed cost of a map (the
# frontmatter plus the ctx header) is ~79 tokens, and the mean content of one is ~146 tokens.
# So merging two folders saves at most ONE fixed block, 79 tokens — and only on a task that
# touches both. A task touching just one of the pair pays the other's 146 tokens of content.
# Break-even is therefore
#
#     p(read together) > 146 / (146 + 79)  ~=  0.65
#
# Two folders must be co-accessed on MORE THAN 65% of tasks before merging them breaks even,
# and the bar climbs steeply for clusters (the refuted rule merged nine). No plausible ledger
# makes that pay: the upside is capped at one small header while the downside is uncapped and
# was measured at 6.7x. Collecting co-access data would not change the arithmetic.
#
# This also settles the direction of future work: attack `fixed_cost`, not `N_maps`. Shrinking
# the per-map overhead is free — no dilution, no behavioural assumption — and it makes merging
# strictly worse, because every token cut from the header lowers the 79 and raises the 0.65.
# Make the unit cheap rather than making fewer units; fewer units costs the property that makes
# maps work at all, which is loading only what the task needs.
#
# The flags below stay as an ESCAPE HATCH for a repo whose folders really are read together —
# they are not a recommendation, and they are not a default anyone should reach for.
# `test_plan.py` pins the default at 0 so it cannot drift back on quietly.
DEFAULT_MERGE_MAX_FILES = 0
DEFAULT_MERGE_HUB_IN = 5


def _folder_of(node) -> str:
    """The node's folder as a plan key: repo-relative dir, or '.' for the repo root."""
    return node.dir or "."


def _is_own_artifact(path: str) -> bool:
    """A map or the index — context-os's own output, never part of the folder tally.

    Counting these makes the plan depend on whether it has already run: the moment
    `index.ngf.md` lands, the repo root acquires a node, becomes a map-keeping folder, and
    starts absorbing folders that were fine on their own. The plan has to give the same answer
    before and after an emit.
    """
    name = path.rsplit("/", 1)[-1]
    return name == "index.ngf.md" or (name.startswith("map-") and name.endswith(".ngf.md"))


def _depth(folder: str) -> int:
    """Path depth, root at 0 — the order keep/merge decisions must be made in."""
    return 0 if folder == "." else folder.count("/") + 1


def _nearest_keeping_ancestor(folder: str, keeps: set) -> Optional[str]:
    """Nearest ancestor that keeps its own map — where this folder's nodes merge into.

    `None` means there is nowhere to merge, so the folder must keep its own map. That is what
    makes the rule total: no folder is ever dropped for want of a parent.
    """
    if folder == ".":
        return None
    parts = folder.split("/")
    for i in range(len(parts) - 1, 0, -1):
        ancestor = "/".join(parts[:i])
        if ancestor in keeps:
            return ancestor
    return "." if "." in keeps else None


def _wants_merge(row: dict, host: Optional[dict], merge_max_files: int, merge_hub_in: int) -> bool:
    """True if this folder is too thin to earn its own map file, and `host` can take it.

    Three cases, widest first: no code at all (pure docs/data/config); SKELETON (small or
    peripheral code); or a thin DEEP folder that nothing much depends on. The hub test is the
    exception that keeps this honest — a folder with `in_degree >= merge_hub_in` is read on its
    own by whoever imports it, so it keeps its card no matter how few files it holds.

    Code never merges into a code-free host. A repo whose root holds only a README would
    otherwise pull `backend/` and `frontend/` into a docs map — the merge running upward past
    the architecture instead of stopping at it.
    """
    if row["code_files"] == 0:
        return True                      # no architecture of its own — always folds (the old FOLD tier)
    if merge_max_files <= 0:
        return False                     # code folders keep their own map unless merging is asked for
    if host is not None and host["code_files"] == 0:
        return False
    if row["tier"] == "SKELETON":
        return True
    return row["code_files"] <= merge_max_files and row["in_degree"] < merge_hub_in


def _assign_maps(rows: List[dict], merge_max_files: int, merge_hub_in: int) -> None:
    """Decide, in place and top-down, which folders keep their own map and which merge upward.

    Shallowest-first, because a folder may only merge into an ancestor that is itself keeping a
    map. That ordering buys two guarantees for free: no chains (A into B into C, where B is gone),
    and no orphans (a folder with nowhere to go keeps its map instead of vanishing).
    """
    by_folder = {r["folder"]: r for r in rows}
    keeps: set = set()
    for row in sorted(rows, key=lambda r: (_depth(r["folder"]), r["folder"])):
        ancestor = _nearest_keeping_ancestor(row["folder"], keeps)
        host = by_folder.get(ancestor) if ancestor else None
        if ancestor is not None and _wants_merge(row, host, merge_max_files, merge_hub_in):
            row["fold_into"] = ancestor
            row["keeps_map"] = False
        else:
            row["fold_into"] = None
            row["keeps_map"] = True
            keeps.add(row["folder"])

    absorbed: Dict[str, List[str]] = {}
    absorbed_code: Dict[str, int] = {}
    for row in rows:
        if row["fold_into"]:
            absorbed.setdefault(row["fold_into"], []).append(row["folder"])
            absorbed_code[row["fold_into"]] = absorbed_code.get(row["fold_into"], 0) + row["code_files"]
    for row in rows:
        row["absorbs"] = sorted(absorbed.get(row["folder"], []))
        row["absorbed_code_files"] = absorbed_code.get(row["folder"], 0)


def _needs_enricher(row: dict) -> bool:
    """Folders worth an enricher call: the ones that keep a map AND carry code — their own
    (DEEP) or code they absorbed from a merged child. A map holding only content nodes is
    already described deterministically by the scanner, so it needs no model."""
    return bool(row["keeps_map"]) and (row["tier"] == "DEEP" or row["absorbed_code_files"] > 0)


def _is_borderline(row: dict, deep_min_files: int, hub_in: int) -> bool:
    """Would flipping one threshold change this folder's tier? Then the agent should weigh in."""
    if row["tier"] == "FOLD":
        return False
    if row["tier"] == "SKELETON":
        # one step from DEEP, or a thin entry point the agent may want to promote
        return (
            row["code_files"] >= deep_min_files - 1
            or row["in_degree"] >= hub_in - 1
            or row["has_entry"]
        )
    # DEEP that qualified ONLY by the min-files edge (not a hub) — the agent may demote
    return row["code_files"] == deep_min_files and row["in_degree"] < hub_in


def compute_plan(
    root: Path,
    deep_min_files: int = DEFAULT_DEEP_MIN_FILES,
    hub_in: int = DEFAULT_HUB_IN,
    merge_max_files: int = DEFAULT_MERGE_MAX_FILES,
    merge_hub_in: int = DEFAULT_MERGE_HUB_IN,
) -> dict:
    """Rank every folder in `root` into DEEP / SKELETON / FOLD from the scan graph."""
    result = scan_module.scan(root)
    name_to_dir = {n.name: _folder_of(n) for n in result.nodes}

    folders: Dict[str, dict] = {}
    for node in result.nodes:
        if _is_own_artifact(node.path):
            continue
        folder = _folder_of(node)
        tally = folders.setdefault(folder, {"code": 0, "content": 0, "in": 0, "out": 0, "entry": False})
        if node.ext in scan_module.SOURCE_EXTENSIONS:
            tally["code"] += 1
        else:
            tally["content"] += 1
        if Path(node.path).stem.lower() in ENTRY_STEMS:
            tally["entry"] = True

    for edge in result.edges:
        src_dir = name_to_dir.get(edge.source)
        tgt_dir = name_to_dir.get(edge.target)
        if src_dir is None or tgt_dir is None or src_dir == tgt_dir:
            continue  # ext targets / intra-folder edges don't count toward cross-folder degree
        folders[src_dir]["out"] += 1
        folders[tgt_dir]["in"] += 1

    rows: List[dict] = []
    for folder in sorted(folders):
        tally = folders[folder]
        score = tally["code"] + 2.0 * tally["in"] + 0.5 * tally["out"] + (3.0 if tally["entry"] else 0.0)
        if tally["code"] == 0:
            tier = "FOLD"
        elif tally["code"] >= deep_min_files or tally["in"] >= hub_in:
            tier = "DEEP"
        else:
            tier = "SKELETON"
        rows.append(
            {
                "folder": folder,
                "tier": tier,
                "code_files": tally["code"],
                "content_files": tally["content"],
                "in_degree": tally["in"],
                "out_degree": tally["out"],
                "has_entry": tally["entry"],
                "score": round(score, 1),
            }
        )

    _assign_maps(rows, merge_max_files=merge_max_files, merge_hub_in=merge_hub_in)
    for row in rows:
        row["borderline"] = _is_borderline(row, deep_min_files, hub_in)

    rows.sort(key=lambda r: (-r["score"], r["folder"]))
    summary = {
        "deep": sum(1 for r in rows if r["tier"] == "DEEP"),
        "skeleton": sum(1 for r in rows if r["tier"] == "SKELETON"),
        "fold": sum(1 for r in rows if r["tier"] == "FOLD"),
        "maps": sum(1 for r in rows if r["keeps_map"]),
        "merged": sum(1 for r in rows if not r["keeps_map"]),
        "enrich": [r["folder"] for r in rows if _needs_enricher(r)],
        "borderline": [r["folder"] for r in rows if r["borderline"]],
    }
    return {
        "root": str(root),
        "folders": rows,
        "summary": summary,
        "params": {
            "deep_min_files": deep_min_files,
            "hub_in": hub_in,
            "merge_max_files": merge_max_files,
            "merge_hub_in": merge_hub_in,
        },
    }


def format_table(plan: dict) -> str:
    lines = [f"{'TIER':9}{'MAP':4}{'code':>5}{'in':>4}{'out':>4}  E {'score':>6}  folder"]
    for r in plan["folders"]:
        entry = "Y" if r["has_entry"] else " "
        star = " *" if r["borderline"] else ""
        keeps = "own" if r["keeps_map"] else "  ↑"
        fold = f"  → merge into {r['fold_into']}" if r["fold_into"] else ""
        absorbs = f"  (absorbs {len(r['absorbs'])})" if r["absorbs"] else ""
        lines.append(
            f"{r['tier']:9}{keeps:4}{r['code_files']:>5}{r['in_degree']:>4}{r['out_degree']:>4}  {entry} "
            f"{r['score']:>6}  {r['folder']}{star}{fold}{absorbs}"
        )
    s = plan["summary"]
    total = len(plan["folders"])
    lines.append("")
    lines.append(
        f"DEEP {s['deep']}  ·  SKELETON {s['skeleton']}  ·  FOLD {s['fold']}   "
        f"({total} folders)   * = borderline ({len(s['borderline'])}, agent may adjust)"
    )
    lines.append(
        f"{s['maps']} map file(s); {s['merged']} folder(s) merge into an ancestor "
        f"(nothing dropped — their nodes move into that map)."
    )
    lines.append(f"Enrich {len(s['enrich'])}: {', '.join(s['enrich']) if s['enrich'] else '(none)'}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fold: merge a too-thin folder's nodes into the nearest map-keeping ancestor
# ---------------------------------------------------------------------------


def _map_file(root: Path, folder: str) -> Path:
    """Path to a folder's `map-*.ngf.md` (matches scan.py's emit naming)."""
    if folder == ".":
        return root / "map-root.ngf.md"
    return root / folder / f"map-{folder.split('/')[-1]}.ngf.md"


def _ctx_node_lines(text: str) -> List[str]:
    """The node/edge lines inside a map's ```ctx block (excludes fences, comments, group headers)."""
    out: List[str] = []
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if not in_block:
            if stripped.startswith("```") and "ctx" in stripped:
                in_block = True
            continue
        if stripped.startswith("```"):
            break
        if not stripped or stripped.startswith("#"):  # blank / comment / ## group header
            continue
        out.append(line)
    return out


def _insert_before_ctx_close(parent_text: str, block_lines: List[str]) -> str:
    """Insert `block_lines` just before the closing ``` of the parent map's ctx block."""
    lines = parent_text.splitlines()
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip().startswith("```"):
            merged = lines[:i] + block_lines + lines[i:]
            return "\n".join(merged) + ("\n" if parent_text.endswith("\n") else "")
    return parent_text


def _prune_index(root: Path, folded: set) -> None:
    """Drop the index rows for folders whose map was folded away (their content lives in a parent)."""
    index = root / "index.ngf.md"
    if not index.is_file() or not folded:
        return
    kept = []
    for line in index.read_text().splitlines():
        match = re.match(r"^\s+(\S+)\s*:", line)
        if match and match.group(1) in folded:
            continue
        kept.append(line)
    index.write_text("\n".join(kept) + "\n")


def _digest_file(root: Path, folder: str) -> Path:
    """Path to a folder's structural digest (matches scan.py's `write_digests` naming)."""
    base = "root" if folder == "." else folder
    return root / ".context-os" / "digests" / base / "digest.txt"


def _merge_digest(root: Path, folder: str, parent: str) -> None:
    """Move a merged folder's structural digest into its parent's.

    Without this the parent's enricher would be handed nodes for files it was given no digest
    for, and would have to open them one by one — or, worse, describe them from the path alone.
    Best-effort: digests are optional (`scan.py --emit-digests`), so a missing one is not an error.
    """
    src, dest = _digest_file(root, folder), _digest_file(root, parent)
    if not src.is_file():
        return
    header = f"# --- merged from {folder}/ ---\n"
    text = src.read_text()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        dest.write_text(dest.read_text().rstrip("\n") + "\n\n" + header + text)
    else:
        dest.write_text(header + text)
    src.unlink()
    try:
        src.parent.rmdir()  # only if now empty — a parent digest dir must survive
    except OSError:
        pass


def apply_fold(
    root: Path,
    deep_min_files: int = DEFAULT_DEEP_MIN_FILES,
    hub_in: int = DEFAULT_HUB_IN,
    merge_max_files: int = DEFAULT_MERGE_MAX_FILES,
    merge_hub_in: int = DEFAULT_MERGE_HUB_IN,
) -> dict:
    """Merge every too-thin folder's nodes into its map-keeping ancestor, then remove its own
    map, its index row, and fold its digest into the parent's.

    Run this BEFORE enrichment. The nodes it moves are code as well as content now, and a code
    node arrives carrying only its path — so the parent's enricher has to see it in order to
    describe it. (Content nodes were always safe to move late; compress.py had already described
    them. Code nodes are not, which is what forced the order change.)
    """
    plan = compute_plan(
        root,
        deep_min_files=deep_min_files,
        hub_in=hub_in,
        merge_max_files=merge_max_files,
        merge_hub_in=merge_hub_in,
    )
    folded: List[dict] = []
    # Deepest first, so a folder's own map is read before any ancestor rewrite can touch it.
    for row in sorted(plan["folders"], key=lambda r: -_depth(r["folder"])):
        if row["keeps_map"] or not row["fold_into"]:
            continue
        fold_map = _map_file(root, row["folder"])
        parent_map = _map_file(root, row["fold_into"])
        if not fold_map.is_file() or not parent_map.is_file():
            continue
        node_lines = _ctx_node_lines(fold_map.read_text())
        if node_lines:
            block = [f"## Folded: {row['folder']}/"] + node_lines
            parent_map.write_text(_insert_before_ctx_close(parent_map.read_text(), block))
        fold_map.unlink()
        _merge_digest(root, row["folder"], row["fold_into"])
        folded.append({"folder": row["folder"], "into": row["fold_into"], "nodes": len(node_lines)})
    _prune_index(root, {f["folder"] for f in folded})
    return {"folded": folded, "count": len(folded)}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rank folders DEEP/SKELETON/FOLD for selective mapping.")
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", action="store_true", help="emit the full plan as JSON")
    parser.add_argument(
        "--deep-only",
        action="store_true",
        help="print the enrich list: folders that keep a map and carry code (own or absorbed)",
    )
    parser.add_argument("--apply-fold", action="store_true", help="merge thin folders into their ancestor map (mutates)")
    parser.add_argument("--deep-min-files", type=int, default=DEFAULT_DEEP_MIN_FILES)
    parser.add_argument("--hub-in", type=int, default=DEFAULT_HUB_IN)
    parser.add_argument("--merge-max-files", type=int, default=DEFAULT_MERGE_MAX_FILES)
    parser.add_argument("--merge-hub-in", type=int, default=DEFAULT_MERGE_HUB_IN)
    args = parser.parse_args(argv)

    knobs = {
        "deep_min_files": args.deep_min_files,
        "hub_in": args.hub_in,
        "merge_max_files": args.merge_max_files,
        "merge_hub_in": args.merge_hub_in,
    }

    if args.apply_fold:
        result = apply_fold(args.root, **knobs)
        for entry in result["folded"]:
            print(f"merged {entry['folder']} → {entry['into']} ({entry['nodes']} node(s))")
        print(f"{result['count']} folder(s) merged into an ancestor map")
        return 0

    plan = compute_plan(args.root, **knobs)
    if args.deep_only:
        for folder in plan["summary"]["enrich"]:
            print(folder)
        return 0
    print(json.dumps(plan, indent=2) if args.json else format_table(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
