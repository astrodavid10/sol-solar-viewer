"""The limb guard is a band around each channel's own measured limb offset.

Measured 2026-10-04 at the fixed fit resolution (12 frames per channel): 0193
sits at +3.49% (8 of 12 frames over a zero-centred 3%), 0304 at +2.22%, 0171
at -0.87%. The band moved, its width did not (footgun 40).
"""

import pytest

from ..config import TEX_CHANNELS, TEX_LIMB_RADIUS_TOL
from ..texture.export import channel_for, limb_in_band

MEASURED = {
    "0193": [3.44, 2.88, 2.99, 4.16, 3.37, 4.64, 2.92, 3.84, 3.65, 2.97, 3.92, 3.06],
    "0171": [-0.18, -0.75, -0.40, -0.58, -1.60, -0.64, -0.75, -1.23, -0.93, -1.14, -1.14, -1.11],
    "0304": [2.20, 2.25, 2.05, 2.03, 2.25, 2.27, 2.32, 2.08, 2.31, 2.15, 2.45, 2.23],
}


def test_the_tolerance_was_not_widened():
    assert TEX_LIMB_RADIUS_TOL == 0.03


@pytest.mark.parametrize("code", sorted(MEASURED))
def test_every_measured_frame_passes(code):
    ch = channel_for(code)
    assert all(limb_in_band(x / 100.0, ch) for x in MEASURED[code])


@pytest.mark.parametrize("code", sorted(MEASURED))
@pytest.mark.parametrize("shift", [+0.035, -0.035])
def test_a_recrop_of_every_channel_is_still_caught(code, shift):
    ch = channel_for(code)
    mean = sum(MEASURED[code]) / len(MEASURED[code]) / 100.0
    assert not limb_in_band(mean + shift, ch)


def test_every_channel_declares_its_offset():
    assert all("limb_excess" in ch for ch in TEX_CHANNELS)
