# Security policy

## Reporting a vulnerability

Please **don't** open a public issue for a suspected vulnerability. Instead:

- email **verbalogic.project@gmail.com**, or
- open a private advisory on GitHub (the repo's **Security → Report a vulnerability**).

Include the version (or commit), what an attacker could do, and steps to reproduce. You'll
get an acknowledgement as soon as possible.

## Attack surface — deliberately small

context-os runs entirely on your machine:

- **No network.** The scanner and hooks make no network calls, send no telemetry, and use
  no API key or account. There is no server to attack and nothing in transit.
- **Standard library only.** `scripts/` imports nothing outside the Python standard library,
  so there is no third-party supply-chain surface.
- **Bounded writes; no execution.** It writes map files next to your code and only ever
  edits its own marked block in `CLAUDE.md`/`AGENTS.md` (timestamped backup first, refuses on
  malformed markers, atomic write, preserves your line endings). It reads your source as
  text — it never executes it.

## What a map may contain

Maps are meant to be **committed**, so what goes into one is a security question and is
enforced in code rather than left to review:

- **Never a secret.** The whole `.env` family is skipped by name (`.env`, `.env.local`,
  `.env.production`, `*.env`), anything your `.gitignore` excludes is skipped, and every
  compressor reports *shape* — key names, column headers, section titles — never file
  content. Pinned by `tests/test_compress.py` and `tests/test_gitignore.py`.
- **Never an instruction.** The map enricher is a model reading whatever is in your repo,
  including vendored dependencies and code from a pull request. Because the pointer block
  makes agents read maps *before* source, text that survived from repo content into a map
  would act as an instruction — every session. `audit.py check` fails on text that only
  makes sense as a directive about an agent's tools, permissions or secrets.
  Pinned by `tests/test_injection.py`.
- **Never a file outside your project.** The MCP tools (`contextos_map`,
  `contextos_retrieve`) confine every path to the project root, so an absolute or `../`
  anchor resolves to nothing rather than to a file elsewhere on your disk.
  Pinned by `tests/test_containment.py`.

## Residual risk — stated plainly

- **The injection check is precision-tuned, not exhaustive.** It catches the payloads that
  work, not a careful attacker. If you run context-os over a repo containing code you do
  not trust, read the generated maps before committing them.
- **`audit.py check` proves node existence and the absence of instruction-shaped text.** It
  does *not* verify that a description is accurate or that an edge points the right way.
- **A map can go stale.** Drift detection flags a folder whose code changed
  (`staleness: DRIFTED`), and a flagged map should be trusted loosely and verified against
  source — for that folder only.

## Supported versions

context-os is pre-1.0; fixes land on the latest release. Please report against the newest
version.
