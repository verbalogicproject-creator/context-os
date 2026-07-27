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
    assert "1 error" in view and "1 warn" in view
    assert "error" in view  # the severity KIND is signal and stays


def test_log_view_never_quotes_the_log(tmp_path):
    """A log's own text must never reach a map description.

    This test used to assert the opposite — `"boom happened" in view` — which pinned an
    80-character verbatim excerpt of the first error line into a file the tool tells you to
    commit. Error lines are where runtime values surface: connection strings with embedded
    passwords, tokens in URLs, hostnames, a customer id in a stack frame. Truncating to 80
    characters bounds the size of the leak, not its sensitivity.
    """
    f = tmp_path / "run.log"
    f.write_text(
        "INFO starting\n"
        "ERROR could not connect to postgres://admin:hunter2@10.0.0.4/prod\n"
        "FATAL token=sk-live-abcdef123456 rejected for user alice@example.com\n"
    )
    view = compress.compress_file(f)
    for secret in ("hunter2", "postgres://", "sk-live", "10.0.0.4", "alice@example.com"):
        assert secret not in view, f"log content leaked into the map description: {secret}"
    assert "2 error" in view


def test_dotenv_gets_no_map_node(tmp_path):
    """`.env` and its variants are never content-compressed — see compress.is_secret_file."""
    for name in (".env", ".env.local", ".env.production", "backend.env"):
        f = tmp_path / name
        f.write_text("STRIPE_SECRET_KEY=sk_live_x\nDATABASE_URL=postgres://u:p@h/db\n")
        assert compress.content_type(f) is None, f"{name} must not be a mapped content type"
        assert compress.compress_file(f) == name  # bare filename, no key names extracted


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
