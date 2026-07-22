---
description: Capture the current session — a compacted summary + the work-state — into one portable snapshot.ngf.md, so you can stop now and resume cold on another machine or model
argument-hint: [goal] (optional — a one-line note on what this session is about)
allowed-tools: Bash(python3:*), Read, Edit, Write, Glob
---

# /snapshot

Write a portable session snapshot so this work can be picked up cold — by a fresh
Claude session, or by Codex or Gemini, on this machine or another — without re-asking
what you were doing.

**You run this yourself, in this conversation** (not via a subagent) — because the
summary must come from *this session's context*, which only you hold. A subagent can't
see it.

## Request

$ARGUMENTS

## Protocol

1. **Resolve the project root** (current working directory unless the repo root is
   obviously elsewhere).

2. **Scaffold the file.** Derive a one-line `goal` from this session and run:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/snapshot.py" scaffold "<root>" --goal "<one-line goal>"
   ```
   This records the git state + each map's `structural_hash` at capture (so a cold
   reader can tell if code moved since), archives any previous snapshot, and writes a
   scaffold with a `## summary` placeholder and a work-state ` ```ctx ` block.

3. **Fill it in** — `Edit` `snapshot.ngf.md`:
   - **`## summary`** — a compacted narrative of *this session*: what was discussed,
     decided, tried, and rejected, and **why**. Enough that a cold reader understands
     the state and the reasoning, not just the outcome. **Relative paths only** — no
     machine-specific absolute paths, no "server running on :NNNN" as load-bearing.
   - **The work-state ` ```ctx ` block** — the real decisions, artifacts, open questions,
     and next steps as nodes (`[decision] [task] [open] [artifact] [next]`), with
     `file:symbol` code pointers (robust to line drift). Edges: `->` leads-to,
     `~>` depends-on, `=>` supersedes.
   - **`re_establish:`** (frontmatter) — what a fresh machine must set up before
     continuing (install deps, env vars, services to start).

4. **Report** the snapshot path (and the archived previous, if any). Tell the user this
   file + the repo is enough to resume cold: a fresh session reads `snapshot.ngf.md`,
   then the maps it references, and continues.

## Honesty

Summarize what actually happened — including what failed or was left unfinished. A
snapshot that overstates progress makes the cold resume worse, not better. If a decision
here belongs in durable project memory, say so.
