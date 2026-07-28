"""Shared bootstrap for context-os's two drift hooks.

Both hook scripts are invoked directly by Claude Code as
`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/<name>.py"`, so they must work with zero
setup (no `pip install`). This puts `<plugin_root>/scripts` on `sys.path` before
importing `ctx_staleness`, exactly like the vouch / hookify `PLUGIN_ROOT` pattern.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def bootstrap_import() -> None:
    """Put `<plugin_root>/scripts` on `sys.path` so `import ctx_staleness` works unconditionally."""
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root:
        # Not running under Claude Code (e.g. manual testing) — fall back to hooks/../.
        plugin_root = str(Path(__file__).resolve().parent.parent)
    scripts_dir = str(Path(plugin_root) / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


def read_hook_input() -> dict:
    """Read and JSON-decode the hook input from stdin. Never raises (fail safe on junk)."""
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def repo_root_from(hook_input: dict) -> Path:
    """The repo root for this call: hook input's `cwd`, else `$CLAUDE_PROJECT_DIR`, else process cwd."""
    cwd = hook_input.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(cwd).resolve() if cwd else Path.cwd()


#: A folder is a project root if it carries a context-os index, or is a git checkout.
#: The index is checked FIRST: it is the thing that makes maps resolvable, and a mapped project
#: nested inside a larger checkout should own its own ledger.
_ROOT_MARKERS = ("index.ngf.md", ".git")


def root_for_path(hook_input: dict, resolved: Path) -> Path:
    """The repo root of the FILE being touched — not of the session.

    The session's `cwd` is the wrong root the moment one session works across two repos, which is
    routine: a tool's own repo in one place, the project it is being run against in another. The
    ledger then records reads of project B under repo A, where B's maps do not resolve, and scores
    mapped files as unmapped. Measured on one real session: 57 of 80 entries foreign-root, 36
    mis-scored.

    So walk up from the file to its own root and log there — two honest ledgers instead of one
    poisoned one. Falls back to the session root when the file is outside every marked ancestor,
    which keeps the single-repo case byte-identical to the old behaviour.
    """
    session_root = repo_root_from(hook_input)
    try:
        folder = resolved.resolve()
    except OSError:
        return session_root
    if folder.is_file() or folder.suffix:
        folder = folder.parent
    for candidate in (folder, *folder.parents):
        for marker in _ROOT_MARKERS:
            if (candidate / marker).exists():
                return candidate
    return session_root


def agent_id_from(hook_input: dict):
    """The subagent that made this call, or None when the main session did.

    Field name and behaviour are OBSERVED, not assumed — a probe on Claude Code v2.1.220
    captured the live PreToolUse input for two parallel `general-purpose` subagents and for the
    main session. Hook input carries `agent_id` + `agent_type`, populated only inside a
    subagent; the main session's call has neither. Both subagents reported the SAME
    `session_id` as their parent, which is why the ledger cannot separate them without this:
    five parallel enrichers appear as one session touching every folder they collectively read,
    and the co-access signal that earned merging would be measuring a fan-out, not a task.

    `CLAUDE_CODE_CHILD_SESSION` is deliberately NOT used: the probe found it set to "1" in the
    main session's environment too, so it does not discriminate.
    """
    value = hook_input.get("agent_id")
    return str(value) if value else None


def tool_failed(hook_input: dict) -> bool:
    """True if the PostToolUse result carries an explicit error (a failed edit teaches nothing)."""
    result = hook_input.get("tool_response")
    if result is None:
        result = hook_input.get("tool_result")
    return isinstance(result, dict) and bool(result.get("error"))


def emit(payload: dict) -> None:
    """Write `payload` as the hook's JSON stdout response."""
    print(json.dumps(payload))
