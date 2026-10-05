"""HMI channels come from JSOC's dated tree (footgun 59).

SDO GSFC stopped publishing HMI browse frames on 2026-09-24. JSOC's images are
the same product (same disk, same orientation, correlation 0.999/1.000 at the
identical instant), served at 4096 only and with no undated fallback.
"""

import io
from datetime import datetime, timezone

import numpy as np
import pytest
from PIL import Image

from ..io_utils import PipelineError
from ..texture import export

NOW = datetime(2026, 10, 5, 11, 0, tzinfo=timezone.utc)

LISTING = """<a href="20261005_103000_Ic_4k.jpg">x</a>
<a href="20261005_103000_Ic_flat_4k.jpg">x</a>
<a href="20261005_103000_M_4k.jpg">x</a>
<a href="20261005_103000_M_color_4k.jpg">x</a>
<a href="20261005_103000_M_1k.jpg">x</a>
<a href="20261005_104500_M_4k.jpg">x</a>
<a href="20261005_120000_M_4k.jpg">x</a>"""


@pytest.fixture
def jsoc_listing(monkeypatch):
    seen = []

    def listing(day, jsoc=False):
        seen.append((day.date().isoformat(), jsoc))
        return LISTING if jsoc and day.date() == NOW.date() else ""

    monkeypatch.setattr(export, "_day_listing", listing)
    return seen


def test_hmi_channels_are_sourced_from_jsoc():
    assert export.channel_for("HMIB")["source"] == "jsoc"
    assert export.channel_for("HMIIC")["source"] == "jsoc"
    assert "source" not in export.channel_for("0171")


def test_jsoc_candidates_match_only_the_4k_product_asked_for(jsoc_listing):
    got = export.browse_candidates(NOW, days=1, code="HMIB")
    names = [u.rsplit("/", 1)[-1] for _, u in got]
    # M_color, M_1k and the Ic products are not the magnetogram at 4k; the
    # 12:00 frame is in the future and is dropped.
    assert names == ["20261005_103000_M_4k.jpg", "20261005_104500_M_4k.jpg"]
    assert got[0][1].startswith(export.JSOC_HMI_BASE + "/2026/10/05/")
    assert jsoc_listing == [("2026-10-05", True)]


def test_aia_channels_still_read_the_gsfc_listing(jsoc_listing):
    export.browse_candidates(NOW, days=1, code="0171")
    assert jsoc_listing == [("2026-10-05", False)]


def _jpeg(size):
    buf = io.BytesIO()
    Image.new("RGB", (size, size), (200, 100, 20)).save(buf, "JPEG")
    return buf.getvalue()


def test_a_jsoc_still_is_asserted_at_4096_then_downsampled():
    raw = _jpeg(4096)
    arr = export._load_rgb(raw, 2048, "HMIB")
    assert arr.shape == (2048, 2048, 3)
    full = export._decode(raw, src_res=4096)
    assert np.allclose(arr.mean(axis=(0, 1), dtype=np.float64),
                       full.mean(axis=(0, 1), dtype=np.float64), atol=1.0)


def test_a_wrong_sized_jsoc_still_is_refused():
    with pytest.raises(PipelineError, match="expected 4096x4096"):
        export._load_rgb(_jpeg(1024), 1024, "HMIB")


def test_no_undated_fallback_for_a_jsoc_channel(monkeypatch):
    monkeypatch.setattr(export, "browse_candidates", lambda *a, **k: [])
    monkeypatch.setattr(export, "http_get_full", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("fell back to a latest_* still")))
    with pytest.raises(PipelineError, match="no usable JSOC HMIB frame"):
        export.fetch_source(NOW, code="HMIB")
