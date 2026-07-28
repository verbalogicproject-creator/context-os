"""The per-session read ledger + delivered-savings measurement (behavioral, not artifact size)."""

import json

import audit
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


def test_a_fanout_of_agents_is_distinguishable_from_one_session(tmp_path):
    """Plan #14 item 1(c). Claude Code hands every subagent its PARENT's `session_id` — observed
    live on v2.1.220, where two parallel `general-purpose` agents both reported the session id of
    the session that spawned them, and were told apart only by `agent_id`.

    Without that column the ledger says "one session read three folders" when what happened was
    three agents reading one folder each. Co-access (item 2) is computed from exactly this, so
    earned merging would have been fitted to the shape of the fan-out rather than of the task.
    """
    _mapped_repo(tmp_path)
    src = tmp_path / "pkg" / "m.py"

    session_log.record_read(tmp_path, "S", "Read", src)                  # the main session
    session_log.record_read(tmp_path, "S", "Read", src, "agent-aaa")     # two parallel subagents
    session_log.record_read(tmp_path, "S", "Read", src, "agent-bbb")

    # One ledger, because they really are one session — but three separable actors inside it.
    assert len(session_log.reads(tmp_path, "S")) == 3
    assert session_log.agents(tmp_path, "S") == [None, "agent-aaa", "agent-bbb"]

    # Scoping to an actor returns only that actor's reads: this is the fan-out, not one reader.
    assert len(session_log.reads(tmp_path, "S", None)) == 1
    assert len(session_log.reads(tmp_path, "S", "agent-aaa")) == 1
    assert len(session_log.reads(tmp_path, "S", "agent-bbb")) == 1


def test_one_agents_map_read_does_not_silence_the_nudge_for_its_siblings(tmp_path):
    """A subagent starts with its own context and has NOT inherited the parent's map read, so
    the nudge is scoped per agent. Session-wide scoping would tell four of five parallel
    enrichers nothing, precisely when the map would have saved the most."""
    map_path = _mapped_repo(tmp_path)

    session_log.record_read(tmp_path, "S", "Read", map_path, "agent-aaa")   # aaa read the map

    assert session_log.map_read_this_session(tmp_path, "S", map_path, "agent-aaa") is True
    assert session_log.map_read_this_session(tmp_path, "S", map_path, "agent-bbb") is False
    assert session_log.map_read_this_session(tmp_path, "S", map_path, None) is False
    # unscoped still answers the session-wide question, for callers that want it
    assert session_log.map_read_this_session(tmp_path, "S", map_path) is True


def test_a_ledger_written_before_the_agent_column_still_reads_as_main_session(tmp_path):
    """Backward compatibility, stated as a test: entries already on disk have no `agent` key.
    They were written by main sessions, and must keep reading as main-session entries rather
    than vanishing from every scoped query."""
    _mapped_repo(tmp_path)
    ledger = session_log.ledger_path(tmp_path, "OLD")
    session_log.ensure_log_dir(tmp_path)
    ledger.write_text(json.dumps(
        {"tool": "Read", "path": "pkg/m.py", "kind": "source_unmapped", "bytes": 30, "owner": None}
    ) + "\n")

    assert len(session_log.reads(tmp_path, "OLD")) == 1
    assert len(session_log.reads(tmp_path, "OLD", None)) == 1      # reads as the main session
    assert session_log.agents(tmp_path, "OLD") == [None]


def test_the_hook_attributes_a_read_to_the_files_repo_not_the_sessions(tmp_path):
    """The other half of the meter fix. Refusing a foreign read (above) stops the ledger being
    WRONG; resolving the root from the file stops it being EMPTY. One session working across two
    repos — a tool's own repo and the project it is run against — is routine, and it must produce
    two honest ledgers rather than one poisoned one or none at all."""
    import _common

    tool_repo = tmp_path / "tool-repo"
    (tool_repo / "scripts").mkdir(parents=True)
    (tool_repo / ".git").mkdir()

    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    (project / "pkg" / "m.py").write_text("import os\ndef f():\n    pass\n")
    scan.write_ngf_skeletons(project, scan.scan(project))     # gives it an index.ngf.md
    assert (project / "index.ngf.md").is_file()

    hook_input = {"cwd": str(tool_repo)}                       # the session sits in the TOOL repo
    resolved = project / "pkg" / "m.py"                        # but this read is in the PROJECT

    assert _common.repo_root_from(hook_input) == tool_repo.resolve()   # session root: tool repo
    assert _common.root_for_path(hook_input, resolved) == project.resolve()

    # and a read inside the session's own repo still resolves to it (no regression)
    own = tool_repo / "scripts" / "x.py"
    own.write_text("def x():\n    pass\n")
    assert _common.root_for_path(hook_input, own) == tool_repo.resolve()

    # a file under no marked root at all falls back to the session root, as before
    loose = tmp_path / "loose.py"
    loose.write_text("def y():\n    pass\n")
    assert _common.root_for_path(hook_input, loose) == tool_repo.resolve()


def test_a_read_in_another_repo_is_never_logged_here(tmp_path):
    """The meter's correctness, pinned. A session whose cwd was repo A logged repo B's reads into
    A's ledger, where `owning_map` looked for B's maps under A, found none, and scored them
    `source_unmapped`. Measured on one real session: 57 of 80 entries foreign-root, 36 of them
    scored "no map existed" for files that have one — an under-report of map use, which is the
    exact direction that makes the tool look worse than it is while still looking usable."""
    root = tmp_path / "repo-a"
    root.mkdir()
    (root / "pkg").mkdir()
    (root / "pkg" / "m.py").write_text("import os\ndef f():\n    pass\n")
    scan.write_ngf_skeletons(root, scan.scan(root))

    other = tmp_path / "repo-b"
    (other / "pkg").mkdir(parents=True)
    foreign = other / "pkg" / "m.py"
    foreign.write_text("import os\ndef g():\n    pass\n")

    assert session_log.contains(root, root / "pkg" / "m.py") is True
    assert session_log.contains(root, foreign) is False
    assert session_log.classify(root, foreign)[0] == session_log.KIND_OTHER
    assert session_log.record_read(root, "s1", "Read", foreign) is None
    assert session_log.record_explore(root, "s1", "Grep", other / "pkg") is None
    assert session_log.reads(root, "s1") == []

    # ...and a read that IS local still lands, so the guard didn't just silence the ledger
    assert session_log.record_read(root, "s1", "Read", root / "pkg" / "m.py") is not None
    assert len(session_log.reads(root, "s1")) == 1


def test_local_artifacts_ignore_themselves_from_inside(tmp_path):
    """`.context-os/` holds only local artifacts, so it carries its own ignore file — rather than
    the tool editing the project's root `.gitignore`, which is someone else's file."""
    map_path = _mapped_repo(tmp_path)
    session_log.record_read(tmp_path, "s1", "Read", map_path)

    ignore = tmp_path / ".context-os" / ".gitignore"
    assert ignore.is_file()
    body = ignore.read_text()
    rules = [ln.strip() for ln in body.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    assert set(rules) == {"digests/", "reads-*.jsonl", "relay.ngf.md"}
    assert not any("map-" in rule for rule in rules)   # maps are meant to be committed


def test_the_scanner_ignores_its_digests_from_the_first_write(tmp_path):
    result = scan.scan(tmp_path if (tmp_path / "pkg").exists() else tmp_path)
    (tmp_path / "pkg").mkdir(exist_ok=True)
    (tmp_path / "pkg" / "m.py").write_text("import os\ndef f():\n    pass\n")
    result = scan.scan(tmp_path)
    scan.write_digests(tmp_path, result)

    assert (tmp_path / ".context-os" / "digests").is_dir()
    assert "digests/" in (tmp_path / ".context-os" / ".gitignore").read_text()


def test_an_edited_ignore_file_is_never_overwritten(tmp_path):
    """A project may have deliberately un-ignored its relay — committing one is supported. The
    tool must not silently revert that on the next write."""
    (tmp_path / ".context-os").mkdir()
    edited = tmp_path / ".context-os" / ".gitignore"
    edited.write_text("# mine\nreads-*.jsonl\n")

    session_log.ensure_log_dir(tmp_path)

    assert edited.read_text() == "# mine\nreads-*.jsonl\n"


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


def test_map_is_enriched_detects_skeleton_vs_enriched(tmp_path):
    map_path = _mapped_repo(tmp_path)
    assert audit.map_is_enriched(map_path) is False           # skeleton: node desc IS the path
    map_path.write_text(map_path.read_text().replace("pkg/m.py", "does the thing"))
    assert audit.map_is_enriched(map_path) is True            # now a real description


def test_catchup_targets_lists_touched_skeleton_folders(tmp_path):
    _mapped_repo(tmp_path)
    session_log.record_read(tmp_path, "cu1", "Read", tmp_path / "pkg" / "m.py")  # touch a skeleton folder
    assert measure.catchup_targets(tmp_path, "cu1") == ["pkg"]
    # once pkg's map is enriched, it's no longer a catch-up target
    map_path = tmp_path / "pkg" / "map-pkg.ngf.md"
    map_path.write_text(map_path.read_text().replace("pkg/m.py", "does the thing"))
    assert measure.catchup_targets(tmp_path, "cu1") == []


def test_catchup_ignores_untouched_folders(tmp_path):
    _mapped_repo(tmp_path)                        # pkg exists + skeleton, but never touched
    session_log.record_read(tmp_path, "cu2", "Read", tmp_path / "pkg" / "map-pkg.ngf.md")  # read the MAP only
    # reading the map (not source) still counts pkg as touched, and it's skeleton → a target
    assert measure.catchup_targets(tmp_path, "cu2") == ["pkg"]
    assert measure.catchup_targets(tmp_path, "never-a-session") == []  # no ledger → nothing


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
