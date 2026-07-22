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
