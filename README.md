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

This isn't a pitch — it's two measurements, and we keep them honest by keeping them
separate. First, the **ceiling**: how much smaller the maps are than your source, computed
against *your* files on every run:

```
188 source files (~46,000 tokens to scan) under . -> CEILING: the context-os map set is
~3,200 tokens vs ~46,000 to scan the source cold (93% smaller). This is the MOST a
session could save, not what it did — realized only when the agent reads a map instead
of re-reading its source.
```

That 93% is an *artifact-size* number — a real, reproducible upper bound. It becomes real
tokens only when a session actually reads the map instead of exploring. So context-os also
measures what a session **delivered**: a hook logs, per session, when the agent read a map
versus re-read (or grepped) the source it already maps, and `python3 measure.py session .`
(or `/context-os-status`) reports the delivered number and the map-consultation rate. Ceiling
tells you the opportunity; delivered tells you whether it landed. We won't sell you the
ceiling as if it were the delivered number.

Generating the maps costs about one cold exploration, once. Every session after *can* read
the map instead — and now you can measure whether it did.

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

### Generation tiers — pick your cost

Generating the maps has three tiers on a dial (the structure, drift, and pointer are the
same in all three — only the prose enrichment differs):

| Invocation | Enrichment | Cost |
|---|---|---|
| `/context-os --skeleton` (`--fast`) | none — structure + drift + pointer only, **no LLM** | ~free, seconds |
| `/context-os` (default) | descriptions + risk cards, by a **parallel fan-out of small per-folder agents** (Haiku) | cheap |
| `/context-os --premium` | same, enrichers run on **Sonnet** for best quality | higher |

Start with `--skeleton` for a free structural map; upgrade to full enrichment when you want
the prose and risk cards.

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

## Retrieve originals, feed any agent, map everything (v0.3)

- **Retrieve the exact original (CCR).** A map is the compressed view; the source is the
  retrievable original. `python3 scripts/retrieve.py . path:symbol` returns the exact
  `def`/`class` block + a content hash — read the cheap map, pull the full original only when
  needed.
- **An MCP server** (`.mcp.json`, stdlib) exposes `contextos_map` + `contextos_retrieve`, so any
  agent — or a runtime message compressor like [Headroom](https://github.com/chopratejas/headroom)
  — can consume the maps and fetch originals. context-os compresses *structure ahead of time*; a
  runtime compressor squeezes *each request*. Different layers — they stack.
- **Non-code folders too.** config / docs / data / log files get a compressed one-line map node
  (JSON shape, doc headings, CSV columns, log errors), so a fresh session sees the whole project.

## What it never does

- **Never invents a node.** Every node in a map traces to a real file the scanner found;
  the built-in `check` audit fails the run if a node doesn't. (Honest scope: `check`
  gates node *existence* mechanically. Descriptions are written from files actually read,
  and edges come from the deterministic scanner — but `check` does not prove a description
  is accurate or an edge points the right way; it flags an edge to a missing target as an
  advisory. A `DRIFTED` flag then tells you when even a correct map has gone out of date.)
- **Never clobbers your CLAUDE.md.** It only ever touches its own marked block, backs up
  before writing, and refuses (rather than guesses) if you've hand-edited the markers.
- **Never phones home.** Free, offline, `$0`, no server, no API keys — a standard-library
  Python scanner and nothing else.

## Layout

```
commands/   the four slash commands
agents/     map-enricher (per-folder, parallel) + map-updater (drift-only refresh)
hooks/      the drift hooks (hooks.json + handlers)
scripts/    scan.py, audit.py, claudemd_splice.py, ctx_staleness.py, snapshot.py,
            retrieve.py (CCR), compress.py (non-code), mcp_server.py (stdlib only)
.mcp.json   the MCP server config (contextos_map + contextos_retrieve)
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
