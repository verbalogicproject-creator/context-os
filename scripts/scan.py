#!/usr/bin/env python3
"""Deterministic, whole-repo grounded skeleton scanner for ctx-architecture.

Adapted from the vendored ``generate_basic_ctx.py`` reference (see
``reference/`` — not shipped). The core per-language import parsers,
``resolve_import`` matching, and ``infer_type`` naming heuristics are the
same logic; the output shape is changed from "one .ctx per folder" to
**one grounded skeleton for the whole repository** (real files as nodes,
resolved imports as edges, inferred ``[type]`` tags, no descriptions).

This module implements the **derive-don't-fabricate** boundary's ground
truth: every node this script emits corresponds to a real file that was
found on disk by ``os.walk``, and every edge corresponds to an import
statement this script actually parsed out of that file's real contents.
Nothing here is invented — descriptions are deliberately left out because
writing them requires *reading* the file, which is the `ctx-scout` agent's
enrichment pass, not this deterministic scanner's job.

Usage:
    python3 scripts/scan.py <root> --json skeleton.json --ctx draft.ctx
    python3 scripts/scan.py <root> --stdout
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

FORMAT_VERSION = "ctx-scan/1.0"

# ---------------------------------------------------------------------------
# Exclusions / source extensions (generalized: caller may add more via CLI)
# ---------------------------------------------------------------------------

DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset(
    {
        "node_modules", ".git", ".next", "__pycache__", "dist", "build",
        "venv", ".venv", "target", "vendor", ".cache", ".tox", "egg-info",
        ".mypy_cache", ".pytest_cache", "coverage", ".nyc_output", "out",
        ".turbo", ".vercel", ".svelte-kit",
    }
)

SOURCE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
        ".kt", ".swift", ".rb", ".php", ".vue", ".svelte",
    }
)

# ---------------------------------------------------------------------------
# Per-language import parsers
# ---------------------------------------------------------------------------


def parse_python_imports(content: str) -> List[str]:
    """Extract dotted module targets from Python `import` / `from ... import` statements."""
    imports = []
    for match in re.finditer(r"^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", content, re.MULTILINE):
        module = match.group(1) or match.group(2)
        imports.append(module)
    return imports


def parse_ts_imports(content: str) -> List[str]:
    """Extract module specifiers from TS/JS/JSX/TSX/Vue/Svelte `import`/`require` statements."""
    imports = []
    pattern = r"""(?:import\s+.*?from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))"""
    for match in re.finditer(pattern, content):
        target = match.group(1) or match.group(2)
        imports.append(target)
    return imports


def parse_go_imports(content: str) -> List[str]:
    """Extract import path strings from Go single-line and block import statements."""
    imports = []
    for match in re.finditer(r'import\s+"([^"]+)"', content):
        imports.append(match.group(1))
    block = re.search(r"import\s*\((.*?)\)", content, re.DOTALL)
    if block:
        for match in re.finditer(r'"([^"]+)"', block.group(1)):
            imports.append(match.group(1))
    return imports


def parse_rust_imports(content: str) -> List[str]:
    """Extract `use` targets from Rust source."""
    return [m.group(1) for m in re.finditer(r"use\s+([\w:]+)", content)]


def parse_java_imports(content: str) -> List[str]:
    """Extract import targets from Java/Kotlin source."""
    return [m.group(1) for m in re.finditer(r"import\s+([\w.]+)", content)]


IMPORT_PARSERS: Dict[str, Callable[[str], List[str]]] = {
    ".py": parse_python_imports,
    ".ts": parse_ts_imports,
    ".tsx": parse_ts_imports,
    ".js": parse_ts_imports,
    ".jsx": parse_ts_imports,
    ".vue": parse_ts_imports,
    ".svelte": parse_ts_imports,
    ".go": parse_go_imports,
    ".rs": parse_rust_imports,
    ".java": parse_java_imports,
    ".kt": parse_java_imports,
}

# ---------------------------------------------------------------------------
# Type inference (filename/directory convention -> [type] tag)
# ---------------------------------------------------------------------------

_ROOT_FILENAMES = frozenset(
    {"index.ts", "index.js", "index.tsx", "main.py", "app.py", "main.go", "main.rs"}
)


def infer_type(filename: str, dir_name: str) -> str:
    """Infer a coarse `[type]` tag from filename/directory naming conventions.

    This is a heuristic, not a semantic read — it is only ever used to seed the
    draft skeleton. The `ctx-scout` agent's enrichment pass (grounded in an
    actual read of the file) is what may refine or override it.
    """
    name_lower = filename.lower()
    dir_lower = dir_name.lower()

    if "test" in name_lower or "spec" in name_lower or dir_lower.startswith("test"):
        return "test"
    if "store" in name_lower or "store" in dir_lower:
        return "store"
    if "route" in name_lower or "router" in name_lower or dir_lower in ("routes", "routers"):
        return "router"
    if "service" in name_lower or dir_lower == "services":
        return "service"
    if "config" in name_lower:
        return "config"
    if "type" in name_lower or dir_lower == "types":
        return "type"
    if "util" in name_lower or "helper" in name_lower or dir_lower in ("lib", "utils", "helpers"):
        return "lib"
    if "page" in name_lower or dir_lower in ("pages", "app", "views"):
        return "screen"
    if "model" in name_lower or dir_lower == "models":
        return "data"
    if name_lower in _ROOT_FILENAMES:
        return "root"
    return "component"


# ---------------------------------------------------------------------------
# Filesystem scan + import resolution
# ---------------------------------------------------------------------------


def scan_project(root: Path, exclude_dirs: Set[str]) -> Dict[str, List[str]]:
    """Walk `root`, honoring `exclude_dirs`, and return {posix_rel_dir: [filenames]}."""
    folders: Dict[str, List[str]] = defaultdict(list)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in exclude_dirs)
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        if rel_dir == ".":
            rel_dir = ""
        for name in sorted(filenames):
            if Path(name).suffix in SOURCE_EXTENSIONS:
                folders[rel_dir].append(name)
    return dict(folders)


def _match_by_suffix(
    needle: str, source_dir: str, all_files: Dict[str, Set[str]]
) -> Optional[Tuple[str, str]]:
    """Find a `(dir, stem)` whose `dir/stem` path matches `needle` on a path
    segment boundary. Prefers an exact full-path match, then a match in the
    importing file's own directory, then any other segment-boundary match — so a
    bare `config` import never binds to `.../myconfig`, and when several dirs
    share a stem the same-directory file wins over an arbitrary iteration hit.
    """
    exact: Optional[Tuple[str, str]] = None
    same_dir: Optional[Tuple[str, str]] = None
    other: Optional[Tuple[str, str]] = None
    for dir_path, files in all_files.items():
        for f in files:
            stem = Path(f).stem
            full_stem = f"{dir_path}/{stem}" if dir_path else stem
            if full_stem == needle:
                exact = (dir_path, stem)
            elif full_stem.endswith("/" + needle):
                if dir_path == source_dir:
                    same_dir = same_dir or (dir_path, stem)
                else:
                    other = other or (dir_path, stem)
    return exact or same_dir or other


def resolve_import(
    imp: str, source_dir: str, all_files: Dict[str, Set[str]]
) -> Optional[Tuple[str, str]]:
    """Resolve an import string to a `(dir, stem)` pair naming a real project file.

    Tries, in order: relative imports (`./foo`, `../bar`), absolute-style imports
    (`@/lib/foo`, `src/lib/foo`), and dotted imports (`services.game_runtime`).
    Returns None if nothing in the scanned project matches.
    """
    if imp.startswith("."):
        parts = imp.split("/")
        if len(parts) > 1:
            base = source_dir if source_dir else "."
            resolved_dir = posixpath.normpath(posixpath.join(base, *parts[:-1]))
        else:
            resolved_dir = source_dir
        if resolved_dir == ".":
            resolved_dir = ""
        target_name = parts[-1] if parts[-1] != "." else ""
        for f in all_files.get(resolved_dir, ()):
            stem = Path(f).stem
            if stem == target_name or f == target_name:
                return resolved_dir, stem
        return None

    cleaned = imp.lstrip("@/")
    match = _match_by_suffix(cleaned, source_dir, all_files)
    if match:
        return match

    dotted = imp.replace(".", "/")
    return _match_by_suffix(dotted, source_dir, all_files)


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScanNode:
    """One real source file, grounded by its actual path on disk."""

    name: str
    path: str
    dir: str
    ext: str
    type: str


@dataclass(frozen=True)
class ScanEdge:
    """One resolved import — both endpoints are real `ScanNode.name` values."""

    source: str
    target: str


@dataclass
class ScanResult:
    """The whole-repo grounded skeleton: real files as nodes, resolved imports as edges."""

    root: str
    scanned_at: str
    format: str
    nodes: List[ScanNode] = field(default_factory=list)
    edges: List[ScanEdge] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)

    def node_names(self) -> Set[str]:
        """All node names present in this skeleton (the ground truth for the fabrication audit)."""
        return {n.name for n in self.nodes}

    def node_paths(self) -> Set[str]:
        """All real, repo-relative file paths present in this skeleton."""
        return {n.path for n in self.nodes}

    def to_dict(self) -> dict:
        """JSON-serializable representation."""
        return {
            "root": self.root,
            "scanned_at": self.scanned_at,
            "format": self.format,
            "nodes": [asdict(n) for n in self.nodes],
            "edges": [asdict(e) for e in self.edges],
            "stats": self.stats,
        }

    def to_draft_ctx(self) -> str:
        """Render a draft, undescribed `ctx/1.0` skeleton grouped by top-level directory.

        This is the artifact `ctx-scout` reads and enriches (descriptions, refined
        edge types, `@entry`, groups, `collapse`) into the final `architecture.ctx`.
        """
        by_group: Dict[str, List[ScanNode]] = defaultdict(list)
        for n in self.nodes:
            top = n.dir.split("/")[0] if n.dir else "(root)"
            by_group[top].append(n)

        edges_by_source: Dict[str, List[str]] = defaultdict(list)
        for e in self.edges:
            edges_by_source[e.source].append(e.target)

        title = Path(self.root).name or "project"
        lines = [
            f"# {title}/ — Draft Architecture Skeleton (auto-generated, no descriptions yet)",
            "# format: ctx/1.0",
            f"# last-verified: {self.scanned_at}",
            "# edges: -> call/render",
            f"# nodes: {len(self.nodes)} | edges: {len(self.edges)} | groups: {len(by_group)}",
            "",
        ]
        for group in sorted(by_group):
            lines.append(f"## {group}/")
            for n in sorted(by_group[group], key=lambda x: x.path):
                lines.append(f"  {n.name} : {n.path} [{n.type}]")
                targets = edges_by_source.get(n.name)
                if targets:
                    lines.append(f"    -> {', '.join(sorted(set(targets)))}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def to_per_folder_ngf(self) -> Dict[str, str]:
        """Render per-folder ``map-{folder}.ngf.md`` skeletons + a root ``index.ngf.md``.

        This is the context-os emit layer (the ctx-architecture original emitted one
        whole-repo ``architecture.ctx`` via ``to_draft_ctx``). Each map is a
        ``.ngf.md``: YAML frontmatter card stub + one fenced ```ctx block listing the
        folder's own files as nodes with intra-folder call edges. Node names are the
        scanner's repo-unique names (a bare stem, or ``dir/stem`` only where two files
        share a stem repo-wide) so the derive-don't-fabricate audit validates them
        unchanged. Descriptions, governance (safe/risk), cross-boundary edges, and
        ``structural_hash``/``staleness`` are left for the enrichment pass (map-scout)
        and the stamp step (``ctx_staleness.py``) — this deterministic scanner only
        emits what it can ground in real files.

        Returns ``{repo_relative_path: file_content}``.
        """
        by_dir: Dict[str, List[ScanNode]] = defaultdict(list)
        for n in self.nodes:
            by_dir[n.dir].append(n)

        node_dir: Dict[str, str] = {n.name: n.dir for n in self.nodes}
        edges_by_source: Dict[str, List[str]] = defaultdict(list)
        for e in self.edges:
            edges_by_source[e.source].append(e.target)

        def slug(d: str) -> str:
            return d.replace("/", "-") if d else "root"

        def base(d: str) -> str:
            return posixpath.basename(d) if d else "root"

        def map_relpath(d: str) -> str:
            fname = f"map-{base(d)}.ngf.md"
            return f"{d}/{fname}" if d else fname

        files: Dict[str, str] = {}

        for d in sorted(by_dir):
            title = f"{d}/" if d else "(repo root)"
            lines = [
                "---",
                f"id: map-{slug(d)}",
                "kind: context_map",
                f'folder: "{d}/"' if d else 'folder: "."',
                "format: ctx/1.1",
                f"last_verified: {self.scanned_at}",
                f"file_count: {len(by_dir[d])}",
                "---",
                "```ctx",
                f"# {title} — architecture (auto-generated skeleton, descriptions pending)",
                "# format: ctx/1.1",
                "# edges: -> call/render | ~> subscribe/read | => HTTP API call",
                "## Files",
            ]
            for n in sorted(by_dir[d], key=lambda x: x.path):
                lines.append(f"  {n.name} : {n.path} [{n.type}]")
                targets = sorted(
                    {
                        t
                        for t in edges_by_source.get(n.name, ())
                        if node_dir.get(t) == d and t != n.name
                    }
                )
                if targets:
                    lines.append(f"    -> {', '.join(targets)}")
            lines.append("```")
            files[map_relpath(d)] = "\n".join(lines) + "\n"

        idx = [
            "---",
            "id: index",
            "kind: context_index",
            'root: "."',
            "format: ctx/1.1",
            f"last_verified: {self.scanned_at}",
            'usage: "Lazy-load — read this, then drill into ONLY the map you need; never scan source."',
            "maintain: \"Each map's staleness flag auto-flips on drift; run /context-os-update on DRIFTED folders.\"",
            "---",
            "```ctx",
            "# index — project context router",
            "# format: ctx/1.1",
            "# edges: -> drill-down",
            "## Folders",
        ]
        for d in sorted(by_dir):
            name = d if d else "."
            idx.append(f"  {name} : {len(by_dir[d])} files [dir] -> {map_relpath(d)}")
        idx.append("```")
        files["index.ngf.md"] = "\n".join(idx) + "\n"

        return files


def write_ngf_skeletons(
    root: Path, result: ScanResult, *, overwrite: bool = False
) -> Tuple[List[str], List[str]]:
    """Write the per-folder map skeletons + index into `root`. Returns (written, skipped).

    Existing maps are skipped unless `overwrite=True`, so a re-init never silently
    destroys an enriched map — refreshing a drifted folder is the updater's job.
    """
    written: List[str] = []
    skipped: List[str] = []
    for rel, content in result.to_per_folder_ngf().items():
        dest = root / rel
        if dest.exists() and not overwrite:
            skipped.append(rel)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        written.append(rel)
    return written, skipped


def scan(root: Path, *, extra_exclude: Optional[Set[str]] = None) -> ScanResult:
    """Scan `root` and return the whole-repo grounded skeleton.

    Node names are the file's stem, unless two or more files across the repo
    share a stem — in that case every colliding file is named `dir/stem` so
    every node name stays unique repo-wide (a whole-repo concern the original
    per-folder tool never had to solve).
    """
    exclude_dirs = set(DEFAULT_EXCLUDE_DIRS) | (extra_exclude or set())
    folders = scan_project(root, exclude_dirs)
    all_files: Dict[str, Set[str]] = {d: set(files) for d, files in folders.items()}

    stem_counts: Counter[str] = Counter()
    file_records: List[Tuple[str, str, str, str]] = []  # (dir, filename, stem, ext)
    for dir_path, files in folders.items():
        for f in files:
            stem = Path(f).stem
            stem_counts[stem] += 1
            file_records.append((dir_path, f, stem, Path(f).suffix))

    def node_name(dir_path: str, stem: str) -> str:
        if stem_counts[stem] > 1:
            return f"{dir_path}/{stem}" if dir_path else stem
        return stem

    nodes: List[ScanNode] = []
    for dir_path, f, stem, ext in file_records:
        rel_path = f"{dir_path}/{f}" if dir_path else f
        name = node_name(dir_path, stem)
        ntype = infer_type(f, posixpath.basename(dir_path) if dir_path else "")
        nodes.append(ScanNode(name=name, path=rel_path, dir=dir_path, ext=ext, type=ntype))
    nodes.sort(key=lambda n: n.path)

    seen_edges: Set[Tuple[str, str]] = set()
    edges: List[ScanEdge] = []
    total_imports = 0
    resolved_count = 0
    for dir_path, f, stem, ext in file_records:
        parser = IMPORT_PARSERS.get(ext)
        if parser is None:
            continue
        full_path = (root / dir_path / f) if dir_path else (root / f)
        try:
            content = full_path.read_text(errors="ignore")
        except OSError:
            continue

        source_name = node_name(dir_path, stem)
        for imp in parser(content):
            total_imports += 1
            resolved = resolve_import(imp, dir_path, all_files)
            if resolved is None:
                continue
            target_dir, target_stem = resolved
            target_name = node_name(target_dir, target_stem)
            if target_name == source_name:
                continue
            key = (source_name, target_name)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            edges.append(ScanEdge(source=source_name, target=target_name))
            resolved_count += 1
    edges.sort(key=lambda e: (e.source, e.target))

    stats = {
        "files_scanned": len(file_records),
        "total_imports": total_imports,
        "resolved_edges": resolved_count,
    }
    return ScanResult(
        root=str(root),
        scanned_at=date.today().isoformat(),
        format=FORMAT_VERSION,
        nodes=nodes,
        edges=edges,
        stats=stats,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point: scan a project root, emit a JSON skeleton and/or a draft `.ctx`."""
    parser = argparse.ArgumentParser(
        description="Deterministic whole-repo grounded skeleton scanner for ctx-architecture."
    )
    parser.add_argument("root", type=Path, help="Project root to scan")
    parser.add_argument("--json", type=Path, default=None, help="Write the scan skeleton as JSON here")
    parser.add_argument("--ctx", type=Path, default=None, help="Write a draft architecture.ctx skeleton here")
    parser.add_argument(
        "--exclude", action="append", default=[], help="Additional directory name to exclude (repeatable)"
    )
    parser.add_argument("--stdout", action="store_true", help="Print the JSON skeleton to stdout")
    parser.add_argument(
        "--emit-ngf",
        action="store_true",
        help="Write per-folder map-*.ngf.md skeletons + index.ngf.md into the project root",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="With --emit-ngf: overwrite existing maps (default: skip them, never clobber enrichment)",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: not a directory: {root}", file=sys.stderr)
        return 1

    result = scan(root, extra_exclude=set(args.exclude))

    if args.json:
        try:
            args.json.write_text(json.dumps(result.to_dict(), indent=2) + "\n")
        except OSError as exc:
            print(
                f"scan.py: cannot write {args.json}: {exc.strerror or exc} — "
                "try a path under your home directory",
                file=sys.stderr,
            )
            return 1
        print(f"wrote scan skeleton ({len(result.nodes)} nodes, {len(result.edges)} edges) -> {args.json}")
    if args.ctx:
        try:
            args.ctx.write_text(result.to_draft_ctx())
        except OSError as exc:
            print(
                f"scan.py: cannot write {args.ctx}: {exc.strerror or exc} — "
                "try a path under your home directory",
                file=sys.stderr,
            )
            return 1
        print(f"wrote draft architecture.ctx skeleton -> {args.ctx}")
    if args.emit_ngf:
        written, skipped = write_ngf_skeletons(root, result, overwrite=args.overwrite)
        print(f"wrote {len(written)} map skeleton(s) + index into {root}")
        if skipped:
            print(f"skipped {len(skipped)} existing map(s) (use --overwrite to replace): {', '.join(skipped[:5])}")

    if args.stdout or not (args.json or args.ctx or args.emit_ngf):
        print(json.dumps(result.to_dict(), indent=2))

    print(
        f"scanned {result.stats['files_scanned']} files, {result.stats['total_imports']} imports "
        f"({result.stats['resolved_edges']} resolved to project edges)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
