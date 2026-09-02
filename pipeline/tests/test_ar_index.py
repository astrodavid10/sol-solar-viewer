"""ar_index: a position into a table CI regenerates every four hours.

Five of the six CI failures were this. The seed set is frozen for the day it
was traced; `ar/regions.json` is rebuilt every run; NOAA's list went 6 -> 5 -> 4
over three days, so any published product older than the next contraction died
on

    FAIL ar_index within regions.json bounds -- range [-1,5] vs 5 regions

and, because validation was all-or-nothing and ran after the promote, took the
five products CI *could* build down with it (footgun 50, measured 2026-08-30,
site 13 h stale on everything).

Schema /2's `seed_regions` makes the hard bound self-consistent and demotes the
comparison against today's list to advice, because a region leaving the SRS is
normal (footgun 23).
"""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from ..config import SCHEMA_PFSS, SCHEMA_PFSS_ACCEPTED
from ..pfss.seeds import region_numbers_for
from ..validate import (Report, _check_ar_index, failing_checks, product_ok,
                        validate_products)

ROOT = Path(__file__).resolve().parents[2] / "public" / "data"

live = pytest.mark.skipif(not (ROOT / "pfss" / "manifest.json").is_file(),
                          reason="no published tree in public/data")


def _ar(*values):
    """An ar_index column: one background row plus the given region rows."""
    return np.asarray([-1] + list(values), dtype=np.int64)


def _run(man, ar, region_numbers):
    rep = Report(verbose=True)
    _check_ar_index(rep, man, ar, region_numbers)
    return rep


# ── schema /2: the self-consistent bound ─────────────────────────────────────

def test_regions_that_rotated_off_are_advice_not_failure():
    """Six frozen seed regions, four still listed: 0 FAIL, 1 WARN."""
    man = {"seed_regions": [4510, 4511, 4512, 4513, 4514, 4515]}
    rep = _run(man, _ar(0, 3, 5), [4510, 4512, 4513, 4515])
    assert rep.failures == 0, failing_checks(rep)
    warn = [ln for ln in rep.lines if "WARN" in ln]
    assert len(warn) == 1, rep.lines
    assert "2 of 6 seed regions no longer listed" in warn[0]
    assert "4511" in warn[0] and "4514" in warn[0]
    # And -- the entire point -- it must not be fatal even under --strict,
    # because this fires on a ~2-day fuse and used to block the whole publish.
    assert rep.warnings == 0 and rep.advisories == 1
    assert product_ok(rep, strict=True)


def test_ar_index_off_the_end_of_seed_regions_is_a_failure():
    """The bound that stays: 6 seed regions, an ar_index of 6."""
    man = {"seed_regions": [4510, 4511, 4512, 4513, 4514, 4515]}
    rep = _run(man, _ar(0, 6), [4510, 4511, 4512, 4513, 4514, 4515])
    fails = failing_checks(rep)
    assert len(fails) == 1, rep.lines
    assert "ar_index within seed_regions bounds" in fails[0]
    assert "[-1,6] vs 6 seed region(s)" in fails[0]


def test_all_seed_regions_still_listed_is_a_clean_pass():
    man = {"seed_regions": [4510, 4511]}
    rep = _run(man, _ar(0, 1), [4511, 4510, 4599])
    assert rep.failures == 0 and rep.warnings == 0 and rep.advisories == 0
    assert any("every seed region is still listed" in ln for ln in rep.lines)


def test_ar_index_below_minus_one_is_always_a_failure():
    rep = _run({"seed_regions": [4510]}, _ar(-2, 0), [4510])
    assert any("ar_index >= -1" in c for c in failing_checks(rep))


def test_a_shrinking_region_list_no_longer_fails_a_schema_2_product():
    """Footgun 50's exact numbers: seeds frozen against 6, SRS down to 5."""
    man = {"seed_regions": [4510, 4511, 4512, 4513, 4514, 4515]}
    rep = _run(man, _ar(0, 5), [4510, 4511, 4512, 4513, 4514])
    assert rep.failures == 0, failing_checks(rep)
    assert product_ok(rep, strict=True)


def test_a_garbage_seed_regions_value_is_reported():
    rep = _run({"seed_regions": [4510, 0, -3]}, _ar(0, 2), [4510])
    assert any("positive NOAA region numbers" in c for c in failing_checks(rep))


def test_missing_regions_json_skips_the_cross_check_but_keeps_the_bound():
    man = {"seed_regions": [4510, 4511]}
    rep = _run(man, _ar(0, 1), None)
    assert rep.failures == 0 and rep.warnings == 0 and rep.advisories == 0
    rep = _run(man, _ar(0, 2), None)
    assert any("seed_regions bounds" in c for c in failing_checks(rep))


# ── schema /1: the legacy path the published tree still uses ─────────────────

def test_a_legacy_manifest_gets_the_old_bound_against_regions_json():
    rep = _run({}, _ar(0, 3), [4510, 4511, 4512, 4513])
    assert rep.failures == 0
    assert any("legacy manifest" in ln for ln in rep.lines)

    rep = _run({}, _ar(0, 4), [4510, 4511, 4512, 4513])
    fails = failing_checks(rep)
    assert len(fails) == 1 and "regions.json bounds" in fails[0]


def test_a_legacy_manifest_with_no_regions_json_warns_as_it_always_did():
    rep = _run({}, _ar(0, 3), None)
    assert rep.failures == 0 and rep.warnings == 1
    assert not product_ok(rep, strict=True)     # unchanged: this one IS fatal


def test_both_pfss_schemas_are_accepted():
    # CI cannot retrace the field (footgun 33), so the served /1 manifest has
    # to keep validating after the bump.
    assert SCHEMA_PFSS == "sol.pfss/2"
    assert set(SCHEMA_PFSS_ACCEPTED) == {"sol.pfss/1", "sol.pfss/2"}


# ── through the real validator, on a real tree ───────────────────────────────

@live
def test_seed_regions_survives_a_shrinking_list_end_to_end(tmp_path):
    tree = tmp_path / "data"
    shutil.copytree(ROOT, tree)
    man_path = tree / "pfss" / "manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8"))
    regions = json.loads(
        (tree / "ar" / "regions.json").read_text(encoding="utf-8"))
    today = [r["number"] for r in regions["regions"]]
    assert today, "published tree lists no regions"

    # Freeze against today's list plus two regions that have since gone, and
    # declare schema /2 -- i.e. exactly what a product traced two days before
    # a contraction looks like.
    man["schema"] = SCHEMA_PFSS
    man["seed_regions"] = list(today) + [9998, 9999]
    man_path.write_text(json.dumps(man), encoding="utf-8")

    reports = validate_products(tree, strict=True, products=["pfss"])
    rep = reports["pfss"]
    assert product_ok(rep, strict=True), failing_checks(rep)
    assert rep.advisories == 1
    assert any("9998" in ln and "9999" in ln for ln in rep.lines
               if "WARN" in ln), [ln for ln in rep.lines if "WARN" in ln]


def test_region_numbers_round_trips_through_the_seed_npz(tmp_path):
    """A cache hit must not lose the mapping, and an OLD npz must recover it.

    The recovery is a derivation, not a rebuild of the seed arrays: the npz
    already carries `regions_json`, and freeze_seed_set reads `rnumber` off
    that same list in that same order, so re-deriving is bit-identical to what
    it would have stored -- and a rebuild would burn a second for it.
    """
    import numpy as np

    from ..pfss.seeds import (SeedSet, load_newest_seed_set, save_seed_set,
                              _seed_cache_path)

    regions = [{"rnumber": 4510, "lat": 12, "lon": 3, "cLon": 100,
                "area": 50, "ext": 4, "numSpots": 2},
               {"rnumber": 4511, "lat": -8, "lon": -20, "cLon": 200,
                "area": 30, "ext": 3, "numSpots": 1}]
    ss = SeedSet(lats=np.zeros(3), lons=np.zeros(3), rs=np.ones(3),
                 ar_index=np.asarray([-1, 0, 1], dtype=np.int16), n_bg=1,
                 region_seed_counts=[1, 1], regions=regions, srs_epoch=None,
                 seed_set_id="abcd1234", region_numbers=[4510, 4511])
    save_seed_set(tmp_path, ss)
    back = load_newest_seed_set(tmp_path)
    assert back is not None and back.region_numbers == [4510, 4511]

    # Now the legacy shape: the same npz with the array stripped out.
    path = _seed_cache_path(tmp_path, "abcd1234")
    with np.load(str(path), allow_pickle=False) as z:
        kept = {k: z[k] for k in z.files if k != "region_numbers"}
    np.savez_compressed(str(path), **kept)
    back = load_newest_seed_set(tmp_path)
    assert back is not None and back.region_numbers == [4510, 4511]


@live
def test_region_numbers_for_matches_the_published_regions_order():
    regions = json.loads(
        (ROOT / "ar" / "regions.json").read_text(encoding="utf-8"))
    # regions.json entries call it `number`; the SRS dicts the seed builder
    # sees call it `rnumber`. Same value, same order -- that identity is what
    # `seed_regions` ships.
    as_srs = [{"rnumber": r["number"]} for r in regions["regions"]]
    assert region_numbers_for(as_srs) == [r["number"]
                                          for r in regions["regions"]]
