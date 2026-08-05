import pytest

from scripts.finalize_cropcraft_reproductive_gate_v9 import (
    validate_distribution,
    validate_duplicate_audit,
)


def test_duplicate_gate_requires_zero_matches() -> None:
    audit = {
        "scope": {"candidate_samples": 100, "reference_samples": 20765},
        "candidate_to_reference_match_count": 0,
        "within_candidate_match_count": 0,
        "within_candidate_cross_split_match_count": 0,
        "within_candidate_same_split_match_count": 0,
        "passed": True,
    }

    result = validate_duplicate_audit(audit, 100, 20765)

    assert result["passed"] is True
    assert result["candidate_to_reference_matches"] == 0


def test_duplicate_gate_rejects_same_split_near_pair() -> None:
    audit = {
        "scope": {"candidate_samples": 100, "reference_samples": 20765},
        "candidate_to_reference_match_count": 0,
        "within_candidate_match_count": 1,
        "within_candidate_cross_split_match_count": 0,
        "within_candidate_same_split_match_count": 1,
        "passed": True,
    }

    with pytest.raises(ValueError, match="within-candidate duplicate matches"):
        validate_duplicate_audit(audit, 100, 20765)


def test_distribution_gate_requires_every_frozen_metric() -> None:
    metrics = ["brightness_mean", "crop_fraction"]
    report = {
        "phase": "pilot",
        "all_quality_gates_passed": True,
        "required_metric_comparison": {
            "brightness_mean": {"passed": True, "synthetic_q50": 0.4},
            "crop_fraction": {"passed": True, "synthetic_q50": 0.45},
        },
    }

    assert validate_distribution(report, "pilot", metrics) == {
        "brightness_mean": 0.4,
        "crop_fraction": 0.45,
    }
