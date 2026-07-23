#!/usr/bin/env python3
"""Content-aware compressed views for NON-code files.

The in-domain version of Headroom's per-content-type routing: config/docs/data/log files get
a one-line view that keeps the *shape/signal* and drops the bulk, so those folders also earn a
useful map node. Stdlib-only, deterministic (no LLM) — the description is computed at scan time.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

CONFIG_EXT = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env", ".properties"}
DOC_EXT = {".md", ".mdx", ".rst", ".txt", ".adoc"}
DATA_EXT = {".csv", ".tsv"}
LOG_EXT = {".log"}
CONTENT_EXTENSIONS = CONFIG_EXT | DOC_EXT | DATA_EXT | LOG_EXT

_TYPE = {
    **{e: "config" for e in CONFIG_EXT},
    **{e: "doc" for e in DOC_EXT},
    **{e: "data" for e in DATA_EXT},
    **{e: "log" for e in LOG_EXT},
}


def content_type(path: Path) -> Optional[str]:
    """The context-os `[type]` for a non-code file, or None if it isn't a mapped content type."""
    return _TYPE.get(path.suffix.lower())


def _compress_json(text: str) -> Optional[str]:
    try:
        obj = json.loads(text)
    except Exception:
        return None
    if isinstance(obj, dict):
        keys = list(obj.keys())
        shown = ", ".join(map(str, keys[:8])) + (f", +{len(keys) - 8} more" if len(keys) > 8 else "")
        return f"JSON object — {len(keys)} keys: {shown}"
    if isinstance(obj, list):
        shape = ""
        if obj and isinstance(obj[0], dict):
            shape = " of objects keyed " + ", ".join(map(str, list(obj[0].keys())[:6]))
        return f"JSON array — {len(obj)} items{shape}"
    return f"JSON {type(obj).__name__}"


def _compress_config(text: str, ext: str) -> str:
    if ext == ".json":
        summary = _compress_json(text)
        if summary:
            return summary
    keys = list(dict.fromkeys(re.findall(r"^\s*([\w.-]+)\s*[:=]", text, re.M)))
    sections = re.findall(r"^\s*\[([^\]]+)\]", text, re.M)
    parts = []
    if sections:
        parts.append(f"{len(sections)} sections: " + ", ".join(sections[:6]))
    if keys:
        parts.append(f"{len(keys)} keys: " + ", ".join(keys[:8]))
    return "config — " + ("; ".join(parts) if parts else "opaque")


def _compress_doc(text: str) -> str:
    lines = text.splitlines()
    title = next((ln.lstrip("# ").strip() for ln in lines if ln.startswith("# ")), "")
    heads = [re.sub(r"^#+\s*", "", ln).strip() for ln in lines if re.match(r"^#{2,}\s", ln)]
    out = "doc"
    if title:
        out += f" — '{title[:60]}'"
    if heads:
        out += " — sections: " + ", ".join(heads[:6])
    if not title and not heads:
        first = next((ln.strip() for ln in lines if ln.strip()), "")
        if first:
            out += f" — {first[:60]}"
    return out


def _compress_data(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "data — empty"
    sep = "\t" if "\t" in lines[0] else ","
    cols = lines[0].split(sep)
    return f"data — {len(cols)} cols ({', '.join(c.strip()[:20] for c in cols[:6])}), {max(0, len(lines) - 1)} rows"


def _compress_log(text: str) -> str:
    lines = text.splitlines()
    errs = [ln for ln in lines if re.search(r"\b(error|exception|fatal|traceback)\b", ln, re.I)]
    warns = [ln for ln in lines if re.search(r"\bwarn(ing)?\b", ln, re.I)]
    out = f"log — {len(lines)} lines, {len(errs)} error / {len(warns)} warn"
    if errs:
        out += f"; first error: {errs[0].strip()[:80]}"
    return out


def compress_file(path: Path) -> str:
    """One-line content-aware compressed view of a non-code file (used as its map description)."""
    ct = content_type(path)
    if ct is None:
        return path.name
    try:
        text = path.read_text(errors="ignore")
    except OSError:
        return path.name
    ext = path.suffix.lower()
    if ct == "config":
        return _compress_config(text, ext)
    if ct == "doc":
        return _compress_doc(text)
    if ct == "data":
        return _compress_data(text)
    if ct == "log":
        return _compress_log(text)
    return path.name
