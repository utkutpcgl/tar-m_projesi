import io

import numpy as np
import pytest
from PIL import Image

from scripts.convert_weedy_rice_uav import (
    coverage_bin,
    normalized_mask_png,
    parse_rgb_filename,
)


def test_parse_standardized_rgb_filename() -> None:
    parsed = parse_rgb_filename(
        "DJI_DateTime_2024_06_02_13_42_0035_lat_10.3040603_"
        "lon_105.2619317_alt_20.018m.JPG"
    )

    assert parsed == {
        "date": "2024-06-02",
        "hour_minute": "13:42",
        "index": "0035",
        "latitude": 10.3040603,
        "longitude": 105.2619317,
        "altitude": 20.018,
    }


def test_parse_standardized_rgb_filename_rejects_unpinned_layout() -> None:
    with pytest.raises(ValueError, match="Unexpected"):
        parse_rgb_filename("DJI_0035.JPG")


def test_partial_mask_mapping_never_turns_source_zero_into_background() -> None:
    source = np.array([[0, 255], [255, 0]], dtype=np.uint8)

    payload = normalized_mask_png(source)
    with Image.open(io.BytesIO(payload)) as image:
        normalized = np.asarray(image, dtype=np.uint8)

    assert normalized.tolist() == [[255, 2], [2, 255]]


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [
        (0.01, "gt_0_le_5_percent"),
        (0.05, "gt_0_le_5_percent"),
        (0.10, "gt_5_le_10_percent"),
        (0.20, "gt_10_le_20_percent"),
        (0.30, "gt_20_le_30_percent"),
        (0.40, "gt_30_le_40_percent"),
        (0.60, "gt_40_le_60_percent"),
        (0.75, "gt_60_le_75_percent"),
        (0.899, "gt_75_lt_90_percent"),
    ],
)
def test_coverage_bins(fraction: float, expected: str) -> None:
    assert coverage_bin(fraction) == expected


@pytest.mark.parametrize("fraction", [0.0, 0.91])
def test_coverage_bins_reject_release_exclusions(fraction: float) -> None:
    with pytest.raises(ValueError):
        coverage_bin(fraction)
