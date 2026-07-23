"""The .ngf.md-aware parser + whole-map fabrication audit (derive-don't-fabricate)."""

import audit
import scan


def test_extract_ctx_block_pulls_only_the_block():
    text = "---\nid: x\nkind: context_map\n---\n```ctx\n## G\n  a : desc [lib]\n```\n"
    body = audit.extract_ctx_block(text)
    assert "## G" in body and "a : desc [lib]" in body
    assert "id: x" not in body  # frontmatter is excluded
    assert "```" not in body  # fences excluded


def test_extract_ctx_block_passes_through_bare_ctx():
    text = "# t\n## G\n  a : desc [lib]\n"  # no fence — a legacy .ctx
    assert audit.extract_ctx_block(text) == text


def _emit(tmp_path):
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "a.py").write_text("def f():\n    pass\n")
    result = scan.scan(tmp_path)
    scan.write_ngf_skeletons(tmp_path, result)


def test_parse_map_reads_nodes_from_block(tmp_path):
    _emit(tmp_path)
    nodes, edges, warnings = audit.parse_ctx_file(tmp_path / "s" / "map-s.ngf.md")
    assert any(n.name == "a" for n in nodes)
    assert warnings == []


def test_check_maps_fabrication_passes_on_grounded_maps(tmp_path):
    _emit(tmp_path)
    result = audit.check_maps_fabrication(tmp_path)
    assert result.ok, result.findings


def test_check_maps_fabrication_catches_an_invented_node(tmp_path):
    _emit(tmp_path)
    map_path = tmp_path / "s" / "map-s.ngf.md"
    text = map_path.read_text().replace(
        "## Files", "## Files\n  ghost : nonexistent.py [component]"
    )
    map_path.write_text(text)
    result = audit.check_maps_fabrication(tmp_path)
    assert not result.ok
    assert any(f.node_name == "ghost" for f in result.findings)


def test_savings_report_is_computable(tmp_path):
    _emit(tmp_path)
    report = audit.compute_maps_token_report(tmp_path)
    assert report.files_scanned >= 1
    assert report.ctx_tokens_est >= 1


def test_edge_advisory_flags_dangling_target_without_failing(tmp_path):
    _emit(tmp_path)
    map_path = tmp_path / "s" / "map-s.ngf.md"
    map_path.write_text(
        map_path.read_text().replace(
            "## Files", "## Files\n  a : local file [component] -> ghosttarget"
        )
    )
    result = audit.check_maps_fabrication(tmp_path)
    assert result.ok  # advisory only: every node is real, so the fabrication gate still passes
    assert any("ghosttarget" in w for w in result.edge_warnings)
