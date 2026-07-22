<!-- context-os:start -->
## Architecture map — read before exploring
This repo is mapped for cheap, cold orientation. Before reading source files or
launching explore/search agents to understand how the code fits together, read the
map — it is the architecture at a fraction of the tokens.

1. Start at `index.ngf.md` (repo root) — it routes you to the folder you need.
2. Read that folder's `map-*.ngf.md` for its graph (`->` calls, `~>` reads, `=>` HTTP).
3. Before you EDIT, check that map's frontmatter `risk_areas` / `safe_edit_points`.

Do NOT fan out exploration agents to reconstruct architecture the maps already document.
If a map's frontmatter says `staleness: DRIFTED`, trust that folder loosely and verify
against source — for that folder only.
<!-- context-os:end -->
