#!/usr/bin/env python3
"""Retrieve the exact original source behind a context-os map reference — the CCR "retrieve".

A map is the *compressed* view of a folder; each source file is the *retrievable original*.
Given an anchor — a repo-relative ``path`` (whole file) or ``path:symbol`` (one
``def``/``class``/``function`` block) — this returns the exact original text plus its
``sha256``, so a reader consults the cheap map and pulls the exact original only when it
actually needs it (Compress-Cache-Retrieve, in-domain, stdlib-only, offline).

The hash lets a caller cache/verify by content, and ties to drift: a mismatch against a hash
captured when the map was built means that exact block changed.

Symbol spans are exact for Python (parsed with the stdlib ``ast``) and best-effort for
brace/indent languages (literal-aware bracket/indent matching). When the best-effort matcher
can't prove the span is clean, the result carries ``low_confidence: true`` so a caller can
fall back to a whole-file read rather than trust a possibly-truncated block. If the symbol
isn't found at all, it falls back to the whole file (``fell_back_to_file: true``).

Usage:
    python3 retrieve.py <root> <anchor>          # print the block; a "# … sha256:…" note on stderr
    python3 retrieve.py <root> <anchor> --json    # {"path","symbol","start_line","end_line","sha256","text",…}
"""

from __future__ import annotations

import ast
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

# (start, end, low_confidence) — 0-based inclusive line span.
Span = Tuple[int, int, bool]


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" \t"))


def _blank_literals(line: str) -> str:
    """Replace string/char-literal bodies and ``//`` line-comments with spaces.

    So a bracket that lives inside a string, template literal, f-string, or line comment
    does not perturb depth counting — the exact failure mode that used to desync the
    matcher. Best-effort and *per line*: it does not track a string that spans lines
    (those are caught by the low-confidence balance check instead).
    """
    out: List[str] = []
    quote: Optional[str] = None
    escaped = False
    for ch in line:
        if quote is not None:
            if escaped:
                escaped = False
                out.append(" ")
            elif ch == "\\":
                escaped = True
                out.append(" ")
            elif ch == quote:
                quote = None
                out.append(ch)
            else:
                out.append(" ")
        elif ch in "\"'`":
            quote = ch
            out.append(ch)
        else:
            out.append(ch)
    blanked = "".join(out)
    idx = blanked.find("//")  # strings are already blanked, so this is a real comment
    if idx != -1:
        blanked = blanked[:idx] + " " * (len(blanked) - idx)
    return blanked


def _bracket_span(lines: List[str], start: int, openers: str = "([{", closers: str = ")]}") -> Span:
    """Span from `start` until the brackets opened in it balance out (literal-aware)."""
    depth, seen = 0, False
    for j in range(start, len(lines)):
        for ch in _blank_literals(lines[j]):
            if ch in openers:
                depth, seen = depth + 1, True
            elif ch in closers:
                depth -= 1
        if seen and depth <= 0:
            return (start, j, False)
    return (start, len(lines) - 1, True)  # never balanced → suspect


def _brace_body_start(lines: List[str], start: int, limit: int = 80) -> Optional[int]:
    """Index of the `{` that opens `start`'s body, scanning *past* a multi-line signature.

    Counts only the signature's own `()`/`[]` depth so a body `{` is recognized at depth 0
    while an object-literal default or an inline `{…}` type inside the params (depth > 0) is
    not. Returns None if the signature ends in `;` (a declaration/abstract member: no body)
    or no brace body appears within `limit` lines.
    """
    depth = 0
    seen_paren = False
    for j in range(start, min(len(lines), start + limit)):
        blanked = _blank_literals(lines[j])
        for ch in blanked:
            if ch in "([":
                depth += 1
                seen_paren = True
            elif ch in ")]":
                depth -= 1
            elif ch == "{" and depth <= 0:
                return j
        if seen_paren and depth <= 0 and ";" in blanked:
            return None
    return None


def _brace_span_from(lines: List[str], def_start: int, brace_line: int) -> Span:
    """Span from `def_start` to the `}` that closes the body opened on `brace_line`."""
    depth, seen = 0, False
    for j in range(brace_line, len(lines)):
        for ch in _blank_literals(lines[j]):
            if ch == "{":
                depth, seen = depth + 1, True
            elif ch == "}":
                depth -= 1
        if seen and depth <= 0:
            return (def_start, j, False)
    return (def_start, len(lines) - 1, True)  # never closed → suspect


def _indent_span(lines: List[str], start: int) -> Span:
    """Span over the more-indented body that follows `start` (Python-like).

    First advances past a possibly multi-line signature (until its brackets balance) so the
    body scan is anchored *after* the `):`, not stopped at it — the old bug.
    """
    base = _indent(lines[start])
    depth = 0
    head_end = start
    for j in range(start, len(lines)):
        for ch in _blank_literals(lines[j]):
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth -= 1
        head_end = j
        if depth <= 0:
            break
    end = head_end
    for j in range(head_end + 1, len(lines)):
        if not lines[j].strip():
            end = j
            continue
        if _indent(lines[j]) > base:
            end = j
        else:
            break
    while end > start and not lines[end].strip():
        end -= 1
    return (start, end, False)


def _python_span_via_ast(text: str, symbol: str) -> Optional[Tuple[int, int]]:
    """Exact 0-based inclusive (start, end) span of `symbol` in Python source, or None.

    Uses the stdlib parser, so multi-line signatures, decorators, and multi-line
    assignments are handled precisely — no heuristics. Returns None on a syntax error
    (partial/invalid file) so the caller falls back to the best-effort matcher.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return None
    best: Optional[Tuple[int, int]] = None
    for node in ast.walk(tree):
        matched = False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            matched = node.name == symbol
        elif isinstance(node, ast.Assign):
            matched = any(isinstance(t, ast.Name) and t.id == symbol for t in node.targets)
        elif isinstance(node, ast.AnnAssign):
            matched = isinstance(node.target, ast.Name) and node.target.id == symbol
        if not matched:
            continue
        start = node.lineno
        for dec in getattr(node, "decorator_list", []) or []:
            start = min(start, dec.lineno)
        end = getattr(node, "end_lineno", None) or node.lineno
        cand = (start - 1, end - 1)
        if best is None or cand[0] < best[0]:  # earliest definition wins (first in file)
            best = cand
    return best


def _find_symbol_span(lines: List[str], symbol: str, ext: str) -> Optional[Span]:
    """Best-effort (start, end, low_confidence) span of `symbol`'s block, or None.

    Language-general: keyword defs (def/class/function/…) get a brace body in brace
    languages (scanning past a multi-line signature) or an indent body otherwise; top-level
    bindings (`NAME = […]`) are bracket-matched. Decorator lines directly above the
    definition are folded into the span. Returns None if the symbol isn't found.
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

    # Fold contiguous decorator lines directly above the definition into the span.
    while start - 1 >= 0 and lines[start - 1].lstrip().startswith("@"):
        start -= 1
    def_line = start
    while def_line < len(lines) and lines[def_line].lstrip().startswith("@"):
        def_line += 1
    if def_line >= len(lines):
        return (start, len(lines) - 1, True)

    if kind == "assign":
        blanked = _blank_literals(lines[def_line])
        opens = sum(blanked.count(c) for c in "([{")
        closes = sum(blanked.count(c) for c in ")]}")
        if opens > closes:
            _, end, low = _bracket_span(lines, def_line)
            return (start, end, low)
        return (start, def_line, False)  # single-line binding

    if ext in _BRACE_EXT:
        brace_line = _brace_body_start(lines, def_line)
        if brace_line is not None:
            _, end, low = _brace_span_from(lines, def_line, brace_line)
            return (start, end, low)
    _, end, low = _indent_span(lines, def_line)
    return (start, end, low)


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

    span: Optional[Span] = None
    if symbol:
        if fpath.suffix == ".py":
            exact = _python_span_via_ast(text, symbol)
            if exact is not None:
                span = (exact[0], exact[1], False)
        if span is None:
            span = _find_symbol_span([l.rstrip("\n") for l in raw_lines], symbol, fpath.suffix)

    if span is None:
        block, start, end, low = text, 0, max(0, len(raw_lines) - 1), False
        resolved_symbol = None
    else:
        start, end, low = span
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
        "low_confidence": bool(low),
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
        if result["fell_back_to_file"]:
            note = " (symbol not found — whole file)"
        elif result["low_confidence"]:
            note = " (best-effort span — LOW CONFIDENCE; re-read the whole file if it looks truncated)"
        else:
            note = ""
        sym = result["symbol"] or ""
        print(
            f"# {result['path']}:{sym} L{result['start_line']}-{result['end_line']} {result['sha256']}{note}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
