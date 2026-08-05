#!/usr/bin/env python3
"""Validate and index every artifact in the frozen unseen visual gallery."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "configs/benchmark/unseen_visual_gallery_v1.yaml"


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "data/processed/audits/unseen_visual_gallery_v1/gallery_index.json"),
    )
    args = parser.parse_args()
    config_path = Path(args.config).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(output)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    checkpoint = Path(str(config["checkpoint"]["path"])).resolve()
    if sha256(checkpoint) != str(config["checkpoint"]["sha256"]):
        raise RuntimeError("Gallery checkpoint changed")

    unlabeled: dict[str, Any] = {}
    for row in config["unlabeled_galleries"]:
        name = str(row["name"])
        if "existing_receipt" in row:
            receipt_path = Path(str(row["existing_receipt"])).resolve()
            contact = Path(str(row["existing_contact_sheet"])).resolve()
            receipt = load_json(receipt_path)
            if receipt.get("all_automated_quality_gates_passed") is not True:
                raise RuntimeError(f"Existing unlabeled gallery is not accepted: {name}")
            unlabeled[name] = {
                "receipt": str(receipt_path),
                "receipt_sha256": sha256(receipt_path),
                "contact_sheets": [{"path": str(contact), "sha256": sha256(contact)}],
                "frame_count": len(receipt["frames"]),
                "numeric_accuracy_reported": False,
            }
            continue
        selection = Path(str(row["selection"])).resolve()
        if sha256(selection) != str(row["selection_sha256"]):
            raise RuntimeError(f"Selection changed: {name}")
        receipt_path = Path(str(row["output"])).resolve() / "unlabeled_gallery_evaluation.json"
        receipt = load_json(receipt_path)
        if receipt.get("all_automated_quality_gates_passed") is not True:
            raise RuntimeError(f"Unlabeled gallery gates failed: {name}")
        if receipt.get("checkpoint_sha256") != config["checkpoint"]["sha256"]:
            raise RuntimeError(f"Unlabeled gallery used another checkpoint: {name}")
        if receipt.get("selection_sha256") != row["selection_sha256"]:
            raise RuntimeError(f"Unlabeled gallery used another selection: {name}")
        unlabeled[name] = {
            "receipt": str(receipt_path),
            "receipt_sha256": sha256(receipt_path),
            "contact_sheets": receipt["contact_sheets"],
            "frame_count": len(receipt["frames"]),
            "numeric_accuracy_reported": False,
        }

    labeled: dict[str, Any] = {}
    for row in config["labeled_galleries"]:
        name = str(row["name"])
        manifest = Path(str(row["manifest"])).resolve()
        if sha256(manifest) != str(row["manifest_sha256"]):
            raise RuntimeError(f"Labeled gallery manifest changed: {name}")
        root = Path(str(row["output"])).resolve()
        index_path = root / "index.json"
        contact_path = root / "contact_sheet_receipt.json"
        index = load_json(index_path)
        contacts = load_json(contact_path)
        if index["checkpoint"]["sha256"] != config["checkpoint"]["sha256"]:
            raise RuntimeError(f"Labeled gallery used another checkpoint: {name}")
        if index["manifest"]["sha256"] != row["manifest_sha256"]:
            raise RuntimeError(f"Labeled gallery used another manifest: {name}")
        if index["manifest"]["split"] != row["split"]:
            raise RuntimeError(f"Labeled gallery used another split: {name}")
        if contacts["gallery_index_sha256"] != sha256(index_path):
            raise RuntimeError(f"Labeled gallery contact sheet is stale: {name}")
        labeled[name] = {
            "gallery_index": str(index_path),
            "gallery_index_sha256": sha256(index_path),
            "contact_sheets": contacts["contact_sheets"],
            "evaluated_images": index["manifest"]["evaluated_images"],
            "displayed_images": index["selection_counts"]["total"],
            "role": row["role"],
        }

    policy = config["policy"]
    gates = {
        "checkpoint_locked": True,
        "all_unlabeled_galleries_present": len(unlabeled) == len(config["unlabeled_galleries"]),
        "all_labeled_galleries_present": len(labeled) == len(config["labeled_galleries"]),
        "unlabeled_accuracy_disabled": policy["unlabeled_numeric_accuracy_authorized"] is False,
        "synthetic_selection_weight_zero": float(policy["synthetic_selection_weight"]) == 0.0,
        "online_selection_weight_zero": float(policy["online_video_selection_weight"]) == 0.0,
        "external_or_final_test_unused": policy["external_or_final_test_used"] is False,
    }
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "checkpoint": config["checkpoint"],
        "unlabeled_galleries": unlabeled,
        "labeled_galleries": labeled,
        "quality_gates": gates,
        "all_quality_gates_passed": all(gates.values()),
        "model_selection_changed": False,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    if not receipt["all_quality_gates_passed"]:
        raise RuntimeError(f"Unseen visual gallery finalization failed: {output}")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
