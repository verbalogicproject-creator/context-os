# Changelog

All notable changes to context-os are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow semver.

## [Unreleased]

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
