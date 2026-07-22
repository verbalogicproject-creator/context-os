#!/usr/bin/env python3
"""The two load-bearing audits: derive-don't-fabricate, and augment-don't-clobber.

Also reuses the `.ctx` parser (adapted from the vendored ``ctx-to-kg.py`` reference's
``parse_ctx_file``) so `ctx-updater` can diff an existing ``architecture.ctx`` against
a fresh ``scan.py`` run without hand-parsing text itself, and computes the quantified
token-save number `ctx-scout` reports at the end of a run.

Usage:
    python3 scripts/audit.py fabrication <root> <architecture.ctx>
    python3 scripts/audit.py splice-safety <before.md> <after.md> [--markers claudemd|changelog]
    python3 scripts/audit.py tokens <root> <architecture.ctx>
    python3 scripts/audit.py parse <architecture.ctx>
    python3 scripts/audit.py all <root> <architecture.ctx> [--before X --after Y]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import claudemd_splice
import scan as scan_module

# ---------------------------------------------------------------------------
# `.ctx` parser (adapted from ctx-to-kg.py's parse_ctx_file)
# ---------------------------------------------------------------------------

_GROUP_RE = re.compile(r"^(#{2,3})\s+(.+)$")
# name : description [type] @marker* -> targets   (compact edge is optional; [type] is required)
_NODE_RE = re.compile(
    r"^(?P<indent>[ \t]+)(?P<name>\S+)\s*:\s*(?P<desc>.+?)\s*\[(?P<type>[\w-]+)\]"
    r"(?P<markers>(?:\s+(?:@\w+|~\d+L))*)"
    r"(?:\s+(?P<edge_op>->|~>|=>)\s+(?P<edge_targets>.+))?"
    r"\s*$"
)
_COLLAPSE_RE = re.compile(
    r"^(?P<indent>[ \t]+)\.\.\.\s+\((?P<count>\d+)\)\s*:\s*(?P<names>.+?)(?:\s+\[(?P<type>[\w-]+)\])?\s*$"
)
_EDGE_LINE_RE = re.compile(r"^[ \t]+(->|~>|=>)\s+(.+)$")


@dataclass(frozen=True)
class CtxNode:
    """One parsed node from an `architecture.ctx` file."""

    name: str
    description: str
    type: str
    group: str


@dataclass(frozen=True)
class CtxEdge:
    """One parsed edge from an `architecture.ctx` file."""

    source: str
    target: str
    op: str


def extract_ctx_block(text: str) -> str:
    """Return the ctx-grammar body from a file's text.

    A context-os map is a `.ngf.md` file: YAML frontmatter + one fenced ```ctx block.
    This returns the block's inner lines. A bare `.ctx` file (no fence) is returned
    unchanged, so this parser reads both the new `.ngf.md` maps and legacy `.ctx` files.
    """
    out: List[str] = []
    in_block = False
    fenced = False
    for line in text.splitlines():
        stripped = line.strip()
        if not in_block and stripped.startswith("```") and "ctx" in stripped[3:]:
            in_block = True
            fenced = True
            continue
        if in_block and stripped.startswith("```"):
            break
        if in_block:
            out.append(line)
    return "\n".join(out) if fenced else text


def parse_ctx_file(path: Path) -> Tuple[List[CtxNode], List[CtxEdge], List[str]]:
    """Parse a `.ctx` file or `.ngf.md` map into (nodes, edges, warnings).

    Node lines require a `[type]` tag (per CTX-FORMAT-SPEC section 5.1); this also lets
    the parser correctly separate a node's description from an optional trailing
    "compact edge" (section 6.4), which the original reference parser mishandled.
    Collapse lines (`... (N) : a, b [type]`) expand into one CtxNode per name.
    """
    nodes: List[CtxNode] = []
    edges: List[CtxEdge] = []
    warnings: List[str] = []
    current_group = ""
    current_node: Optional[str] = None

    for lineno, raw in enumerate(extract_ctx_block(path.read_text()).splitlines(), start=1):
        line = raw.rstrip()
        if not line:
            continue

        group_match = _GROUP_RE.match(line)
        if group_match:
            current_group = group_match.group(2).split(" -> ")[0].strip()
            current_node = None
            continue

        if line.startswith("#"):
            continue  # header field / full-line comment (changelog block, etc.) — single '#', not a group

        node_match = _NODE_RE.match(line)
        if node_match:
            name = node_match.group("name")
            nodes.append(
                CtxNode(
                    name=name,
                    description=node_match.group("desc").strip(),
                    type=node_match.group("type"),
                    group=current_group,
                )
            )
            current_node = name
            edge_op = node_match.group("edge_op")
            if edge_op:
                for target in _split_targets(node_match.group("edge_targets")):
                    edges.append(CtxEdge(source=name, target=target, op=edge_op))
            continue

        collapse_match = _COLLAPSE_RE.match(line)
        if collapse_match:
            count = int(collapse_match.group("count"))
            names = [n.strip() for n in collapse_match.group("names").split(",") if n.strip()]
            ntype = collapse_match.group("type") or "component"
            if len(names) != count:
                warnings.append(
                    f"line {lineno}: collapse count ({count}) does not match {len(names)} listed name(s)"
                )
            for name in names:
                nodes.append(CtxNode(name=name, description="(collapsed)", type=ntype, group=current_group))
            current_node = None
            continue

        edge_match = _EDGE_LINE_RE.match(line)
        if edge_match and current_node:
            op, targets_str = edge_match.group(1), edge_match.group(2)
            for target in _split_targets(targets_str):
                edges.append(CtxEdge(source=current_node, target=target, op=op))
            continue

        warnings.append(f"line {lineno}: unrecognized syntax: {line.strip()!r}")

    return nodes, edges, warnings


def _split_targets(targets_str: str) -> List[str]:
    """Split a comma-separated edge target list, stripping any `"label"` suffix."""
    targets = []
    for raw in re.split(r",\s*", targets_str.strip()):
        target = re.sub(r'\s*"[^"]*"\s*$', "", raw).strip()
        if target:
            targets.append(target)
    return targets


# ---------------------------------------------------------------------------
# Boundary 1 — derive-don't-fabricate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FabricationFinding:
    """A node in architecture.ctx with no backing file in the fresh scan skeleton."""

    node_name: str
    node_type: str
    reason: str


@dataclass
class FabricationAuditResult:
    """Result of the derive-don't-fabricate audit."""

    ok: bool
    total_nodes: int
    exempt_external: int
    findings: List[FabricationFinding] = field(default_factory=list)
    format_error: Optional[str] = None


def check_derive_dont_fabricate(root: Path, ctx_path: Path) -> FabricationAuditResult:
    """Every non-`[ext]` node in `ctx_path` must exist in a fresh scan of `root`.

    `[ext]` nodes are exempt — they declare external systems, not project files
    (CTX-FORMAT-SPEC section 6.5 / 8.4). `[dir]` nodes are accepted if the name
    resolves to a real directory under `root` (a collapsed subtree).
    """
    nodes, _edges, _warnings = parse_ctx_file(ctx_path)
    scan_result = scan_module.scan(root)
    ground_truth_names = scan_result.node_names()

    findings: List[FabricationFinding] = []
    exempt = 0
    for node in nodes:
        if node.type == "ext":
            exempt += 1
            continue
        if node.name in ground_truth_names:
            continue
        if node.type == "dir" and (root / node.name).is_dir():
            continue
        findings.append(
            FabricationFinding(
                node_name=node.name,
                node_type=node.type,
                reason="no matching file in the fresh scan skeleton",
            )
        )

    # A non-empty .ctx that parses to zero nodes is a format mismatch, not a pass:
    # the anti-fabrication guard would otherwise print "PASS ... 0 node(s) checked"
    # and let a wrong-format map ship unvalidated (silent no-op).
    content_lines = sum(
        1
        for ln in ctx_path.read_text().splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    )
    format_error: Optional[str] = None
    if not nodes and content_lines:
        format_error = (
            f"0 nodes parsed from {ctx_path.name}, but it has {content_lines} non-comment "
            f"line(s) — the file does not match ctx/1.0. Each node line must be indented under "
            f"a `## group` and end with a `[type]` tag (see docs/01-the-ctx-format.md)."
        )

    return FabricationAuditResult(
        ok=(not findings and format_error is None),
        total_nodes=len(nodes),
        exempt_external=exempt,
        findings=findings,
        format_error=format_error,
    )


# ---------------------------------------------------------------------------
# Boundary 2 — augment-don't-clobber (byte-identity outside the managed block)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SpliceSafetyResult:
    """Result of the byte-identity-outside-the-block audit."""

    ok: bool
    reason: Optional[str]


def check_splice_byte_identity(
    before_path: Path, after_path: Path, *, markers: str = "claudemd"
) -> SpliceSafetyResult:
    """Strip the managed block from `before_path` and `after_path`; the remainder must match.

    This is the mechanical proof that a splice only ever touched bytes inside its own
    marker span — every other byte of the file is untouched.
    """
    start, end = (
        (claudemd_splice.CLAUDE_START, claudemd_splice.CLAUDE_END)
        if markers == "claudemd"
        else (claudemd_splice.CHANGELOG_START, claudemd_splice.CHANGELOG_END)
    )
    before_text = before_path.read_text() if before_path.exists() else ""
    after_text = after_path.read_text() if after_path.exists() else ""
    try:
        before_stripped = claudemd_splice.strip_block(before_text, start, end)
        after_stripped = claudemd_splice.strip_block(after_text, start, end)
    except claudemd_splice.MalformedMarkersError as exc:
        return SpliceSafetyResult(ok=False, reason=str(exc))

    if before_stripped != after_stripped:
        return SpliceSafetyResult(ok=False, reason="remainder outside the managed block changed")
    return SpliceSafetyResult(ok=True, reason=None)


# ---------------------------------------------------------------------------
# Quantified token-save report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenReport:
    """The quantified token-save number ctx-scout reports at the end of a run."""

    files_scanned: int
    source_chars: int
    source_tokens_est: int
    ctx_chars: int
    ctx_tokens_est: int
    reduction_pct: float


def _estimate_tokens(num_chars: int) -> int:
    """Rough token estimate (~4 chars/token) — the standard order-of-magnitude heuristic."""
    return max(1, round(num_chars / 4))


def compute_token_report(root: Path, ctx_path: Path) -> TokenReport:
    """Compare total scanned source size against the shipped `architecture.ctx` size."""
    scan_result = scan_module.scan(root)
    source_chars = 0
    for node in scan_result.nodes:
        try:
            source_chars += len((root / node.path).read_text(errors="ignore"))
        except OSError:
            continue
    ctx_chars = len(ctx_path.read_text()) if ctx_path.exists() else 0

    source_tokens = _estimate_tokens(source_chars)
    ctx_tokens = _estimate_tokens(ctx_chars)
    reduction = 0.0 if source_tokens == 0 else round((1 - ctx_tokens / source_tokens) * 100, 1)

    return TokenReport(
        files_scanned=len(scan_result.nodes),
        source_chars=source_chars,
        source_tokens_est=source_tokens,
        ctx_chars=ctx_chars,
        ctx_tokens_est=ctx_tokens,
        reduction_pct=reduction,
    )


# ---------------------------------------------------------------------------
# Whole-map (per-folder .ngf.md set) audits — the context-os layer
# ---------------------------------------------------------------------------


def find_map_files(root: Path) -> List[Path]:
    """All context-os map files in `root`: every `**/map-*.ngf.md` plus `index.ngf.md`."""
    maps = sorted(root.glob("**/map-*.ngf.md"))
    index = root / "index.ngf.md"
    if index.exists():
        maps.append(index)
    return maps


def check_maps_fabrication(root: Path) -> FabricationAuditResult:
    """Derive-don't-fabricate across the whole map set: every node traces to real code.

    One fresh scan is the ground truth for every map. Leaf-map nodes carry the
    scanner's repo-unique names (so they match directly); index `[dir]` nodes must
    name a real directory; `[ext]` nodes are exempt. Anything else is a fabrication.
    """
    scan_result = scan_module.scan(root)
    ground_truth_names = scan_result.node_names()
    findings: List[FabricationFinding] = []
    exempt = 0
    total = 0
    for map_path in find_map_files(root):
        nodes, _edges, _warnings = parse_ctx_file(map_path)
        for node in nodes:
            total += 1
            if node.type == "ext":
                exempt += 1
                continue
            if node.name in ground_truth_names:
                continue
            if node.type == "dir" and (root / node.name).is_dir():
                continue
            findings.append(
                FabricationFinding(
                    node_name=node.name,
                    node_type=node.type,
                    reason=f"in {map_path.name}: no matching file in the fresh scan",
                )
            )
    return FabricationAuditResult(
        ok=not findings,
        total_nodes=total,
        exempt_external=exempt,
        findings=findings,
        format_error=None,
    )


def compute_maps_token_report(root: Path) -> TokenReport:
    """Compare total scanned source size against the whole context-os map set size."""
    scan_result = scan_module.scan(root)
    source_chars = 0
    for node in scan_result.nodes:
        try:
            source_chars += len((root / node.path).read_text(errors="ignore"))
        except OSError:
            continue
    map_chars = 0
    for map_path in find_map_files(root):
        try:
            map_chars += len(map_path.read_text(errors="ignore"))
        except OSError:
            continue

    source_tokens = _estimate_tokens(source_chars)
    map_tokens = _estimate_tokens(map_chars)
    reduction = 0.0 if source_tokens == 0 else round((1 - map_tokens / source_tokens) * 100, 1)
    return TokenReport(
        files_scanned=len(scan_result.nodes),
        source_chars=source_chars,
        source_tokens_est=source_tokens,
        ctx_chars=map_chars,
        ctx_tokens_est=map_tokens,
        reduction_pct=reduction,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for the fabrication, splice-safety, tokens, parse, and all audits."""
    parser = argparse.ArgumentParser(description="ctx-architecture audits: used by CI and by ctx-updater.")
    sub = parser.add_subparsers(dest="mode", required=True)

    fab = sub.add_parser("fabrication", help="Derive-don't-fabricate: every node maps to a real file")
    fab.add_argument("root", type=Path)
    fab.add_argument("ctx", type=Path)

    safety = sub.add_parser("splice-safety", help="Augment-don't-clobber: byte-identity outside the block")
    safety.add_argument("before", type=Path)
    safety.add_argument("after", type=Path)
    safety.add_argument("--markers", choices=["claudemd", "changelog"], default="claudemd")

    tokens = sub.add_parser("tokens", help="Print the quantified token-save number")
    tokens.add_argument("root", type=Path)
    tokens.add_argument("ctx", type=Path)

    parse_p = sub.add_parser("parse", help="Parse a .ctx/.ngf.md file and print its nodes/edges as JSON")
    parse_p.add_argument("ctx", type=Path)

    check_p = sub.add_parser("check", help="Derive-don't-fabricate across every map-*.ngf.md + index.ngf.md")
    check_p.add_argument("root", type=Path)

    savings_p = sub.add_parser("savings", help="Print the token-save number for the whole map set")
    savings_p.add_argument("root", type=Path)

    allp = sub.add_parser("all", help="Run fabrication + tokens, and splice-safety if --before/--after given")
    allp.add_argument("root", type=Path)
    allp.add_argument("ctx", type=Path)
    allp.add_argument("--before", type=Path, default=None)
    allp.add_argument("--after", type=Path, default=None)
    allp.add_argument("--markers", choices=["claudemd", "changelog"], default="claudemd")

    args = parser.parse_args(argv)

    if args.mode == "fabrication":
        result = check_derive_dont_fabricate(args.root, args.ctx)
        _print_fabrication(result)
        return 0 if result.ok else 1

    if args.mode == "splice-safety":
        result = check_splice_byte_identity(args.before, args.after, markers=args.markers)
        print("PASS: byte-identical outside the managed block" if result.ok else f"FAIL: {result.reason}")
        return 0 if result.ok else 1

    if args.mode == "tokens":
        report = compute_token_report(args.root, args.ctx)
        _print_tokens(report, args.root, args.ctx)
        return 0

    if args.mode == "parse":
        nodes, edges, warnings = parse_ctx_file(args.ctx)
        print(
            json.dumps(
                {
                    "nodes": [asdict(n) for n in nodes],
                    "edges": [asdict(e) for e in edges],
                    "warnings": warnings,
                },
                indent=2,
            )
        )
        return 0

    if args.mode == "check":
        result = check_maps_fabrication(args.root)
        _print_fabrication(result)
        return 0 if result.ok else 1

    if args.mode == "savings":
        report = compute_maps_token_report(args.root)
        _print_maps_tokens(report, args.root)
        return 0

    # all
    fab_result = check_derive_dont_fabricate(args.root, args.ctx)
    _print_fabrication(fab_result)
    ok = fab_result.ok

    if args.before and args.after:
        safety_result = check_splice_byte_identity(args.before, args.after, markers=args.markers)
        print("PASS: byte-identical outside the managed block" if safety_result.ok else f"FAIL: {safety_result.reason}")
        ok = ok and safety_result.ok

    report = compute_token_report(args.root, args.ctx)
    _print_tokens(report, args.root, args.ctx)

    return 0 if ok else 1


def _print_fabrication(result: FabricationAuditResult) -> None:
    if result.format_error:
        print(f"ERROR: derive-don't-fabricate — {result.format_error}", file=sys.stderr)
        return
    if result.ok:
        print(
            f"PASS: derive-don't-fabricate — {result.total_nodes} node(s) checked "
            f"({result.exempt_external} external-exempt), 0 unbacked"
        )
        return
    print(f"FAIL: derive-don't-fabricate — {len(result.findings)} unbacked node(s):", file=sys.stderr)
    for finding in result.findings:
        print(f"  - {finding.node_name} [{finding.node_type}]: {finding.reason}", file=sys.stderr)


def _print_tokens(report: TokenReport, root: Path, ctx_path: Path) -> None:
    print(
        f"{report.files_scanned} source files (~{report.source_tokens_est} tokens to scan) under {root} -> "
        f"{ctx_path.name} is ~{report.ctx_tokens_est} tokens "
        f"({report.reduction_pct}% smaller; Claude now loads {report.ctx_tokens_est} on demand "
        f"instead of re-scanning {report.source_tokens_est})."
    )


def _print_maps_tokens(report: TokenReport, root: Path) -> None:
    print(
        f"{report.files_scanned} source files (~{report.source_tokens_est} tokens to scan) under {root} -> "
        f"the context-os map set is ~{report.ctx_tokens_est} tokens "
        f"({report.reduction_pct}% smaller; a fresh session loads {report.ctx_tokens_est} on demand "
        f"instead of re-scanning {report.source_tokens_est})."
    )


if __name__ == "__main__":
    raise SystemExit(main())
