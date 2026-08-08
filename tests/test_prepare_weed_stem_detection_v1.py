from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZipFile

import yaml
from PIL import Image

from scripts.prepare_weed_stem_detection_v1 import prepare


def _config(tmp_path: Path, archive: Path) -> Path:
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    payload = {
        "schema_version": 1,
        "dataset_id": "test_wsd",
        "data_root": str(tmp_path),
        "source": {
            "dataset_page": "https://example.test/wsd",
            "dataset_revision": "abc",
            "dataset_license": "Apache-2.0",
            "archive": archive.name,
            "archive_bytes": archive.stat().st_size,
            "archive_sha256": digest,
            "paper": "https://example.test/paper",
            "reference_code": "https://example.test/code",
            "reference_code_revision": "def",
        },
        "archive_layout": {
            "image_prefix": "labelled/images",
            "box_label_prefix": "labelled/labels",
            "point_label_prefix": "labelled/points_labels",
            "class_names": {0: "weed", 1: "maize", 2: "soybean"},
            "image_suffixes": [".bmp"],
        },
        "split_policy": {
            "train_dates": ["20231130"],
            "val_dates": ["20231204"],
            "test_dates": ["20231206"],
        },
        "normalization_policy": {
            "accepted_box_field_counts": [5, 7],
            "stem_keypoint_class": 0,
            "missing_point": [0.0, 0.0],
            "visible_keypoint_value": 2,
            "missing_keypoint_value": 0,
        },
        "outputs": {
            "root": "prepared",
            "receipt": "audit/receipt.json",
            "manifest": "manifest.csv",
            "contact_sheet": "audit/contact.jpg",
            "ultralytics_yaml": "prepared/data.yaml",
        },
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _archive(tmp_path: Path) -> Path:
    archive = tmp_path / "wsd.zip"
    with ZipFile(archive, "w") as handle:
        for date in ("20231130", "20231204", "20231206"):
            stem = f"Image_{date}120000000"
            image = tmp_path / f"{stem}.bmp"
            Image.new("RGB", (32, 32), "green").save(image)
            handle.write(image, f"labelled/images/{stem}.bmp")
            handle.writestr(
                f"labelled/labels/{stem}.txt",
                "0 0.5 0.5 0.25 0.25\n1 0.2 0.2 0.1 0.1\n",
            )
            handle.writestr(
                f"labelled/points_labels/{stem}.txt", "0.52 0.48\n0 0\n"
            )
    return archive


def test_prepare_builds_date_disjoint_pose_dataset(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    receipt = prepare(_config(tmp_path, archive))

    assert receipt["archive_inventory"]["paired_samples"] == 3
    assert receipt["annotations"]["visible_weed_points"] == 3
    assert receipt["quality_gates"]["research_pilot_approved"] is True
    assert receipt["split_statistics"]["train"]["images"] == 1
    label = next((tmp_path / "prepared/labels/train").glob("*.txt"))
    rows = label.read_text(encoding="utf-8").splitlines()
    assert rows[0].endswith(" 2")
    assert rows[1].endswith("0 0 0")
    data = yaml.safe_load((tmp_path / "prepared/data.yaml").read_text())
    assert data["kpt_shape"] == [1, 3]
    assert data["test"] == "images/test"


def test_audit_only_does_not_extract(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    receipt = prepare(_config(tmp_path, archive), audit_only=True)

    assert receipt["status"] == "audit_only"
    assert not (tmp_path / "prepared").exists()
