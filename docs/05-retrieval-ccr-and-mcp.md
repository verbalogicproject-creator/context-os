# 05 — Retrieving originals (CCR) and the MCP server

Continuing in `/tmp/cos-tutorial` (with chapters 01 and 03's edits applied — `api/store.py`
now has a `remove` method). A map is deliberately compressed: one line per file. This
chapter is about the other half of that trade — pulling the **exact** original back, only
when you actually need it.

## Compress-Cache-Retrieve

The map is the *compressed* view of a folder; each source file is the *retrievable
original*. `scripts/retrieve.py` resolves an **anchor** — a repo-relative `path` (whole
file) or `path:symbol` (one `def`/`class`/`function` block) — to the exact original text
plus a content hash:

```bash
python3 scripts/retrieve.py /tmp/cos-tutorial api/store.py:remove
```

```
# api/store.py:remove L14-15 sha256:b19d9ffb1f525efb
    def remove(self, name):
        self._items.remove(name)
```

That's the real method you added in chapter 03 — pulled by name, not by re-reading the
whole file. `--json` gives you the same thing structured, for a caller that wants to
cache/verify by hash:

```bash
python3 scripts/retrieve.py /tmp/cos-tutorial api/store.py:remove --json
```

```json
{
  "anchor": "api/store.py:remove",
  "path": "api/store.py",
  "symbol": "remove",
  "start_line": 14,
  "end_line": 15,
  "sha256": "sha256:b19d9ffb1f525efb",
  "text": "    def remove(self, name):\n        self._items.remove(name)\n",
  "fell_back_to_file": false,
  "low_confidence": false
}
```

Two honesty flags matter here:

- **`fell_back_to_file`** — if the symbol isn't found, `retrieve` falls back to the whole
  file rather than erroring, and says so.
- **`low_confidence`** — Python symbols are resolved exactly (the stdlib `ast`, so decorators
  and multi-line signatures don't get truncated); brace/indent languages (TS/JS/Go/…) use a
  best-effort literal-aware matcher, and flag `low_confidence: true` when it can't prove the
  span is clean — so a caller knows to fall back to a full read rather than trust a possibly
  truncated block.

Omit the symbol to get the whole file (still hashed):

```bash
python3 scripts/retrieve.py /tmp/cos-tutorial api/routes.py
```

```
# api/routes.py: L1-6 sha256:3d4710f1902e6374
import json
from api.store import Store

def register(app, store: Store):
    app["/items"] = lambda: store.all()
    app["/items/add"] = lambda name: store.add(name)
```

It works the same across languages — here, the TypeScript client's `fetchItems`:

```bash
python3 scripts/retrieve.py /tmp/cos-tutorial web/client.ts:fetchItems
```

```
# web/client.ts:fetchItems L1-4 sha256:373cff08e0d7d3fe
export async function fetchItems(): Promise<string[]> {
  const r = await fetch("/items");
  return r.json();
}
```

## The same thing, over MCP

`.mcp.json` registers a stdlib stdio server (`scripts/mcp_server.py`) exposing exactly two
tools — `contextos_map` and `contextos_retrieve` — so any MCP-speaking agent (or a runtime
message compressor stacking underneath context-os) gets the same compressed-map-then-exact-
retrieve flow without shelling out to the scripts directly.

Here's a real JSON-RPC exchange over stdio (`initialize` → `tools/list` → both tools) against
the same `/tmp/cos-tutorial`:

```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
```

The reply names exactly the two tools (full `inputSchema` omitted here for space — run it
yourself to see the whole thing):

```json
{
  "result": {
    "tools": [
      {"name": "contextos_map", "description": "Return a context-os map (the compressed architecture view). No folder -> the root index.ngf.md; a folder -> that folder's map-*.ngf.md."},
      {"name": "contextos_retrieve", "description": "Retrieve the EXACT original source behind a map reference. Anchor is a repo-relative 'path' (whole file) or 'path:symbol' (one def/class/function block). Returns the block plus its sha256."}
    ]
  }
}
```
```json
{"jsonrpc": "2.0", "id": 4, "method": "tools/call",
 "params": {"name": "contextos_retrieve",
            "arguments": {"anchor": "api/store.py:remove", "root": "/tmp/cos-tutorial"}}}
```
```json
{
  "result": {
    "content": [{"type": "text",
      "text": "# api/store.py:remove L14-15 sha256:b19d9ffb1f525efb\n    def remove(self, name):\n        self._items.remove(name)\n"}]
  }
}
```

Identical text to the direct `retrieve.py` call above — the MCP server is a thin protocol
wrapper, not a second implementation.

context-os compresses *structure ahead of time* (the map); a runtime compressor like
[Headroom](https://github.com/chopratejas/headroom) squeezes *each individual request*.
They're different layers and they stack — context-os doesn't depend on one being installed.

## Verify your build

Reproduce the full round-trip yourself and confirm the transcript matches (the hash is
content-based, so an identical `remove` method gives you the identical `sha256`):

```bash
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
{"jsonrpc": "2.0", "method": "notifications/initialized"}
{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "contextos_retrieve", "arguments": {"anchor": "api/store.py:remove", "root": "/tmp/cos-tutorial"}}}' \
  | python3 scripts/mcp_server.py
```

You should see `sha256:b19d9ffb1f525efb` in the reply — the same hash `retrieve.py` printed
above, because the same 2-line method hashes the same way regardless of which surface asked
for it.

Next: **[06 — mapping non-code files](06-non-code-maps.md)**, where config, docs, data, and
log files get their own map nodes too.
