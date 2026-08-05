import csv
from pathlib import Path

import pytest

from scripts.evaluate_riceseg_additive_fixed_epoch_development import (
    validate_training_inputs,
)


HEADER = [
    "sample_id",
    "image_path",
    "mask_path",
    "split",
    "dataset_id",
    "field_id",
    "session_id",
    "capture_date",
    "platform",
    "sensor",
    "target_crop_id",
    "crop_species",
    "weed_species_optional",
    "growth_stage",
    "annotation_exhaustive",
    "license_status",
    "commercial_allowed",
]


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)


def row(sample_id: str, split: str, dataset_id: str, session: str) -> dict[str, str]:
    return {
        "sample_id": sample_id,
        "image_path": f"images/{sample_id}.png",
        "mask_path": f"masks/{sample_id}.png",
        "split": split,
        "dataset_id": dataset_id,
        "field_id": session,
        "session_id": session,
        "capture_date": "2024",
        "platform": "ground",
        "sensor": "rgb",
        "target_crop_id": "12",
        "crop_species": "Oryza sativa",
        "weed_species_optional": "weed",
        "growth_stage": "reproductive",
        "annotation_exhaustive": "True",
        "license_status": "research",
        "commercial_allowed": "False",
    }


def config(root: Path, manifest: Path, exposure: float) -> dict:
    old = (1.0 - exposure) / 8.0
    return {
        "data_root": str(root),
        "manifest": str(manifest),
        "model": {"known_crop_ids": [0, 2, 3, 4, 5, 6, 7, 8, 9, 12]},
        "training": {
            "samples_per_epoch": 3780,
            "dataset_weights": {
                **{f"old_{index}": old for index in range(8)},
                **({"riceseg": exposure} if exposure else {}),
            },
        },
    }


def test_riceseg_train_is_allowed_but_calibration_overlap_is_rejected(tmp_path: Path) -> None:
    train = tmp_path / "train.csv"
    calibration = tmp_path / "calibration.csv"
    write_manifest(train, [row("train", "train", "riceseg", "train_group")])
    write_manifest(
        calibration,
        [row("calibration", "external_calibration", "riceseg", "cal_group")],
    )
    result = validate_training_inputs(config(tmp_path, train, 0.05), tmp_path, calibration)
    assert result["riceseg_rows"] == 1
    assert result["riceseg_exposure"] == pytest.approx(0.05)

    write_manifest(
        calibration,
        [row("train", "external_calibration", "riceseg", "cal_group")],
    )
    with pytest.raises(ValueError, match="calibration leaked"):
        validate_training_inputs(config(tmp_path, train, 0.05), tmp_path, calibration)


def test_evaluation_only_real_dataset_is_rejected(tmp_path: Path) -> None:
    train = tmp_path / "train.csv"
    calibration = tmp_path / "calibration.csv"
    write_manifest(train, [row("bad", "train", "growingsoy", "group")])
    write_manifest(
        calibration,
        [row("calibration", "external_calibration", "riceseg", "cal_group")],
    )
    with pytest.raises(ValueError, match="development-only datasets"):
        validate_training_inputs(config(tmp_path, train, 0.0), tmp_path, calibration)
