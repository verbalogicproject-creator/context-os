# context-os — user manual

A complete guide to using context-os. For a 30-second install, see **`INSTALL.md`**. For
the file format's technical spec, see **`SPEC.md`**.

---

## Contents

1. [What context-os is (the 2-minute version)](#1-what-context-os-is)
2. [Your first run](#2-your-first-run)
3. [The four commands](#3-the-four-commands)
4. [How to read a map](#4-how-to-read-a-map)
5. [The daily workflow — drift](#5-the-daily-workflow--drift)
6. [Committing maps to git](#6-committing-maps-to-git)
7. [Stopping and resuming — /snapshot](#7-stopping-and-resuming--snapshot)
8. [Privacy & security](#8-privacy--security)
9. [FAQ](#9-faq)
10. [Troubleshooting](#10-troubleshooting)
11. [Advanced: running the scripts directly (CI)](#11-advanced-running-the-scripts-directly)

---

## 1. What context-os is

A fresh AI session doesn't know your codebase. So before it helps you, it re-derives the
architecture from scratch — reading files, grepping, working out what connects to what.
On a large repo that's hundreds of thousands of tokens, **every session**. It's slow, it's
expensive, and it's why switching to another model feels like starting over.

context-os writes a small **map** of each folder — what's in it, how the pieces connect,
and what's risky to change — as a plain text file that lives next to your code. A fresh
session reads the map instead of re-scanning everything. The maps are plain Markdown, so
Claude, Codex, and Gemini all read them the same way, cold. And when your code changes,
the affected map marks itself `DRIFTED`, so a stale map warns you instead of misleading
you.

You generate the maps once (`/context-os`). After that they mostly look after themselves.

---

## 2. Your first run

Open a project in Claude Code and run:

```
/context-os
```

It will:

1. **Scan** your repo — find the real source files and the imports between them.
2. **Read** those files and write, for each folder, a `map-{folder}.ngf.md` (the folder's
   map) plus a `index.ngf.md` at the repo root (a table of contents).
3. **Add a short pointer** to your `CLAUDE.md` and `AGENTS.md` telling any AI agent to read
   the map before exploring. (Your existing content is untouched — it only adds its own
   marked block, and backs the file up first.)
4. **Print the token-save**, measured against your actual source.

Now just work normally. Because of the pointer, a fresh session reads the map for the
folder it's touching instead of re-scanning your repo. You don't do anything — that's the
point.

---

## 3. The four commands

| Command | What it does | When to run it |
|---|---|---|
| **`/context-os`** | Generate (or fully refresh) the maps + the pointer block; print the token-save. | Once per project, and any time you want to rebuild from scratch. |
| **`/context-os-update`** | Refresh **only** the folders whose code drifted since their map was verified. Reports every node it removes, by name. | When `/context-os-status` shows drift. Optionally scoped: `/context-os-update src/api`. |
| **`/context-os-status`** | Read-only. Lists each map as `verified` or `DRIFTED`, and the current token-save. Changes nothing. | Anytime you want to know if the maps are current. |
| **`/snapshot`** | Capture the current session — a summary + the work-state — into one portable file for cold resume. | Before you stop, switch machines, or hand off to another model. See §7. |

---

## 4. How to read a map

The maps are meant to be read by AI agents, but they're plain text and easy for you to read
too. A map has two parts: a **card** (the `--- … ---` header) and a **graph** (the fenced
` ```ctx ` block).

```
---
kind: context_map
folder: "api/"
safe_edit_points:
  - "Add new endpoints in routes.py via register()"
risk_areas:
  - "Store._items — the single source of item state; every read/write funnels through Store"
structural_hash: sha256:0144…          ← the drift baseline (managed for you)
staleness: verified                     ← verified, or DRIFTED
---
```ctx
# api/ — in-memory item service
# edges: -> call/render | ~> subscribe/read | => HTTP API call
## Files
  main : App factory — builds the app and registers routes [root] @entry @risk
    -> routes, store
  routes : Registers the /items handlers against the Store [router]
    -> store
  store : In-memory item state; every read/write funnels through here [store] @risk
```
```

**The card** tells you, at a glance:
- `safe_edit_points` — what's safe to change here.
- `risk_areas` — what breaks if you get it wrong.
- `staleness` — whether the map is current (`verified`) or the code moved under it (`DRIFTED`).

**The graph** is a list of the folder's files (nodes) and how they connect (edges):
- `name : description [type]` — one file. `[type]` is a hint (`[router]`, `[store]`,
  `[component]`, `[service]`, `[config]`, `[ext]` for an external system, …).
- `->` means "calls / renders / imports" (a hard dependency).
- `~>` means "reads / subscribes to" (a looser, reactive dependency).
- `=>` means "makes an HTTP call to" (crosses a network boundary).
- `@entry` marks the folder's main entry point; `@risk` marks a file named in `risk_areas`.

So the example reads: *`main` is the entry point and builds the app over `routes` and
`store`; `routes` calls `store`; `store` holds all the state (and is risky to touch).*

The root **`index.ngf.md`** is the same shape, but its "files" are your folders — each with
a one-line description and a link to that folder's map. An agent starts there and drills
into only the map it needs.

---

## 5. The daily workflow — drift

You don't maintain the maps by hand. context-os keeps each map's `staleness` flag honest
automatically:

- **When you edit a source file**, its folder's map flips to `DRIFTED`.
- **When a map is read**, it's re-checked first — so a change that happened outside Claude
  Code (a `git pull`, a branch switch, an edit in another editor) is caught too.

"Drift" is *semantic*, not a timestamp: reformatting a file, adding a comment, or cloning
the repo does **not** count; adding or removing a file, or changing what it imports, does.

The promise is not "always perfectly fresh" — it's **never misleads you**. A `DRIFTED` map
tells an agent to trust that one folder loosely and check the source. When you want to bring
drifted maps current, run `/context-os-update` (it only touches the folders that changed).

Check status anytime with `/context-os-status`.

---

## 6. Committing maps to git

**Commit the maps.** They're the whole point — a teammate, a fresh clone, or CI should all
get them without re-generating. Commit `index.ngf.md`, the `map-*.ngf.md` files, and the
`CLAUDE.md`/`AGENTS.md` pointer blocks.

To keep generated-file noise out of code review, add to `.gitattributes`:

```gitattributes
**/map-*.ngf.md linguist-generated=true
index.ngf.md    linguist-generated=true
```

GitHub/GitLab then collapse these in pull-request diffs (still expandable).

---

## 7. Stopping and resuming — /snapshot

`/snapshot` writes `snapshot.ngf.md`: a portable record of *where you are*, so you can stop
now and pick up cold later — on another machine, or with another AI model.

It contains:
- a **compacted summary** of the session (what was discussed, decided, tried, and why);
- the **work-state** — decisions, what's built, open questions, and the next steps, with
  `file:symbol` pointers into the code;
- the **git state** and each map's hash **at capture** (so a later session can tell if the
  code moved since).

To resume: copy the repo + `snapshot.ngf.md` to the other machine (or just open a new
session), and tell the agent to read `snapshot.ngf.md`. It reads the summary, the
work-state, and the maps it points to — and continues, without you re-explaining anything.

Each `/snapshot` archives the previous one under `.context-os/snapshots/`, so they're
versioned, not overwritten. Snapshots are point-in-time — they don't drift, they just age.

---

## 8. Privacy & security

- **Nothing leaves your machine.** context-os is a local Python program that reads your
  files and writes text files next to them. It makes no network calls, sends no telemetry,
  and uses no API key or account.
- **It never invents.** Every entry in a map traces to a real file that was actually found
  and read. A built-in check fails the run if anything was fabricated.
- **It never overwrites your notes.** It only ever touches its own marked block in
  `CLAUDE.md`/`AGENTS.md`, writes a timestamped backup first, and refuses (rather than
  guessing) if those markers have been hand-edited.
- **No dependencies to trust.** The scanner is Python standard library only — nothing is
  pulled from a package registry, so there's no supply-chain surface.

---

## 9. FAQ

**Does this cost anything or need an API key?**
No. It's free, offline, and uses no key. It *saves* you tokens; it doesn't spend any of its
own.

**Will it mess up my `CLAUDE.md`?**
No. It adds one marked block and backs the file up first. If you've hand-edited its markers
into a broken state, it refuses to write rather than guess.

**Do the maps work with Codex / Gemini / other tools?**
Yes — the maps and the `AGENTS.md` pointer are plain Markdown that any agent reads. (Claude
Code reads the `CLAUDE.md` pointer specifically; the `AGENTS.md` one is there for the
others.)

**How often do I regenerate?**
You don't, on a schedule. Edit code as normal; the affected maps mark themselves `DRIFTED`.
Run `/context-os-update` when you want to catch them up (or before an important session).

**My token-save number looks tiny or negative.**
The project or folder is very small, so the map's header outweighs the source. The saving
shows on real codebases, where source dwarfs the map.

**What languages are supported?**
The scanner understands imports for Python, TypeScript/JavaScript (+ JSX/TSX/Vue/Svelte),
Go, Rust, and Java/Kotlin. Other files are still listed; only the import-edge detection is
language-specific.

**Should I edit the maps by hand?**
You can fix a description, but don't hand-maintain them — that's what `/context-os-update`
is for. If you edit a map, don't touch its `structural_hash`/`staleness` lines (context-os
manages those).

---

## 10. Troubleshooting

- **"REFUSED" when writing the pointer block.** Your `CLAUDE.md`/`AGENTS.md` has malformed
  `<!-- context-os:start/end -->` markers (usually a hand-edit). Fix or remove the markers
  and re-run — context-os refuses rather than guess.
- **A map stays `DRIFTED`.** Run `/context-os-update` to bring it (and its baseline) current
  with the code. `DRIFTED` means the code changed; it clears once the map catches up.
- **`/context-os` didn't map a folder.** It only maps folders that contain recognized source
  files. Folders of only config/data/docs are skipped by design.
- **Nothing seems to use the maps.** Confirm the pointer block is in your `CLAUDE.md`
  (`/context-os` adds it). The block tells the agent to read the map before exploring.

---

## 11. Advanced: running the scripts directly

The plugin's scripts are plain stdlib Python — you can run them without the agent, e.g. in
CI:

```bash
python3 scripts/scan.py .        --emit-ngf   # write the per-folder map skeletons
python3 scripts/ctx_staleness.py stamp-all .  # stamp the drift baseline
python3 scripts/ctx_staleness.py status .     # exit 1 if any map is DRIFTED  (a CI drift gate)
python3 scripts/audit.py check .              # exit 1 if any map node is fabricated
python3 scripts/audit.py savings .            # print the token-save number
```

(The skeletons that `scan.py` writes have placeholder descriptions; the `/context-os`
command's agent is what fills in real descriptions and the risk card. For a pure-CI setup,
the skeleton + drift gate still work on their own.)
