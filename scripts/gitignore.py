#!/usr/bin/env python3
"""A stdlib `.gitignore` matcher, used to keep deliberately-excluded files out of maps.

WHY THIS EXISTS. The scanner used a hardcoded `DEFAULT_EXCLUDE_DIRS` list and consulted
`.gitignore` nowhere. That is fine as a performance filter and wrong as a safety one: the
single clearest statement a project makes about "do not look at this" is its `.gitignore`,
and the scanner ignored it. A local `secrets.yaml` or `dump.csv` that the project has
deliberately kept out of git was scanned anyway, and its shape written into a map file that
the tool then asks the user to commit.

WHAT THIS IMPLEMENTS, honestly. A practical subset of gitignore(5), not the whole spec:

  - comments (`#`) and blank lines are skipped; trailing whitespace is stripped
  - `!pattern` re-includes, and later rules win over earlier ones
  - a trailing `/` restricts a rule to directories
  - a `/` anywhere but the end anchors the rule to the file containing it
  - `*` and `?` do not cross `/`; `**` does
  - nested `.gitignore` files apply to their own subtree

NOT implemented: `\\` escapes, and character ranges (`[a-z]`) are passed to the regex
engine rather than given gitignore's exact semantics. Both are rare, and both fail toward
*over*-matching, which for this use is the safe direction — an over-excluded file loses a
map node, an under-excluded one can leak.

This is deliberately not a shell-out to `git check-ignore`. That would be exact, but it
would make map contents depend on whether git is installed and whether the directory
happens to be a repository — so the same tree could produce two different maps. Determinism
is worth more here than the last few percent of spec fidelity.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

IGNORE_FILENAME = ".gitignore"


def _translate(pattern: str) -> str:
    """Glob → regex source, with gitignore's `*` vs `**` distinction."""
    out: List[str] = []
    i, n = 0, len(pattern)
    while i < n:
        char = pattern[i]
        if char == "*":
            if pattern.startswith("**", i):
                # `**/` spans zero or more directories; a bare `**` spans anything.
                if pattern.startswith("**/", i):
                    out.append("(?:.*/)?")
                    i += 3
                    continue
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char in "[]":
            out.append(char)
        else:
            out.append(re.escape(char))
        i += 1
    return "".join(out)


class Rule:
    """One `.gitignore` line, compiled."""

    __slots__ = ("regex", "negated", "dir_only", "base")

    def __init__(self, line: str, base: str):
        self.negated = line.startswith("!")
        if self.negated:
            line = line[1:]
        self.dir_only = line.endswith("/")
        line = line.rstrip("/")
        self.base = base

        anchored = "/" in line
        body = _translate(line.lstrip("/"))
        # An anchored rule matches from the .gitignore's own directory down; an unanchored
        # one matches a path segment at any depth (git's "matches in any directory").
        self.regex = re.compile(f"^{body}$" if anchored else f"^(?:.*/)?{body}$")

    def matches(self, rel: str, is_dir: bool) -> bool:
        if self.dir_only and not is_dir:
            return False
        if self.base:
            prefix = self.base + "/"
            if not rel.startswith(prefix):
                return False
            rel = rel[len(prefix):]
        return bool(self.regex.match(rel))


class GitIgnore:
    """The rules from every `.gitignore` in a tree, applied in git's precedence order."""

    def __init__(self, rules: Optional[List[Rule]] = None):
        self.rules: List[Rule] = rules or []

    def __bool__(self) -> bool:
        return bool(self.rules)

    @classmethod
    def load(cls, root: Path, exclude_dirs: Optional[set] = None) -> "GitIgnore":
        """Collect `.gitignore` files under `root`, shallowest first.

        Shallowest-first ordering matters: a deeper file's rules are evaluated after a
        shallower one's, so a subdirectory can re-include (`!keep.log`) something its
        parent excluded — which is the whole reason nested ignore files exist.
        """
        import os

        skip = exclude_dirs or set()
        found: List[Tuple[int, str, Path]] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in skip and d != ".git")
            if IGNORE_FILENAME not in filenames:
                continue
            rel = Path(dirpath).relative_to(root).as_posix()
            rel = "" if rel == "." else rel
            found.append((rel.count("/") if rel else -1, rel, Path(dirpath) / IGNORE_FILENAME))

        rules: List[Rule] = []
        for _depth, base, path in sorted(found, key=lambda f: (f[0], f[1])):
            try:
                text = path.read_text(errors="ignore")
            except OSError:
                continue
            for raw in text.splitlines():
                line = raw.rstrip()
                if not line or line.lstrip().startswith("#"):
                    continue
                try:
                    rules.append(Rule(line, base))
                except re.error:
                    continue  # an unparseable pattern is skipped, never fatal
        return cls(rules)

    def ignored(self, rel: str, is_dir: bool = False) -> bool:
        """True if `rel` (a posix path relative to root) is excluded.

        Last matching rule wins, which is how a `!` re-include overrides an earlier
        exclude. Anything under an ignored directory is ignored too — git stops
        descending, and so do we.
        """
        verdict = False
        for rule in self.rules:
            if rule.matches(rel, is_dir):
                verdict = not rule.negated
        if verdict:
            return True
        # A file inside an ignored directory is ignored even if no rule names the file.
        parts = rel.split("/")
        for i in range(1, len(parts)):
            if self.ignored("/".join(parts[:i]), is_dir=True):
                return True
        return False
