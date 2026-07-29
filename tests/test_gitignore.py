"""The `.gitignore` matcher, and the guarantee that ignored files never reach a map.

The scanner previously consulted `.gitignore` nowhere, so a file a project deliberately
kept out of git — a local `secrets.yaml`, a `dump.csv`, a debug log — was scanned anyway
and its shape written into a map file the tool then asks the user to commit.
"""

from pathlib import Path

import compress
import gitignore
import scan


def _ignore(tmp_path: Path, text: str, sub: str = "") -> gitignore.GitIgnore:
    target = tmp_path / sub if sub else tmp_path
    target.mkdir(parents=True, exist_ok=True)
    (target / ".gitignore").write_text(text)
    return gitignore.GitIgnore.load(tmp_path)


def test_basename_pattern_matches_at_any_depth(tmp_path):
    ig = _ignore(tmp_path, "*.log\n")
    assert ig.ignored("run.log")
    assert ig.ignored("a/b/run.log")
    assert not ig.ignored("run.txt")


def test_anchored_pattern_only_matches_at_root(tmp_path):
    ig = _ignore(tmp_path, "/config.json\n")
    assert ig.ignored("config.json")
    assert not ig.ignored("pkg/config.json")


def test_directory_only_pattern(tmp_path):
    ig = _ignore(tmp_path, "build/\n")
    assert ig.ignored("build", is_dir=True)
    assert not ig.ignored("build", is_dir=False)
    # everything under an ignored directory is ignored too
    assert ig.ignored("build/out.json")


def test_negation_reincludes(tmp_path):
    ig = _ignore(tmp_path, "*.log\n!keep.log\n")
    assert ig.ignored("run.log")
    assert not ig.ignored("keep.log")


def test_later_rule_wins(tmp_path):
    ig = _ignore(tmp_path, "!keep.log\n*.log\n")
    assert ig.ignored("keep.log")  # order reversed → the exclude now wins


def test_doublestar_spans_directories(tmp_path):
    ig = _ignore(tmp_path, "docs/**/draft.md\n")
    assert ig.ignored("docs/draft.md")
    assert ig.ignored("docs/a/b/draft.md")
    assert not ig.ignored("other/draft.md")


def test_nested_gitignore_applies_to_its_subtree(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / ".gitignore").write_text("*.json\n")
    (tmp_path / "pkg" / ".gitignore").write_text("!allowed.json\n")
    ig = gitignore.GitIgnore.load(tmp_path)
    assert ig.ignored("top.json")
    assert not ig.ignored("pkg/allowed.json")   # re-included by the deeper file
    assert ig.ignored("pkg/other.json")


def test_comments_and_blank_lines_are_skipped(tmp_path):
    ig = _ignore(tmp_path, "# a comment\n\n   \n*.log\n")
    assert ig.ignored("x.log")
    assert not ig.ignored("a comment")


def test_no_gitignore_means_nothing_is_ignored(tmp_path):
    ig = gitignore.GitIgnore.load(tmp_path)
    assert not ig
    assert not ig.ignored("anything.json")


# ---------------------------------------------------------------------------
# Integration — the scanner must honour it
# ---------------------------------------------------------------------------


def test_scan_skips_gitignored_content_file(tmp_path):
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "settings.json").write_text('{"a": 1}')
    (tmp_path / "conf" / "secrets.json").write_text('{"api_key": "sk-live-xyz"}')
    (tmp_path / ".gitignore").write_text("secrets.json\n")

    result = scan.scan(tmp_path)
    paths = {n.path for n in result.nodes}
    assert "conf/settings.json" in paths
    assert "conf/secrets.json" not in paths

    scan.write_ngf_skeletons(tmp_path, result)
    map_text = (tmp_path / "conf" / "map-conf.ngf.md").read_text()
    assert "api_key" not in map_text
    assert "secrets" not in map_text


def test_scan_skips_gitignored_source_file(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("def f():\n    pass\n")
    (tmp_path / "app" / "generated.py").write_text("X = 1\n")
    (tmp_path / ".gitignore").write_text("generated.py\n")

    result = scan.scan(tmp_path)
    paths = {n.path for n in result.nodes}
    assert "app/main.py" in paths
    assert "app/generated.py" not in paths


def test_scan_never_maps_a_dotenv_even_without_gitignore(tmp_path):
    """`.env` is excluded by name — a project that forgot to gitignore it is still safe."""
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "settings.json").write_text('{"a": 1}')
    (tmp_path / "conf" / ".env").write_text("STRIPE_SECRET_KEY=sk_live_x\n")
    (tmp_path / "conf" / ".env.production").write_text("DATABASE_URL=postgres://u:p@h/db\n")

    result = scan.scan(tmp_path)
    paths = {n.path for n in result.nodes}
    assert "conf/settings.json" in paths
    assert not any(".env" in p for p in paths)

    scan.write_ngf_skeletons(tmp_path, result)
    map_text = (tmp_path / "conf" / "map-conf.ngf.md").read_text()
    for leak in ("STRIPE_SECRET_KEY", "DATABASE_URL", "sk_live"):
        assert leak not in map_text


def test_ignored_directory_is_not_descended(tmp_path):
    (tmp_path / "vendor" / "deep").mkdir(parents=True)
    (tmp_path / "vendor" / "deep" / "lib.py").write_text("X = 1\n")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("def f():\n    pass\n")
    (tmp_path / ".gitignore").write_text("vendor/\n")

    result = scan.scan(tmp_path)
    paths = {n.path for n in result.nodes}
    assert "app/main.py" in paths
    assert not any(p.startswith("vendor/") for p in paths)


def test_compress_is_secret_file_covers_the_dotenv_family():
    assert compress.is_secret_file(Path(".env"))
    assert compress.is_secret_file(Path(".env.local"))
    assert compress.is_secret_file(Path("a/b/.env.production"))
    assert compress.is_secret_file(Path("backend.env"))
    assert not compress.is_secret_file(Path("environment.json"))
    assert not compress.is_secret_file(Path("settings.json"))


def test_the_local_ignore_file_ignores_itself_and_the_state_dir(tmp_path):
    """Otherwise `.context-os/` still shows as untracked in every mapped project — the exact
    complaint the nested-ignore change set out to fix. The ignore file is not ignored by its own
    patterns, so git reports the directory; git still READS an ignored .gitignore, so
    self-ignoring costs nothing and makes the directory genuinely invisible."""
    import session_log
    session_log.ensure_log_dir(tmp_path)
    text = (tmp_path / ".context-os" / ".gitignore").read_text()
    assert ".gitignore" in text.splitlines()
    assert "state/" in text.splitlines()
