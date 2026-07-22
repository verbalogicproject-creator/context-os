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
  malformed markers). It reads your source as text — it never executes it.

One thing to be aware of, as with any dev tool: the maps and the pointer block are read by
your AI agent as context. Treat a generated map the way you treat any committed file —
review changes before you rely on them.

## Supported versions

context-os is pre-1.0; fixes land on the latest release. Please report against the newest
version.
