"""The pointer-block splice: augment-don't-clobber — preserve, idempotent, refuse-on-malformed."""

import claudemd_splice as cs


def test_splice_appends_and_preserves_existing(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text("# My Project\n\nMy own notes.\n")
    result = cs.splice_claudemd(path)
    assert result.changed
    out = path.read_text()
    assert "# My Project" in out and "My own notes." in out
    assert cs.CLAUDE_START in out and cs.CLAUDE_END in out


def test_splice_into_fresh_file(tmp_path):
    path = tmp_path / "AGENTS.md"
    result = cs.splice_claudemd(path)
    assert result.changed
    assert cs.CLAUDE_START in path.read_text()


def test_splice_is_idempotent(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text("# Mine\n")
    cs.splice_claudemd(path)
    result2 = cs.splice_claudemd(path)
    assert not result2.changed  # no spurious rewrite / no second .bak


def test_refuse_on_malformed_markers(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text(f"{cs.CLAUDE_START}\nstart but no end\n")
    result = cs.splice_claudemd(path)
    assert result.refused
    assert not result.changed


def test_byte_identity_outside_the_block(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text("# Mine\n\nnotes\n")
    before = path.read_text()
    cs.splice_claudemd(path)
    after = path.read_text()
    assert cs.strip_block(before, cs.CLAUDE_START, cs.CLAUDE_END) == cs.strip_block(
        after, cs.CLAUDE_START, cs.CLAUDE_END
    )


def test_pointer_block_stops_the_explore_reflex(tmp_path):
    # the load-bearing sentence must actually be present
    block = cs.build_claudemd_block()
    assert "Do NOT fan out exploration agents" in block
    assert "index.ngf.md" in block
