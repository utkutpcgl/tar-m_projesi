#!/usr/bin/env python3
"""Lock a fixed-epoch semantic checkpoint without reading final-test data.

This selector is intentionally separate from the spray-policy selector.  It
uses source validation and a declared development set only, requires every
seed's calibrated fixed-epoch checkpoint to pass the configured risk gates,
and chooses the median seed by the minimum of source/development mIoU.  The
median rule avoids selecting the luckiest seed before a one-time final test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def fixed_epoch_validation(history_path: Path, epoch: int) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for line in history_path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if int(record.get("epoch", -1)) == epoch:
            matches.append(record)
    if len(matches) != 1 or not isinstance(matches[0].get("val"), dict):
        raise ValueError(
            f"Expected exactly one validated epoch {epoch}: {history_path}"
        )
    return matches[0]["val"]


def run_record(
    candidate_dir: Path,
    candidate_name: str,
    seed: int,
    epoch: int,
) -> dict[str, Any]:
    run_dir = (candidate_dir / f"seed_{seed}").resolve()
    summary_path = run_dir / "summary.json"
    config_path = run_dir / "config.resolved.json"
    history_path = run_dir / "history.jsonl"
    source_checkpoint = run_dir / "last.pt"
    receipt_path = (
        run_dir
        / "development"
        / "cwfid_unknown_calibration_semantic_epoch15.json"
    )
    development_path = run_dir / "development" / "cwfid_semantic_epoch15.json"

    summary = load_object(summary_path)
    config = load_object(config_path)
    receipt = load_object(receipt_path)
    development = load_object(development_path)
    source = fixed_epoch_validation(history_path, epoch)

    if summary.get("status") != "complete" or int(summary.get("epochs", -1)) != epoch:
        raise ValueError(f"Run is not complete at epoch {epoch}: {run_dir}")
    if config.get("experiment") != candidate_name or int(config.get("seed", -1)) != seed:
        raise ValueError(f"Candidate/seed mismatch: {config_path}")
    if receipt.get("external_test_used") is not False:
        raise ValueError(f"Calibration receipt used external test: {receipt_path}")
    if receipt.get("role") != "declared_unknown_crop_development_calibration":
        raise ValueError(f"Unexpected calibration role: {receipt_path}")
    if receipt.get("deployment_eligible") is not True:
        raise ValueError(f"Fixed-epoch checkpoint failed risk gates: {receipt_path}")
    if development.get("calibration_source", {}).get(
        "external_threshold_sweep_performed"
    ) is not False:
        raise ValueError(f"Development evaluation swept thresholds: {development_path}")

    expected_source = source_checkpoint.resolve()
    receipt_source = Path(receipt["source_checkpoint"]).resolve()
    if receipt_source != expected_source:
        raise ValueError(f"Receipt source is not fixed epoch last.pt: {receipt_path}")
    if sha256(expected_source) != receipt["source_checkpoint_sha256"]:
        raise ValueError(f"Source checkpoint hash mismatch: {expected_source}")
    calibrated = Path(receipt["calibrated_checkpoint"]).resolve()
    calibrated_hash = sha256(calibrated)
    if calibrated_hash != receipt["calibrated_checkpoint_sha256"]:
        raise ValueError(f"Calibrated checkpoint hash mismatch: {calibrated}")
    evaluated = Path(development["calibration_source"]["checkpoint"]).resolve()
    if evaluated != calibrated:
        raise ValueError(f"Development checkpoint mismatch: {development_path}")

    source_iou = source["iou"]
    development_iou = development["iou"]
    source_safety = receipt["source_at_frozen_threshold"]
    development_safety = receipt["development_at_frozen_threshold"]
    robust_miou = min(float(source["mean_iou"]), float(development["mean_iou"]))
    return {
        "candidate": candidate_name,
        "seed": seed,
        "fixed_epoch": epoch,
        "run_dir": str(run_dir),
        "calibrated_checkpoint": str(calibrated),
        "calibrated_checkpoint_sha256": calibrated_hash,
        "source_checkpoint": str(expected_source),
        "source_checkpoint_sha256": receipt["source_checkpoint_sha256"],
        "summary": str(summary_path),
        "summary_sha256": sha256(summary_path),
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "history": str(history_path),
        "history_sha256": sha256(history_path),
        "calibration_receipt": str(receipt_path),
        "calibration_receipt_sha256": sha256(receipt_path),
        "development_metrics": str(development_path),
        "development_metrics_sha256": sha256(development_path),
        "manifest_sha256": summary["manifest_sha256"],
        "normalized_mask_tree_sha256": summary["normalized_mask_tree_sha256"],
        "source_tree_sha256": summary["source_tree_sha256"],
        "source_mean_iou": float(source["mean_iou"]),
        "source_crop_iou": float(source_iou["target_crop"]),
        "source_weed_iou": float(source_iou["other_vegetation"]),
        "source_worst_domain_weed_iou": float(source["worst_domain_weed_iou"]),
        "development_mean_iou": float(development["mean_iou"]),
        "development_crop_iou": float(development_iou["target_crop"]),
        "development_weed_iou": float(development_iou["other_vegetation"]),
        "development_worst_domain_weed_iou": float(
            development["worst_domain_weed_iou"]
        ),
        "robust_semantic_mean_iou": robust_miou,
        "source_worst_domain_safe_weed_recall": float(
            source_safety["worst_domain_safe_weed_recall"]
        ),
        "development_safe_weed_recall": float(
            development_safety["macro_domain_safe_weed_recall"]
        ),
        "development_crop_spray_risk": float(
            development_safety["worst_domain_crop_spray_risk"]
        ),
        "development_crop_spray_risk_p99": float(
            development_safety["per_image_crop_spray_risk"].get("p99", 0.0)
        ),
        "development_crop_spray_risk_violation_rate": float(
            development_safety["per_image_crop_spray_risk"].get(
                "violation_rate", 0.0
            )
        ),
        "technical_risk_gates_met": True,
    }


def mean_std(runs: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [float(run[key]) for run in runs]
    return {
        "mean": statistics.fmean(values),
        "std": statistics.stdev(values) if len(values) > 1 else 0.0,
        "min": min(values),
        "max": max(values),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate_dir")
    parser.add_argument("--candidate-name", required=True)
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--fixed-epoch", type=int, required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    seeds = sorted(set(args.seeds))
    if len(seeds) != len(args.seeds):
        raise ValueError("Seeds must be unique")
    runs = [
        run_record(
            Path(args.candidate_dir).expanduser().resolve(),
            args.candidate_name,
            seed,
            args.fixed_epoch,
        )
        for seed in seeds
    ]
    for provenance_key in (
        "manifest_sha256",
        "normalized_mask_tree_sha256",
        "source_tree_sha256",
    ):
        if len({run[provenance_key] for run in runs}) != 1:
            raise ValueError(f"Mixed provenance across seeds: {provenance_key}")

    ordered = sorted(
        runs,
        key=lambda run: (run["robust_semantic_mean_iou"], run["seed"]),
    )
    representative = ordered[len(ordered) // 2]
    zero_source_worst_recall = any(
        run["source_worst_domain_safe_weed_recall"] <= 0.0 for run in runs
    )
    metric_keys = (
        "source_mean_iou",
        "source_crop_iou",
        "source_weed_iou",
        "source_worst_domain_weed_iou",
        "development_mean_iou",
        "development_crop_iou",
        "development_weed_iou",
        "robust_semantic_mean_iou",
        "development_safe_weed_recall",
    )
    output = {
        "schema_version": 1,
        "selection_scope": "semantic segmentation benchmark checkpoint",
        "selection_inputs": "source validation plus declared CWFID development only",
        "locked_external_test_used": False,
        "candidate": args.candidate_name,
        "seeds": seeds,
        "fixed_epoch": args.fixed_epoch,
        "fixed_epoch_rule": (
            "epoch 15 frozen after the seed-17 source-semantic probe and before "
            "running seeds 29 and 43"
        ),
        "candidate_rule": (
            "all seeds pass calibrated aggregate and tail risk gates; compare "
            "fixed-epoch source/development semantic metrics"
        ),
        "checkpoint_rule": (
            "median seed by min(source mIoU, development mIoU); no final-test "
            "metric is read"
        ),
        "semantic_selection_status": "locked_for_one_time_final_evaluation",
        "technical_risk_gate_pass_rate": 1.0,
        "spray_deployment_status": (
            "not_operationally_eligible_zero_source_worst_domain_safe_weed_recall"
            if zero_source_worst_recall
            else "requires_independent_field_validation"
        ),
        "selected_seed": representative["seed"],
        "selected_checkpoint": representative["calibrated_checkpoint"],
        "selected_checkpoint_sha256": representative[
            "calibrated_checkpoint_sha256"
        ],
        "metric_summary": {key: mean_std(runs, key) for key in metric_keys},
        "run_ranking": sorted(
            runs,
            key=lambda run: (run["robust_semantic_mean_iou"], run["seed"]),
            reverse=True,
        ),
        "selection_script": str(Path(__file__).resolve()),
        "selection_script_sha256": sha256(__file__),
    }

    destination = Path(args.output).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
