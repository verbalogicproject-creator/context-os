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


# ---------------------------------------------------------------------------
# keeps_map — one file per folder over-fragments; one file per repo over-charges
# ---------------------------------------------------------------------------


def _merge_repo(tmp_path):
    """pkg/ with a real hub, a thin sibling, and a docs folder."""
    (tmp_path / "pkg").mkdir()
    for name in ("a", "b", "c", "d"):
        (tmp_path / "pkg" / f"{name}.py").write_text(f"from pkg.hub.h1 import x\n\ndef {name}():\n    pass\n")
    (tmp_path / "pkg" / "hub").mkdir()
    (tmp_path / "pkg" / "hub" / "h1.py").write_text("x = 1\n\ndef helper():\n    pass\n")
    (tmp_path / "pkg" / "thin").mkdir()
    (tmp_path / "pkg" / "thin" / "t.py").write_text("from pkg.hub.h1 import x\n\ndef t():\n    pass\n")
    (tmp_path / "pkg" / "docs").mkdir()
    (tmp_path / "pkg" / "docs" / "guide.md").write_text("# Guide\n\n## S\ntext\n")


def test_code_folders_keep_their_own_map_by_default(tmp_path):
    """Merging code folders trades fragmentation for DILUTION, and measured on a real project it
    lost: 12 of 15 folders cost more to read, none less. So the default is one map per folder —
    zero dilution — and merging is opt-in until a ledger says which folders are read together."""
    _merge_repo(tmp_path)
    plan = plan_mod.compute_plan(tmp_path)

    assert _row(plan, "pkg/thin")["keeps_map"] is True     # one file, but still its own map
    assert _row(plan, "pkg/hub")["keeps_map"] is True
    assert _row(plan, "pkg")["keeps_map"] is True
    assert _row(plan, "pkg/docs")["keeps_map"] is False    # code-free still folds — it always did
    assert _row(plan, "pkg/docs")["fold_into"] == "pkg"


def test_thin_folder_merges_up_and_hub_keeps_its_own_map(tmp_path):
    _merge_repo(tmp_path)
    plan = plan_mod.compute_plan(tmp_path, merge_max_files=4)   # opt-in

    thin = _row(plan, "pkg/thin")
    assert thin["keeps_map"] is False
    assert thin["fold_into"] == "pkg"          # one file is not worth its own map

    hub = _row(plan, "pkg/hub")
    assert hub["in_degree"] >= plan["params"]["merge_hub_in"]
    assert hub["keeps_map"] is True            # a hub keeps its card however small

    assert _row(plan, "pkg")["keeps_map"] is True
    assert "pkg/thin" in _row(plan, "pkg")["absorbs"]


def test_merged_folders_are_not_separately_enriched(tmp_path):
    _merge_repo(tmp_path)
    plan = plan_mod.compute_plan(tmp_path, merge_max_files=4)   # opt-in
    enrich = plan["summary"]["enrich"]
    assert "pkg" in enrich and "pkg/hub" in enrich
    assert "pkg/thin" not in enrich            # its files are described inside pkg's map
    assert "pkg/docs" not in enrich
    assert len(enrich) < plan["summary"]["deep"] + plan["summary"]["skeleton"]


def test_code_never_merges_into_a_docs_only_host(tmp_path):
    """A repo whose root holds only a README must not swallow backend/ into a docs map."""
    (tmp_path / "README.md").write_text("# Project\n\n## About\ntext\n")
    (tmp_path / "backend").mkdir()
    for name in ("main", "models", "util"):
        (tmp_path / "backend" / f"{name}.py").write_text(f"def {name}():\n    pass\n")

    plan = plan_mod.compute_plan(tmp_path)
    root = _row(plan, ".")
    backend = _row(plan, "backend")
    assert root["code_files"] == 0 and root["keeps_map"] is True
    assert backend["keeps_map"] is True        # kept, despite being thin enough to merge
    assert backend["fold_into"] is None


def test_plan_ignores_its_own_maps_so_a_second_run_agrees(tmp_path):
    """The plan must give the same answer before and after an emit — `index.ngf.md` at the root
    would otherwise make the root a map-keeping folder that absorbs the whole repo."""
    _merge_repo(tmp_path)
    before = {r["folder"]: (r["keeps_map"], r["fold_into"]) for r in plan_mod.compute_plan(tmp_path)["folders"]}

    scan.write_ngf_skeletons(tmp_path, scan.scan(tmp_path))
    after = {r["folder"]: (r["keeps_map"], r["fold_into"]) for r in plan_mod.compute_plan(tmp_path)["folders"]}

    assert before == after


def test_apply_fold_moves_code_nodes_and_their_digest(tmp_path):
    _merge_repo(tmp_path)
    result = scan.scan(tmp_path)
    scan.write_ngf_skeletons(tmp_path, result)
    scan.write_digests(tmp_path, result)
    assert (tmp_path / "pkg" / "thin" / "map-thin.ngf.md").is_file()
    assert (tmp_path / ".context-os" / "digests" / "pkg/thin" / "digest.txt").is_file()

    folded = plan_mod.apply_fold(tmp_path, merge_max_files=4)   # opt-in

    assert {f["folder"] for f in folded["folded"]} >= {"pkg/thin", "pkg/docs"}
    assert not (tmp_path / "pkg" / "thin" / "map-thin.ngf.md").exists()
    pkg_map = (tmp_path / "pkg" / "map-pkg.ngf.md").read_text()
    assert "Folded: pkg/thin/" in pkg_map and "t" in pkg_map
    assert (tmp_path / "pkg" / "hub" / "map-hub.ngf.md").is_file()   # the hub kept its own
    # the digest moved too — otherwise pkg's enricher gets a node it was given nothing about
    assert not (tmp_path / ".context-os" / "digests" / "pkg/thin" / "digest.txt").exists()
    assert "merged from pkg/thin/" in (tmp_path / ".context-os" / "digests" / "pkg" / "digest.txt").read_text()
    assert audit.check_maps_fabrication(tmp_path).ok


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


def test_merging_code_folders_is_off_by_default_and_stays_off(tmp_path):
    """The default nobody was pinning. Merging shipped once, measured negative within the hour
    (12 of 15 folders cost MORE, none less), and was reverted — but only the opt-in path had a
    test, so a refactor could have flipped the default back silently, which is how the rule
    shipped in the first place.

    The cost model in plan.py closes it for good: a merge saves at most one ~79-token header and
    costs ~146 tokens of foreign content whenever a task touches only one of the pair, so two
    folders must be co-accessed on >65% of tasks to break even. Same fixture as the opt-in test
    above, opposite outcome — that contrast IS the guarantee.
    """
    assert plan_mod.DEFAULT_MERGE_MAX_FILES == 0

    _merge_repo(tmp_path)
    plan = plan_mod.compute_plan(tmp_path)                  # defaults, no flags

    thin = _row(plan, "pkg/thin")
    assert thin["keeps_map"] is True, "a thin CODE folder keeps its own map by default"
    assert thin["fold_into"] is None

    # code-free folders still fold — that behaviour predates the merge rule and was always right
    assert _row(plan, "pkg/docs")["keeps_map"] is False

    # and the escape hatch still works, so this pins the default without deleting the feature
    opted_in = plan_mod.compute_plan(tmp_path, merge_max_files=4)
    assert _row(opted_in, "pkg/thin")["keeps_map"] is False
