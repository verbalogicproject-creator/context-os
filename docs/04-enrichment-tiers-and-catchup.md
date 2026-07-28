# 04 — Enrichment tiers, ranking, and catch-up

Chapter 01's skeleton and chapter 02's enriched map documented the *same* three files. The
gap between them — one-line descriptions, verified edges beyond plain imports, and the
`safe_edit_points`/`risk_areas` governance card — is the only part of context-os that costs
tokens. This chapter is about *how much of that gap you choose to pay for, and where*.

## The one part that costs anything

Everything you ran in chapters 01 and 03 — `scan.py`, `ctx_staleness.py`, `claudemd_splice.py`,
`audit.py` — is stdlib Python: deterministic, free, offline. The only step with a real cost is
**enrichment**: an LLM agent (`agents/map-enricher.md`) reading a folder's code and writing its
descriptions and risk card. That step only runs inside a live Claude Code session (it's a
subagent dispatch, not a script you can call from a terminal) — so this chapter shows you the
**deterministic** decision of *which folders would be enriched*, using the real committed
output from chapter 02 as "here's what that step produces."

`/context-os` has a dial for this, because enrichment is the one place cost and quality trade
off against each other:

| Invocation | Enrichment | Cost |
|---|---|---|
| `/context-os --skeleton` (`--fast`) | none — what chapter 01 did | free, seconds, no LLM |
| `/context-os` (default) | descriptions + risk cards, Haiku, fanned out one small agent per folder in parallel | cheap |
| `/context-os --premium` | the same, on Sonnet | higher, best prose/risk quality |

## Ranking: map what matters, not every folder

Even at the cheap tier, enriching *every* folder in a large repo pays for folders a session
never opens. `scripts/plan.py` ranks folders from the scan graph alone (real code? an import
hub? an entry point?) — no LLM — into three tiers:

- **DEEP** — real code, or other folders import it → worth enriching.
- **SKELETON** — small or peripheral → keep the free skeleton, skip the enricher.
- **FOLD** — pure docs/data/config → merge into the parent's map instead of getting its own.

Run it against the tutorial project from chapter 01:

```bash
python3 scripts/plan.py /tmp/cos-tutorial
```

```
TIER      code  in out  E  score  folder
DEEP         3   0   0  Y    6.0  api *
SKELETON     2   0   0  Y    5.0  web *
FOLD         0   0   0       0.0  .

DEEP 1  ·  SKELETON 1  ·  FOLD 1   (3 folders)   * = borderline (2, agent may adjust)
Enrich only the 1 DEEP folders; skeleton 1; fold 1 content folders into their parent.
```

Read honestly: on a project this tiny, both real code folders are `*` (borderline) — the
ranker is telling you it's not confident, and an orchestrating agent may promote `web` to
DEEP too (it does, in the real committed `demo/`, which has both `api/` and `web/` fully
enriched — a human/agent judgment call the ranker flags rather than hides). The root (`.`,
just `README.md`/`CLAUDE.md`/`AGENTS.md`) is FOLD — pure docs, no code — and gets merged into
whichever parent map makes sense rather than a map of its own.

`--deep-only` prints just the enrich list, the input `/context-os` actually dispatches
agents against:

```bash
python3 scripts/plan.py /tmp/cos-tutorial --deep-only
```

```
api
```

## What enrichment actually adds (the real output, from chapter 02)

`/context-os` dispatches one `context-os:map-enricher` agent per DEEP folder (`api`, here),
each in its own isolated context — that's what lets a 50-folder repo fan out cheaply instead
of growing one context across all of them. Its rule, verbatim from `agents/map-enricher.md`:

> The boundary you embody: **derive, never fabricate.** Every description and every added
> edge or risk traces to something you actually read.

Concretely, comparing chapter 01's skeleton to chapter 02's real, committed
`demo/api/map-api.ngf.md`:

| | Skeleton (ch. 01) | Enriched (ch. 02, real) |
|---|---|---|
| `main` node | `api/main.py` | `App factory — builds the app and registers routes over a shared Store` |
| Card | none | `safe_edit_points`, `risk_areas`, `depends_on`, `audience` |
| Edges | `->` only, from imports | same `->` edges (never re-derived — the enricher trusts the scanner), plus any verified `~>`/`=>`/`[ext]` the scanner couldn't see |

The enricher never touches the `->` edges the scanner already resolved, never renames a
node, and never invents a risk for a folder that doesn't warrant one — a good set of grounded
descriptions is a complete, honest result for a low-risk leaf folder.

## Going lazy: pay only for what you touch

Even enriching just the DEEP folders up front can pay for folders a given session never
opens. The lazy alternative:

```
/context-os --skeleton        # once: whole repo as skeletons, $0, instant — chapter 01
… work in the repo …          # the PreToolUse hook logs which folders you actually touch
/context-os-catchup           # enrich only those folders, on demand
```

`/context-os-catchup`'s targeting is deterministic and inspectable the same way `plan.py` is —
`scripts/measure.py catchup` reads the session's read ledger (`.context-os/reads-<session>.jsonl`)
and lists touched-but-still-skeleton folders:

```bash
python3 scripts/measure.py catchup /tmp/cos-tutorial
```

```
no session ledger yet — nothing touched to catch up on
```

(You're seeing this because the ledger only exists once a real Claude Code session has read
or grepped something in this project — there isn't one here. Inside an actual session, this
would list exactly the folders you'd worked in but hadn't yet enriched.)

## Verify your build

Confirm the ranking is reproducible and the DEEP/SKELETON/FOLD counts add up to every folder
`scan.py` found in chapter 01 (3: `.`, `api`, `web`):

```bash
python3 scripts/plan.py /tmp/cos-tutorial --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(sorted(r['folder'] for r in d['folders']))"
```

```
['.', 'api', 'web']
```

Next: **[05 — retrieving originals (CCR) and the MCP server](05-retrieval-ccr-and-mcp.md)**,
where you pull the exact source behind any map node by reference.
