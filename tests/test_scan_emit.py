"""The per-folder .ngf.md emit: valid maps + index, collision-safe names, skip-existing."""

import scan


def _make_project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("from src.b import thing\n")
    (tmp_path / "src" / "b.py").write_text("def thing():\n    pass\n")
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "util.py").write_text("import os\n")
    return tmp_path


def test_emit_creates_maps_and_index(tmp_path):
    root = _make_project(tmp_path)
    result = scan.scan(root)
    written, skipped = scan.write_ngf_skeletons(root, result)

    assert (root / "index.ngf.md").exists()
    assert (root / "src" / "map-src.ngf.md").exists()
    assert (root / "lib" / "map-lib.ngf.md").exists()
    assert skipped == []

    idx = (root / "index.ngf.md").read_text()
    assert "kind: context_index" in idx
    assert "-> src/map-src.ngf.md" in idx
    assert "-> lib/map-lib.ngf.md" in idx

    src_map = (root / "src" / "map-src.ngf.md").read_text()
    assert src_map.startswith("---")
    assert "kind: context_map" in src_map
    assert 'folder: "src/"' in src_map
    assert "```ctx" in src_map
    # the resolved intra-folder import shows up as an edge
    assert "-> b" in src_map


def test_skeleton_skips_existing(tmp_path):
    root = _make_project(tmp_path)
    result = scan.scan(root)
    scan.write_ngf_skeletons(root, result)
    written2, skipped2 = scan.write_ngf_skeletons(root, result)
    assert written2 == []
    assert skipped2  # everything already there is skipped, never clobbered


def test_stem_collision_names_are_repo_unique(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "config.py").write_text("x = 1\n")
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "config.py").write_text("y = 2\n")
    result = scan.scan(tmp_path)
    names = result.node_names()
    assert "backend/config" in names
    assert "web/config" in names
    assert "config" not in names  # bare stem never used when it collides
