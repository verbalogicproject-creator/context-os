"""Real token usage from a transcript — the delivered number stops being an estimate.

Every other figure in `measure.py` is `bytes/4`. Claude Code records the real `usage` on
every assistant turn, so the delivered number never had to be a guess; nothing read it.
"""

import json

import measure


def _transcript(tmp_path, turns):
    """Write a minimal Claude Code-shaped .jsonl carrying `turns` usage blocks."""
    path = tmp_path / "session.jsonl"
    lines = []
    for usage in turns:
        lines.append(json.dumps({"type": "assistant", "message": {"role": "assistant", "usage": usage}}))
    path.write_text("\n".join(lines) + "\n")
    return path


def test_usage_totals_sums_every_class(tmp_path):
    path = _transcript(tmp_path, [
        {"input_tokens": 10, "cache_creation_input_tokens": 100,
         "cache_read_input_tokens": 1000, "output_tokens": 5},
        {"input_tokens": 20, "cache_creation_input_tokens": 200,
         "cache_read_input_tokens": 2000, "output_tokens": 15},
    ])
    totals = measure.usage_totals(path.read_text())
    assert totals["turns"] == 2
    assert totals["input_tokens"] == 30
    assert totals["cache_creation_input_tokens"] == 300
    assert totals["cache_read_input_tokens"] == 3000
    assert totals["output_tokens"] == 20


def test_usage_totals_skips_lines_without_usage(tmp_path):
    path = tmp_path / "s.jsonl"
    path.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "hi"}}) + "\n"
        + "not json at all\n"
        + json.dumps({"type": "assistant", "message": {"usage": {"output_tokens": 7}}}) + "\n"
    )
    totals = measure.usage_totals(path.read_text())
    assert totals["turns"] == 1
    assert totals["output_tokens"] == 7


def test_usage_totals_on_empty_transcript():
    totals = measure.usage_totals("")
    assert totals["turns"] == 0
    assert all(totals[k] == 0 for k in measure.WEIGHTS)


def test_cost_profile_shares_sum_to_one(tmp_path):
    path = _transcript(tmp_path, [
        {"input_tokens": 100, "cache_creation_input_tokens": 100,
         "cache_read_input_tokens": 100, "output_tokens": 100},
    ])
    profile = measure.cost_profile(measure.usage_totals(path.read_text()))
    # shares are rounded to 4dp for display, so they sum to 1 only within rounding error
    assert abs(sum(profile["weighted_share"].values()) - 1.0) < 1e-3


def test_cost_profile_weights_match_the_published_ratios(tmp_path):
    """Equal token counts, so each share is just that class's weight over the total."""
    path = _transcript(tmp_path, [
        {"input_tokens": 100, "cache_creation_input_tokens": 100,
         "cache_read_input_tokens": 100, "output_tokens": 100},
    ])
    share = measure.cost_profile(measure.usage_totals(path.read_text()))["weighted_share"]
    total_weight = sum(measure.WEIGHTS.values())  # 1.0 + 1.25 + 0.1 + 5.0
    assert abs(share["output_tokens"] - 5.0 / total_weight) < 1e-4
    assert abs(share["cache_read_input_tokens"] - 0.1 / total_weight) < 1e-4
    # output dominates at equal counts — which is why cache_read only wins by VOLUME
    assert share["output_tokens"] > share["cache_read_input_tokens"]


def test_mean_prefix_is_cache_read_per_turn(tmp_path):
    path = _transcript(tmp_path, [
        {"cache_read_input_tokens": 1000},
        {"cache_read_input_tokens": 3000},
    ])
    profile = measure.cost_profile(measure.usage_totals(path.read_text()))
    assert profile["mean_prefix_tokens"] == 2000


def test_context_tax_grows_with_remaining_turns():
    """The point of the whole function: a read is not a one-time charge."""
    early = measure.context_tax(30_000, turns_remaining=5_000)
    late = measure.context_tax(30_000, turns_remaining=10)
    assert early["cache_read_tokens"] == 30_000 * 5_000
    assert early["weighted_cost"] > late["weighted_cost"]
    # admitted early, it costs hundreds of times its apparent size
    assert early["multiple_of_naive"] > 100
    # admitted late, it costs about what it looks like
    assert late["multiple_of_naive"] < 5


def test_context_tax_at_zero_remaining_turns_is_just_the_write():
    tax = measure.context_tax(1000, turns_remaining=0)
    assert tax["cache_read_tokens"] == 0
    assert tax["multiple_of_naive"] == measure.WEIGHTS["cache_creation_input_tokens"]


def test_cost_cli_reports_and_exits_zero(tmp_path, capsys):
    path = _transcript(tmp_path, [
        {"input_tokens": 1, "cache_creation_input_tokens": 10,
         "cache_read_input_tokens": 1000, "output_tokens": 5},
    ])
    assert measure.main(["cost", str(path)]) == 0
    out = capsys.readouterr().out
    assert "cache read" in out
    assert "mean prefix re-processed per turn" in out


def test_cost_cli_json_and_at_turn(tmp_path, capsys):
    path = _transcript(tmp_path, [{"cache_read_input_tokens": 100} for _ in range(50)])
    assert measure.main(["cost", str(path), "--json", "--at-turn", "10", "--tokens", "1000"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["turns"] == 50
    assert payload["context_tax"]["turns_remaining"] == 40
    assert payload["context_tax"]["cache_read_tokens"] == 40_000


def test_cost_cli_fails_loudly_on_a_transcript_with_no_usage(tmp_path, capsys):
    """A wrong zero is worse than an error for a user who cannot check."""
    path = tmp_path / "empty.jsonl"
    path.write_text('{"type": "user"}\n')
    assert measure.main(["cost", str(path)]) == 1
    assert "no usage data" in capsys.readouterr().err
