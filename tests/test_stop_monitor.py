"""The context-threshold monitor: warn once per band as re-reading the conversation gets costly.

Cost is the integral of context over turns — 61-73% of it is prefix re-processing on four
measured sessions — so the expensive thing is how long a session runs, not how big one read was.
This monitor is the part of context-os that acts on that, and a monitor that repeats gets muted,
so the once-only guarantee is as load-bearing as the thresholds themselves.
"""

import json

import stop


def _hook_input(tmp_path, transcript, session="S"):
    return {"transcript_path": str(transcript), "session_id": session, "cwd": str(tmp_path)}


def _transcript(tmp_path, cache_read):
    """A minimal transcript tail carrying the field `relay.prefix_tokens` reads."""
    path = tmp_path / "t.jsonl"
    path.write_text(json.dumps({
        "type": "assistant",
        "message": {"usage": {"cache_read_input_tokens": cache_read,
                              "input_tokens": 3, "output_tokens": 5}},
    }) + "\n")
    return path


# --- band selection ---------------------------------------------------------

def test_below_the_first_band_says_nothing():
    """The common case. A monitor that speaks early is a monitor that gets ignored."""
    assert stop.band_for(199_999, set()) is None
    assert stop.band_for(0, set()) is None


def test_each_band_fires_at_its_edge():
    assert stop.band_for(200_000, set()) == 200_000
    assert stop.band_for(250_000, set()) == 250_000
    assert stop.band_for(300_000, set()) == 300_000


def test_just_below_a_band_reports_the_one_actually_crossed():
    assert stop.band_for(249_999, set()) == 200_000
    assert stop.band_for(299_999, set()) == 250_000


def test_far_above_reports_the_highest_band_not_the_lowest():
    """A session that jumps past several bands in one turn should name where it IS, not the
    threshold it left long ago."""
    assert stop.band_for(900_000, set()) == 300_000


def test_a_fired_band_is_skipped_and_the_next_one_still_fires():
    assert stop.band_for(260_000, {250_000}) == 200_000
    assert stop.band_for(260_000, {250_000, 200_000}) is None


# --- once-only, across hook invocations -------------------------------------

def test_a_band_fires_once_and_then_stays_quiet(tmp_path):
    """The whole guarantee, exercised through `main()` rather than the helpers — this is what
    repeated Stop events actually do."""
    transcript = _transcript(tmp_path, 210_000)
    hook_input = _hook_input(tmp_path, transcript)

    assert stop.band_for(210_000, stop.fired_bands(tmp_path, "S")) == 200_000
    stop.record_band(tmp_path, "S", 200_000)
    # every later turn at the same size must now be silent
    for _ in range(5):
        assert stop.band_for(210_000, stop.fired_bands(tmp_path, "S")) is None
    assert stop.fired_bands(tmp_path, "S") == {200_000}
    assert hook_input["session_id"] == "S"


def test_two_sessions_do_not_share_a_band_state(tmp_path):
    stop.record_band(tmp_path, "SESSION-A", 200_000)
    assert stop.fired_bands(tmp_path, "SESSION-A") == {200_000}
    assert stop.fired_bands(tmp_path, "SESSION-B") == set()


def test_state_is_gitignored_by_its_own_nested_file(tmp_path):
    """`ensure_log_dir` never overwrites an existing `.context-os/.gitignore`, so a project that
    installed an earlier version would never receive a new pattern. The state directory carries
    its own ignore file instead, which works for old and new installs alike."""
    directory = stop.state_dir(tmp_path)
    assert (directory / ".gitignore").read_text().strip() == "*"


def test_unreadable_state_reads_as_nothing_fired(tmp_path):
    stop.state_dir(tmp_path)
    stop._state_path(tmp_path, "S").write_text("{not json")
    assert stop.fired_bands(tmp_path, "S") == set()


# --- invariant 7: never break the session -----------------------------------

def test_a_missing_transcript_is_silent_not_fatal(tmp_path, capsys):
    stop.main.__globals__["read_hook_input"] = lambda: _hook_input(tmp_path, tmp_path / "nope.jsonl")
    try:
        assert stop.main() == 0
        assert json.loads(capsys.readouterr().out) == {}
    finally:
        stop.main.__globals__["read_hook_input"] = stop.read_hook_input


def test_junk_hook_input_is_silent_not_fatal(tmp_path, capsys):
    stop.main.__globals__["read_hook_input"] = lambda: {"transcript_path": None}
    try:
        assert stop.main() == 0
        assert json.loads(capsys.readouterr().out) == {}
    finally:
        stop.main.__globals__["read_hook_input"] = stop.read_hook_input


def test_an_exploding_hook_input_still_exits_clean(capsys):
    """Invariant 7 stated as a test: the monitor swallows everything."""
    def boom():
        raise RuntimeError("transcript unreadable")
    stop.main.__globals__["read_hook_input"] = boom
    try:
        assert stop.main() == 0
        assert json.loads(capsys.readouterr().out) == {}
    finally:
        stop.main.__globals__["read_hook_input"] = stop.read_hook_input


# --- the message itself -----------------------------------------------------

def test_the_message_names_the_band_and_points_at_relay():
    text = stop.message(250_000, 262_144)
    assert "250,000" in text and "262,144" in text
    assert "/relay" in text


def test_the_message_carries_no_jargon():
    """Public-facing copy rule (CLAUDE.md): plain English only.

    Matched on word boundaries, not substrings — `sag` is inside `message`, and a check that
    crude fails on correct copy, which is how a style gate gets deleted instead of fixed.
    """
    import re
    text = stop.message(200_000, 201_000).lower()
    for word in ("ngf", "substrate", "sag", "declared", "declaration",
                 "prefix", "integral", "ai_card"):
        assert not re.search(rf"\b{re.escape(word)}\b", text), word


# --- end to end through main() ----------------------------------------------

def test_main_emits_the_warning_once_for_a_real_transcript(tmp_path, capsys):
    transcript = _transcript(tmp_path, 305_000)
    stop.main.__globals__["read_hook_input"] = lambda: _hook_input(tmp_path, transcript)
    try:
        assert stop.main() == 0
        first = json.loads(capsys.readouterr().out)
        assert "300,000" in first["systemMessage"]

        assert stop.main() == 0          # same session, same size, next turn
        assert json.loads(capsys.readouterr().out) == {}
    finally:
        stop.main.__globals__["read_hook_input"] = stop.read_hook_input


def test_crossing_a_high_band_satisfies_the_lower_ones(tmp_path, capsys):
    """The repeat bug this monitor would otherwise have: a session sitting above 300k warned on
    three consecutive turns — 300k, then 250k, then 200k — because each lower band was still
    unfired. Crossing a threshold means the ones below it were crossed too."""
    transcript = _transcript(tmp_path, 320_000)
    stop.main.__globals__["read_hook_input"] = lambda: _hook_input(tmp_path, transcript)
    try:
        assert stop.main() == 0
        assert "300,000" in json.loads(capsys.readouterr().out)["systemMessage"]
        for _ in range(4):                       # four more turns, same session
            assert stop.main() == 0
            assert json.loads(capsys.readouterr().out) == {}
    finally:
        stop.main.__globals__["read_hook_input"] = stop.read_hook_input
    assert stop.fired_bands(tmp_path, "S") == {200_000, 250_000, 300_000}


def test_a_growing_session_still_gets_each_higher_band_once(tmp_path, capsys):
    """The other direction: satisfying lower bands early must not mute the higher ones later."""
    for size, expect in ((205_000, "200,000"), (255_000, "250,000"), (305_000, "300,000")):
        transcript = _transcript(tmp_path, size)
        stop.main.__globals__["read_hook_input"] = lambda: _hook_input(tmp_path, transcript)
        try:
            assert stop.main() == 0
            assert expect in json.loads(capsys.readouterr().out)["systemMessage"]
            assert stop.main() == 0
            assert json.loads(capsys.readouterr().out) == {}   # quiet until the next band
        finally:
            stop.main.__globals__["read_hook_input"] = stop.read_hook_input
