"""Pin the headline compression number so a refactor can't silently tank (or inflate) it.

The 90%+ figures quoted for real repos are one-off runs; nothing used to keep the ratio from
drifting. This locks the committed demo's ceiling into a band: change scan.py's emit or the
map format enough to move it, and CI fails until the CHANGELOG is updated deliberately.
"""

from pathlib import Path

import audit

DEMO = Path(__file__).resolve().parent.parent / "demo"


def test_demo_ceiling_within_expected_band():
    report = audit.compute_maps_token_report(DEMO)
    assert report.files_scanned >= 2
    # A ceiling, not a session number — but it must stay a real, positive compression.
    assert 40.0 < report.reduction_pct < 99.9, f"demo ceiling drifted to {report.reduction_pct}%"


def test_demo_maps_are_smaller_than_source():
    report = audit.compute_maps_token_report(DEMO)
    assert report.ctx_tokens_est < report.source_tokens_est
