"""The GONG FITS cache is pruned to the window by observation time."""

from datetime import datetime, timezone

from ..sources.gong import prune_cache


def test_prune_keys_on_the_filename_stamp_not_the_mtime(tmp_path):
    for name in ("mrzqs260901t1914c2313_000.fits",
                 "mrzqs261004t1914c2316_000.fits", "notes.txt"):
        (tmp_path / name).write_text("x")
    removed = prune_cache(tmp_path, datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert removed == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "mrzqs261004t1914c2316_000.fits", "notes.txt"]
