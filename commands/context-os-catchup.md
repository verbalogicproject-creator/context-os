---
description: Enrich only the folders you actually worked in this session — the lazy/on-demand companion to a cheap skeleton-first map. Pay for the folders you touched, not the whole repo.
argument-hint: "[project-root] (optional — defaults to the current directory)"
---

# /context-os-catchup

The lazy way to map a repo. Instead of enriching every folder up front, you map the whole repo
as **skeletons once** (`/context-os --skeleton` — real nodes + edges + drift, no LLM, `$0`), then
run this whenever you like: it enriches **only the folders this session actually touched** and that
are still skeleton-only. Enrichment cost tracks real use — you pay for the ~handful of folders you
worked in, not the hundreds you didn't.

It reads the per-session ledger the drift hook already keeps (`.context-os/reads-<session>.jsonl`):
every folder whose source you read or grepped is "touched." Of those, the ones whose map is still a
bare skeleton are the catch-up set.

## Request

$ARGUMENTS

## Protocol

1. **Resolve the project root.** Use `$1` if given, else the current directory. If there's no
   `index.ngf.md`, the repo isn't mapped yet — say so and suggest `/context-os --skeleton` first
   (the cheap, `$0` skeleton pass that lazy mode builds on). Do not invent maps here.

2. **Find the catch-up set** — folders touched this session whose map is still skeleton-only:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/measure.py" catchup "<root>"
   ```
   If it prints nothing, report plainly: every folder you touched is already enriched (or you
   haven't touched a mapped folder yet) — nothing to do. Stop.

3. **Enrich exactly that set.** Dispatch one `context-os:map-enricher` agent per folder in the
   list, in **parallel batches of ~8–12**, each with `{project_root, folder}` (Haiku by default;
   pass `--premium` intent through if the user asked for Sonnet). Each enricher fills its own map's
   descriptions, edges, and risk card and returns one line. If an enricher fails, note the folder
   and continue — its map stays a valid skeleton.

4. **Repair loop** (same as `/context-os`): 
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/audit.py" repair-targets "<root>"
   ```
   For any folder that fails, delete its `map-*.ngf.md`, re-emit its skeleton
   (`scan.py "<root>" --emit-ngf`), re-enrich it, and re-check — at most **2 rounds**. Leave and
   report anything still failing.

5. **Re-stamp + verify:**
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ctx_staleness.py" stamp-all "<root>"
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/audit.py" check "<root>"
   ```
   `check` must PASS. Report which folders you enriched this catch-up, any the repair loop couldn't
   fix, and the `check` result. Do not report success if `check` still fails.

## The lazy flow, end to end

```
/context-os --skeleton        # once: whole repo as skeletons, $0, instant
… work in the repo …          # the hook logs which folders you touch
/context-os-catchup           # enrich just the folders you touched, on demand
```

Re-run catch-up any time — it only ever enriches the newly-touched skeleton folders, never
re-does an already-enriched one.
