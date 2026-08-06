from __future__ import annotations

import numpy as np

from scripts.evaluate_domain_adaptation_curve_v1 import (
    _aggregate,
    _valid_cache,
    _write_json_atomic,
    paired_bootstrap_delta,
    select_candidate,
)


def _row(sample: str, confusion: list[list[int]]) -> dict[str, object]:
    return {
        "sample_id": sample,
        "confusion": confusion,
        "crop_pixels": 10,
        "weed_pixels": 10,
        "safe_pixels": 5,
        "safe_crop_pixels": 0,
        "safe_weed_pixels": 5,
    }


def test_aggregate_semantic_and_safe_pixel_metrics() -> None:
    result = _aggregate([_row("a", [[10, 0, 0], [0, 8, 2], [0, 1, 9]])])
    assert result["images"] == 1
    assert result["crop_spray_risk"] == 0.0
    assert result["safe_weed_recall"] == 0.5
    assert 0.0 < result["mean_iou"] < 1.0


def test_paired_bootstrap_detects_strictly_better_candidate() -> None:
    baseline = [
        _row(str(index), [[8, 1, 1], [1, 6, 3], [1, 3, 6]])
        for index in range(8)
    ]
    candidate = [
        _row(str(index), [[10, 0, 0], [0, 10, 0], [0, 0, 10]])
        for index in range(8)
    ]
    result = paired_bootstrap_delta(baseline, candidate, resamples=100, seed=3)
    assert result["ci95_low"] > 0.0
    assert result["bootstrap_probability_delta_gt_zero"] == 1.0


def test_paired_bootstrap_rejects_mismatched_order() -> None:
    first = [_row("a", np.eye(3, dtype=int).tolist())]
    second = [_row("b", np.eye(3, dtype=int).tolist())]
    try:
        paired_bootstrap_delta(first, second, resamples=10)
    except ValueError:
        pass
    else:
        raise AssertionError("mismatched pairs must fail closed")


def _run(name: str, frames: int, source: float, target: float, breadth: float):
    return {
        "candidate": name,
        "target_train_frames": frames,
        "source_validation": {"mean_iou": source},
        "development": {
            "target": {"mean_iou": target},
            "breadth": {"mean_iou": breadth},
        },
    }


def test_selection_uses_frozen_gates_and_simplicity_tolerance() -> None:
    runs = [
        _run("base", 0, 0.80, 0.60, 0.55),
        _run("small", 10, 0.79, 0.66, 0.55),
        _run("large", 100, 0.79, 0.665, 0.55),
        _run("forgetful", 25, 0.70, 0.75, 0.55),
    ]
    result = select_candidate(
        runs,
        baseline_candidate="base",
        specification={
            "weights": {
                "source_validation": 0.2,
                "target": 0.6,
                "breadth": 0.2,
            },
            "minimum_delta_vs_baseline": {
                "source_validation": -0.025,
                "target": 0.0,
                "breadth": -0.025,
            },
            "simplicity_tolerance": 0.005,
        },
    )
    assert result["selected_candidate"] == "small"
    diagnostics = {row["candidate"]: row for row in result["diagnostics"]}
    assert diagnostics["forgetful"]["eligible"] is False
    assert diagnostics["forgetful"]["failed_gates"] == ["source_validation"]


def test_evaluation_cache_is_identity_strict_and_atomic(tmp_path) -> None:
    path = tmp_path / "cache" / "result.json"
    identity = {"sample_ids": ["a"], "checkpoint_sha256": "abc"}
    payload = {
        "identity": identity,
        "result": {"images": 1, "mean_iou": 0.5},
        "per_image": [{"sample_id": "a", "confusion": [[1]]}],
    }
    _write_json_atomic(path, payload)
    cached = _valid_cache(path, expected=identity)
    assert cached is not None
    assert cached[0]["mean_iou"] == 0.5
    assert _valid_cache(
        path,
        expected={"sample_ids": ["a"], "checkpoint_sha256": "different"},
    ) is None
    assert not path.with_suffix(".json.tmp").exists()
