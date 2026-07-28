# 07 — Snapshot: stopping and resuming cold

Everything so far — maps, drift, retrieval, non-code nodes — describes the *code*. This
chapter is about a different problem: capturing *where you are in a session* so you (or a
different model, on a different machine) can pick the work back up without you re-explaining
it.

`/snapshot` is orthogonal to the rest of context-os: it isn't drift-checked, it doesn't need
`index.ngf.md` to exist, and unlike a map it's meant to be read **once**, at cold start — so
it's allowed to be a little more prose-heavy than the single-`ctx`-block rule the maps hold
to (see `SPEC.md` §4).

## Scaffold one

`scripts/snapshot.py` does only the mechanical part — recording git state and every map's
hash at this moment, archiving any previous snapshot — and leaves the actual narrative for
the agent holding the conversation to fill in (a subagent can't see your session, which is
why `/snapshot` always runs in the main session, never dispatched):

```bash
python3 scripts/snapshot.py scaffold /tmp/cos-tutorial --goal "Walked the context-os docs/ tutorial end to end"
```

```
scaffolded /tmp/cos-tutorial/snapshot.ngf.md
Next: fill in ## summary and the work-state ```ctx block from the conversation.
```

## What it captured

```bash
cat /tmp/cos-tutorial/snapshot.ngf.md
```

````
---
id: snapshot
kind: snapshot
created: 2026-07-27T13:43:45Z
goal: "Walked the context-os docs/ tutorial end to end"
git_branch: (no git)
git_head: (none)
git_dirty: false
maps_at_capture:
  - {path: api/map-api.ngf.md, structural_hash: sha256:344e2dd522868e74, staleness: verified}
  - {path: config/map-config.ngf.md, structural_hash: sha256:e3b0c44298fc1c14, staleness: verified}
  - {path: data/map-data.ngf.md, structural_hash: sha256:e3b0c44298fc1c14, staleness: verified}
  - {path: docs/map-docs.ngf.md, structural_hash: sha256:e3b0c44298fc1c14, staleness: verified}
  - {path: logs/map-logs.ngf.md, structural_hash: sha256:e3b0c44298fc1c14, staleness: verified}
  - {path: map-root.ngf.md, structural_hash: sha256:e3b0c44298fc1c14, staleness: verified}
  - {path: web/map-web.ngf.md, structural_hash: sha256:57c7fd21811ad906, staleness: verified}
re_establish:
  - "(agent: what a fresh machine must set up — install deps, env vars, running services)"
---

## summary

<!-- agent: replace this with a compacted narrative of THIS session — what was
     discussed, decided, tried, and rejected, and WHY. Relative paths only; no
     machine-specific absolute paths or running-server assumptions. -->

```ctx
# work-state — decisions, artifacts, and what is next
# format: ctx/1.1
# node types: [decision] [task] [open] [artifact] [next]
# edges: -> leads-to | ~> depends-on | => supersedes
## state
  # agent: fill with the real work-state, e.g.:
  #   d1 : chose X over Y because Z [decision]
  #   a1 : the artifact built so far [artifact] -> n1
  #   n1 : the very next action [next]
  #   o1 : still-open question [open]
  # code pointers use file:symbol (robust to line drift), e.g. scan.py:to_per_folder_ngf
```
````

Three things worth noticing:

- **`created`** is a real ISO timestamp from the moment you ran this — yours will differ,
  and that's correct (a snapshot is point-in-time by design).
- **`git_branch`/`git_head`: `(no git)`** — `/tmp/cos-tutorial` isn't a git repo, so
  `snapshot.py` says so plainly instead of guessing. In an actual project, you'd see the real
  branch and commit SHA here.
- **The four content-only folders (`config`, `data`, `docs`, `logs`) all share the same
  `structural_hash`** (`sha256:e3b0c44298fc1c14`). That's not a bug — the structural hash is
  computed only from *architecture-bearing* lines (imports and declarations), and a folder
  with zero code files has none, so every such folder hashes to the same "empty" signature.
  `api/` and `web/` — the folders that actually hold code — each keep their own distinct hash.

This is the mechanical scaffold, not the finished snapshot: the placeholders in `## summary`
and the `ctx` block are exactly that — comments telling the agent what to write, in this
session's own words. A real `/snapshot` run (inside Claude Code) fills those in from the
actual conversation before reporting done; this script only ever produces the scaffold.

## Resuming cold

To hand this off — to another machine, or to a different model entirely — you'd copy the
project plus `snapshot.ngf.md`, and point a fresh session at the snapshot file. It reads
(in order): the frontmatter (goal, git state, each map's hash *at capture* — so it can tell
if code moved since), the `## summary` narrative, and the work-state graph with its
`file:symbol` pointers — then drills into only the maps it actually needs, exactly like
`index.ngf.md` in chapter 02.

Run `/snapshot` again later and the previous one is archived, not overwritten:

```bash
python3 scripts/snapshot.py scaffold /tmp/cos-tutorial --goal "A second pass"
ls /tmp/cos-tutorial/.context-os/snapshots/
```

```
scaffolded /tmp/cos-tutorial/snapshot.ngf.md
archived previous -> /tmp/cos-tutorial/.context-os/snapshots/20260727T134345Z.ngf.md
Next: fill in ## summary and the work-state ```ctx block from the conversation.
```
```
20260727T134345Z.ngf.md
```

(Your archived filename is a compact timestamp derived from the first snapshot's `created`
field, not the one shown above verbatim — the exact digits will differ by the second.)

## Verify your build

```bash
test -f /tmp/cos-tutorial/snapshot.ngf.md && echo "current snapshot present"
ls /tmp/cos-tutorial/.context-os/snapshots/ | wc -l
```

You should see `current snapshot present` and a count of `1` archived snapshot (from the
first scaffold, before the second one replaced it).

## Where this leaves you

You've now driven the whole pipeline on one running example: generated a map (01), read it
(02), drifted and healed it (03), seen how enrichment is targeted and cost-controlled (04),
retrieved an exact original two ways (05), mapped the non-code parts of the project (06),
and captured the session for cold resume (07). That's the whole surface `README.md` and
`HOW-TO-USE.md` describe — this is the version where you ran every command yourself.

For the next level of detail: `CODEBASE-REPORT.md` maps context-os's *own* code
module-by-module, `SPEC.md` is the formal file-format spec, and `ROADMAP.md` is what's next
(honestly labelled as unbuilt).
