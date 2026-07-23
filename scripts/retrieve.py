#!/usr/bin/env python3
"""Retrieve the exact original source behind a context-os map reference — the CCR "retrieve".

A map is the *compressed* view of a folder; each source file is the *retrievable original*.
Given an anchor — a repo-relative ``path`` (whole file) or ``path:symbol`` (one
``def``/``class``/``function`` block) — this returns the exact original text plus its
``sha256``, so a reader consults the cheap map and pulls the exact original only when it
actually needs it (Compress-Cache-Retrieve, in-domain, stdlib-only, offline).

The hash lets a caller cache/verify by content, and ties to drift: a mismatch against a hash
captured when the map was built means that exact block changed.

Usage:
    python3 retrieve.py <root> <anchor>          # print the block; a "# … sha256:…" note on stderr
    python3 retrieve.py <root> <anchor> --json    # {"path","symbol","start_line","end_line","sha256","text",…}
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

_BRACE_EXT = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java", ".kt",
    ".c", ".h", ".cpp", ".cs", ".swift", ".php", ".vue", ".svelte",
}


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _bracket_span(lines: List[str], start: int, openers: str = "([{", closers: str = ")]}") -> Tuple[int, int]:
    """Span from `start` until the brackets opened in it balance out (best-effort; ignores strings)."""
    depth, seen = 0, False
    for j in range(start, len(lines)):
        for ch in lines[j]:
            if ch in openers:
                depth, seen = depth + 1, True
            elif ch in closers:
                depth -= 1
        if seen and depth <= 0:
            return (start, j)
    return (start, len(lines) - 1)


def _indent_span(lines: List[str], start: int) -> Tuple[int, int]:
    """Span from `start` over the more-indented body that follows it (Python-like)."""
    base = _indent(lines[start])
    end = start
    for j in range(start + 1, len(lines)):
        if not lines[j].strip():
            end = j
            continue
        if _indent(lines[j]) > base:
            end = j
        else:
            break
    while end > start and not lines[end].strip():
        end -= 1
    return (start, end)


def _find_symbol_span(lines: List[str], symbol: str, ext: str) -> Optional[Tuple[int, int]]:
    """0-based inclusive (start, end) line span of `symbol`'s definition block, or None.

    Best-effort, language-general: keyword defs (def/class/function/…) are brace-matched in
    brace languages and indent-matched otherwise; top-level assignments (`NAME = […]`) are
    bracket-matched. Returns None if the symbol isn't found (caller falls back to whole file).
    """
    esc = re.escape(symbol)
    keyword = re.compile(
        r"^\s*(?:export\s+|default\s+|public\s+|private\s+|protected\s+|internal\s+|async\s+)*"
        r"(?:def|class|func|function|fn|fun|interface|type|struct|enum|trait|object|const|let|var)\s+" + esc + r"\b"
    )
    assign = re.compile(r"^" + esc + r"\s*[:=]")  # a top-level constant / binding (indent 0)

    start, kind = None, None
    for i, ln in enumerate(lines):
        if keyword.match(ln):
            start, kind = i, "keyword"
            break
        if assign.match(ln):
            start, kind = i, "assign"
            break
    if start is None:
        return None

    head = "\n".join(lines[start:start + 3])
    opens = sum(head.count(c) for c in "([{")
    closes = sum(head.count(c) for c in ")]}")

    if kind == "assign":
        return _bracket_span(lines, start) if opens > closes else _indent_span(lines, start)
    if ext in _BRACE_EXT and "{" in head:
        return _bracket_span(lines, start, "{", "}")
    return _indent_span(lines, start)


def _split_anchor(anchor: str) -> Tuple[str, Optional[str]]:
    """Split `path:symbol` when the tail is an identifier; otherwise it's a whole-file path."""
    if ":" in anchor:
        path_part, sym = anchor.rsplit(":", 1)
        if re.fullmatch(r"[A-Za-z_]\w*", sym):
            return path_part, sym
    return anchor, None


def retrieve(root: Path, anchor: str) -> dict:
    """Resolve `anchor` under `root` to the exact original block + its sha256."""
    path_part, symbol = _split_anchor(anchor)
    fpath = root / path_part
    if not fpath.is_file():
        return {"error": f"no such file: {path_part}", "anchor": anchor}

    text = fpath.read_text(errors="ignore")
    raw_lines = text.splitlines(keepends=True)
    span = _find_symbol_span([l.rstrip("\n") for l in raw_lines], symbol, fpath.suffix) if symbol else None

    if span is None:
        block, start, end = text, 0, max(0, len(raw_lines) - 1)
        resolved_symbol = None
    else:
        start, end = span
        block = "".join(raw_lines[start:end + 1])
        resolved_symbol = symbol

    return {
        "anchor": anchor,
        "path": path_part,
        "symbol": resolved_symbol,
        "start_line": start + 1,
        "end_line": end + 1,
        "sha256": "sha256:" + hashlib.sha256(block.encode("utf-8", "ignore")).hexdigest()[:16],
        "text": block,
        "fell_back_to_file": bool(symbol) and resolved_symbol is None,
    }


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2

    result = retrieve(Path(args[0]).resolve(), args[1])
    if "error" in result:
        print(result["error"], file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps(result, indent=2))
    else:
        sys.stdout.write(result["text"])
        if not result["text"].endswith("\n"):
            sys.stdout.write("\n")
        note = " (symbol not found — whole file)" if result["fell_back_to_file"] else ""
        sym = result["symbol"] or ""
        print(
            f"# {result['path']}:{sym} L{result['start_line']}-{result['end_line']} {result['sha256']}{note}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
