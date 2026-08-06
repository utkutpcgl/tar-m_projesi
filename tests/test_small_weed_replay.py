from __future__ import annotations

from scripts.build_small_weed_replay_v1 import _window


def test_center_window_is_fixed_size_interior() -> None:
    start, end, before, after = _window(600.0, 1400)
    assert (start, end, before, after) == (344, 856, 0, 0)
    assert end - start + before + after == 512


def test_center_window_pads_at_image_edges() -> None:
    for center, length in ((3.0, 1000), (997.0, 1000), (20.0, 120)):
        start, end, before, after = _window(center, length)
        assert start >= 0 and end <= length
        assert end - start + before + after == 512
