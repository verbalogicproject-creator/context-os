---
description: Write a handoff file before this session ends — the one next action, what done looks like, and what not to redo — then have a fresh reader check it can actually be resumed from
argument-hint: "[the one next action] (optional — inferred from this session if omitted)"
---

# /relay

Leave behind a file the next session can start from cold, without asking you anything.

A relay is one page: the single next action, what "done" looks like for it, the decisions
already settled, the things not to redo, and the real paths to reuse. A fresh session reads
it and picks the work straight up — on this machine or another, in Claude, Codex or Gemini.

**You run this yourself, in this conversation** (not through a subagent) — half of a relay
can only be written from *this session's context*, and a subagent cannot see it. Everything a
script can establish on its own, the script writes; everything else, you write.

**The check matters more than the file.** A handoff can only be repaired while the context
that would repair it still exists. So the last step sends the relay to a reader with no prior
knowledge, and if that reader cannot resume from it, you fix it now — not next time.

## Request

$ARGUMENTS

## Protocol

Everywhere below, `${CLAUDE_PLUGIN_ROOT}` is this plugin's directory.

1. **Resolve the project root** (current working directory unless the repo root is obviously
   elsewhere). Derive the **one next action** from this session — one concrete thing, phrased
   as a command or an edit to a named file. Not a theme, not a list.

2. **Write the mechanical half:**
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay.py" capture "<root>" --goal "<the one next action>"
   ```
   This records the git state, each map's hash at capture, the folders this session touched,
   and the current context size — each from its real source — and leaves every part only you
   can write as a placeholder line.

   **If a relay already exists it refuses, and exits 2.** That is deliberate: the file it
   would replace is the previous session's only handoff. Show the user the refusal, say what
   would be overwritten, and only re-run with `--force` once they choose it. `--force` records
   the replaced relay's id so nothing disappears silently. **Never pass `--force` on your own.**

3. **Write the half only you have** — `Edit` the file and replace every placeholder line:
   - **`## Done when`** — numbered acceptance criteria, one per deliverable. A cold reader
     must be able to tell, without asking, whether each one is met.
   - **`## Do not`** — each prohibition **with its reason**. A rule with no reason gets
     re-litigated by the next session, which is exactly the cost this file exists to avoid.
   - **`## Decisions locked`** — each with who decided it and why.
   - **`## Open`** — each question, which phase or deliverable it blocks, and a fallback if
     there is one.
   - **`## Verify`** — commands **with their expected output**. A command with no expected
     output cannot be checked by someone who has never seen it pass.
   - **`## Pointers`** — real paths only. Flag anything that lives outside the repo, since it
     can change without the repo's history showing it.

   Say what actually happened, including what failed or was left unfinished. A relay that
   overstates progress makes the next session worse, not better.

4. **Check the size and that nothing was left blank:**
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay.py" budget "<root>/.context-os/relay.ngf.md"
   ```
   Exits 1 while any placeholder remains, or above the character ceiling. Fix and re-run
   until it exits 0. **Do not proceed past a failing budget check.**

5. **Run the cold-read check.** Dispatch **one** `context-os:relay-cold-reader` agent. Give it
   the relay's absolute path and **nothing else** — no summary of this session, no background,
   no "here's what we were doing". Anything extra you tell it invalidates the result, because
   the whole test is whether the *file* carries the work.

   Save its report, then:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/relay.py" gate "<report-file>"
   ```
   It exits 0 only when the reader scored **8/10 or better**.

6. **If the gate fails, fix the relay and re-run steps 4-5.** The reader names what is
   missing; add exactly that. Do not argue with the score and do not carry on regardless —
   below 8/10 means a fresh session would have to come back and ask you, and after this
   session ends there is no one to ask.

   If the reader reports **contaminated** isolation, that is a finding about the harness, not
   about the relay: it was handed files it was never given, so it did not read as coldly as
   the test assumes. This has happened on every run so far, so it does **not** fail the gate —
   it makes the number **provisional**. Report it that way, and name what leaked in. Never
   present a provisional score as a clean one.

7. **Report** the relay's path, the score, and anything still open in it. A relay stays local
   by default — it carries conversation state, so it is likelier to hold something private
   than a map is. Committing one is a deliberate, per-case choice, never automatic.

## Honesty

The gate is only worth having if it can fail. If the relay scores below 8, say so plainly and
fix it — never round a 7 up because the file looks thorough. Length is not sufficiency: the
worst handoff measured so far was longer than the best one.
