from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.evaluate_spot_spray_rig_acceptance_v1 import (
    DEFAULT_CONTRACT_CANONICAL_SHA256,
    DEFAULT_CONTRACT_SHA256,
    FAIL,
    NOT_MEASURED,
    PASS,
    PROJECT_ROOT,
    atomic_write_text,
    canonical_mapping_sha256,
    evaluate,
    load_yaml_mapping,
    sha256_file,
    validate_contract_identity,
)


CONTRACT_PATH = (
    PROJECT_ROOT / "configs/deploy/spot_spray_rig_acceptance_v1.yaml"
)
V2_CONFIG_PATH = (
    PROJECT_ROOT / "configs/deploy/spot_spray_capture_optimization_v2.yaml"
)
V2_DOCUMENT_PATH = PROJECT_ROOT / "docs/CONTROLLED_CAPTURE_OPTIMIZATION_V2.md"
FIXTURE_DIR = PROJECT_ROOT / "tests/fixtures/spot_spray_rig_acceptance_v1"
SCRIPT_PATH = PROJECT_ROOT / "scripts/evaluate_spot_spray_rig_acceptance_v1.py"


@pytest.fixture(scope="module")
def contract() -> dict:
    return load_yaml_mapping(CONTRACT_PATH)


def receipt(name: str) -> dict:
    return load_yaml_mapping(FIXTURE_DIR / f"{name}.yaml")


def evaluate_fixture(contract: dict, name: str) -> dict:
    path = FIXTURE_DIR / f"{name}.yaml"
    return evaluate(contract, receipt(name), PROJECT_ROOT, path)


def stage_gate(result: dict, stage: str, gate_id: str) -> dict:
    return next(
        item
        for item in result["stage_results"][stage]["gates"]
        if item["gate_id"] == gate_id
    )


def test_contract_locks_frozen_v2_sources_and_decisive_thresholds(
    contract: dict,
) -> None:
    sources = contract["frozen_v2_sources"]
    assert sources["repository_commit_at_freeze"] == (
        "dfd4fad4c5675cd1d23b484ce465d1616460c095"
    )
    assert sources["capture_contract"]["sha256"] == sha256_file(V2_CONFIG_PATH)
    assert sources["decision_document"]["sha256"] == sha256_file(
        V2_DOCUMENT_PATH
    )

    v2 = yaml.safe_load(V2_CONFIG_PATH.read_text(encoding="utf-8"))
    thresholds = contract["thresholds"]
    assert thresholds["A_procurement_and_identity"]["camera"]["model"] == (
        v2["camera_shortlist"][0]["model"]
    )
    assert thresholds["A_procurement_and_identity"]["lens"]["model"] == (
        v2["baseline_optics"]["lens"]["model"]
    )
    assert thresholds["B_transport_trigger_and_thermal"][
        "strobe_jitter_p95_maximum_us"
    ] == v2["illumination"]["trigger_to_light_jitter_p95_maximum_us"]
    assert thresholds["C_optics_and_window"]["region_ids"] == [
        f"R{index}" for index in range(1, 10)
    ]
    assert thresholds["C_optics_and_window"]["expected_cell_count"] == (
        len(v2["baseline_optics"]["nine_region_gate"]["normalized_centers"])
        * len(
            v2["baseline_optics"]["nine_region_gate"][
                "object_plane_offsets_above_ground_mm"
            ]
        )
    )
    assert thresholds["D_light_hood_and_polarization"][
        "ambient_off_on_ratio_maximum"
    ] == v2["illumination"]["image_gates"][
        "corrected_ambient_off_on_luma_ratio_maximum_each_region"
    ]
    assert thresholds["E_motion_tracking_and_compute"][
        "end_to_end_rate_hz"
    ] == v2["motion_and_observation"]["acquisition_rate_hz"]["baseline"]
    stage_f = thresholds["F_registration_and_safe_actuation"]
    assert stage_f["calibration"][
        "ground_homography_residual_p95_maximum_mm"
    ] == v2["interfaces"]["calibration"][
        "ground_homography_residual_p95_maximum_mm"
    ]
    assert stage_f["dry_marker"]["end_to_end_error_maximum_mm"] == v2[
        "interfaces"
    ]["calibration"]["dry_marker_end_to_end_error_maximum_mm"]
    assert stage_f["safety"]["forced_no_fire_faults"] == v2["interfaces"][
        "safety"
    ]["no_fire_on"]
    assert contract["decision_policy"]["controlled_data_collection_stages"] == [
        "A_procurement_and_identity",
        "B_transport_trigger_and_thermal",
        "C_optics_and_window",
        "D_light_hood_and_polarization",
        "E_motion_tracking_and_compute",
    ]
    assert contract["decision_policy"]["dry_marker_readiness_stages"] == [
        *contract["decision_policy"]["controlled_data_collection_stages"],
        "F_registration_and_safe_actuation",
    ]


def test_default_contract_has_exact_byte_and_canonical_policy_identity(
    contract: dict,
) -> None:
    identity_policy = contract["default_contract_identity"]
    assert identity_policy == {
        "identity_id": "controlled_spot_spray_rig_acceptance_v1_exact_default",
        "canonicalization": "sorted_compact_JSON_UTF8_with_ISO8601_dates_v1",
        "CLI_requires_exact_default_bytes": True,
        "library_requires_exact_canonical_policy": True,
        "duplicate_YAML_mapping_keys_rejected": True,
        "drift_rule": "reject_before_any_gate_evaluation",
    }
    assert sha256_file(CONTRACT_PATH) == DEFAULT_CONTRACT_SHA256
    assert canonical_mapping_sha256(contract) == (
        DEFAULT_CONTRACT_CANONICAL_SHA256
    )
    verified = validate_contract_identity(contract, CONTRACT_PATH)
    assert verified["exact_bytes_verified"] is True
    assert verified["canonical_policy_verified"] is True
    assert verified["observed_exact_byte_sha256"] == DEFAULT_CONTRACT_SHA256


def test_empty_stage_policy_bypass_is_rejected_before_receipt_evaluation(
    contract: dict,
) -> None:
    relaxed = deepcopy(contract)
    policy = relaxed["decision_policy"]
    policy["evaluated_stages"] = []
    policy["controlled_data_collection_stages"] = []
    policy["dry_marker_readiness_stages"] = []

    synthetic_attack_receipt = receipt("synthetic_pass")
    synthetic_attack_receipt.update(
        evidence_kind="physical_bench",
        deployment_evidence=True,
        synthetic_fixture=False,
        artifacts={},
        stages={},
    )
    with pytest.raises(ValueError, match="canonical-policy identity mismatch"):
        evaluate(relaxed, synthetic_attack_receipt)


def test_reordered_subset_and_relaxed_threshold_contracts_are_rejected(
    contract: dict,
) -> None:
    reordered = deepcopy(contract)
    reordered["decision_policy"]["evaluated_stages"].reverse()

    subset = deepcopy(contract)
    subset["decision_policy"]["controlled_data_collection_stages"].pop()

    relaxed_threshold = deepcopy(contract)
    relaxed_threshold["thresholds"]["D_light_hood_and_polarization"][
        "ambient_off_on_ratio_maximum"
    ] = 1.0

    for drifted in (reordered, subset, relaxed_threshold):
        with pytest.raises(ValueError, match="canonical-policy identity mismatch"):
            evaluate(drifted, receipt("synthetic_pass"))


def test_contract_byte_drift_is_rejected_even_if_policy_is_canonical(
    contract: dict,
    tmp_path: Path,
) -> None:
    drifted_path = tmp_path / "contract_with_comment.yaml"
    drifted_path.write_text(
        CONTRACT_PATH.read_text(encoding="utf-8") + "\n# byte-only drift\n",
        encoding="utf-8",
    )
    drifted = load_yaml_mapping(drifted_path)
    assert canonical_mapping_sha256(drifted) == canonical_mapping_sha256(contract)
    with pytest.raises(ValueError, match="exact-byte identity mismatch"):
        validate_contract_identity(drifted, drifted_path)


def test_duplicate_mapping_keys_are_rejected_in_contract_and_receipt(
    tmp_path: Path,
) -> None:
    duplicate_contract = tmp_path / "duplicate_contract.yaml"
    duplicate_contract.write_text(
        CONTRACT_PATH.read_text(encoding="utf-8") + "\nschema_version: 1\n",
        encoding="utf-8",
    )
    duplicate_receipt = tmp_path / "duplicate_receipt.yaml"
    duplicate_receipt.write_text(
        (FIXTURE_DIR / "synthetic_pass.yaml").read_text(encoding="utf-8")
        + "\ndeployment_evidence: true\n",
        encoding="utf-8",
    )
    for path in (duplicate_contract, duplicate_receipt):
        with pytest.raises(yaml.constructor.ConstructorError, match="duplicate"):
            load_yaml_mapping(path)


@pytest.mark.parametrize("collision", ["receipt", "contract"])
def test_cli_output_cannot_overwrite_receipt_or_selected_contract(
    collision: str,
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "receipt.yaml"
    receipt_path.write_bytes((FIXTURE_DIR / "synthetic_pass.yaml").read_bytes())
    contract_path = tmp_path / "contract.yaml"
    contract_path.write_bytes(CONTRACT_PATH.read_bytes())
    protected = receipt_path if collision == "receipt" else contract_path
    protected_before = protected.read_bytes()

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--contract",
            str(contract_path),
            "--receipt",
            str(receipt_path),
            "--output",
            str(protected),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "Output path collides with protected" in completed.stderr
    assert protected.read_bytes() == protected_before


def test_atomic_output_replace_keeps_old_file_on_replace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "result.json"
    atomic_write_text(target, '{"state":"complete"}\n')
    assert target.read_text(encoding="utf-8") == '{"state":"complete"}\n'

    def reject_replace(source: Path, destination: Path) -> None:
        raise OSError(f"injected replace failure: {source} -> {destination}")

    monkeypatch.setattr(
        "scripts.evaluate_spot_spray_rig_acceptance_v1.os.replace",
        reject_replace,
    )
    with pytest.raises(OSError, match="injected replace failure"):
        atomic_write_text(target, '{"state":"partial"}\n')
    assert target.read_text(encoding="utf-8") == '{"state":"complete"}\n'
    assert list(tmp_path.glob(".result.json.*.tmp")) == []


def test_cli_publishes_complete_result_without_changing_inputs(
    tmp_path: Path,
) -> None:
    receipt_path = tmp_path / "receipt.yaml"
    receipt_path.write_bytes((FIXTURE_DIR / "synthetic_pass.yaml").read_bytes())
    contract_path = tmp_path / "contract.yaml"
    contract_path.write_bytes(CONTRACT_PATH.read_bytes())
    output_path = tmp_path / "result.json"
    input_hashes = (sha256_file(receipt_path), sha256_file(contract_path))

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--contract",
            str(contract_path),
            "--receipt",
            str(receipt_path),
            "--output",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 2
    assert output_path.read_text(encoding="utf-8") == completed.stdout
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["contract_identity"]["exact_bytes_verified"] is True
    assert payload["implementation"] == {
        "script": "scripts/evaluate_spot_spray_rig_acceptance_v1.py",
        "script_sha256": sha256_file(SCRIPT_PATH),
    }
    assert payload["decision"]["controlled_data_collection_allowed"] is False
    assert (sha256_file(receipt_path), sha256_file(contract_path)) == input_hashes
    assert list(tmp_path.glob(".result.json.*.tmp")) == []


def test_synthetic_boundary_fixture_passes_all_gate_logic_but_never_deploys(
    contract: dict,
) -> None:
    result = evaluate_fixture(contract, "synthetic_pass")
    assert result["receipt_validation"]["status"] == PASS
    assert result["frozen_v2_source_integrity"]["status"] == PASS
    assert result["gate_outcome"] == PASS
    assert result["acceptance_outcome"] == PASS
    assert result["collection_gate_outcome_A_E"] == PASS
    assert result["dry_marker_gate_outcome_A_F"] == PASS
    assert all(
        stage["status"] == PASS for stage in result["stage_results"].values()
    )
    decision = result["decision"]
    assert decision["code"] == "SYNTHETIC_NOT_DEPLOYMENT_EVIDENCE"
    assert decision["controlled_data_collection_allowed"] is False
    assert decision["deployment_evidence_eligible"] is False
    assert decision["stage_F_evaluated"] is True
    assert decision["dry_marker_readiness"] == {
        "code": "SYNTHETIC_NOT_DRY_MARKER_EVIDENCE",
        "reason": (
            "Synthetic fixture can prove Stage F logic only; dry-marker "
            "actuation remains blocked."
        ),
        "ready": False,
        "deployment_evidence_eligible": False,
    }
    assert decision["chemical_fire_allowed"] is False
    assert "no quantitative deposition or crop-injury" in decision[
        "chemical_fire_blocker"
    ]
    assert result["receipt_sha256"] == sha256_file(
        FIXTURE_DIR / "synthetic_pass.yaml"
    )


def test_explicit_failure_and_not_measured_fixtures_fail_closed(
    contract: dict,
) -> None:
    failed = evaluate_fixture(contract, "synthetic_fail")
    assert failed["gate_outcome"] == FAIL
    assert failed["stage_results"]["D_light_hood_and_polarization"][
        "status"
    ] == FAIL
    ambient = stage_gate(
        failed,
        "D_light_hood_and_polarization",
        "D.nine_region_image_and_ambient_metrics",
    )
    assert ambient["status"] == FAIL
    assert next(row for row in ambient["records"] if row["key"] == "R9")[
        "status"
    ] == FAIL
    assert failed["stage_results"]["F_registration_and_safe_actuation"][
        "status"
    ] == FAIL
    assert stage_gate(
        failed,
        "F_registration_and_safe_actuation",
        "F.actuation_deadline_and_forced_abort",
    )["status"] == FAIL
    assert failed["dry_marker_gate_outcome_A_F"] == FAIL
    assert failed["decision"]["controlled_data_collection_allowed"] is False

    missing = evaluate_fixture(contract, "synthetic_not_measured")
    assert missing["gate_outcome"] == NOT_MEASURED
    assert missing["acceptance_outcome"] == NOT_MEASURED
    assert missing["dry_marker_gate_outcome_A_F"] == NOT_MEASURED
    assert all(
        stage["status"] == NOT_MEASURED
        for stage in missing["stage_results"].values()
    )
    assert missing["decision"]["controlled_data_collection_allowed"] is False


def test_missing_scalar_is_not_measured_not_an_implicit_pass(contract: dict) -> None:
    candidate = receipt("synthetic_pass")
    candidate["stages"]["D_light_hood_and_polarization"].pop("exterior_lux")
    result = evaluate(contract, candidate)
    assert result["stage_results"]["D_light_hood_and_polarization"][
        "status"
    ] == NOT_MEASURED
    fixed = stage_gate(
        result,
        "D_light_hood_and_polarization",
        "D.fixed_installed_light_setting",
    )
    lux = next(item for item in fixed["checks"] if item["check_id"] == "exterior_lux")
    assert lux["status"] == NOT_MEASURED
    assert result["decision"]["controlled_data_collection_allowed"] is False


def test_quote_refresh_and_transport_counts_enforce_the_frozen_boundary(
    contract: dict,
) -> None:
    quote_stale = receipt("synthetic_pass")
    quote_stale["stages"]["A_procurement_and_identity"][
        "supplier_quote_date"
    ] = "2026-08-11"
    stale_result = evaluate(contract, quote_stale)
    assert stale_result["stage_results"]["A_procurement_and_identity"][
        "status"
    ] == FAIL

    dropped = receipt("synthetic_pass")
    dropped["stages"]["B_transport_trigger_and_thermal"]["trigger_test"][
        "missing_frame_counters"
    ] = 1
    dropped_result = evaluate(contract, dropped)
    assert dropped_result["stage_results"][
        "B_transport_trigger_and_thermal"
    ]["status"] == FAIL


def test_optics_requires_exact_27_cell_coverage_and_per_cell_pass(
    contract: dict,
) -> None:
    incomplete = receipt("synthetic_pass")
    incomplete["stages"]["C_optics_and_window"]["cells"].pop()
    incomplete_result = evaluate(contract, incomplete)
    matrix = stage_gate(
        incomplete_result,
        "C_optics_and_window",
        "C.twenty_seven_cell_optical_matrix",
    )
    assert matrix["status"] == NOT_MEASURED
    assert matrix["coverage"] == {"expected": 27, "observed": 26}

    soft_corner = receipt("synthetic_pass")
    soft_corner["stages"]["C_optics_and_window"]["cells"][0][
        "MTF50_cycles_px"
    ] = 0.149
    soft_result = evaluate(contract, soft_corner)
    assert soft_result["stage_results"]["C_optics_and_window"]["status"] == FAIL


def test_polarization_is_off_by_default_and_enabled_only_at_measured_gain(
    contract: dict,
) -> None:
    enabled_below_gate = receipt("synthetic_pass")
    polarization = enabled_below_gate["stages"][
        "D_light_hood_and_polarization"
    ]["polarization"]
    polarization["enabled"] = True
    polarization["saturated_glare_reduction_fraction"] = 0.49
    failed = evaluate(contract, enabled_below_gate)
    assert failed["stage_results"]["D_light_hood_and_polarization"][
        "status"
    ] == FAIL

    enabled_at_gate = deepcopy(enabled_below_gate)
    enabled_at_gate["stages"]["D_light_hood_and_polarization"][
        "polarization"
    ]["saturated_glare_reduction_fraction"] = 0.50
    passed = evaluate(contract, enabled_at_gate)
    assert passed["stage_results"]["D_light_hood_and_polarization"][
        "status"
    ] == PASS


def test_motion_compute_rejects_deadline_overrun_and_pipeline_omission(
    contract: dict,
) -> None:
    late = receipt("synthetic_pass")
    late["stages"]["E_motion_tracking_and_compute"]["end_to_end"][
        "latency_p95_ms"
    ] = 66.67
    late_result = evaluate(contract, late)
    assert late_result["stage_results"]["E_motion_tracking_and_compute"][
        "status"
    ] == FAIL

    incomplete = receipt("synthetic_pass")
    incomplete["stages"]["E_motion_tracking_and_compute"]["end_to_end"][
        "pipeline_components"
    ].remove("result_transfer")
    incomplete_result = evaluate(contract, incomplete)
    assert incomplete_result["stage_results"][
        "E_motion_tracking_and_compute"
    ]["status"] == FAIL


def test_relabeling_synthetic_placeholders_as_physical_cannot_create_a_pass(
    contract: dict,
) -> None:
    forged = receipt("synthetic_pass")
    forged["evidence_kind"] = "physical_bench"
    forged["deployment_evidence"] = True
    forged["synthetic_fixture"] = False
    result = evaluate(contract, forged)
    assert result["receipt_validation"]["status"] == PASS
    assert result["gate_outcome"] == NOT_MEASURED
    assert result["decision"]["code"] == "NO_GO_NOT_MEASURED"
    assert result["decision"]["controlled_data_collection_allowed"] is False
    assert result["decision"]["deployment_evidence_eligible"] is False


def test_source_or_receipt_hash_drift_fails_integrity(contract: dict) -> None:
    drifted = receipt("synthetic_pass")
    drifted["frozen_v2_source_sha256"]["capture_contract"] = "0" * 64
    result = evaluate(contract, drifted)
    assert result["frozen_v2_source_integrity"]["status"] == FAIL
    assert result["acceptance_outcome"] == FAIL
    assert result["decision"]["controlled_data_collection_allowed"] is False


def _relabel_as_physical_with_synthetic_artifacts(candidate: dict) -> None:
    """Prove that relabeling synthetic placeholders remains blocked."""
    candidate["evidence_kind"] = "physical_bench"
    candidate["deployment_evidence"] = True
    candidate["synthetic_fixture"] = False


def test_stage_f_not_measured_does_not_change_A_E_collection_gate(
    contract: dict,
) -> None:
    candidate = receipt("synthetic_pass")
    candidate["stages"]["F_registration_and_safe_actuation"] = {
        "measurement_status": "not_measured"
    }
    result = evaluate(contract, candidate)
    assert result["collection_gate_outcome_A_E"] == PASS
    assert result["dry_marker_gate_outcome_A_F"] == NOT_MEASURED
    assert result["decision"]["code"] == "SYNTHETIC_NOT_DEPLOYMENT_EVIDENCE"
    assert result["decision"]["dry_marker_readiness"]["code"] == (
        "SYNTHETIC_NOT_DRY_MARKER_EVIDENCE"
    )
    assert result["decision"]["controlled_data_collection_allowed"] is False
    assert result["decision"]["dry_marker_readiness"]["ready"] is False


def test_stage_f_formulae_are_recomputed_and_mismatch_fails(contract: dict) -> None:
    candidate = receipt("synthetic_pass")
    stage_f = candidate["stages"]["F_registration_and_safe_actuation"]
    stage_f["nozzle_registration"]["formula_verification"][
        "command_encoder_mm"
    ] = 1250.01
    stage_f["nozzle_registration"]["frozen_no_fire_distance_mm"] = 15.99
    result = evaluate(contract, candidate)
    formula_gate = stage_gate(
        result,
        "F_registration_and_safe_actuation",
        "F.measured_nozzle_latency_footprint_and_formulae",
    )
    assert formula_gate["status"] == FAIL
    assert result["collection_gate_outcome_A_E"] == PASS
    assert result["dry_marker_gate_outcome_A_F"] == FAIL

    deadline_mismatch = receipt("synthetic_pass")
    deadline_mismatch["stages"]["F_registration_and_safe_actuation"][
        "actuation_deadline"
    ]["feasible_case"]["calculated_required_latency_ms"] = 79.0
    deadline_result = evaluate(contract, deadline_mismatch)
    assert stage_gate(
        deadline_result,
        "F_registration_and_safe_actuation",
        "F.actuation_deadline_and_forced_abort",
    )["status"] == FAIL

    dishonest_feasibility = receipt("synthetic_pass")
    dishonest_feasibility["stages"]["F_registration_and_safe_actuation"][
        "actuation_deadline"
    ]["forced_missed_deadline"]["remaining_encoder_distance_mm"] = 90.0
    dishonest_feasibility["stages"]["F_registration_and_safe_actuation"][
        "actuation_deadline"
    ]["forced_missed_deadline"]["calculated_available_time_ms"] = 90.0
    dishonest_result = evaluate(contract, dishonest_feasibility)
    assert stage_gate(
        dishonest_result,
        "F_registration_and_safe_actuation",
        "F.actuation_deadline_and_forced_abort",
    )["status"] == FAIL


def test_stage_f_explicit_evidence_roles_are_required(contract: dict) -> None:
    candidate = receipt("synthetic_pass")
    candidate["stages"]["F_registration_and_safe_actuation"][
        "evidence_roles"
    ].pop("nozzle_latency_and_footprint")
    result = evaluate(contract, candidate)
    role_gate = stage_gate(
        result,
        "F_registration_and_safe_actuation",
        "F.explicit_measurement_evidence_roles",
    )
    assert role_gate["status"] == NOT_MEASURED
    assert result["dry_marker_gate_outcome_A_F"] == NOT_MEASURED


def test_stage_f_dry_marker_residual_drift_and_error_boundaries(contract: dict) -> None:
    for dotted_path, invalid in (
        ("calibration.ground_homography_residual_p95_mm", 1.001),
        ("calibration.ground_homography_residual_max_mm", 2.001),
        ("calibration.daily_registration_drift_mm", 2.001),
        ("dry_marker.end_to_end_error_p95_mm", 5.001),
        ("dry_marker.end_to_end_error_max_mm", 10.001),
    ):
        candidate = receipt("synthetic_pass")
        target = candidate["stages"]["F_registration_and_safe_actuation"]
        keys = dotted_path.split(".")
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = invalid
        result = evaluate(contract, candidate)
        assert result["stage_results"]["F_registration_and_safe_actuation"][
            "status"
        ] == FAIL
        assert result["collection_gate_outcome_A_E"] == PASS


def test_stage_f_encoder_and_time_alignment_boundaries(contract: dict) -> None:
    for field, invalid in (
        ("shared_real_time_controller_clock", False),
        ("trigger_encoder_same_hardware_event", False),
        ("host_arrival_timestamp_used_for_control", True),
        ("encoder_resolution_mm_per_count", 1.001),
        ("encoder_scale_error_mm_per_m", 1.001),
        ("trigger_encoder_delta_p95_us", 100.001),
        ("trigger_encoder_delta_max_us", 250.001),
        ("encoder_stale_no_fire_after_ms", 5.001),
    ):
        candidate = receipt("synthetic_pass")
        candidate["stages"]["F_registration_and_safe_actuation"][
            "time_and_encoder"
        ][field] = invalid
        result = evaluate(contract, candidate)
        assert stage_gate(
            result,
            "F_registration_and_safe_actuation",
            "F.shared_clock_encoder_and_time_alignment",
        )["status"] == FAIL
        assert result["collection_gate_outcome_A_E"] == PASS
        assert result["dry_marker_gate_outcome_A_F"] == FAIL


def test_stage_f_latency_and_footprint_require_allowed_physical_method(
    contract: dict,
) -> None:
    candidate = receipt("synthetic_pass")
    candidate["stages"]["F_registration_and_safe_actuation"][
        "nozzle_registration"
    ]["latency_footprint_measurement_method"] = "CAD_assumption"
    result = evaluate(contract, candidate)
    assert stage_gate(
        result,
        "F_registration_and_safe_actuation",
        "F.measured_nozzle_latency_footprint_and_formulae",
    )["status"] == FAIL

    for field, invalid in (
        ("offset_physically_measured", False),
        ("offset_CAD_assumed", True),
    ):
        offset_candidate = receipt("synthetic_pass")
        offset_candidate["stages"]["F_registration_and_safe_actuation"][
            "nozzle_registration"
        ][field] = invalid
        offset_result = evaluate(contract, offset_candidate)
        assert stage_gate(
            offset_result,
            "F_registration_and_safe_actuation",
            "F.measured_nozzle_latency_footprint_and_formulae",
        )["status"] == FAIL


def test_forced_deadline_abort_and_every_no_fire_fault_are_required(
    contract: dict,
) -> None:
    unsafe_abort = receipt("synthetic_pass")
    forced = unsafe_abort["stages"]["F_registration_and_safe_actuation"][
        "actuation_deadline"
    ]["forced_missed_deadline"]
    forced.update(abort_observed=False, valve_enable=True, fire_command=True)
    abort_result = evaluate(contract, unsafe_abort)
    assert stage_gate(
        abort_result,
        "F_registration_and_safe_actuation",
        "F.actuation_deadline_and_forced_abort",
    )["status"] == FAIL

    missing_fault = receipt("synthetic_pass")
    missing_fault["stages"]["F_registration_and_safe_actuation"]["safety"][
        "fault_injection_results"
    ].pop()
    missing_result = evaluate(contract, missing_fault)
    fault_gate = stage_gate(
        missing_result,
        "F_registration_and_safe_actuation",
        "F.each_frozen_fault_forces_no_fire",
    )
    assert fault_gate["status"] == NOT_MEASURED
    assert fault_gate["coverage"] == {"expected": 6, "observed": 5}

    unsafe_fault = receipt("synthetic_pass")
    unsafe_fault["stages"]["F_registration_and_safe_actuation"]["safety"][
        "fault_injection_results"
    ][0]["valve_enable"] = True
    unsafe_result = evaluate(contract, unsafe_fault)
    assert unsafe_result["stage_results"][
        "F_registration_and_safe_actuation"
    ]["status"] == FAIL


def test_estop_watchdog_and_chemical_states_fail_closed(contract: dict) -> None:
    for dotted_path, invalid in (
        ("safety.emergency_stop.valve_enable", True),
        ("safety.emergency_stop.strobe_enable", True),
        ("safety.watchdog.default_no_fire", False),
        ("safety.watchdog.valve_enable", True),
        ("chemical.chemical_enable", True),
        ("chemical.chemical_enable_hardware_line_verified_disabled", False),
        ("chemical.deposition_acceptance_status", "pass"),
        ("chemical.crop_injury_acceptance_status", "pass"),
    ):
        candidate = receipt("synthetic_pass")
        target = candidate["stages"]["F_registration_and_safe_actuation"]
        keys = dotted_path.split(".")
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = invalid
        result = evaluate(contract, candidate)
        assert result["stage_results"]["F_registration_and_safe_actuation"][
            "status"
        ] == FAIL
        assert result["decision"]["chemical_fire_allowed"] is False


def test_physical_A_F_numeric_pass_still_requires_real_artifact_integrity(
    contract: dict,
) -> None:
    candidate = receipt("synthetic_pass")
    _relabel_as_physical_with_synthetic_artifacts(candidate)
    result = evaluate(contract, candidate)
    assert result["collection_gate_outcome_A_E"] == NOT_MEASURED
    assert result["dry_marker_gate_outcome_A_F"] == NOT_MEASURED
    assert result["decision"]["controlled_data_collection_allowed"] is False
    assert result["decision"]["dry_marker_readiness"]["ready"] is False
    assert result["decision"]["chemical_fire_allowed"] is False


def test_fixture_names_and_notes_cannot_be_mistaken_for_hardware_evidence() -> None:
    for path in sorted(FIXTURE_DIR.glob("*.yaml")):
        payload = load_yaml_mapping(path)
        assert payload["evidence_kind"] == "synthetic_fixture"
        assert payload["deployment_evidence"] is False
        assert payload["synthetic_fixture"] is True
        assert "SYNTHETIC" in payload["receipt_id"]
        assert "not" in payload["notes"].lower()
