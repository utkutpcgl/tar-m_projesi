#!/usr/bin/env python3
"""Select one deployment checkpoint from calibrated multi-seed runs.

The script consumes only source-validation metrics and a declared-development
calibration receipt. Locked external-test metrics are neither accepted nor
read. Candidate ranking uses every seed; the representative checkpoint is the
median robust-recall seed of the winning candidate to avoid test-set or
best-seed cherry-picking.
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


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def risk(point: dict[str, Any]) -> float:
    return float(point["worst_domain_crop_spray_risk"])


def recall(point: dict[str, Any]) -> float:
    return float(point["worst_domain_safe_weed_recall"])


def macro_recall(point: dict[str, Any]) -> float:
    return float(point["macro_domain_safe_weed_recall"])


def p99(point: dict[str, Any]) -> float:
    return float(point["per_image_crop_spray_risk"].get("p99", 0.0))


def violation_rate(point: dict[str, Any]) -> float:
    return float(
        point["per_image_crop_spray_risk"].get("violation_rate", 0.0)
    )


def run_record(run: dict[str, Any], development_name: str) -> dict[str, Any]:
    run_dir = Path(run["run_dir"]).resolve()
    metrics_path = run_dir / "metrics.json"
    development_path = run_dir / "development" / f"{development_name}.json"
    receipt_path = (
        run_dir / "development" / f"{development_name}_unknown_calibration.json"
    )
    resolved_config_path = run_dir / "config.resolved.json"
    metrics = load_json(metrics_path)
    development_metrics = load_json(development_path)
    receipt = load_json(receipt_path)
    resolved_config = load_json(resolved_config_path)
    if receipt.get("external_test_used") is not False:
        raise ValueError(f"Receipt is not development-only: {receipt_path}")
    if receipt.get("role") != "declared_unknown_crop_development_calibration":
        raise ValueError(f"Unexpected calibration role: {receipt_path}")
    if str(resolved_config.get("experiment")) != str(run["candidate"]):
        raise ValueError(f"Candidate/config mismatch in {run_dir}")
    if int(resolved_config.get("seed", -1)) != int(run["seed"]):
        raise ValueError(f"Seed/config mismatch in {run_dir}")

    expected_source = (run_dir / "best.pt").resolve()
    source_path = Path(receipt["source_checkpoint"]).resolve()
    if source_path != expected_source:
        raise ValueError(
            f"Calibration source is not this run's best.pt: {receipt_path}"
        )
    if sha256(source_path) != receipt["source_checkpoint_sha256"]:
        raise ValueError(f"Source checkpoint hash mismatch: {source_path}")
    checkpoint_path = Path(receipt["calibrated_checkpoint"]).resolve()
    checkpoint_hash = sha256(checkpoint_path)
    if checkpoint_hash != receipt["calibrated_checkpoint_sha256"]:
        raise ValueError(f"Calibrated checkpoint hash mismatch: {checkpoint_path}")

    known = metrics["known_crop_id_calibration"]["selected_operating_point"]
    source_unknown = receipt["source_at_frozen_threshold"]
    development = receipt["development_at_frozen_threshold"]
    max_risk = float(receipt["max_crop_spray_risk"])
    max_p99_risk = float(
        receipt.get("max_per_image_crop_spray_risk_p99", 1.0)
    )
    max_violation_rate = float(
        receipt.get("max_crop_spray_risk_violation_rate", 1.0)
    )
    points = [known, source_unknown, development]
    risks = [risk(point) for point in points]
    p99_risks = [p99(point) for point in points]
    violation_rates = [violation_rate(point) for point in points]
    recalls = [recall(point) for point in points]
    macro_recalls = [macro_recall(point) for point in points]
    tolerance = 1e-12
    aggregate_met = all(value <= max_risk + tolerance for value in risks)
    tail_met = all(
        p99_value <= max_p99_risk + tolerance
        and violation_value <= max_violation_rate + tolerance
        for p99_value, violation_value in zip(p99_risks, violation_rates)
    )
    worst_risk = max(risks)
    worst_p99_risk = max(p99_risks)
    worst_violation_rate = max(violation_rates)
    return {
        "candidate": str(run["candidate"]),
        "seed": int(run["seed"]),
        "run_dir": str(run_dir),
        "data_license_scope": run.get("data_license_scope", "unspecified"),
        "weight_license_status": run.get(
            "weight_license_status", "unspecified"
        ),
        "calibrated_checkpoint": str(checkpoint_path),
        "calibrated_checkpoint_sha256": checkpoint_hash,
        "source_metrics": str(metrics_path),
        "source_metrics_sha256": sha256(metrics_path),
        "development_metrics": str(development_path),
        "development_metrics_sha256": sha256(development_path),
        "calibration_receipt": str(receipt_path),
        "calibration_receipt_sha256": sha256(receipt_path),
        "frozen_unknown_threshold": float(receipt["frozen_unknown_threshold"]),
        "max_crop_spray_risk": max_risk,
        "max_per_image_crop_spray_risk_p99": max_p99_risk,
        "max_crop_spray_risk_violation_rate": max_violation_rate,
        "known_source_crop_spray_risk": risks[0],
        "source_unknown_crop_spray_risk": risks[1],
        "development_crop_spray_risk": risks[2],
        "worst_crop_spray_risk": worst_risk,
        "per_image_crop_spray_risk_p99_worst": worst_p99_risk,
        "per_image_crop_spray_risk_violation_rate_worst": (
            worst_violation_rate
        ),
        "aggregate_safety_constraints_met": aggregate_met,
        "tail_safety_constraints_met": tail_met,
        "aggregate_safety_excess": max(0.0, worst_risk - max_risk),
        "tail_p99_safety_excess": max(
            0.0, worst_p99_risk - max_p99_risk
        ),
        "tail_violation_safety_excess": max(
            0.0, worst_violation_rate - max_violation_rate
        ),
        "known_source_safe_weed_recall": recalls[0],
        "source_unknown_safe_weed_recall": recalls[1],
        "development_safe_weed_recall": recalls[2],
        "robust_safe_weed_recall": min(recalls),
        "robust_macro_safe_weed_recall": min(macro_recalls),
        "robust_worst_domain_weed_iou": min(
            float(metrics["worst_domain_weed_iou"]),
            float(development_metrics["worst_domain_weed_iou"]),
        ),
        "robust_crop_iou": min(
            float(metrics["iou"]["target_crop"]),
            float(development_metrics["iou"]["target_crop"]),
        ),
        "all_safety_constraints_met": aggregate_met and tail_met,
    }

def run_key(run: dict[str, Any]) -> tuple[float, ...]:
    if run["all_safety_constraints_met"]:
        return (
            1.0,
            run["robust_safe_weed_recall"],
            run["robust_macro_safe_weed_recall"],
            run["robust_worst_domain_weed_iou"],
            -run["per_image_crop_spray_risk_violation_rate_worst"],
            -run["per_image_crop_spray_risk_p99_worst"],
            -run["worst_crop_spray_risk"],
        )
    return (
        0.0,
        -run["aggregate_safety_excess"],
        -run["tail_violation_safety_excess"],
        -run["tail_p99_safety_excess"],
        run["robust_safe_weed_recall"],
        run["robust_macro_safe_weed_recall"],
        run["robust_worst_domain_weed_iou"],
    )


def candidate_key(candidate: dict[str, Any]) -> tuple[float, ...]:
    if candidate["all_safety_constraints_met"]:
        return (
            1.0,
            candidate["robust_safe_weed_recall_worst_seed"],
            candidate["robust_safe_weed_recall_mean"],
            candidate["robust_worst_domain_weed_iou_worst_seed"],
            -candidate[
                "worst_per_image_crop_spray_risk_violation_rate_across_seeds"
            ],
            -candidate[
                "worst_per_image_crop_spray_risk_p99_across_seeds"
            ],
            -candidate["worst_crop_spray_risk_across_seeds"],
        )
    return (
        0.0,
        candidate["safety_pass_rate"],
        -candidate["aggregate_safety_excess_across_seeds"],
        -candidate["tail_violation_safety_excess_across_seeds"],
        -candidate["tail_p99_safety_excess_across_seeds"],
        candidate["robust_safe_weed_recall_worst_seed"],
        candidate["robust_safe_weed_recall_mean"],
    )


def median_representative(
    candidate_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered = sorted(
        candidate_runs,
        key=lambda item: (item["robust_safe_weed_recall"], item["seed"]),
    )
    return ordered[len(ordered) // 2]

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("benchmark_results")
    parser.add_argument("--development-name", default="cwfid")
    parser.add_argument("--expected-seeds", nargs="*", type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    benchmark_path = Path(args.benchmark_results).resolve()
    benchmark = load_json(benchmark_path)
    runs = [run_record(run, args.development_name) for run in benchmark["runs"]]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        grouped.setdefault(run["candidate"], []).append(run)
    if args.expected_seeds:
        expected_seeds = set(args.expected_seeds)
        for name, candidate_runs in grouped.items():
            actual_seeds = {run["seed"] for run in candidate_runs}
            if actual_seeds != expected_seeds:
                raise ValueError(
                    f"Candidate {name} seeds {sorted(actual_seeds)} do not "
                    f"match expected {sorted(expected_seeds)}"
                )

    candidates: list[dict[str, Any]] = []
    for name, candidate_runs in grouped.items():
        recalls = [run["robust_safe_weed_recall"] for run in candidate_runs]
        weed_ious = [run["robust_worst_domain_weed_iou"] for run in candidate_runs]
        safe_count = sum(
            bool(run["all_safety_constraints_met"]) for run in candidate_runs
        )
        candidates.append(
            {
                "candidate": name,
                "seeds": sorted(run["seed"] for run in candidate_runs),
                "all_safety_constraints_met": safe_count == len(candidate_runs),
                "safety_pass_rate": safe_count / len(candidate_runs),
                "worst_crop_spray_risk_across_seeds": max(
                    run["worst_crop_spray_risk"] for run in candidate_runs
                ),
                "worst_per_image_crop_spray_risk_p99_across_seeds": max(
                    run["per_image_crop_spray_risk_p99_worst"]
                    for run in candidate_runs
                ),
                "worst_per_image_crop_spray_risk_violation_rate_across_seeds": max(
                    run["per_image_crop_spray_risk_violation_rate_worst"]
                    for run in candidate_runs
                ),
                "aggregate_safety_excess_across_seeds": max(
                    run["aggregate_safety_excess"] for run in candidate_runs
                ),
                "tail_p99_safety_excess_across_seeds": max(
                    run["tail_p99_safety_excess"] for run in candidate_runs
                ),
                "tail_violation_safety_excess_across_seeds": max(
                    run["tail_violation_safety_excess"]
                    for run in candidate_runs
                ),
                "weight_license_statuses": sorted(
                    {str(run["weight_license_status"]) for run in candidate_runs}
                ),
                "data_license_scopes": sorted(
                    {str(run["data_license_scope"]) for run in candidate_runs}
                ),
                "robust_safe_weed_recall_mean": statistics.fmean(recalls),
                "robust_safe_weed_recall_std": (
                    statistics.stdev(recalls) if len(recalls) > 1 else 0.0
                ),
                "robust_safe_weed_recall_worst_seed": min(recalls),
                "robust_worst_domain_weed_iou_mean": statistics.fmean(weed_ious),
                "robust_worst_domain_weed_iou_worst_seed": min(weed_ious),
            }
        )
    candidates.sort(key=candidate_key, reverse=True)
    for index, candidate in enumerate(candidates, start=1):
        candidate["rank"] = index

    diagnostic_name = candidates[0]["candidate"]
    diagnostic_runs = [
        run for run in runs if run["candidate"] == diagnostic_name
    ]
    diagnostic_representative = median_representative(diagnostic_runs)

    deployment_candidates = [
        candidate
        for candidate in candidates
        if candidate["all_safety_constraints_met"]
    ]
    deployment_representative: dict[str, Any] | None = None
    deployment_name: str | None = None
    if deployment_candidates:
        deployment_name = str(deployment_candidates[0]["candidate"])
        deployment_runs = [
            run
            for run in runs
            if run["candidate"] == deployment_name
            and run["all_safety_constraints_met"]
        ]
        deployment_representative = median_representative(deployment_runs)

    output = {
        "schema_version": 1,
        "selection_inputs": "source validation plus declared development only",
        "locked_external_test_used": False,
        "candidate_rule": (
            "all seeds meet aggregate crop-risk, per-image p99, and per-image "
            "violation-rate bounds; then maximize worst-seed robust recall, "
            "mean robust recall, and worst-seed worst-domain weed IoU"
        ),
        "checkpoint_rule": (
            "median robust-recall seed of the selected candidate; no final-test "
            "metric is read"
        ),
        "deployment_selection_status": (
            "eligible" if deployment_representative is not None
            else "no_candidate_met_all_predeclared_safety_constraints"
        ),
        "benchmark_results": str(benchmark_path),
        "benchmark_results_sha256": sha256(benchmark_path),
        "selection_script_sha256": sha256(__file__),
        "development_name": args.development_name,
        "candidate_ranking": candidates,
        "run_ranking": sorted(runs, key=run_key, reverse=True),
        "selected_candidate": deployment_name,
        "selected_seed": (
            deployment_representative["seed"]
            if deployment_representative is not None
            else None
        ),
        "selected_checkpoint": (
            deployment_representative["calibrated_checkpoint"]
            if deployment_representative is not None
            else None
        ),
        "selected_checkpoint_sha256": (
            deployment_representative["calibrated_checkpoint_sha256"]
            if deployment_representative is not None
            else None
        ),
        "diagnostic_best_candidate": diagnostic_name,
        "diagnostic_representative_seed": diagnostic_representative["seed"],
        "diagnostic_representative_checkpoint": diagnostic_representative[
            "calibrated_checkpoint"
        ],
        "diagnostic_representative_checkpoint_sha256": (
            diagnostic_representative["calibrated_checkpoint_sha256"]
        ),
    }
    destination = Path(args.output).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(destination)
    destination.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
