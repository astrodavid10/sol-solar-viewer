"""A failed non-default channel keeps its last good layer, within its ceiling.

0193 failed the limb-fit guard in 3 of 4 runs around 2026-10-04. Each failure
dropped the layer from the site and _prune_orphan_textures deleted its
history, so the guest's "Hot Corona" option came and went between runs.
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from ..cli import _carry_forward_layer
from ..io_utils import iso_z

NOW = datetime(2026, 10, 5, 1, 0, tzinfo=timezone.utc)
CH = {"code": "0193", "label": "Hot Corona"}


def _tree(tmp_path, obs_age_hours, with_files=True):
    tex = tmp_path / "texture"
    tex.mkdir()
    layer = {
        "channel": "0193", "url": "sdo0193_carrington_4096x2048.jpg",
        "obs_iso": iso_z(NOW - timedelta(hours=obs_age_hours)),
        "off_limb": {"tiers": [{"size": 1024, "url": "sdo0193_offlimb_1024.jpg"}]},
        "frames": [{"target_iso": "x", "url": "old.jpg"}],
    }
    (tex / "texture.json").write_text(json.dumps({"layers": [layer]}))
    if with_files:
        for name in (layer["url"], "sdo0193_offlimb_1024.jpg"):
            (tex / name).write_bytes(b"jpg")
    noted = []
    ctx = SimpleNamespace(out=tmp_path, now=NOW,
                          staging=SimpleNamespace(note=noted.append))
    return ctx, noted


def test_a_recent_layer_is_carried_and_marked(tmp_path):
    ctx, noted = _tree(tmp_path, 5)
    got = _carry_forward_layer(ctx, CH)
    assert got["carried"] is True and got["status"] == "ok"
    assert got["obs_age_hours"] == 5.0
    assert "frames" not in got                  # rebuilt by _texture_history
    assert "texture/sdo0193_carrington_4096x2048.jpg" in noted


def test_a_layer_past_its_ceiling_is_not_carried(tmp_path):
    ctx, _ = _tree(tmp_path, 30)
    assert _carry_forward_layer(ctx, CH) is None


def test_a_layer_whose_files_are_gone_is_not_carried(tmp_path):
    ctx, _ = _tree(tmp_path, 5, with_files=False)
    assert _carry_forward_layer(ctx, CH) is None


def test_a_channel_never_published_is_not_carried(tmp_path):
    ctx, _ = _tree(tmp_path, 5)
    assert _carry_forward_layer(ctx, {"code": "HMIB"}) is None
