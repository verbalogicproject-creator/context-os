# Contributing to context-os

Thanks for looking. context-os is small on purpose — a stdlib-only scanner plus a few
agents and hooks — and the design has a handful of load-bearing rules. Please keep them.

## Set up

```bash
git clone https://github.com/verbalogicproject-creator/context-os
cd context-os
python3 -m pip install pytest      # the only dev dependency
python3 -m pytest tests/ -q        # should be all green
```

There is nothing to build and nothing to install for the plugin itself — the scripts run
on the system Python 3.

## Run the full check before a PR

```bash
python3 -m pytest tests/ -q
python3 scripts/audit.py check demo && python3 scripts/ctx_staleness.py status demo
```

## The invariants (don't regress these)

1. **`scripts/` is standard-library only.** No third-party import — offline, `$0`, no
   supply-chain surface is the whole point. This includes no YAML library (frontmatter is
   handled line-based in `ctx_staleness.py`).
2. **Never fabricate a map node.** Every non-`[ext]` node must trace to a real file;
   `audit.py check` is the gate, and `tests/test_audit_ngf.py` locks it in.
3. **Drift is semantic, not temporal.** `ctx_staleness.signature` hashes only import and
   declaration lines — a reformat or `git clone` must not drift a map
   (`test_staleness.py::test_whitespace_and_comments_do_not_drift`).
4. **Only `claudemd_splice.py` writes `CLAUDE.md`/`AGENTS.md`**, only inside its marked
   block, backup-first, refusing on malformed markers. Keep `test_splice.py` green.
5. **Public-facing copy is plain English** — no ecosystem jargon in `README.md`,
   `HOW-TO-USE.md`, `INSTALL.md`, `plugin.json`, or the command/agent descriptions.

More detail on the internals is in **`CLAUDE.md`** (the working-in-this-repo guide) and the
format is specified in **`SPEC.md`**.

## Reporting issues

Open a GitHub issue with: what you ran, what you expected, what happened, and (if relevant)
the output of `/context-os-status` or `python3 scripts/audit.py check .`. Since context-os
runs entirely locally, most issues are reproducible from the command output alone.

## License

By contributing you agree your contributions are licensed under Apache-2.0 (see `LICENSE`).
