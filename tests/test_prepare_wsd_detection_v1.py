from pathlib import Path

import json
import yaml

from scripts.prepare_wsd_detection_v1 import prepare, sha256


def test_prepare_derives_five_field_labels_and_links_images(tmp_path: Path) -> None:
    source = tmp_path / "pose"
    for split in ("train", "val", "test"):
        (source / "images" / split).mkdir(parents=True)
        (source / "labels" / split).mkdir(parents=True)
        (source / "images" / split / f"{split}.bmp").write_bytes(b"image")
        (source / "labels" / split / f"{split}.txt").write_text(
            "0 0.5 0.5 0.2 0.3 0.51 0.49 2\n"
            "1 0.2 0.2 0.1 0.1 0 0 0\n",
            encoding="utf-8",
        )
    source_receipt = tmp_path / "source.json"
    source_receipt.write_text(
        json.dumps(
            {
                "quality_gates": {"research_pilot_approved": True},
                "derived": {"pose_label_tree_sha256": "pose-tree"},
            }
        ),
        encoding="utf-8",
    )
    config = {
        "dataset_id": "test_detect",
        "data_root": str(tmp_path),
        "source_pose_root": "pose",
        "source_receipt": "source.json",
        "source_receipt_sha256": sha256(source_receipt),
        "outputs": {
            "root": "detect",
            "receipt": "detect_receipt.json",
            "ultralytics_yaml": "detect/data.yaml",
        },
        "derivation": {
            "class_names": {0: "weed", 1: "maize", 2: "soybean"}
        },
        "release_policy": {"limitations": ["test"]},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    receipt = prepare(config_path)

    assert (tmp_path / "detect/labels/train/train.txt").read_text() == (
        "0 0.5 0.5 0.2 0.3\n1 0.2 0.2 0.1 0.1\n"
    )
    assert (tmp_path / "detect/images/train/train.bmp").read_bytes() == b"image"
    assert receipt["derivation"]["split_statistics"]["test"]["instances"] == 2
    assert receipt["quality_gates"]["images_are_zero_copy_links"] is True
