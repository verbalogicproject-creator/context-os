# Installing context-os

context-os is a **Claude Code plugin**. Installing it takes two commands and about
thirty seconds. No account, no API key, no payment, nothing to download and run yourself.

## Before you start

You need **Claude Code** installed and reasonably up to date. If typing `/plugin` in
Claude Code shows "unknown command," update Claude Code first (see the Claude Code docs
for how to update), then come back.

That's the only prerequisite. context-os itself runs on the Python 3 that ships with your
system — it needs no extra packages.

## Install (2 steps)

Type these **inside Claude Code**, at the prompt:

**1. Add the marketplace** (a one-time step — a marketplace is just a list of plugins):

```
/plugin marketplace add verbalogicproject-creator/verbalogix
```

**2. Install context-os from it:**

```
/plugin install context-os@verbalogix
```

That's it. context-os is now available in every project.

## Check it worked

Open any code project in Claude Code and run:

```
/context-os
```

You should see it scan your repo, create some map files, and print a line like:

```
… the context-os map set is ~3,200 tokens (93% smaller; a fresh session loads 3,200
on demand instead of re-scanning 46,000).
```

If you see that number, you're done. (On a *very* small project the number can be small
or negative — that's normal; the saving shows on real codebases.)

## Updating

When a new version is released, refresh the marketplace and update:

```
/plugin marketplace update verbalogix
/plugin update context-os@verbalogix
```

## Uninstalling

```
/plugin uninstall context-os@verbalogix
```

The maps context-os wrote are ordinary files in your repo — uninstalling the plugin
doesn't delete them. Remove them by hand if you want (`index.ngf.md`, the `map-*.ngf.md`
files, and the `<!-- context-os -->` block in your `CLAUDE.md`/`AGENTS.md`).

## Try it before installing (optional)

To test-drive without installing into your setup, clone the repo and point Claude Code at
it for one session:

```bash
git clone https://github.com/verbalogicproject-creator/context-os
claude --plugin-dir ./context-os
```

## Troubleshooting

- **`/plugin` says "unknown command."** Your Claude Code is too old — update it, restart,
  and try again.
- **`/context-os` doesn't appear after installing.** Run `/reload-plugins`, or restart
  Claude Code. Confirm it's enabled with `/plugin`.
- **"marketplace add" fails.** Check your internet connection and that
  `verbalogicproject-creator/verbalogix` is typed exactly (it's a GitHub `owner/repo`).
- **Do I need an API key or a paid plan?** No. context-os is a local Python scanner. It
  sends nothing anywhere and costs nothing to run. (See "Privacy & security" in
  `HOW-TO-USE.md`.)

For everything else — what the maps are, how to read them, the daily workflow — see the
user manual in **`HOW-TO-USE.md`**.
