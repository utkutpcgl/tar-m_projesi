#!/usr/bin/env python3
"""Apply frozen target-like and generalist gates to the recovery screen."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RECOVERY = PROJECT_ROOT / "configs/benchmark/simulation_diversity_real_recovery_v1.yaml"
DEFAULT_TARGET_PROTOCOL = PROJECT_ROOT / "configs/benchmark/target_weighted_real_recovery_v1.yaml"
DEFAULT_MATRIX = PROJECT_ROOT / "configs/benchmark/target_weighted_real_recovery_matrix_v1.yaml"


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.suffix == ".json"
        else yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping: {path}")
    return value


def run_by_name(score: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [row for row in score["runs"] if row["candidate"] == name]
    if len(matches) != 1:
        raise ValueError(f"Expected one scored run named {name}")
    return matches[0]


def generalist_checks(
    control: dict[str, Any], candidate: dict[str, Any], rules: dict[str, Any]
) -> dict[str, Any]:
    names = sorted(control["real_domains"])
    if names != sorted(candidate["real_domains"]):
        raise ValueError("Control/candidate real-domain sets differ")
    control_macro = statistics.fmean(
        control["real_domains"][name]["field_session_macro"]["mean_iou"] for name in names
    )
    candidate_macro = statistics.fmean(
        candidate["real_domains"][name]["field_session_macro"]["mean_iou"] for name in names
    )
    control_tail = float(control["aggregate"]["domain_balanced_field_tail_mean_iou"])
    candidate_tail = float(candidate["aggregate"]["domain_balanced_field_tail_mean_iou"])
    control_primary = 0.80 * control_macro + 0.20 * control_tail
    candidate_primary = 0.80 * candidate_macro + 0.20 * candidate_tail
    target_delta = float(candidate["aggregate"]["target_like_mean_iou"]) - float(
        control["aggregate"]["target_like_mean_iou"]
    )
    critical_deltas = {
        name: float(candidate["real_domains"][name]["field_session_macro"]["mean_iou"])
        - float(control["real_domains"][name]["field_session_macro"]["mean_iou"])
        for name in rules["critical_target_domains"]
    }
    field_deltas: dict[str, float] = {}
    for name in names:
        left = control["real_domains"][name]["field_session_units"]
        right = candidate["real_domains"][name]["field_session_units"]
        if set(left) != set(right):
            raise ValueError(f"Field/session mismatch: {name}")
        for field in left:
            field_deltas[f"{name}::{field}"] = float(right[field]["mean_iou"]) - float(
                left[field]["mean_iou"]
            )
    regressed = sum(value < -0.025 for value in field_deltas.values())
    fraction_regressed = regressed / len(field_deltas)
    deltas = {
        "equal_real_domain_macro_mean_iou": candidate_macro - control_macro,
        "domain_balanced_field_tail_mean_iou": candidate_tail - control_tail,
        "generalist_primary": candidate_primary - control_primary,
        "target_like_domain_macro_mean_iou": target_delta,
        "critical_domains": critical_deltas,
    }
    checks = {
        "minimum_generalist_primary_gain": deltas["generalist_primary"]
        >= float(rules["minimum_primary_gain"]),
        "target_like_noninferiority": target_delta
        >= -float(rules["maximum_target_like_macro_regression"]),
        "lower_tail_noninferiority": deltas["domain_balanced_field_tail_mean_iou"]
        >= -float(rules["maximum_lower_tail_regression"]),
        "critical_domain_noninferiority": all(
            value >= -float(rules["maximum_critical_domain_regression"])
            for value in critical_deltas.values()
        ),
        "field_regression_fraction_within_limit": fraction_regressed
        <= float(rules["maximum_fraction_fields_regressing_more_than_0_025"]),
    }
    return {
        "scores": {
            "control_equal_real_domain_macro_mean_iou": control_macro,
            "candidate_equal_real_domain_macro_mean_iou": candidate_macro,
            "control_domain_balanced_field_tail_mean_iou": control_tail,
            "candidate_domain_balanced_field_tail_mean_iou": candidate_tail,
            "control_generalist_primary": control_primary,
            "candidate_generalist_primary": candidate_primary,
        },
        "deltas": deltas,
        "field_session_count": len(field_deltas),
        "fields_regressing_more_than_0_025": regressed,
        "fraction_fields_regressing_more_than_0_025": fraction_regressed,
        "worst_field_delta": min(field_deltas.values()),
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", required=True)
    parser.add_argument("--recovery-protocol", default=str(DEFAULT_RECOVERY))
    parser.add_argument("--target-protocol", default=str(DEFAULT_TARGET_PROTOCOL))
    parser.add_argument("--matrix", default=str(DEFAULT_MATRIX))
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    score_path = Path(args.score).resolve()
    recovery_path = Path(args.recovery_protocol).resolve()
    target_path = Path(args.target_protocol).resolve()
    matrix_path = Path(args.matrix).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(output)
    recovery = load(recovery_path)
    score = load(score_path)
    if score["protocol_sha256"] != sha256(target_path):
        raise RuntimeError("Target scorer protocol hash mismatch")
    if score["benchmark_sha256"] != sha256(matrix_path):
        raise RuntimeError("Target scorer matrix hash mismatch")
    control_name = str(load(target_path)["control"])
    challenger_name = "recovery_v10_diversity_real_e2_v1"
    control = run_by_name(score, control_name)
    challenger = run_by_name(score, challenger_name)
    rules = recovery["selection"]["generalist_base"]
    generalist = generalist_checks(control, challenger, rules)
    target_summary = score["candidate_summary"][challenger_name]
    target_passed = bool(target_summary["accepted"])
    generalist_passed = bool(generalist["passed"])
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "score": str(score_path),
        "score_sha256": sha256(score_path),
        "recovery_protocol": str(recovery_path),
        "recovery_protocol_sha256": sha256(recovery_path),
        "target_protocol": str(target_path),
        "target_protocol_sha256": sha256(target_path),
        "matrix": str(matrix_path),
        "matrix_sha256": sha256(matrix_path),
        "control": control_name,
        "challenger": challenger_name,
        "target_like_screen": target_summary,
        "generalist_screen": generalist,
        "decision": {
            "target_confirmation_authorized": target_passed,
            "generalist_confirmation_authorized": generalist_passed,
            "seed17_replaces_existing_target_base": False,
            "seed17_replaces_existing_generalist_base": False,
            "reason": (
                "The frozen protocol makes seed 17 a screen only; a pass authorizes "
                "paired seeds 29/43, never immediate replacement."
            ),
        },
        "selection_weights": {
            "real_domains": 1.0,
            "synthetic_diagnostics": 0.0,
            "unlabeled_online_or_farmbot": 0.0,
        },
        "external_or_final_test_used": False,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
