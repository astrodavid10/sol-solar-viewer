"""The latest_*.jpg fallback may not publish an old or undated image.

The defect (2026-10-04): SDO stopped publishing HMI browse frames on
2026-09-24 and froze every latest_*.jpg at 2026-09-21. fetch_source fell back
to those stills with no age bound, so the Visible Sun and Magnetic Map layers
showed 13-day-old maps under a texture product that said ok. A missing
Last-Modified used to become `now`, which invented an observation time.
"""

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest

from ..io_utils import PipelineError
from ..texture import export

NOW = datetime(2026, 10, 4, 20, 0, tzinfo=timezone.utc)


def _no_browse(monkeypatch, headers):
    """An empty browse archive and a latest_*.jpg answering with `headers`."""
    monkeypatch.setattr(export, "browse_candidates", lambda *a, **k: [])

    def fake_get(url, timeout=30.0, **_kw):
        assert "/latest_" in url
        return b"not-a-jpeg", headers

    monkeypatch.setattr(export, "http_get_full", fake_get)
    # Reaching the decoder means the guard let the image through.
    monkeypatch.setattr(export, "_decode", lambda raw, src_res=0: (_ for _ in ()).throw(
        AssertionError("decoded an image the age guard should have refused")))


def test_an_old_latest_still_is_refused(monkeypatch):
    lm = format_datetime(NOW - timedelta(days=13), usegmt=True)
    _no_browse(monkeypatch, {"last-modified": lm})
    with pytest.raises(PipelineError, match="past the 24 h ceiling"):
        export.fetch_source(NOW, code="HMIB")


def test_an_undated_latest_still_is_refused(monkeypatch):
    _no_browse(monkeypatch, {})
    with pytest.raises(PipelineError, match="observation time is unknown"):
        export.fetch_source(NOW, code="HMIIC")


def test_a_recent_latest_still_reaches_the_decoder(monkeypatch):
    lm = format_datetime(NOW - timedelta(hours=2), usegmt=True)
    _no_browse(monkeypatch, {"last-modified": lm})
    with pytest.raises(AssertionError, match="decoded an image"):
        export.fetch_source(NOW, code="0171")


def test_the_ceiling_is_per_channel_with_a_global_default():
    assert export.max_age_hours({"code": "X"}) == export.TEX_MAX_OBS_AGE_HOURS
    assert export.max_age_hours({"code": "X", "max_age_hours": 6}) == 6.0


def test_layer_status_uses_the_channel_ceiling():
    assert export.texture_status(5.0, 6.0) == "ok"
    assert export.texture_status(7.0, 6.0) == "degraded"
