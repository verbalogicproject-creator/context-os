# 02 — Reading a map

Chapter 01 gave you a **skeleton**: real nodes and edges, placeholder descriptions. This
chapter reads the **enriched** version of that same folder — the one already committed at
`demo/api/map-api.ngf.md` — so you can see exactly what enrichment adds on top of the
skeleton, field by field.

```bash
cat demo/api/map-api.ngf.md
```

````
---
id: map-api
kind: context_map
folder: "api/"
format: ctx/1.1
last_verified: 2026-07-22
file_count: 3
audience: [ai-coder]
safe_edit_points:
  - "Add new endpoints in routes.py via register()"
  - "Add query/mutation methods on Store"
risk_areas:
  - "main.create_app — the app-factory wiring; changing the store/register order breaks startup"
  - "Store._items — the single source of item state; every read/write funnels through Store"
depends_on: ["web/ (called over HTTP: /items, /items/add)"]
structural_hash: sha256:014419841168d9a2
staleness: verified
---
```ctx
# api/ — in-memory item service
# format: ctx/1.1
# edges: -> call/render | ~> subscribe/read | => HTTP API call
## Files
  main : App factory — builds the app and registers routes over a shared Store [root] @entry @risk
    -> routes, store
  routes : Registers the /items and /items/add handlers against the Store [router]
    -> store
  store : In-memory item state; every read/write funnels through here [store] @risk
```
````

A map is two parts: a **card** (the `--- ... ---` YAML frontmatter) and a **graph** (the one
fenced ` ```ctx ` block). Nothing else — no prose section outside those two. That's
deliberate: if a node needed a paragraph, its one-line description would be too weak, not
the format.

## The card

| Field | What it tells you |
|---|---|
| `folder` | Which folder this documents (`"api/"`). |
| `file_count` | How many source files — cross-check against what you'd `ls`. |
| `safe_edit_points` | Where you can change things without surprises — here, adding a new
  endpoint in `routes.py`, or a new method on `Store`. |
| `risk_areas` | What breaks if you get it wrong, named plainly: get the store/register
  order wrong in `main.create_app` and startup breaks; `Store._items` is the one place all
  item state lives. |
| `depends_on` | Cross-folder dependencies at a glance — `api/` is called over HTTP by
  `web/`. |
| `structural_hash` / `staleness` | The drift baseline and its live verdict. Chapter 03 is
  entirely about this pair. |

Compare this to chapter 01's skeleton: same `folder`, same `file_count` — the deterministic
facts didn't change. What's new is everything an enricher had to actually *read the code* to
know: the governance card, and the descriptions below.

## The graph

```
# api/ — in-memory item service
# format: ctx/1.1
# edges: -> call/render | ~> subscribe/read | => HTTP API call
## Files
  main : App factory — builds the app and registers routes over a shared Store [root] @entry @risk
    -> routes, store
  routes : Registers the /items and /items/add handlers against the Store [router]
    -> store
  store : In-memory item state; every read/write funnels through here [store] @risk
```

Reading it line by line:

- `main : <description> [root] @entry @risk` — one node per file. `[root]` is a type hint
  (others you'll see: `[router]`, `[store]`, `[component]`, `[service]`, `[config]`,
  `[doc]`, `[ext]` for something outside this folder). `@entry` marks the folder's real
  entry point; `@risk` marks a node named in `risk_areas` above — the two are linked, never
  duplicated (the risk *text* lives in the card; the block just carries the pointer marker).
- `-> routes, store` — an edge. `->` means "calls / imports" (a hard dependency): `main`
  imports both `routes` and `store`. This came straight from the Python `import` lines — the
  same fact chapter 01's skeleton already had.
- `routes -> store` — `routes.py` imports `store.py` too.
- `store` has no outgoing edge — it's the leaf: everything ends up funneling into `Store`.

So the whole folder reads as one sentence: **`main` is the entry point, wiring `routes` and
`store` together; `routes` calls into `store`; `store` holds all the state, and is risky to
change.** That's the architecture of a 3-file folder, in about 60 tokens, without opening a
single file.

## The other two edge kinds

`api/`'s edges are all `->` (imports), but a map can carry two more, visible in
`demo/web/map-web.ngf.md`:

```bash
cat demo/web/map-web.ngf.md
```

````
---
id: map-web
kind: context_map
folder: "web/"
format: ctx/1.1
last_verified: 2026-07-22
file_count: 2
audience: [ai-coder, frontend-designer]
safe_edit_points:
  - "Item-list markup in app.render()"
risk_areas:
  - "client.fetchItems / client.addItem — the only calls into the api; the /items paths must match api/routes.py"
depends_on: ["api/ (called over HTTP: /items, /items/add)"]
structural_hash: sha256:57c7fd21811ad906
staleness: verified
---
```ctx
# web/ — browser client
# format: ctx/1.1
# edges: -> call/render | ~> subscribe/read | => HTTP API call
## Files
  app : Renders the item list; re-exports addItem [component] @entry
    -> client
  client : Fetch wrapper — the only calls into the api service [component] @risk
    => api
## External
  api : Python item service (see ../api/map-api.ngf.md) [ext]
```
````

Here `client => api` uses `=>`, "makes an HTTP call to" — a boundary the scanner can't see
from an import (there's no `import` from a TypeScript file to a Python one; someone had to
verify the actual `fetch()` calls). The target, `api`, is an `[ext]` node under `## External`
— a *folder-granularity* pointer to `api/map-api.ngf.md`, not a fabricated node inside
`web/`. (The third kind, `~>` "reads/subscribes to," shows up in state-store patterns this
tiny demo doesn't have — same idea: verified, not import-derived.)

## The root index, the same shape

`index.ngf.md` is the router: its "files" are folders, each with a drill-down edge.

```bash
cat demo/index.ngf.md
```

````
---
id: index
kind: context_index
root: "."
format: ctx/1.1
last_verified: 2026-07-22
usage: "Lazy-load — read this, then drill into ONLY the map you need; never scan source."
maintain: "Each map's staleness flag auto-flips on drift; run /context-os-update on DRIFTED folders."
---
```ctx
# index — project context router
# format: ctx/1.1
# edges: -> drill-down
## Folders
  api : 3 files — Python in-memory item service (app factory, routes, store) [dir] -> api/map-api.ngf.md
  web : 2 files — TypeScript browser client (render + fetch wrapper) [dir] -> web/map-web.ngf.md
```
````

An agent starts here, reads one line per folder, and drills into only the map it actually
needs — never the whole repo at once.

## Verify your build

Confirm the fabrication gate holds on the real, enriched `demo/`:

```bash
python3 scripts/audit.py check demo
```

```
PASS: derive-don't-fabricate — 8 node(s) checked (1 external-exempt), 0 unbacked
PASS: no instruction-shaped text in the map set
```

`8 node(s)` = `main`, `routes`, `store` (api) + `app`, `client`, `api` (web, incl. the
`[ext]` pointer) + `api`, `web` (the two `[dir]` nodes in `index.ngf.md`). The one
`external-exempt` node is `api`'s `[ext]` entry in `map-web.ngf.md` — it's exempt from
"trace to a real file" because it names another *folder*, not a file; that folder's own
existence is what `index.ngf.md`'s `[dir]` check verifies instead.

Next: **[03 — drift and staying honest](03-drift-and-staying-honest.md)**, where you change
the demo's code and watch this exact map react.
