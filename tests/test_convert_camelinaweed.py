import io

import numpy as np
import pytest
from PIL import Image

from scripts.convert_camelinaweed import (
    normalized_partial_mask_png,
    polygon_points,
)


def test_polygon_points_accepts_closed_coco_image_boundary() -> None:
    points, boundaries = polygon_points([0, 0, 10, 0, 10, 8], 10, 8)

    assert points == [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0)]
    assert boundaries == 3


@pytest.mark.parametrize(
    "polygon",
    [
        [0, 0, 1, 1],
        [0, 0, 1, 1, 2, 2, 3],
        [0, 0, 1, 1, 11, 2],
        [0, 0, 1, 1, True, 2],
        [0, 0, 1, 1, float("nan"), 2],
    ],
)
def test_polygon_points_rejects_invalid_polygon(polygon: list[object]) -> None:
    with pytest.raises(ValueError):
        polygon_points(polygon, 10, 8)


def test_partial_mask_keeps_every_non_polygon_pixel_ignored() -> None:
    payload, positive = normalized_partial_mask_png(
        5, 5, [[(1.0, 1.0), (3.0, 1.0), (1.0, 3.0)]]
    )

    with Image.open(io.BytesIO(payload)) as image:
        mask = np.asarray(image, dtype=np.uint8)
    assert positive == int((mask == 2).sum())
    assert positive > 0
    assert set(np.unique(mask)) == {2, 255}
    assert mask[0, 0] == 255
    assert mask[1, 1] == 2


def test_partial_mask_rejects_empty_polygon_inventory() -> None:
    with pytest.raises(ValueError, match="accepted polygon"):
        normalized_partial_mask_png(5, 5, [])
