"""Today's SRS regions get the same impossible-position guard as the JSON feed.

Footgun 51's drop (NOAA keyed AR4521 at latitude 98) existed only in
fetch_regions_json. parse_srs, which feeds today's field-line seeds and
markers, accepted any two-digit latitude, and a changed header made it return
an empty list that published as a genuinely spotless Sun.
"""

import pytest

from ..sources.srs import SrsFormatError, parse_srs, region_is_possible

HEADER = """:Product: 1005SRS.txt
I.  Regions with Sunspots.  Locations Valid at 04/2400Z
Nmbr Location  Lo  Area  Z   LL   NN Mag Type
"""


def test_a_good_region_parses():
    regs = parse_srs(HEADER + "4545 N20E33  222  0020 Dao  06  05 Beta\nIA. H-alpha Plages\n")
    assert [(r["rnumber"], r["lat"], r["lon"], r["cLon"]) for r in regs] == [(4545, 20, -33, 222)]


def test_an_impossible_latitude_is_dropped_loudly(capsys):
    regs = parse_srs(HEADER + "4521 N98E67  100  0010 Axx  01  01 Alpha\n"
                              "4545 N20E33  222  0020 Dao  06  05 Beta\nIA.\n")
    assert [r["rnumber"] for r in regs] == [4545]
    assert "AR4521: impossible record" in capsys.readouterr().out


def test_a_spotless_sun_is_still_legal():
    assert parse_srs(HEADER + "None\nIA. H-alpha Plages\n") == []


def test_a_missing_header_is_a_format_error_not_a_spotless_sun():
    with pytest.raises(SrsFormatError):
        parse_srs(":Product: SRS\nSomething entirely different\n")


@pytest.mark.parametrize("lat,lon,clon,ok", [
    (20, -33, 222, True), (60, 180, 0, True), (61, 0, 0, False),
    (0, 181, 0, False), (0, 0, 360, False), (0, 0, -1, False)])
def test_bounds(lat, lon, clon, ok):
    assert region_is_possible(lat, lon, clon) is ok
