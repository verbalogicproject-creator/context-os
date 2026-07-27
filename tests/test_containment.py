"""Security regressions: path containment, and the atomic/newline-safe CLAUDE.md write.

Each test here corresponds to a defect that shipped in a published version. They are kept
in one file so the reason they exist stays visible — these are not feature tests, they are
the guard rail that stops a fixed defect from coming back through a refactor.
"""

from pathlib import Path

import claudemd_splice
import mcp_server
import retrieve


# ---------------------------------------------------------------------------
# contain() — `root / relative` does NOT confine the result to root
# ---------------------------------------------------------------------------


def test_absolute_anchor_cannot_escape_root(tmp_path):
    """`Path(root) / "/etc/passwd"` returns `/etc/passwd` — pathlib discards the left side."""
    secret = tmp_path / "outside.txt"
    secret.write_text("SENSITIVE")
    root = tmp_path / "repo"
    root.mkdir()

    assert retrieve.contain(root, str(secret)) is None
    result = retrieve.retrieve(root, str(secret))
    assert "error" in result
    assert "SENSITIVE" not in str(result)


def test_dotdot_anchor_cannot_escape_root(tmp_path):
    secret = tmp_path / "outside.txt"
    secret.write_text("SENSITIVE")
    root = tmp_path / "repo"
    root.mkdir()

    assert retrieve.contain(root, "../outside.txt") is None
    result = retrieve.retrieve(root, "../outside.txt")
    assert "error" in result
    assert "SENSITIVE" not in str(result)


def test_contain_allows_a_real_file_inside_root(tmp_path):
    """The guard must not break the thing it protects."""
    root = tmp_path / "repo"
    (root / "pkg").mkdir(parents=True)
    target = root / "pkg" / "mod.py"
    target.write_text("def f():\n    return 1\n")

    assert retrieve.contain(root, "pkg/mod.py") == target.resolve()
    result = retrieve.retrieve(root, "pkg/mod.py")
    assert "error" not in result
    assert "def f()" in result["text"]


def test_mcp_map_path_rejects_escape(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    assert mcp_server._map_path(root, "../..") is None
    assert mcp_server._map_path(root, "/etc") is None
    # the root index and an ordinary folder still resolve
    assert mcp_server._map_path(root, None) == root / "index.ngf.md"
    assert mcp_server._map_path(root, "src") == (root / "src" / "map-src.ngf.md").resolve()


def test_mcp_call_tool_reports_escape_without_reading(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    out = mcp_server.call_tool("contextos_map", {"root": str(root), "folder": "/etc"})
    assert "outside the project" in out


# ---------------------------------------------------------------------------
# splice() — the one irreplaceable file
# ---------------------------------------------------------------------------

_START = claudemd_splice.CLAUDE_START
_END = claudemd_splice.CLAUDE_END


def test_splice_preserves_crlf_line_endings(tmp_path):
    """A CRLF-authored CLAUDE.md must not come back as a whole-file diff."""
    path = tmp_path / "CLAUDE.md"
    path.write_bytes(b"# My rules\r\n\r\nAlways run tests.\r\n")

    claudemd_splice.splice(
        path, f"{_START}\nmanaged\n{_END}\n", start_marker=_START, end_marker=_END
    )

    raw = path.read_bytes()
    assert b"# My rules\r\n" in raw
    assert b"Always run tests.\r\n" in raw
    # no bare LF anywhere — every newline in a CRLF file stays a CRLF
    assert raw.replace(b"\r\n", b"") .count(b"\n") == 0


def test_splice_leaves_lf_files_alone(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_bytes(b"# My rules\n\nAlways run tests.\n")

    claudemd_splice.splice(
        path, f"{_START}\nmanaged\n{_END}\n", start_marker=_START, end_marker=_END
    )

    raw = path.read_bytes()
    assert b"\r\n" not in raw
    assert b"# My rules\n" in raw


def test_splice_write_is_atomic_and_leaves_no_temp_files(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text("# Mine\n")

    claudemd_splice.splice(
        path, f"{_START}\nmanaged\n{_END}\n", start_marker=_START, end_marker=_END
    )

    assert "managed" in path.read_text()
    assert "# Mine" in path.read_text()
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".ctxtmp-")]
    assert leftovers == []


def test_splice_still_backs_up_before_writing(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text("# Mine\n")
    result = claudemd_splice.splice(
        path, f"{_START}\nmanaged\n{_END}\n", start_marker=_START, end_marker=_END
    )
    assert result.backup_path is not None
    assert Path(result.backup_path).read_text() == "# Mine\n"
