---
format: ngf/0.0.3
kind: relay
id: relay-context-os
created: "2026-07-28"
resume_target: "Create scripts/relay.py with three subcommands: capture, budget, prefix."
git_branch: main
git_head: b81a648632b6578ae1fed80b904eaf4a585a64fc
git_dirty: false
prefix_at_capture: 351175        # tokens
touched:
  - scripts/ctx_staleness.py
  - CODEBASE-REPORT.md
  - .gitignore
  - docs/00-mental-model.md … docs/07-snapshot-cold-resume.md
maps_at_capture: none            # this repo is the tool; demo/ holds the example maps
previous_relay: none
---

# Start here

Everything needed to begin is in this file. The two files under **Read first** are the only
ones you must open before writing code; the ones under **Reuse** you open as you need them.
Do not go exploring beyond this list — if something seems missing, it is a defect in this
relay, so say so rather than searching for it.

## Resume target — the one next action

**Create `/root/projects/context-os/scripts/relay.py`** — the mechanical half of relay
capture. Stdlib only. Three subcommands:

| subcommand | behaviour | exit |
|---|---|---|
| `capture <root> --goal "…"` | write `<root>/.context-os/relay.ngf.md` — mechanical fields from real sources, authored slots as literal placeholders | 0 |
| `budget <file>` | print `chars/ceiling`; **ceiling is 16000 characters** | 1 if over |
| `prefix <root>` | print the current context prefix in tokens | 1 if no usage found |

**`--goal` is the one authored value `capture` may write**: it goes verbatim into the
`resume_target` frontmatter scalar. Every other authored slot gets a `TODO(relay):` line.
**If the target file already exists, `capture` refuses with exit 2 unless `--force`**, and on
`--force` it sets `previous_relay` to the replaced file's `id` before overwriting. Without
that refusal, done-criterion 1 run as written would destroy this very file.

This is Plan #13 Phase 1. Phase 0 is done: this file exists and cleared its gate at 8/10.

## The relay format — inline, because it is what you are building

**Do not go to the plan file for this table.** The plan lives outside the repo at
`/root/.claude/plans/` and is not covered by `git_head`, so it can drift without detection.
This section is authoritative.

**MECHANICAL — `relay.py` writes these, no model involved:**

| field | source |
|---|---|
| `git_branch` `git_head` `git_dirty` | `scripts/snapshot.py:42 git_state` — reuse as-is |
| `maps_at_capture` | `scripts/snapshot.py:50 map_hashes` — reuse as-is |
| `touched` | `scripts/session_log.py:118 reads` + the owner-fold at `scripts/measure.py:283` |
| `prefix_at_capture` | last `message.usage.cache_read_input_tokens`, bounded tail |
| `created` `id` `kind` `format` `previous_relay` | trivial |

**AUTHORED — the main session writes these; `relay.py` emits placeholders only:**

| slot | rule |
|---|---|
| `resume_target` | frontmatter scalar. **Exactly one** concrete action. |
| `## Done when` | numbered acceptance criteria, one per subcommand or deliverable |
| `## Do not` | prohibition **+ its reason**, one line each |
| `## Decisions locked` | each with decider and why |
| `## Open` | question + which phase it blocks + a fallback if there is one |
| `## Verify` | command → **expected output** |
| `## Pointers` | every entry a real path |

**Placeholder syntax** — `capture` writes exactly this for each authored slot. A slot counts
as unfilled when a line, **outside any fenced block**, begins with `TODO(relay):` after
stripping whitespace. The fence exemption is required: this very file documents the syntax
below and must not fail its own budget check.

```
## Do not
TODO(relay): prohibition + reason, one line each. Delete this line when filled.
```

## Done when

Phase 1 is complete when **all six** hold:

1. `python3 scripts/relay.py capture . --goal "test"` writes `.context-os/relay.ngf.md` with
   every mechanical field above populated from its real source, and every authored slot
   present as a `TODO(relay)` line. It must never invent an authored value.
2. `python3 scripts/relay.py prefix .` prints a token count in **under 1 second**, reading a
   bounded tail. Benchmark against the live transcript named in Pointers below.
3. `python3 scripts/relay.py budget <file>` exits 1 above 16000 chars, or when any line
   outside a fenced block begins with `TODO(relay):`; 0 otherwise. **This file must pass** —
   it mentions the marker four times, all either in prose or inside a fence.
4. The write goes through `ctx_staleness._atomic_write`. **And `scripts/snapshot.py:114`'s
   bare `write_text` is converted to it too** — same defect, same fix, do not leave it.
5. `.gitignore` gains `.context-os/relay.ngf.md`; commit that one-line change (committing
   `.gitignore` is fine — committing a *relay* is what is forbidden). `git status --porcelain`
   is empty afterwards. Until then it reports `?? .context-os/`, which is expected.
6. `python3 -m pytest tests/ -q` green, with **new tests covering at least**: the bounded
   read never loads the whole file, the atomic write, placeholder integrity (no authored slot
   silently filled), and `budget` failing in both directions. 126 pass today.

## Do not

- **Do not read the whole transcript to get the prefix.** The live one is 51 MB, the largest
  on this machine is 108 MB, `/root/.claude/projects` totals 493 MB.
  `/root/.claude/plugins/marketplaces/claude-plugins-official/plugins/hookify/core/rule_engine.py:209`
  does a full `f.read()` into memory — that is the anti-pattern. Seek to the last ~256 KB and
  scan backwards for the most recent `message.usage.cache_read_input_tokens`. Measured 0.24 s.
- **Do not add a third-party import.** `scripts/` is stdlib-only (CLAUDE.md invariant 1),
  including no YAML — frontmatter is line-based via `ctx_staleness.fm_get`/`fm_set`.
- **Do not estimate tokens for `budget`.** The ceiling is in **characters** on purpose: it is
  exact, needs no tokeniser, and avoids repeating the `bytes/4` mistake this repo already
  corrected once. The token figure is a human convenience only.
- **Do not have a subagent write the authored half.** A subagent cannot see the conversation;
  `commands/snapshot.md:13-15` establishes the rule for the same reason.
- **Do not commit a relay by default.** It carries conversation state and is far likelier to
  hold a secret than a map is. Criterion 5 gitignores it; `--commit` stays deliberate.
- **Do not write a new git or map-hash helper.** Two already exist; see the format table.
- **Do not trust that `PostCompact` exists.** It is absent from the official hook validator's
  event list and zero hooks on this machine use it. Phase 4's problem, not Phase 1's.

## Decisions locked (do not relitigate)

Eyal decided all four on 2026-07-28 via AskUserQuestion; the first three were the
recommended options. Ask him if one needs reopening.

| # | decision | why |
|---|---|---|
| 1 | relay lives **inside context-os** and replaces `/snapshot` | `/snapshot` has **zero instantiations** on this machine — designed, never used. relay reuses its mechanical half. |
| 2 | the cold-read gate **blocks**, with an explicit `--force` | it scored the best existing handoff 4/10 and found a missing half-mandate; an advisory gate on a fear-removal product is no gate |
| 3 | **local by default**, `--commit` deliberate | conversation state ≠ map content |
| 4 | one format, three resume targets | plan→implement / continuation / in-the-spot differ only in `resume_target` |

## State you inherit — checkable, not asserted

- `context-os` at **`main`, clean**, 126 tests passing, `scripts/` = 12 files / 4,139 lines.
- The three security defects found by the Scientifix council are fixed and committed
  (secrets-in-maps, MCP path traversal, non-atomic CLAUDE.md write), plus CRLF preservation.
- `.context-os/` did not exist before this relay; this file created it. **It is not yet
  gitignored** — `.gitignore:37` covers only `.context-os/reads-*.jsonl`. Fixing that is
  done-criterion 5.
- Nothing is mid-edit. Phase 0 stopped deliberately at a phase boundary, with the session
  prefix at 351k — above the 300k band this project's own measurements flag as expensive.

## Open — answer or explicitly defer

1. **Does `relay` join `audit.py check`?** `snapshot.ngf.md` sits outside it entirely
   (`scripts/audit.py:346 find_map_files` globs only `map-*.ngf.md` + `index.ngf.md`). A relay
   carries model-written prose, so `check_maps_injection` is the relevant gate, not the
   fabrication one. **Blocks Phase 5.** Decide it; do not let it lapse.
2. **Can a `Stop` hook emit `systemMessage` alone?** Every local example pairs it with
   `decision:"block"`, which re-prompts the model and is not wanted. **Blocks Phase 3.**
   Fallback: a throttled `PostToolUse`.
3. **Is the 16000-character ceiling right?** It is a first calibration — this file is ~11,000.
   Revisit once three real relays exist. Not blocking.
4. **The gate's isolation leaks.** Both cold-read runs disclosed that the harness injected
   `/root/projects/context-os/CLAUDE.md` unrequested — one of the two "read first" pointers.
   So this file's 8/10 was scored under slightly easier conditions than a true cold start.
   Phase 2 should pin what `relay-cold-reader` is allowed to receive, and re-score. **Blocks
   trusting any future score, not Phase 1.**

## Verify — command → expected output

```bash
cd /root/projects/context-os
git rev-parse HEAD          # → b81a648632b6578ae1fed80b904eaf4a585a64fc (or later)
git status --porcelain      # → "?? .context-os/" — this relay is untracked and not yet
                            #   ignored. Empty only AFTER done-criterion 5 lands.
python3 -m pytest tests/ -q # → "126 passed" today; must only go up
python3 scripts/audit.py check demo
   # → PASS: derive-don't-fabricate — 8 node(s) checked (1 external-exempt), 0 unbacked
   # → PASS: no instruction-shaped text in the map set
python3 scripts/ctx_staleness.py status demo
   # → "2 map(s), 0 drifted", exit 0
```

## Pointers — every one a real path

**Read first (these two, before writing code):**

- `/root/projects/context-os/CLAUDE.md` — the nine invariants any change must respect.
- `/root/projects/context-os/SPEC.md` §4 — the `snapshot` kind relay supersedes. Needed
  *before* designing `capture`'s output, not after.

**Reuse, do not rewrite:**

- `scripts/snapshot.py:42 git_state` · `scripts/snapshot.py:50 map_hashes` · `:114` the defect
- `scripts/session_log.py:118 reads` — the per-session read ledger primitive
- `scripts/measure.py:283` — ledger entries → touched folders
- `scripts/measure.py:189 usage_totals` — the only existing reader of `message.usage`
- `scripts/ctx_staleness.py:47 _atomic_write` · `:134 fm_get` · `:148 fm_set`
- `scripts/retrieve.py:262 contain` — path containment, if relay takes a path argument
- `tests/conftest.py` — the whole harness: `scripts/` on `sys.path`, no packaging step

**The live transcript** (for done-criterion 2's benchmark):
`/root/.claude/projects/-root-projects/89cde0bf-cfc3-4a9c-aa98-1a566c1e9f29.jsonl` — 51 MB.
The directory name is the project cwd with `/` replaced by `-`.

**Optional context:**

- `/root/projects/future-session-1-resume-2026-07-27.ngf.md` — the doc the cold-read test
  scored 4/10. Read it to see what this format corrects.
- `/root/.claude/plans/glowing-hugging-karp.md` — Plan #13, for phases 2–5. **Not needed for
  Phase 1**, and not covered by `git_head`, so prefer this file where they disagree.
