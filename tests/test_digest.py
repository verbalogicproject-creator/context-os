"""Per-folder structural digests (cheap enrichment input for map-enricher)."""

import scan


def test_file_digest_captures_doc_and_declarations(tmp_path):
    f = tmp_path / "svc.py"
    f.write_text(
        '"""Item service — owns the store."""\n'
        "import os\n"
        "class Store:\n"
        "    def add(self):\n        pass\n"
        "def helper():\n    pass\n"
    )
    digest = scan.file_digest(f, "svc.py")
    assert "svc.py" in digest
    assert "Item service" in digest       # leading docstring
    assert "class Store" in digest        # declaration
    assert "def helper" in digest


def test_write_digests_creates_per_folder_files(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text('"""Module A."""\ndef f():\n    pass\n')
    result = scan.scan(tmp_path)
    count = scan.write_digests(tmp_path, result)
    assert count >= 1
    digest_file = tmp_path / ".context-os" / "digests" / "pkg" / "digest.txt"
    assert digest_file.exists()
    assert "a.py" in digest_file.read_text()
