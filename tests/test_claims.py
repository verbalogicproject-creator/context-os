"""Public copy must not present a saving it cannot defend (CLAUDE.md invariant 6).

The delivered map-consultation rate has never been collected and published, and before 0.7.0
the instrument that produces it under-reported. So the defensible claim is the cost
*mechanism* — context is re-processed every turn, 61-73% of spend on four measured sessions —
never a token saving. This is a copy gate: the failure mode is a confident number drifting
back into the README months from now, and prose has no other test.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SURFACES = ["README.md", "HOW-TO-USE.md"]


def _texts():
    return [(name, (ROOT / name).read_text()) for name in SURFACES if (ROOT / name).is_file()]


def test_the_ceiling_is_never_presented_as_tokens_saved():
    """Every percentage that describes the map set must be marked as a ceiling/upper bound
    near where it appears, not left to read as a realized saving."""
    for name, text in _texts():
        for match in re.finditer(r"(\d{2,3})% smaller", text):
            window = text[max(0, match.start() - 400): match.end() + 400].lower()
            assert any(w in window for w in ("ceiling", "upper bound", "most a")), \
                f"{name}: '{match.group(0)}' is not marked as a ceiling"


def test_the_delivered_number_is_disclosed_as_having_no_result_yet():
    """The honest gap: the instrument exists, the evidence does not."""
    for name, text in _texts():
        low = text.lower()
        assert "map-consultation rate" in low, f"{name}: delivered number not described"
        assert ("no result yet" in low or "no delivered rate has been collected" in low
                or "no published result yet" in low), \
            f"{name}: does not disclose that the delivered rate has no result yet"


def test_pre_0_7_0_ledgers_are_marked_untrustworthy():
    """A defect that silently under-reported is worse than no meter, so it is disclosed rather
    than quietly fixed — anyone holding an old ledger must be told to discard it."""
    for name, text in _texts():
        low = text.lower()
        assert "0.7.0" in low and ("discard" in low or "thrown away" in low), \
            f"{name}: no guidance to discard ledgers from before the meter fix"


def test_no_unqualified_savings_claim_in_the_plugin_description():
    """The marketplace description is the one surface a user reads before installing."""
    desc = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())["description"].lower()
    for banned in ("guaranteed saving", "saves you money", "cuts your bill",
                   "proven saving", "reduces your costs by"):
        assert banned not in desc, banned
    # the ceiling may be mentioned, but never as a delivered figure
    for match in re.finditer(r"(\d{2,3})% (?:fewer|less|smaller|reduction|saving)", desc):
        window = desc[max(0, match.start() - 200): match.end() + 200]
        assert any(w in window for w in ("ceiling", "upper bound", "most a")), \
            f"plugin.json: '{match.group(0)}' reads as a delivered saving"
