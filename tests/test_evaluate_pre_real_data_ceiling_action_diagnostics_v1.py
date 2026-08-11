import math

import pytest

from scripts.evaluate_pre_real_data_ceiling_action_diagnostics_v1 import (
    normalize_threshold_size_map,
    pre_real_decision,
    wilson_upper,
)


def metric(*, f1: float, precision: float, recall: float, crop_rate: float, upper: float) -> dict:
    return {
        "f1": f1,
        "precision": precision,
        "recall": recall,
        "crop_collision_rate_per_attempt": crop_rate,
        "crop_collision_wilson_upper_95": upper,
    }


def test_wilson_upper_is_explicit_and_fail_closed_for_no_trials() -> None:
    assert wilson_upper(0, 0) is None
    assert math.isclose(wilson_upper(0, 100), 0.03699349820698568)
    with pytest.raises(ValueError):
        wilson_upper(2, 1)


def test_synthetic_size_view_uses_an_explicit_existing_pheno_threshold_view() -> None:
    assert normalize_threshold_size_map(
        [0.0, 41.0, 82.0], [0.0, 28.0, 42.0, 56.0, 82.0], {"0": 0, "41": 42, "82": 82}
    ) == {"0": 0.0, "41": 42.0, "82": 82.0}
    with pytest.raises(ValueError):
        normalize_threshold_size_map(
            [0.0, 41.0, 82.0], [0.0, 42.0, 82.0], {"0": 0, "41": 41, "82": 82}
        )


def test_pre_real_decision_uses_only_real_panels_and_keeps_field_gate_separate() -> None:
    current_pheno = metric(f1=0.72, precision=0.82, recall=0.65, crop_rate=0.11, upper=0.16)
    candidate_pheno = metric(f1=0.71, precision=0.81, recall=0.64, crop_rate=0.12, upper=0.17)
    current_bonirob = metric(f1=0.05, precision=0.14, recall=0.03, crop_rate=0.12, upper=0.18)
    candidate_bonirob = metric(f1=0.10, precision=0.20, recall=0.07, crop_rate=0.10, upper=0.15)
    rules = {
        "phenobench_f1_maximum_regression": 0.03,
        "phenobench_crop_hit_maximum_absolute_increase": 0.02,
        "bonirob_f1_minimum_absolute_gain": 0.03,
        "bonirob_crop_hit_maximum_absolute_increase": 0.0,
    }
    field_gate = {
        "precision_minimum": 0.98,
        "recall_minimum": 0.95,
        "f1_minimum": 0.965,
        "crop_hit_rate_maximum": 0.005,
        "crop_hit_upper_95_maximum": 0.005,
    }
    result = pre_real_decision(
        current_pheno,
        candidate_pheno,
        current_bonirob,
        candidate_bonirob,
        rules,
        field_gate,
    )
    assert result["candidate_displaces_current_pre_real_best"] is True
    assert result["synthetic_score_used"] is False
    assert result["field_fire_go"] is False
