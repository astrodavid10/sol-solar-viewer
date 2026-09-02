"""Per-product validation, and the rollback decision it feeds.

The defect: validation was all-or-nothing and ran in CI AFTER the promote, so
one bad record in someone else's feed discarded every product. Footgun 50 (a
frozen seed set's ar_index running off a shrinking NOAA region list) and
footgun 51 (NOAA keying AR4521 at latitude 98) are the two recorded instances;
each left the site 11-13 h stale on all six products, six of forty-four runs.

The corruption tests are deliberately the two REAL failures, reproduced on a
temp copy of the published tree: a lat_deg of 98 and a truncated frame binary.
"""

import json
import shutil
from pathlib import Path

import pytest

from ..validate import (CONSUMES, PRODUCT_ORDER, failing_checks, overlay_tree,
                        plan_rollbacks, product_ok, tree_from_root,
                        validate_products)

ROOT = Path(__file__).resolve().parents[2] / "public" / "data"
DATA_PRODUCTS = ("pfss", "active_regions", "ephemeris", "stats", "texture",
                 "events")

live = pytest.mark.skipif(not (ROOT / "index.json").is_file(),
                          reason="no published tree in public/data")


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    """One shared copy of the published tree; tests never mutate it."""
    dst = tmp_path_factory.mktemp("published") / "data"
    shutil.copytree(ROOT, dst)
    return dst


@pytest.fixture
def tree(tmp_path, published):
    """A fresh writable copy per test (the tree is ~28 MB, so copy once more)."""
    dst = tmp_path / "data"
    shutil.copytree(published, dst)
    return dst


def _bad(reports, strict=True):
    return sorted(name for name, rep in reports.items()
                  if not product_ok(rep, strict=strict))


def _read(p):
    return json.loads(p.read_text(encoding="utf-8"))


def _write(p, doc):
    p.write_text(json.dumps(doc), encoding="utf-8")


# ── the pure rollback decision ───────────────────────────────────────────────

def test_no_failures_rolls_back_nothing():
    assert plan_rollbacks({"pfss": [], "stats": []}) == (set(), set())


def test_a_failing_product_rolls_back_alone():
    roll, recheck = plan_rollbacks({"stats": ["windWindow future point"],
                                    "pfss": [], "texture": []})
    assert roll == {"stats"}
    # stats has no consumers, so nothing is re-judged.
    assert recheck == set()


def test_rolling_back_regions_rechecks_its_consumers_not_rolls_them():
    roll, recheck = plan_rollbacks({"active_regions": ["lat_deg within +/-60"],
                                    "pfss": [], "events": []})
    assert roll == {"active_regions"}
    # NOT rolled back transitively: an ar_index that addressed five regions is
    # still valid if the published list also has five.
    assert recheck == {"pfss", "events"}


def test_a_consumer_that_failed_on_its_own_is_not_also_rechecked():
    roll, recheck = plan_rollbacks({"active_regions": ["bad"],
                                    "events": ["also bad"]})
    assert roll == {"active_regions", "events"}
    assert recheck == {"pfss"}


def test_the_dependency_map_is_the_ar_index_consumers():
    # If a third consumer of ar/regions.json ever appears, this is the line
    # that has to change with it.
    assert set(CONSUMES) == {"pfss", "events"}
    assert all(p == ("active_regions",) for p in CONSUMES.values())


# ── the whole published tree ─────────────────────────────────────────────────

@live
def test_every_product_of_the_published_tree_passes(tree):
    reports = validate_products(tree_from_root(str(tree)), strict=True)
    assert set(reports) == set(PRODUCT_ORDER)
    bad = _bad(reports)
    # stats may carry Task 1's known live defect (wind points in the future);
    # anything else failing is a regression in this refactor.
    assert [n for n in bad if n != "stats"] == [], {
        n: failing_checks(reports[n]) for n in bad}


@live
def test_a_subset_runs_only_the_products_asked_for(tree):
    reports = validate_products(tree, products=["ephemeris"])
    assert set(reports) == {"ephemeris"}


@live
def test_an_unknown_product_name_is_a_programming_error(tree):
    with pytest.raises(ValueError):
        validate_products(tree, products=["ephemerides"])


# ── footgun 51, reproduced ───────────────────────────────────────────────────

@live
def test_an_impossible_region_latitude_fails_only_active_regions(tree):
    doc = _read(tree / "ar" / "regions.json")
    history = doc.get("history") or []
    assert history, "published tree has no region history to corrupt"
    # NOAA published AR4521 at "latitude": 98 on 2026-09-01 having reported 9
    # the day before. This is that record.
    history[-1]["regions"][0]["lat_deg"] = 98.0
    _write(tree / "ar" / "regions.json", doc)

    reports = validate_products(tree, strict=True)
    bad = _bad(reports)
    assert "active_regions" in bad
    assert [n for n in bad if n not in ("active_regions", "stats")] == [], {
        n: failing_checks(reports[n]) for n in bad}
    assert any("lat_deg within +/-60" in c
               for c in failing_checks(reports["active_regions"]))


@live
def test_dropping_regions_does_not_fail_the_regions_product_itself(tree):
    """Footgun 50's shape: the list shrinks and its CONSUMER is what fails.

    This is the check that proves the cross-product assertions live with the
    consumer. Truncating the array leaves regions.json internally consistent,
    so `active_regions` passes -- and pfss, whose frozen ar_index column now
    runs off the end, is the one that fails.
    """
    doc = _read(tree / "ar" / "regions.json")
    assert len(doc["regions"]) >= 2
    doc["regions"] = doc["regions"][:1]
    doc["count"] = 1
    _write(tree / "ar" / "regions.json", doc)

    reports = validate_products(tree, strict=True)
    bad = _bad(reports)
    assert "active_regions" not in bad, failing_checks(
        reports["active_regions"])
    assert "pfss" in bad
    assert any("ar_index" in c for c in failing_checks(reports["pfss"]))


# ── a corrupt binary ─────────────────────────────────────────────────────────

@live
def test_a_truncated_frame_binary_fails_only_pfss(tree):
    man = _read(tree / "pfss" / "manifest.json")
    victim = tree / "pfss" / man["frames"][3]["url"]
    blob = victim.read_bytes()
    victim.write_bytes(blob[:-6])

    reports = validate_products(tree, strict=True)
    bad = _bad(reports)
    assert "pfss" in bad
    assert [n for n in bad if n not in ("pfss", "stats")] == [], {
        n: failing_checks(reports[n]) for n in bad}
    assert any("exact length" in c for c in failing_checks(reports["pfss"]))


# ── the staging overlay ──────────────────────────────────────────────────────

@live
def test_overlay_reads_staging_first_then_published(tree):
    staging = tree / ".staging"
    (staging / "ar").mkdir(parents=True)
    (staging / "ar" / "regions.json").write_bytes(b'{"staged": true}')
    ov = overlay_tree(staging, tree)

    assert json.loads(ov.get("ar/regions.json")) == {"staged": True}
    # Not staged -> the published copy, which is the whole point: the overlay
    # is the tree as it will be after promote().
    assert ov.get("index.json") is not None
    assert ov.probe("ar/regions.json") == 16
    assert ov.get("nope/missing.json") is None
    assert ov.probe("nope/missing.json") is None
    # No single directory, so no orphan check is possible from an overlay.
    assert ov.root is None


@live
def test_overlay_validates_a_product_the_published_tree_lacks(tree):
    """A staged fix must be judged on the staged bytes, not the served ones."""
    doc = _read(tree / "ar" / "regions.json")
    doc["count"] = 999                      # break the PUBLISHED copy
    _write(tree / "ar" / "regions.json", doc)
    assert not product_ok(
        validate_products(tree, products=["active_regions"])["active_regions"])

    doc["count"] = len(doc["regions"])      # ...and stage the correct one
    staging = tree / ".staging" / "ar"
    staging.mkdir(parents=True)
    _write(staging / "regions.json", doc)

    reports = validate_products(overlay_tree(tree / ".staging", tree),
                                products=["active_regions"])
    assert product_ok(reports["active_regions"], strict=True), failing_checks(
        reports["active_regions"])
