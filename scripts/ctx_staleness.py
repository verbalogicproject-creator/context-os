#!/usr/bin/env python3
"""Structural-hash drift detection for context-os maps. Stdlib only, offline.

A map (`map-{folder}.ngf.md`) documents the source files in one folder. Its
frontmatter carries two fields:

  structural_hash : the folder's *last-known-good* signature (written by generate /
                    update — the baseline). Only `stamp` touches this.
  staleness       : the *live* verdict (`verified` / `DRIFTED …` / `unstamped`).
                    Only `flip` touches this — it is what the drift hook rewrites.

The signature hashes only a folder's **architecture-bearing lines** — imports
(edges) and top-level declarations (nodes) — sorted and non-recursive, so a
reformat, a comment change, or a `git clone` (which rewrites mtimes) does NOT
count as drift, while an added/removed file, import, or declaration does. This is
the deliberate improvement over an mtime comparison: staleness is *semantic*
(did the architecture move?), not *temporal* (was a byte touched?).

The verdict lives *inside the map file*, so a fresh session — Claude, Codex, or
Gemini, hook or no hook — sees `staleness: DRIFTED` just by reading the map. The
hook only keeps that in-file flag true.

Usage:
    python3 ctx_staleness.py signature <folder>       # debug: print a folder's signature
    python3 ctx_staleness.py stamp <map.ngf.md>       # write baseline hash + staleness: verified
    python3 ctx_staleness.py stamp-all <root>         # stamp every map-*.ngf.md under root
    python3 ctx_staleness.py flip <map.ngf.md>        # recompute vs baseline, set the staleness flag
    python3 ctx_staleness.py check <root> <path>      # resolve the map owning <path>, then flip it
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path
from typing import List, Optional

SRC_EXT = frozenset(
    {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java",
        ".kt", ".swift", ".rb", ".php", ".vue", ".svelte", ".c", ".h", ".cpp", ".cs",
    }
)

# Architecture-bearing lines: dependencies (edges) + top-level declarations (nodes).
_STRUCT_RE = re.compile(
    r"^\s*(import\s|from\s.+import|require\(|use\s|#include|"
    r"export\s|def\s|class\s|func\s|function\s|interface\s|type\s|"
    r"@app\.|@router\.|@\w+\.(get|post|put|delete|patch))"
)


# ---------------------------------------------------------------------------
# Signature
# ---------------------------------------------------------------------------


def signature(folder: Path) -> str:
    """A cheap, order-insensitive, non-recursive signature of a folder's architecture.

    Bounded by one folder's source files (not the repo) — typically <50ms.
    """
    parts: List[str] = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return "sha256:" + hashlib.sha256(b"").hexdigest()[:16]
    for name in names:
        path = folder / name
        if not path.is_file() or path.suffix not in SRC_EXT:
            continue
        hits: List[str] = []
        try:
            with open(path, encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    if _STRUCT_RE.match(line):
                        hits.append(re.sub(r"\s+", " ", line.strip()))
        except OSError:
            continue
        parts.append(name + "\n" + "\n".join(sorted(hits)))
    blob = "\n--\n".join(parts)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Frontmatter read/write (line-based; no YAML dependency)
# ---------------------------------------------------------------------------


def _frontmatter_close(lines: List[str]) -> Optional[int]:
    """Index of the closing `---` of a leading YAML frontmatter block, or None."""
    if not lines or lines[0].strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return i
    return None


def fm_get(text: str, key: str) -> Optional[str]:
    """Read a scalar frontmatter value, or None if the file has no frontmatter/key."""
    lines = text.splitlines()
    close = _frontmatter_close(lines)
    if close is None:
        return None
    pattern = re.compile(rf"^{re.escape(key)}\s*:\s*(.*)$")
    for i in range(1, close):
        match = pattern.match(lines[i])
        if match:
            return match.group(1).strip()
    return None


def fm_set(text: str, key: str, value: str) -> str:
    """Return `text` with frontmatter `key` set to `value` (replaced, or inserted before `---`).

    Refuses (returns text unchanged) if there is no frontmatter — never guesses a
    place to put it. Values are kept colon-free by callers so no quoting is needed.
    """
    lines = text.splitlines()
    close = _frontmatter_close(lines)
    if close is None:
        return text
    trailing_nl = "\n" if text.endswith("\n") else ""
    new_line = f"{key}: {value}"
    pattern = re.compile(rf"^{re.escape(key)}\s*:")
    for i in range(1, close):
        if pattern.match(lines[i]):
            lines[i] = new_line
            return "\n".join(lines) + trailing_nl
    lines.insert(close, new_line)
    return "\n".join(lines) + trailing_nl


# ---------------------------------------------------------------------------
# Map resolution
# ---------------------------------------------------------------------------


def _is_map_file(path: Path) -> bool:
    return path.name.startswith("map-") and path.name.endswith(".ngf.md")


def _map_name_for_dir(root: Path, folder: Path) -> str:
    """The map filename that documents `folder` (matches scan.py's emit naming)."""
    rel = folder.resolve().relative_to(root.resolve()).as_posix()
    base = "root" if rel == "." else Path(rel).name
    return f"map-{base}.ngf.md"


def owning_map(root: Path, path: Path) -> Optional[Path]:
    """The map that documents `path` — itself if it's a map, else the nearest ancestor folder's map."""
    root = root.resolve()
    path = path.resolve()
    if _is_map_file(path):
        return path
    folder = path if path.is_dir() else path.parent
    while True:
        try:
            folder.relative_to(root)
        except ValueError:
            return None
        candidate = folder / _map_name_for_dir(root, folder)
        if candidate.is_file():
            return candidate
        if folder == root:
            return None
        folder = folder.parent


# ---------------------------------------------------------------------------
# stamp / flip
# ---------------------------------------------------------------------------


def stamp(map_path: Path) -> None:
    """Write the folder's current signature as the baseline + `staleness: verified`."""
    text = map_path.read_text()
    text = fm_set(text, "structural_hash", signature(map_path.parent))
    text = fm_set(text, "staleness", "verified")
    map_path.write_text(text)


def flip(map_path: Path) -> str:
    """Recompute the folder signature vs the stored baseline and set the staleness flag.

    Returns the new status string. Writes only if the flag actually changed.
    """
    text = map_path.read_text()
    baseline = fm_get(text, "structural_hash")
    now = signature(map_path.parent)
    if baseline is None:
        status = "unstamped — run /context-os-update"
    elif now == baseline:
        status = "verified"
    else:
        status = "DRIFTED — folder changed since last verify; trust loosely, run /context-os-update"
    updated = fm_set(text, "staleness", status)
    if updated != text:
        map_path.write_text(updated)
    return status


def stamp_all(root: Path) -> int:
    """Stamp every `map-*.ngf.md` under `root`. Returns the count stamped."""
    count = 0
    for map_path in sorted(root.glob("**/map-*.ngf.md")):
        stamp(map_path)
        count += 1
    return count


def status_all(root: Path) -> List[tuple]:
    """Re-flip every `map-*.ngf.md` under `root` and return [(path, status), ...].

    Flipping first makes the report reflect current source truth even for out-of-band
    changes no hook saw. A row whose status is not exactly `verified` is drifted.
    """
    rows = []
    for map_path in sorted(root.glob("**/map-*.ngf.md")):
        rows.append((map_path, flip(map_path)))
    return rows


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(__doc__)
        return 2
    mode = args[0]

    if mode == "signature" and len(args) == 2:
        print(signature(Path(args[1])))
        return 0

    if mode == "stamp" and len(args) == 2:
        stamp(Path(args[1]))
        print(f"stamped {args[1]}")
        return 0

    if mode == "stamp-all" and len(args) == 2:
        n = stamp_all(Path(args[1]))
        print(f"stamped {n} map(s)")
        return 0

    if mode == "flip" and len(args) == 2:
        status = flip(Path(args[1]))
        print(f"{args[1]}: {status}")
        return 0

    if mode == "status" and len(args) == 2:
        root = Path(args[1])
        rows = status_all(root)
        drifted = 0
        for map_path, status in rows:
            rel = map_path.relative_to(root) if map_path.is_relative_to(root) else map_path
            flag = "ok " if status == "verified" else "!! "
            if status != "verified":
                drifted += 1
            print(f"{flag}{rel}: {status}")
        print(f"\n{len(rows)} map(s), {drifted} drifted")
        return 1 if drifted else 0

    if mode == "check" and len(args) == 3:
        root, path = Path(args[1]), Path(args[2])
        ext_ok = _is_map_file(path) or path.suffix in SRC_EXT
        if not ext_ok:
            return 0
        target = owning_map(root, path)
        if target is not None:
            status = flip(target)
            print(f"{target}: {status}")
        return 0

    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
