"""A moved upstream fails loudly; an old DONKI cache is refused.

Footgun 58: CCMC retired the kauai DONKI base on 2026-09-30 with a 301 to an
HTML news page. urllib followed it, json.loads failed with "Expecting value",
which reads like a transient, and the events stage served its cache -- by then
empty -- to guests as "DONKI unreachable; served from cache", stamped now.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from ..io_utils import PipelineError, UpstreamContractError, _check_contract, iso_z
from ..sources import donki

NOW = datetime(2026, 10, 4, 20, 0, tzinfo=timezone.utc)
JSON_HDR = {"content-type": "application/json"}


def test_an_off_host_redirect_is_upstream_moved():
    with pytest.raises(UpstreamContractError, match=r"^UPSTREAM MOVED: .*redirected off-host"):
        _check_contract("https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get/FLR",
                        "https://ccmc.gsfc.nasa.gov/news/major-updates",
                        b"<!doctype html>", {"content-type": "text/html"}, "json")


def test_html_where_json_was_expected_is_upstream_moved():
    with pytest.raises(UpstreamContractError, match=r"^UPSTREAM MOVED: .*text/html"):
        _check_contract("https://x.test/a", "https://x.test/a",
                        b"  <html>", {"content-type": "text/html; charset=utf-8"}, "json")


def test_an_untyped_body_that_starts_with_a_tag_is_caught_too():
    with pytest.raises(UpstreamContractError):
        _check_contract("https://x.test/a", "https://x.test/a", b"<html>", {}, "json")


def test_a_same_host_json_response_passes():
    _check_contract("https://x.test/a", "https://x.test/a?b=1", b"[]", JSON_HDR, "json")


def _cache(tmp_path, kind, records, fetched):
    d = tmp_path / "donki"
    d.mkdir(parents=True, exist_ok=True)
    (d / "{0}.json".format(kind)).write_text(json.dumps(records))
    if fetched is not None:
        (d / "{0}.meta.json".format(kind)).write_text(json.dumps({"fetched_iso": fetched}))


def _offline(monkeypatch, exc):
    def boom(*a, **k):
        raise exc
    monkeypatch.setattr(donki, "http_get_full", boom)


def test_a_recent_cache_is_served_with_its_fetch_time(monkeypatch, tmp_path):
    fetched = iso_z(NOW - timedelta(hours=3))
    _cache(tmp_path, "FLR", [{"flrID": "a"}], fetched)
    _offline(monkeypatch, OSError("timed out"))
    data, source, got = donki._fetch("FLR", NOW, 72, tmp_path)
    assert (len(data), source, got) == (1, "cached", fetched)


def test_an_old_cache_is_refused(monkeypatch, tmp_path):
    _cache(tmp_path, "FLR", [{"flrID": "a"}], iso_z(NOW - timedelta(hours=30)))
    _offline(monkeypatch, OSError("timed out"))
    with pytest.raises(PipelineError, match="DONKI FLR unavailable"):
        donki._fetch("FLR", NOW, 72, tmp_path)


def test_a_cache_of_unknown_age_is_refused(monkeypatch, tmp_path):
    _cache(tmp_path, "CME", [], None)
    _offline(monkeypatch, OSError("timed out"))
    with pytest.raises(PipelineError):
        donki._fetch("CME", NOW, 72, tmp_path)


def test_a_moved_endpoint_never_falls_back_to_the_cache(monkeypatch, tmp_path):
    _cache(tmp_path, "FLR", [{"flrID": "a"}], iso_z(NOW - timedelta(hours=1)))
    _offline(monkeypatch, UpstreamContractError("UPSTREAM MOVED: test"))
    with pytest.raises(UpstreamContractError, match="^UPSTREAM MOVED"):
        donki._fetch("FLR", NOW, 72, tmp_path)
