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
