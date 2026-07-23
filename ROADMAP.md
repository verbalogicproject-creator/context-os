# Roadmap

v0.1 shipped the core: per-folder maps, structural-hash drift detection via Claude Code
hooks, the CLAUDE.md/AGENTS.md pointer, and `/snapshot`.

**v0.2 shipped generation-cost tiers** (from the memorylog- dogfood, where map generation was
~45% of a session): a free `--skeleton` structural tier, sharded per-folder `map-enricher`
agents on Haiku (default) with `--premium` for Sonnet, and per-folder structural digests so
enrichers read signatures not whole files. Next levers below:

- **Wire the digest deeper + measure.** Confirm the Haiku-on-digest quality bar against Sonnet
  on a few real repos; tune the digest (more languages, better doc extraction) and the batch size.

**v0.3 shipped Headroom's compression ideas in-domain** (stdlib-only, no Headroom dep): CCR
retrieval (`retrieve.py` — the map is the compressed view, the source the retrievable original,
by `path:symbol` anchor + hash), an MCP server exposing map + retrieve so context-os stacks under
any runtime compressor, content-aware maps for config/docs/data/log folders (`compress.py`), and
cache-stability hygiene (`audit.py cache-check`).

**v0.3.1 closed the claim-vs-delivery gap** (Scientifix-Council review): per-session behavioral
measurement (`session_log.py` + `measure.py` + `audit.py session-savings`) so the savings number
is the delivered map-consultation rate, not an artifact-size ceiling; a non-blocking map nudge;
ast-exact + literal-aware symbol spans with a `low_confidence` flag; atomic map writes + a
malformed-frontmatter guard; an edge advisory in `check`; and a CI band pinning the headline.

**Validated end-to-end (2026-07-23, ARIA-Therapeutic — 77 folders, 554 files, Python+TS+React):**
The parallel Haiku enricher fan-out ran end-to-end for the first time. Deterministic pass: ~5.4s,
$0, `check` PASS (553 nodes, 0 fabricated), ceiling 98.6% (~1.65M source tokens → ~23K map tokens).
A 10-folder parallel enricher batch: ~86s wall-clock (vs ~588s serial, ~6.8× from parallelism),
~26K Haiku tokens/folder, 6/10 folders needed 0 full-file reads (digest sufficient; JSX-component
folders needed more). First-pass Haiku quality on real messy code: ~1 rename→fabrication + ~5
prose-in-edge-target errors per 10 folders — **both classes caught** by `audit check` (hard fail)
and the edge advisory. Fixed at root cause: `map-enricher.md` hardened (keep disambiguated
`dir/stem` names verbatim; edge target is a node name, never prose) → re-ran the two folders →
`check` PASS. Conclusion: the orchestration is sound; the audit gate is load-bearing for the
default Haiku tier.

Still open from the same review (scoped, not yet built):
- **Orchestrator repair loop.** Because default-Haiku output isn't ship-clean on the first pass
  (see above), have `/context-os` re-run *only* the folders whose nodes fail `check` (bounded
  retries), so a stray fabrication/edge slip self-heals instead of leaving the map set failing.
- **Confirm the Haiku-vs-Sonnet quality delta** now that the Haiku error classes are known and
  guarded; tune the digest for JSX/React (thin docstrings forced full reads). Consider defaulting
  correctness-critical runs to `--skeleton` (honestly free, zero fabrication risk) or `--premium`.
- **Edge direction, not just existence.** `check`'s edge pass is advisory (dangling targets only).
  Tag ambiguous import resolutions in `scan.py` (the `_match_by_suffix` "other" branch, where a
  stem collision is resolved by iteration order) so a low-confidence edge is visible, not silent.
- **Verify the MCP server against a live Claude Code session** (`test_mcp.py` proves the protocol,
  not a real client); broaden symbol-span + content-type coverage; store a per-node build-time hash
  for verifiable CCR when a project opts in.
- **Quadratic import resolution.** `_match_by_suffix` is O(imports × files); pre-index `all_files`
  by stem for the "hundreds of thousands of tokens" monorepo case the README targets.
- **True per-session tokens.** `measure.py transcript` counts reads best-effort; wire it to sum the
  real `usage` deltas Claude Code already writes per turn, so delivered savings are in real tokens.

The items below are researched, scoped, and not yet built.

## Git integration (the human + CI loop)

v0.1's hooks are the *AI-agent* loop (flip a map's flag when the agent edits a file). Git
hooks are the *human + CI* loop — keeping maps honest when work arrives via `git pull`,
branch switches, teammates, or non-agent edits.

- **Git-diff-narrowed drift.** Use `git diff --name-only <verified_at_commit>` (+ `git
  status --porcelain` for uncommitted/untracked) as a cheap first pass to get the candidate
  changed folders, then recompute `structural_hash` only there to confirm *semantic* drift.
  Record `verified_at_commit` in each map's frontmatter next to `structural_hash`. Keep this
  an **optional** layer — the core must stay git-free and work offline.
- **Git hooks**, shipped via `lefthook` or a `.githooks/` dir + `core.hooksPath` (not husky
  — target repos aren't all Node): `pre-commit` = fast stamp/verify + `git add` the touched
  maps; `post-merge` / `post-checkout` = regenerate the affected folders' maps. CI is the
  real enforcement, not the hooks (they're bypassable).
- **Commit the maps, conflict-light.** Deterministic output (already sorted); a
  `.gitattributes` `linguist-generated=true` to collapse them in review; and a
  regenerate-on-conflict merge driver (`merge=contextos`) so a map conflict becomes a no-op
  re-generation instead of a text merge.
- **CI drift gate.** `python3 scripts/ctx_staleness.py status .` already exits non-zero on
  drift; add a documented GitHub Actions job (`git diff --exit-code` after regen) and an
  optional auto-regenerate-and-open-PR workflow (with bot-loop guards + a `paths:` filter).

## Merkle-tree structural hash

Restructure `structural_hash` as a Merkle tree — a folder's hash = hash of its children's
hashes, and the root index hash = hash of the top-level folder hashes. Then "did anything
change anywhere?" is a single root-hash comparison, and drift localizes to exactly the
changed subtree. (Prior art: claude-context's incremental re-indexing.)

## `/snapshot` ↔ git

Enrich the snapshot with `git stash create` (a SHA capturing dirty working-tree state
without committing) and support cross-machine transfer via `git bundle`. Restore =
fetch the bundle / checkout the SHA → apply the stash → re-verify maps against HEAD.

## Native-memory fit (validated for v0.1, deepen later)

Research confirms the v0.1 split is token-optimal: the **pointer block lives in CLAUDE.md**
(auto-loaded every session, ~50 tokens), while **maps stay lazy-loaded on demand** (never
`@import`ed — that would load them all every session). Snapshots stay **in the repo**
(`.context-os/snapshots/`), not in Claude Code's native auto-memory (which is machine-local
and meant for the agent's own learnings). Note: Claude Code does not read `AGENTS.md`
natively — the AGENTS.md pointer is specifically for Codex/Gemini portability.

Possible later: an optional per-folder nested `CLAUDE.md` pointing at that folder's map, so
Claude lazy-loads the map when it first touches the folder (native lazy-load), traded off
against the extra per-folder file + churn.

## Smaller

- `--min-files` threshold to fold trivially small folders into their parent's map.
- Auto-generated `sections:` line hints in a map's frontmatter for very large blocks
  (partial-read addressing), regenerated on each stamp — never hand-authored.
- A `context-os` console script so the scripts are runnable without `python3 scripts/…`.
