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


# --- regression: the span-truncation bug the council found (v0.3.1) --------------------


def test_python_multiline_signature_not_truncated(tmp_path):
    # Black-style one-param-per-line signature: the body must not be truncated at `):`.
    (tmp_path / "m.py").write_text(
        "def target(\n    a,\n    b,\n):\n    return a + b\n" "AFTER = 1\n"
    )
    r = retrieve.retrieve(tmp_path, "m.py:target")
    assert r["symbol"] == "target"
    assert "return a + b" in r["text"]      # body captured
    assert "AFTER = 1" not in r["text"]     # stops at the def
    assert r["low_confidence"] is False


def test_python_includes_decorators(tmp_path):
    (tmp_path / "m.py").write_text(
        "import functools\n@functools.cache\ndef target(x):\n    return x\n"
    )
    r = retrieve.retrieve(tmp_path, "m.py:target")
    assert "@functools.cache" in r["text"]
    assert "def target(x):" in r["text"]


def test_python_multiline_assignment(tmp_path):
    (tmp_path / "m.py").write_text(
        "CONFIG = {\n    'a': 1,\n    'b': 2,\n}\nOTHER = 9\n"
    )
    r = retrieve.retrieve(tmp_path, "m.py:CONFIG")
    assert "'b': 2" in r["text"]
    assert "OTHER = 9" not in r["text"]


def test_ts_multiline_signature_not_truncated(tmp_path):
    # Prettier-style wrapped signature pushes `{` past line 3 — the exact failure case.
    (tmp_path / "a.ts").write_text(
        "export function target(\n  a: number,\n  b: number,\n): number {\n"
        "  const y = a + b;\n  return y;\n}\nconst after = 1;\n"
    )
    r = retrieve.retrieve(tmp_path, "a.ts:target")
    assert "return y;" in r["text"]                       # body captured (was truncated)
    assert "const after" not in r["text"]
    assert r["text"].count("{") == r["text"].count("}")
    assert r["low_confidence"] is False


def test_ts_object_default_param(tmp_path):
    (tmp_path / "a.ts").write_text(
        "export function target(opts = { a: 1, b: 2 }) {\n  return opts.a;\n}\nconst after = 2;\n"
    )
    r = retrieve.retrieve(tmp_path, "a.ts:target")
    assert "return opts.a;" in r["text"]                  # not truncated at the object literal
    assert "const after" not in r["text"]
    assert r["text"].count("{") == r["text"].count("}")


def test_js_string_embedded_brace(tmp_path):
    (tmp_path / "a.js").write_text(
        "function target() {\n  const s = '}';\n  return s;\n}\nconst after = 3;\n"
    )
    r = retrieve.retrieve(tmp_path, "a.js:target")
    assert "return s;" in r["text"]                       # a `}` in a string must not close the block
    assert "const after" not in r["text"]


def test_low_confidence_on_unbalanced_braces(tmp_path):
    (tmp_path / "a.ts").write_text("export function target() {\n  return 1;\n")  # never closes
    r = retrieve.retrieve(tmp_path, "a.ts:target")
    assert r["low_confidence"] is True                    # flagged, not silently wrong
