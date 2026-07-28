---
format: ngf/0.0.3
kind: relay
id: relay-gutted
created: "2026-07-28"
resume_target: "Continue the work on the parser."
git_branch: main
git_dirty: false
previous_relay: none
---

# Start here

Pick up where the last session left off.

## Resume target — the one next action

Continue the work on the parser. It was mostly working.

## Done when

The tests pass and it works properly.

## Do not

- Don't refactor.
- Don't change the config.

## Decisions locked

We agreed on the approach.

## Open

A few things are still undecided.

## Verify

```bash
python3 -m pytest tests/ -q
python3 scripts/audit.py check
```

## Pointers

- The main module — read this first.
- The helper file.
- The plan document.
