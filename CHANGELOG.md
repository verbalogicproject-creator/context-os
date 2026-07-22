# Changelog

All notable changes to context-os are documented here. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions follow semver.

## [Unreleased]

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
