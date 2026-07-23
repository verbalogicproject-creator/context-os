#!/usr/bin/env python3
"""A tiny stdlib MCP server exposing context-os maps + CCR retrieve over stdio.

No dependencies — newline-delimited JSON-RPC 2.0 over stdin/stdout (the MCP stdio transport).
Lets any MCP client (Claude Code, or a runtime compressor like Headroom) read the compressed
maps and retrieve exact originals by anchor. This is CCR as MCP tools: read the cheap map,
fetch the exact original only when needed.

Tools:
  contextos_map(folder?)      -> index.ngf.md, or a folder's map-*.ngf.md (the compressed view)
  contextos_retrieve(anchor)  -> the exact original block behind a `path[:symbol]` anchor + its hash

Project root = the tool's optional `root` arg, else $CLAUDE_PROJECT_DIR, else the process cwd.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retrieve as _retrieve  # noqa: E402

SERVER = {"name": "context-os", "version": "0.3.0"}
DEFAULT_PROTOCOL = "2025-06-18"


def _root(args: dict) -> Path:
    r = args.get("root") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(r).resolve()


def _map_path(root: Path, folder: Optional[str]) -> Path:
    if not folder or folder in (".", "/"):
        return root / "index.ngf.md"
    base = Path(folder).name
    return root / folder / f"map-{base}.ngf.md"


TOOLS = [
    {
        "name": "contextos_map",
        "description": (
            "Return a context-os map (the compressed architecture view). No folder -> the root "
            "index.ngf.md; a folder -> that folder's map-*.ngf.md."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string", "description": "Repo-relative folder, e.g. 'src/store'. Omit for the root index."},
                "root": {"type": "string", "description": "Repo root (defaults to the project dir)."},
            },
        },
    },
    {
        "name": "contextos_retrieve",
        "description": (
            "Retrieve the EXACT original source behind a map reference. Anchor is a repo-relative "
            "'path' (whole file) or 'path:symbol' (one def/class/function block). Returns the block "
            "plus its sha256."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "anchor": {"type": "string", "description": "e.g. 'backend/game/state.py:apply_action' or 'src/app.ts'."},
                "root": {"type": "string"},
            },
            "required": ["anchor"],
        },
    },
]


def call_tool(name: str, args: dict) -> str:
    root = _root(args)
    if name == "contextos_map":
        path = _map_path(root, args.get("folder"))
        if not path.is_file():
            return f"no map at {path} — run /context-os to generate maps first."
        return path.read_text(errors="ignore")
    if name == "contextos_retrieve":
        result = _retrieve.retrieve(root, args.get("anchor", ""))
        if "error" in result:
            return result["error"]
        head = f"# {result['path']}:{result['symbol'] or ''} L{result['start_line']}-{result['end_line']} {result['sha256']}"
        return head + "\n" + result["text"]
    return f"unknown tool: {name}"


def handle(msg: dict) -> Optional[dict]:
    """Return a JSON-RPC response for a request, or None for a notification."""
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        proto = (msg.get("params") or {}).get("protocolVersion") or DEFAULT_PROTOCOL
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER,
        }}
    if method in ("notifications/initialized", "initialized"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        try:
            text = call_tool(params.get("name", ""), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": text}]}}
        except Exception as exc:  # never crash the server on a bad call
            return {"jsonrpc": "2.0", "id": mid,
                    "result": {"content": [{"type": "text", "text": f"error: {exc}"}], "isError": True}}
    if mid is not None:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return None


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
