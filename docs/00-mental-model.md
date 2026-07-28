# 00 — The mental model

Every chapter in `docs/` builds on the same tiny example: the two-service app committed at
`demo/` (`demo/api/` — a Python "item store" service; `demo/web/` — its TypeScript browser
client). By the end of chapter 07 you'll have driven that one example through the whole
pipeline yourself. This chapter is the "why," with one real number to anchor it.

## The problem

A fresh AI session doesn't know your repo. Before it can help you, it re-derives the
architecture from scratch: reading files, grepping, working out what calls what. On a
large repo that's real, repeated cost — hundreds of thousands of tokens, every session,
before any actual work happens. It's also why moving a project to another model, or just
starting a new chat, feels like starting over.

## The fix, in one sentence

context-os scans your repo **once** and writes a small **map** next to each folder — what's
in it, how the pieces connect, what's risky to touch — so a session reads the map instead of
re-scanning the source. When code changes, the affected map flags itself `DRIFTED` instead of
quietly going stale.

## How it fits together (read bottom-up)

```
                     your source files (demo/api/, demo/web/)
                                    │
                                    │ scanned once (scripts/scan.py — no LLM)
                                    ▼
                     map-{folder}.ngf.md  +  index.ngf.md
                     (small text files, committed next to your code)
                                    │
                                    │ read on demand instead of re-scanning
                                    ▼
                     CLAUDE.md / AGENTS.md pointer block
                     ("read the map before you explore")
                                    │
                                    │ kept honest automatically
                                    ▼
              hooks flip a map to DRIFTED the moment its folder's
              code changes — so a stale map warns you, it never lies
```

The generation cost is paid once (roughly one cold exploration). Every session after that
*can* read the map instead — chapters 03 and beyond show how context-os checks whether it
actually did.

## The one real number for this chapter

The maps for `demo/` are already committed in this repo — real context-os output, not a
mockup. Run this from the repo root:

```bash
python3 scripts/audit.py savings demo
```

Expected output (verified against this repo — yours will match, since it reads the
committed `demo/` maps as-is):

```
CEILING: the context-os map set is ~601 tokens vs ~1290 to scan 11 source files cold (53.4% smaller). This is the MOST a session could save, not what it did — realized only when the agent reads a map instead of re-reading its source. Measure the delivered number with `python3 measure.py session demo`. (~4 chars/token estimate.)
```

Read that number honestly, the way context-os itself insists on:

- **53.4% smaller** is a **ceiling** — an artifact-size fact about `demo/`, computed from the
  actual files on disk. It is real, but it is not a claim about what any given session did.
- `demo/` is a deliberately tiny example (5 source files). The ratio *grows* with real
  repos — a big project's governance-card overhead is fixed-size while its source keeps
  growing, so the saving compounds. (See the README's own worked number: 188 source files →
  93% smaller.)
- **Delivered** is a separate, smaller claim: did *this session* actually read the map
  instead of re-reading the source? That's a behavioral question, not an artifact-size one —
  chapter 03 measures it for real.

## What you'll build, chapter by chapter

1. **Ch 01** — generate a fresh skeleton map for `demo/` yourself (no LLM, seconds, `$0`).
2. **Ch 02** — read a map's two parts (the card, the graph) using the real enriched `demo/`
   maps already committed here.
3. **Ch 03** — edit the demo's source, watch the map flip `DRIFTED`, and bring it back
   `verified` — and see that a pure reformat does *not* count as drift.
4. **Ch 04** — see how context-os decides which folders are worth full enrichment (`plan.py`),
   and the lazy `--skeleton` → `/context-os-catchup` flow.
5. **Ch 05** — pull the *exact* original source behind a map node by reference (CCR), and see
   the same thing happen over a real MCP JSON-RPC exchange.
6. **Ch 06** — map non-code files (config/docs/data/logs), not just source.
7. **Ch 07** — capture a session into one portable file and see what a cold reader gets.

Next: **[01 — your first map](01-your-first-map.md)**.
