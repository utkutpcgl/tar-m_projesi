from __future__ import annotations

from scripts.build_camera_domain_comparison_gallery_v1 import quantile_indices


def test_quantile_indices_are_deterministic_and_cover_endpoints() -> None:
    assert quantile_indices(10, 3) == [0, 4, 9]
    assert quantile_indices(3, 10) == [0, 1, 2]
    assert quantile_indices(1, 2) == [0]
    assert quantile_indices(0, 2) == []
