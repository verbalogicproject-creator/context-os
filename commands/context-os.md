---
description: Map this project into portable per-folder context files so a fresh session reads a cheap map instead of re-scanning your whole repo, and drop a pointer into CLAUDE.md + AGENTS.md
argument-hint: [project-root] (optional — defaults to the current directory)
---

# /context-os

Give this project a set of small, always-current architecture maps — one per folder
plus a root index — so Claude (and Codex, and Gemini) stop re-discovering your codebase
from scratch every session.

## What this does

Dispatches the `map-scout` agent (`${CLAUDE_PLUGIN_ROOT}/agents/map-scout.md`) against
`$1` (default: the current working directory) to:

1. Run the deterministic scanner (`${CLAUDE_PLUGIN_ROOT}/scripts/scan.py --emit-ngf`) to
   write grounded skeletons — one `map-{folder}.ngf.md` per folder + a root
   `index.ngf.md`, every node a real file, every `->` edge a real resolved import.
2. Read the real files and enrich each map: one-line descriptions, verified `~>`/`=>`
   edges, `@entry` markers, `collapse` for noise, and the frontmatter governance card
   (`safe_edit_points` / `risk_areas`) grounded in what would actually break.
3. Stamp the drift baseline (`ctx_staleness.py stamp-all`) into every map's frontmatter.
4. Write (or refresh) the marker-delimited pointer block in **CLAUDE.md and AGENTS.md**
   via the deterministic splice helper — never a free-form edit. (Claude reads the
   CLAUDE.md one; the AGENTS.md one makes the maps discoverable to Codex/Gemini too.)
5. Verify itself with `audit.py check` before reporting done, and print the token-save
   number (`audit.py savings`).

If maps already exist, prefer `/context-os-update` for a lighter, drift-only refresh.

## Request

$ARGUMENTS

## Protocol

1. **Resolve the project root.** Use `$1` if given, else the current working directory.
   Confirm it looks like a real project (has source files) before proceeding.
2. **Dispatch `map-scout`** with `{project_root}`. Let it run its full
   scan → enrich → stamp → splice → self-verify protocol.
3. **Report** exactly what `map-scout` returns: the maps written, the pointer blocks
   spliced (and any `.bak`), the `check` result, and the `savings` line. If `check`
   fails, this is not done — surface it and let `map-scout` fix it first.
