# CLAUDE.md — context-os (this plugin's own repo)

This is the `context-os` Claude Code plugin itself — not a project mapped BY it. (For an
example of its output, see `demo/`, which carries real, committed maps.)

## Layout

- `.claude-plugin/plugin.json` — plugin manifest (metadata only; dirs auto-discovered).
- `commands/*.md` — the six slash commands (`/context-os`, `/context-os-catchup`,
  `/context-os-update`, `/context-os-status`, `/snapshot`, `/relay`). `/relay` writes the
  cold-start handoff and **blocks on a cold-read gate** — `relay.py capture` → the main
  session fills the authored half → `budget` → a `relay-cold-reader` agent scores it → below
  8/10 the session fixes the relay before it ends. `/context-os` is the **orchestrator**:
  scan → `plan.py` ranks folders → fan out one `map-enricher` per **DEEP** folder in parallel →
  repair loop → fold content into parents; `--skeleton` skips enrichment, `--premium` runs Sonnet,
  `--all` enriches every folder. `/context-os-catchup` is the **lazy** path: after a `--skeleton`
  pass, it enriches only the folders the session's read ledger shows you touched.
- `agents/*.md` — `map-enricher` (enriches ONE folder's map, `model: haiku`), `map-updater`
  (drift-only refresh, `model: sonnet`), and `relay-cold-reader` (reads ONE handoff file and
  nothing else, and scores whether a cold session could resume from it, `model: sonnet`).
  (The old monolithic `map-scout` was retired in v0.2 — its work is split between the command
  orchestrator and the per-folder `map-enricher`.)
- `hooks/` — `hooks.json` + `pre_tool_use.py` / `post_tool_use.py` / `_common.py`: the
  drift hooks that keep each map's `staleness` flag honest.
- `scripts/` — stdlib-only, offline:
  - `scan.py` — deterministic scanner + the per-folder `.ngf.md` emit (`--emit-ngf`).
  - `plan.py` — deterministic folder ranker from the scan graph, two decisions per folder and
    no LLM. **Tier** (DEEP/SKELETON/FOLD) = how much it is worth describing → `--deep-only` is
    the enrich list. **`keeps_map`** = whether it earns its own map file; a folder too thin to
    (no code, SKELETON, or ≤ `merge_max_files` that little depends on) merges into its nearest
    map-keeping ancestor via `--apply-fold`, while an import hub (`in_degree ≥ merge_hub_in`)
    keeps its card however small. `--apply-fold` runs **before** enrichment — a merged code node
    arrives with only its path, so the absorbing map's enricher must see it. Code never merges
    into a code-free host, and the plan ignores context-os's own `map-*`/`index.ngf.md` so it
    gives the same answer before and after an emit.
  - `claudemd_splice.py` — the ONLY code path allowed to write the CLAUDE.md/AGENTS.md
    marked block.
  - `audit.py` — the `.ngf.md`-aware `.ctx` parser + `check` (derive-don't-fabricate, + an
    advisory dangling-edge pass) + `savings` (the CEILING) + `session-savings` (DELIVERED) +
    `repair-targets` (folders the orchestrator re-enriches when an enricher left a bad map).
  - `ctx_staleness.py` — the structural-hash engine (`signature`/`stamp`/`flip`/`status`);
    map writes are atomic and malformed frontmatter fails loudly. `signature` covers the folder
    **plus every descendant with no map of its own** — the same set `owning_map` resolves to that
    map, so a merged folder still drifts the map that absorbed it. For a leaf folder it is the
    old single-folder hash, byte for byte (`test_leaf_folder_hashes_exactly_as_before_the_descent`).
  - `session_log.py` — owns `.context-os/`: `ensure_log_dir` creates it and writes the nested
    `.gitignore` (`digests/`, `reads-*.jsonl`, `relay.ngf.md`) that keeps context-os's local
    artifacts out of a mapped project's history — never by editing that project's root
    `.gitignore`, and never overwriting an existing one. Also the per-session read ledger
    (`.context-os/reads-<session>.jsonl`):
    classifies each Read/Grep/Glob as map / source-in-mapped-folder / explore. The behavioral
    ground truth for "did the agent read the map?".
  - `measure.py` — turns that ledger into the DELIVERED number (map-consultation rate); a
    best-effort `transcript` mode reads Claude Code's own session `.jsonl`.
  - `snapshot.py` — the mechanical scaffolder for `/snapshot`.
  - `relay.py` — the mechanical half of a cold-start handoff (`.context-os/relay.ngf.md`,
    gitignored): `capture` (git state + map hashes + touched folders + the context prefix,
    with every authored slot emitted as a literal `TODO(relay):` line), `budget` (a
    16,000-CHARACTER ceiling; fails while any slot outside a fence is unfilled), `prefix`
    (current context size, from a bounded tail of the session transcript — never the whole
    file), `gate` (parses the cold reader's `SCORE:`/`ISOLATION:` trailer; fails below 8/10,
    and marks a score **provisional** when the reader disclosed injected context rather than
    failing on it — every run so far has been contaminated, and a gate that can never pass is
    not a gate). A relay supersedes `snapshot` and reuses its `git_state`/`map_hashes`.
  - `retrieve.py` — CCR: resolve a `path[:symbol]` anchor to the exact original block + hash
    (ast-exact for Python; literal-aware best-effort elsewhere, with a `low_confidence` flag).
  - `compress.py` — content-aware compressed views for non-code files (config/doc/data/log).
  - `mcp_server.py` — stdlib stdio MCP server (`contextos_map` + `contextos_retrieve`), wired by `.mcp.json`.
- `demo/` — a two-service app with its own committed maps, used by the README and CI.
- `tests/` — pytest; `conftest.py` puts `scripts/` on `sys.path` (no packaging step).

`scan.py`, `claudemd_splice.py`, and `audit.py` were adapted from the ctx-architecture
plugin and **vendored** here so context-os is self-contained (see `NOTICE`).

## Working in this repo — invariants (do not regress)

1. **`scripts/` is stdlib-only.** No third-party import — the whole point is that it runs
   offline, `$0`, with no dependency that could silently break. This includes no YAML lib:
   frontmatter is read/written line-based in `ctx_staleness.py` (`fm_get`/`fm_set`).
2. **Never fabricate a node.** Every non-`[ext]` map node must trace to a real file;
   `audit.py check` is the gate. Keep `tests/test_audit_ngf.py` green.
3. **Staleness is semantic, not temporal.** `ctx_staleness.signature` hashes only
   import/declaration lines, sorted — a reformat or `git clone` must NOT drift a map. The
   `test_staleness.py::test_whitespace_and_comments_do_not_drift` test locks this in.
4. **Only `claudemd_splice.py` touches CLAUDE.md/AGENTS.md**, only inside its own marked
   block, with a `.bak` first, and it REFUSES on malformed markers. Keep the four
   refusal/idempotency/byte-identity tests in `test_splice.py` green.
5. **The pointer block must keep the "Do NOT fan out exploration agents" line** — that
   sentence is the token-saving *intervention* (`test_splice.py` asserts it). Its *effect* is
   not assumed: the PreToolUse hook + `session_log.py` measure whether the agent actually
   read the map, and `measure.py`/`session-savings` report the delivered rate.
6. **Ceiling ≠ delivered — never conflate them.** `audit.py savings` is an artifact-size
   *ceiling* (the most a session could save); the delivered number comes only from the
   session ledger. Public copy must not present the ceiling as tokens actually saved. The
   `check` gate proves node *existence* and the absence of instruction-shaped text — **not**
   description accuracy or edge direction (say "never invents a node", never an unqualified
   "never invents").
7. **Hooks never block and never break a tool call.** The drift/telemetry/nudge hooks emit
   `systemMessage` at most (no permission decision) and swallow every exception. The ledger
   is local, gitignored (`.context-os/reads-*.jsonl`), and `other`-kind reads aren't logged.
8. **A map never carries a secret.** Maps are meant to be COMMITTED, so the scanner must
   not put anything private in one. Three layers, all in `test_gitignore.py` /
   `test_compress.py`: `compress.is_secret_file` drops the whole `.env` family by name;
   `gitignore.GitIgnore` drops anything the project itself excluded; and every compressor
   reports SHAPE (key names, column headers, section titles), never file content.
   `_compress_log` used to append 80 verbatim characters of the first error line — the one
   place content leaked — and that is why the rule is stated as an invariant rather than
   left to judgement.
9. **A map never carries an instruction.** The `map-enricher` is a model reading arbitrary
   repo content, and the pointer block makes every session read maps *before* source — so
   prose that survives from a hostile README into a map description acts as an instruction,
   first, every session. `audit.py check` fails on text that only makes sense as a directive
   about the agent's own tools, permissions or secrets (`check_maps_injection`). The
   patterns are tuned for PRECISION: "do not edit this file directly" is legitimate
   architecture prose and must keep passing — `test_injection.py` pins both directions.

Run the full check before considering a change done:
```bash
python3 -m pytest tests/ -q
python3 scripts/audit.py check demo && python3 scripts/ctx_staleness.py status demo
```

## Public-facing copy — plain English only

`plugin.json`, the command/agent descriptions, `README.md`, `HOW-TO-USE.md`, and hook
messages are for a general audience. Do **not** use ecosystem jargon there — no `NLKE`,
`substrate`, `SAG`, `declared`/`declaration`-as-jargon, `ai_card`. Say what it does in
plain words ("reads a map instead of re-scanning", "flags a map when its folder changes").
The `.ngf.md` file extension stays (it's the format), but explain it plainly where it first
appears ("a Markdown file with a YAML header").

## Attribution

Eyal Nof, sole author. Apache-2.0 (`LICENSE`, `NOTICE`). Do not add a co-author trailer to
commits in this repo. Stop before pushing — pushing is the author's call.
