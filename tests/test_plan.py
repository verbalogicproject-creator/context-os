"""Deterministic folder ranking (DEEP / SKELETON / FOLD) from the scan graph."""

import audit
import plan as plan_mod
import scan


def _row(plan, folder):
    return next(r for r in plan["folders"] if r["folder"] == folder)


def _build(tmp_path):
    # core/: 3 code files, imported by app → a hub (DEEP by files AND by in-degree)
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "util.py").write_text("def u():\n    pass\n")
    (tmp_path / "core" / "helpers.py").write_text("def h():\n    pass\n")
    (tmp_path / "core" / "models.py").write_text("class M:\n    pass\n")
    # app/: an entry point (main.py) that imports core → DEEP via has_entry
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("from core.util import u\nfrom core.models import M\n")
    # app/docs/: content only → FOLD, folds into app
    (tmp_path / "app" / "docs").mkdir()
    (tmp_path / "app" / "docs" / "guide.md").write_text("# Guide\n\n## Section\ntext\n")
    # leaf/: a single peripheral code file → SKELETON
    (tmp_path / "leaf").mkdir()
    (tmp_path / "leaf" / "tiny.py").write_text("x = 1\n")
    # mid/: two code files, unimported → SKELETON but borderline (one file short of DEEP)
    (tmp_path / "mid").mkdir()
    (tmp_path / "mid" / "a.py").write_text("def a():\n    pass\n")
    (tmp_path / "mid" / "b.py").write_text("def b():\n    pass\n")


def test_hub_is_deep_thin_entry_is_borderline_skeleton(tmp_path):
    _build(tmp_path)
    plan = plan_mod.compute_plan(tmp_path)
    assert _row(plan, "core")["tier"] == "DEEP"
    assert _row(plan, "core")["in_degree"] >= 2       # app imports two of its files
    app = _row(plan, "app")
    assert app["tier"] == "SKELETON"                  # one thin entry file — not auto-DEEP
    assert app["has_entry"] is True                   # main.py
    assert app["borderline"] is True                  # flagged for the agent to promote if it matters


def test_peripheral_code_is_skeleton(tmp_path):
    _build(tmp_path)
    plan = plan_mod.compute_plan(tmp_path)
    assert _row(plan, "leaf")["tier"] == "SKELETON"
    assert _row(plan, "leaf")["borderline"] is False


def test_content_folder_folds_into_parent(tmp_path):
    _build(tmp_path)
    plan = plan_mod.compute_plan(tmp_path)
    docs = _row(plan, "app/docs")
    assert docs["tier"] == "FOLD"
    assert docs["code_files"] == 0
    assert docs["fold_into"] == "app"                 # nothing vanishes — it names its parent


def test_borderline_folder_is_flagged(tmp_path):
    _build(tmp_path)
    plan = plan_mod.compute_plan(tmp_path)
    mid = _row(plan, "mid")
    assert mid["tier"] == "SKELETON"
    assert mid["borderline"] is True                  # one file short of DEEP — the agent may promote
    assert "mid" in plan["summary"]["borderline"]


def test_summary_counts_and_selectivity(tmp_path):
    _build(tmp_path)
    plan = plan_mod.compute_plan(tmp_path)
    s = plan["summary"]
    assert s["deep"] >= 1 and s["skeleton"] >= 2 and s["fold"] >= 1
    # the whole point: we enrich fewer folders than exist
    assert s["deep"] < len(plan["folders"])


def test_apply_fold_merges_content_into_parent(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("def m():\n    pass\n")
    (tmp_path / "app" / "models.py").write_text("class M:\n    pass\n")
    (tmp_path / "app" / "util.py").write_text("def u():\n    pass\n")   # 3 code files → DEEP
    (tmp_path / "app" / "docs").mkdir()
    (tmp_path / "app" / "docs" / "guide.md").write_text("# Guide\n\n## S\ntext\n")  # content-only → FOLD

    result = scan.scan(tmp_path)
    scan.write_ngf_skeletons(tmp_path, result)
    assert (tmp_path / "app" / "docs" / "map-docs.ngf.md").is_file()  # its own map, pre-fold

    folded = plan_mod.apply_fold(tmp_path)
    assert folded["count"] >= 1
    assert not (tmp_path / "app" / "docs" / "map-docs.ngf.md").exists()  # map removed
    app_map = (tmp_path / "app" / "map-app.ngf.md").read_text()
    assert "Folded: app/docs/" in app_map                              # content moved into parent
    assert "guide" in app_map
    assert "app/docs :" not in (tmp_path / "index.ngf.md").read_text()  # index row pruned
    assert audit.check_maps_fabrication(tmp_path).ok                    # still all-real, gate passes
