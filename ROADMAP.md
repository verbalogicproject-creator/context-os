# Roadmap

v0.1 shipped the core: per-folder maps, structural-hash drift detection via Claude Code
hooks, the CLAUDE.md/AGENTS.md pointer, and `/snapshot`.

**v0.2 shipped generation-cost tiers** (from the memorylog- dogfood, where map generation was
~45% of a session): a free `--skeleton` structural tier, sharded per-folder `map-enricher`
agents on Haiku (default) with `--premium` for Sonnet, and per-folder structural digests so
enrichers read signatures not whole files. Next levers below:

- **Wire the digest deeper + measure.** Confirm the Haiku-on-digest quality bar against Sonnet
  on a few real repos; tune the digest (more languages, better doc extraction) and the batch size.

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
