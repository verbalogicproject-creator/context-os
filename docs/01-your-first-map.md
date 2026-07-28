# 01 — Your first map

In this chapter you generate a map set from scratch, on a scratch copy of `demo/`, using
only the deterministic scanner — no LLM, no Claude Code session required. This is exactly
what `/context-os --skeleton` does inside Claude Code; running the script directly just
lets you see each step (and is how this repo's own CI verifies itself — see
`.github/workflows/ci.yml`).

## Set up a scratch copy

Run this from the `context-os` repo root:

```bash
cp -r demo /tmp/cos-tutorial
find /tmp/cos-tutorial -name '*.ngf.md' -delete
find /tmp/cos-tutorial -type f | sort
```

```
/tmp/cos-tutorial/AGENTS.md
/tmp/cos-tutorial/CLAUDE.md
/tmp/cos-tutorial/README.md
/tmp/cos-tutorial/api/main.py
/tmp/cos-tutorial/api/routes.py
/tmp/cos-tutorial/api/store.py
/tmp/cos-tutorial/web/app.ts
/tmp/cos-tutorial/web/client.ts
```

That's the whole example: a Python service (`api/`, 3 files) and a TypeScript client
(`web/`, 2 files), plus the plugin's own `CLAUDE.md`/`AGENTS.md` (already carrying the
pointer block from a previous run — you'll see that matters in a moment).

## Scan it

```bash
python3 scripts/scan.py /tmp/cos-tutorial --emit-ngf --emit-digests
```

Real output:

```
scanned 8 files, 4 imports (4 resolved to project edges)
wrote 4 map skeleton(s) + index into /tmp/cos-tutorial
wrote 3 folder digest(s) into /tmp/cos-tutorial/.context-os/digests
```

("8 files" counts the 5 source files *and* the 3 root-level `.md` files — context-os maps
non-code files too, see chapter 06. "4 imports" are `main.py`→`store.py`, `main.py`→
`routes.py`, `routes.py`→`store.py`, and `app.ts`→`client.ts`.)

## Look at what it wrote

```bash
cat /tmp/cos-tutorial/index.ngf.md
```

````
---
id: index
kind: context_index
root: "."
format: ctx/1.1
last_verified: 2026-07-27
usage: "Lazy-load — read this, then drill into ONLY the map you need; never scan source."
maintain: "Each map's staleness flag auto-flips on drift; run /context-os-update on DRIFTED folders."
---
```ctx
# index — project context router
# format: ctx/1.1
# edges: -> drill-down
## Folders
  . : 3 files [dir] -> map-root.ngf.md
  api : 3 files [dir] -> api/map-api.ngf.md
  web : 2 files [dir] -> web/map-web.ngf.md
```
````

(`last_verified` will show *today's* date when you run it — that's expected, it's stamped
at generation time, not hardcoded.)

```bash
cat /tmp/cos-tutorial/api/map-api.ngf.md
```

````
---
id: map-api
kind: context_map
folder: "api/"
format: ctx/1.1
last_verified: 2026-07-27
file_count: 3
---
```ctx
# api/ — architecture (auto-generated skeleton, descriptions pending)
# format: ctx/1.1
# edges: -> call/render | ~> subscribe/read | => HTTP API call
## Files
  main : api/main.py [root]
    -> routes, store
  routes : api/routes.py [router]
    -> store
  store : api/store.py [store]
```
````

Notice two things:

- **The `->` edges are already real**, resolved from the actual `import` statements — this
  is the deterministic part, and it's the same in every generation tier.
- **The description is a placeholder** (`main : api/main.py`, not "the app factory that
  wires the store to the routes"). That's the one thing an LLM enrichment pass adds — see
  chapter 04. The header even says so: `descriptions pending`.

This skeleton is already useful on its own: it's real, grounded structure at `$0`, and it's
what `check` gates against (chapter 03 covers that gate in the context of drift).

## Finish the deterministic pipeline

Two more steps make this a *usable* map set — stamping a drift baseline, and telling an
agent where to look (via `CLAUDE.md`/`AGENTS.md`):

```bash
python3 scripts/ctx_staleness.py stamp-all /tmp/cos-tutorial
python3 scripts/claudemd_splice.py claudemd /tmp/cos-tutorial/CLAUDE.md
python3 scripts/claudemd_splice.py claudemd /tmp/cos-tutorial/AGENTS.md
```

```
stamped 3 map(s)
no change needed: /tmp/cos-tutorial/CLAUDE.md
no change needed: /tmp/cos-tutorial/AGENTS.md
```

("no change needed" because `demo/`'s `CLAUDE.md`/`AGENTS.md` already carry the pointer
block from when this repo's own demo was generated — the splice is idempotent, so
re-running it against an already-spliced file is always a safe no-op. If you spliced into a
project's `CLAUDE.md` for the first time, you'd see `spliced: …` instead.)

## Verify your build

```bash
python3 scripts/audit.py check /tmp/cos-tutorial
```

```
PASS: derive-don't-fabricate — 11 node(s) checked (0 external-exempt), 0 unbacked
PASS: no instruction-shaped text in the map set
```

If you see `PASS` with `0 unbacked`, your map set matches this chapter: every node in every
map traces to a real file the scanner actually found. That's the mechanical half of "never
invents a node" — chapter 03 shows what a *fabricated* node looks like and how this same
gate catches it.

Next: **[02 — reading a map](02-reading-a-map.md)**, where you'll compare this skeleton
against the real, enriched version of the same folder already committed in this repo.
