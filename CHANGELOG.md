# Changelog

All notable changes to context-os are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow semver.

## [Unreleased]

## [0.8.0] — 2026-07-28

Adds the context-threshold monitor, makes the scanner linear instead of quadratic, and stops
implying a saving that has never been measured.

### Changed
- **The delivered saving is now stated as having no result yet.** README and HOW-TO-USE
  described the map-consultation rate as though a number existed behind it. One does not: the
  instrument runs, but no delivered rate has ever been collected and published, so what a user
  gets is their own session rather than evidence that maps pay off in general. Both surfaces now
  say so, and both tell anyone holding a pre-0.7.0 ledger to discard it — before that release a
  session working across two repositories logged one's reads into the other's ledger and scored
  them as unmapped, always under-reporting map use. The defensible claim is the cost
  *mechanism* (context is re-processed every turn; 61-73% of spend on four measured sessions),
  never a token saving. `tests/test_claims.py` pins this as a copy gate, because prose has no
  other test and a confident number drifts back in otherwise.

### Added
- **A warning when the conversation itself becomes the cost.** Reading a file is charged once,
  but everything already in the conversation is re-processed on every message after it — on four
  measured sessions that re-processing was 61-73% of total token cost. No map-layout change
  competes with that, and the only thing that resets it is ending the session. A `Stop` hook now
  warns once as the session passes 200k / 250k / 300k tokens and points at `/relay`. Each band
  fires at most once, and crossing a high band satisfies the lower ones, so a long session is
  warned once rather than on three consecutive turns. The channel was verified live before
  anything was built — on Claude Code v2.1.220 a `Stop` hook's `systemMessage` is honored alone,
  with no `decision: "block"` and no re-prompt — so the throttled `PostToolUse` fallback was not
  needed. State lives in `.context-os/state/`, which carries its own `.gitignore`: the existing
  ignore file is deliberately never overwritten, so a new pattern there would never reach a
  project that installed an earlier version. Invariant 7 holds — no permission decision, every
  exception swallowed.

### Fixed
- **Import resolution was quadratic in repo size.** `_match_by_suffix` walked every directory
  and every file for *every* import, so the scanner slowed as the square of the tree — on the
  one code path the "works on a large repo" claim depends on. Measured on synthetic repos
  before the fix: 200 files 1.30s, 400 4.40s, 800 16.76s, 1600 67.78s, 3200 261.75s, roughly
  3.7x per doubling. Candidates are now grouped by stem once per scan (`build_stem_index`),
  which is exact rather than a heuristic: a match requires the candidate's stem to equal the
  import's last path segment, so the narrowed lookup cannot miss anything the full scan found.
  Same tree, after: 0.18s / 0.25s / 0.50s / 0.96s / 1.97s — **133x at 3,200 files, and linear**.
  Equivalence is not assumed: output was compared against the previous resolver over 17 real
  repositories (1,317 edges, including a 5,696-node tree) and both stem-collision shapes, with
  zero differences, and `_match_by_suffix` is pinned in the suite against the exhaustive scan
  it replaced.

## [0.7.0] — 2026-07-28

The meter release. Everything below was measured on this cycle rather than reasoned about,
and two of the three headline changes are a rule being *withdrawn* because the measurement
refuted it.

### Changed
- **Merging code folders is OFF by default — it measured negative.** The rule below shipped
  earlier in this cycle and was measured within the hour: on a real 17-folder project it cut the
  whole map set by 34.6%, which is the wrong metric, because a session reads the one map covering
  the folder it is in, not the set. Per folder, on identical source, **12 of 15 cost more and none
  cost less** — `services` went 95 → 634 tokens, 6.7×. Merging trades fragmentation for
  **dilution**, and the nine folders absorbed into one map averaged 125 tokens each, so the merged
  map only pays off once a task spans ~6 of them; real tasks span two or three. The default is now
  one map per folder (zero dilution, the safe prior); `--merge-max-files` turns merging on
  explicitly. Code-free docs/data folders still fold into their parent, as they always did.

### Fixed
- **A fan-out of subagents was recorded as one session.** Claude Code gives every subagent the
  `session_id` of the session that spawned it, so five parallel enrichers appeared in the ledger
  as one session that had touched all five folders. Co-access — which folders get read *together*
  — is computed from exactly that, so it was measuring the shape of the fan-out rather than of the
  task. Each entry now carries the `agent` that made it (`null` = the main session), and
  `session_log.agents()` lists the distinct actors. The field name was **observed, not assumed**:
  a probe of the live PreToolUse input on Claude Code v2.1.220 showed `agent_id` + `agent_type`
  populated only inside a subagent. (`CLAUDE_CODE_CHILD_SESSION` is deliberately unused — the
  probe found it set to `"1"` in the main session too, so it does not discriminate.) Ledgers
  written before this column keep reading as main-session entries.
- **The map nudge is now scoped per agent.** A subagent starts with its own empty context and has
  not inherited the parent's map read, so a sibling's read no longer silences it — previously the
  first reader in a fan-out suppressed the hint for every other agent, exactly when the map would
  have saved the most.
- **The read ledger scored another repo's files as unmapped.** `_rel` fell back to an absolute
  path instead of refusing when a read landed outside the root, so a session whose cwd was repo A
  logged repo B's reads into A's ledger — where `owning_map` looked for B's maps under A, found
  none, and recorded `source_unmapped` for files that have a map. Measured on one real session:
  **57 of 80 entries were foreign-root, 36 of them mis-scored**. This is the instrument the whole
  delivered-savings claim rests on, and it was under-reporting map use — the direction that looks
  usable while being wrong. Paths outside the root are now `KIND_OTHER` and never logged.

### Changed
- **A folder no longer automatically gets its own map file.** One map per folder over-fragments a
  small project — five folders holding one file each cost five reads and five headers — while one
  map for a whole repo makes every session pay for the parts it isn't touching. `plan.py` now makes
  a second, separate decision per folder: whether it earns its own file. A folder too thin to
  (no code, peripheral code, or few files that little depends on) **merges** into its nearest
  map-keeping ancestor; an import hub keeps its own card however small, because the folders
  everything imports are exactly the ones worth reading alone. Nothing is dropped — a merged
  folder's nodes move into the map that absorbed it. On a real 17-folder project this went from
  15 map files and 10 enricher calls to 6 and 5. Tune with `--merge-max-files` / `--merge-hub-in`,
  or keep the old behaviour with `--all`.
- **`--apply-fold` now runs before enrichment, not after.** A merged *code* node arrives carrying
  only its path, so the absorbing map's enricher has to see it to describe it. The folder's
  structural digest moves with it, for the same reason. (Content nodes were always safe to merge
  late — the scanner had already described them.)
- **A map's drift signature now covers the folders it absorbed.** `signature` descends into every
  descendant with no map of its own — the same set `owning_map` already resolved to that map.
  Without this, editing a merged folder would flip the parent map's hook but never change its hash,
  leaving a map that silently goes stale, which is worse than no map. For a leaf folder the hash is
  unchanged byte for byte, so baselines already committed do not drift on upgrade.

### Fixed
- **context-os left its own local artifacts untracked in your repo.** `/context-os` writes
  `.context-os/digests/` into the project it maps — scanner output, regenerable, and stale the
  moment the code moves — and nothing told git to ignore it, so every mapped project grew an
  untracked directory. `.context-os/` now carries its own `.gitignore` (`digests/`,
  `reads-*.jsonl`, `relay.ngf.md`), written on first use by whichever writer gets there first.
  git honors a nested ignore file identically, so the tool never has to edit a project's root
  `.gitignore` — someone else's file, with its own conventions. An existing one is never
  overwritten: committing a relay is a supported per-case choice, and silently reverting that
  would be the tool overruling you in your own repo. Your maps are unaffected — they live beside
  your code and are meant to be committed.
- **The injection gate failed honest maps that merely mentioned a system prompt.** `system prompt`
  was matched as a bare phrase, so an AI project's own architecture doc — "Phase 4 — Integration
  (System Prompt Injection)" — failed the gate, and a false positive on a real repo blocks a map
  that is fine. The phrase is now only instruction-shaped when it addresses the agent's own prompt
  (`your system prompt`) or acts on one (reveal / override / replace / "is now"). Found by
  dogfooding on a real project; both directions are pinned in `test_injection.py`.
- **`plan.py` counted context-os's own output.** `index.ngf.md` gave the repo root a node the moment
  the scanner ran, so a second plan on the same repo could disagree with the first — and with the
  merge rule above, that root would then absorb the whole project. Maps and the index are excluded
  from the tally now, and a test pins that the plan is the same before and after an emit.

## [0.6.0] — 2026-07-28

Two things a session could not do before: leave a handoff the next one can actually start from,
and know what its context is really costing. Plus the security work — maps are meant to be
committed, so what can reach one is now enforced in code rather than left to review.

### Added
- **`/relay` — the handoff you write before a session ends.** One page: the single next action,
  what "done" looks like, the decisions already settled, what not to redo, and the real paths to
  reuse. A fresh session reads it and picks the work straight up — on another machine, or in
  Codex or Gemini. It replaces `/snapshot`, which was built around a narrative rather than a
  next action.
- **The cold-read check, and it blocks.** The last step of `/relay` sends the file to a reader
  with no prior knowledge of the project (`relay-cold-reader`), which reads *only* that file and
  scores 0-10 whether it could resume from it. Below 8/10 you fix the relay before the session
  ends — because a handoff can only be repaired while the context that would repair it still
  exists. Measured in both directions: a real relay scored 8/10, a deliberately gutted one 2/10.
- **`scripts/relay.py`** — `capture` (writes everything a script can establish: git state, map
  hashes, folders touched, current context size — and leaves every judgement to you as a marked
  placeholder), `budget` (a 16,000-character ceiling, and fails while any placeholder remains),
  `prefix` (current context size, read from a bounded tail of the session log — never the whole
  file, which runs to tens of megabytes), `gate` (reads the cold reader's verdict).
- **`measure.py cost <transcript.jsonl>`** — real token usage, reported by the API, instead of a
  bytes/4 estimate. Across three real sessions (5,328 / 2,262 / 1,325 turns): re-reading the
  conversation so far was **61-73%** of all cost, output 14-25%, first-sight-of-new-content
  10-15%, fresh input ~0.02%. Exits 1 with a message when a log carries no usage data, rather
  than printing a confident zero.
- **`scripts/gitignore.py`** — the scanner now honours your `.gitignore`, in-process. Deliberately
  not a shell-out to `git check-ignore`: map contents must not depend on whether git is installed.
- **`docs/` chapters and `CODEBASE-REPORT.md`** — README had linked both since v0.5.0 without
  either being present.

### Changed
- **The saving is described honestly as a whole-session effect, not a startup one.** Reading a
  file is not charged once: everything already in the conversation is re-processed on every
  message after it. On a 5,328-message session, reading 30,000 tokens of source at message 100
  cost 524x its apparent size. So swapping a source read for a map read does not save you once —
  it saves you on every message that follows.
- **`SECURITY.md` states what the code enforces**, each guarantee pointing at the test that pins
  it, and names the residual risks instead of omitting them. The old policy handed the one real
  risk back to the user as "review it before you rely on it" — advice this tool's audience, by
  design, will not take.
- `snapshot.py` writes through the atomic helper, like every other map write.

### Fixed
- **A secret could reach a committed map.** `.env` was treated as an ordinary config file, so its
  key names were listed into a map; the log compressor appended 80 verbatim characters of a real
  error line, which is exactly where passwords in connection strings and tokens in URLs surface.
  The whole `.env` family is now dropped by name, and logs report severity kinds only.
- **A map could carry an instruction.** The enricher is a model reading arbitrary repo content,
  and every session reads maps *before* source — so prose surviving from a hostile README into a
  map description would act as a command, first, every session. `audit.py check` now fails on it,
  tuned for precision so ordinary architecture prose still passes.
- **Any readable file was fetchable over MCP.** `path` joins were unscoped, and `.mcp.json`
  registers the server by default. Both call sites now go through a containment check that
  returns a plain "not found", so a probe learns nothing.
- **The one file that is not regenerable was written without the atomic guard** — your CLAUDE.md.
  It also reads and writes with newlines preserved, so a CRLF-authored file no longer comes back
  as a whole-file diff.
- `ctx_staleness.py`'s usage banner omitted `status`, a working subcommand the docs and the CI
  block both use; the MCP server advertised v0.3.0 while the plugin was at 0.5.0.

## [0.5.0] — 2026-07-23

Lazy / on-demand mapping. Even mapping only the strategic folders pays for folders a given session
never opens. Now you can map the whole repo as free skeletons once, then enrich only what you touch.

### Added
- **`/context-os-catchup` — enrich only the folders you actually worked in.** Reads the per-session
  read ledger the drift hook already keeps, finds the touched folders whose map is still a bare
  skeleton, and enriches exactly those (same batched enrich + repair loop as `/context-os`). Re-run
  it any time; it never re-does an already-enriched folder. So enrichment cost tracks real use —
  pay for the ~handful you touched, not the hundreds you didn't.
- **`measure.py catchup <root>`** — lists the touched-but-skeleton folders (the catch-up set).
- **`audit.py map_is_enriched()`** — tells a bare skeleton (node description IS the file path) from
  an enriched map, so catch-up knows what still needs work.

The lazy flow: `/context-os --skeleton` (whole repo, `$0`, instant) → work → `/context-os-catchup`.

## [0.4.0] — 2026-07-23

Map what matters. Instead of blindly enriching every folder, `/context-os` now ranks folders and
enriches only the strategic ones — validated when the full ARIA run (77 folders, ~1.78M Haiku tokens,
~18 min) confirmed most of that spend went to folders a real session never reads.

### Added
- **`scripts/plan.py` — deterministic folder ranker.** From the scan graph (code files, cross-folder
  import in/out-degree, entry points — no LLM, no `tree` binary), it tiers every folder **DEEP**
  (enrich), **SKELETON** (structure-only, no enricher), or **FOLD** (pure docs/data/config). An entry
  point flags a folder `borderline` for the agent to promote rather than auto-enriching every route.
  `--deep-only` prints the enrich list; `--apply-fold` merges each FOLD folder's already-described
  content into its parent map and prunes the index (nothing vanishes — it names its `fold_into`
  parent). Tests in `test_plan.py`.
- **`/context-os` is strategic by default** (new plan step + fold step): rank → enrich only DEEP (plus
  promoted borderline) → fold content folders into parents. `--all` restores exhaustive mapping. On
  ARIA: ~40 strategic folders enriched instead of 77, and the fold took the map set 77 → 58 files.

### Changed
- The repair loop now resets a failing folder's skeleton before re-enriching (matches the validated
  repair flow: reset → re-enrich → re-check).

## [0.3.2] — 2026-07-23

Post-dogfood hardening. The v0.3.1 "measure, don't claim" work was validated by the first real
end-to-end run of the parallel Haiku enricher fan-out (ARIA-Therapeutic: 77 folders, 554 files,
Python+TS+React). The orchestration held (~86s wall-clock for a 10-folder parallel batch, ~6.8×
over serial; digest sufficed for 6/10 folders), but surfaced two first-pass Haiku error classes on
real messy code — both caught by the audit layer. This release hardens against them and makes the
orchestration self-heal.

### Added
- **Orchestrator repair loop (`audit.py repair-targets` + `/context-os` step 4).** After enrichment,
  `repair-targets` lists exactly the folders whose map has a fabricated node or a dangling edge
  (same predicates as `check`, factored into shared helpers so they can't drift); the orchestrator
  re-dispatches enrichers for only those folders, bounded to 2 rounds, so a stray Haiku slip
  self-heals instead of leaving the whole map set failing. Tests in `test_audit_ngf.py`.

### Changed
- **`agents/map-enricher.md` hardened** on the two observed failure modes: keep the scanner's
  disambiguated `dir/stem` node names verbatim (never shorten a collision name to its bare stem —
  that fabricates a node the audit can't trace), and an edge target is a node name, never prose
  (`~> chat`, not `~> chat store for messages`). Re-running the two offending ARIA folders with the
  hardened prompt produced a clean `check` PASS.

## [0.3.1] — 2026-07-23

"Measure, don't claim." A Scientifix-Council review found the savings machinery measured the
**artifact** (map size vs source size), never the **behavior** (did the agent read the map?),
and turned up two silent correctness bugs. This release closes the claim-vs-delivery gap and
fixes the bugs — same discipline mcp-triage already applies to its own payoff.

### Added
- **Per-session delivery measurement (`scripts/session_log.py` + `scripts/measure.py`).** A hook
  logs, per session, whether the agent read a **map**, re-read **source in a mapped folder**, or
  **grep/glob-explored** a mapped folder — to `.context-os/reads-<session>.jsonl`. `measure.py
  session <root>` (and `audit.py session-savings`, and `/context-os-status`) report the delivered
  map-consultation rate: what the agent actually did, not an artifact-size hypothetical. The
  ledger pattern is the one `vouch` proved live. A best-effort `measure.py transcript` reads
  Claude Code's own session `.jsonl` too. Tests in `test_measure.py`.
- **Gentle, non-blocking nudge.** When a session reaches for source (or fans out) in a folder
  whose map it hasn't read, the PreToolUse hook emits a one-line `systemMessage` pointing at the
  map — once per folder, never a permission block. Hook matcher widened to `Read|Grep|Glob`.
- **Edge advisory in `audit.py check`.** Flags an edge whose target names no node in any map
  (advisory only — never fails the node-fabrication gate; skips index→map navigation links).
- **CI band on the headline (`test_savings_band.py`).** Pins the committed demo's ceiling into a
  band so a scan/format change can't silently tank or inflate the compression number unnoticed.

### Fixed
- **`retrieve.py` silent span truncation.** Python symbols now use the stdlib `ast` (exact spans,
  incl. decorators and multi-line signatures/assignments); brace/indent languages get literal-aware,
  multi-line-signature-aware matching. A suspect span is flagged `low_confidence` instead of
  returning a confident hash over truncated text. Regression tests for Black/Prettier wrapping,
  decorators, object-literal defaults, and string-embedded braces.
- **`ctx_staleness.py` silent-corruption paths.** Map writes are now atomic (tempfile + `os.replace`),
  so an OOM/Phantom-Process-Killer kill mid-write can't corrupt a map's `---` delimiters; malformed
  frontmatter now fails loudly (`stamp` raises, `flip` returns an `unreadable` status, `stamp-all`
  reports failures) instead of silently no-op'ing; a leading BOM is tolerated.

### Changed
- **Copy: ceiling vs delivered, kept separate.** `audit.py savings` and the README now label the
  90%+ figure a **ceiling** (artifact size — the most a session *could* save) and point to the
  delivered measurement. "Never invents" is qualified to "never invents a **node**" (existence is
  gated; description accuracy and edge direction are not). mcp-triage drops the unsourced
  "~120 tokens/5 servers" figure and points users to `/context` to measure their own.

## [0.3.0] — 2026-07-22

[Headroom](https://github.com/chopratejas/headroom)'s token-saving ideas, adopted **in-domain**
(stdlib-only, no Headroom dependency). context-os is the ahead-of-time *structural* compressor;
these make it stronger and let it stack under any runtime compressor.

### Added
- **CCR — retrieve (`scripts/retrieve.py`).** The map is the compressed view; the source is the
  retrievable original. `retrieve <root> <path[:symbol]>` returns the EXACT original block (a
  whole file, or one `def`/`class`/`function`/const via best-effort symbol-span resolution) plus
  a content hash — so a reader pulls the exact original only when needed. Tests in `test_retrieve.py`.
- **MCP server (`scripts/mcp_server.py` + `.mcp.json`).** A stdlib stdio JSON-RPC server exposing
  `contextos_map(folder?)` and `contextos_retrieve(anchor)` — CCR as MCP tools, so any agent or
  proxy (including Headroom) can read the compressed maps and fetch originals. Tests in `test_mcp.py`.
- **Content-aware maps for non-code folders (`scripts/compress.py`).** config/JSON (keys+shape),
  docs (title+headings), data (columns+rows), and logs (errors/warnings) now get a deterministic
  compressed map node — so config/docs/data folders are mapped too, not just code. Skips tooling
  dot-dirs. Tests in `test_compress.py`.
- **Cache-stability hygiene (`audit.py cache-check`).** Flags volatile content (timestamps/UUIDs/
  hashes/JWTs) in the always-loaded CLAUDE.md/AGENTS.md pointer block that would bust provider
  prompt caches; the block is guaranteed byte-stable. Tests in `test_cache_check.py`.

### Changed
- The scanner (`scan.py`) now also emits non-code content nodes with their compressed views;
  `ScanNode` gains a `desc` field. The fabrication audit still gates every node.

## [0.2.0] — 2026-07-22

Generation cost optimization — prompted by the memorylog- dogfood, where the monolithic
`map-scout` spent ~410k tokens (~45% of the session) mapping 50 folders in one growing
context on a premium model.

### Added
- **`/context-os --skeleton` (`--fast`) — a free structural tier.** Runs only the deterministic
  pipeline (scan → stamp → splice → audit), no LLM: real nodes + `->` edges + drift + pointer,
  in seconds at ~$0. Skeleton maps omit descriptions and the risk card.
- **`/context-os --premium`** — runs the enrichers on Sonnet for best prose/risk quality.
- **Per-folder structural digests** (`scan.py --emit-digests`, `folder_digest()`): a file's
  leading doc + declaration signatures + imports, so an enricher writes descriptions without
  reading whole bodies. Skips license headers and local-variable noise. Tests in `tests/test_digest.py`.

### Changed
- **Sharded enrichment.** `/context-os` is now an orchestrator: scan → fan out one **`map-enricher`
  per folder in parallel** (isolated small contexts) → stamp/splice/audit. This replaces the single
  growing context — the core cost fix. New agent `agents/map-enricher.md`, `model: haiku` (the cheap
  default). `audit.py check` still gates fabrication across every shard.

### Removed
- The monolithic **`map-scout`** agent — its work is split between the command orchestrator and the
  per-folder `map-enricher`.

## [0.1.1] — 2026-07-22

Fixes from the first live enrichment run on a real Python repo.

### Fixed
- **Scanner now resolves Python relative imports** (`from .rooms import`,
  `from ..models.x import`) and **imports nested in `try/except`/functions** (indented).
  Previously these `->` edges were dropped from the skeleton and had to be repaired by
  hand during enrichment. (`scan.py`; regression tests in `tests/test_scan_imports.py`.)

### Changed
- `map-scout` agent: documented how to represent a **cross-folder `->` dependency**
  (folder-granularity `[ext]` node + edge + `depends_on`), pointing at the `demo/`
  convention — previously only `~>`/`=>` cross-boundary edges were spelled out.

## [0.1.0] — 2026-07-22

Initial release.

### Added
- **Per-folder context maps.** `scan.py --emit-ngf` writes one `map-{folder}.ngf.md` per
  folder + a root `index.ngf.md` router, in the `ctx/1.1` format (YAML card + one fenced
  ` ```ctx ` graph block).
- **The `map-scout` agent** (`/context-os`): scan → enrich each map with descriptions,
  verified edges, and a `safe_edit_points`/`risk_areas` governance card → stamp → splice
  the CLAUDE.md/AGENTS.md pointer → self-verify.
- **The `map-updater` agent** (`/context-os-update`): drift-only refresh of the maps whose
  folder changed; reports every removed node by name.
- **`/context-os-status`**: read-only freshness + token-save report.
- **Structural-hash drift detection** (`ctx_staleness.py`): a semantic (not mtime) folder
  signature written to each map's frontmatter as `structural_hash` + a live `staleness`
  flag, with `stamp`/`flip`/`status` operations.
- **Drift hooks** (`hooks/`): PostToolUse flips a map to `DRIFTED` when a source file in its
  folder changes; PreToolUse re-checks a map just before it's read (catching out-of-band
  changes). Never blocks; the warning lives inside the map file (portable to any tool).
- **`/snapshot`** (`snapshot.py`): a portable session-handoff file (compacted summary +
  work-state graph + git state + map hashes at capture) for cold resume on another machine
  or model. Previous snapshots archived under `.context-os/snapshots/`.
- **The pointer block** (`claudemd_splice.py`): a marked, idempotent, refuse-on-malformed,
  backup-first block written into both CLAUDE.md and AGENTS.md instructing agents to read
  the map before exploring.
- **`audit.py check` / `savings`**: derive-don't-fabricate audit over the whole map set,
  and a token-save number measured against real source.
- Tests (23), CI, a worked `demo/`, and `SPEC.md` (the `ctx/1.1` format).

### Notes
- The `scan.py`, `claudemd_splice.py`, and `audit.py` cores were adapted from the
  ctx-architecture plugin and vendored so context-os is self-contained.
- Free, offline, `$0`, stdlib-only, no server, no API keys.
