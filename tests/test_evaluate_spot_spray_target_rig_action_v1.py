import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from scripts.evaluate_spot_spray_target_rig_action_v1 import (
    ContractError,
    choose_validation_threshold,
    evaluate,
    exit_code_for_status,
    load_manifest,
    metric_gates,
    parse_args,
    point_in_polygon,
    run_cli,
    sha256,
    wilson_upper,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml"
CAPTURE_SCHEMA = ROOT / "configs/data/spot_spray_capture_manifest_v1.schema.json"
FIXTURES = ROOT / "tests/fixtures/spot_spray_target_rig_model_v1"
MANIFEST = FIXTURES / "capture_manifest_v1.json"
CAPTURE_AUDIT = FIXTURES / "capture_audit_result_v1.json"
LEGACY_FRAME_ROWS = FIXTURES / "capture_manifest_v1.jsonl"
PREDICTIONS = FIXTURES / "predictions_v1.jsonl"


@pytest.fixture(scope="module")
def fixture_result() -> dict:
    return evaluate(CONFIG, MANIFEST, CAPTURE_AUDIT, PREDICTIONS)


def test_frozen_contract_pins_selected_checkpoint_and_zero_synthetic_weight() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert config["model"]["foundation"]["checkpoint_sha256"] == (
        "3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100"
    )
    assert config["model"]["evaluated_checkpoint"]["checkpoint"] is None
    assert config["model"]["evaluated_checkpoint"]["checkpoint_sha256"] is None
    assert (
        config["offline_go_gates"]["synthetic_score_weight_in_real_go_decision"]
        == 0.0
    )
    assert (
        config["offline_go_gates"][
            "crop_hit_upper_confidence_bound_required"
        ]
        is True
    )
    assert (
        config["threshold_calibration"][
            "crop_hit_upper_confidence_bound_required"
        ]
        is True
    )
    for source in config["locked_sources"].values():
        assert sha256(ROOT / source["path"]) == source["sha256"]


def test_fixture_conforms_to_capture_lane_canonical_schema() -> None:
    schema = json.loads(CAPTURE_SCHEMA.read_text(encoding="utf-8"))
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)


def test_validation_only_calibration_is_fixed_on_test(fixture_result: dict) -> None:
    calibration = fixture_result["calibration"]
    assert calibration["source_split"] == "validation"
    assert calibration["test_accessed_during_selection"] is False
    assert calibration["selection"]["constraints_passed"] is False
    assert calibration["selection"]["status"] == (
        "no_validation_safety_feasible_threshold_fallback_for_diagnostics"
    )
    assert calibration["selection"]["threshold"] == pytest.approx(0.8)
    assert fixture_result["test"]["fixed_weed_confidence_threshold"] == pytest.approx(
        0.8
    )
    assert fixture_result["test"]["threshold_source"] == "validation_only"


def test_eligible_track_denominator_and_three_of_five_fire_once(
    fixture_result: dict,
) -> None:
    metric = fixture_result["test"]["pooled"]
    assert metric["all_gt_weed_tracks"] == 3
    assert metric["eligible_weed_tracks"] == 2
    assert metric["excluded_noneligible_weed_tracks"] == 1
    assert metric["ignored_noneligible_weed_hits"] == 1
    events = metric["event_audit"]
    pweed = [event for event in events if event["predicted_track_id"] == "pweed"]
    assert len(pweed) == 1
    assert pweed[0]["frame_index"] == 4
    assert pweed[0]["confirmations_in_window"] == 3
    assert len({(event["video_id"], event["predicted_track_id"]) for event in events}) == len(
        events
    )
    assert fixture_result["test"]["temporal_counts"]["weed_observations_crop_vetoed"] == 3


def test_one_to_one_matching_exposes_duplicate_and_crop_collision(
    fixture_result: dict,
) -> None:
    metric = fixture_result["test"]["pooled"]
    assert metric["true_positive"] == 2
    assert metric["false_positive"] == 2
    assert metric["false_negative"] == 0
    assert metric["attempted_fire_events"] == 5
    assert metric["duplicate_shot"] == 1
    assert metric["duplicate_shot_rate"] == pytest.approx(0.2)
    assert metric["crop_collision"] == 1
    assert metric["crop_hit_rate"] == pytest.approx(0.2)
    dispositions = [event["disposition"] for event in metric["event_audit"]]
    assert dispositions.count("true_positive_first_track_hit") == 2
    assert dispositions.count("duplicate_track_hit_false_positive") == 1
    assert dispositions.count("crop_collision_false_positive") == 1


def test_per_field_and_worst_field_are_hard_gates(fixture_result: dict) -> None:
    test = fixture_result["test"]
    assert test["per_field_gates"]["field_a"]["crop_hit_rate"] is True
    assert test["per_field_gates"]["field_a"]["crop_hit_wilson_upper_95"] is False
    assert test["per_field_gates"]["field_a"]["all_pass"] is False
    assert test["per_field_gates"]["field_b"]["all_pass"] is False
    assert test["every_field_pass"] is False
    assert test["worst_field"]["precision"] == {
        "field_id": "field_b",
        "value": pytest.approx(1 / 3),
        "direction": "minimum",
    }
    assert test["worst_field"]["crop_hit_rate"]["field_id"] == "field_b"


def test_fixture_metrics_can_never_authorize_real_or_chemical_go(
    fixture_result: dict,
) -> None:
    assert fixture_result["status"] == "FIXTURE_ONLY"
    assert fixture_result["readiness"]["capture_evidence_scope"] == "synthetic_fixture"
    assert fixture_result["readiness"]["capture_audit_real_proof_accepted"] is False
    assert fixture_result["readiness"]["real_data_ready"] is False
    assert (
        fixture_result["readiness"]["checks"]
        ["evaluated_checkpoint_path_and_hash_frozen"]
        is False
    )
    assert fixture_result["decision"]["offline_model_go"] is False
    assert fixture_result["decision"]["chemical_fire_go"] is False
    assert (
        fixture_result["decision"]["synthetic_score_weight_in_real_go_decision"]
        == 0.0
    )


def test_cli_without_real_inputs_returns_not_ready_and_nonzero() -> None:
    result, exit_code = run_cli(parse_args(["--config", str(CONFIG)]))
    assert exit_code == 2
    assert result["status"] == "NOT_READY"
    assert result["decision"]["offline_model_go"] is False
    assert result["decision"]["field_fire_go"] is False
    assert result["decision"]["chemical_fire_go"] is False
    assert result["decision"]["fail_closed"] is True
    assert "capture_audit_result_json" in result["reason"]


def test_fixture_cli_is_diagnostic_and_never_returns_success() -> None:
    result, exit_code = run_cli(
        parse_args(
            [
                "--config",
                str(CONFIG),
                "--manifest",
                str(MANIFEST),
                "--capture-audit",
                str(CAPTURE_AUDIT),
                "--predictions",
                str(PREDICTIONS),
            ]
        )
    )
    assert result["status"] == "FIXTURE_ONLY"
    assert exit_code == 4


def test_prediction_provenance_mismatch_fails_closed(tmp_path: Path) -> None:
    rows = PREDICTIONS.read_text(encoding="utf-8").splitlines()
    metadata = json.loads(rows[0])
    metadata["capture_manifest_sha256"] = "0" * 64
    bad_predictions = tmp_path / "bad_predictions.jsonl"
    bad_predictions.write_text(
        "\n".join([json.dumps(metadata), *rows[1:]]) + "\n", encoding="utf-8"
    )
    with pytest.raises(ContractError, match="manifest hash"):
        evaluate(CONFIG, MANIFEST, CAPTURE_AUDIT, bad_predictions)


def _write_synthetic_audit(path: Path, manifest_path: Path) -> Path:
    report = json.loads(CAPTURE_AUDIT.read_text(encoding="utf-8"))
    report["inputs"]["manifest"] = str(manifest_path.resolve())
    report["inputs"]["manifest_sha256"] = sha256(manifest_path)
    path.write_text(json.dumps(report) + "\n", encoding="utf-8")
    return path


def _write_bound_predictions(
    path: Path,
    manifest_path: Path,
    audit_path: Path,
    checkpoint_sha256: str,
) -> Path:
    prediction_lines = PREDICTIONS.read_text(encoding="utf-8").splitlines()
    metadata = json.loads(prediction_lines[0])
    metadata["capture_manifest_sha256"] = sha256(manifest_path)
    metadata["capture_audit_result_sha256"] = sha256(audit_path)
    metadata["model_checkpoint_sha256"] = checkpoint_sha256
    path.write_text(
        "\n".join([json.dumps(metadata), *prediction_lines[1:]]) + "\n",
        encoding="utf-8",
    )
    return path


def _write_relabeled_manifest(path: Path) -> Path:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["evidence_scope"] = "real_target_rig"
    manifest["rig_acceptance"] = {
        "result_path": "receipts/fixture_only.json",
        "result_sha256": "0" * 64,
    }
    for frame in manifest["frames"]:
        frame.update(
            {
                "image_sha256": "0" * 64,
                "camera_frame_counter": frame["frame_index"],
                "camera_timestamp_ns": frame["timestamp_ns"] + 1,
                "white_balance": {
                    "mode": "manual",
                    "red_gain": 1.0,
                    "green_gain": 1.0,
                    "blue_gain": 1.0,
                },
                "native_width_px": 1024,
                "native_height_px": 1024,
                "pixel_format": "RGB8",
                "camera_id": "fixture_camera",
                "rig_id": "fixture_rig",
                "capture_profile_id": "fixture_profile",
                "strobe_settings": {
                    "profile_id": frame["strobe_profile_id"],
                    "pulse_width_us": 100.0,
                    "peak_current_a": 1.0,
                },
            }
        )
    path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    return path


def test_only_offline_model_go_has_success_exit_code() -> None:
    assert exit_code_for_status("EVALUATED_OFFLINE_MODEL_GO") == 0
    assert exit_code_for_status("NOT_READY") == 2
    assert exit_code_for_status("EVALUATED_NO_GO") == 3
    assert exit_code_for_status("FIXTURE_ONLY") == 4
    assert exit_code_for_status("CONTRACT_ERROR") == 5


def test_relabeled_real_manifest_without_audit_is_not_ready(tmp_path: Path) -> None:
    real_manifest = _write_relabeled_manifest(tmp_path / "relabeled_manifest.json")
    result, exit_code = run_cli(
        parse_args(
            [
                "--config",
                str(CONFIG),
                "--manifest",
                str(real_manifest),
                "--predictions",
                str(PREDICTIONS),
            ]
        )
    )
    assert result["status"] == "NOT_READY"
    assert result["decision"]["offline_model_go"] is False
    assert exit_code == 2


def test_synthetic_audit_cannot_unlock_a_relabeled_real_manifest(tmp_path: Path) -> None:
    real_manifest = _write_relabeled_manifest(tmp_path / "relabeled_manifest.json")
    synthetic_audit = _write_synthetic_audit(
        tmp_path / "synthetic_audit.json",
        real_manifest,
    )
    foundation_sha = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))["model"][
        "foundation"
    ]["checkpoint_sha256"]
    predictions = _write_bound_predictions(
        tmp_path / "predictions.jsonl",
        real_manifest,
        synthetic_audit,
        foundation_sha,
    )
    result = evaluate(CONFIG, real_manifest, synthetic_audit, predictions)
    assert result["status"] == "FIXTURE_ONLY"
    assert result["readiness"]["capture_audit_real_proof_accepted"] is False
    assert result["readiness"]["real_data_ready"] is False
    assert result["decision"]["offline_model_go"] is False


def test_relabeling_audit_flags_without_real_integrity_cannot_unlock(
    tmp_path: Path,
) -> None:
    real_manifest = _write_relabeled_manifest(tmp_path / "relabeled_manifest.json")
    report = json.loads(CAPTURE_AUDIT.read_text(encoding="utf-8"))
    report.update({"status": "READY", "valid": True, "ready": True})
    report["evidence"].update(
        {
            "scope": "real_target_rig",
            "synthetic_fixture": False,
            "counts_as_real_target_rig_evidence": True,
        }
    )
    report["errors"] = []
    report["readiness_reasons"] = []
    report["inputs"]["manifest"] = str(real_manifest.resolve())
    report["inputs"]["manifest_sha256"] = sha256(real_manifest)
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    trusted = config["capture_audit"]["trusted_sources"]
    schema = (ROOT / trusted["schema"]).resolve()
    policy = (ROOT / trusted["policy"]).resolve()
    implementation = (ROOT / trusted["implementation"]).resolve()
    report["inputs"].update(
        {
            "schema": str(schema),
            "schema_sha256": sha256(schema),
            "policy": str(policy),
            "policy_sha256": sha256(policy),
        }
    )
    report["implementation"] = {
        "script": str(implementation),
        "script_sha256": sha256(implementation),
    }
    relabeled_audit = tmp_path / "relabeled_audit.json"
    relabeled_audit.write_text(json.dumps(report) + "\n", encoding="utf-8")
    foundation_sha = config["model"]["foundation"]["checkpoint_sha256"]
    predictions = _write_bound_predictions(
        tmp_path / "predictions.jsonl",
        real_manifest,
        relabeled_audit,
        foundation_sha,
    )
    result = evaluate(CONFIG, real_manifest, relabeled_audit, predictions)
    checks = result["readiness"]["capture_audit_real_proof_checks"]
    assert checks["real_capture_metadata_complete"] is False
    assert checks["all_real_image_sha256_verified"] is False
    assert checks["all_real_image_content_verified"] is False
    assert checks["rig_acceptance_passed"] is False
    assert result["readiness"]["capture_audit_real_proof_accepted"] is False
    assert result["status"] == "NOT_READY"


def test_capture_audit_manifest_hash_drift_is_a_contract_error(tmp_path: Path) -> None:
    report = json.loads(CAPTURE_AUDIT.read_text(encoding="utf-8"))
    report["inputs"]["manifest_sha256"] = "0" * 64
    bad_audit = tmp_path / "bad_audit.json"
    bad_audit.write_text(json.dumps(report) + "\n", encoding="utf-8")
    predictions = _write_bound_predictions(
        tmp_path / "predictions.jsonl",
        MANIFEST,
        bad_audit,
        json.loads(PREDICTIONS.read_text(encoding="utf-8").splitlines()[0])[
            "model_checkpoint_sha256"
        ],
    )
    with pytest.raises(ContractError, match="Capture audit manifest hash"):
        evaluate(CONFIG, MANIFEST, bad_audit, predictions)

    result, exit_code = run_cli(
        parse_args(
            [
                "--config",
                str(CONFIG),
                "--manifest",
                str(MANIFEST),
                "--capture-audit",
                str(bad_audit),
                "--predictions",
                str(predictions),
            ]
        )
    )
    assert result["status"] == "CONTRACT_ERROR"
    assert exit_code == 5


def test_capture_audit_manifest_path_drift_is_rejected(tmp_path: Path) -> None:
    report = json.loads(CAPTURE_AUDIT.read_text(encoding="utf-8"))
    report["inputs"]["manifest"] = str((tmp_path / "other_manifest.json").resolve())
    bad_audit = tmp_path / "wrong_path_audit.json"
    bad_audit.write_text(json.dumps(report) + "\n", encoding="utf-8")
    predictions = _write_bound_predictions(
        tmp_path / "predictions.jsonl",
        MANIFEST,
        bad_audit,
        json.loads(PREDICTIONS.read_text(encoding="utf-8").splitlines()[0])[
            "model_checkpoint_sha256"
        ],
    )
    with pytest.raises(ContractError, match="manifest path"):
        evaluate(CONFIG, MANIFEST, bad_audit, predictions)


def test_prediction_must_bind_the_exact_capture_audit_hash(tmp_path: Path) -> None:
    rows = PREDICTIONS.read_text(encoding="utf-8").splitlines()
    metadata = json.loads(rows[0])
    metadata["capture_audit_result_sha256"] = "0" * 64
    bad_predictions = tmp_path / "bad_audit_binding.jsonl"
    bad_predictions.write_text(
        "\n".join([json.dumps(metadata), *rows[1:]]) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ContractError, match="capture-audit hash"):
        evaluate(CONFIG, MANIFEST, CAPTURE_AUDIT, bad_predictions)


def test_wilson_upper_bound_enforces_statistical_crop_safety() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    gates = config["offline_go_gates"]
    tiny_perfect = {
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "crop_hit_rate": 0.0,
        "crop_hit_wilson_upper_95": wilson_upper(0, 1),
        "duplicate_shot_rate": 0.0,
    }
    assert tiny_perfect["crop_hit_wilson_upper_95"] == pytest.approx(
        0.7934506856227626
    )
    tiny_gates = metric_gates(tiny_perfect, gates)
    assert tiny_gates["crop_hit_rate"] is True
    assert tiny_gates["crop_hit_wilson_upper_95"] is False
    assert tiny_gates["all_pass"] is False
    selection = choose_validation_threshold(
        [{"threshold": 0.8, "metrics": tiny_perfect}],
        config["threshold_calibration"],
    )
    assert selection["constraints_passed"] is False

    statistically_sufficient = {
        **tiny_perfect,
        "crop_hit_wilson_upper_95": wilson_upper(0, 1000),
    }
    assert statistically_sufficient["crop_hit_wilson_upper_95"] < 0.005
    assert metric_gates(statistically_sufficient, gates)["all_pass"] is True


def test_frozen_upper_confidence_requirement_cannot_be_disabled(
    tmp_path: Path,
) -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["offline_go_gates"]["crop_hit_upper_confidence_bound_required"] = False
    config["threshold_calibration"][
        "crop_hit_upper_confidence_bound_required"
    ] = False
    unsafe_config = tmp_path / "unsafe.yaml"
    unsafe_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(ContractError, match="upper-confidence gate cannot be disabled"):
        evaluate(unsafe_config, MANIFEST, CAPTURE_AUDIT, PREDICTIONS)


def test_partial_unknown_may_transition_to_known_without_freezing_unknown(
    tmp_path: Path,
) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    first = payload["frames"][0]["instances"][0]
    first["class_name"] = "partial_unknown"
    first["canopy_span_mm"] = None
    first["partial"] = True
    first["visible_fraction"] = 0.5
    transition_manifest = tmp_path / "transition.json"
    transition_manifest.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    parsed = load_manifest(transition_manifest, config)
    classes = {
        frame.frame_id: frame.instances[0].class_name
        for frame in parsed.frames
        if frame.frame_id in {"val_000", "val_001"}
    }
    assert classes == {"val_000": "partial_unknown", "val_001": "weed"}


def test_known_crop_to_weed_track_conflict_remains_rejected(tmp_path: Path) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    first = payload["frames"][0]["instances"][0]
    first["class_name"] = "partial_unknown"
    first["canopy_span_mm"] = None
    first["partial"] = True
    payload["frames"][1]["instances"][0]["class_name"] = "crop"
    conflicting_manifest = tmp_path / "known_conflict.json"
    conflicting_manifest.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    with pytest.raises(ContractError, match="conflicts between known classes"):
        load_manifest(conflicting_manifest, config)


def test_frozen_final_checkpoint_hash_mismatch_fails_closed(tmp_path: Path) -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["model"]["evaluated_checkpoint"]["checkpoint"] = "/tmp/final.pt"
    config["model"]["evaluated_checkpoint"]["checkpoint_sha256"] = "1" * 64
    frozen_config = tmp_path / "frozen.yaml"
    frozen_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(ContractError, match="frozen model"):
        evaluate(frozen_config, MANIFEST, CAPTURE_AUDIT, PREDICTIONS)


def test_adjacent_video_frames_cannot_cross_splits(tmp_path: Path) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["frames"][6]["split"] = "validation"
    bad_manifest = tmp_path / "leaky_manifest.json"
    bad_manifest.write_text(
        json.dumps(payload) + "\n", encoding="utf-8"
    )
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    with pytest.raises(ContractError, match="cross splits"):
        load_manifest(bad_manifest, config)


def test_legacy_frame_row_jsonl_is_not_accepted_as_canonical_manifest() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    with pytest.raises(ContractError, match="Invalid capture manifest JSON"):
        load_manifest(LEGACY_FRAME_ROWS, config)


def test_polygon_contact_includes_boundary_and_excludes_background() -> None:
    polygon = ((0.1, 0.1), (0.2, 0.1), (0.2, 0.2), (0.1, 0.2))
    assert point_in_polygon((0.15, 0.15), polygon)
    assert point_in_polygon((0.1, 0.15), polygon)
    assert not point_in_polygon((0.3, 0.3), polygon)
