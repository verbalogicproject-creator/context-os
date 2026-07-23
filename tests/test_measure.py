"""The per-session read ledger + delivered-savings measurement (behavioral, not artifact size)."""

import json

import ctx_staleness
import measure
import scan
import session_log


def _mapped_repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "m.py").write_text("import os\ndef f():\n    pass\n")
    result = scan.scan(tmp_path)
    scan.write_ngf_skeletons(tmp_path, result)
    map_path = tmp_path / "pkg" / "map-pkg.ngf.md"
    ctx_staleness.stamp(map_path)
    return map_path


def test_classify_map_and_source(tmp_path):
    map_path = _mapped_repo(tmp_path)
    assert session_log.classify(tmp_path, map_path)[0] == session_log.KIND_MAP
    kind, owner = session_log.classify(tmp_path, tmp_path / "pkg" / "m.py")
    assert kind == session_log.KIND_SOURCE_MAPPED
    assert owner == map_path.resolve()


def test_source_without_map_is_unmapped(tmp_path):
    (tmp_path / "solo.py").write_text("x = 1\n")
    kind, _owner = session_log.classify(tmp_path, tmp_path / "solo.py")
    assert kind == session_log.KIND_SOURCE_UNMAPPED


def test_source_read_without_map_read_scores_zero_consultation(tmp_path):
    _mapped_repo(tmp_path)
    session_log.record_read(tmp_path, "s1", "Read", tmp_path / "pkg" / "m.py")
    s = measure.summarize(tmp_path, "s1")
    assert s["source_in_mapped_dirs"] == 1
    assert s["maps_read"] == 0
    assert s["consultation_rate"] == 0.0  # touched a mapped folder but never read its map


def test_reading_the_map_counts_as_consulted(tmp_path):
    map_path = _mapped_repo(tmp_path)
    session_log.record_read(tmp_path, "s2", "Read", map_path)
    session_log.record_read(tmp_path, "s2", "Read", tmp_path / "pkg" / "m.py")
    s = measure.summarize(tmp_path, "s2")
    assert s["maps_read"] == 1
    assert s["consultation_rate"] == 1.0


def test_explore_logged_only_for_mapped_folders(tmp_path):
    _mapped_repo(tmp_path)
    entry = session_log.record_explore(tmp_path, "s3", "Grep", tmp_path / "pkg")
    assert entry is not None and entry["kind"] == session_log.KIND_EXPLORE
    (tmp_path / "nomap").mkdir()
    assert session_log.record_explore(tmp_path, "s3", "Grep", tmp_path / "nomap") is None
    assert measure.summarize(tmp_path, "s3")["explored_mapped_dirs"] == 1


def test_other_reads_are_not_logged(tmp_path):
    _mapped_repo(tmp_path)
    (tmp_path / "notes.txt").write_text("hi")
    assert session_log.record_read(tmp_path, "s4", "Read", tmp_path / "notes.txt") is None
    assert session_log.reads(tmp_path, "s4") == []


def test_latest_session_id(tmp_path):
    map_path = _mapped_repo(tmp_path)
    session_log.record_read(tmp_path, "sX", "Read", map_path)
    assert session_log.latest_session_id(tmp_path) == "sX"


def test_corrupt_ledger_line_is_skipped(tmp_path):
    _mapped_repo(tmp_path)
    session_log.record_read(tmp_path, "s5", "Read", tmp_path / "pkg" / "m.py")
    ledger = session_log.ledger_path(tmp_path, "s5")
    ledger.write_text(ledger.read_text() + "{ not json\n")  # a torn append
    assert len(session_log.reads(tmp_path, "s5")) == 1  # the good line survives


def test_transcript_best_effort_counts_a_source_read(tmp_path):
    _mapped_repo(tmp_path)
    line = json.dumps(
        {"message": {"content": [{"type": "tool_use", "name": "Read",
                                   "input": {"file_path": "pkg/m.py"}}]}}
    )
    transcript = tmp_path / "sess.jsonl"
    transcript.write_text(line + "\n")
    result = measure.summarize_transcript(tmp_path, transcript)
    assert result["source_in_mapped_dirs"] == 1
