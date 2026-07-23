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


def _folder_of(node) -> str:
    """The node's folder as a plan key: repo-relative dir, or '.' for the repo root."""
    return node.dir or "."


def _nearest_mapped_ancestor(folder: str, tier_by_dir: Dict[str, str]) -> Optional[str]:
    """Nearest ancestor folder that is DEEP or SKELETON — where a FOLD folder's node folds into."""
    if folder == ".":
        return None
    parts = folder.split("/")
    for i in range(len(parts) - 1, 0, -1):
        ancestor = "/".join(parts[:i])
        if tier_by_dir.get(ancestor) in ("DEEP", "SKELETON"):
            return ancestor
    return "." if tier_by_dir.get(".") in ("DEEP", "SKELETON") else None


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
    root: Path, deep_min_files: int = DEFAULT_DEEP_MIN_FILES, hub_in: int = DEFAULT_HUB_IN
) -> dict:
    """Rank every folder in `root` into DEEP / SKELETON / FOLD from the scan graph."""
    result = scan_module.scan(root)
    name_to_dir = {n.name: _folder_of(n) for n in result.nodes}

    folders: Dict[str, dict] = {}
    for node in result.nodes:
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

    tier_by_dir = {r["folder"]: r["tier"] for r in rows}
    for row in rows:
        row["fold_into"] = _nearest_mapped_ancestor(row["folder"], tier_by_dir) if row["tier"] == "FOLD" else None
        row["borderline"] = _is_borderline(row, deep_min_files, hub_in)

    rows.sort(key=lambda r: (-r["score"], r["folder"]))
    summary = {
        "deep": sum(1 for r in rows if r["tier"] == "DEEP"),
        "skeleton": sum(1 for r in rows if r["tier"] == "SKELETON"),
        "fold": sum(1 for r in rows if r["tier"] == "FOLD"),
        "borderline": [r["folder"] for r in rows if r["borderline"]],
    }
    return {
        "root": str(root),
        "folders": rows,
        "summary": summary,
        "params": {"deep_min_files": deep_min_files, "hub_in": hub_in},
    }


def format_table(plan: dict) -> str:
    lines = [f"{'TIER':9}{'code':>5}{'in':>4}{'out':>4}  E {'score':>6}  folder"]
    for r in plan["folders"]:
        entry = "Y" if r["has_entry"] else " "
        star = " *" if r["borderline"] else ""
        fold = f"  → fold into {r['fold_into']}" if r["tier"] == "FOLD" and r["fold_into"] else ""
        lines.append(
            f"{r['tier']:9}{r['code_files']:>5}{r['in_degree']:>4}{r['out_degree']:>4}  {entry} "
            f"{r['score']:>6}  {r['folder']}{star}{fold}"
        )
    s = plan["summary"]
    total = len(plan["folders"])
    lines.append("")
    lines.append(
        f"DEEP {s['deep']}  ·  SKELETON {s['skeleton']}  ·  FOLD {s['fold']}   "
        f"({total} folders)   * = borderline ({len(s['borderline'])}, agent may adjust)"
    )
    lines.append(
        f"Enrich only the {s['deep']} DEEP folders; skeleton {s['skeleton']}; "
        f"fold {s['fold']} content folders into their parent."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Fold: merge a content-only (FOLD) folder's deterministic nodes into its parent map
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


def apply_fold(
    root: Path, deep_min_files: int = DEFAULT_DEEP_MIN_FILES, hub_in: int = DEFAULT_HUB_IN
) -> dict:
    """Fold each FOLD folder's deterministic content nodes into its parent map, then remove its
    own map and its index row. Run this AFTER enrichment — the folded content is deterministic
    (compress.py already described it), so it never needs an enricher and never disturbs one.
    """
    plan = compute_plan(root, deep_min_files=deep_min_files, hub_in=hub_in)
    folded: List[dict] = []
    for row in plan["folders"]:
        if row["tier"] != "FOLD" or not row["fold_into"]:
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
        folded.append({"folder": row["folder"], "into": row["fold_into"], "nodes": len(node_lines)})
    _prune_index(root, {f["folder"] for f in folded})
    return {"folded": folded, "count": len(folded)}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rank folders DEEP/SKELETON/FOLD for selective mapping.")
    parser.add_argument("root", type=Path)
    parser.add_argument("--json", action="store_true", help="emit the full plan as JSON")
    parser.add_argument("--deep-only", action="store_true", help="print only the DEEP folder paths (one per line)")
    parser.add_argument("--apply-fold", action="store_true", help="fold content folders into their parent map (mutates)")
    parser.add_argument("--deep-min-files", type=int, default=DEFAULT_DEEP_MIN_FILES)
    parser.add_argument("--hub-in", type=int, default=DEFAULT_HUB_IN)
    args = parser.parse_args(argv)

    if args.apply_fold:
        result = apply_fold(args.root, deep_min_files=args.deep_min_files, hub_in=args.hub_in)
        for entry in result["folded"]:
            print(f"folded {entry['folder']} → {entry['into']} ({entry['nodes']} node(s))")
        print(f"{result['count']} folder(s) folded into their parent")
        return 0

    plan = compute_plan(args.root, deep_min_files=args.deep_min_files, hub_in=args.hub_in)
    if args.deep_only:
        for row in plan["folders"]:
            if row["tier"] == "DEEP":
                print(row["folder"])
        return 0
    print(json.dumps(plan, indent=2) if args.json else format_table(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
