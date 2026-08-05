import pytest

from scripts.build_weedy_rice_uav_contact_sheet import coverage_bin


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [
        (0.001, "gt_0_le_5"),
        (0.05, "gt_0_le_5"),
        (0.0501, "gt_5_le_10"),
        (0.2, "gt_10_le_20"),
        (0.3, "gt_20_le_30"),
        (0.4, "gt_30_le_40"),
        (0.6, "gt_40_le_60"),
        (0.75, "gt_60_le_75"),
        (0.899, "gt_75_lt_90"),
    ],
)
def test_coverage_bin(fraction: float, expected: str) -> None:
    assert coverage_bin(fraction) == expected


@pytest.mark.parametrize("fraction", [0.0, 0.901])
def test_coverage_bin_rejects_outside_release_range(fraction: float) -> None:
    with pytest.raises(ValueError):
        coverage_bin(fraction)
