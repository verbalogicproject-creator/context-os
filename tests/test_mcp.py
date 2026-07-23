"""The stdlib MCP server: JSON-RPC handshake + the contextos_map / contextos_retrieve tools."""

import json
import subprocess
import sys
from pathlib import Path

import mcp_server


def test_initialize_and_tools_list():
    init = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                              "params": {"protocolVersion": "2025-06-18"}})
    assert init["result"]["serverInfo"]["name"] == "context-os"
    assert init["result"]["protocolVersion"] == "2025-06-18"

    listing = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in listing["result"]["tools"]}
    assert names == {"contextos_map", "contextos_retrieve"}

    # a notification returns nothing
    assert mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_retrieve_tool(tmp_path):
    (tmp_path / "f.py").write_text("def target():\n    return 42\n")
    out = mcp_server.call_tool("contextos_retrieve", {"anchor": "f.py:target", "root": str(tmp_path)})
    assert "def target():" in out
    assert "return 42" in out
    assert "sha256:" in out


def test_map_tool(tmp_path):
    (tmp_path / "index.ngf.md").write_text("---\nkind: context_index\n---\n```ctx\n## Folders\n```\n")
    out = mcp_server.call_tool("contextos_map", {"root": str(tmp_path)})
    assert "context_index" in out
    missing = mcp_server.call_tool("contextos_map", {"folder": "nope", "root": str(tmp_path)})
    assert "no map at" in missing


def test_stdio_round_trip(tmp_path):
    (tmp_path / "f.py").write_text("def target():\n    return 7\n")
    server = Path(__file__).resolve().parent.parent / "scripts" / "mcp_server.py"
    msgs = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "contextos_retrieve",
                               "arguments": {"anchor": "f.py:target", "root": str(tmp_path)}}}),
    ]) + "\n"
    proc = subprocess.run([sys.executable, str(server)], input=msgs,
                          capture_output=True, text=True, timeout=15)
    lines = [json.loads(l) for l in proc.stdout.splitlines() if l.strip()]
    ids = {m.get("id"): m for m in lines}
    assert ids[1]["result"]["serverInfo"]["name"] == "context-os"   # initialize replied
    assert "return 7" in ids[2]["result"]["content"][0]["text"]      # tools/call replied with the block
