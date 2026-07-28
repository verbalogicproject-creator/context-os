"""relay.py — the mechanical half of a cold-start handoff.

Four things are load-bearing and each has a test here:

1. the prefix read is BOUNDED — a session transcript is tens of megabytes and reading one
   whole is the anti-pattern this subcommand exists to avoid;
2. the write is ATOMIC — a torn relay is a handoff that silently lies;
3. PLACEHOLDER INTEGRITY — capture must never fill an authored slot, because a filled slot
   reads as if a session had checked it;
4. `budget` fails in BOTH directions — over the character ceiling, and on any unfilled slot.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import ctx_staleness
import relay

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "relay.py"


def _usage_line(tokens: int) -> str:
    return json.dumps({"type": "assistant", "message": {"usage": {
        "input_tokens": 2, "cache_read_input_tokens": tokens, "output_tokens": 9}}})


def _transcript(path: Path, tokens: int, padding_bytes: int = 0) -> Path:
    """A transcript whose LAST usage record is `tokens`, padded ahead of it to force a tail."""
    filler = json.dumps({"type": "user", "message": {"content": "x" * 2000}}) + "\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(_usage_line(111))  # an older turn, must lose to the newer one
        handle.write("\n")
        written = 0
        while written < padding_bytes:
            handle.write(filler)
            written += len(filler)
        handle.write(_usage_line(tokens) + "\n")
    return path


# --- 1. the bounded read -----------------------------------------------------------------


def test_prefix_reads_a_bounded_tail_not_the_whole_file(tmp_path):
    big = _transcript(tmp_path / "big.jsonl", 42_000, padding_bytes=2 * 1024 * 1024)
    size = big.stat().st_size
    assert size > relay.TAIL_STEPS[0] * 4  # the file really is bigger than the window

    tokens, read = relay.prefix_tokens(big)

    assert tokens == 42_000
    assert read <= relay.TAIL_STEPS[0]
    assert read < size


def test_tail_text_drops_the_partial_first_line(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text("first-line-would-be-cut\nsecond\nthird\n")

    text, read = relay.tail_text(path, 12)

    assert "first-line-would-be-cut" not in text
    assert read == 12


def test_prefix_takes_the_most_recent_usage(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(_usage_line(100) + "\n" + _usage_line(300) + "\n" + _usage_line(200) + "\n")

    assert relay.prefix_tokens(path)[0] == 200


def test_prefix_exits_1_when_there_is_no_usage(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text('{"type":"user","message":{"content":"hi"}}\n')

    assert relay.prefix_tokens(path)[0] is None
    assert relay.main(["prefix", str(tmp_path), "--transcript", str(path)]) == 1


def test_prefix_survives_a_corrupt_tail(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(_usage_line(500) + "\n" + '{"broken": ' + "\n")

    assert relay.prefix_tokens(path)[0] == 500


# --- 2. the atomic write -----------------------------------------------------------------


def test_capture_writes_through_the_atomic_helper(tmp_path, monkeypatch):
    calls = []
    real = relay._atomic_write
    monkeypatch.setattr(relay, "_atomic_write",
                        lambda path, text: (calls.append(path), real(path, text))[1])

    target, _ = relay.capture(tmp_path, "do the thing", "2026-07-28")

    assert calls == [target]
    assert not list(target.parent.glob(".ctxtmp-*"))  # no temp file left behind


def test_snapshot_scaffold_is_atomic_too(tmp_path, monkeypatch):
    """snapshot.py had the same bare write_text defect; it must not come back."""
    import snapshot

    calls = []
    real = ctx_staleness._atomic_write
    monkeypatch.setattr(snapshot, "_atomic_write",
                        lambda path, text: (calls.append(path), real(path, text))[1])

    snap, _ = snapshot.scaffold(tmp_path, "goal", "2026-07-28T00:00:00Z")

    assert snap in calls
    assert not list(tmp_path.glob(".ctxtmp-*"))


# --- 3. placeholder integrity ------------------------------------------------------------


def test_capture_fills_nothing_but_the_goal(tmp_path):
    target, _ = relay.capture(tmp_path, "Create scripts/relay.py", "2026-07-28")
    text = target.read_text()

    # every authored slot is present, and present as an UNFILLED placeholder
    unfilled = relay.unfilled_slots(text)
    assert len(unfilled) == len(relay.AUTHORED_SLOTS)
    for heading, _rule in relay.AUTHORED_SLOTS:
        assert f"\n{heading}\n" in text

    # the goal is the one authored value, and it lands verbatim in the scalar
    assert ctx_staleness.fm_get(text, "resume_target") == '"Create scripts/relay.py"'


def test_capture_populates_every_mechanical_field(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a.py").write_text("import os\n")

    target, _ = relay.capture(tmp_path, "goal", "2026-07-28")
    text = target.read_text()

    assert ctx_staleness.fm_get(text, "format") == "ngf/0.0.3"
    assert ctx_staleness.fm_get(text, "kind") == "relay"
    assert ctx_staleness.fm_get(text, "id") == f"relay-{tmp_path.name}"
    assert ctx_staleness.fm_get(text, "created") == '"2026-07-28"'
    assert ctx_staleness.fm_get(text, "git_branch") not in (None, "")
    assert ctx_staleness.fm_get(text, "git_dirty") in ("true", "false")
    assert ctx_staleness.fm_get(text, "maps_at_capture") == "none"
    assert ctx_staleness.fm_get(text, "previous_relay") == "none"
    # no transcript for a tmp_path project — say so, never guess a number
    assert ctx_staleness.fm_get(text, "prefix_at_capture").startswith("unknown")


def test_a_goal_with_quotes_stays_one_readable_scalar(tmp_path):
    target, _ = relay.capture(tmp_path, 'ship "relay.py"\nand    stop', "2026-07-28")

    value = ctx_staleness.fm_get(target.read_text(), "resume_target")
    assert value == '"ship \\"relay.py\\" and stop"'


def test_capture_refuses_to_overwrite_without_force(tmp_path):
    relay.capture(tmp_path, "first", "2026-07-28")

    with pytest.raises(FileExistsError):
        relay.capture(tmp_path, "second", "2026-07-28")
    assert relay.main(["capture", str(tmp_path), "--goal", "second"]) == 2
    assert "first" in (tmp_path / relay.RELAY_REL).read_text()


def test_force_names_the_relay_it_replaced(tmp_path):
    relay.capture(tmp_path, "first", "2026-07-28")

    target, _ = relay.capture(tmp_path, "second", "2026-07-28", force=True)

    text = target.read_text()
    assert ctx_staleness.fm_get(text, "previous_relay") == f"relay-{tmp_path.name}"
    assert "second" in text


def test_touched_folds_mapped_reads_and_keeps_unmapped_files(tmp_path):
    import session_log

    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "map-pkg.ngf.md").write_text("---\nid: map-pkg\n---\n")
    (tmp_path / "pkg" / "mod.py").write_text("import os\n")
    (tmp_path / "loose.py").write_text("import os\n")

    session_log.record_read(tmp_path, "s1", "Read", tmp_path / "pkg" / "mod.py")
    session_log.record_read(tmp_path, "s1", "Read", tmp_path / "loose.py")

    assert relay.touched(tmp_path, "s1") == ["loose.py", "pkg"]
    assert relay.touched(tmp_path, None) == []


# --- 4. budget, both directions ----------------------------------------------------------


def _filled(tmp_path, body: str) -> Path:
    path = tmp_path / "r.ngf.md"
    path.write_text(body)
    return path


def test_budget_passes_a_small_filled_relay(tmp_path, capsys):
    path = _filled(tmp_path, "---\nkind: relay\n---\n\n## Do not\n\n- push. it is the author's call.\n")

    assert relay.main(["budget", str(path)]) == 0
    assert f"/{relay.CHAR_CEILING} chars" in capsys.readouterr().out


def test_budget_fails_over_the_character_ceiling(tmp_path):
    path = _filled(tmp_path, "x" * (relay.CHAR_CEILING + 1))

    assert relay.budget(path)[0] == relay.CHAR_CEILING + 1
    assert relay.main(["budget", str(path)]) == 1


def test_budget_fails_on_an_unfilled_slot(tmp_path):
    path = _filled(tmp_path, f"## Do not\n\n{relay.TODO_MARKER} prohibition + reason.\n")

    assert relay.main(["budget", str(path)]) == 1
    assert [n for n, _ in relay.unfilled_slots(path.read_text())] == [3]


def test_budget_ignores_a_placeholder_inside_a_fence(tmp_path):
    """A relay that documents the relay format must not fail its own check."""
    path = _filled(tmp_path, f"## Do not\n\n- nothing.\n\n```\n{relay.TODO_MARKER} example\n```\n")

    assert relay.unfilled_slots(path.read_text()) == []
    assert relay.main(["budget", str(path)]) == 0


def test_budget_ceiling_is_characters_not_an_estimate(tmp_path):
    """The ceiling is exact by construction — no tokeniser, no bytes/4."""
    body = "é" * 100  # multi-byte: a byte count would disagree with a character count
    path = _filled(tmp_path, body)

    assert relay.budget(path)[0] == 100


# --- the freshly captured scaffold is itself unfilled, and small -------------------------


def test_a_fresh_capture_is_under_budget_but_not_yet_filled(tmp_path):
    target, _ = relay.capture(tmp_path, "goal", "2026-07-28")

    chars, unfilled = relay.budget(target)
    assert chars < relay.CHAR_CEILING
    assert len(unfilled) == len(relay.AUTHORED_SLOTS)
    assert relay.main(["budget", str(target)]) == 1


def test_cli_is_runnable_as_a_script(tmp_path):
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "capture", str(tmp_path), "--goal", "go"],
        capture_output=True, text=True,
    )

    assert out.returncode == 0
    assert (tmp_path / relay.RELAY_REL).is_file()
