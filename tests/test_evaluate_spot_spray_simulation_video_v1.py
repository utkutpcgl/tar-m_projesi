import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from scripts import evaluate_spot_spray_simulation_video_v1 as evaluator


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/benchmark/spot_spray_simulation_video_inference_v1.yaml"


def _write_image(path: Path, image: np.ndarray) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), image)
    return evaluator.sha256_file(path)


def _fixture_truth() -> tuple[np.ndarray, np.ndarray, list[dict]]:
    semantic = np.zeros((32, 32), dtype=np.uint8)
    track_mask = np.zeros((32, 32), dtype=np.uint16)
    semantic[2:11, 2:11] = 1
    track_mask[2:11, 2:11] = 1
    semantic[17:29, 17:29] = 2
    track_mask[17:29, 17:29] = 2
    tracks = [
        {
            "mask_id": 1,
            "track_id": "placeholder:crop",
            "class_name": "crop",
            "canopy_span_mm": 25.0,
            "visible_fraction": 1.0,
            "partial": False,
            "size_stratum": "small",
        },
        {
            "mask_id": 2,
            "track_id": "placeholder:weed",
            "class_name": "weed",
            "canopy_span_mm": 30.0,
            "visible_fraction": 1.0,
            "partial": False,
            "size_stratum": "small",
        },
    ]
    return semantic, track_mask, tracks


def _write_manifest(tmp_path: Path) -> Path:
    semantic, track_mask, track_rows = _fixture_truth()
    sequences = []
    for split in ("calibration", "test"):
        pair_id = f"{split}:scene_a"
        semantic_path = tmp_path / "truth" / split / "semantic.png"
        track_path = tmp_path / "truth" / split / "tracks.png"
        semantic_sha = _write_image(semantic_path, semantic)
        track_sha = _write_image(track_path, track_mask)
        tracks = []
        for row in track_rows:
            item = dict(row)
            item["track_id"] = f"{pair_id}:{item['class_name']}"
            tracks.append(item)
        for condition in ("ideal", "degraded"):
            frames = []
            for frame_index in range(3):
                image = np.full((32, 32, 3), 80, dtype=np.uint8)
                image[semantic == 1] = (20, 170, 20)
                image[semantic == 2] = (30, 210, 30)
                if condition == "degraded":
                    image = cv2.GaussianBlur(image, (3, 3), 0.8)
                image_path = (
                    tmp_path / "rgb" / split / condition / f"frame_{frame_index:04d}.png"
                )
                image_sha = _write_image(image_path, image)
                frames.append(
                    {
                        "frame_id": f"{condition}:{pair_id}:frame_{frame_index:04d}",
                        "frame_index": frame_index,
                        "image_path": str(image_path),
                        "image_sha256": image_sha,
                        "semantic_mask_path": str(semantic_path),
                        "semantic_mask_sha256": semantic_sha,
                        "track_mask_path": str(track_path),
                        "track_mask_sha256": track_sha,
                        "tracks": tracks,
                    }
                )
            sequences.append(
                {
                    "sequence_id": f"{condition}:{pair_id}",
                    "pair_id": pair_id,
                    "scene_id": "scene_a",
                    "split": split,
                    "condition": condition,
                    "frames": frames,
                }
            )
    manifest = {
        "schema_version": 1,
        "contract": evaluator.MANIFEST_CONTRACT,
        "dataset_id": "unit_fixture",
        "evidence_scope": "synthetic_diagnostic_only",
        "declared_splits": {"calibration": "calibration", "locked_test": "test"},
        "conditions": ["ideal", "degraded"],
        "provenance": {"fixture": True},
        "derivation": {"type": "unit_fixture"},
        "sequences": sequences,
    }
    path = tmp_path / "sequence_manifest.json"
    evaluator.write_json(path, manifest)
    return path


def _detection(class_name: str, mask: np.ndarray, confidence: float, track_id: str) -> evaluator.Detection:
    return evaluator.Detection(
        detection_id=0,
        class_name=class_name,
        confidence=confidence,
        mask=mask,
        bbox_xyxy=evaluator.mask_bbox(mask),
        centroid_xy=evaluator.mask_centroid(mask),
        action_point_xy=evaluator.maximum_interior_point(mask),
        predicted_track_id=track_id,
    )


def _perfect_prediction(sequence: evaluator.SequenceRecord) -> evaluator.PredictionSequence:
    frames = []
    for frame in sequence.frames:
        semantic = cv2.imread(str(frame.semantic_mask_path), cv2.IMREAD_UNCHANGED)
        frames.append(
            evaluator.PredictionFrame(
                frame=frame,
                detections=[
                    _detection("weed", semantic == 2, 0.9, "p0001"),
                    _detection("crop", semantic == 1, 0.9, "p0002"),
                ],
                inference_wall_ms=1.0,
                model_speed_ms={"inference": 0.5},
            )
        )
    return evaluator.PredictionSequence(sequence=sequence, frames=frames)


def test_frozen_config_is_checkpoint_bound_and_never_real_go() -> None:
    config = evaluator.load_config(CONFIG)
    assert config["checkpoint"]["sha256"] == (
        "3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100"
    )
    assert config["evidence_policy"]["synthetic_score_weight_in_real_go_decision"] == 0.0
    assert config["evidence_policy"]["chemical_fire_go_allowed"] is False
    assert config["calibration"]["test_access_forbidden"] is True
    assert config["calibration"]["shared_threshold_across_conditions"] is True
    assert config["descriptive_targets"]["ideal_minimum"] == pytest.approx(0.97)
    assert config["descriptive_targets"]["degraded_reference"] == pytest.approx(0.75)
    assert config["descriptive_targets"]["use_in_threshold_selection"] is False


def test_checkpoint_hash_gate_runs_before_model_factory(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"not the selected checkpoint")
    factory_called = False

    def factory(*args, **kwargs):
        nonlocal factory_called
        factory_called = True
        raise AssertionError("factory must not be called on a hash mismatch")

    with pytest.raises(evaluator.ContractError, match="SHA-256 mismatch"):
        evaluator.load_verified_model(checkpoint, "0" * 64, yolo_factory=factory)
    assert factory_called is False


def test_checkpoint_factory_is_called_after_valid_hash(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"fixture checkpoint")
    calls = []

    class FakeModel:
        names = {0: "weed", 1: "crop"}

    def factory(path: str, task: str):
        calls.append((path, task))
        return FakeModel()

    model, receipt = evaluator.load_verified_model(
        checkpoint,
        evaluator.sha256_file(checkpoint),
        yolo_factory=factory,
    )
    assert isinstance(model, FakeModel)
    assert calls == [(str(checkpoint.resolve()), "segment")]
    assert receipt["hash_verified_before_model_loader_invocation"] is True


def test_deterministic_degradation_is_seed_bound() -> None:
    config = evaluator.load_config(CONFIG)
    image = np.tile(np.arange(32, dtype=np.uint8), (32, 1))
    image = np.repeat(image[:, :, None], 3, axis=2)
    degradation = config["conditions"]["degraded"]
    first = evaluator.deterministic_degradation(image, degradation, seed=7)
    second = evaluator.deterministic_degradation(image, degradation, seed=7)
    third = evaluator.deterministic_degradation(image, degradation, seed=8)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, third)
    assert first.shape == image.shape


def test_manifest_verifies_hashes_pairs_and_split_isolation(tmp_path: Path) -> None:
    config = evaluator.load_config(CONFIG)
    manifest = _write_manifest(tmp_path)
    sequences, metadata = evaluator.load_sequence_manifest(manifest, config)
    assert len(sequences) == 4
    assert metadata["matched_pair_count"] == 2
    assert metadata["ground_truth_identical_within_pairs"] is True
    assert metadata["calibration_test_pair_ids_disjoint"] is True
    assert metadata["all_consumed_files_sha256_verified"] is True


def test_manifest_hash_tamper_fails_closed(tmp_path: Path) -> None:
    config = evaluator.load_config(CONFIG)
    manifest = _write_manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    image = Path(payload["sequences"][0]["frames"][0]["image_path"])
    image.write_bytes(image.read_bytes() + b"tamper")
    with pytest.raises(evaluator.ContractError, match="SHA-256 mismatch"):
        evaluator.load_sequence_manifest(manifest, config)


def test_manifest_rejects_condition_specific_ground_truth(tmp_path: Path) -> None:
    config = evaluator.load_config(CONFIG)
    manifest = _write_manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    degraded = next(
        row
        for row in payload["sequences"]
        if row["split"] == "calibration" and row["condition"] == "degraded"
    )
    alternate = np.zeros((32, 32), dtype=np.uint8)
    alternate[2:11, 2:11] = 1
    alternate[17:29, 17:29] = 2
    alternate[0, 0] = 2
    alternate_path = tmp_path / "truth" / "alternate_semantic.png"
    alternate_sha = _write_image(alternate_path, alternate)
    for frame in degraded["frames"]:
        frame["semantic_mask_path"] = str(alternate_path)
        frame["semantic_mask_sha256"] = alternate_sha
    evaluator.write_json(manifest, payload)
    with pytest.raises(evaluator.ContractError, match="ground truth differs"):
        evaluator.load_sequence_manifest(manifest, config)


def test_access_ledger_forbids_early_or_repeated_test_access() -> None:
    ledger = evaluator.AccessLedger("calibration", "test")
    with pytest.raises(evaluator.ContractError, match="before calibration"):
        ledger.record_inference("test", "test:sequence")
    ledger.record_inference("calibration", "calibration:sequence")
    ledger.freeze_threshold(0.5)
    ledger.record_inference("test", "test:sequence")
    ledger.begin_locked_test_evaluation()
    with pytest.raises(evaluator.ContractError, match="exactly once"):
        ledger.begin_locked_test_evaluation()
    ledger.finish()
    assert ledger.receipt()["locked_test_metric_evaluations"] == 1
    assert ledger.receipt()["test_accessed_during_threshold_selection"] is False


def test_mask_tracker_preserves_identity_across_three_frames(tmp_path: Path) -> None:
    config = evaluator.load_config(CONFIG)
    sequences, _ = evaluator.load_sequence_manifest(_write_manifest(tmp_path), config)
    sequence = next(row for row in sequences if row.sequence_id == "ideal:calibration:scene_a")
    prediction = _perfect_prediction(sequence)
    for frame in prediction.frames:
        for detection in frame.detections:
            detection.predicted_track_id = None
    evaluator.assign_predicted_tracks(prediction.frames, config["tracking"])
    weed_ids = {
        detection.predicted_track_id
        for frame in prediction.frames
        for detection in frame.detections
        if detection.class_name == "weed"
    }
    crop_ids = {
        detection.predicted_track_id
        for frame in prediction.frames
        for detection in frame.detections
        if detection.class_name == "crop"
    }
    assert len(weed_ids) == 1
    assert len(crop_ids) == 1
    assert weed_ids.isdisjoint(crop_ids)


def test_perfect_three_frame_track_fires_once_and_scores_all_levels(tmp_path: Path) -> None:
    config = evaluator.load_config(CONFIG)
    sequences, _ = evaluator.load_sequence_manifest(_write_manifest(tmp_path), config)
    sequence = next(row for row in sequences if row.sequence_id == "ideal:test:scene_a")
    counts, events, audit = evaluator.evaluate_prediction_sequence(
        _perfect_prediction(sequence), config, 0.5
    )
    summary = evaluator.summary_from_counts(counts, config)
    assert summary["pixel"]["weed"]["f1"] == pytest.approx(1.0)
    assert summary["instance"]["weed"]["f1"] == pytest.approx(1.0)
    assert summary["eligible_weed_track"]["f1"] == pytest.approx(1.0)
    assert summary["action"]["f1"] == pytest.approx(1.0)
    assert summary["action"]["crop_hit_rate"] == 0.0
    assert summary["action"]["duplicate_fire_rate"] == 0.0
    assert len(events) == 1
    assert events[0].frame_index == 2
    assert events[0].confirmations_in_window == 3
    assert events[0].disposition == "eligible_weed_true_positive"
    assert audit["track_matches"][0]["iou"] == pytest.approx(1.0)
    assert audit["predicted_track_diagnostics"][0]["disposition"] == (
        "matched_eligible_gt_track"
    )
    eligible_diagnostic = audit["eligible_gt_track_diagnostics"][0]
    assert eligible_diagnostic["disposition"] == "matched"
    assert eligible_diagnostic["top_predicted_candidates"][0][
        "spatiotemporal_mask_iou"
    ] == pytest.approx(1.0)


def test_track_audit_explains_frozen_iou_rejection(tmp_path: Path) -> None:
    config = evaluator.load_config(CONFIG)
    sequences, _ = evaluator.load_sequence_manifest(_write_manifest(tmp_path), config)
    sequence = next(row for row in sequences if row.sequence_id == "ideal:test:scene_a")
    frames = []
    for frame in sequence.frames:
        semantic = cv2.imread(str(frame.semantic_mask_path), cv2.IMREAD_UNCHANGED)
        small_weed = np.zeros_like(semantic, dtype=bool)
        small_weed[18:22, 18:22] = True
        frames.append(
            evaluator.PredictionFrame(
                frame=frame,
                detections=[_detection("weed", small_weed, 0.9, "p0001")],
                inference_wall_ms=1.0,
                model_speed_ms={},
            )
        )
    prediction = evaluator.PredictionSequence(sequence=sequence, frames=frames)
    counts, _, audit = evaluator.evaluate_prediction_sequence(prediction, config, 0.5)
    assert counts["eligible_weed_track"] == {
        "tp": 0,
        "fp": 1,
        "fn": 1,
        "ignored_ineligible_predictions": 0,
    }
    predicted = audit["predicted_track_diagnostics"][0]
    assert predicted["rejection_reason"] == "best_eligible_gt_iou_below_frozen_threshold"
    assert predicted["top_eligible_candidates"][0]["spatiotemporal_mask_iou"] < 0.5
    eligible = audit["eligible_gt_track_diagnostics"][0]
    assert eligible["rejection_reason"] == "best_predicted_iou_below_frozen_threshold"
    assert audit["eligible_track_metric_definition"]["minimum_iou"] == pytest.approx(0.5)


def test_duplicate_predicted_tracks_expose_duplicate_fire(tmp_path: Path) -> None:
    config = evaluator.load_config(CONFIG)
    sequences, _ = evaluator.load_sequence_manifest(_write_manifest(tmp_path), config)
    sequence = next(row for row in sequences if row.sequence_id == "ideal:test:scene_a")
    prediction = _perfect_prediction(sequence)
    for frame in prediction.frames:
        weed = next(item for item in frame.detections if item.class_name == "weed")
        frame.detections.append(_detection("weed", weed.mask.copy(), 0.85, "p0099"))
    counts, events, _ = evaluator.evaluate_prediction_sequence(prediction, config, 0.5)
    summary = evaluator.summary_from_counts(counts, config)
    assert len(events) == 2
    assert [item.disposition for item in events] == [
        "eligible_weed_true_positive",
        "duplicate_fire_false_positive",
    ]
    assert summary["action"]["duplicate_fire_events"] == 1
    assert summary["action"]["duplicate_fire_rate"] == pytest.approx(0.5)


def test_crop_collision_has_precedence_at_action_point(tmp_path: Path) -> None:
    config = evaluator.load_config(CONFIG)
    sequences, _ = evaluator.load_sequence_manifest(_write_manifest(tmp_path), config)
    sequence = next(row for row in sequences if row.sequence_id == "ideal:test:scene_a")
    frames = []
    for frame in sequence.frames:
        semantic = cv2.imread(str(frame.semantic_mask_path), cv2.IMREAD_UNCHANGED)
        frames.append(
            evaluator.PredictionFrame(
                frame=frame,
                detections=[_detection("weed", semantic == 1, 0.9, "p0001")],
                inference_wall_ms=1.0,
                model_speed_ms={},
            )
        )
    prediction = evaluator.PredictionSequence(sequence=sequence, frames=frames)
    counts, events, _ = evaluator.evaluate_prediction_sequence(prediction, config, 0.5)
    summary = evaluator.summary_from_counts(counts, config)
    assert len(events) == 1
    assert events[0].disposition == "crop_hit_false_positive"
    assert summary["action"]["crop_hit_rate"] == pytest.approx(1.0)
    assert summary["action"]["false_negative"] == 1


def test_threshold_selection_uses_calibration_metrics_and_deterministic_fallback() -> None:
    config = evaluator.load_config(CONFIG)
    base = evaluator._empty_counts()
    base["eligible_weed_track"].update({"tp": 7, "fp": 1, "fn": 3})
    base["action"].update({"tp": 7, "fp": 0, "fn": 3, "attempted_fire_events": 7})
    stronger = evaluator._empty_counts()
    stronger["eligible_weed_track"].update({"tp": 8, "fp": 2, "fn": 2})
    stronger["action"].update({"tp": 8, "fp": 0, "fn": 2, "attempted_fire_events": 8})
    curve = [
        {"threshold": 0.4, "metrics": evaluator.summary_from_counts(base, config)},
        {"threshold": 0.5, "metrics": evaluator.summary_from_counts(stronger, config)},
    ]
    selection = evaluator.select_calibration_threshold(curve, config)
    assert selection["status"] == "no_calibration_safety_feasible_threshold_diagnostic_fallback"
    assert selection["threshold"] == pytest.approx(0.5)
    assert selection["test_accessed"] is False


def test_descriptive_target_assessment_is_explicit_and_not_a_tuning_input() -> None:
    config = evaluator.load_config(CONFIG)
    ideal_counts = evaluator._empty_counts()
    ideal_counts["eligible_weed_track"].update({"tp": 97, "fp": 3, "fn": 3})
    degraded_counts = evaluator._empty_counts()
    degraded_counts["eligible_weed_track"].update({"tp": 3, "fp": 1, "fn": 1})
    results = {
        "ideal": {"metrics": evaluator.summary_from_counts(ideal_counts, config)},
        "degraded": {
            "metrics": evaluator.summary_from_counts(degraded_counts, config)
        },
    }
    assessment = evaluator.assess_descriptive_targets(results, config)
    assert assessment["ideal"]["observed"] == pytest.approx(0.97)
    assert assessment["ideal"]["reaches_minimum"] is True
    assert assessment["degraded"]["observed"] == pytest.approx(0.75)
    assert assessment["degraded"]["near_range_inclusive"] == pytest.approx([0.70, 0.80])
    assert assessment["degraded"]["within_near_range"] is True
    assert assessment["conclusion"] == "both_descriptive_targets_met"
    assert assessment["used_in_threshold_selection"] is False
    assert assessment["used_in_model_or_degradation_tuning"] is False


def test_bootstrap_interval_is_deterministic(tmp_path: Path) -> None:
    config = evaluator.load_config(CONFIG)
    first = evaluator._empty_counts()
    first["eligible_weed_track"].update({"tp": 8, "fp": 1, "fn": 2})
    second = evaluator._empty_counts()
    second["eligible_weed_track"].update({"tp": 5, "fp": 2, "fn": 5})
    kwargs = dict(
        counts_by_unit={"a": first, "b": second},
        metric_key="track_f1",
        resamples=100,
        seed=91,
        confidence_level=float(config["uncertainty"]["confidence_level"]),
    )
    left = evaluator.bootstrap_metric_interval(**kwargs)
    right = evaluator.bootstrap_metric_interval(**kwargs)
    assert left == right
    assert left["unit_count"] == 2
    assert 0.0 <= left["lower"] <= left["upper"] <= 1.0


def test_overlay_video_is_written_and_read_back(tmp_path: Path) -> None:
    config = evaluator.load_config(CONFIG)
    sequences, _ = evaluator.load_sequence_manifest(_write_manifest(tmp_path), config)
    by_condition = {}
    results = {}
    for condition in ("ideal", "degraded"):
        sequence = next(
            row for row in sequences if row.sequence_id == f"{condition}:test:scene_a"
        )
        prediction = _perfect_prediction(sequence)
        by_condition[condition] = {sequence.sequence_id: prediction}
        evaluation = evaluator.evaluate_prediction_set(
            by_condition[condition], config, 0.5, include_uncertainty=False
        )
        results[condition] = evaluation
    receipt = evaluator.render_overlay_videos(
        by_condition,
        results,
        0.5,
        config,
        tmp_path / "videos",
    )
    assert receipt["enabled"] is True
    for condition in ("ideal", "degraded"):
        assert receipt["conditions"][condition]["frames_decoded"] == 3
        assert receipt["conditions"][condition]["readback_verified"] is True
