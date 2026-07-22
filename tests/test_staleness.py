"""The structural-hash drift engine: semantic (not temporal) change detection + frontmatter I/O."""

import ctx_staleness
import scan


def _setup(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("import os\ndef f():\n    pass\n")
    result = scan.scan(tmp_path)
    scan.write_ngf_skeletons(tmp_path, result)
    return tmp_path / "pkg" / "map-pkg.ngf.md"


def test_stamp_writes_baseline_and_verified(tmp_path):
    map_path = _setup(tmp_path)
    ctx_staleness.stamp(map_path)
    text = map_path.read_text()
    assert "structural_hash: sha256:" in text
    assert ctx_staleness.flip(map_path) == "verified"


def test_whitespace_and_comments_do_not_drift(tmp_path):
    map_path = _setup(tmp_path)
    ctx_staleness.stamp(map_path)
    # reformat + add a comment: NOT an architecture change
    (map_path.parent / "m.py").write_text("import os\n\n# a note\ndef f():\n        pass\n")
    assert ctx_staleness.flip(map_path) == "verified"


def test_new_import_drifts(tmp_path):
    map_path = _setup(tmp_path)
    ctx_staleness.stamp(map_path)
    (map_path.parent / "m.py").write_text("import os\nimport sys\ndef f():\n    pass\n")
    assert ctx_staleness.flip(map_path).startswith("DRIFTED")


def test_new_file_drifts(tmp_path):
    map_path = _setup(tmp_path)
    ctx_staleness.stamp(map_path)
    (map_path.parent / "n.py").write_text("def g():\n    pass\n")
    assert ctx_staleness.flip(map_path).startswith("DRIFTED")


def test_unstamped_when_no_baseline(tmp_path):
    map_path = _setup(tmp_path)
    assert ctx_staleness.flip(map_path).startswith("unstamped")


def test_owning_map_resolves_source_and_self(tmp_path):
    map_path = _setup(tmp_path)
    source = map_path.parent / "m.py"
    assert ctx_staleness.owning_map(tmp_path, source) == map_path
    assert ctx_staleness.owning_map(tmp_path, map_path) == map_path


def test_frontmatter_set_get_roundtrip():
    text = "---\nid: x\nkind: context_map\n---\nbody\n"
    out = ctx_staleness.fm_set(text, "staleness", "verified")
    assert ctx_staleness.fm_get(out, "staleness") == "verified"
    out2 = ctx_staleness.fm_set(out, "staleness", "DRIFTED — folder changed")
    assert ctx_staleness.fm_get(out2, "staleness") == "DRIFTED — folder changed"
    assert out2.count("staleness:") == 1  # replaced in place, never duplicated


def test_frontmatter_set_refuses_without_frontmatter():
    text = "no frontmatter here\n"
    assert ctx_staleness.fm_set(text, "staleness", "verified") == text
