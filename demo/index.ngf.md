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
