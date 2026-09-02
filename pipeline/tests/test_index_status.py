"""index.json's fallback status decision.

The bug this pins: `_existing_product` derived status purely from the age of
the PREVIOUSLY PUBLISHED copy, so a stage that raised got
``status: "ok", note: "not regenerated this run"`` -- indistinguishable from a
stage nobody asked to run.  Footgun 48 records what that costs: a self-
inflicted ImportError read as an upstream hiccup, with a green exit code.

`_fallback_status` is pure so the decision can be tested without a filesystem,
a network, or a five-minute run.
"""

from datetime import datetime, timedelta, timezone

from ..cli import _fallback_status, published_mag_unix, short_error
from ..config import STALE_HOURS

NOW = datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc)
FRESH = NOW - timedelta(hours=1)                    # inside STALE_HOURS
OLD = NOW - timedelta(hours=STALE_HOURS + 5.0)      # outside it
BOOM = RuntimeError("GONG listing timed out")


def test_fresh_copy_plus_failure_is_degraded():
    status, note, err = _fallback_status(True, FRESH, NOW, short_error(BOOM))
    assert status == "degraded"
    assert "stage failed this run" in note
    assert "GONG listing timed out" in note
    assert err == "RuntimeError: GONG listing timed out"


def test_stale_copy_plus_failure_stays_stale_but_names_the_failure():
    # `stale` is the stronger statement and must not be downgraded, but the
    # note and last_error still have to say the stage raised.
    status, note, err = _fallback_status(True, OLD, NOW, short_error(BOOM))
    assert status == "stale"
    assert "stage failed this run" in note
    assert err == "RuntimeError: GONG listing timed out"


def test_fresh_copy_deliberately_skipped_is_ok():
    status, note, err = _fallback_status(True, FRESH, NOW)
    assert status == "ok"
    assert note == "not regenerated this run"
    assert err == ""


def test_stale_copy_deliberately_skipped_is_stale():
    status, note, err = _fallback_status(True, OLD, NOW)
    assert status == "stale"
    assert note == "not regenerated this run"
    assert err == ""


def test_unparseable_generated_iso_counts_as_stale():
    status, _, _ = _fallback_status(True, None, NOW)
    assert status == "stale"


def test_nothing_published_is_absent_either_way():
    assert _fallback_status(False, None, NOW)[0] == "absent"
    status, note, err = _fallback_status(False, None, NOW, short_error(BOOM))
    assert status == "absent"
    assert "nothing has ever been published" in note
    assert err == "RuntimeError: GONG listing timed out"


def test_short_error_is_one_bounded_line():
    exc = ValueError("line one\nline two   with   spaces")
    assert short_error(exc) == "ValueError: line one line two with spaces"
    long = short_error(RuntimeError("x" * 500))
    assert len(long) == 200 and long.endswith("...")
    assert short_error(None) == ""


def test_published_mag_unix_prefers_the_frames():
    man = {"frames": [{"mag_unix": 100}, {"mag_unix": 300},
                      {"mag_unix": 200}],
           "newest_mag_unix": 999, "newest_mag_iso": "2026-01-01T00:00:00Z"}
    assert published_mag_unix(man) == 300


def test_published_mag_unix_falls_back_for_a_legacy_manifest():
    # A schema /1 manifest with no usable frames array still has to yield an
    # age, or the stale path loses data_age_hours again.
    assert published_mag_unix({"newest_mag_unix": 42}) == 42
    assert published_mag_unix(
        {"newest_mag_iso": "2026-09-02T12:00:00Z"}) == int(
            datetime(2026, 9, 2, 12, tzinfo=timezone.utc).timestamp())
    assert published_mag_unix({}) is None
    assert published_mag_unix(None) is None
