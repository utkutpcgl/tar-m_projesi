import json
from pathlib import Path

import numpy as np

from scripts import audit_spot_spray_native_fixture_fairness_v1 as audit


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/benchmark/spot_spray_native_fixture_fairness_audit_v1.yaml"
RESULT = ROOT / "docs/results/spot_spray_native_fixture_fairness_audit_v1/audit_summary.json"


def _mask(x0: int, y0: int, x1: int, y1: int, shape: tuple[int, int] = (16, 16)) -> audit.BinaryMask:
    value = np.zeros(shape, dtype=bool)
    value[y0:y1, x0:x1] = True
    return audit.BinaryMask.from_full(value)


def _truth_frame(mask: audit.BinaryMask, track_id: str = "gt_weed") -> audit.TruthFrame:
    label = audit.TrackLabel(
        mask_id=1,
        track_id=track_id,
        class_name="weed",
        canopy_span_mm=30.0,
        visible_fraction=1.0,
        partial=False,
        size_stratum="small",
    )
    return audit.TruthFrame(
        semantic_path=Path("unused_semantic.png"),
        semantic_sha256="0" * 64,
        track_path=Path("unused_tracks.png"),
        track_sha256="0" * 64,
        shape=mask.shape,
        semantic_counts={0: mask.shape[0] * mask.shape[1] - mask.area, 2: mask.area},
        labels=(label,),
        masks_by_id={1: mask},
    )


def _detection(
    frame_index: int,
    detection_id: int,
    class_name: str,
    mask: audit.BinaryMask,
    track_id: str,
    confidence: float = 0.9,
) -> audit.Detection:
    class_id = 0 if class_name == "weed" else 1
    return audit.Detection(
        frame_index=frame_index,
        detection_id=detection_id,
        class_id=class_id,
        class_name=class_name,
        confidence=confidence,
        stored_track_id=track_id,
        mask=mask,
        centroid_xy=mask.centroid_xy,
    )


def _sequence(
    truth_mask: audit.BinaryMask,
    detection_masks: list[audit.BinaryMask],
) -> audit.PredictionSequence:
    frames = []
    for frame_index, detection_mask in enumerate(detection_masks):
        frames.append(
            audit.PredictionFrame(
                frame_id=f"ideal:pair:frame_{frame_index:04d}",
                frame_index=frame_index,
                image_path=Path("unused.png"),
                image_sha256="0" * 64,
                truth=_truth_frame(truth_mask),
                detections=(
                    _detection(
                        frame_index,
                        0,
                        "weed",
                        detection_mask,
                        f"p{frame_index + 1:04d}",
                    ),
                ),
            )
        )
    return audit.PredictionSequence(
        sequence_id="ideal:pair",
        pair_id="pair",
        split="test",
        condition="ideal",
        frames=tuple(frames),
    )


def _inference_contract() -> dict:
    return {
        "tracking": {
            "minimum_track_observations": 3,
            "eligible_track_match_iou": 0.5,
        },
        "ground_truth": {
            "eligible_weed_minimum_canopy_span_mm": 20.0,
            "eligible_weed_minimum_visible_fraction": 0.7,
            "require_non_partial_observation": True,
        },
    }


def test_config_is_hash_bound_non_tuning_and_synthetic_only() -> None:
    config = audit.load_config(CONFIG)
    assert config["sources"]["metrics"]["sha256"] == (
        "310b887750019c44169e4924354b7fc53e22925b8d453abbb112df9fa1d4d4a3"
    )
    assert config["sources"]["threshold_lock"]["sha256"] == (
        "3e56891c4889b6314c90a2a2927cd6751744650c9d88654be9b4a5e307046795"
    )
    assert config["sources"]["predictions"]["ideal_test"]["sha256"] == (
        "f087c40c794218ce8641ad3b46f596c718ad9bebd40d2dc8adc65a5ca532f6a3"
    )
    assert config["evidence_policy"]["locked_test_retuning_allowed"] is False
    assert config["evidence_policy"]["descriptive_sweeps_are_selection_inputs"] is False
    assert config["acceptance_rule"]["undefined_f1_fails_target_gate"] is True
    assert config["acceptance_rule"]["synthetic_results_authorize_field_or_chemical_action"] is False
    distances = config["descriptive_diagnostics"][
        "association_max_centroid_distance_px_values"
    ]
    assert max(distances) > 455.0


def test_binary_mask_iou_union_and_semantic_overlap() -> None:
    left = _mask(1, 1, 5, 5)
    right = _mask(3, 3, 7, 7)
    assert left.area == 16
    assert left.intersection_area(right) == 4
    assert left.iou(right) == 4 / 28
    merged = audit.mask_union([left, right], left.shape)
    assert merged.area == 28
    semantic = np.zeros(left.shape, dtype=np.uint8)
    semantic[1:5, 1:5] = 2
    assert left.semantic_overlap(semantic, 2) == 16
    assert right.semantic_overlap(semantic, 2) == 4


def test_f1_null_and_numeric_zero_are_distinct_states() -> None:
    undefined = audit.prf_metrics({"tp": 0, "fp": 0, "fn": 2})
    assert undefined["precision"] is None
    assert undefined["recall"] == 0.0
    assert undefined["f1"] is None
    assert undefined["f1_state"] == "undefined_missing_precision_or_recall_denominator"

    numeric_zero = audit.prf_metrics({"tp": 0, "fp": 1, "fn": 2})
    assert numeric_zero["precision"] == 0.0
    assert numeric_zero["recall"] == 0.0
    assert numeric_zero["f1"] == 0.0
    assert numeric_zero["f1_state"] == "defined_numeric_zero"


def test_tracker_geometry_and_class_gates_are_independent() -> None:
    truth = _truth_frame(_mask(1, 1, 4, 4))
    first = _detection(0, 0, "weed", _mask(1, 1, 3, 3), "p0001")
    shifted = _detection(1, 0, "weed", _mask(6, 1, 8, 3), "p0002")
    wrong_class = _detection(1, 1, "crop", _mask(1, 1, 3, 3), "p0003")
    sequence = audit.PredictionSequence(
        sequence_id="ideal:pair",
        pair_id="pair",
        split="test",
        condition="ideal",
        frames=(
            audit.PredictionFrame("f0", 0, Path("x"), "0" * 64, truth, (first,)),
            audit.PredictionFrame(
                "f1", 1, Path("x"), "0" * 64, truth, (shifted, wrong_class)
            ),
        ),
    )
    strict = audit.assign_tracks(
        sequence, minimum_iou=0.1, maximum_distance=4.0, maximum_gap=2
    )
    assert strict[(0, 0)] == "p0001"
    assert strict[(1, 0)] == "p0002"
    assert strict[(1, 1)] == "p0003"

    relaxed = audit.assign_tracks(
        sequence, minimum_iou=0.1, maximum_distance=6.0, maximum_gap=2
    )
    assert relaxed[(0, 0)] == relaxed[(1, 0)]
    assert relaxed[(1, 1)] != relaxed[(0, 0)]


def test_track_qualification_produces_undefined_f1_when_all_tracks_fragment() -> None:
    truth_mask = _mask(1, 1, 5, 5)
    sequence = _sequence(truth_mask, [truth_mask, truth_mask, truth_mask])
    fragmented = {
        (0, 0): "p0001",
        (1, 0): "p0002",
        (2, 0): "p0003",
    }
    counts, diagnostics = audit.evaluate_tracks(
        sequence, 0.8, _inference_contract(), fragmented
    )
    metrics = audit.prf_metrics(counts)
    assert diagnostics["above_threshold_detection_count"] == 3
    assert diagnostics["qualifying_predicted_track_count"] == 0
    assert counts["tp"] == 0 and counts["fp"] == 0 and counts["fn"] == 1
    assert metrics["f1"] is None


def test_qualifying_wrong_track_produces_numeric_zero_f1() -> None:
    truth_mask = _mask(1, 1, 5, 5)
    wrong_mask = _mask(10, 10, 14, 14)
    sequence = _sequence(truth_mask, [wrong_mask, wrong_mask, wrong_mask])
    joined = {(frame_index, 0): "p0001" for frame_index in range(3)}
    counts, diagnostics = audit.evaluate_tracks(
        sequence, 0.8, _inference_contract(), joined
    )
    metrics = audit.prf_metrics(counts)
    assert diagnostics["qualifying_predicted_track_count"] == 1
    assert counts["tp"] == 0 and counts["fp"] == 1 and counts["fn"] == 1
    assert metrics["f1"] == 0.0
    assert metrics["f1_state"] == "defined_numeric_zero"


def test_checkpoint_name_normalization_preserves_numeric_ids() -> None:
    assert audit.normalize_class_names({"0": "weed", "1": "crop"}) == {
        0: "weed",
        1: "crop",
    }
    assert audit.normalize_class_names(["weed", "crop"]) == {0: "weed", 1: "crop"}


def test_association_summary_separates_track_formation_from_true_positive() -> None:
    rows = []
    for condition in ("ideal", "degraded"):
        rows.extend(
            [
                {
                    "split": "test",
                    "condition": condition,
                    "is_frozen_setting": True,
                    "association_min_mask_iou": 0.1,
                    "association_max_centroid_distance_px": 160.0,
                    "maximum_frame_gap": 2,
                    "locked_weed_detection_count": 4,
                    "locked_weed_track_count": 4,
                    "locked_weed_singleton_track_count": 4,
                    "locked_weed_qualifying_track_count": 0,
                    "raw_weed_maximum_observations": 2,
                    "track_tp": 0,
                    "track_fp": 0,
                    "track_fn": 2,
                    "track_f1": None,
                    "track_f1_state": "undefined_missing_precision_or_recall_denominator",
                },
                {
                    "split": "test",
                    "condition": condition,
                    "is_frozen_setting": False,
                    "association_min_mask_iou": 0.1,
                    "association_max_centroid_distance_px": 480.0,
                    "maximum_frame_gap": 2,
                    "locked_weed_detection_count": 4,
                    "locked_weed_track_count": 1,
                    "locked_weed_singleton_track_count": 0,
                    "locked_weed_qualifying_track_count": 1,
                    "raw_weed_maximum_observations": 4,
                    "track_tp": 0,
                    "track_fp": 1,
                    "track_fn": 2,
                    "track_f1": 0.0,
                    "track_f1_state": "defined_numeric_zero",
                },
            ]
        )
    inference = {
        "tracking": {
            "association_min_mask_iou": 0.1,
            "association_max_centroid_distance_px": 160.0,
            "maximum_frame_gap": 2,
        }
    }
    summary = audit.summarize_association_sweep(rows, inference)
    for condition in ("ideal", "degraded"):
        assert summary[condition]["settings_with_locked_qualifying_tracks"] == 1
        assert summary[condition]["settings_with_defined_track_f1"] == 1
        assert summary[condition]["settings_with_track_true_positive"] == 0
        assert summary[condition]["diagnostic_result"] == (
            "geometry_relaxation_forms_qualifying_tracks_but_none_match_eligible_gt"
        )


def test_generated_terminal_package_preserves_honest_interpretation() -> None:
    payload = json.loads(RESULT.read_text(encoding="utf-8"))
    checks = audit.validate_terminal_audit(payload)
    assert checks and all(checks.values())
    for condition in ("ideal", "degraded"):
        assert payload["eligible_track_f1_semantics"][condition]["f1"] is None
    acceptance = payload["corrective_full_benchmark_acceptance_rule"]
    assert acceptance["current_fixture_passes_target_gate"] is False
    assert acceptance["require_exactly_one_locked_test_evaluation"] is True
