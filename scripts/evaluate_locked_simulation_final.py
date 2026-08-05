#!/usr/bin/env python3
"""Evaluate the selected model on the locked Sorghum test exactly once."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agri_seg.engine import evaluate_checkpoint


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    selection_path = Path(args.selection).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    if output_path.exists() or receipt_path.exists():
        raise FileExistsError(
            "Locked evaluation output/receipt already exists; refusing a repeat"
        )
    selection = load_object(selection_path)
    if selection.get("selection_status") != "locked_for_one_time_external_test":
        raise ValueError("Selection receipt has not locked the final model")
    if selection.get("external_test_used_for_selection") is not False:
        raise ValueError("Selection receipt used external-test data")
    locked = selection["locked_external_test"]
    if Path(locked["manifest"]).resolve() != manifest_path:
        raise ValueError("Manifest does not match the locked selection receipt")
    if locked.get("split") != "external_test":
        raise ValueError("Only the locked external_test split is allowed")
    checkpoint_path = Path(selection["selected_checkpoint"]).resolve()
    checkpoint_hash = sha256(checkpoint_path)
    if checkpoint_hash != selection["selected_checkpoint_sha256"]:
        raise ValueError("Selected checkpoint hash mismatch")

    metrics = evaluate_checkpoint(
        checkpoint_path,
        manifest_path,
        Path(args.data_root).expanduser().resolve(),
        "external_test",
        output_path,
        batch_size=1,
        workers=args.workers,
    )
    calibration = metrics["calibration_source"]
    if calibration.get("external_threshold_sweep_performed") is not False:
        raise RuntimeError("Final evaluation unexpectedly swept thresholds")
    if Path(calibration["checkpoint"]).resolve() != checkpoint_path:
        raise RuntimeError("Final metrics evaluated a different checkpoint")

    selected = metrics["selected_operating_point"]
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "access_policy": "one_time_after_model_recipe_and_checkpoint_lock",
        "final_test_performance_evaluation_count_in_this_workflow": 1,
        "selection_receipt": str(selection_path),
        "selection_receipt_sha256": sha256(selection_path),
        "selected_candidate": selection["selected_candidate"],
        "selected_seed": selection["selected_seed"],
        "selected_fixed_epoch": selection["selected_fixed_epoch"],
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": checkpoint_hash,
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "split": "external_test",
        "threshold_sweep_performed": False,
        "metrics_artifact": str(output_path),
        "metrics_artifact_sha256": sha256(output_path),
        "semantic": {
            "mean_iou": metrics["mean_iou"],
            "crop_iou": metrics["iou"]["target_crop"],
            "weed_iou": metrics["iou"]["other_vegetation"],
        },
        "safety": {
            "constraint_met": metrics["safety_constraint"]["met"],
            "crop_spray_risk": selected["global"]["crop_spray_risk"],
            "safe_weed_recall": selected["global"]["safe_weed_recall"],
            "crop_spray_risk_p99": selected["per_image_crop_spray_risk"][
                "p99"
            ],
            "crop_spray_risk_violation_rate": selected[
                "per_image_crop_spray_risk"
            ]["violation_rate"],
        },
        "interpretation_limit": (
            "Official image-disjoint split from one named farm; this is not "
            "unseen-field validation or spray deployment approval."
        ),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
