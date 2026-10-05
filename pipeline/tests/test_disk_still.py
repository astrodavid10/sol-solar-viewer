"""The default channel publishes a 1024 px disk still for the app's failure card (T33)."""

import io
from datetime import datetime, timezone

import numpy as np
from PIL import Image

from ..texture import export


def test_the_disk_still_is_a_1024_jpeg_of_the_source():
    rgb = np.zeros((4096, 4096, 3), np.float32)
    rgb[1024:3072, 1024:3072] = (240.0, 160.0, 20.0)
    src = export.SourceImage(rgb, datetime(2026, 10, 5, tzinfo=timezone.utc),
                             "https://example.test/x.jpg", "browse", 0)
    blob = export.build_disk_still(src)
    with Image.open(io.BytesIO(blob)) as im:
        assert im.format == "JPEG" and im.size == (1024, 1024)
        centre = np.asarray(im.convert("RGB"))[512, 512]
    assert abs(int(centre[0]) - 240) < 8 and abs(int(centre[2]) - 20) < 8
    assert export.disk_still_name("0171") == "sdo0171_disk_1024.jpg"
