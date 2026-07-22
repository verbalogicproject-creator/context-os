---
description: Read-only — report each map's freshness (verified vs DRIFTED) and the current token-save, without changing anything
argument-hint: [project-root] (optional — defaults to the current directory)
allowed-tools: Bash(python3:*), Read, Glob
---

# /context-os-status

Show, at a glance, whether this project's maps are current — which folders have drifted
since their map was last verified, and how many tokens the maps are saving. Read-only:
it re-checks and reports, it does not re-author any map.

## Request

$ARGUMENTS

## Protocol

1. **Resolve the project root.** Use `$1` if given, else the current working directory.
   If no `index.ngf.md` exists, say so plainly and suggest `/context-os` to create the
   maps — do not invent a status.
2. **Report freshness** (this also refreshes each map's in-file flag against current
   source, so out-of-band changes are reflected):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ctx_staleness.py" status "<project_root>"
   ```
3. **Report the token-save and grounding**:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/audit.py" savings "<project_root>"
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/audit.py" check "<project_root>"
   ```
4. **Summarize** honestly: total maps, how many are `DRIFTED` (and which folders), the
   savings line, and whether `check` passed. If anything is `DRIFTED`, point to
   `/context-os-update`. Never report "all current" unless `status` actually said so.
