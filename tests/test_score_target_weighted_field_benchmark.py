import json
from pathlib import Path

import pytest

from scripts.score_target_weighted_field_benchmark import (
    paired_checks,
    score_run,
    validate_confirmation_seed_set,
    validate_locked_evidence,
)


def artifact(path: Path, values: list[float]) -> Path:
    groups = {}
    for index, value in enumerate(values):
        groups[f"field_{index}"] = {
            "mean_iou": value,
            "iou": {
                "background": value,
                "target_crop": value - 0.01,
                "other_vegetation": value - 0.02,
            },
        }
    path.write_text(json.dumps({"domains": groups}), encoding="utf-8")
    return path


def protocol() -> dict:
    return {
        "real_domains": {
            "large_target": {"panel": "target_like"},
            "small_target": {"panel": "target_like"},
            "breadth": {"panel": "breadth"},
        },
        "ranking": {
            "tail_fraction": 0.25,
            "weights": {
                "target_like_domain_macro": 0.60,
                "breadth_domain_macro": 0.25,
                "domain_balanced_field_tail": 0.15,
            },
        },
        "acceptance": {
            "maximum_domain_mean_iou_regression": {
                "target_like": 0.01,
                "breadth": 0.015,
            },
            "maximum_any_field_mean_iou_regression": 0.025,
            "maximum_primary_regression": 0.002,
            "maximum_target_like_regression": 0.005,
            "maximum_tail_regression": 0.01,
        },
    }


def test_dataset_macro_prevents_large_dataset_domination(tmp_path: Path) -> None:
    large = artifact(tmp_path / "large.json", [0.9] * 100)
    small = artifact(tmp_path / "small.json", [0.3])
    breadth = artifact(tmp_path / "breadth.json", [0.5])
    result = score_run(
        protocol(),
        {
            "candidate": "model",
            "seed": 17,
            "real_artifacts": {
                "large_target": str(large),
                "small_target": str(small),
                "breadth": str(breadth),
            },
            "synthetic_artifacts": {},
        },
    )
    assert result["panel_scores"]["target_like"]["mean_iou"] == 0.6
    assert result["synthetic_weight_in_real_score"] == 0.0


def test_union_empty_class_iou_stays_null_and_does_not_break_primary_score(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.json"
    missing.write_text(
        json.dumps(
            {
                "domains": {
                    "field_without_weed_union": {
                        "mean_iou": 0.9,
                        "iou": {
                            "background": 0.91,
                            "target_crop": 0.89,
                            "other_vegetation": None,
                        },
                    },
                    "field_with_weed_union": {
                        "mean_iou": 0.6,
                        "iou": {
                            "background": 0.7,
                            "target_crop": 0.7,
                            "other_vegetation": 0.4,
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    normal = artifact(tmp_path / "normal.json", [0.5])
    result = score_run(
        protocol(),
        {
            "candidate": "model",
            "seed": 17,
            "real_artifacts": {
                "large_target": str(missing),
                "small_target": str(normal),
                "breadth": str(normal),
            },
            "synthetic_artifacts": {},
        },
    )
    summary = result["real_domains"]["large_target"]
    assert summary["field_session_macro"]["mean_iou"] == 0.75
    assert summary["field_session_macro"]["weed_iou"] == 0.4
    assert summary["defined_unit_count"]["weed_iou"] == 1
    assert result["aggregate"]["mean_iou"] is not None


def test_any_field_regression_is_a_hard_gate(tmp_path: Path) -> None:
    paths = {
        "large_target": artifact(tmp_path / "large.json", [0.8, 0.8]),
        "small_target": artifact(tmp_path / "small.json", [0.7]),
        "breadth": artifact(tmp_path / "breadth.json", [0.6]),
    }
    candidate_paths = {
        "large_target": artifact(tmp_path / "large_c.json", [0.9, 0.76]),
        "small_target": artifact(tmp_path / "small_c.json", [0.75]),
        "breadth": artifact(tmp_path / "breadth_c.json", [0.65]),
    }
    base = score_run(
        protocol(),
        {"candidate": "base", "seed": 17, "real_artifacts": paths},
    )
    candidate = score_run(
        protocol(),
        {"candidate": "candidate", "seed": 17, "real_artifacts": candidate_paths},
    )
    checks = paired_checks(protocol(), base, candidate)
    assert checks["aggregate_deltas"]["mean_iou"] > 0.0
    assert checks["checks"]["all_field_noninferiority"] is False
    assert checks["passed"] is False


def test_confirmation_requires_exact_frozen_seed_set() -> None:
    frozen = {"required_confirmation": {"paired_seeds": [17, 29, 43]}}
    validate_confirmation_seed_set(frozen, [43, 17, 29])
    with pytest.raises(ValueError, match="seed set differs"):
        validate_confirmation_seed_set(frozen, [17])


def test_locked_evidence_checks_hash_and_flags(tmp_path: Path) -> None:
    evidence = tmp_path / "release.json"
    evidence.write_text(
        json.dumps({"holdout_release_accepted": True}), encoding="utf-8"
    )
    import hashlib

    digest = hashlib.sha256(evidence.read_bytes()).hexdigest()
    validated = validate_locked_evidence(
        {
            "locked_evidence": [
                {
                    "name": "holdout",
                    "path": str(evidence),
                    "sha256": digest,
                    "required_true": ["holdout_release_accepted"],
                }
            ]
        }
    )
    assert validated[0]["sha256"] == digest
