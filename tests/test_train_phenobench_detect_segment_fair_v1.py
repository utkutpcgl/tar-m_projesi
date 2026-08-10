from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from scripts.train_phenobench_detect_segment_fair_v1 import locked_inputs


def test_locked_inputs_require_matched_dataset_quality(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "quality": {
                    "detect_segment_image_membership_equal": True,
                    "detect_segment_eligible_instance_membership_equal": True,
                    "full_pixels_without_instance_id": 0,
                    "instances_without_valid_polygon": 0,
                }
            }
        ),
        encoding="utf-8",
    )
    dataset = tmp_path / "dataset.yaml"
    dataset.write_text("names: {0: weed, 1: crop}\n", encoding="utf-8")
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"checkpoint")

    from scripts.train_phenobench_detect_segment_fair_v1 import sha256

    config = {
        "data_root": str(tmp_path),
        "dataset_receipt": receipt.name,
        "dataset_receipt_sha256": sha256(receipt),
        "arms": {
            "detect": {
                "dataset_yaml": dataset.name,
                "dataset_yaml_sha256": sha256(dataset),
                "pretrained_checkpoint": checkpoint.name,
                "pretrained_checkpoint_sha256": sha256(checkpoint),
            }
        },
    }
    _, resolved_dataset, resolved_checkpoint, _ = locked_inputs(
        config, tmp_path, "detect"
    )
    assert resolved_dataset == dataset
    assert resolved_checkpoint == checkpoint

    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["quality"]["detect_segment_eligible_instance_membership_equal"] = False
    receipt.write_text(json.dumps(payload), encoding="utf-8")
    config["dataset_receipt_sha256"] = sha256(receipt)
    with pytest.raises(ValueError, match="quality contract"):
        locked_inputs(config, tmp_path, "detect")


def test_frozen_training_contract_is_symmetric() -> None:
    path = Path("configs/benchmark/phenobench_detect_segment_training_fair_v1.yaml")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert set(config["arms"]) == {"detect", "segment"}
    assert config["training"]["epochs"] == 50
    assert config["training"]["image_size"] == 1024
    assert config["training"]["patience"] == 0
    assert config["selection"]["checkpoint"] == "last.pt"
    assert config["selection"]["test_role"] == "one-time locked comparison only"
