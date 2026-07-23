"""Content-aware compression for non-code files, and its integration into the scan/emit."""

from pathlib import Path

import audit
import compress
import scan


def test_json_config_view(tmp_path):
    f = tmp_path / "package.json"
    f.write_text('{"name": "x", "version": "1", "scripts": {}, "deps": {}}')
    assert compress.content_type(f) == "config"
    view = compress.compress_file(f)
    assert "JSON object" in view and "name" in view and "version" in view


def test_markdown_doc_view(tmp_path):
    f = tmp_path / "README.md"
    f.write_text("# Title\n\n## Install\ntext\n## Usage\ntext\n")
    view = compress.compress_file(f)
    assert "Title" in view and "Install" in view and "Usage" in view


def test_csv_data_view(tmp_path):
    f = tmp_path / "rows.csv"
    f.write_text("id,name,score\n1,a,9\n2,b,8\n")
    view = compress.compress_file(f)
    assert "3 cols" in view and "2 rows" in view


def test_log_view(tmp_path):
    f = tmp_path / "run.log"
    f.write_text("INFO ok\nERROR boom happened\nWARN careful\nINFO ok\n")
    view = compress.compress_file(f)
    assert "1 error" in view and "1 warn" in view and "boom happened" in view


def test_non_code_folder_gets_a_map_node(tmp_path):
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "settings.json").write_text('{"a": 1, "b": 2}')
    result = scan.scan(tmp_path)
    scan.write_ngf_skeletons(tmp_path, result)
    map_text = (tmp_path / "conf" / "map-conf.ngf.md").read_text()
    assert "settings :" in map_text
    assert "JSON object" in map_text          # the compressed view is the description
    assert "[config]" in map_text
    # and the whole-map fabrication audit still passes (content nodes trace to real files)
    assert audit.check_maps_fabrication(tmp_path).ok


def test_content_node_bracket_safe(tmp_path):
    # a config whose view might contain brackets must not break the [type] parse
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "a.py").write_text("def f():\n    pass\n")
    (tmp_path / "app" / "data.json").write_text('[{"k": 1}, {"k": 2}]')
    result = scan.scan(tmp_path)
    scan.write_ngf_skeletons(tmp_path, result)
    nodes, _edges, warnings = audit.parse_ctx_file(tmp_path / "app" / "map-app.ngf.md")
    assert warnings == []
    assert any(n.name == "data" and n.type == "config" for n in nodes)  # .json → config
