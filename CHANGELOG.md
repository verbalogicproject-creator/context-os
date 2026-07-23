# Changelog

All notable changes to context-os are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow semver.

## [Unreleased]

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
