# Codebase report — context-os

A module-by-module map of this repo's own code, for anyone extending context-os itself
(vs. a project *mapped by* context-os — see `demo/` for that). For the narrative version of
these rules see `CLAUDE.md`; for the file format see `SPEC.md`; for what's planned next see
`ROADMAP.md`. This report doesn't repeat those — it's the connective map between them.

**Snapshot facts** (re-derive with the commands shown; don't trust a stale number):

| Fact | Value | How to check it yourself |
|---|---|---|
| Version | `0.5.0` | `.claude-plugin/plugin.json` → `version` |
| License | Apache-2.0, Eyal Nof sole author | `LICENSE`, `NOTICE` |
| Python files (repo, excl. caches) | 36 | `find . -name '*.py' -not -path './.pytest_cache/*' -not -path '*/__pycache__/*' \| wc -l` |
| `scripts/` — lines | 12 files, 4,139 lines | `wc -l scripts/*.py` |
| `hooks/` — lines | 3 files, 202 lines | `wc -l hooks/*.py` |
| Tests | 126 passing, 17 test files + `conftest.py` | `python3 -m pytest tests/ -q` |
| Slash commands | 5 (`commands/*.md`) | `ls commands/` |
| Agents | 2 (`agents/*.md`) | `ls agents/` |
| MCP tools | 2 (`contextos_map`, `contextos_retrieve`) | `.mcp.json` + `scripts/mcp_server.py` |
| Demo | 2 folders, 5 source files (`api/` ×3 Python, `web/` ×2 TypeScript) | `find demo -name '*.py' -o -name '*.ts'` |

Third-party dependency count for `scripts/`, `hooks/`, and the plugin itself: **zero**
(stdlib only; `pytest` is a dev-only test dependency — see `CONTRIBUTING.md`).

---

## How it fits together (read bottom-up)

```
                         ┌─────────────────────────────┐
                         │   a project (any repo)      │
                         │   your source files          │
                         └───────────────┬──────────────┘
                                         │ scanned by
                         ┌───────────────▼──────────────┐
                         │        scripts/scan.py        │  deterministic, stdlib-only
                         │  imports → edges, decls → nodes│  (calls compress.py for
                         └───────────────┬──────────────┘   non-code files)
                                         │ writes
                    ┌────────────────────┼────────────────────┐
                    ▼                    ▼                    ▼
          index.ngf.md          map-{folder}.ngf.md    .context-os/digests/*
          (root router)         (one per folder,        (structural digest,
                                  skeleton first)          enrichment input)
                                         │
                    ┌────────────────────┼─────────────────────┐
                    ▼                                          ▼
        scripts/plan.py ranks                     agents/map-enricher.md
        folders DEEP/SKELETON/FOLD                 (Haiku/Sonnet, one per DEEP
        (no LLM)                                    folder, parallel, isolated)
                    │                                          │
                    └───────────────────┬──────────────────────┘
                                         ▼
                          scripts/audit.py check   (derive-don't-fabricate gate)
                                         │
                    ┌────────────────────┼─────────────────────┐
                    ▼                    ▼                     ▼
       ctx_staleness.py stamp   claudemd_splice.py       audit.py savings
       (drift baseline)         (CLAUDE.md/AGENTS.md      (the CEILING number)
                                  pointer block)
                                         │
                                         ▼
                     ┌───────────────────────────────────┐
                     │   hooks/ (PostToolUse, PreToolUse) │  keep staleness honest
                     │   session_log.py (the read ledger) │  log map vs. source reads
                     └───────────────────┬────────────────┘
                                         ▼
                           scripts/measure.py session/catchup
                           (the DELIVERED number, behavioral)

  Two more surfaces read the same maps, sideways to the pipeline above:

    scripts/retrieve.py  ── CCR: map reference -> exact original block + sha256
    scripts/mcp_server.py ── exposes retrieve.py + map reads as MCP tools
                             (contextos_map, contextos_retrieve), wired by .mcp.json

  And one command writes a different kind of file, orthogonal to all of the above:

    commands/snapshot.md + scripts/snapshot.py ── snapshot.ngf.md (session handoff,
                                                    not drift-checked, ages not drifts)
```

Read this diagram bottom-up: a project's source is scanned once (free), ranked (free),
selectively enriched (the only step that costs tokens), gated by the fabrication audit,
stamped for drift, spliced into the project's own `CLAUDE.md`/`AGENTS.md`, and from then on
kept honest by two hooks that never block anything.

---

## Directory layout (annotated)

```
context-os/
├── .claude-plugin/
│   └── plugin.json          Plugin manifest — name, version, description, author,
│                             license. Command/agent/hook dirs are auto-discovered by
│                             Claude Code from their conventional paths; nothing here
│                             lists them explicitly.
├── .mcp.json                 Registers the MCP server: `python3 scripts/mcp_server.py`.
├── commands/                 5 slash commands (Markdown w/ YAML frontmatter — Claude
│   ├── context-os.md          Code reads `description`/`argument-hint` and the body as
│   ├── context-os-catchup.md  the prompt). See "Commands" below.
│   ├── context-os-update.md
│   ├── context-os-status.md
│   └── snapshot.md
├── agents/                   2 subagent definitions (frontmatter: name/description/
│   ├── map-enricher.md        tools/model). See "Agents" below.
│   └── map-updater.md
├── hooks/
│   ├── hooks.json             Wires PostToolUse (Edit|Write|MultiEdit) and PreToolUse
│   │                           (Read|Grep|Glob) to the two handler scripts.
│   ├── _common.py              Shared bootstrap: put scripts/ on sys.path, read the
│   │                            hook's JSON stdin, resolve the project root, emit JSON.
│   ├── post_tool_use.py         On a successful source edit, flip the owning map's
│   │                            staleness (never blocks; swallows every exception).
│   └── pre_tool_use.py           On Read/Grep/Glob: re-check a map's staleness before
│                                  it's read, log the read to the session ledger, and
│                                  (once per folder) nudge if source is read without its
│                                  map. Never blocks.
├── scripts/                  11 stdlib-only Python modules — the whole engine. See
│   │                          "Module map" below for one row per file.
│   ├── scan.py                (772 lines) the scanner
│   ├── plan.py                (285 lines) the folder ranker
│   ├── audit.py                (735 lines) the audits (fabrication, cache, savings…)
│   ├── ctx_staleness.py         (349 lines) the drift engine
│   ├── claudemd_splice.py        (317 lines) the CLAUDE.md/AGENTS.md writer
│   ├── retrieve.py                (336 lines) CCR — resolve an anchor to an original
│   ├── compress.py                 (120 lines) non-code content-aware views
│   ├── measure.py                   (227 lines) delivered-savings measurement
│   ├── session_log.py                (164 lines) the per-session read ledger
│   ├── snapshot.py                    (137 lines) the /snapshot scaffolder
│   └── mcp_server.py                   (139 lines) the stdio MCP server
├── tests/                    83 tests across 13 `test_*.py` files + `conftest.py`
│                              (puts scripts/ on sys.path — no packaging step).
├── demo/                     The worked example: a tiny two-service app (`api/` in
│   ├── api/  (3 .py files)    Python, `web/` in TypeScript) with REAL, committed
│   ├── web/  (2 .ts files)    context-os output (`index.ngf.md` + `map-*.ngf.md`),
│   ├── index.ngf.md           used by the README, HOW-TO-USE, docs/, and CI's smoke
│   ├── CLAUDE.md / AGENTS.md  test.
│   └── README.md
├── docs/                     Numbered, hands-on chapters (see docs/00-mental-model.md).
├── .github/workflows/ci.yml  pytest, a fresh-scan-and-verify smoke test on a copy of
│                              demo/, and a drift gate on the committed demo maps.
├── SPEC.md                   The `ctx/1.1` file-format spec (the three `kind:`s).
├── ROADMAP.md                What shipped per version, and what's next (unbuilt).
├── CHANGELOG.md               Keep-a-changelog-style, one entry per shipped version.
├── CLAUDE.md / README.md / HOW-TO-USE.md / INSTALL.md / CONTRIBUTING.md / SECURITY.md
└── LICENSE / NOTICE           Apache-2.0; vendoring note for scan.py/claudemd_splice.py/
                                audit.py (adapted from the ctx-architecture plugin).
```

---

## Module map — `scripts/`

Every module is stdlib-only Python; `imports →` names other files under `scripts/` it
imports (an internal edge — not a claim about what the *target project's* code imports).

| Module | Lines | Responsibility | Imports → | Imported by (internal) |
|---|---|---|---|---|
| `scan.py` | 805 | Deterministic scanner: walks a project, resolves per-language imports (Python incl. relative/nested; TS/JS incl. JSX/TSX/Vue/Svelte; Go, Rust, Java/Kotlin) into `ScanResult` (nodes+edges), emits `map-*.ngf.md` skeletons + `index.ngf.md` (`--emit-ngf`) and per-folder structural digests (`--emit-digests`). Calls `compress.py` for non-code file descriptions. | `compress.py` | `audit.py`, `plan.py`, 6 test files |
| `plan.py` | 285 | Ranks every folder **DEEP** (enrich — real code, or an import hub) / **SKELETON** (small/peripheral, keep the free skeleton) / **FOLD** (pure docs/data/config — merge into parent), from the scan graph alone. No LLM. `--apply-fold` mutates the map set to merge FOLD folders into their parent. | `scan.py` | `test_plan.py` |
| `audit.py` | 821 | The load-bearing gates: `check` (derive-don't-fabricate — every non-`[ext]` node must trace to a real file, across the whole map set — **and** `check_maps_injection`, which fails on instruction-shaped text in any map, since agents read maps before source), `repair-targets` (which folders need a re-enrich), `cache-check` (the always-loaded pointer block must be volatile-free/byte-stable), `savings`/`session-savings` (ceiling vs. delivered token numbers), `splice-safety` (byte-identity outside the marked block), `parse` (debug: dump a map's nodes/edges as JSON). | `claudemd_splice.py`, `measure.py`, `scan.py` | `measure.py`, 6 test files |
| `ctx_staleness.py` | 349 | The drift engine: `signature` hashes only a folder's import/declaration lines (sorted, non-recursive — semantic, not temporal); `stamp` writes the baseline; `flip` recomputes and sets the live `staleness` verdict; `stamp-all`/`status` operate repo-wide. Atomic writes (tempfile + `os.replace`); malformed frontmatter fails loudly rather than silently no-op'ing. | (none — stdlib only) | `post_tool_use.py`, `pre_tool_use.py`, `session_log.py`, `snapshot.py`, 2 test files |
| `claudemd_splice.py` | 356 | The **only** code path allowed to write the marked block into `CLAUDE.md`/`AGENTS.md` (or a changelog block): finds markers, backs up first (timestamped), refuses on malformed markers rather than guessing, is idempotent (a second run is a byte-identical no-op), writes atomically (tempfile + `os.replace`) and preserves the file's original line endings. | (none — stdlib only) | `audit.py`, 2 test files |
| `retrieve.py` | 364 | CCR "retrieve": `contain()` confines every anchor to the project root (`root / path` does NOT — pathlib discards the root when the path is absolute); resolves a `path` or `path:symbol` anchor to the exact original block + `sha256`. Python spans are exact (stdlib `ast`); brace/indent languages use literal-aware best-effort matching, flagging `low_confidence` rather than trusting a possibly-truncated span; falls back to the whole file if the symbol isn't found. | (none — stdlib only) | `mcp_server.py`, `test_retrieve.py` |
| `compress.py` | 157 | Deterministic compressed one-line views for **non-code** files: `[config]` (JSON/YAML keys+shape), `[doc]` (title+headings), `[data]` (CSV columns+row count), `[log]` (error/warning count + which severities appear). Reports SHAPE, never contents; `is_secret_file` drops the `.env` family so it never becomes a map node. No LLM — called at scan time. | (none — stdlib only) | `scan.py`, `test_compress.py` |
| `gitignore.py` | 160 | A stdlib subset of `gitignore(5)` — negation, directory-only rules, anchoring, `**`, nested ignore files — so anything a project deliberately excluded never becomes a map node. Deliberately not a shell-out to `git check-ignore`: that would make map contents depend on whether git is installed, so the same tree could produce two different maps. | (none — stdlib only) | `scan.py`, `test_gitignore.py` |
| `measure.py` | 391 | Turns the session read ledger into the **delivered** number, plus `cost` — the REAL per-turn usage from a Claude Code `.jsonl` (not a bytes/4 estimate), with `context_tax()` pricing what admitting N tokens at turn T costs over the rest of the session. `session` (map-consultation rate for one session), `catchup` (touched-but-still-skeleton folders — the `/context-os-catchup` set), `transcript` (best-effort read count from Claude Code's own `.jsonl`). | `audit.py`, `session_log.py` | `audit.py`, `test_measure.py` |
| `session_log.py` | 164 | The per-session read ledger (`.context-os/reads-<session>.jsonl`, gitignored): classifies each Read/Grep/Glob as a map read, a source read in a mapped folder, or an explore over a mapped folder — the behavioral ground truth `measure.py` reports on. | `ctx_staleness.py` | `measure.py`, `pre_tool_use.py`, `test_measure.py` |
| `snapshot.py` | 137 | Mechanical scaffolder for `/snapshot`: records git state + every map's `structural_hash`/`staleness` at capture, archives the previous snapshot under `.context-os/snapshots/`, writes a `## summary` + work-state `ctx` block scaffold for the agent to fill in (the agent — not this script — writes the actual narrative). | `ctx_staleness.py` | (none — leaf) |
| `mcp_server.py` | 149 | A stdlib stdio JSON-RPC server exposing `contextos_map(folder?, root?)` and `contextos_retrieve(anchor, root?)` as MCP tools, wired by `.mcp.json`. | `retrieve.py` | `test_mcp.py` |

**Note — found by this report, since fixed:** `scripts/mcp_server.py` reported
`version: "0.3.0"` in its `initialize` response, a hardcoded value last bumped for the
v0.3.0 MCP-server release and stale against the plugin's `0.5.0`. Cosmetic (protocol
negotiation doesn't depend on it), and now synced. It stays recorded here because the class
of defect recurs: a version string duplicated outside `plugin.json` has nothing keeping it
honest, so the next one will drift the same way.

## Module map — `hooks/`

| Module | Lines | Responsibility |
|---|---|---|
| `_common.py` | 56 | Shared bootstrap for both hooks: put `scripts/` on `sys.path` so hooks can import the engine without packaging, read the hook's JSON off stdin, resolve the project root, `emit()` the JSON response. |
| `post_tool_use.py` | 59 | `Edit\|Write\|MultiEdit` matcher. On a *successful* edit to a source file (checked by extension against `ctx_staleness.SRC_EXT`), resolves the owning `map-*.ngf.md` and flips its staleness. Editing a map's own prose does **not** drift it — the signature hashes source, not the map. |
| `pre_tool_use.py` | 87 | `Read\|Grep\|Glob` matcher. Reading a map re-checks its staleness first (catches out-of-band changes like `git pull`). Every call is logged to the session ledger. Once per folder, if source is read (or grepped) without that folder's map having been read first, emits a one-line `systemMessage` nudge — never a permission decision. |

Both hooks: exit 0 always, swallow every exception (telemetry/drift bookkeeping must never
break a tool call), and speak only via `systemMessage` (informational), never `permissionDecision`.

## Commands (`commands/*.md`)

| Command | Dispatches | Model | Mutates |
|---|---|---|---|
| `/context-os` | orchestrates `scan.py` → `plan.py` → N× `map-enricher` (parallel) → repair loop → `plan.py --apply-fold` → `ctx_staleness.py stamp-all` → `claudemd_splice.py` → `audit.py check`/`savings` | Haiku (default), Sonnet (`--premium`), none (`--skeleton`) | maps, digests, `CLAUDE.md`/`AGENTS.md` |
| `/context-os-catchup` | `measure.py catchup` → N× `map-enricher` for the touched-and-still-skeleton set → repair loop → `stamp-all`/`check` | same as above | maps only (no new folders) |
| `/context-os-update` | the `map-updater` agent | Sonnet | drifted maps only, `index.ngf.md` if shape changed |
| `/context-os-status` | `ctx_staleness.py status` + `audit.py savings`/`check`/`session-savings` | — | nothing (read-only) |
| `/snapshot` | `snapshot.py scaffold`, then the **main session itself** fills in the summary | — (must run in the main session, not a subagent) | `snapshot.ngf.md`, archives the prior one |

## Agents (`agents/*.md`)

| Agent | Model | Scope | Invariant |
|---|---|---|---|
| `map-enricher` | `haiku` (default), `sonnet` under `--premium` | Exactly ONE folder's map, isolated context (so a whole-repo run fans many out in parallel, cheaply) | **Derive, never fabricate** — every description, edge, and risk it writes must trace to a file or digest it actually read. Never renames a node, never touches another folder's map, never stamps/splices/audits. |
| `map-updater` | `sonnet` | Only the maps `ctx_staleness.py status` reports `DRIFTED`; diffs against a fresh scan rather than re-authoring | **Report removals** — never silently drops a node; if a node's file is gone, it says so by name in its report. |

`map-enricher`'s grounding rule is the core invariant of the whole enrichment path: the
`audit.py check` gate mechanically proves every node traces to a real file, but the discipline
that makes descriptions *trustworthy in the first place* is the agent never writing one it
can't point to a read for.

## MCP surface (`.mcp.json` → `scripts/mcp_server.py`)

| Tool | Input | Output |
|---|---|---|
| `contextos_map` | `folder?` (repo-relative; omit for the root index), `root?` | The map's/`index.ngf.md`'s full text, or `"no map at …"`. |
| `contextos_retrieve` | `anchor` (`path` or `path:symbol`), `root?` | The exact original block (`retrieve.py`'s output) plus its `sha256`. |

Verified live in `tests/test_mcp.py::test_stdio_round_trip` — a real subprocess speaking
JSON-RPC over stdio (`initialize` → `notifications/initialized` → `tools/call`), not just the
in-process `handle()` function.

## Test coverage map (`tests/*.py` → what it locks in)

| Test file | Tests | Covers |
|---|---|---|
| `test_scan_imports.py` | 3 | Python relative/nested import resolution → `->` edges |
| `test_scan_emit.py` | 3 | `--emit-ngf`: valid maps + index, collision-safe names, skip-existing |
| `test_digest.py` | 2 | Per-folder structural digests (doc + signatures + imports) |
| `test_compress.py` | 6 | Non-code compressed views (config/doc/data/log) + their scan/emit integration |
| `test_plan.py` | 6 | DEEP/SKELETON/FOLD ranking + `--apply-fold` |
| `test_audit_ngf.py` | 10 | `.ngf.md` parsing, whole-map fabrication audit, edge advisory, `repair-targets` |
| `test_cache_check.py` | 3 | Pointer-block volatile-content flagging + byte-stability |
| `test_savings_band.py` | 2 | CI band pinning the demo's ceiling number |
| `test_splice.py` | 6 | CLAUDE.md/AGENTS.md splice: preserve, idempotent, refuse-on-malformed, byte-identity |
| `test_staleness.py` | 13 | Structural-hash signature, stamp/flip/status, atomic writes, malformed-frontmatter handling |
| `test_measure.py` | 12 | Session ledger classification, delivered-savings, `catchup` targeting |
| `test_retrieve.py` | 13 | CCR symbol-span resolution (Python `ast`-exact, brace/indent best-effort, `low_confidence`) |
| `test_mcp.py` | 4 | MCP JSON-RPC handshake, `tools/list`, both tools, a real stdio round-trip |

Total: **83 tests**, run with `python3 -m pytest tests/ -q` — all green as of this report
(verified: see the Snapshot facts table above for the exact command).

---

## Data flow at a glance

1. **Generate** (`scan.py` → optionally `plan.py`/`map-enricher` → `ctx_staleness.py stamp` →
   `claudemd_splice.py` → `audit.py check`). Produces the map set + the pointer.
2. **Stay honest** (`hooks/` flip `staleness` on edit; re-check it on read). No LLM, no cost.
3. **Measure** (`session_log.py` logs; `measure.py`/`audit.py session-savings` report). Turns
   the ceiling claim into a delivered number.
4. **Retrieve on demand** (`retrieve.py`, `mcp_server.py`). Sideways to the pipeline — any
   reader (this repo's own agents, or an external one over MCP) can pull the exact original
   behind any map node.
5. **Snapshot** (`snapshot.py` + the main session's own narrative). Orthogonal — a point-in-time
   handoff file, not part of the drift/enrichment loop.

## Known gaps (see `ROADMAP.md` for the full, current list)

- `scripts/mcp_server.py`'s hardcoded `version: "0.3.0"` is stale against `plugin.json`'s
  `0.5.0` (noted above — cosmetic, not a protocol issue).
- Git integration (drift narrowed by `git diff`, git hooks, a CI auto-regenerate workflow),
  a Merkle-tree structural hash, and `/snapshot` ↔ `git stash create`/`git bundle` are
  researched and scoped in `ROADMAP.md` but **not built** — do not describe them as shipped.
- `plan.py`'s edge-direction advisory and the Haiku-vs-Sonnet quality delta are open
  measurement questions, not yet resolved (`ROADMAP.md`, "still open" section).
