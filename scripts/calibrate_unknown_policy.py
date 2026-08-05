#!/usr/bin/env python3
"""Calibrate the unseen-crop safety threshold on declared development data.

Known-crop thresholds remain source-validation-only. This utility may consume
only an ``external_calibration`` split whose crop IDs were absent from model
training. It writes a new checkpoint plus an auditable receipt; final-test data
is explicitly rejected.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from dataclasses import asdict, replace
from pathlib import Path
from typing import Mapping, Sequence

import torch
from torch.utils.data import DataLoader

from agri_seg.data import EvalTransform, ManifestDataset, padded_collate
from agri_seg.engine import _validation_selection_key, evaluate, load_checkpoint
from agri_seg.manifest import (
    manifest_sha256,
    mask_tree_sha256,
    read_manifest,
)
from agri_seg.safety import SafetyPolicy


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def point_at(
    curve: Sequence[Mapping[str, object]], threshold: float
) -> dict[str, object]:
    for point in curve:
        if math.isclose(
            float(point["weed_threshold"]), threshold, abs_tol=1e-12
        ):
            return dict(point)
    raise ValueError(f"Threshold {threshold} is absent from a calibration curve")


def json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkpoint")
    parser.add_argument("calibration_manifest")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--output-checkpoint", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    source_path = Path(args.checkpoint).expanduser().resolve()
    output_path = Path(args.output_checkpoint).expanduser().resolve()
    receipt_path = Path(args.receipt).expanduser().resolve()
    if source_path == output_path:
        raise ValueError("Calibrated checkpoint must not overwrite its source")
    if output_path.exists() or receipt_path.exists():
        raise FileExistsError("Calibration output already exists")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for native-resolution calibration")

    records = [
        record
        for record in read_manifest(args.calibration_manifest)
        if record.split == "external_calibration"
    ]
    if not records:
        raise ValueError("Calibration manifest has no external_calibration records")
    all_records = read_manifest(args.calibration_manifest)
    if len(records) != len(all_records):
        raise ValueError(
            "Calibration manifest must contain only external_calibration data"
        )

    device = torch.device("cuda")
    model, checkpoint = load_checkpoint(source_path, device)
    config = checkpoint["config"]
    known_crop_ids = {
        int(value) for value in config["model"].get("known_crop_ids", [])
    }
    calibration_crop_ids = {record.target_crop_id for record in records}
    overlap = sorted(known_crop_ids & calibration_crop_ids)
    if overlap:
        raise ValueError(
            "Development calibration must use crop IDs unseen in training; "
            f"overlap={overlap}"
        )

    dataset = ManifestDataset(
        records, args.data_root, EvalTransform(), verify_files=True
    )
    loader = DataLoader(
        dataset,
        batch_size=1,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=True,
        collate_fn=padded_collate,
    )
    training = config["training"]
    thresholds = [float(value) for value in training["weed_thresholds"]]
    configured_policy = SafetyPolicy(**dict(config.get("safety", {})))
    sweep_policy = replace(
        configured_policy,
        weed_threshold_by_crop_id={},
        unknown_crop_weed_threshold=None,
    )
    max_risk = float(training.get("max_crop_spray_risk", 0.005))
    max_p99_risk = float(
        training.get("max_per_image_crop_spray_risk_p99", 1.0)
    )
    max_violation_rate = float(
        training.get("max_crop_spray_risk_violation_rate", 1.0)
    )
    calibration_metrics = evaluate(
        model,
        loader,
        device,
        sweep_policy,
        thresholds,
        max_risk,
        use_amp=bool(training.get("amp", True)),
        tile_size=training.get("eval_tile_size"),
        tile_overlap=int(training.get("eval_tile_overlap", 128)),
        tile_trigger_pixels=int(
            training.get("eval_tile_trigger_pixels", 4_000_000)
        ),
        max_per_image_crop_spray_risk_p99=max_p99_risk,
        max_crop_spray_risk_violation_rate=max_violation_rate,
    )
    validation = checkpoint.get("validation")
    if not isinstance(validation, Mapping):
        raise ValueError("Checkpoint has no source validation")
    source_unknown = validation.get("unknown_crop_calibration")
    if not isinstance(source_unknown, Mapping):
        raise ValueError("Checkpoint has no source unknown-crop calibration")
    source_selected = source_unknown["selected_operating_point"]
    development_selected = calibration_metrics["selected_operating_point"]
    source_threshold = float(source_selected["weed_threshold"])
    development_threshold = float(development_selected["weed_threshold"])
    chosen_threshold = max(source_threshold, development_threshold)
    source_point = point_at(
        source_unknown["threshold_curve"], chosen_threshold
    )
    development_point = point_at(
        calibration_metrics["threshold_curve"], chosen_threshold
    )
    def point_meets_safety(point: Mapping[str, object]) -> bool:
        image_risk = point["per_image_crop_spray_risk"]
        tolerance = 1e-12
        return (
            float(point["worst_domain_crop_spray_risk"])
            <= max_risk + tolerance
            and float(image_risk.get("p99", 0.0))
            <= max_p99_risk + tolerance
            and float(image_risk.get("violation_rate", 0.0))
            <= max_violation_rate + tolerance
        )

    source_meets_safety = point_meets_safety(source_point)
    development_meets_safety = point_meets_safety(development_point)
    deployment_eligible = source_meets_safety and development_meets_safety

    calibrated = copy.deepcopy(checkpoint)
    calibrated_validation = calibrated["validation"]
    selected = calibrated_validation["selected_operating_point"]
    known = calibrated_validation.get("known_crop_id_calibration")
    if not isinstance(known, Mapping):
        raise ValueError("Checkpoint has no known-crop calibration details")
    known_selected = known["selected_operating_point"]
    selected["weed_threshold"] = chosen_threshold
    selected["unknown_crop_weed_threshold"] = chosen_threshold
    selected["calibration_mode"] = (
        "source_per_crop_id_plus_source_and_declared_development_unknown_crop"
    )
    selected["unknown_crop_policy"] = source_point
    selected["worst_domain_crop_spray_risk"] = max(
        float(known_selected["worst_domain_crop_spray_risk"]),
        float(source_point["worst_domain_crop_spray_risk"]),
    )
    selected["worst_domain_safe_weed_recall"] = min(
        float(known_selected["worst_domain_safe_weed_recall"]),
        float(source_point["worst_domain_safe_weed_recall"]),
    )
    selected["macro_domain_safe_weed_recall"] = min(
        float(known_selected["macro_domain_safe_weed_recall"]),
        float(source_point["macro_domain_safe_weed_recall"]),
    )
    known_risk_distribution = known_selected["per_image_crop_spray_risk"]
    source_risk_distribution = source_point["per_image_crop_spray_risk"]
    selected["per_image_crop_spray_risk_by_policy_mode"] = {
        "known_crop_ids": known_risk_distribution,
        "unknown_crop": source_risk_distribution,
    }
    if float(source_risk_distribution.get("p99", 0.0)) > float(
        known_risk_distribution.get("p99", 0.0)
    ):
        selected["per_image_crop_spray_risk"] = source_risk_distribution
    else:
        selected["per_image_crop_spray_risk"] = known_risk_distribution
    calibrated_validation["unknown_crop_calibration"] = {
        **dict(source_unknown),
        "selected_operating_point": source_point,
    }
    calibrated_validation["safety_constraint"]["unknown_crop_met"] = (
        source_meets_safety
    )
    calibrated_validation["safety_constraint"][
        "development_unknown_crop_met"
    ] = development_meets_safety
    calibrated_validation["safety_constraint"]["met"] = bool(
        calibrated_validation["safety_constraint"].get(
            "known_crop_ids_met", False
        )
    ) and deployment_eligible
    calibrated["validation_selection_key"] = _validation_selection_key(
        calibrated_validation
    )
    calibration_receipt = {
        "schema_version": 2,
        "role": "declared_unknown_crop_development_calibration",
        "calibration_status": (
            "eligible"
            if deployment_eligible
            else "no_common_threshold_met_all_safety_constraints"
        ),
        "deployment_eligible": deployment_eligible,
        "source_checkpoint": str(source_path),
        "source_checkpoint_sha256": sha256(source_path),
        "calibration_manifest": str(
            Path(args.calibration_manifest).expanduser().resolve()
        ),
        "calibration_manifest_sha256": manifest_sha256(
            args.calibration_manifest
        ),
        "calibration_mask_tree_sha256": mask_tree_sha256(
            records, args.data_root
        ),
        "calibration_crop_ids": sorted(calibration_crop_ids),
        "known_training_crop_ids": sorted(known_crop_ids),
        "source_unknown_threshold": source_threshold,
        "development_selected_threshold": development_threshold,
        "frozen_unknown_threshold": chosen_threshold,
        "max_crop_spray_risk": max_risk,
        "max_per_image_crop_spray_risk_p99": max_p99_risk,
        "max_crop_spray_risk_violation_rate": max_violation_rate,
        "source_at_frozen_threshold": source_point,
        "source_at_frozen_threshold_met": source_meets_safety,
        "development_at_frozen_threshold": development_point,
        "development_at_frozen_threshold_met": development_meets_safety,
        "development_raw_safety_constraint_met": bool(
            calibration_metrics["safety_constraint"]["met"]
        ),
        "external_test_used": False,
        "policy": {
            **asdict(configured_policy),
            "weed_threshold_by_crop_id": selected[
                "weed_threshold_by_crop_id"
            ],
            "unknown_crop_weed_threshold": chosen_threshold,
        },
    }
    calibrated["development_calibration"] = calibration_receipt

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    torch.save(calibrated, temporary)
    temporary.replace(output_path)
    calibration_receipt["calibrated_checkpoint"] = str(output_path)
    calibration_receipt["calibrated_checkpoint_sha256"] = sha256(output_path)
    calibration_receipt["script_sha256"] = sha256(__file__)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(
            json_safe(calibration_receipt),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(json_safe(calibration_receipt), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
