from pathlib import Path

import numpy as np
from PIL import Image

from scripts.analyze_cropcraft_riceseg_distribution import aggregate, frame_stats


def test_frame_stats_reads_cropcraft_palette(tmp_path: Path) -> None:
    image = tmp_path / "rgb.jpg"
    mask = tmp_path / "mask.png"
    Image.fromarray(np.full((8, 8, 3), [64, 128, 32], dtype=np.uint8)).save(image)
    labels = np.zeros((8, 8, 3), dtype=np.uint8)
    labels[:4] = [0, 255, 0]
    labels[4:6] = [255, 0, 0]
    Image.fromarray(labels).save(mask)

    row = frame_stats(image, mask)

    assert row["crop_fraction"] == 0.5
    assert row["weed_fraction"] == 0.25
    assert row["green_dominance"] > 0.0


def test_aggregate_uses_median_for_distribution_gate() -> None:
    result = aggregate([{"value": 1.0}, {"value": 2.0}, {"value": 100.0}])

    assert result["samples"] == 3
    assert result["metrics"]["value"]["q50"] == 2.0
