"""CCR retrieve: resolve a path[:symbol] anchor to the exact original block + a content hash."""

import retrieve


def test_retrieve_python_symbol_block(tmp_path):
    (tmp_path / "svc.py").write_text(
        "import os\n"
        "def helper():\n    return 1\n"
        "def target(x):\n    y = x + 1\n    return y\n"
        "TAIL = 9\n"
    )
    r = retrieve.retrieve(tmp_path, "svc.py:target")
    assert r["symbol"] == "target"
    assert "def target(x):" in r["text"]
    assert "return y" in r["text"]
    assert "def helper" not in r["text"]      # only the target block
    assert "TAIL = 9" not in r["text"]        # stops at dedent
    assert r["sha256"].startswith("sha256:")


def test_retrieve_brace_language_block(tmp_path):
    (tmp_path / "a.ts").write_text(
        "export function target(x: number) {\n  const y = x + 1;\n  return y;\n}\n"
        "const after = 1;\n"
    )
    r = retrieve.retrieve(tmp_path, "a.ts:target")
    assert r["symbol"] == "target"
    assert r["text"].count("{") == r["text"].count("}")   # brace-balanced block
    assert "const after" not in r["text"]


def test_retrieve_whole_file_when_no_symbol(tmp_path):
    (tmp_path / "f.py").write_text("A = 1\nB = 2\n")
    r = retrieve.retrieve(tmp_path, "f.py")
    assert r["symbol"] is None
    assert r["text"] == "A = 1\nB = 2\n"


def test_unknown_symbol_falls_back_to_whole_file(tmp_path):
    (tmp_path / "f.py").write_text("def real():\n    pass\n")
    r = retrieve.retrieve(tmp_path, "f.py:ghost")
    assert r["fell_back_to_file"] is True
    assert r["symbol"] is None
    assert "def real" in r["text"]


def test_hash_changes_when_block_changes(tmp_path):
    (tmp_path / "f.py").write_text("def target():\n    return 1\n")
    h1 = retrieve.retrieve(tmp_path, "f.py:target")["sha256"]
    (tmp_path / "f.py").write_text("def target():\n    return 2\n")
    h2 = retrieve.retrieve(tmp_path, "f.py:target")["sha256"]
    assert h1 != h2


def test_missing_file_errors(tmp_path):
    r = retrieve.retrieve(tmp_path, "nope.py:x")
    assert "error" in r
