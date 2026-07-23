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
3. **Report the CEILING (artifact size) and grounding**:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/audit.py" savings "<project_root>"
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/audit.py" check "<project_root>"
   ```
4. **Report the DELIVERED number for this session** (behavioral — what the agent actually
   did, from the read ledger; prints a friendly message if nothing's been logged yet):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/audit.py" session-savings "<project_root>"
   ```
5. **Summarize** honestly, keeping the two numbers distinct: total maps and how many are
   `DRIFTED` (and which folders); the **ceiling** (how much smaller the maps are than
   source) as an upper bound, *not* a delivered figure; the **delivered** map-consultation
   rate for this session if any reads were logged; and whether `check` passed. If anything
   is `DRIFTED`, point to `/context-os-update`. Never present the ceiling as tokens actually
   saved, and never report "all current" unless `status` actually said so.
