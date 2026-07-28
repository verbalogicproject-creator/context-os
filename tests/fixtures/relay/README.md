# Relay gate fixtures — the two directions

The cold-read gate is a **model judgement**, so it cannot be unit-tested. What these two
files pin is the harness around it, and one honest fact about the split.

- `good.ngf.md` — the Phase-1 relay, verbatim, as it was actually scored: **8/10**, twice.
  It is kept here because a real relay lives at `.context-os/relay.ngf.md`, which is
  gitignored and overwritten on each capture, so the only passing example would otherwise
  be unrecoverable.
- `gutted.ngf.md` — a relay that is deficient in exactly the ways the 4/10 run was: headings
  with no body, no definition of done, pointers with no real paths, state asserted with no
  SHA, verification commands with no expected output. Scored **2/10** live.

Both scores were **provisional**: every reader so far has disclosed that the harness injected
this repo's `CLAUDE.md` and the user's memory index into it unrequested. That is why the gate
fails on the score alone and records contamination beside it, rather than failing on it —
a gate that can never pass is not a gate.

**Both pass `relay.py budget`.** That is the point, not a bug: the deterministic check only
proves the file is short enough and has no placeholder left, and the gutted one satisfies
both. Whether a fresh session could *resume* from it is a judgement, which is why the gate
exists and why it is a model call. Running it for real:

```bash
# dispatch a context-os:relay-cold-reader agent on each file, save its report, then:
python3 scripts/relay.py gate <report>     # exit 0 only at >= 8/10 AND clean isolation
```
