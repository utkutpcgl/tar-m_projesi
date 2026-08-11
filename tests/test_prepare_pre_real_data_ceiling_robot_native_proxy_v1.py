from pathlib import Path

import numpy as np

from scripts.prepare_pre_real_data_ceiling_robot_native_proxy_v1 import (
    candidate_origins,
    choose_native_window,
    stratified_sample,
)


def test_candidate_origins_cover_corners_and_center_without_resize() -> None:
    assert candidate_origins(2048, 1536, 1024) == [
        (0, 0),
        (512, 0),
        (1024, 0),
        (0, 256),
        (512, 256),
        (1024, 256),
        (0, 512),
        (512, 512),
        (1024, 512),
    ]


def test_choose_native_window_requires_both_classes_and_prefers_weed() -> None:
    mask = np.zeros((8, 12), dtype=np.uint8)
    mask[0:4, 0:4] = 1
    mask[0:2, 2:4] = 2
    mask[4:8, 8:12] = 1
    mask[4:7, 8:12] = 2
    row = choose_native_window(
        mask,
        tile_size=4,
        minimum_crop_pixels=1,
        minimum_weed_pixels=1,
    )
    assert row == {"x": 8, "y": 4, "crop_pixels": 4, "weed_pixels": 12}


def test_choose_native_window_rejects_single_class_tile() -> None:
    mask = np.ones((8, 8), dtype=np.uint8)
    assert (
        choose_native_window(
            mask,
            tile_size=4,
            minimum_crop_pixels=1,
            minimum_weed_pixels=1,
        )
        is None
    )


def test_stratified_sample_is_stable_and_quota_exact() -> None:
    groups = {
        "a": [{"sample_id": f"a-{index}", "path": Path(str(index))} for index in range(5)],
        "b": [{"sample_id": f"b-{index}", "path": Path(str(index))} for index in range(5)],
    }
    first = stratified_sample(groups, {"a": 2, "b": 3}, seed=17)
    second = stratified_sample({key: list(reversed(value)) for key, value in groups.items()}, {"a": 2, "b": 3}, seed=17)
    assert [row["sample_id"] for row in first] == [row["sample_id"] for row in second]
    assert sum(row["sample_id"].startswith("a-") for row in first) == 2
    assert sum(row["sample_id"].startswith("b-") for row in first) == 3
