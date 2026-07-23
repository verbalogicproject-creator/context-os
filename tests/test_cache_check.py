"""Cache-stability hygiene: the pointer block must stay volatile-free and byte-stable."""

import audit
import claudemd_splice as cs


def test_clean_pointer_block_passes(tmp_path):
    path = tmp_path / "CLAUDE.md"
    cs.splice_claudemd(path)  # the real, fixed pointer block
    assert audit.check_cache_stability(tmp_path) == []


def test_volatile_content_is_flagged(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text(
        f"{cs.CLAUDE_START}\n"
        "generated 2026-07-22T14:00, session 550e8400-e29b-41d4-a716-446655440000\n"
        f"{cs.CLAUDE_END}\n"
    )
    kinds = {kind for _f, kind, _s in audit.check_cache_stability(tmp_path)}
    assert "timestamp" in kinds
    assert "uuid" in kinds


def test_pointer_block_is_byte_stable(tmp_path):
    # the always-loaded block must be deterministic — identical bytes every regeneration
    assert cs.build_claudemd_block() == cs.build_claudemd_block()
    path = tmp_path / "CLAUDE.md"
    path.write_text("# my notes\n")
    cs.splice_claudemd(path)
    first = path.read_text()
    cs.splice_claudemd(path)  # idempotent re-run must not change a byte
    assert path.read_text() == first
