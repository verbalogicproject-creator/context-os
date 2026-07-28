#!/usr/bin/env python3
"""Scaffold a session relay (`.context-os/relay.ngf.md`) — the cold-start handoff.

A relay is what a session leaves behind so the next one can resume without re-deriving
anything: one concrete next action, the acceptance criteria for it, the prohibitions and
decisions that are already settled, and the real paths to reuse. It is the episodic
sibling of a map, and it supersedes `snapshot` (SPEC.md §4) — same mechanical half, but
built around a single resume target rather than a narrative.

This helper does the MECHANICAL half only, and deliberately nothing else:

    MECHANICAL (written here, from a real source)   AUTHORED (placeholder only)
    ---------------------------------------------   ---------------------------
    git_branch / git_head / git_dirty                resume_target  (except --goal)
    maps_at_capture                                  ## Done when
    touched                                          ## Do not
    prefix_at_capture                                ## Decisions locked
    created / id / kind / format / previous_relay    ## Open · ## Verify · ## Pointers

The authored half must be written by the agent that HOLDS the conversation — a subagent
cannot see it (the same rule `commands/snapshot.md` states for the same reason). So every
authored slot is emitted as a literal `TODO(relay):` line and `budget` fails while any
remains, rather than this script inventing a value that would read as if a session had
checked it.

Usage:
    python3 relay.py capture <root> --goal "the one next action" [--force]
    python3 relay.py budget <file>        # chars/ceiling; exit 1 over budget or unfilled
    python3 relay.py prefix <root>        # current context prefix, in tokens
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure  # noqa: E402  (reuse the ledger owner-fold)
import session_log  # noqa: E402  (reuse the per-session read ledger)
import snapshot  # noqa: E402  (reuse git_state + map_hashes — do not write new ones)
from ctx_staleness import _atomic_write, fm_get  # noqa: E402

#: The budget ceiling is in CHARACTERS, not tokens, on purpose: it is exact, needs no
#: tokeniser (invariant 1 forbids the dependency), and avoids repeating the `bytes/4`
#: estimate this repo already corrected once. A token figure is a human convenience only.
CHAR_CEILING = 16000

#: A line that begins with this, outside a fenced block, marks an authored slot as unfilled.
#: The fence exemption is required — a relay may legitimately document this syntax.
TODO_MARKER = "TODO(relay):"

#: Bounded tail sizes for the prefix read, smallest first. A Claude Code transcript is
#: routinely tens of megabytes (51 MB live here, 108 MB largest on this machine), so it is
#: never read whole; we seek to the end and scan backwards. The escalation exists only
#: because a single transcript LINE can be large enough to fill the first window; the last
#: step is still a hard cap far below the file size.
TAIL_STEPS = (256 * 1024, 1024 * 1024, 4 * 1024 * 1024)

RELAY_REL = ".context-os/relay.ngf.md"

#: The authored slots, in the order they appear in a relay, with the rule for each.
AUTHORED_SLOTS = [
    ("## Done when", "numbered acceptance criteria, one per subcommand or deliverable."),
    ("## Do not", "prohibition + reason, one line each."),
    ("## Decisions locked", "each decision with its decider and why."),
    ("## Open", "question + which phase it blocks + a fallback if there is one."),
    ("## Verify", "command -> expected output, one pair per line."),
    ("## Pointers", "every entry a real path."),
]


# ---------------------------------------------------------------------------
# prefix — the current context size, from a bounded tail of the session transcript
# ---------------------------------------------------------------------------


def _project_transcript_dir(path: Path) -> Path:
    """Claude Code's transcript directory for a project cwd (`/` and `.` become `-`)."""
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(path))


def find_transcript(root: Path) -> Optional[Path]:
    """The most recently written session transcript for `root` or any parent of it.

    A session's transcript lives under the directory for its CWD, which is often an
    ANCESTOR of the repo being captured (running Claude Code from `/root/projects` while
    working in `/root/projects/context-os`). So the chain is searched, and the newest
    file across it wins — mtime is what identifies the live session, not path depth.
    The chosen path is reported by the CLI so the number stays checkable.
    """
    root = root.resolve()
    candidates: List[Path] = []
    for parent in [root, *root.parents]:
        directory = _project_transcript_dir(parent)
        if directory.is_dir():
            candidates.extend(p for p in directory.glob("*.jsonl") if p.is_file())
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def tail_text(path: Path, max_bytes: int) -> Tuple[str, int]:
    """Read at most the last `max_bytes` of `path`. Returns (text, bytes_read).

    A partial first line is discarded when the read did not start at byte 0, so every
    line handed to the caller is a complete JSON record.
    """
    size = path.stat().st_size
    offset = max(0, size - max_bytes)
    with open(path, "rb") as handle:
        handle.seek(offset)
        raw = handle.read()
    text = raw.decode("utf-8", errors="ignore")
    if offset > 0:
        newline = text.find("\n")
        text = text[newline + 1:] if newline != -1 else ""
    return text, len(raw)


def _prefix_in(text: str) -> Optional[int]:
    """The most recent `message.usage.cache_read_input_tokens` in `text`, scanning back."""
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line or "cache_read_input_tokens" not in line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = obj.get("message") if isinstance(obj, dict) else None
        usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict):
            continue
        value = usage.get("cache_read_input_tokens")
        if isinstance(value, int) and value > 0:
            return value
    return None


def prefix_tokens(transcript: Path) -> Tuple[Optional[int], int]:
    """The session's current context prefix in tokens. Returns (tokens|None, bytes_read).

    `cache_read_input_tokens` is the prefix the API re-processed on the most recent turn —
    reported by the API itself, not estimated here (the same source `measure.usage_totals`
    reads, and the reason `measure.py` calls cost an integral over turns).
    """
    size = transcript.stat().st_size
    read_total = 0
    for window in TAIL_STEPS:
        text, read = tail_text(transcript, window)
        read_total = read
        found = _prefix_in(text)
        if found is not None:
            return found, read_total
        if window >= size:
            break
    return None, read_total


# ---------------------------------------------------------------------------
# touched — what this session actually opened, from the read ledger
# ---------------------------------------------------------------------------


def touched(root: Path, session_id: Optional[str]) -> List[str]:
    """Folders (when mapped) and files (when not) this session read, from the ledger.

    Entries that belong to a mapped folder fold up to that folder — `measure.touched_owners`
    is the same fold `/context-os-catchup` uses. Entries with no owning map cannot fold, so
    the file itself is reported. Empty when there is no ledger for this session.
    """
    if not session_id:
        return []
    out = set()
    for owner_rel in measure.touched_owners(root, session_id):
        folder = Path(owner_rel).parent.as_posix()
        out.add(folder if folder not in ("", ".") else ".")
    for entry in session_log.reads(root, session_id):
        if not entry.get("owner") and entry.get("path"):
            out.add(entry["path"])
    return sorted(out)


# ---------------------------------------------------------------------------
# capture
# ---------------------------------------------------------------------------


def _scalar(value: str) -> str:
    """A one-line, double-quoted YAML scalar — the ONLY authored text capture writes."""
    flat = " ".join(str(value).split())
    return '"' + flat.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(
    root: Path,
    goal: str,
    now: str,
    prefix: Optional[int],
    previous_relay: str,
    session_id: Optional[str],
) -> str:
    git = snapshot.git_state(root)
    maps = snapshot.map_hashes(root)
    files = touched(root, session_id)

    lines = [
        "---",
        "format: ngf/0.0.3",
        "kind: relay",
        f"id: relay-{root.name}",
        f'created: "{now}"',
        f"resume_target: {_scalar(goal)}",
        f"git_branch: {git['branch']}",
        f"git_head: {git['head']}",
        f"git_dirty: {str(git['dirty']).lower()}",
        f"prefix_at_capture: {prefix}        # tokens" if prefix is not None
        else "prefix_at_capture: unknown       # no session transcript found",
    ]
    if files:
        lines.append("touched:")
        lines.extend(f"  - {item}" for item in files)
    else:
        lines.append("touched: none")
    if maps:
        lines.append("maps_at_capture:")
        lines.extend(
            f"  - {{path: {rel}, structural_hash: {structural_hash}, staleness: {staleness}}}"
            for rel, structural_hash, staleness in maps
        )
    else:
        lines.append("maps_at_capture: none")
    lines += [
        f"previous_relay: {previous_relay}",
        "---",
        "",
        "# Start here",
        "",
        "Everything needed to begin is in this file. Fill every `TODO(relay):` line below from",
        "the conversation that is capturing this relay — a later session cannot recover what",
        "only this one knows. `relay.py budget` fails while any of them remains.",
        "",
        "## Resume target — the one next action",
        "",
        goal.strip(),
        "",
    ]
    for heading, rule in AUTHORED_SLOTS:
        lines += [heading, "", f"{TODO_MARKER} {rule} Delete this line when filled.", ""]
    return "\n".join(lines)


def capture(
    root: Path,
    goal: str,
    now: str,
    force: bool = False,
    session_id: Optional[str] = None,
    transcript: Optional[Path] = None,
) -> Tuple[Path, Optional[int]]:
    """Write `<root>/.context-os/relay.ngf.md`. Raises FileExistsError unless `force`."""
    target = root / RELAY_REL
    previous_relay = "none"
    if target.exists():
        if not force:
            raise FileExistsError(target)
        # Overwriting is destructive and the replaced relay may be the only record of a
        # prior handoff, so name it rather than dropping it silently.
        previous_relay = fm_get(target.read_text(errors="ignore"), "id") or "unknown"

    transcript = transcript or find_transcript(root)
    prefix = prefix_tokens(transcript)[0] if transcript and transcript.is_file() else None
    if session_id is None:
        session_id = session_log.latest_session_id(root)

    target.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(target, render(root, goal, now, prefix, previous_relay, session_id))
    return target, prefix


# ---------------------------------------------------------------------------
# budget
# ---------------------------------------------------------------------------


def unfilled_slots(text: str) -> List[Tuple[int, str]]:
    """Line numbers of unfilled authored slots — `TODO(relay):` lines OUTSIDE any fence.

    The fence exemption is not a convenience: a relay whose subject is the relay format
    itself must be able to show the placeholder syntax without failing its own check.
    """
    out: List[Tuple[int, str]] = []
    in_fence = False
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if not in_fence and stripped.startswith(TODO_MARKER):
            out.append((number, stripped))
    return out


def budget(path: Path) -> Tuple[int, List[Tuple[int, str]]]:
    """Returns (characters, unfilled slots). Over budget or unfilled → the caller exits 1."""
    text = path.read_text(errors="ignore")
    return len(text), unfilled_slots(text)


# ---------------------------------------------------------------------------
# gate — read the cold-reader's verdict; the judgement is a model call, this is not
# ---------------------------------------------------------------------------

#: The pass mark. A relay that scores below this is fixed and re-scored while the session
#: that could fix it still exists — after it ends, the context is gone and the gate is moot.
PASS_MARK = 8

_SCORE_RE = re.compile(r"^SCORE:\s*(\d+)\s*/\s*10\s*$", re.MULTILINE)
_ISOLATION_RE = re.compile(r"^ISOLATION:\s*(clean|contaminated)\b(.*)$", re.MULTILINE)


def parse_gate_report(text: str) -> dict:
    """Pull the two machine-readable lines out of a `relay-cold-reader` report.

    The score itself is a judgement only a model can make — this parses it, it does not
    reproduce it. Both lines are REQUIRED: a report missing either is treated as a failed
    run, never as a pass, because an unparseable verdict read as "fine" is the one failure
    mode that would quietly disable the gate.

    `isolation` is carried beside the score, and NOT folded into the pass/fail. Measured
    3 runs out of 3: the harness injects the project's CLAUDE.md — and the user's memory
    index, and an agent-type listing — into a subagent unrequested, both before the task and
    again by system-reminder after the Read. Failing the gate on that would block every
    relay forever, on a condition the author cannot fix. So contamination makes the score
    **provisional** — reported loudly, recorded beside the number — while the pass/fail
    stays on the score, which is what the author can actually act on.
    """
    score_match = _SCORE_RE.search(text)
    isolation_match = _ISOLATION_RE.search(text)
    score = int(score_match.group(1)) if score_match else None
    isolation = isolation_match.group(1) if isolation_match else None
    return {
        "score": score,
        "isolation": isolation,
        "contamination": (isolation_match.group(2).strip(" —-") if isolation_match else ""),
        "provisional": isolation != "clean",
        "passed": score is not None and isolation is not None and score >= PASS_MARK,
        "reason": (
            "no SCORE: n/10 line in the report" if score is None
            else "no ISOLATION: line in the report" if isolation is None
            else f"scored {score}/10, below the {PASS_MARK}/10 pass mark" if score < PASS_MARK
            else ""
        ),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Capture and check a session relay.")
    sub = parser.add_subparsers(dest="mode", required=True)

    cap = sub.add_parser("capture", help="Write the mechanical half of a relay")
    cap.add_argument("root", type=Path)
    cap.add_argument("--goal", required=True, help="The one concrete next action (verbatim)")
    cap.add_argument("--force", action="store_true", help="Overwrite an existing relay")
    cap.add_argument("--now", default=None, help="ISO date (default: today, UTC)")
    cap.add_argument("--session", default=None, help="Session id (default: newest ledger)")
    cap.add_argument("--transcript", type=Path, default=None, help="Session .jsonl to read")

    bud = sub.add_parser("budget", help="Check a relay's size and whether it is filled in")
    bud.add_argument("file", type=Path)

    pre = sub.add_parser("prefix", help="Print the current context prefix, in tokens")
    pre.add_argument("root", type=Path)
    pre.add_argument("--transcript", type=Path, default=None)

    gat = sub.add_parser("gate", help="Read a cold-reader report and decide pass/fail")
    gat.add_argument("report", type=Path, help="The reader's report ('-' for stdin)")

    args = parser.parse_args(argv)

    if args.mode == "capture":
        now = args.now or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            target, prefix = capture(
                args.root.resolve(), args.goal, now,
                force=args.force, session_id=args.session, transcript=args.transcript,
            )
        except FileExistsError as exc:
            print(f"refusing to overwrite {exc.args[0]} — pass --force", file=sys.stderr)
            return 2
        print(f"captured {target}")
        if prefix is None:
            print("prefix_at_capture: unknown (no session transcript found)", file=sys.stderr)
        print(f"Next: fill the {len(AUTHORED_SLOTS)} TODO(relay) slots, then: "
              f"python3 scripts/relay.py budget {target}")
        return 0

    if args.mode == "budget":
        if not args.file.is_file():
            print(f"no such file: {args.file}", file=sys.stderr)
            return 1
        chars, unfilled = budget(args.file)
        print(f"{chars}/{CHAR_CEILING} chars")
        if chars > CHAR_CEILING:
            print(f"OVER BUDGET by {chars - CHAR_CEILING} chars — a relay is read cold, "
                  f"in full, every time", file=sys.stderr)
        for number, line in unfilled:
            print(f"unfilled slot at line {number}: {line}", file=sys.stderr)
        return 1 if (chars > CHAR_CEILING or unfilled) else 0

    if args.mode == "gate":
        text = sys.stdin.read() if str(args.report) == "-" else args.report.read_text(errors="ignore")
        verdict = parse_gate_report(text)
        print(f"score {verdict['score']}/10 · isolation {verdict['isolation']}"
              if verdict["score"] is not None else "unreadable report")
        if verdict["provisional"] and verdict["contamination"]:
            print(f"PROVISIONAL — the reader also saw: {verdict['contamination']}",
                  file=sys.stderr)
            print("  so this is not a clean cold-read score; record it as provisional",
                  file=sys.stderr)
        if verdict["passed"]:
            return 0
        print(f"GATE FAILED — {verdict['reason']}", file=sys.stderr)
        print("  fix the relay now — the context that could fix it ends with this session",
              file=sys.stderr)
        return 1

    transcript = args.transcript or find_transcript(args.root.resolve())
    if transcript is None or not transcript.is_file():
        print("no session transcript found for that root or any parent", file=sys.stderr)
        return 1
    tokens, read = prefix_tokens(transcript)
    if tokens is None:
        print(f"no usage data in the last {read:,} bytes of {transcript}", file=sys.stderr)
        return 1
    print(tokens)
    print(f"({transcript} — read {read:,} of {transcript.stat().st_size:,} bytes)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
