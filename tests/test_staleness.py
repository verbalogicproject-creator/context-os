"""The structural-hash drift engine: semantic (not temporal) change detection + frontmatter I/O."""

import pytest

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


# --- regression: malformed-frontmatter guard + atomic writes (v0.3.1) ------------------


def test_stamp_raises_on_malformed_frontmatter(tmp_path):
    bad = tmp_path / "map-x.ngf.md"
    bad.write_text("no frontmatter at all\n```ctx\n```\n")
    with pytest.raises(ctx_staleness.MalformedFrontmatterError):
        ctx_staleness.stamp(bad)  # must NOT silently no-op and report success


def test_flip_reports_unreadable_frontmatter(tmp_path):
    bad = tmp_path / "map-x.ngf.md"
    bad.write_text("no frontmatter here\n")
    assert ctx_staleness.flip(bad) == ctx_staleness.STATUS_UNREADABLE


def test_bom_frontmatter_is_tolerated(tmp_path):
    map_path = _setup(tmp_path)
    ctx_staleness.stamp(map_path)
    map_path.write_text("﻿" + map_path.read_text())  # a BOM a Windows editor might leave
    ctx_staleness.stamp(map_path)  # does not raise: BOM tolerated on line 0
    assert ctx_staleness.flip(map_path) == "verified"


def test_stamp_leaves_no_temp_files(tmp_path):
    map_path = _setup(tmp_path)
    ctx_staleness.stamp(map_path)
    assert list(map_path.parent.glob(".ctxtmp-*")) == []  # atomic write cleans up its temp


def test_stamp_all_reports_failures(tmp_path):
    good = _setup(tmp_path)  # a real, well-formed map under pkg/
    (tmp_path / "map-broken.ngf.md").write_text("not a map\n")
    count, failed = ctx_staleness.stamp_all(tmp_path)
    assert count == 1
    assert len(failed) == 1 and failed[0].name == "map-broken.ngf.md"
    assert ctx_staleness.flip(good) == "verified"  # the good one was still stamped
