# context-os format specification — `ctx/1.1` + the three kinds

> **Status:** v0.1 (as implemented)
> **Author:** Eyal Nof
> **Format version:** `ctx/1.1` (additive minor bump over the `.ctx` v1.0 grammar)

context-os writes three kinds of `.ngf.md` file. Every one is **YAML frontmatter (a card)
+ one fenced ` ```ctx ` block** — with a single deliberate exception (a `snapshot` adds a
prose `## summary`). The `ctx` graph grammar inside the block is unchanged from `.ctx`
v1.0; `ctx/1.1` only moves the metadata that used to live in `#` header comments into the
YAML card, and adds the drift stamp.

| `kind:` | File | One per | Role |
|---|---|---|---|
| `context_index` | `index.ngf.md` | repo root | Router. Nodes are folders (`[dir]`) with drill-down edges to each map. |
| `context_map` | `map-{folder}.ngf.md` | folder | The folder's architecture graph + governance card. Lives inside the folder. |
| `snapshot` | `snapshot.ngf.md` | session | Portable session handoff: summary + work-state graph. Not drift-checked. |

Maps are glob-able as `**/map-*.ngf.md`. `kind:` is the authoritative discriminator.

---

## 1. `context_map` — `map-{folder}.ngf.md`

### 1.1 File shape

```
---
<the card — YAML frontmatter, §1.2>
---
```ctx
<the graph — ctx/1.1 body, §1.3>
```
```

The body is **exactly one fenced ` ```ctx ` block and nothing else**. No prose section: if a
node needs a paragraph, its one-line description is too weak — fix the description. (The
markdown container invites prose; the single-block rule is what preserves the token density
that is the whole point.)

### 1.2 The card (frontmatter)

**Written by the scanner (`scan.py --emit-ngf`):**

| Field | Meaning |
|---|---|
| `id` | Stable id, e.g. `map-src` (`map-` + the folder path, slugified). |
| `kind` | `context_map`. |
| `folder` | The folder this documents, repo-relative (`"src/"`, or `"."` for the root). |
| `format` | `ctx/1.1`. |
| `last_verified` | ISO date the map was last generated/updated against source. |
| `file_count` | Source files in the folder. |

**Written by the enrichment pass (`map-scout`) — the governance card:**

| Field | Meaning |
|---|---|
| `safe_edit_points` | List: what is safe to change in this folder. |
| `risk_areas` | List: what breaks if touched wrong (name the node + the failure). A node named here should carry a trailing `@risk` marker in the block. |
| `audience` | (optional) e.g. `[ai-coder, frontend-designer]`. |
| `depends_on` | (optional) cross-folder / external dependencies at a glance. |

**Written by the drift stamp (`ctx_staleness.py stamp`):**

| Field | Meaning |
|---|---|
| `structural_hash` | The folder's last-known-good signature (§3). The baseline. Only `stamp` writes it. |
| `staleness` | The live verdict: `verified` \| `DRIFTED — …` \| `unstamped`. Only `flip` writes it. |

Governance lives in the card only; the block never duplicates a risk's text — a node just
carries the `@risk` pointer marker. This keeps the frontmatter and the block from drifting
against each other.

### 1.3 The graph (`ctx/1.1` block body)

Block header — three comment lines only (everything else migrated to the card):

```
# {folder}/ — architecture
# format: ctx/1.1
# edges: -> call/render | ~> subscribe/read | => HTTP API call
```

Body grammar is `.ctx` v1.0, unchanged: `##`/`###` groups; nodes
`name : description [type]` with optional `@entry` / `@hot` / `@risk` / `~NNNL` markers;
inline edges `->` (call), `~>` (subscribe/read), `=>` (HTTP); collapse
`... (N) : a, b, c [type]`; an `## External` group for `[ext]` systems. Node names are the
scanner's repo-unique names (a bare stem, or `dir/stem` only where two files share a stem
repo-wide) so every non-`[ext]`/`[dir]` node resolves to a real file — this is what the
`check` audit verifies.

---

## 2. `context_index` — `index.ngf.md`

Same shape (frontmatter + one ` ```ctx ` block), minimally filled. Its nodes are the repo's
source folders as `[dir]` nodes, each with a drill-down edge to that folder's map:

```
## Folders
  src : 188 files — Next.js frontend: chat, game, dashboard [dir] -> src/map-src.ngf.md
  backend : 145 files — FastAPI: routers, services, tests [dir] -> backend/map-backend.ngf.md
## External
  geminiAPI : Gemini Live API — voice WebSocket [ext]
```

A `[dir]` node's name is the real directory path, so the `check` audit accepts it (the
directory exists). Frontmatter carries `usage` and `maintain` one-liners; the full
lazy-load / anti-drift protocol lives once in the CLAUDE.md/AGENTS.md pointer block, not
repeated per file.

---

## 3. Staleness — the structural hash

`structural_hash` = a cheap, order-insensitive, **non-recursive** hash of a folder's
*architecture-bearing lines only* — imports (edges) and top-level declarations (nodes) —
sorted, per source file. Stdlib only, bounded by one folder's files (<50ms). It is
deliberately **semantic, not temporal**: a reformat, a comment change, or a `git clone`
(which rewrites mtimes) does **not** count as drift; an added/removed file, import, or
declaration does.

- `stamp` records the current signature as `structural_hash` and sets `staleness: verified`.
- `flip` recomputes the signature and compares: equal → `verified`; different → `DRIFTED …`;
  no baseline → `unstamped`. It only rewrites the `staleness` line, never the baseline.

The verdict lives **inside the map file**, so any tool — Claude, Codex, Gemini, hook or no
hook — sees `staleness: DRIFTED` just by reading the map. The Claude Code hooks
(PostToolUse on source edits, PreToolUse on map reads) only keep that in-file flag true.

The contract is **honesty, not freshness**: a `DRIFTED` map is still useful (structure
drifts slowly, and drift is localized to the touched folder) — an agent trusts a `DRIFTED`
folder's structure loosely and verifies against source, for that folder only.

---

## 4. `snapshot` — `snapshot.ngf.md`

The one kind that bends the single-block rule, because it is read **once at cold-start**
(completeness > density), not every session. Three parts:

1. **Frontmatter** — `id`, `kind: snapshot`, `created`, `goal`, git state
   (`git_branch`/`git_head`/`git_dirty`), `maps_at_capture` (each map's `structural_hash`
   + `staleness` at capture, so a cold reader can tell if code moved since), and a
   `re_establish` list (what a fresh machine must set up).
2. **`## summary`** — a compacted narrative of the session: discussed / decided / tried /
   rejected, and *why*. **Relative paths only; no machine-state as load-bearing.**
3. **A ` ```ctx ` work-state graph** — node types `[decision] [task] [open] [artifact]
   [next]`; edges `->` leads-to, `~>` depends-on, `=>` supersedes; `file:symbol` code
   pointers (robust to line drift).

Snapshots **age, they don't drift** — they are point-in-time, versioned by archiving the
previous one under `.context-os/snapshots/<timestamp>.ngf.md`. No staleness hook applies.
The summary must be written by the agent that holds the conversation (a subagent can't see
it), so `/snapshot` runs in the main session; `scripts/snapshot.py` does only the
mechanical scaffolding.

---

## 5. Validation

A map is **valid** if: frontmatter parses and carries the required `context_map` fields; the
body is exactly one ` ```ctx ` block; the block header has `format: ctx/1.1` + an `edges:`
legend; every node name is unique in the block; every non-`[ext]` node resolves to a real
file (`audit.py check`), and every `[dir]`/index node names a real directory.

It is **well-formed** if additionally: every name in `risk_areas` that looks like a node ref
exists in the block; `staleness` is honestly `verified` or `DRIFTED`; and `last_verified` is
within policy or the map is honestly `DRIFTED`.
