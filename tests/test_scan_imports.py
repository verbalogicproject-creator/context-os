"""Import resolution: Python relative-dotted imports and indented imports resolve to edges.

Regression guard for the gaps the live map-scout test on a real Python repo surfaced —
`from .rooms import` and imports nested in try/except were being dropped from the skeleton.
"""

import scan


def _edges(root):
    return {(e.source, e.target) for e in scan.scan(root).edges}


def test_relative_dotted_import_same_package(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "state.py").write_text("from .rooms import get_world\n")
    (tmp_path / "pkg" / "rooms.py").write_text("def get_world():\n    pass\n")
    assert ("state", "rooms") in _edges(tmp_path)


def test_relative_dotted_import_parent_package(tmp_path):
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "child.py").write_text("from ..util import helper\n")
    (tmp_path / "a" / "util.py").write_text("def helper():\n    pass\n")
    assert ("child", "util") in _edges(tmp_path)


def test_indented_import_is_captured(tmp_path):
    (tmp_path / "p").mkdir()
    (tmp_path / "p" / "engine.py").write_text(
        "try:\n    from p.backend import X\nexcept ImportError:\n    X = None\n"
    )
    (tmp_path / "p" / "backend.py").write_text("X = 1\n")
    assert ("engine", "backend") in _edges(tmp_path)


def _match_by_full_scan(needle, source_dir, all_files):
    """The pre-index resolver, kept verbatim as the reference implementation.

    `build_stem_index` narrows the search to candidates sharing `needle`'s last path segment.
    That is an exactness claim, not a heuristic, so it is pinned against the exhaustive scan it
    replaced rather than against hand-written expectations.
    """
    exact = same_dir = other = None
    for dir_path, files in all_files.items():
        for f in sorted(files):
            stem = __import__("pathlib").Path(f).stem
            full_stem = f"{dir_path}/{stem}" if dir_path else stem
            if full_stem == needle:
                exact = (dir_path, stem)
            elif full_stem.endswith("/" + needle):
                if dir_path == source_dir:
                    same_dir = same_dir or (dir_path, stem)
                else:
                    other = other or (dir_path, stem)
    return exact or same_dir or other


def test_the_stem_index_resolves_exactly_as_the_full_scan_did():
    """Equivalence, over the collision shapes the index could plausibly get wrong: a bare stem
    several directories share, a dotted path, a nested suffix, a stem that is a suffix of a
    longer name (`config` must never bind to `myconfig`), and a miss."""
    all_files = {
        "": {"setup.py"},
        "alpha": {"config.py", "main.py"},
        "beta": {"config.py", "myconfig.py"},
        "beta/deep": {"config.py", "util.ts"},
        "gamma": {"util.py", "util.ts"},          # same stem twice in one directory
    }
    needles = [
        "config", "util", "main", "setup", "myconfig",
        "alpha/config", "beta/deep/config", "deep/config",
        "beta/config", "gamma/util", "nope", "onfig", "a/b/c",
    ]
    for needle in needles:
        for source_dir in ("", "alpha", "beta", "beta/deep", "gamma"):
            assert scan._match_by_suffix(needle, source_dir, all_files) == \
                   _match_by_full_scan(needle, source_dir, all_files), (needle, source_dir)


def test_a_bare_stem_never_binds_to_a_longer_name_that_ends_with_it(tmp_path):
    """The precedence the index must not quietly lose: `import config` resolves to `config.py`,
    never to `myconfig.py`, and the importer's own directory wins over another directory."""
    for d in ("alpha", "beta"):
        (tmp_path / d).mkdir()
    (tmp_path / "alpha" / "config.py").write_text("VALUE = 1\n")
    (tmp_path / "beta" / "myconfig.py").write_text("VALUE = 2\n")
    (tmp_path / "beta" / "config.py").write_text("VALUE = 3\n")
    (tmp_path / "beta" / "main.py").write_text("import config\n")
    edges = _edges(tmp_path)
    # node names collapse to the bare stem where it is unambiguous, so the importer is `main`
    # while the two `config.py` files stay directory-qualified.
    assert ("main", "beta/config") in edges
    assert ("main", "beta/myconfig") not in edges
    assert ("main", "alpha/config") not in edges
