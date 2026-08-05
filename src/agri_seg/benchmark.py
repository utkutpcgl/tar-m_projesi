"""Run an explicit model/seed matrix and build a comparable result table."""

from __future__ import annotations

import json
import statistics
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from .engine import evaluate_checkpoint, source_tree_sha256, train_from_config
from .manifest import manifest_sha256, mask_tree_sha256, read_manifest


def _compact_metrics(metrics: dict[str, object]) -> dict[str, object]:
    selected = metrics["selected_operating_point"]
    image_risk = selected["per_image_crop_spray_risk"]
    return {
        "crop_spray_risk": selected["worst_domain_crop_spray_risk"],
        "per_image_crop_spray_risk_p95": image_risk.get("p95"),
        "per_image_crop_spray_risk_p99": image_risk.get("p99"),
        "per_image_crop_spray_risk_max": image_risk.get("max"),
        "per_image_crop_spray_risk_violation_rate": image_risk.get(
            "violation_rate"
        ),
        "safe_weed_recall": selected["macro_domain_safe_weed_recall"],
        "worst_domain_safe_weed_recall": selected[
            "worst_domain_safe_weed_recall"
        ],
        "weed_iou": metrics["iou"]["other_vegetation"],
        "worst_domain_weed_iou": metrics["worst_domain_weed_iou"],
        "crop_iou": metrics["iou"]["target_crop"],
        "mean_iou": metrics["mean_iou"],
        "constraint_met": metrics["safety_constraint"]["met"],
        "weed_threshold": selected["weed_threshold"],
        "weed_threshold_by_crop_id": selected.get(
            "weed_threshold_by_crop_id", {}
        ),
        "unknown_crop_weed_threshold": selected.get(
            "unknown_crop_weed_threshold", selected["weed_threshold"]
        ),
    }


def run_benchmark(matrix_path: str | Path) -> Path:
    matrix_file = Path(matrix_path)
    with matrix_file.open("r", encoding="utf-8") as handle:
        matrix = yaml.safe_load(handle)
    base_path = (matrix_file.parent / matrix["base_config"]).resolve()
    with base_path.open("r", encoding="utf-8") as handle:
        base = yaml.safe_load(handle)
    work_dir = Path(matrix["work_dir"]).expanduser()
    generated = work_dir / "resolved_configs"
    generated.mkdir(parents=True, exist_ok=True)
    current_source_hash = source_tree_sha256()
    dataset_fingerprints: dict[tuple[str, str], tuple[str, str]] = {}

    def dataset_fingerprint(config: dict[str, Any]) -> tuple[str, str]:
        key = (str(config["manifest"]), str(config["data_root"]))
        if key not in dataset_fingerprints:
            records = read_manifest(config["manifest"])
            dataset_fingerprints[key] = (
                manifest_sha256(config["manifest"]),
                mask_tree_sha256(records, config["data_root"]),
            )
        return dataset_fingerprints[key]

    runs: list[dict[str, object]] = []
    for candidate in matrix["candidates"]:
        for seed in candidate.get("seeds", matrix.get("seeds", [17])):
            config: dict[str, Any] = deepcopy(base)
            config["seed"] = int(seed)
            config["experiment"] = str(candidate["name"])
            for key in ("manifest", "data_root", "commercial_only"):
                if key in matrix:
                    config[key] = matrix[key]
                if key in candidate:
                    config[key] = candidate[key]
            config["model"].update(matrix.get("model", {}))
            config["model"].update(candidate["model"])
            config["training"].update(matrix.get("training", {}))
            config["training"].update(candidate.get("training", {}))
            config["loss"].update(matrix.get("loss", {}))
            config["loss"].update(candidate.get("loss", {}))
            config["safety"].update(matrix.get("safety", {}))
            config["safety"].update(candidate.get("safety", {}))
            resolved_path = generated / f"{candidate['name']}_seed_{seed}.yaml"
            resolved_path.write_text(
                yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
            )
            expected_run_dir = (
                Path(config["output_root"])
                / str(config["experiment"])
                / f"seed_{seed}"
            )
            summary_path = expected_run_dir / "summary.json"
            resolved_json = expected_run_dir / "config.resolved.json"
            reuse = bool(matrix.get("reuse_completed", True))
            if reuse and summary_path.is_file() and resolved_json.is_file():
                completed = json.loads(summary_path.read_text(encoding="utf-8"))
                prior_config = json.loads(
                    resolved_json.read_text(encoding="utf-8")
                )
                manifest_hash, mask_hash = dataset_fingerprint(config)
                provenance_matches = (
                    completed.get("source_tree_sha256") == current_source_hash
                    and completed.get("manifest_sha256") == manifest_hash
                    and completed.get("normalized_mask_tree_sha256") == mask_hash
                )
                if (
                    completed.get("status") != "complete"
                    or prior_config != config
                    or not provenance_matches
                ):
                    raise RuntimeError(
                        f"Refusing to reuse incompatible run {expected_run_dir}"
                    )
                run_dir = expected_run_dir
            else:
                run_dir = train_from_config(resolved_path)
            metrics_path = run_dir / "metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            source = _compact_metrics(metrics)
            development: dict[str, object] = {}
            for evaluation in matrix.get("development_evaluations", []):
                name = str(evaluation["name"])
                output = run_dir / "development" / f"{name}.json"
                if reuse and output.is_file():
                    external_metrics = json.loads(
                        output.read_text(encoding="utf-8")
                    )
                else:
                    external_metrics = evaluate_checkpoint(
                        run_dir / "best.pt",
                        evaluation["manifest"],
                        evaluation.get("data_root", config["data_root"]),
                        evaluation.get("split", "external_calibration"),
                        output,
                        int(evaluation.get("batch_size", 1)),
                        int(evaluation.get("workers", 4)),
                    )
                development[name] = _compact_metrics(external_metrics)
            runs.append(
                {
                    "candidate": candidate["name"],
                    "seed": seed,
                    "run_dir": str(run_dir.resolve()),
                    "data_license_scope": matrix.get(
                        "data_license_scope", "unspecified"
                    ),
                    "weight_license_status": candidate.get(
                        "weight_license_status",
                        candidate.get("license_bucket", "unspecified"),
                    ),
                    "source_validation": source,
                    "development": development,
                }
            )

    def ranking_values(run: dict[str, object]) -> dict[str, float | bool]:
        source = run["source_validation"]
        development = run["development"]
        points = [source, *development.values()]
        constraints_met = all(bool(point["constraint_met"]) for point in points)
        worst_risk = max(float(point["crop_spray_risk"]) for point in points)
        robust_recall = min(
            float(point["worst_domain_safe_weed_recall"])
            for point in points
        )
        robust_macro_recall = min(
            float(point["safe_weed_recall"]) for point in points
        )
        robust_weed_iou = min(
            float(point["worst_domain_weed_iou"]) for point in points
        )
        return {
            "constraints_met": constraints_met,
            "worst_risk": worst_risk,
            "robust_recall": robust_recall,
            "robust_macro_recall": robust_macro_recall,
            "robust_weed_iou": robust_weed_iou,
        }

    def rank_key(
        run: dict[str, object],
    ) -> tuple[float, float, float, float, float]:
        values = ranking_values(run)
        if bool(values["constraints_met"]):
            return (
                1.0,
                float(values["robust_recall"]),
                float(values["robust_macro_recall"]),
                float(values["robust_weed_iou"]),
                -float(values["worst_risk"]),
            )
        # Failed candidates are ordered by how close they came to the safety
        # boundary, never by a recall that was bought with crop damage.
        return (
            0.0,
            -float(values["worst_risk"]),
            float(values["robust_recall"]),
            float(values["robust_macro_recall"]),
            float(values["robust_weed_iou"]),
        )

    run_ranking = [
        {
            "rank": index,
            "candidate": run["candidate"],
            "seed": run["seed"],
            "all_safety_constraints_met": bool(
                ranking_values(run)["constraints_met"]
            ),
            "worst_crop_spray_risk": ranking_values(run)["worst_risk"],
            "robust_safe_weed_recall": ranking_values(run)["robust_recall"],
            "robust_macro_safe_weed_recall": ranking_values(run)[
                "robust_macro_recall"
            ],
            "robust_worst_domain_weed_iou": ranking_values(run)[
                "robust_weed_iou"
            ],
        }
        for index, run in enumerate(
            sorted(runs, key=rank_key, reverse=True), start=1
        )
    ]
    by_candidate: dict[str, list[dict[str, object]]] = {}
    for run in runs:
        by_candidate.setdefault(str(run["candidate"]), []).append(run)

    def candidate_key(
        item: tuple[str, list[dict[str, object]]],
    ) -> tuple[float, float, float, float, float]:
        _, candidate_runs = item
        values = [ranking_values(run) for run in candidate_runs]
        all_safe = all(bool(value["constraints_met"]) for value in values)
        worst_risk = max(float(value["worst_risk"]) for value in values)
        recalls = [float(value["robust_recall"]) for value in values]
        weed_ious = [float(value["robust_weed_iou"]) for value in values]
        if not all_safe:
            return (
                0.0,
                -worst_risk,
                min(recalls),
                statistics.fmean(recalls),
                min(weed_ious),
            )
        return (
            1.0,
            min(recalls),
            statistics.fmean(recalls),
            min(weed_ious),
            -worst_risk,
        )

    ranking: list[dict[str, object]] = []
    for index, (candidate, candidate_runs) in enumerate(
        sorted(by_candidate.items(), key=candidate_key, reverse=True),
        start=1,
    ):
        values = [ranking_values(run) for run in candidate_runs]
        recalls = [float(value["robust_recall"]) for value in values]
        weed_ious = [float(value["robust_weed_iou"]) for value in values]
        ranking.append(
            {
                "rank": index,
                "candidate": candidate,
                "seeds": [run["seed"] for run in candidate_runs],
                "all_safety_constraints_met": all(
                    bool(value["constraints_met"]) for value in values
                ),
                "safety_pass_rate": sum(
                    bool(value["constraints_met"]) for value in values
                )
                / len(values),
                "worst_crop_spray_risk_across_seeds": max(
                    float(value["worst_risk"]) for value in values
                ),
                "robust_safe_weed_recall_mean": statistics.fmean(recalls),
                "robust_safe_weed_recall_std": (
                    statistics.stdev(recalls) if len(recalls) > 1 else 0.0
                ),
                "robust_safe_weed_recall_worst_seed": min(recalls),
                "robust_worst_domain_weed_iou_mean": statistics.fmean(
                    weed_ious
                ),
                "robust_worst_domain_weed_iou_worst_seed": min(weed_ious),
            }
        )
    result = {
        "matrix": str(matrix_file.resolve()),
        "data_license_scope": matrix.get(
            "data_license_scope", "unspecified"
        ),
        "threshold_selection": (
            "per-target-crop-ID and initial unknown fallback on source "
            "validation; development is evaluated with that source-frozen "
            "policy in this preliminary table"
        ),
        "architecture_selection": (
            "preliminary source plus declared-development screen; authoritative "
            "selection requires per-run development calibration receipts; "
            "final tests untouched"
        ),
        "ranking_status": "preliminary_before_unknown_development_calibration",
        "ranking_rule": (
            "meet every configured aggregate and tail crop-spray constraint, "
            "then maximize the minimum capture-group safe-weed recall, then "
            "set-macro recall, then minimum worst-domain weed IoU"
        ),
        "ranking": ranking,
        "run_ranking": run_ranking,
        "runs": runs,
    }
    destination = work_dir / "benchmark_results.json"
    destination.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination
