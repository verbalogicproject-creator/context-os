#!/usr/bin/env python3
"""context-os Stop — warn once per band as the session's context gets expensive.

Cost is the integral of context over turns, not the size of any one read: on four measured
sessions, 61-73% of all token cost was the prefix being re-processed on every subsequent turn.
No map-layout tuning competes with that, and the only lever that resets the integral is ending
the session — so this warns while there is still a cheap turn left to write a handoff in.

Wired on the `Stop` event, which fires once at the end of an assistant turn. That cadence is
the point: `PostToolUse` would fire several times per turn for the same information.

The channel was verified live before this was built, not inferred from docs: on Claude Code
v2.1.220 a `Stop` hook's `systemMessage` is honored on its own, with no `decision: "block"`
and no re-prompt of the model. Emitting `systemMessage` alone is therefore both sufficient and
non-disruptive here.

Invariant 7 (CLAUDE.md): this makes no permission decision, and every exception is swallowed —
a crash in the monitor must never break the session.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from _common import bootstrap_import, emit, read_hook_input

bootstrap_import()

import relay  # noqa: E402
import session_log  # noqa: E402

#: Warn as the prefix crosses each of these, once each, largest first.
BANDS = (300_000, 250_000, 200_000)


def state_dir(root: Path) -> Path:
    """`.context-os/state/`, carrying its own `.gitignore` so it is never committed.

    A nested ignore file is used rather than a new pattern in `.context-os/.gitignore`, because
    `ensure_log_dir` deliberately never overwrites an existing ignore file — a project that
    installed an earlier version would otherwise start seeing this state as untracked content
    in its own repo.
    """
    directory = session_log.ensure_log_dir(root) / "state"
    directory.mkdir(parents=True, exist_ok=True)
    ignore = directory / ".gitignore"
    if not ignore.exists():
        try:
            ignore.write_text("*\n")
        except OSError:
            pass
    return directory


def _state_path(root: Path, session_id: str) -> Path:
    return state_dir(root) / f"bands-{session_log._safe(session_id)}.json"


def fired_bands(root: Path, session_id: str) -> set:
    """Bands already warned about in this session (empty on anything unreadable)."""
    try:
        data = json.loads(_state_path(root, session_id).read_text())
        return {int(b) for b in data} if isinstance(data, list) else set()
    except (OSError, ValueError, TypeError):
        return set()


def record_band(root: Path, session_id: str, band: int) -> None:
    """Mark `band` fired — and every band below it, which the session has necessarily crossed.

    Recording only the one band that fired would make the monitor speak on three consecutive
    turns for a session sitting above 300k: the top band fires, then the next turn finds 250k
    still unfired and warns again, then 200k. Crossing a threshold means the lower ones were
    crossed too, so they are satisfied at the same time.
    """
    fired = fired_bands(root, session_id) | {b for b in BANDS if b <= band}
    try:
        _state_path(root, session_id).write_text(json.dumps(sorted(fired)))
    except OSError:
        pass  # a monitor that cannot persist must still not break the session


def band_for(prefix: int, already: set):
    """The highest band `prefix` has crossed that has not fired yet, or None.

    Highest-first so a session that jumps straight past several bands reports the one it is
    actually in, rather than warning about a threshold it left long ago.
    """
    for band in BANDS:
        if prefix >= band and band not in already:
            return band
    return None


def message(band: int, prefix: int) -> str:
    """Plain English, no jargon — this is user-facing copy (CLAUDE.md)."""
    return (
        f"context-os: this session is now re-reading about {prefix:,} tokens of conversation "
        f"on every message you send (past {band:,}). That cost repeats per message and only "
        f"goes up. A good moment to run /relay and start fresh — it writes the handoff while "
        f"there is still room to write it in."
    )


def main() -> int:
    nudge = None
    try:
        hook_input = read_hook_input()
        transcript = hook_input.get("transcript_path")
        session_id = str(hook_input.get("session_id", "unknown"))
        if transcript:
            path = Path(transcript)
            if path.is_file():
                # Bounded tail, never the whole file — a real transcript reached 53 MB.
                prefix, _ = relay.prefix_tokens(path)
                if prefix is not None:
                    root = Path(hook_input.get("cwd") or Path.cwd())
                    already = fired_bands(root, session_id)
                    band = band_for(prefix, already)
                    if band is not None:
                        record_band(root, session_id, band)
                        nudge = message(band, prefix)
    except Exception:
        nudge = None  # invariant 7: the monitor never breaks the session

    emit({"systemMessage": nudge} if nudge else {})
    return 0


if __name__ == "__main__":
    sys.exit(main())
