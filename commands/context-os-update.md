---
description: Refresh only the maps whose folder has drifted — diff-update against current source, re-stamp, and surface any removed nodes
argument-hint: [project-root-or-folder] (optional — defaults to the current directory)
---

# /context-os-update

Bring drifted maps current without regenerating everything and without silently losing
anything a map recorded.

## What this does

Dispatches the `map-updater` agent (`${CLAUDE_PLUGIN_ROOT}/agents/map-updater.md`) against
`$1` (default: the current working directory) to:

1. Re-check every map against current source (`ctx_staleness.py status`) — catching
   out-of-band changes too — and act only on the `DRIFTED` ones.
2. For each drifted folder: parse the existing map (`audit.py parse`), re-scan fresh
   (`scan.py`), diff, and update only what changed with grounded re-reads (new files,
   deleted files, changed edges, shifted risk).
3. Re-stamp each updated map's drift baseline; refresh `index.ngf.md` and the pointer
   block only if the top-level shape changed.
4. Report every removed node by name, and self-verify with `audit.py check`.

## Request

$ARGUMENTS

## Protocol

1. **Resolve the target.** Use `$1` if given (a project root, or a single folder to
   restrict to), else the current working directory. If `index.ngf.md` doesn't exist,
   stop and tell the user to run `/context-os` first.
2. **Dispatch `map-updater`** with `{project_root}` (and `{folder}` if one was named).
3. **Report** exactly what it returns: which maps were drifted, what changed per folder,
   **every node removed and why** (or "no nodes removed this run"), and the final
   `check` + `status` results. If anything still reads `DRIFTED` or `check` fails, it is
   not done.
