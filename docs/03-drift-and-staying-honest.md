# 03 — Drift, and staying honest

This chapter continues in `/tmp/cos-tutorial` from chapter 01 (run its steps first if you
haven't — you should have a `check`-passing map set there now). You'll change the demo's
source three ways and watch the map react each time — including one change that
*shouldn't* count as drift, and does not.

Inside Claude Code, two hooks do this automatically: `PostToolUse` flips a map to `DRIFTED`
the instant you edit a source file in its folder; `PreToolUse` re-checks a map right before
it's read (catching a change that happened outside the agent — a `git pull`, a branch
switch). Here you'll call the same underlying check, `ctx_staleness.py flip`, directly, so
you can see exactly what it does.

## 1. A real structural change drifts the map

Add a method to `api/store.py`:

```bash
cat >> /tmp/cos-tutorial/api/store.py <<'EOF'

    def remove(self, name):
        self._items.remove(name)
EOF
```

Now re-check the map that documents this folder:

```bash
python3 scripts/ctx_staleness.py flip /tmp/cos-tutorial/api/map-api.ngf.md
python3 scripts/ctx_staleness.py status /tmp/cos-tutorial
```

```
/tmp/cos-tutorial/api/map-api.ngf.md: DRIFTED — folder changed since last verify; trust loosely, run /context-os-update
!! api/map-api.ngf.md: DRIFTED — folder changed since last verify; trust loosely, run /context-os-update
ok map-root.ngf.md: verified
ok web/map-web.ngf.md: verified

3 map(s), 1 drifted
```

Look at the map's frontmatter now:

```bash
sed -n '1,9p' /tmp/cos-tutorial/api/map-api.ngf.md
```

```
---
id: map-api
kind: context_map
folder: "api/"
format: ctx/1.1
last_verified: 2026-07-22
file_count: 3
structural_hash: sha256:014419841168d9a2
staleness: DRIFTED — folder changed since last verify; trust loosely, run /context-os-update
---
```

`structural_hash` is untouched — it's the baseline, and only `stamp` ever rewrites it.
`staleness` is what `flip` just rewrote. The warning now lives *inside the file*, so any
reader — Claude, Codex, Gemini, a human, a hook or no hook — sees it just by opening the map.
It doesn't lie by omission and it doesn't need a live process watching it.

Bring it current (this is the mechanical half of what `/context-os-update` does — it also
diffs in the actual content change, which needs an agent; see `agents/map-updater.md`):

```bash
python3 scripts/ctx_staleness.py stamp /tmp/cos-tutorial/api/map-api.ngf.md
python3 scripts/ctx_staleness.py status /tmp/cos-tutorial
```

```
stamped /tmp/cos-tutorial/api/map-api.ngf.md
ok api/map-api.ngf.md: verified
ok map-root.ngf.md: verified
ok web/map-web.ngf.md: verified

3 map(s), 0 drifted
```

## 2. A pure reformat does NOT drift the map

This is the part that makes "drift" trustworthy instead of noisy. Add a comment and some
blank lines to the same file — no logic change at all:

```bash
python3 - /tmp/cos-tutorial/api/store.py <<'PYEOF'
import pathlib
p = pathlib.Path("/tmp/cos-tutorial/api/store.py")
text = p.read_text()
text = "# in-memory item store\n\n" + text.replace(
    "    def remove(self, name):",
    "\n    # remove an item by name\n    def remove(self, name):",
)
p.write_text(text)
PYEOF
```

```bash
python3 scripts/ctx_staleness.py flip /tmp/cos-tutorial/api/map-api.ngf.md
python3 scripts/ctx_staleness.py status /tmp/cos-tutorial
```

```
/tmp/cos-tutorial/api/map-api.ngf.md: verified
ok api/map-api.ngf.md: verified
ok map-root.ngf.md: verified
ok web/map-web.ngf.md: verified

3 map(s), 0 drifted
```

Still `verified` — no restamp needed. `structural_hash` is a hash of only the folder's
*architecture-bearing* lines (imports and top-level declarations), sorted, per file. A
comment, blank lines, or a whole-file reformat touch none of those lines, so the signature
doesn't move. This is the deliberate difference from an mtime check: staleness answers *did
the architecture move?*, never *was a byte touched?*.

## 3. A new import drifts it too — not just a new function

One more real change, this time in `api/routes.py` — add an import, nothing else:

```bash
python3 - /tmp/cos-tutorial/api/routes.py <<'PYEOF'
import pathlib
p = pathlib.Path("/tmp/cos-tutorial/api/routes.py")
p.write_text("import json\n" + p.read_text())
PYEOF
```

```bash
python3 scripts/ctx_staleness.py flip /tmp/cos-tutorial/api/map-api.ngf.md
python3 scripts/ctx_staleness.py status /tmp/cos-tutorial
```

```
/tmp/cos-tutorial/api/map-api.ngf.md: DRIFTED — folder changed since last verify; trust loosely, run /context-os-update
!! api/map-api.ngf.md: DRIFTED — folder changed since last verify; trust loosely, run /context-os-update
ok map-root.ngf.md: verified
ok web/map-web.ngf.md: verified

3 map(s), 1 drifted
```

An import is an edge-bearing line even with no new node or call — the signature is sensitive
to exactly the two things that make a map's *graph* wrong: new/changed declarations (nodes)
and new/changed imports (edges).

## Verify your build

Bring it current one more time and confirm the gate still holds:

```bash
python3 scripts/ctx_staleness.py stamp /tmp/cos-tutorial/api/map-api.ngf.md
python3 scripts/audit.py check /tmp/cos-tutorial
python3 scripts/ctx_staleness.py status /tmp/cos-tutorial
```

You should see `PASS` from `check` and `0 drifted` from `status`. If you do, you've
reproduced the exact contract this repo's own CI enforces on the committed `demo/` maps
(the "drift gate" step in `.github/workflows/ci.yml`).

**The promise isn't "always fresh" — it's "never lies."** A `DRIFTED` map is still useful
(drift is localized to the one folder that actually changed); it just tells you to trust
that folder loosely and check the source, instead of trusting a number that quietly stopped
being true.

Next: **[04 — enrichment tiers, ranking, and catch-up](04-enrichment-tiers-and-catchup.md)**,
where you'll see how context-os decides *which* folders are worth the cost of the prose you
read in chapter 02.
