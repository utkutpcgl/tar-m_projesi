#!/usr/bin/env python3
"""Score real-only field benchmarks without letting one dataset dominate.

Each evaluation artifact is first macro-averaged over its field/session groups,
then datasets are macro-averaged within target-like and breadth panels.  A
domain-balanced lower-tail term rewards robustness.  Synthetic diagnostics are
reported separately and have exactly zero weight in the real selection score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


METRICS = ("mean_iou", "crop_iou", "weed_iou")
MetricValue = float | None


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    value = (
        json.loads(source.read_text(encoding="utf-8"))
        if source.suffix.lower() == ".json"
        else yaml.safe_load(source.read_text(encoding="utf-8"))
    )
    if not isinstance(value, dict):
        raise ValueError(f"Expected object: {source}")
    return value


def validate_confirmation_seed_set(
    protocol: dict[str, Any], seeds: list[int]
) -> None:
    confirmation = protocol.get("required_confirmation", {})
    if not isinstance(confirmation, dict):
        raise ValueError("required_confirmation must be a mapping")
    if "paired_seeds" in confirmation:
        expected = sorted(int(value) for value in confirmation["paired_seeds"])
    elif "screen_seed" in confirmation:
        expected = [int(confirmation["screen_seed"])]
    else:
        return
    if sorted(seeds) != expected:
        raise ValueError(
            f"Benchmark seed set differs from frozen protocol: "
            f"{sorted(seeds)} != {expected}"
        )


def validate_locked_evidence(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    rows = protocol.get("locked_evidence", [])
    if not isinstance(rows, list):
        raise ValueError("locked_evidence must be a list")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("locked_evidence entries must be mappings")
        path = Path(str(row["path"])).expanduser().resolve()
        actual_sha = sha256(path)
        if actual_sha != str(row["sha256"]):
            raise ValueError(f"Locked evidence SHA-256 changed: {path}")
        document = load_object(path)
        required_true = row.get("required_true", [])
        if not isinstance(required_true, list):
            raise ValueError("locked_evidence.required_true must be a list")
        for key in required_true:
            if document.get(str(key)) is not True:
                raise ValueError(f"Locked evidence flag is not true: {path}::{key}")
        validated.append(
            {
                "name": str(row["name"]),
                "path": str(path),
                "sha256": actual_sha,
                "required_true": [str(key) for key in required_true],
            }
        )
    return validated


def finite(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite {name}: {value}")
    return result


def finite_or_none(value: Any, name: str) -> MetricValue:
    """Keep union-empty class IoU undefined instead of inventing a score."""
    if value is None:
        return None
    return finite(value, name)


def unit_metrics(group: dict[str, Any], name: str) -> dict[str, MetricValue]:
    iou = group.get("iou")
    if not isinstance(iou, dict):
        raise ValueError(f"Missing IoU mapping: {name}")
    return {
        "mean_iou": finite(group["mean_iou"], f"{name}.mean_iou"),
        "crop_iou": finite_or_none(
            iou["target_crop"], f"{name}.target_crop"
        ),
        "weed_iou": finite_or_none(
            iou["other_vegetation"], f"{name}.other_vegetation"
        ),
    }


def lower_tail(values: list[float], fraction: float) -> float:
    if not values:
        raise ValueError("Cannot score an empty tail")
    count = max(1, math.ceil(len(values) * fraction))
    return statistics.fmean(sorted(values)[:count])


def defined_mean(values: list[MetricValue]) -> MetricValue:
    defined = [value for value in values if value is not None]
    return statistics.fmean(defined) if defined else None


def defined_lower_tail(
    values: list[MetricValue], fraction: float
) -> MetricValue:
    defined = [value for value in values if value is not None]
    return lower_tail(defined, fraction) if defined else None


def summarize_artifact(path: Path, tail_fraction: float) -> dict[str, Any]:
    artifact = load_object(path)
    groups = artifact.get("domains")
    if not isinstance(groups, dict) or not groups:
        raise ValueError(f"Evaluation has no field/session groups: {path}")
    units = {
        str(name): unit_metrics(value, str(name))
        for name, value in sorted(groups.items())
    }
    macro = {
        metric: defined_mean([unit[metric] for unit in units.values()])
        for metric in METRICS
    }
    tail = {
        metric: defined_lower_tail(
            [unit[metric] for unit in units.values()], tail_fraction
        )
        for metric in METRICS
    }
    if macro["mean_iou"] is None or tail["mean_iou"] is None:
        raise ValueError(f"Evaluation has no defined mean-IoU units: {path}")
    selected = artifact.get("selected_operating_point", {})
    safety = None
    if isinstance(selected, dict):
        risk = selected.get("worst_domain_crop_spray_risk")
        recall = selected.get("worst_domain_safe_weed_recall")
        if risk is not None and recall is not None:
            safety = {
                "worst_domain_crop_spray_risk": finite(risk, "crop_spray_risk"),
                "worst_domain_safe_weed_recall": finite(recall, "safe_weed_recall"),
            }
    return {
        "path": str(path),
        "sha256": sha256(path),
        "field_session_units": units,
        "unit_count": len(units),
        "defined_unit_count": {
            metric: sum(unit[metric] is not None for unit in units.values())
            for metric in METRICS
        },
        "field_session_macro": macro,
        "field_session_lower_tail": tail,
        "safety_diagnostic": safety,
    }


def mean_dict(
    rows: list[dict[str, MetricValue]],
) -> dict[str, MetricValue]:
    if not rows:
        raise ValueError("Cannot macro-average an empty panel")
    return {
        metric: defined_mean([row[metric] for row in rows])
        for metric in METRICS
    }


def score_run(
    protocol: dict[str, Any], run: dict[str, Any]
) -> dict[str, Any]:
    real_domains = protocol["real_domains"]
    artifacts = run.get("real_artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(real_domains):
        raise ValueError(
            f"Real artifact set differs from protocol: "
            f"{sorted(artifacts or {})} != {sorted(real_domains)}"
        )
    tail_fraction = finite(protocol["ranking"]["tail_fraction"], "tail_fraction")
    if not 0.0 < tail_fraction <= 1.0:
        raise ValueError("tail_fraction must be in (0, 1]")
    domains: dict[str, Any] = {}
    panel_rows: dict[str, list[dict[str, MetricValue]]] = {
        "target_like": [],
        "breadth": [],
    }
    tail_rows: list[dict[str, MetricValue]] = []
    for name, domain_cfg in real_domains.items():
        panel = str(domain_cfg["panel"])
        if panel not in panel_rows:
            raise ValueError(f"Unknown panel for {name}: {panel}")
        path = Path(str(artifacts[name])).expanduser().resolve()
        summary = summarize_artifact(path, tail_fraction)
        summary["panel"] = panel
        domains[name] = summary
        panel_rows[panel].append(summary["field_session_macro"])
        tail_rows.append(summary["field_session_lower_tail"])

    target = mean_dict(panel_rows["target_like"])
    breadth = mean_dict(panel_rows["breadth"])
    tail = mean_dict(tail_rows)
    weights = protocol["ranking"]["weights"]
    if not math.isclose(sum(float(value) for value in weights.values()), 1.0):
        raise ValueError("Ranking weights must sum to one")
    aggregate: dict[str, MetricValue] = {}
    for metric in METRICS:
        components = (target[metric], breadth[metric], tail[metric])
        aggregate[metric] = (
            None
            if any(value is None for value in components)
            else float(weights["target_like_domain_macro"]) * components[0]
            + float(weights["breadth_domain_macro"]) * components[1]
            + float(weights["domain_balanced_field_tail"]) * components[2]
        )
    if any(
        value is None
        for value in (target["mean_iou"], breadth["mean_iou"], tail["mean_iou"])
    ):
        raise ValueError("Primary mean-IoU score has an undefined panel")
    aggregate.update(
        {
            "target_like_mean_iou": target["mean_iou"],
            "breadth_mean_iou": breadth["mean_iou"],
            "domain_balanced_field_tail_mean_iou": tail["mean_iou"],
        }
    )

    synthetic: dict[str, Any] = {}
    synthetic_artifacts = run.get("synthetic_artifacts", {})
    if not isinstance(synthetic_artifacts, dict):
        raise ValueError("synthetic_artifacts must be a mapping")
    for name, value in sorted(synthetic_artifacts.items()):
        synthetic[name] = summarize_artifact(
            Path(str(value)).expanduser().resolve(), tail_fraction
        )
    return {
        "candidate": str(run["candidate"]),
        "seed": int(run["seed"]),
        "real_domains": domains,
        "panel_scores": {"target_like": target, "breadth": breadth},
        "domain_balanced_field_tail": tail,
        "aggregate": aggregate,
        "synthetic_diagnostics": synthetic,
        "synthetic_weight_in_real_score": 0.0,
    }


def paired_checks(
    protocol: dict[str, Any], control: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    rules = protocol["acceptance"]
    deltas: dict[str, MetricValue] = {}
    for key, right in candidate["aggregate"].items():
        left = control["aggregate"][key]
        deltas[key] = None if left is None or right is None else right - left
    required_deltas = (
        "mean_iou",
        "target_like_mean_iou",
        "breadth_mean_iou",
        "domain_balanced_field_tail_mean_iou",
    )
    if any(deltas[key] is None for key in required_deltas):
        raise ValueError("A primary paired mean-IoU delta is undefined")
    domain_checks: dict[str, bool] = {}
    field_checks: dict[str, bool] = {}
    worst_field_delta = math.inf
    for name, cfg in protocol["real_domains"].items():
        left = control["real_domains"][name]
        right = candidate["real_domains"][name]
        limit = float(rules["maximum_domain_mean_iou_regression"][cfg["panel"]])
        domain_checks[name] = (
            right["field_session_macro"]["mean_iou"]
            - left["field_session_macro"]["mean_iou"]
            >= -limit
        )
        if set(left["field_session_units"]) != set(right["field_session_units"]):
            raise ValueError(f"Field/session unit mismatch for paired domain {name}")
        for unit in left["field_session_units"]:
            delta = (
                right["field_session_units"][unit]["mean_iou"]
                - left["field_session_units"][unit]["mean_iou"]
            )
            worst_field_delta = min(worst_field_delta, delta)
            field_checks[f"{name}::{unit}"] = delta >= -float(
                rules["maximum_any_field_mean_iou_regression"]
            )
    checks = {
        "primary_noninferiority": deltas["mean_iou"]
        >= -float(rules["maximum_primary_regression"]),
        "target_like_noninferiority": deltas["target_like_mean_iou"]
        >= -float(rules["maximum_target_like_regression"]),
        "tail_noninferiority": deltas["domain_balanced_field_tail_mean_iou"]
        >= -float(rules["maximum_tail_regression"]),
        "all_domain_noninferiority": all(domain_checks.values()),
        "all_field_noninferiority": all(field_checks.values()),
    }
    return {
        "aggregate_deltas": deltas,
        "domain_checks": domain_checks,
        "field_checks": field_checks,
        "worst_field_mean_iou_delta": worst_field_delta,
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--benchmark", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    protocol_path = Path(args.protocol).expanduser().resolve()
    benchmark_path = Path(args.benchmark).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    if output.exists():
        raise FileExistsError(output)
    protocol = load_object(protocol_path)
    if protocol.get("frozen_before_challenger_training") is not True:
        raise ValueError("Protocol is not frozen before challenger training")
    if float(protocol.get("synthetic_weight_in_real_score", -1)) != 0.0:
        raise ValueError("Synthetic data must have zero real-score weight")
    locked_evidence = validate_locked_evidence(protocol)
    benchmark = load_object(benchmark_path)
    scored = [score_run(protocol, run) for run in benchmark["runs"]]
    indexed = {(run["candidate"], run["seed"]): run for run in scored}
    if len(indexed) != len(scored):
        raise ValueError("Duplicate candidate/seed run")
    control_name = str(protocol["control"])
    candidates = sorted({run["candidate"] for run in scored} - {control_name})
    seeds = sorted({run["seed"] for run in scored})
    validate_confirmation_seed_set(protocol, seeds)
    paired: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        paired[candidate] = {}
        for seed in seeds:
            if (control_name, seed) not in indexed or (candidate, seed) not in indexed:
                raise ValueError(f"Missing paired run for {candidate}/seed{seed}")
            paired[candidate][str(seed)] = paired_checks(
                protocol,
                indexed[(control_name, seed)],
                indexed[(candidate, seed)],
            )
    summary: dict[str, Any] = {}
    for candidate, rows in paired.items():
        values = list(rows.values())
        primary = [row["aggregate_deltas"]["mean_iou"] for row in values]
        target = [row["aggregate_deltas"]["target_like_mean_iou"] for row in values]
        rules = protocol["acceptance"]
        checks = {
            "mean_primary_gain": statistics.fmean(primary)
            >= float(rules["minimum_mean_primary_gain"]),
            "mean_target_like_gain": statistics.fmean(target)
            >= float(rules["minimum_mean_target_like_gain"]),
            "minimum_seed_wins": sum(value > 0.0 for value in primary)
            >= int(rules["minimum_primary_wins"]),
            "paired_noninferiority": all(row["passed"] for row in values),
        }
        summary[candidate] = {
            "mean_primary_delta": statistics.fmean(primary),
            "mean_target_like_delta": statistics.fmean(target),
            "primary_wins": sum(value > 0.0 for value in primary),
            "checks": checks,
            "accepted": all(checks.values()),
        }
    scorer_path = Path(__file__).resolve()
    receipt = {
        "schema_version": 2,
        "scorer": str(scorer_path),
        "scorer_sha256": sha256(scorer_path),
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "benchmark": str(benchmark_path),
        "benchmark_sha256": sha256(benchmark_path),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "real_only_selection_score": True,
        "synthetic_weight_in_real_score": 0.0,
        "undefined_class_metric_policy": {
            "field_session_mean_iou": (
                "Use the frozen evaluator value verbatim; a class whose prediction "
                "and ground-truth union is empty is omitted by that evaluator."
            ),
            "descriptive_crop_and_weed_iou": (
                "Preserve union-empty values as null and macro-average only defined "
                "field/session units; never replace null with zero."
            ),
            "selection_impact": (
                "Crop-IoU and weed-IoU are descriptive only; every acceptance and "
                "ranking gate uses finite field/session mean-IoU."
            ),
        },
        "locked_evidence": locked_evidence,
        "runs": scored,
        "paired": paired,
        "candidate_summary": summary,
        "external_test_used_for_selection": False,
        "deployment_claim_from_this_score": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
