# context-os

**Stop Claude burning your tokens re-exploring your own code every session.**

A fresh AI session doesn't know your repo. So it re-derives the architecture from
source — reading dozens of files, grepping, reconstructing what calls what — *every
session*. On a large repo that's hundreds of thousands of tokens, every time, before it
does any real work. It's also why moving a project to another model feels like starting
over.

**And that reading isn't charged once.** Everything already in the conversation is
re-processed on every message you send after it. So a file read early in a session is paid
for again, and again, until the session ends. That is the part most people never see, and
it is where the money actually goes:

```
context-os — real token usage across 5328 turns:
  cache read (prefix re-processed each turn)   2,364,116,086    70.9% of cost
  cache create (first sight of new content)       39,313,779    14.7%
  output                                           9,579,925    14.4%
  raw input (uncached)                                76,817     0.0%

  mean prefix re-processed per turn: 443,715 tokens

  admitting 30,000 tokens at turn 100 costs 524.05x its apparent size
  (156,840,000 cache-read tokens over 5228 remaining turns)
```

Those are real numbers from one real session, not an estimate — Claude Code records what
each message actually cost, and `measure.py cost` reads it back. **Seven out of every ten
tokens went on re-reading the conversation so far.** Reading five files early doesn't cost
you 30,000 tokens; on that session it cost 524 times that.

This is why a small map is worth so much more than the size difference suggests. Swapping a
30,000-token source read for a 3,000-token map read doesn't save you 27,000 tokens — it
saves you 27,000 tokens *on every message that follows*. And it's why "your session starts
cheaper" is the wrong promise: the saving isn't at the start, it accrues the whole way
through.

context-os maps your repo once into small, portable context files — one per folder plus
a root index — that an agent reads on demand instead of re-scanning your whole project.
The maps are plain Markdown with a YAML header, so **Claude, Codex, and Gemini all read
them the same way, cold.** And they keep themselves honest: when a folder's code changes,
its map flips to `DRIFTED` so a stale map *warns you* instead of quietly lying.

## Three numbers, kept separate on purpose

This isn't a pitch — it's measurements, and they stay honest by never being merged.

**1. The ceiling** — how much smaller the maps are than your source, computed against
*your* files on every run:

```
188 source files (~46,000 tokens to scan) under . -> CEILING: the context-os map set is
~3,200 tokens vs ~46,000 to scan the source cold (93% smaller). This is the MOST a
session could save, not what it did — realized only when the agent reads a map instead
of re-reading its source.
```

That 93% is an *artifact-size* upper bound: real and reproducible, but it becomes real
tokens only if a session actually reads the map.

**2. What a session delivered** — a hook logs, per session, when the agent read a map
versus re-read (or grepped) source it already maps. `python3 scripts/measure.py session .`
(or `/context-os-status`) reports the map-consultation rate. Ceiling tells you the
opportunity; delivered tells you whether it landed.

**3. Where your tokens actually went** — `python3 scripts/measure.py cost <session.jsonl>`
reads the real per-message usage Claude Code already records for you:

```
python3 scripts/measure.py cost ~/.claude/projects/<your-project>/<session-id>.jsonl
python3 scripts/measure.py cost <session>.jsonl --at-turn 100 --tokens 30000
```

This one is a **cost profile, not a savings figure** — it shows where the spend is, which
is what makes the case for maps. It doesn't prove the maps saved you anything; only number
2 speaks to that.

We won't sell you the ceiling as if it were the delivered number, and we won't sell you a
cost profile as if it were either.

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

By default `/context-os` is **strategic** — it ranks folders and enriches only the ones that
carry architecture (code hubs, entry points), keeps a cheap skeleton for the rest, and folds
pure docs/data folders into their parent. Pass `--all` to enrich every folder.

**Or go lazy.** Map the whole repo as free skeletons once, then let enrichment follow your
work: `/context-os-catchup` enriches only the folders you actually touched this session (it reads
the same per-session ledger the drift hook keeps). Run it whenever; it never re-does a folder
that's already enriched. So you pay for the handful of folders you worked in, not the whole repo.

```
/context-os --skeleton      # once: whole repo as skeletons, $0, instant
… work in the repo …        # the hook logs which folders you touch
/context-os-catchup         # enrich just those folders, on demand
```

## The six commands

| Command | What it does |
|---|---|
| `/context-os` | Map (or re-map) the project: generate maps + the pointer block, print the token-save. |
| `/context-os-catchup` | Enrich only the folders you actually worked in this session (the lazy companion to a `--skeleton` pass). |
| `/context-os-update` | Refresh only the folders whose code drifted since their map was last verified. |
| `/context-os-status` | Read-only: which maps are current vs `DRIFTED`, and the current token-save. |
| `/relay` | Write the handoff before you stop — the one next action, what done looks like, what not to redo — then have a fresh reader check it can actually be resumed from. |
| `/snapshot` | The older, narrative-shaped capture that `/relay` replaces. Still here; prefer `/relay`. |

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

## Resuming cold — `/relay`

`/relay` writes one page a fresh session can start from: the **single next action**, what
*done* looks like for it, the decisions already settled and why, what not to redo, and the
real paths to reuse. Everything a script can establish — git state, each map's hash at
capture, the folders you touched, the current context size — it fills in itself; the
judgement is yours, and it leaves a marked placeholder for each piece until you write it.

**Then it checks the file can actually be used.** The last step hands the relay to a reader
that has no knowledge of your project and is allowed to open *nothing else* — not even the
files the relay points at. It answers five questions (what is the next action? what would I
open? what must I not redo? what is missing?) and scores 0-10. Below 8, you fix the relay
before the session ends — because a handoff can only be repaired while the context that
would repair it still exists. In testing, a real relay scored 8/10 and a deliberately gutted
one scored 2/10.

Copy the repo + that file to a clean machine, hand a fresh session (Claude, Codex, whatever)
the relay, and it continues from where you stopped — no prior coordination.

`/snapshot` still exists and writes the older narrative-shaped `snapshot.ngf.md`. `/relay`
supersedes it: a next action beats a summary, and a summary was never checked.

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
- **Never puts a secret in a map.** Maps are meant to be committed, so this is enforced in
  code, not left to you to catch: the whole `.env` family is skipped by name, anything your
  `.gitignore` excludes is skipped, and the map of a config or log file describes its
  *shape* — key names, column headers, how many errors — never its contents.
- **Never lets a map become an instruction.** Agents read maps before source, so text that
  drifted in from a dependency's README or someone's pull request would act as a command,
  every session. `check` fails on text that only makes sense as an instruction about an
  agent's tools, permissions, or secrets. (It's tuned to be precise, not exhaustive — if
  you map a repo you don't trust, read the maps before committing them.)
- **Never reads outside your project.** The MCP tools confine every path to the project
  root, so an anchor pointing elsewhere on your disk resolves to nothing.
- **Never clobbers your CLAUDE.md.** It only ever touches its own marked block, backs up
  before writing, writes atomically (so an interrupted run can't truncate it), keeps your
  line endings, and refuses (rather than guesses) if you've hand-edited the markers.
- **Never phones home.** Free, offline, `$0`, no server, no API keys — a standard-library
  Python scanner and nothing else.

## Layout

```
commands/   the six slash commands
agents/     map-enricher (per-folder, parallel), map-updater (drift-only refresh),
            relay-cold-reader (scores a handoff from a cold read)
hooks/      the drift hooks (hooks.json + handlers)
scripts/    scan.py, audit.py, claudemd_splice.py, ctx_staleness.py, relay.py, snapshot.py,
            retrieve.py (CCR), compress.py (non-code), mcp_server.py (stdlib only)
.mcp.json   the MCP server config (contextos_map + contextos_retrieve)
demo/       a tiny two-service app with real, committed context-os output
docs/       numbered, progressive chapters that build the demo app's maps step by step
SPEC.md     the format specification (ctx/1.1 + the three kinds)
CODEBASE-REPORT.md  a module-by-module map of this plugin's own code
```

## Documentation

- **[INSTALL.md](INSTALL.md)** — install in two commands (beginner-friendly): prerequisites,
  verifying it worked, updating, uninstalling, troubleshooting.
- **[HOW-TO-USE.md](HOW-TO-USE.md)** — the full user manual: the six commands in depth, **how
  to read a map**, the drift workflow, committing maps, `/relay`, privacy & security, FAQ.
- **[docs/](docs/00-mental-model.md)** — numbered, hands-on chapters that build one small
  runnable thing at a time on the `demo/` app: generate a map, read it, drift it, retrieve an
  original, map non-code files, snapshot for cold resume.
- **[SPEC.md](SPEC.md)** — the file-format specification (`ctx/1.1` + the three kinds).
- **[ROADMAP.md](ROADMAP.md)** — what's planned next (git integration, Merkle-tree drift).
- **[SECURITY.md](SECURITY.md)** — what a map may and may not contain (no secrets, no
  instructions, nothing outside your project), the residual risks stated plainly, and how to
  report a vulnerability.
- **[CODEBASE-REPORT.md](CODEBASE-REPORT.md)** — a module-by-module map of this plugin's own
  code, for anyone extending context-os itself.

Free, offline, `$0`, no server, no API keys. Apache-2.0 — Eyal Nof.
