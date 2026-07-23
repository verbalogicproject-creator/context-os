# CLAUDE.md — context-os (this plugin's own repo)

This is the `context-os` Claude Code plugin itself — not a project mapped BY it. (For an
example of its output, see `demo/`, which carries real, committed maps.)

## Layout

- `.claude-plugin/plugin.json` — plugin manifest (metadata only; dirs auto-discovered).
- `commands/*.md` — the four slash commands (`/context-os`, `/context-os-update`,
  `/context-os-status`, `/snapshot`). `/context-os` is the **orchestrator**: it runs the
  deterministic scan, then (for the enriched tiers) fans out one `map-enricher` per folder in
  parallel; `--skeleton` skips enrichment entirely, `--premium` runs the enrichers on Sonnet.
- `agents/*.md` — `map-enricher` (enriches ONE folder's map, `model: haiku`) and `map-updater`
  (drift-only refresh, `model: sonnet`). (The old monolithic `map-scout` was retired in v0.2 —
  its work is split between the command orchestrator and the per-folder `map-enricher`.)
- `hooks/` — `hooks.json` + `pre_tool_use.py` / `post_tool_use.py` / `_common.py`: the
  drift hooks that keep each map's `staleness` flag honest.
- `scripts/` — stdlib-only, offline:
  - `scan.py` — deterministic scanner + the per-folder `.ngf.md` emit (`--emit-ngf`).
  - `claudemd_splice.py` — the ONLY code path allowed to write the CLAUDE.md/AGENTS.md
    marked block.
  - `audit.py` — the `.ngf.md`-aware `.ctx` parser + `check` (derive-don't-fabricate) +
    `savings` (token report).
  - `ctx_staleness.py` — the structural-hash engine (`signature`/`stamp`/`flip`/`status`).
  - `snapshot.py` — the mechanical scaffolder for `/snapshot`.
  - `retrieve.py` — CCR: resolve a `path[:symbol]` anchor to the exact original block + hash.
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
   sentence is the whole token-saving intervention (`test_splice.py` asserts it).

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
