# 06 — Mapping non-code files

So far every map node has been a source file. Real projects also have config, docs, data,
and log files — and a fresh session needs those too. This chapter adds four such files to
the tutorial project and re-scans.

## Add some non-code files

Starting from a clean `/tmp/cos-tutorial` (delete the maps from earlier chapters first, the
same way you would before any full re-scan):

```bash
find /tmp/cos-tutorial -name '*.ngf.md' -delete

mkdir -p /tmp/cos-tutorial/config /tmp/cos-tutorial/docs /tmp/cos-tutorial/data /tmp/cos-tutorial/logs

cat > /tmp/cos-tutorial/config/settings.json <<'EOF'
{
  "port": 8080,
  "debug": false,
  "items": ["a", "b"]
}
EOF

cat > /tmp/cos-tutorial/docs/notes.md <<'EOF'
# Demo notes

## Setup
Run the api then the web client.

## Known issues
None yet.
EOF

cat > /tmp/cos-tutorial/data/items.csv <<'EOF'
name,qty,price
apple,3,1.20
banana,5,0.50
EOF

cat > /tmp/cos-tutorial/logs/app.log <<'EOF'
2026-07-27 10:00:00 INFO started
2026-07-27 10:00:05 ERROR store index out of range
2026-07-27 10:00:06 WARNING retrying add
EOF
```

## Scan

```bash
python3 scripts/scan.py /tmp/cos-tutorial --emit-ngf
```

```
scanned 12 files, 5 imports (4 resolved to project edges)
wrote 8 map skeleton(s) + index into /tmp/cos-tutorial
```

("5 imports, 4 resolved" — the `import json` you added to `api/routes.py` back in chapter 03
is real, but it's a standard-library import with no project file behind it, so it's counted
and correctly left unresolved rather than forced onto some file.)

## Look at what got mapped

Each non-code file gets a **deterministic, one-line compressed view** — no LLM, computed at
scan time by `scripts/compress.py`:

```bash
cat /tmp/cos-tutorial/config/map-config.ngf.md
```
````
---
id: map-config
kind: context_map
folder: "config/"
format: ctx/1.1
last_verified: 2026-07-27
file_count: 1
---
```ctx
# config/ — architecture (auto-generated skeleton, descriptions pending)
# format: ctx/1.1
# edges: -> call/render | ~> subscribe/read | => HTTP API call
## Files
  settings : JSON object — 3 keys: port, debug, items [config]
```
````

```bash
cat /tmp/cos-tutorial/docs/map-docs.ngf.md
```
```
## Files
  notes : doc — 'Demo notes' — sections: Setup, Known issues [doc]
```

```bash
cat /tmp/cos-tutorial/data/map-data.ngf.md
```
```
## Files
  items : data — 3 cols (name, qty, price), 2 rows [data]
```

```bash
cat /tmp/cos-tutorial/logs/map-logs.ngf.md
```
```
## Files
  logs/app : log — 3 lines, 1 error / 1 warn; severities: error [log]
```

Four content types, four deterministic descriptions:

| Type | What it extracts |
|---|---|
| `[config]` | JSON/YAML object keys + shape ("3 keys: port, debug, items") |
| `[doc]` | The title + heading list ("'Demo notes' — sections: Setup, Known issues") |
| `[data]` | CSV columns + row count |
| `[log]` | Error/warning counts + which severities appear — never a line of the log |

Notice `logs/app`, not `app` — the scanner already has an `app` node from `web/app.ts` (from
chapter 01), so it disambiguates the repo-wide name collision to `logs/app`. This is the same
disambiguation rule `agents/map-enricher.md` insists an enricher must **never** shorten back
to a bare stem — doing so would fabricate a node the fabrication audit can't trace.

These descriptions need no enrichment pass at all — `map-enricher` explicitly leaves any node
that already has a real, non-placeholder description alone, and only fills in code files'
`: <path>` placeholders.

## Shape, never contents

**Notice what the log node does *not* say.** It counts the errors and names the severity
kinds, but it never quotes the log. That is deliberate, and it is the rule every row of that
table follows: these descriptions report a file's **shape** — key names, column headers,
heading titles, counts — and never its **contents**.

Log files are where the distinction bites. An earlier version of this chapter documented the
log node as ending `first error: 2026-07-27 10:00:05 ERROR store index out of range`, because
`compress.py` used to append the first 80 characters of the first matching error line.
Harmless in a tutorial with a made-up log; not harmless in a real one, where error lines are
exactly where runtime *values* surface — a connection string with a password in it, a token
in a URL, a customer's email in a stack frame. And map files are meant to be committed.
Truncating to 80 characters bounds how much leaks, not how sensitive it is.

Two more layers sit behind that, both silent by design: any file in the `.env` family is
skipped by name, and so is anything your `.gitignore` excludes — so a `secrets.yaml` you
deliberately kept out of git never becomes a map node either. Try it:

```bash
echo "logs/" >> /tmp/cos-tutorial/.gitignore
find /tmp/cos-tutorial -name '*.ngf.md' -delete
python3 scripts/scan.py /tmp/cos-tutorial --emit-ngf
```

```
scanned 11 files, 5 imports (4 resolved to project edges)
wrote 7 map skeleton(s) + index into /tmp/cos-tutorial
```

Eleven files instead of twelve, seven maps instead of eight: no `logs/map-logs.ngf.md` is
generated and `logs` disappears from the index — the folder is not described anywhere.
(Delete that `.gitignore` line before continuing, so the rest of the chapter matches.)

## The router sees the whole project now

```bash
cat /tmp/cos-tutorial/index.ngf.md
```

```
## Folders
  . : 3 files [dir] -> map-root.ngf.md
  api : 3 files [dir] -> api/map-api.ngf.md
  config : 1 files [dir] -> config/map-config.ngf.md
  data : 1 files [dir] -> data/map-data.ngf.md
  docs : 1 files [dir] -> docs/map-docs.ngf.md
  logs : 1 files [dir] -> logs/map-logs.ngf.md
  web : 2 files [dir] -> web/map-web.ngf.md
```

A fresh session reading only `index.ngf.md` now sees the *whole* project shape — code and
non-code — before deciding what to drill into. (In a real `/context-os` run, `plan.py`
would also likely fold these single-file, no-code folders into their parent's map rather
than giving each its own file — see chapter 04's FOLD tier; this chapter shows them
unfolded so you can see each compressed view on its own.)

## Verify your build

```bash
python3 scripts/ctx_staleness.py stamp-all /tmp/cos-tutorial
python3 scripts/audit.py check /tmp/cos-tutorial
```

```
stamped 7 map(s)
PASS: derive-don't-fabricate — 19 node(s) checked (0 external-exempt), 0 unbacked
PASS: no instruction-shaped text in the map set
```

Every non-code node still traces to a real file — the same gate from chapter 01 covers them
too. `check` doesn't have a separate "code" and "non-code" mode; a node is a node.

Next: **[07 — snapshot: stopping and resuming cold](07-snapshot-cold-resume.md)**.
