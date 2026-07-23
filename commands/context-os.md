---
description: Map this project into portable per-folder context files so a fresh session reads a cheap map instead of re-scanning your whole repo, and drop a pointer into CLAUDE.md + AGENTS.md
argument-hint: "[project-root] [--skeleton|--fast] [--premium] (root defaults to cwd)"
---

# /context-os

Give this project a set of small, always-current architecture maps — one per folder plus a
root index — so Claude (and Codex, and Gemini) stop re-discovering your codebase from scratch
every session.

## Three tiers (pick with a flag)

| Invocation | What it does | Cost |
|---|---|---|
| `/context-os --skeleton` (or `--fast`) | Structure-only: real nodes + `->` edges + drift baseline + pointer. No descriptions, no risk cards, **no LLM**. | ~free, seconds |
| `/context-os` (default) | Full maps — descriptions, verified edges, and a safe-edit/risk card — enriched by a **fan-out of small per-folder agents in parallel** (Haiku). | cheap |
| `/context-os --premium` | Same, but the per-folder enrichers run on **Sonnet** for the best prose/risk quality. | higher |

The deterministic scanner + drift stamp + pointer splice + fabrication audit are the same in
all three; only the enrichment differs.

**Strategic by default (map what matters).** On the enriched tiers, `/context-os` first *ranks*
folders (`plan.py`) and enriches only the **DEEP** ones — folders with real code or that other
folders import; small/peripheral folders keep a free skeleton, and pure docs/data folders fold
into their parent. So a big repo pays for the handful that carry the architecture, not every
folder. Pass **`--all`** to enrich every folder the old way.

## Request

$ARGUMENTS

## Protocol

1. **Parse flags + resolve root.** Root = the first non-flag arg, else the current directory
   (confirm it has source files). Detect `--skeleton`/`--fast`, `--premium`, and `--all` (enrich
   every folder — skip the plan and the fold). Everywhere below, `${CLAUDE_PLUGIN_ROOT}` is this
   plugin's script/agent dir.

2. **Scan → grounded skeletons** (all tiers):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scan.py" "<root>" --emit-ngf --emit-digests
   ```
   This writes one `map-{folder}.ngf.md` per folder + `index.ngf.md`, and (for the enriched
   tiers) a per-folder structural digest under `<root>/.context-os/digests/`.

3. **Plan — choose what to enrich** (default; skip for `--skeleton`; `--all` maps every folder):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan.py" "<root>"                # ranked table
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan.py" "<root>" --deep-only     # just the enrich list
   ```
   `plan.py` ranks every folder from the scan graph into **DEEP** (real code, or an import hub →
   enrich), **SKELETON** (small/peripheral code → keep the free skeleton, no enricher), and **FOLD**
   (pure docs/data/config → merged into its parent in step 6). Take the `--deep-only` list. Optionally
   **adjust the `*`-flagged borderline folders** — promote a thin-but-critical entry, or demote a
   big-but-boilerplate folder — a handful, each with a one-line reason. Never touch the clear DEEP or
   FOLD cases. This is the difference between mapping what matters and blindly mapping every folder.

4. **Enrich** — branch on the tier:

   - **`--skeleton`/`--fast`:** skip enrichment entirely. Go straight to step 5.

   - **default / `--premium`:** **dispatch one `context-os:map-enricher` agent per DEEP folder** (plus
     any borderline you promoted; for `--all`, every folder), in **parallel batches of ~8–12** (wait
     for each batch before the next). Give each `{project_root, folder}`. For **`--premium`**, dispatch
     each enricher on the **Sonnet** model; otherwise its default (Haiku). Each enricher fills its own
     map's descriptions, edges, and risk card in isolation and returns one line. If an enricher fails,
     note the folder and continue — its map stays a valid skeleton. SKELETON and FOLD folders are left
     as their deterministic maps (FOLD content is already described by the scanner).
     Then **enrich the index yourself**: give each DEEP folder's node in `index.ngf.md` a one-line
     description derived from that folder's now-enriched map (cheap — read each map's title line).

5. **Repair loop** (enriched tiers only — skip for `--skeleton`): before folding/stamping, catch any
   map an enricher left broken. Default Haiku output is not always ship-clean first-pass — the two
   common slips are a renamed node (a disambiguated `dir/stem` name shortened to its bare stem → fails
   the fabrication gate) and a prose edge target (`~> chat store for messages` instead of `~> chat`).
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/audit.py" repair-targets "<root>"
   ```
   This prints the folders whose map has a fabricated node or a dangling edge. If the list is
   **non-empty**, for each: delete its `map-*.ngf.md`, re-emit its skeleton
   (`scan.py "<root>" --emit-ngf`), re-dispatch a `context-os:map-enricher`, then run `repair-targets`
   again. Repeat at most **2 rounds**. If a folder still fails after 2 rounds, leave it, name it in the
   report, and suggest `--premium` or a manual look — never hand-fix the map yourself.

6. **Fold content folders into their parent** (default; skip for `--all`): merge each FOLD folder's
   deterministic content nodes into its parent map, and drop its own map + index row — so the map set
   is the folders that carry architecture, not every docs/data folder (nothing vanishes; the content
   moves into the parent).
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan.py" "<root>" --apply-fold
   ```

7. **Stamp the drift baseline** (all tiers):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ctx_staleness.py" stamp-all "<root>"
   ```

8. **Write the pointer block into CLAUDE.md AND AGENTS.md** — via the splice helper only:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/claudemd_splice.py" claudemd "<root>/CLAUDE.md"
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/claudemd_splice.py" claudemd "<root>/AGENTS.md"
   ```
   If either reports `REFUSED` (malformed markers, usually a hand-edit), stop and report it — do not
   fix the file yourself.

9. **Self-verify + report:**
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/audit.py" check "<root>"
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/audit.py" savings "<root>"
   ```
   `check` must PASS (every node traces to a real file). Report: the tier used, how many folders were
   DEEP-enriched vs SKELETON vs FOLDed (and any borderline you adjusted), any folders the repair loop
   re-ran (and any it couldn't fix), the pointer splice result, the `check` result, and the `savings`
   line. If `check` still fails after the repair loop, surface it plainly — do not report success.

If maps already exist, prefer `/context-os-update` for a lighter, drift-only refresh.
