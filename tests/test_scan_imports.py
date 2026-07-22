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
