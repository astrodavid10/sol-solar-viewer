"""The manifest URL walker, against the LIVE published manifests.

Deliberately not a synthetic fixture for the coverage tests: the walker's whole
job is to find urls nobody remembered to enumerate, and a fixture can only
contain the ones its author remembered.  The published tree is the only
document that has the real shape.
"""

import json
import shutil
from pathlib import Path

import pytest

from ..manifest_urls import (is_sibling_file_url, is_url_key,
                             iter_manifest_urls, manifest_url_set)
from ..validate import validate

ROOT = Path(__file__).resolve().parents[2] / "public" / "data"
TEXTURE_JSON = ROOT / "texture" / "texture.json"
PFSS_JSON = ROOT / "pfss" / "manifest.json"

live = pytest.mark.skipif(not TEXTURE_JSON.is_file(),
                          reason="no published tree in public/data")


def _load(p):
    return json.loads(p.read_text(encoding="utf-8"))


# ── the rule itself ──────────────────────────────────────────────────────────

def test_url_key_convention():
    assert is_url_key("url") and is_url_key("topology_url")
    assert is_url_key("source_url") and is_url_key("active_regions_url")
    assert not is_url_key("urls") and not is_url_key("curl")


def test_absolute_urls_are_not_files_in_our_tree():
    assert not is_sibling_file_url(
        "https://sdo.gsfc.nasa.gov/assets/img/browse/x.jpg")
    assert not is_sibling_file_url("//cdn.example/x.jpg")
    assert not is_sibling_file_url("data:image/jpeg;base64,AAA")


def test_cross_directory_urls_are_skipped():
    # pfss/manifest.json's active_regions_url. Excluded on purpose: it is a
    # cross-product pointer, and resolving it would couple pfss's existence
    # pass to the active-regions product's presence.
    assert not is_sibling_file_url("../ar/regions.json")
    assert not is_sibling_file_url("sub/dir/x.jpg")


def test_nesting_depth_is_irrelevant():
    doc = {"a": {"b": [{"c": {"d": [{"url": "deep.jpg"}]}}]}}
    assert list(iter_manifest_urls(doc)) == ["deep.jpg"]


def test_duplicates_collapse():
    # The newest texture frame's url IS the layer's url, by design.
    doc = {"url": "same.jpg", "frames": [{"url": "same.jpg"}]}
    assert list(iter_manifest_urls(doc)) == ["same.jpg"]


# ── coverage on the live manifests ───────────────────────────────────────────

@live
def test_walker_finds_every_texture_file_on_disk():
    doc = _load(TEXTURE_JSON)
    found = manifest_url_set(doc)
    on_disk = {p.name for p in (ROOT / "texture").glob("*.jpg")}
    assert found == on_disk, {
        "missing_from_walker": sorted(on_disk - found),
        "referenced_but_absent": sorted(found - on_disk),
    }
    # Sanity on the magnitude: 5 channels x (18 frames + 3 off-limb tiers)
    # plus a high_res map each, minus the newest-frame/layer-url and
    # default-tier duplicates.
    assert len(found) > 100, len(found)


@live
def test_walker_finds_every_nested_texture_block():
    """The four blocks the hand-written keep-set forgot, one at a time."""
    doc = _load(TEXTURE_JSON)
    found = manifest_url_set(doc)
    layer = doc["layers"][0]
    assert layer["url"] in found
    assert layer["off_limb"]["url"] in found
    for tier in layer["off_limb"].get("tiers") or []:
        assert tier["url"] in found
    for frame in layer["frames"]:
        assert frame["url"] in found
        near = frame.get("near_side")
        if isinstance(near, dict):
            assert near["url"] in found
    hires = layer.get("high_res")
    if isinstance(hires, dict):
        assert hires["url"] in found
    # And source_url, which is external provenance, is NOT a file we keep.
    assert layer["source_url"] not in found


@live
def test_walker_finds_topology_and_every_pfss_frame():
    doc = _load(PFSS_JSON)
    found = manifest_url_set(doc)
    on_disk = {p.name for p in (ROOT / "pfss").glob("*.bin")}
    assert found == on_disk, {
        "missing_from_walker": sorted(on_disk - found),
        "referenced_but_absent": sorted(found - on_disk),
    }
    assert doc["geometry"]["topology_url"] in found
    for frame in doc["frames"]:
        assert frame["url"] in found
    assert len(found) == len(doc["frames"]) + 1
    # The cross-product pointer is not a file this product owns.
    assert doc["active_regions_url"] not in found


# ── the validator passes the walker feeds ────────────────────────────────────

def _texture_only_tree(tmp_path: Path) -> Path:
    """A tree with only texture/ + index.json, so the report is about texture.

    index.json claims texture is `ok`, which is what makes a missing file a
    failure rather than a legitimately-absent product.
    """
    dst = tmp_path / "data"
    (dst / "texture").mkdir(parents=True)
    for p in (ROOT / "texture").iterdir():
        if p.is_file():
            shutil.copy2(p, dst / "texture" / p.name)
    shutil.copy2(ROOT / "index.json", dst / "index.json")
    return dst


def _fail_lines(text: str):
    return [ln for ln in text.splitlines() if ln.strip().startswith("FAIL")]


@live
def test_deleting_a_non_sampled_history_frame_is_caught(tmp_path):
    """The hole this pass was written to close.

    _check_texture_frames decodes the newest, middle and oldest of eighteen,
    so deleting one of the other fifteen used to leave --strict passing.
    """
    tree = _texture_only_tree(tmp_path)
    doc = _load(tree / "texture" / "texture.json")
    frames = doc["layers"][0]["frames"]
    # Index 5 of 18 is neither 0, nor 8 (the middle), nor the newest.
    victim = frames[5]["url"]
    assert victim != doc["layers"][0]["url"]
    (tree / "texture" / victim).unlink()

    ok, text = validate(root=str(tree), strict=True)
    assert not ok
    hits = [ln for ln in _fail_lines(text) if "is in the tree" in ln]
    assert len(hits) == 1, _fail_lines(text)
    assert victim in hits[0], hits[0]


@live
def test_a_zero_byte_referenced_file_is_caught(tmp_path):
    tree = _texture_only_tree(tmp_path)
    doc = _load(tree / "texture" / "texture.json")
    victim = doc["layers"][0]["frames"][5]["url"]
    (tree / "texture" / victim).write_bytes(b"")

    ok, text = validate(root=str(tree), strict=True)
    assert not ok
    assert any("zero bytes" in ln for ln in _fail_lines(text)), _fail_lines(text)


@live
def test_orphan_is_a_failure_only_when_asked_for(tmp_path):
    tree = _texture_only_tree(tmp_path)
    (tree / "texture" / "zzz.jpg").write_bytes(b"not really a jpeg")

    ok_off, text_off = validate(root=str(tree), strict=True,
                                check_orphans=False)
    assert not any("unreferenced" in ln for ln in _fail_lines(text_off))

    ok_on, text_on = validate(root=str(tree), strict=True, check_orphans=True)
    assert not ok_on
    hits = [ln for ln in _fail_lines(text_on) if "unreferenced" in ln]
    assert len(hits) == 1 and "zzz.jpg" in hits[0], _fail_lines(text_on)
