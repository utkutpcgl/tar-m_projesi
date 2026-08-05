import pytest

from scripts.build_camelinaweed_contact_sheet import quantile_index


@pytest.mark.parametrize(
    ("size", "quantile", "expected"),
    [(1, 0.1, 0), (10, 0.1, 1), (10, 0.5, 4), (10, 0.9, 8), (11, 0.5, 5)],
)
def test_quantile_index(size: int, quantile: float, expected: int) -> None:
    assert quantile_index(size, quantile) == expected


@pytest.mark.parametrize(("size", "quantile"), [(0, 0.5), (2, -0.1), (2, 1.1)])
def test_quantile_index_rejects_invalid_input(size: int, quantile: float) -> None:
    with pytest.raises(ValueError):
        quantile_index(size, quantile)
