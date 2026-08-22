from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest
import yaml

from scripts import evaluate_spot_spray_ego_motion_tracker_v1 as tracker
from scripts import evaluate_spot_spray_target_rig_action_v1 as action_evaluator


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/benchmark/spot_spray_ego_motion_tracker_v1.yaml"
ACTION_CONFIG = ROOT / "configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml"
GSD_MM_PER_PX = 479.0 / 2048.0
ORIGIN_PX = (1024.5, 1024.5)
HOMOGRAPHY_SHA = "a" * 64
ENCODER_SHA = "b" * 64


@pytest.fixture(scope="module")
def contract() -> tracker.TrackerContract:
    return tracker.load_tracker_contract(CONFIG)


def _homography_payload(contract: tracker.TrackerContract) -> dict:
    origin_u, origin_v = ORIGIN_PX
    matrix = [
        [GSD_MM_PER_PX, 0.0, -GSD_MM_PER_PX * origin_u],
        [0.0, GSD_MM_PER_PX, -GSD_MM_PER_PX * origin_v],
        [0.0, 0.0, 1.0],
    ]

    def ground(pixel: tuple[float, float]) -> list[float]:
        return [
            GSD_MM_PER_PX * (pixel[0] - origin_u),
            GSD_MM_PER_PX * (pixel[1] - origin_v),
        ]

    return {
        "schema_version": 1,
        "contract_id": "neutral_planar_fiducial_homography_v1",
        "evidence_scope": "synthetic_calibration_mechanics_only",
        "receipt_sha256": HOMOGRAPHY_SHA,
        "direction": tracker.HOMOGRAPHY_DIRECTION,
        "pixel_space_id": contract.pixel_space_id,
        "preprocessing_sha256": contract.preprocessing_sha256,
        "matrix_i2g": matrix,
        "support_polygon_px": [
            [64.0, 64.0],
            [1984.0, 64.0],
            [1984.0, 1984.0],
            [64.0, 1984.0],
        ],
        "residual_p95_mm": 1.0,
        "residual_max_mm": 2.0,
        "daily_registration_drift_mm": 2.0,
        "orientation_witnesses": [
            {
                "role": "origin",
                "pixel_xy": list(ORIGIN_PX),
                "ground_xy_mm": ground(ORIGIN_PX),
            },
            {
                "role": "forward",
                "pixel_xy": [1124.5, 1024.5],
                "ground_xy_mm": ground((1124.5, 1024.5)),
            },
            {
                "role": "right",
                "pixel_xy": [1024.5, 1124.5],
                "ground_xy_mm": ground((1024.5, 1124.5)),
            },
        ],
    }


def _homography(contract: tracker.TrackerContract) -> tracker.HomographyBinding:
    return tracker.homography_binding_from_mapping(_homography_payload(contract), contract)


def _encoder_payload() -> dict:
    return {
        "schema_version": 1,
        "contract_id": "neutral_encoder_acceptance_fixture_v1",
        "evidence_scope": "synthetic_calibration_mechanics_only",
        "receipt_sha256": ENCODER_SHA,
        "same_hardware_event": True,
        "positive_axis": "product_ground_positive_x",
        "resolution_um_per_count": 1000,
        "scale_error_um_per_m": 1000,
        "trigger_encoder_delta_limit_us": 250,
        "stale_after_us": 5000,
    }


def _encoder(contract: tracker.TrackerContract) -> tracker.EncoderBinding:
    return tracker.encoder_binding_from_mapping(_encoder_payload(), contract)


def _timestamp_ns(frame_index: int) -> int:
    return round(frame_index * 1_000_000_000 / 15)


def _telemetry(
    frame_index: int,
    encoder_um: int | None,
    *,
    timestamp_ns: int | None = None,
    latch_delta_us: int | None = 0,
    encoder_age_us: int | None = 0,
    homography_id: str = HOMOGRAPHY_SHA,
) -> tracker.FrameTelemetry:
    return tracker.FrameTelemetry(
        frame_index=frame_index,
        timestamp_ns=_timestamp_ns(frame_index) if timestamp_ns is None else timestamp_ns,
        encoder_position_um=encoder_um,
        trigger_encoder_delta_us=latch_delta_us,
        encoder_age_us=encoder_age_us,
        homography_binding_id=homography_id,
    )


def _column_for_world_x(world_x_mm: float, encoder_um: int) -> int:
    local_x_mm = world_x_mm - encoder_um / 1000.0
    centre_u = ORIGIN_PX[0] + local_x_mm / GSD_MM_PER_PX
    return int(round(centre_u - 0.5))


def _detection_at(
    column: int,
    *,
    row: int = 1024,
    class_name: str = "weed",
    confidence: float = 0.9,
    action_point: tuple[float, float] | None = None,
) -> tracker.DetectionInput:
    mask = np.zeros((2048, 2048), dtype=bool)
    mask[row, column] = True
    centre = ((column + 0.5) / 2048.0, (row + 0.5) / 2048.0)
    half = 0.01
    polygon = (
        (max(0.0, centre[0] - half), max(0.0, centre[1] - half)),
        (min(1.0, centre[0] + half), max(0.0, centre[1] - half)),
        (min(1.0, centre[0] + half), min(1.0, centre[1] + half)),
        (max(0.0, centre[0] - half), min(1.0, centre[1] + half)),
    )
    return tracker.DetectionInput(
        mask=mask,
        class_name=class_name,
        confidence=confidence,
        polygon=polygon,
        action_point=centre if action_point is None else action_point,
    )


def _run_single_object(
    contract: tracker.TrackerContract,
    raw_classes: tuple[str, ...],
    confidences: tuple[float, ...],
    *,
    speed_um_per_frame: int = 66_667,
) -> dict:
    instance = tracker.EgoMotionTracker(contract)
    instance.start_sequence(_homography(contract), _encoder(contract))
    for frame_index, (class_name, confidence) in enumerate(zip(raw_classes, confidences)):
        encoder_um = frame_index * speed_um_per_frame
        column = _column_for_world_x(80.0, encoder_um)
        instance.process_frame(
            f"opaque-{frame_index}",
            _telemetry(frame_index, encoder_um),
            [_detection_at(column, class_name=class_name, confidence=confidence)],
        )
    return instance.finish_sequence()


def _candidate_ids(result: dict) -> list[list[str]]:
    return [
        [candidate["predicted_track_id"] for candidate in frame["candidates"]]
        for frame in result["prediction_frames"]
    ]


def test_frozen_contract_source_locks_and_gate_vectors(contract: tracker.TrackerContract) -> None:
    assert contract.pixel_space_id == "native_2048_square_zero_based_pixel_centres_v1"
    assert contract.maximum_frame_index_delta == 2
    assert contract.hard_gate_ceiling_um == 45_000
    assert contract.dynamic_gate_um(33_334) == 18_000
    assert contract.dynamic_gate_um(66_667) == 27_000
    assert contract.dynamic_gate_um(133_334) == 45_000
    assert {row.name for row in contract.source_locks} == {
        "adaptive_plan",
        "capture_optimization",
        "fairness_audit",
        "frozen_action_contract",
        "frozen_action_evaluator",
        "product_architecture",
        "rig_acceptance",
    }
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert raw["claim_boundary"]["locked_test_access_allowed"] is False
    assert raw["claim_boundary"]["model_loading_allowed"] is False
    assert raw["association"]["raw_pixel_fallback_allowed"] is False


def test_positive_encoder_sign_removes_raw_160_px_ceiling(
    contract: tracker.TrackerContract,
) -> None:
    homography = _homography(contract)
    frame0 = _detection_at(_column_for_world_x(80.0, 0))
    frame1 = _detection_at(_column_for_world_x(80.0, 66_667))
    raw0 = tracker.prepare_detection(frame0, homography, contract, 0)
    raw1 = tracker.prepare_detection(frame1, homography, contract, 66_667)
    raw_pixel_displacement = abs(raw1.centroid_px[0] - raw0.centroid_px[0])
    compensated_residual_um = math.isqrt(
        (raw1.anchor_um[0] - raw0.anchor_um[0]) ** 2
        + (raw1.anchor_um[1] - raw0.anchor_um[1]) ** 2
    )
    local0 = tracker.project_pixel_to_ground_mm(
        homography, raw0.centroid_px, contract.projection_denominator_minimum
    )
    local1 = tracker.project_pixel_to_ground_mm(
        homography, raw1.centroid_px, contract.projection_denominator_minimum
    )
    wrong_sign_residual_mm = abs((local1[0] - 66.667) - local0[0])
    assert raw_pixel_displacement > 160.0
    assert compensated_residual_um <= contract.dynamic_gate_um(66_667)
    assert wrong_sign_residual_mm * 1000 > contract.dynamic_gate_um(66_667)

    result = _run_single_object(contract, ("weed", "weed"), (0.9, 0.8))
    assert _candidate_ids(result) == [["trk_000001"], ["trk_000001"]]
    matched = [
        row for row in result["diagnostic_sidecar"] if row["association_state"] == "matched"
    ]
    assert len(matched) == 1
    assert matched[0]["gate_um"] == 27_000
    assert matched[0]["residual_squared_um2"] <= 27_000**2


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda row: row.update(direction="ground_to_image"), "direction"),
        (lambda row: row.update(matrix_i2g=[[1.0, 0.0, 0.0]] * 3), "singular"),
        (lambda row: row.update(residual_p95_mm=1.001), "p95"),
    ],
)
def test_homography_validation_fails_closed(
    contract: tracker.TrackerContract, mutation, message: str
) -> None:
    payload = _homography_payload(contract)
    mutation(payload)
    with pytest.raises(tracker.TrackerContractError, match=message) as captured:
        tracker.homography_binding_from_mapping(payload, contract)
    assert captured.value.code == "INVALID_HOMOGRAPHY_BINDING"


def test_axis_swapped_homography_fails_orientation_witnesses(
    contract: tracker.TrackerContract,
) -> None:
    payload = _homography_payload(contract)
    payload["matrix_i2g"] = [
        [0.0, GSD_MM_PER_PX, -GSD_MM_PER_PX * ORIGIN_PX[1]],
        [GSD_MM_PER_PX, 0.0, -GSD_MM_PER_PX * ORIGIN_PX[0]],
        [0.0, 0.0, 1.0],
    ]
    with pytest.raises(tracker.TrackerContractError, match="orientation witness"):
        tracker.homography_binding_from_mapping(payload, contract)


@pytest.mark.parametrize(
    "field,value",
    [
        ("same_hardware_event", False),
        ("positive_axis", "negative_x"),
        ("resolution_um_per_count", 1001),
        ("scale_error_um_per_m", 1001),
        ("trigger_encoder_delta_limit_us", 251),
        ("stale_after_us", 5001),
    ],
)
def test_encoder_binding_limits_fail_before_first_frame(
    contract: tracker.TrackerContract, field: str, value
) -> None:
    payload = _encoder_payload()
    payload[field] = value
    with pytest.raises(tracker.TrackerContractError) as captured:
        tracker.encoder_binding_from_mapping(payload, contract)
    assert captured.value.code == "INVALID_ENCODER_BINDING"


def test_exact_global_assignment_beats_greedy_and_has_canonical_ties() -> None:
    greedy_failure = {(0, 0): 1, (0, 1): 4, (1, 0): 1}
    assert tracker.deterministic_global_assignment(2, 2, greedy_failure, 45_000) == (
        (0, 1),
        (1, 0),
    )
    all_tied = {(1, 1): 0, (0, 1): 0, (1, 0): 0, (0, 0): 0}
    assert tracker.deterministic_global_assignment(2, 2, all_tied, 45_000) == (
        (0, 0),
        (1, 1),
    )
    assert tracker.deterministic_global_assignment(
        2, 2, dict(reversed(list(all_tied.items()))), 45_000
    ) == ((0, 0), (1, 1))


def test_association_is_class_confidence_and_action_point_blind(
    contract: tracker.TrackerContract,
) -> None:
    conflicted = _run_single_object(
        contract,
        ("weed", "crop", "partial_unknown"),
        (0.91, 0.77, 0.66),
    )
    relabelled = _run_single_object(
        contract,
        ("crop", "crop", "crop"),
        (0.11, 0.22, 0.33),
    )
    assert _candidate_ids(conflicted) == _candidate_ids(relabelled) == [
        ["trk_000001"],
        ["trk_000001"],
        ["trk_000001"],
    ]
    geometry_trace = lambda result: [
        (
            row["association_state"],
            row["residual_squared_um2"],
            row["gate_um"],
            row["frame_delta"],
            row["encoder_delta_um"],
        )
        for row in result["diagnostic_sidecar"]
    ]
    assert geometry_trace(conflicted) == geometry_trace(relabelled)
    candidates = [frame["candidates"][0] for frame in conflicted["prediction_frames"]]
    assert [row["class_name"] for row in candidates] == ["weed", "weed", "weed"]
    assert [row["confidence"] for row in candidates] == [0.91, 0.0, 0.0]
    assert all("action_point" in row for row in candidates)
    assert [row["raw_label_conflict"] for row in conflicted["diagnostic_sidecar"]] == [
        False,
        True,
        True,
    ]


def test_frame_delta_two_bridges_one_missing_detection_but_delta_three_expires(
    contract: tracker.TrackerContract,
) -> None:
    instance = tracker.EgoMotionTracker(contract)
    instance.start_sequence(_homography(contract), _encoder(contract))
    instance.process_frame(
        "f0",
        _telemetry(0, 0),
        [_detection_at(_column_for_world_x(60.0, 0))],
    )
    instance.process_frame("f1", _telemetry(1, 33_334), [])
    instance.process_frame(
        "f2",
        _telemetry(2, 66_667),
        [_detection_at(_column_for_world_x(60.0, 66_667))],
    )
    bridged = instance.finish_sequence()
    assert _candidate_ids(bridged) == [["trk_000001"], [], ["trk_000001"]]

    instance.reset_sequence()
    instance.start_sequence(_homography(contract), _encoder(contract))
    instance.process_frame(
        "g0",
        _telemetry(0, 0),
        [_detection_at(_column_for_world_x(60.0, 0))],
    )
    instance.process_frame("g1", _telemetry(1, 33_334), [])
    instance.process_frame("g2", _telemetry(2, 66_667), [])
    instance.process_frame(
        "g3",
        _telemetry(3, 100_000),
        [_detection_at(_column_for_world_x(60.0, 100_000))],
    )
    expired = instance.finish_sequence()
    assert _candidate_ids(expired) == [["trk_000001"], [], [], ["trk_000002"]]
    assert any(
        row["association_state"] == "expired_before_association"
        for row in expired["diagnostic_sidecar"]
    )


@pytest.mark.parametrize(
    ("fault_telemetry", "expected_code"),
    [
        (_telemetry(1, None), "MISSING_ENCODER"),
        (_telemetry(1, 33_334, encoder_age_us=5001), "STALE_ENCODER"),
        (_telemetry(1, 33_334, latch_delta_us=251), "UNSYNCHRONIZED_ENCODER"),
        (_telemetry(1, -1), "REVERSE_OR_AMBIGUOUS_DIRECTION"),
        (_telemetry(1, 33_334, timestamp_ns=0), "INVALID_TIMESTAMP"),
        (_telemetry(2, 33_334), "INVALID_FRAME_ORDER"),
        (_telemetry(1, 33_334, homography_id="c" * 64), "HOMOGRAPHY_BINDING_DRIFT"),
        (_telemetry(1, 70_000), "TRAVEL_OUTSIDE_PROOF_ENVELOPE"),
    ],
)
def test_mid_video_fault_discards_all_publishable_output(
    contract: tracker.TrackerContract,
    fault_telemetry: tracker.FrameTelemetry,
    expected_code: str,
) -> None:
    instance = tracker.EgoMotionTracker(contract)
    instance.start_sequence(_homography(contract), _encoder(contract))
    instance.process_frame(
        "valid-before-fault",
        _telemetry(0, 0),
        [_detection_at(_column_for_world_x(40.0, 0))],
    )
    with pytest.raises(tracker.TrackerContractError) as captured:
        instance.process_frame("fault", fault_telemetry, [])
    assert captured.value.code == expected_code
    assert instance.state == tracker.STATE_INVALID
    assert instance.failure_receipt() == {
        "contract_id": tracker.CONTRACT_ID,
        "status": tracker.STATE_INVALID,
        "failure_code": expected_code,
        "reason": str(captured.value),
        "publishable_prediction": False,
        "partial_prediction_discarded": True,
        "field_go": False,
        "product_go": False,
        "chemical_fire_allowed": False,
    }
    with pytest.raises(tracker.TrackerContractError, match="ACTIVE"):
        instance.finish_sequence()


def test_ids_are_input_order_deterministic_and_never_leak_across_videos(
    contract: tracker.TrackerContract,
) -> None:
    def run(order: tuple[float, float]) -> dict:
        instance = tracker.EgoMotionTracker(contract)
        instance.start_sequence(_homography(contract), _encoder(contract))
        detections = [
            _detection_at(_column_for_world_x(world_x, 0), class_name="crop")
            for world_x in order
        ]
        instance.process_frame("opaque", _telemetry(0, 0), detections)
        return instance.finish_sequence()

    forward = run((-40.0, 50.0))
    reverse = run((50.0, -40.0))
    assert tracker.canonical_json_bytes(forward) == tracker.canonical_json_bytes(reverse)
    assert _candidate_ids(forward) == [["trk_000001", "trk_000002"]]

    instance = tracker.EgoMotionTracker(contract)
    instance.start_sequence(_homography(contract), _encoder(contract))
    instance.process_frame(
        "video-a-frame",
        _telemetry(0, 0),
        [_detection_at(_column_for_world_x(10.0, 0))],
    )
    first = instance.finish_sequence()
    with pytest.raises(tracker.TrackerContractError):
        instance.process_frame("illegal", _telemetry(1, 1), [])
    instance.reset_sequence()
    instance.start_sequence(_homography(contract), _encoder(contract))
    instance.process_frame(
        "video-b-frame",
        _telemetry(0, 500_000),
        [_detection_at(_column_for_world_x(10.0, 0))],
    )
    second = instance.finish_sequence()
    assert _candidate_ids(first) == _candidate_ids(second) == [["trk_000001"]]


def test_forbidden_identity_fields_are_rejected_before_association(
    contract: tracker.TrackerContract,
) -> None:
    detection = {
        "mask": np.zeros((2048, 2048), dtype=bool),
        "class_name": "weed",
        "confidence": 0.9,
        "polygon": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]],
        "action_point": [0.15, 0.15],
        "pair_id": "forbidden",
    }
    with pytest.raises(tracker.TrackerContractError) as captured:
        tracker.detection_from_mapping(detection, contract)
    assert captured.value.code == "FORBIDDEN_ASSOCIATION_INPUT"

    frame = {
        "frame_id": "opaque",
        "frame_index": 0,
        "timestamp_ns": 0,
        "encoder_position_um": 0,
        "trigger_encoder_delta_us": 0,
        "encoder_age_us": 0,
        "homography_binding_id": HOMOGRAPHY_SHA,
        "detections": [],
        "gt_track_id": "forbidden",
    }
    with pytest.raises(tracker.TrackerContractError) as captured:
        tracker.telemetry_and_detections_from_mapping(frame, contract)
    assert captured.value.code == "FORBIDDEN_ASSOCIATION_INPUT"


def test_evaluator_candidate_schema_accepts_stable_tracker_output(
    contract: tracker.TrackerContract,
) -> None:
    result = _run_single_object(contract, ("weed", "crop"), (0.9, 0.8))
    config = yaml.safe_load(ACTION_CONFIG.read_text(encoding="utf-8"))
    parsed = [
        action_evaluator._parse_candidate(frame["candidates"][0], "candidate", config)
        for frame in result["prediction_frames"]
    ]
    assert [candidate.predicted_track_id for candidate in parsed] == [
        "trk_000001",
        "trk_000001",
    ]
    assert [candidate.class_name for candidate in parsed] == ["weed", "weed"]
    assert [candidate.confidence for candidate in parsed] == [0.9, 0.0]
    assert all(candidate.action_point is not None for candidate in parsed)
    assert all(
        set(frame["candidates"][0])
        == {"predicted_track_id", "class_name", "confidence", "polygon", "action_point"}
        for frame in result["prediction_frames"]
    )


def test_canonical_mask_hash_binds_shape_and_bits() -> None:
    first = np.zeros((4, 8), dtype=bool)
    first[1, 3] = True
    second = first.copy()
    second[1, 4] = True
    digest = tracker.canonical_mask_sha256(first)
    assert digest == tracker.canonical_mask_sha256(first.copy())
    assert digest != tracker.canonical_mask_sha256(second)
    expected = hashlib.sha256(
        (4).to_bytes(4, "big")
        + (8).to_bytes(4, "big")
        + np.packbits(first.reshape(-1).astype(np.uint8), bitorder="big").tobytes()
    ).hexdigest()
    assert digest == expected


def _audit_generated_payloads(
    contract: tracker.TrackerContract, payloads: dict[str, bytes]
) -> dict:
    config_raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    configured_files = config_raw["calibration_fixture_lock"]["files"]
    input_locks = {
        name: {
            "path": configured_files[name]["path"],
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        for name, payload in payloads.items()
    }
    implementation_path = ROOT / "scripts/evaluate_spot_spray_ego_motion_tracker_v1.py"
    return tracker.audit_calibration_payloads(
        contract,
        payloads,
        config_path=CONFIG,
        config_sha256=tracker.sha256_file(CONFIG),
        implementation_path=implementation_path,
        implementation_sha256=tracker.sha256_file(implementation_path),
        input_locks=input_locks,
    )


def _replace_generation_hash(payloads: dict[str, bytes], name: str) -> None:
    generation = json.loads(payloads["generation_receipt"])
    generation["files"][name] = hashlib.sha256(payloads[name]).hexdigest()
    payloads["generation_receipt"] = tracker.canonical_json_bytes(generation)


def test_neutral_two_speed_calibration_is_target_free_and_removes_raw_ceiling(
    contract: tracker.TrackerContract,
) -> None:
    first = tracker.build_neutral_calibration_fixture_payloads(contract)
    second = tracker.build_neutral_calibration_fixture_payloads(contract)
    assert first == second
    candidate = _audit_generated_payloads(contract, first)
    assert candidate["status"] == "TRACKER_CALIBRATION_MECHANICS_PASS"
    assert candidate["evidence_scope"] == tracker.NEUTRAL_FIXTURE_SCOPE
    assert candidate["raw_pixel_p95_1m_s"] > 160.0
    assert candidate["positive_sign_gate_violation_count"] == 0
    assert candidate["wrong_sign_gate_violation_count"] > 0
    assert candidate["maximum_dynamic_gate_um"] == 45_000
    assert candidate["speed_summaries"]["speed_0p5_m_s"]["frame_count"] == 30
    assert candidate["speed_summaries"]["speed_1p0_m_s"]["frame_count"] == 30
    assert candidate["claim_boundary"] == {
        "installed_rig_homography_validated": False,
        "target_performance_claimed": False,
        "ready_for_parent_integration_after_release_seal": True,
        "parent_runtime_homography_binding_required": True,
    }
    assert all(value is False for value in candidate["forbidden_access_assertions"].values())


def test_calibration_scope_rejects_forbidden_identity_before_metrics(
    contract: tracker.TrackerContract,
) -> None:
    payloads = tracker.build_neutral_calibration_fixture_payloads(contract)
    timing_rows = [json.loads(line) for line in payloads["frame_timing"].splitlines()]
    timing_rows[0]["pair_id"] = "forbidden"
    payloads["frame_timing"] = tracker.canonical_jsonl_bytes(timing_rows)
    _replace_generation_hash(payloads, "frame_timing")
    with pytest.raises(tracker.TrackerContractError) as captured:
        _audit_generated_payloads(contract, payloads)
    assert captured.value.code == "TRACKER_INVALID_SCOPE_VIOLATION"


def test_calibration_generation_receipt_detects_source_drift(
    contract: tracker.TrackerContract,
) -> None:
    payloads = tracker.build_neutral_calibration_fixture_payloads(contract)
    payloads["calibration_witnesses"] += b"\n"
    with pytest.raises(tracker.TrackerContractError) as captured:
        _audit_generated_payloads(contract, payloads)
    assert captured.value.code == "TRACKER_NONDETERMINISTIC_OR_SOURCE_DRIFT"


def test_calibration_positive_sign_failure_does_not_widen_gate(
    contract: tracker.TrackerContract,
) -> None:
    payloads = tracker.build_neutral_calibration_fixture_payloads(contract)
    witness_rows = [
        json.loads(line) for line in payloads["calibration_witnesses"].splitlines()
    ]
    changed = False
    for row in witness_rows:
        if (
            row["sequence_id"] == "neutral_linear_1000000um_s_v1"
            and row["frame_index"] == 1
            and 700.0 < row["pixel_xy"][0] < 1400.0
        ):
            row["pixel_xy"][0] += 300.0
            changed = True
            break
    assert changed
    payloads["calibration_witnesses"] = tracker.canonical_jsonl_bytes(witness_rows)
    _replace_generation_hash(payloads, "calibration_witnesses")
    with pytest.raises(tracker.TrackerContractError) as captured:
        _audit_generated_payloads(contract, payloads)
    assert captured.value.code == "REPLAN_REQUIRED_HOMOGRAPHY_OR_ENCODER"
    assert "gate_um=27000" in str(captured.value)


def test_calibration_fixture_lock_hashes_every_input_and_implementation(
    contract: tracker.TrackerContract,
) -> None:
    fixture_lock = tracker.load_calibration_fixture_lock(CONFIG)
    assert fixture_lock.fixture_id == tracker.NEUTRAL_FIXTURE_ID
    assert fixture_lock.implementation_sha256 == tracker.sha256_file(
        ROOT / "scripts/evaluate_spot_spray_ego_motion_tracker_v1.py"
    )
    assert {item.name for item in fixture_lock.files} == {
        "frame_timing",
        "homography_receipt",
        "encoder_receipt",
        "calibration_witnesses",
        "generation_receipt",
    }
    assert all(hashlib.sha256(item.payload).hexdigest() == item.sha256 for item in fixture_lock.files)


def test_calibration_candidate_is_mapping_order_deterministic(
    contract: tracker.TrackerContract,
) -> None:
    payloads = tracker.build_neutral_calibration_fixture_payloads(contract)
    forward = _audit_generated_payloads(contract, payloads)
    reverse = _audit_generated_payloads(contract, dict(reversed(list(payloads.items()))))
    assert tracker.canonical_json_bytes(forward) == tracker.canonical_json_bytes(reverse)


def test_calibration_outputs_fail_closed_outside_lane_roots() -> None:
    with pytest.raises(tracker.TrackerContractError) as captured:
        tracker._require_lane_write_path(ROOT / "docs/results/not_this_lane/receipt.json")
    assert captured.value.code == "TRACKER_INVALID_SCOPE_VIOLATION"


def test_cli_contract_summary_is_non_operational(capsys: pytest.CaptureFixture[str]) -> None:
    assert tracker.main(["--config", str(CONFIG), "--print-contract"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "TRACKER_CONTRACT_VALIDATED_NO_SEQUENCE_RUN"
    assert payload["model_loaded"] is False
    assert payload["locked_test_accessed"] is False
    assert payload["hard_gate_ceiling_um"] == 45_000
