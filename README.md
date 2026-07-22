# context-os

**Stop Claude burning your tokens re-exploring your own code every session.**

A fresh AI session doesn't know your repo. So it re-derives the architecture from
source — reading dozens of files, grepping, reconstructing what calls what — *every
session*. On a large repo that's hundreds of thousands of tokens, every time, before it
does any real work. It's also why moving a project to another model feels like starting
over.

context-os maps your repo once into small, portable context files — one per folder plus
a root index — that an agent reads on demand instead of re-scanning your whole project.
The maps are plain Markdown with a YAML header, so **Claude, Codex, and Gemini all read
them the same way, cold.** And they keep themselves honest: when a folder's code changes,
its map flips to `DRIFTED` so a stale map *warns you* instead of quietly lying.

This isn't a pitch — it's a measurement. Every run prints the number, computed against
*your* source:

```
188 source files (~46,000 tokens to scan) under . -> the context-os map set is
~3,200 tokens (93% smaller; a fresh session loads 3,200 on demand instead of
re-scanning 46,000).
```

Generating the maps costs about one cold exploration, once. Every session after reads
the map instead. Break-even is the first session.

## Quickstart

```
/plugin marketplace add verbalogicproject-creator/verbalogix
/plugin install context-os@verbalogix
```

New to Claude Code plugins? **[INSTALL.md](INSTALL.md)** walks through it step by step
(prerequisites, verifying it worked, updating, troubleshooting).

Then, in any project:

```
/context-os
```

That scans your repo, writes `index.ngf.md` + a `map-*.ngf.md` in each folder, drops a
short pointer into `CLAUDE.md` and `AGENTS.md` (so both Claude and Codex/Gemini find the
maps), and prints the token-save number. From then on, an agent reads the map for the
folder it's working in instead of re-scanning everything.

## The four commands

| Command | What it does |
|---|---|
| `/context-os` | Map (or re-map) the project: generate maps + the pointer block, print the token-save. |
| `/context-os-update` | Refresh only the folders whose code drifted since their map was last verified. |
| `/context-os-status` | Read-only: which maps are current vs `DRIFTED`, and the current token-save. |
| `/snapshot` | Capture this session — a compacted summary + the work-state — into one portable file so you can resume cold on another machine or model. |

## How it stays honest

Every map's YAML header carries a `structural_hash` (a hash of the folder's import and
declaration lines) and a `staleness` flag. Two hooks keep the flag true:

- when you **edit a source file**, its folder's map flips to `DRIFTED`;
- when a map is **read**, it's re-checked first — so even an out-of-band change (a
  `git pull`, a branch switch) is caught.

The hash is *semantic*, not a timestamp: a reformat, a comment, or a `git clone` doesn't
count as drift; a changed import or a new/removed file does. The warning lives *inside the
map file*, so any tool sees it — no hook required on the reader's side. The promise isn't
"always fresh," it's **never lies**: a `DRIFTED` map tells you to trust that one folder
loosely and check the source.

## Resuming cold — `/snapshot`

`/snapshot` writes `snapshot.ngf.md`: a compacted summary of the session, the current
work-state (decisions, artifacts, open questions, next steps, with `file:symbol`
pointers), the git state, and each map's hash at capture. Copy the repo + that file to a
clean machine, hand a fresh session (Claude, Codex, whatever) the snapshot, and it
continues from where you stopped — no prior coordination.

## What it never does

- **Never invents.** Every node in a map traces to a real file the scanner found; every
  description is written from a file that was actually read. A built-in `check` audit
  fails the run if anything is fabricated.
- **Never clobbers your CLAUDE.md.** It only ever touches its own marked block, backs up
  before writing, and refuses (rather than guesses) if you've hand-edited the markers.
- **Never phones home.** Free, offline, `$0`, no server, no API keys — a standard-library
  Python scanner and nothing else.

## Layout

```
commands/   the four slash commands
agents/     map-scout (generate) + map-updater (drift-only refresh)
hooks/      the drift hooks (hooks.json + handlers)
scripts/    scan.py, audit.py, claudemd_splice.py, ctx_staleness.py, snapshot.py (stdlib only)
demo/       a tiny two-service app with real, committed context-os output
SPEC.md     the format specification (ctx/1.1 + the three kinds)
```

## Documentation

- **[INSTALL.md](INSTALL.md)** — install in two commands (beginner-friendly): prerequisites,
  verifying it worked, updating, uninstalling, troubleshooting.
- **[HOW-TO-USE.md](HOW-TO-USE.md)** — the full user manual: the four commands in depth, **how
  to read a map**, the drift workflow, committing maps, `/snapshot`, privacy & security, FAQ.
- **[SPEC.md](SPEC.md)** — the file-format specification (`ctx/1.1` + the three kinds).
- **[ROADMAP.md](ROADMAP.md)** — what's planned next (git integration, Merkle-tree drift).
- **[SECURITY.md](SECURITY.md)** — privacy posture (no network, no keys, stdlib-only) and how
  to report a vulnerability.

Free, offline, `$0`, no server, no API keys. Apache-2.0 — Eyal Nof.
