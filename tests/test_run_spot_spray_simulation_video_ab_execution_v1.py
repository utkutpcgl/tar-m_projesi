from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from scripts import run_spot_spray_simulation_video_ab_execution_v1 as execution


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/benchmark/spot_spray_simulation_video_ab_execution_v1.yaml"


def test_execution_config_is_native_synthetic_and_outcome_agnostic() -> None:
    config = execution.load_config(CONFIG)
    assert config["status"] == "SYNTHETIC_EXECUTION_ONLY"
    assert config["native_contract"]["width_px"] == 2048
    assert config["native_contract"]["height_px"] == 2048
    assert config["native_contract"]["frames_per_arm"] == 30
    assert config["native_contract"]["frame_rate_hz"] == 15
    assert config["native_contract"]["full_frame_resize_allowed"] is False
    assert config["evidence_policy"]["synthetic_score_weight_in_real_go_decision"] == 0.0
    assert config["evidence_policy"]["chemical_fire_go_allowed"] is False
    assert config["descriptive_targets"]["ideal_minimum"] == pytest.approx(0.97)
    assert config["descriptive_targets"]["degraded_reference"] == pytest.approx(0.75)
    assert config["descriptive_targets"]["use_in_threshold_selection"] is False
    assert config["descriptive_targets"]["use_in_model_or_degradation_tuning"] is False


def test_execution_source_locks_and_protocol_nested_locks_match_current_bytes() -> None:
    config = execution.load_config(CONFIG)
    receipt = execution.verify_all_sources(config)
    assert receipt["execution_locks"]
    assert receipt["protocol_internal_locks"]
    by_name = {row["name"]: row for row in receipt["execution_locks"]}
    assert by_name["protocol"]["sha256"] == (
        "de12cd76d3f497f1ea3a6ffa1d1c7fc8eea4e70a9af218c2769bae81da0f329f"
    )
    assert by_name["botanical_validation_receipt"]["sha256"] == (
        "491776943143ca486c0fda7f307db4ec7372cc35adfd216c9243ac5efd36c956"
    )
    assert by_name["botanical_patch"]["sha256"] == (
        "c2301376c2f1607d1abfeeb75a6b9ad9b29873c764b027bd6995b10ebcaddd24"
    )
    assert by_name["paired_validation_receipt"]["sha256"] == (
        "179410f6f975e1b7b43c369839ea3b58f74e6eb2ccc667dc4e64127b5ce7d5b3"
    )
    assert by_name["paired_renderer"]["sha256"] == (
        "3fa5b6a5838dc45126f55d54875c65da7fc6cc7ff0e3078104f207f5d3809082"
    )
    assert by_name["simulation_evaluator"]["sha256"] == (
        "83c6fabd1acc3db47799e96aea91b46d29f514d891c5f19091d3fb14bf3811f7"
    )
    assert by_name["selected_checkpoint"]["sha256"] == (
        "3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100"
    )


def test_source_lock_mismatch_fails_closed_before_use(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"source-bound fixture")
    with pytest.raises(execution.ContractError, match="Source drift"):
        execution.verified_file_row(
            "tampered", {"path": str(source), "sha256": "0" * 64}
        )


def test_native_scene_derivation_preserves_profile_and_exact_geometry() -> None:
    config = execution.load_config(CONFIG)
    for scene in config["fixture"]["scenes"]:
        source = config["source_locks"][scene["source_lock"]]
        base = execution.load_yaml(execution.resolve_path(source["path"]))
        derived = execution.derive_native_scene_config(base, scene, config)
        render = derived["render"]
        assert (render["resolution_x"], render["resolution_y"]) == (2048, 2048)
        assert render["frames"] == 30
        assert render["samples"] == config["fixture"]["render_samples"]
        assert derived["agri_asset_profile"]["correlated_scene_profile"] == scene[
            "scene_profile"
        ]
        bed = next(iter(derived["field"]["beds"].values()))
        travel = (bed["plants_count"] - 1) * bed["plant_distance"]
        assert travel == pytest.approx(
            scene["travel_speed_m_s"] * config["native_contract"]["duration_s"],
            abs=1.0e-8,
        )
        assert bed["rows_count"] == 2
        assert bed["row_distance"] == pytest.approx(0.01)
        assert derived["field"]["noise"]["position"] == 0.0
        assert derived["botanical_gt_contract"][
            "semantic_connected_components_for_identity_forbidden"
        ] is True
        assert derived["botanical_gt_contract"][
            "deterministic_crop_row_overlap_stress"
        ] is True
        assert list(derived["field"]["weeds"]) == [config["fixture"]["weed_family"]]
        weed = next(iter(derived["field"]["weeds"].values()))
        assert weed["density"] == config["fixture"]["weed_density_per_family"]


@pytest.mark.parametrize("family", ["linear", "smooth_curved"])
@pytest.mark.parametrize("length", [0.0, 0.32, 0.75])
def test_protocol_psf_is_deterministic_normalized_and_centered(
    family: str, length: float
) -> None:
    first, first_state = execution.motion_psf(length, family, 17)
    second, second_state = execution.motion_psf(length, family, 17)
    assert np.array_equal(first, second)
    assert first_state == second_state
    assert first.shape == (3, 3)
    assert float(first.sum()) == pytest.approx(1.0, abs=1.0e-6)
    assert first_state["requested_path_length_px"] <= 0.75
    assert first_state["centroid_error_px"] <= 0.15


def test_capture_degradation_uses_only_frozen_subpixel_motion() -> None:
    yy, xx = np.indices((96, 96), dtype=np.uint16)
    image = np.stack(
        ((xx * 3) % 256, (yy * 5) % 256, ((xx + yy) * 7) % 256), axis=2
    ).astype(np.uint8)
    first, first_state = execution.apply_protocol_degradation(
        image,
        speed_m_s=1.0,
        pulse_width_us=170.0,
        gsd_mm_per_px=479.0 / 2048.0,
        path_family="smooth_curved",
        sample_count=17,
    )
    second, second_state = execution.apply_protocol_degradation(
        image,
        speed_m_s=1.0,
        pulse_width_us=170.0,
        gsd_mm_per_px=479.0 / 2048.0,
        path_family="smooth_curved",
        sample_count=17,
    )
    assert np.array_equal(first, second)
    assert first_state == second_state
    assert not np.array_equal(first, image)
    assert first_state["requested_path_length_px"] <= 0.75
    assert first_state["extra_noise_or_compression_applied"] is False
    assert first_state["post_outcome_rescaling_applied"] is False


def test_access_guard_forbids_ideal_or_test_before_threshold_and_repeat_metrics() -> None:
    guard = execution.ExecutionAccessGuard()
    with pytest.raises(execution.ContractError, match="before threshold"):
        guard.record_test_inference("ideal", "ideal:test:scene")
    guard.seal_release("1" * 64, model_outputs_present=False)
    with pytest.raises(execution.ContractError, match="Only degraded"):
        guard.record_calibration_inference("ideal", "ideal:calibration:scene")
    guard.record_calibration_inference("degraded", "degraded:calibration:scene")
    guard.seal_threshold(
        0.5, source_condition="degraded", test_predictions_present=False
    )
    guard.record_calibration_inference("ideal", "ideal:calibration:scene")
    guard.record_test_inference("ideal", "ideal:test:scene")
    guard.record_test_inference("degraded", "degraded:test:scene")
    guard.begin_locked_test_evaluation()
    with pytest.raises(execution.ContractError, match="exactly once"):
        guard.begin_locked_test_evaluation()
    guard.finish()
    receipt = guard.receipt()
    assert receipt["test_accessed_before_threshold_lock"] is False
    assert receipt["locked_test_metric_evaluations"] == 1


def test_access_guard_rejects_duplicate_locked_test_sequence() -> None:
    guard = execution.ExecutionAccessGuard()
    guard.seal_release("2" * 64, model_outputs_present=False)
    guard.record_calibration_inference("degraded", "degraded:calibration:scene")
    guard.seal_threshold(
        0.45, source_condition="degraded", test_predictions_present=False
    )
    guard.record_test_inference("ideal", "ideal:test:scene")
    with pytest.raises(execution.ContractError, match="more than once"):
        guard.record_test_inference("ideal", "ideal:test:scene")


def test_composed_patch_binds_constituents_in_frozen_order(tmp_path: Path) -> None:
    config = execution.load_config(CONFIG)
    destination = tmp_path / "combined.patch"
    receipt = execution.compose_scene_patch(config, destination)
    assert receipt["ordered_constituents"][0]["sha256"] == (
        "ad3f65815a1a269bbefa41cb3292c9836e63ccd91af146ed27247a5befde416b"
    )
    assert receipt["ordered_constituents"][1]["sha256"] == (
        "c2301376c2f1607d1abfeeb75a6b9ad9b29873c764b027bd6995b10ebcaddd24"
    )
    assert receipt["sha256"] == execution.sha256_file(destination)
    assert destination.read_bytes().endswith(b"\n")


def test_execution_inference_config_is_native_and_tracker_frozen(tmp_path: Path) -> None:
    config = execution.load_config(CONFIG)
    destination = tmp_path / "inference.yaml"
    resolved = execution.build_execution_inference_config(destination, config)
    assert resolved["source"]["mode"] == "external_botanical_native_manifest"
    assert resolved["inference"]["image_size_px"] == 2048
    assert resolved["tracking"]["association_max_centroid_distance_px"] == 160.0
    assert resolved["calibration"]["test_access_forbidden"] is True
    assert resolved["calibration"]["shared_threshold_across_conditions"] is True
    assert resolved["video"]["fps"] == 15.0


def test_full_capacity_estimate_is_predeclared_not_outcome_extended() -> None:
    config = execution.load_config(CONFIG)
    estimate = config["storage_estimate"]
    assert estimate["full_calibration_pairs"] == 32
    assert estimate["full_locked_test_pairs"] == 64
    assert estimate["full_total_pairs"] == 96
    assert estimate["full_arm_videos"] == 192
    assert estimate["full_native_frames"] == 5760
    assert estimate["full_estimated_bytes"] == config["runtime"][
        "minimum_full_free_bytes"
    ]


def test_fixture_output_paths_are_bounded_to_lane_contract() -> None:
    config = execution.load_config(CONFIG)
    paths = execution.fixture_paths(config)
    assert str(paths["synthetic"]).endswith(
        "data/synthetic/cropcraft/spot_spray_simulation_video_ab_execution_v1/native_fixture_v1"
    )
    assert str(paths["run"]).endswith(
        "data/runs/spot_spray_simulation_video_ab_execution_v1/native_fixture_v1"
    )
    assert str(paths["docs"]).endswith(
        "docs/results/spot_spray_simulation_video_ab_execution_v1/native_fixture_v1"
    )


def test_full_roster_is_protocol_exact_deterministic_and_outcome_free() -> None:
    config = execution.load_config(CONFIG)
    protocol = execution._protocol(config)
    templates = execution._scene_template_inventory(config)
    first = execution.build_full_roster(config, protocol, templates)
    second = execution.build_full_roster(config, protocol, templates)
    assert first == second
    validation = execution.validate_full_roster(first, protocol)
    assert validation["split_pair_counts"] == {"calibration": 32, "locked_test": 64}
    assert validation["cell_count_per_split"] == 8
    assert validation["candidate_count"] == 960
    assert validation["unique_candidate_identity_count"] == 960
    assert validation["seed_count"] == 4800
    assert validation["unique_seed_count"] == 4800
    assert validation["lhs_midpoint_strata_complete"] is True
    assert validation["outcome_inputs_absent"] is True
    assert first[0]["pair_id"] == "calibration_c000_r00"
    assert first[-1]["pair_id"] == "locked_test_c007_r07"
    assert "/media/" not in json.dumps(first)


def test_protocol_seed_derivation_is_exact_and_rejects_undeclared_inputs() -> None:
    config = execution.load_config(CONFIG)
    protocol = execution._protocol(config)
    seed = execution.derive_protocol_seed(
        protocol,
        split="calibration",
        cell_id="cell_000",
        replicate_index=0,
        candidate_index=0,
        channel="scene_seed",
    )
    assert seed == 6231740899753832926
    with pytest.raises(execution.ContractError, match="Undeclared seed channel"):
        execution.derive_protocol_seed(
            protocol,
            split="calibration",
            cell_id="cell_000",
            replicate_index=0,
            candidate_index=0,
            channel="model_outcome_seed",
        )
    with pytest.raises(execution.ContractError, match="outside frozen range"):
        execution.derive_protocol_seed(
            protocol,
            split="calibration",
            cell_id="cell_000",
            replicate_index=0,
            candidate_index=10,
            channel="scene_seed",
        )


def test_full_source_templates_and_derived_asset_partition_are_split_pure() -> None:
    config = execution.load_config(CONFIG)
    templates = execution._scene_template_inventory(config)
    assert templates["cross_split"]["ground_material_overlap"] == []
    assert templates["cross_split"]["environment_overlap"] == []
    assert templates["cross_split"]["base_crop_filename_overlap_count"] > 0
    partition = execution.build_role_asset_partition(config, templates)
    validation = partition["validation"]
    assert validation["filename_overlap_count"] == 0
    assert validation["object_sha256_overlap_count"] == 0
    assert validation["all_template_model_queries_nonempty"] is True
    assert min(validation["crop_model_count_by_role"].values()) >= 6
    calibration = set(partition["roles"]["calibration"]["allowlist"])
    locked_test = set(partition["roles"]["locked_test"]["allowlist"])
    assert calibration.isdisjoint(locked_test)


def test_full_capacity_gate_uses_fixture_measurement_and_conservative_floor() -> None:
    config = execution.load_config(CONFIG)
    preflight = execution.preflight(CONFIG, scope="full")
    receipt = execution.build_full_capacity_receipt(config, preflight)
    projection = receipt["projection"]
    assert receipt["passed"] is True
    assert projection["full_pair_count"] == 96
    assert projection["pair_count_multiplier"] == pytest.approx(48.0)
    assert projection["required_bytes"] >= projection["measured_linear_bytes"]
    assert projection["required_bytes"] == config["runtime"][
        "minimum_full_free_bytes"
    ]
    assert projection["headroom_after_required_and_reserve_bytes"] > 0
    assert projection["absolute_ten_candidate_attempt_ceiling_hours"] == pytest.approx(
        projection["planning_upper_hours_one_candidate_per_slot"] * 10
    )
    constrained = json.loads(json.dumps(preflight))
    constrained["capacity"]["free_bytes"] = (
        projection["required_bytes"] + projection["reserve_bytes"] - 1
    )
    with pytest.raises(execution.ContractError, match="capacity gate failed"):
        execution.build_full_capacity_receipt(config, constrained)


def test_atomic_full_pair_publish_and_resume_is_fail_closed(tmp_path: Path) -> None:
    full_root = tmp_path / "full"
    pair_id = "calibration_c000_r00"
    row = {
        "pair_id": pair_id,
        "protocol_split": "calibration",
        "pair_slot_identity_sha256": "a" * 64,
    }
    staging = (
        full_root / "work" / f".partial-{pair_id}-candidate-00-testnonce"
    )
    staging.mkdir(parents=True)
    execution.write_json(
        staging / "full_pair_receipt.json",
        {
            "contract": execution.FULL_PAIR_RECEIPT_CONTRACT,
            "status": "PASS_FULL_PAIR_PREOUTCOME_SYNTHETIC_ONLY",
            "pair_id": pair_id,
            "protocol_split": "calibration",
            "pair_slot_identity_sha256": "a" * 64,
            "selected_candidate_index": 0,
            "candidate_identity_sha256": "b" * 64,
            "pair_quality_gates": {"all_preoutcome_gates": True},
            "inventory_sha256": "c" * 64,
            "model_outputs_present_false": True,
        },
    )
    destination = full_root / "pairs/calibration" / pair_id
    published = execution.atomic_publish_full_pair(
        full_root, staging, destination, row
    )
    assert published["published_atomically"] is True
    state = execution.inspect_full_render_state(full_root, [row])
    assert state["completed_pair_ids"] == [pair_id]
    assert state["pending_pair_count"] == 0
    assert state["model_outputs_present"] is False
    retry_staging = (
        full_root / "work" / f".partial-{pair_id}-candidate-01-retrynonce"
    )
    retry_staging.mkdir(parents=True)
    with pytest.raises(execution.ContractError, match="overwrite"):
        execution.atomic_publish_full_pair(
            full_root, retry_staging, destination, row
        )


def test_interrupted_full_pair_cleanup_is_exact_and_bounded(tmp_path: Path) -> None:
    full_root = tmp_path / "full"
    pair_id = "calibration_c000_r00"
    selected = full_root / "work" / f".partial-{pair_id}-candidate-00-a"
    selected_two = full_root / "work" / f".partial-{pair_id}-candidate-01-b"
    unrelated = (
        full_root / "work" / ".partial-calibration_c000_r01-candidate-00-c"
    )
    for path in (selected, selected_two, unrelated):
        path.mkdir(parents=True)
    result = execution.cleanup_interrupted_full_pair_staging(full_root, pair_id)
    assert result["removed"] == [selected.name, selected_two.name]
    assert not selected.exists() and not selected_two.exists()
    assert unrelated.is_dir()
    with pytest.raises(execution.ContractError, match="Unsafe"):
        execution.cleanup_interrupted_full_pair_staging(full_root, "../escape")


def test_atomic_full_pair_rejects_prediction_or_failed_gate(tmp_path: Path) -> None:
    full_root = tmp_path / "full"
    pair_id = "locked_test_c000_r00"
    row = {
        "pair_id": pair_id,
        "protocol_split": "locked_test",
        "pair_slot_identity_sha256": "d" * 64,
    }
    staging = (
        full_root / "work" / f".partial-{pair_id}-candidate-00-testnonce"
    )
    staging.mkdir(parents=True)
    execution.write_json(
        staging / "full_pair_receipt.json",
        {
            "contract": execution.FULL_PAIR_RECEIPT_CONTRACT,
            "status": "PASS_FULL_PAIR_PREOUTCOME_SYNTHETIC_ONLY",
            "pair_id": pair_id,
            "protocol_split": "locked_test",
            "pair_slot_identity_sha256": "d" * 64,
            "pair_quality_gates": {"pixel_visual": False},
            "model_outputs_present_false": True,
        },
    )
    with pytest.raises(execution.ContractError, match="not publishable"):
        execution.atomic_publish_full_pair(
            full_root,
            staging,
            full_root / "pairs/locked_test" / pair_id,
            row,
        )


def test_full_gate_and_atomic_contract_forbid_model_and_outcome_access() -> None:
    config = execution.load_config(CONFIG)
    protocol = execution._protocol(config)
    gates = execution.build_candidate_gate_contract(protocol)
    atomic = execution.build_atomic_render_state_contract(config)
    assert gates["model_or_outcome_inputs_allowed"] is False
    assert gates["prediction_file_access_allowed"] is False
    assert gates["registered_target_access_allowed"] is False
    assert gates["selected_candidate_is_first_passing_index"] is True
    assert atomic["model_access_allowed"] is False
    assert atomic["overwrite_allowed"] is False
    assert atomic["atomic_state_machine_implemented"] is True


def test_first_full_candidate_derivation_binds_assets_seeds_and_capture_arms() -> None:
    config = execution.load_config(CONFIG)
    row = execution.full_roster_row(config, "calibration_c000_r00")
    candidate = row["candidates"][0]
    partition = execution.load_json(
        execution.full_paths(config)["synthetic"]
        / "planning/asset_partition_v1.json"
    )
    role = partition["roles"]["calibration"]
    source = execution.full_candidate_source_path(config, row, candidate)
    derived = execution.derive_full_native_scene_config(
        execution.load_yaml(source), row, candidate, role, config
    )
    render = derived["render"]
    contract = derived["full_execution_contract"]
    assert (render["resolution_x"], render["resolution_y"]) == (2048, 2048)
    assert render["frames"] == 30
    assert render["samples"] == 16
    assert derived["field"]["random_seed"] == 6231740899753832926
    assert contract["seeds"] == candidate["seeds"]
    assert contract["seed_channels_exact"] == [
        "scene_seed",
        "trajectory_seed",
        "capture_draw_seed",
        "renderer_seed",
        "audit_sample_seed",
    ]
    assert contract["role_asset_allowlist_sha256"] == role["allowlist_sha256"]
    assert contract["ideal_capture_parameters"] != contract[
        "degraded_capture_parameters"
    ]
    assert contract["model_access_allowed"] is False
    assert contract["outcome_inputs"] == []
    assert min(
        weed["density"] for weed in derived["field"]["weeds"].values()
    ) >= config["full_benchmark"]["weed_density_minimum_per_family"]


def test_full_runtime_overlay_is_deterministic_and_model_free() -> None:
    first = execution.full_runtime_overlay_patch()
    second = execution.full_runtime_overlay_patch()
    assert first == second
    text = first.decode("utf-8")
    assert "core/full_ab.py" in text
    assert "full_ab.render_capture_arms" in text
    assert "full_ab.filter_models" in text
    assert "deterministic_replay_ideal_rgb" in text
    assert "model_access_allowed" in text
    assert "model.predict" not in text
    assert "ultralytics" not in text
    assert execution.full_render_implementation_sha256() == (
        execution.full_render_implementation_sha256()
    )


def test_full_candidate_gate_is_preoutcome_and_rejects_bad_pixel_operability() -> None:
    config = execution.load_config(CONFIG)
    row = execution.full_roster_row(config, "calibration_c000_r00")
    condition = {
        "mean_brightness_minimum": 100.0,
        "mean_brightness_mean": 110.0,
        "mean_brightness_maximum": 120.0,
        "fully_clipped_white_fraction_maximum": 0.0,
        "fully_clipped_black_fraction_maximum": 0.0,
    }
    pair = {
        "pixel_audit": {"ideal": dict(condition), "degraded": dict(condition)},
        "semantic_audit": {
            "mean_crop_fraction": 0.02,
            "mean_weed_fraction": 0.02,
            "crop_free_frame_fraction": 0.0,
            "weed_free_frame_fraction": 0.0,
        },
        "capture_difference": {"changed_pixel_fraction_minimum": 0.5},
        "arm_gt_identity": {"byte_identical": True},
        "frame_count_per_arm": 30,
        "native_dimensions_px": [2048, 2048],
        "frame_rate_hz": 15,
        "quality_gates": {"all_videos_readable": True},
        "visible_eligible_weed_track_count": 2,
        "temporal_audit": {
            "eligible_track_with_at_least_three_observations": True
        },
    }
    botanical = {
        "quality_gates": {"source_identity": True},
        "track_count": 4,
        "weed_track_count": 2,
    }
    assets = {
        "all_used_and_exposed_assets_allowed": True,
        "used_asset_count": 3,
    }
    capture = {
        "deterministic_replay": {
            "all_frames_pixel_exact": True,
            "all_png_bytes_exact": True,
        },
        "seed_bindings": {
            name: {"value": value}
            for name, value in row["candidates"][0]["seeds"].items()
        },
    }
    result = execution.evaluate_full_candidate_gates(
        pair, botanical, assets, capture, row, config
    )
    assert all(result["pair_quality_gates"].values())
    assert result["model_or_outcome_inputs"] == []
    pair["semantic_audit"]["mean_crop_fraction"] = 0.001
    with pytest.raises(execution.CandidateRejected, match="pixel_and_visual"):
        execution.evaluate_full_candidate_gates(
            pair, botanical, assets, capture, row, config
        )


def test_gt_scout_overlay_is_deterministic_gt_only_and_model_free() -> None:
    first = execution.gt_scout_runtime_overlay_patch()
    second = execution.gt_scout_runtime_overlay_patch()
    assert first == second
    text = first.decode("utf-8")
    assert "core/gt_scout.py" in text
    assert "gt_scout.bind_trajectory_only" in text
    assert "gt_scout.write_runner_proxies" in text
    assert "full_ab.render_capture_arms" in text
    assert "rgb_capture_rendered" in text
    assert "model.predict" not in text
    assert "ultralytics" not in text


def test_gt_scout_decision_can_reject_only_frozen_semantic_or_eligibility() -> None:
    config = execution.load_config(CONFIG)
    contract = execution.gt_scout_decision_contract(config)
    assert contract["permitted_rejection_families"] == [
        "frozen_semantic_operability",
        "frozen_eligible_weed_temporal_denominator",
    ]
    assert contract["pass_authority"] == "none_full_render_required"
    assert contract["model_or_outcome_inputs_allowed"] is False
    passing = {
        "pair_id": "calibration_c000_r01",
        "visible_eligible_weed_track_count": 1,
        "semantic_audit": {
            "mean_crop_fraction": 0.10,
            "mean_weed_fraction": 0.02,
            "crop_free_frame_fraction": 0.0,
            "weed_free_frame_fraction": 0.0,
        },
        "temporal_audit": {
            "eligible_track_with_at_least_three_observations": True,
        },
    }
    passed = execution.evaluate_gt_scout_decision(passing, config)
    assert passed["rejectable_by_scout"] is False
    assert passed["full_render_still_required_for_acceptance"] is True
    rejected = copy.deepcopy(passing)
    rejected["semantic_audit"]["mean_weed_fraction"] = 0.001
    rejected["visible_eligible_weed_track_count"] = 0
    rejected["temporal_audit"][
        "eligible_track_with_at_least_three_observations"
    ] = False
    failed = execution.evaluate_gt_scout_decision(rejected, config)
    assert failed["rejectable_by_scout"] is True
    assert failed["rejection_reasons"] == [
        "semantic:mean_weed_fraction_in_range",
        "eligibility:eligible_weed_track_present",
        "eligibility:eligible_track_with_at_least_three_observations",
    ]
    assert failed["model_or_outcome_inputs_used"] is False


def test_gt_scout_candidate_selection_uses_canonical_roster_order(tmp_path: Path) -> None:
    config = execution.load_config(CONFIG)
    row = execution.full_roster_row(config, "calibration_c000_r01")
    planning = tmp_path / "planning"
    planning.mkdir()
    execution.write_jsonl(
        planning / "candidate_rejection_ledger_v1.jsonl",
        [
            {
                "pair_id": row["pair_id"],
                "candidate_index": 0,
                "candidate_identity_sha256": row["candidates"][0][
                    "candidate_identity_sha256"
                ],
            }
        ],
    )
    selected = execution._next_gt_scout_candidate(tmp_path, row)
    assert selected["candidate_index"] == 1
    tampered = execution.read_jsonl(
        planning / "candidate_rejection_ledger_v1.jsonl"
    )
    tampered[0]["candidate_identity_sha256"] = "0" * 64
    execution.write_jsonl(
        planning / "candidate_rejection_ledger_v1.jsonl", tampered
    )
    with pytest.raises(execution.ContractError, match="identity changed"):
        execution._next_gt_scout_candidate(tmp_path, row)


def test_gt_scout_rejection_commit_is_reject_only_and_idempotent(
    tmp_path: Path,
) -> None:
    config = execution.load_config(CONFIG)
    row = execution.full_roster_row(config, "calibration_c000_r01")
    candidate = row["candidates"][0]
    planning = tmp_path / "planning"
    planning.mkdir()
    execution.write_jsonl(
        planning / "candidate_rejection_ledger_v1.jsonl", []
    )
    destination = tmp_path / "scout_result"
    destination.mkdir()
    execution.write_json(
        destination / "gt_scout_terminal_receipt.json", {"status": "REJECT"}
    )
    decision = {
        "rejectable_by_scout": True,
        "rejection_reasons": ["semantic:mean_weed_fraction_in_range"],
    }
    execution.write_json(destination / "decision_receipt.json", decision)
    first = execution._commit_gt_scout_rejection(
        tmp_path, destination, row, candidate, decision
    )
    second = execution._commit_gt_scout_rejection(
        tmp_path, destination, row, candidate, decision
    )
    ledger = execution.read_jsonl(
        planning / "candidate_rejection_ledger_v1.jsonl"
    )
    assert first["appended_by_this_call"] is True
    assert second["appended_by_this_call"] is False
    assert len(ledger) == 1
    assert ledger[0]["reason_type"] == "GtScoutCandidateRejected"
    assert ledger[0]["model_or_outcome_inputs_used"] is False
    assert ledger[0]["bulk_payload_retained"] is False
    with pytest.raises(execution.ContractError, match="passing candidate"):
        execution._commit_gt_scout_rejection(
            tmp_path,
            destination,
            row,
            candidate,
            {"rejectable_by_scout": False, "rejection_reasons": []},
        )


def test_gt_scout_rejection_commit_accepts_only_exact_recovery_terminal(
    tmp_path: Path,
) -> None:
    config = execution.load_config(CONFIG)
    row = execution.full_roster_row(config, "calibration_c000_r03")
    candidate = row["candidates"][1]
    planning = tmp_path / "planning"
    planning.mkdir()
    execution.write_jsonl(planning / "candidate_rejection_ledger_v1.jsonl", [])
    destination = tmp_path / "recovery_result"
    destination.mkdir()
    recovery_terminal = destination / "recovery_terminal_receipt.json"
    execution.write_json(recovery_terminal, {"status": "ZERO_WEED_REJECT"})
    decision = {
        "contract": execution.GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
        "rejectable_by_scout": True,
        "rejection_reasons": ["eligibility:source_weed_track_present"],
    }
    execution.write_json(destination / "decision_receipt.json", decision)
    committed = execution._commit_gt_scout_rejection(
        tmp_path, destination, row, candidate, decision
    )
    ledger = execution.read_jsonl(
        planning / "candidate_rejection_ledger_v1.jsonl"
    )
    assert committed["appended_by_this_call"] is True
    assert ledger[0]["gt_scout_terminal_receipt_sha256"] == (
        execution.sha256_file(recovery_terminal)
    )
    assert ledger[0]["reason"] == "eligibility:source_weed_track_present"

    other = tmp_path / "invalid_recovery_result"
    other.mkdir()
    execution.write_json(other / "recovery_terminal_receipt.json", {})
    execution.write_json(other / "decision_receipt.json", decision)
    wrong = dict(decision, rejection_reasons=["eligibility:different"])
    with pytest.raises(execution.ContractError, match="terminal receipt is missing"):
        execution._commit_gt_scout_rejection(
            tmp_path, other, row, row["candidates"][2], wrong
        )


def test_gt_scout_auditor_reproduces_published_candidate6_gt(tmp_path: Path) -> None:
    config = execution.load_config(CONFIG)
    row = execution.full_roster_row(config, "calibration_c000_r00")
    pair_root = (
        execution.full_paths(config)["synthetic"]
        / "pairs/calibration/calibration_c000_r00"
    )
    audit = execution.audit_gt_scout_scene(
        pair_root / "source_scene", tmp_path, row, config
    )
    pair_receipt = execution.load_json(pair_root / "pair_receipt.json")
    assert audit["canonical_gt_sha256"] == pair_receipt["canonical_gt_sha256"]
    assert audit["semantic_audit"] == pair_receipt["semantic_audit"]
    assert audit["temporal_audit"] == pair_receipt["temporal_audit"]
    assert audit["visible_eligible_weed_track_count"] == pair_receipt[
        "visible_eligible_weed_track_count"
    ]


def test_gt_scout_preserves_exact_sealed_full_render_lock() -> None:
    config = execution.load_config(CONFIG)
    sealed = execution._validate_sealed_full_render_lock(config)
    assert execution.full_render_implementation_sha256() == (
        execution.SEALED_FULL_RENDER_IMPLEMENTATION_SHA256
    )
    assert sealed["sha256"] == (
        execution.SEALED_FULL_RENDER_EXECUTION_LOCK_SHA256
    )


def test_zero_source_weed_recovery_accepts_only_exact_locked_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = copy.deepcopy(execution.load_config(CONFIG))
    config["native_contract"]["width_px"] = 1
    config["native_contract"]["height_px"] = 1
    scene = tmp_path / "scene"
    gt = scene / "botanical_ground_truth"
    instance = gt / "instance_masks"
    semantic = scene / "render/masks"
    instance.mkdir(parents=True)
    semantic.mkdir(parents=True)
    source = {
        "source_scene_graph_identity_sha256": "4" * 64,
        "tracks": [
            {
                "track_id": "crop/row/000000",
                "render_id": 1,
                "class_name": "crop",
            }
        ],
    }
    execution.write_json(gt / "source_objects.json", source)
    execution.write_json(gt / "track_registry.json", {"frame_count": 30})
    execution.write_jsonl(
        gt / "tracks.jsonl",
        [
            {
                "frame_id": f"frame_{frame_index + 1:04d}",
                "track_id": "crop/row/000000",
            }
            for frame_index in range(30)
        ],
    )
    for frame_index in range(30):
        name = f"frame_{frame_index + 1:04d}.png"
        execution.Image.new("RGB", (1, 1)).save(instance / name)
        execution.Image.new("RGB", (1, 1)).save(semantic / name)

    def exact_failure(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("Too few source weed tracks: 0")

    monkeypatch.setattr(execution, "validate_botanical_scene", exact_failure)
    audit = execution._audit_zero_source_weed_failure(scene, config)
    assert audit["source_crop_track_count"] == 1
    assert audit["source_weed_track_count"] == 0
    assert audit["track_table_full_grid"] is True
    assert audit["rejection_reason"] == "eligibility:source_weed_track_present"
    assert audit["model_or_outcome_inputs_used"] is False

    def different_failure(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("different source failure")

    monkeypatch.setattr(execution, "validate_botanical_scene", different_failure)
    with pytest.raises(execution.ContractError, match="different validator failure"):
        execution._audit_zero_source_weed_failure(scene, config)


def test_source_cardinality_recovery_is_separate_from_sealed_workers() -> None:
    recovery = execution.gt_source_cardinality_recovery_implementation_sha256()
    assert recovery == execution.gt_source_cardinality_recovery_implementation_sha256()
    assert recovery not in {
        execution.SEALED_FULL_RENDER_IMPLEMENTATION_SHA256,
        execution.gt_scout_implementation_sha256(),
        execution.calibration_batch_implementation_sha256(),
    }
    assert execution.full_render_implementation_sha256() == (
        execution.SEALED_FULL_RENDER_IMPLEMENTATION_SHA256
    )
    source = execution.inspect.getsource(
        execution.run_gt_source_cardinality_recovery
    )
    assert "locked_test" not in source
    assert "run_fixture_inference" not in source
    assert "eligibility:source_weed_track_present" in source


def test_locked_test_zero_source_recovery_context_binds_active_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full_root = tmp_path / "full"
    paths = {
        "synthetic": full_root,
        "docs": tmp_path / "docs",
        "run": tmp_path / "runs",
    }
    rows = [
        {"pair_id": "calibration_c000_r00", "protocol_split": "calibration"},
        {
            "pair_id": "locked_test_c000_r00",
            "protocol_split": "locked_test",
            "evaluator_split": "test",
        },
    ]
    state = {
        "completed_pair_ids": ["calibration_c000_r00"],
        "pending_pair_ids": ["locked_test_c000_r00"],
        "model_outputs_present": False,
    }
    monkeypatch.setattr(
        execution, "inspect_full_render_state", lambda _root, _rows: state
    )
    batch_id = "locked_test_render_batch_locked_test_c000_r00_deadbeef"
    request = {
        "contract": execution.LOCKED_TEST_RENDER_BATCH_CONTRACT,
        "protocol_split": "locked_test",
        "target_pair_ids": ["locked_test_c000_r00"],
        "render_and_machine_audit_only": True,
        "model_access_allowed": False,
        "prediction_access_allowed": False,
        "locked_test_outcome_access_allowed": False,
    }
    intent = {
        "status": "LOCKED_TEST_RENDER_BATCH_INTENT_PREOUTCOME_SYNTHETIC_ONLY",
        "batch_id": batch_id,
        "request_identity_sha256": execution.stable_sha256(request),
        "request": request,
        "locked_test_predictions_present_at_start": False,
        "model_loaded": False,
        "inference_calls": 0,
        "outcome_inputs": [],
    }
    intent_path = (
        full_root
        / "planning/locked_test_render_batches_v1"
        / batch_id
        / "batch_intent.json"
    )
    execution.write_json(intent_path, intent)

    row, validated_intent, validated_state, batch_root = (
        execution._validate_locked_test_zero_source_recovery_context(
            {}, paths, rows, "locked_test_c000_r00", batch_id
        )
    )
    assert row["protocol_split"] == "locked_test"
    assert validated_intent == intent
    assert validated_state == state
    assert batch_root == intent_path.parent

    request["prediction_access_allowed"] = True
    intent["request_identity_sha256"] = execution.stable_sha256(request)
    execution.write_json(intent_path, intent)
    with pytest.raises(execution.ContractError, match="intent changed"):
        execution._validate_locked_test_zero_source_recovery_context(
            {}, paths, rows, "locked_test_c000_r00", batch_id
        )


def test_locked_test_source_cardinality_recovery_is_separate_and_cli_bound() -> None:
    legacy = execution.gt_source_cardinality_recovery_implementation_sha256()
    recovery = (
        execution.locked_test_gt_source_cardinality_recovery_implementation_sha256()
    )
    assert recovery == (
        execution.locked_test_gt_source_cardinality_recovery_implementation_sha256()
    )
    assert recovery not in {
        legacy,
        execution.SEALED_FULL_RENDER_IMPLEMENTATION_SHA256,
        execution.gt_scout_implementation_sha256(),
        execution.calibration_batch_implementation_sha256(),
        execution.locked_test_render_batch_implementation_sha256(),
    }
    assert execution.full_render_implementation_sha256() == (
        execution.SEALED_FULL_RENDER_IMPLEMENTATION_SHA256
    )
    assert execution.locked_test_render_batch_implementation_sha256() == (
        "8fcb95eeac50260068244809db9fe1e34aa208571d81dae137976dd98f423e70"
    )
    legacy_source = execution.inspect.getsource(
        execution.run_gt_source_cardinality_recovery
    )
    source = execution.inspect.getsource(
        execution.run_locked_test_gt_source_cardinality_recovery
    )
    assert "locked_test" not in legacy_source
    assert "locked_test" in source
    assert "_audit_zero_source_weed_failure" in source
    assert "run_fixture_inference" not in source
    parsed = execution.parse_args(
        [
            "full-recover-zero-weed-locked-test-scout",
            "--pair-id",
            "locked_test_c000_r01",
            "--candidate-index",
            "0",
            "--batch-id",
            "locked_test_render_batch_locked_test_c000_r00_deadbeef",
        ]
    )
    assert parsed.command == "full-recover-zero-weed-locked-test-scout"
    assert parsed.pair_id == "locked_test_c000_r01"
    assert parsed.candidate_index == 0
    assert parsed.batch_id.endswith("deadbeef")


def test_calibration_batch_targets_are_explicit_contiguous_and_calibration_only() -> None:
    config = execution.load_config(CONFIG)
    rows = execution.full_roster_rows(config)
    selected = execution._validate_calibration_batch_targets(
        rows,
        ["calibration_c000_r02", "calibration_c000_r03"],
        1,
    )
    assert [row["pair_id"] for row in selected] == [
        "calibration_c000_r02",
        "calibration_c000_r03",
    ]
    with pytest.raises(execution.ContractError, match="locked-test"):
        execution._validate_calibration_batch_targets(
            rows, ["locked_test_c000_r00"], 1
        )
    with pytest.raises(execution.ContractError, match="contiguous"):
        execution._validate_calibration_batch_targets(
            rows,
            ["calibration_c000_r02", "calibration_c001_r00"],
            1,
        )
    with pytest.raises(execution.ContractError, match="limit"):
        execution._validate_calibration_batch_targets(
            rows, ["calibration_c000_r02"], 2
        )


def test_calibration_batch_has_separate_lock_without_changing_sealed_workers() -> None:
    first = execution.calibration_batch_implementation_sha256()
    second = execution.calibration_batch_implementation_sha256()
    assert first == second
    assert first not in {
        execution.SEALED_FULL_RENDER_IMPLEMENTATION_SHA256,
        execution.gt_scout_implementation_sha256(),
    }
    assert execution.full_render_implementation_sha256() == (
        execution.SEALED_FULL_RENDER_IMPLEMENTATION_SHA256
    )
    source = execution.inspect.getsource(execution.run_calibration_batch)
    assert "run_gt_scout_candidate" in source
    assert "render_full_pair" in source
    assert "locked_test_outcome_accessed" in source
    assert "run_fixture_inference" not in source


def test_locked_test_render_batch_targets_are_explicit_contiguous_and_split_locked() -> None:
    config = execution.load_config(CONFIG)
    rows = execution.full_roster_rows(config)
    selected = execution._validate_locked_test_render_batch_targets(
        rows,
        ["locked_test_c000_r00", "locked_test_c000_r01"],
        1,
    )
    assert [row["pair_id"] for row in selected] == [
        "locked_test_c000_r00",
        "locked_test_c000_r01",
    ]
    with pytest.raises(execution.ContractError, match="calibration"):
        execution._validate_locked_test_render_batch_targets(
            rows, ["calibration_c000_r00"], 1
        )
    with pytest.raises(execution.ContractError, match="contiguous"):
        execution._validate_locked_test_render_batch_targets(
            rows,
            ["locked_test_c000_r00", "locked_test_c000_r02"],
            1,
        )
    with pytest.raises(execution.ContractError, match="limit"):
        execution._validate_locked_test_render_batch_targets(
            rows, ["locked_test_c000_r00"], 2
        )


def test_locked_test_render_batch_access_guard_fails_closed(
    tmp_path: Path,
) -> None:
    rows = [
        {"pair_id": "calibration_c000_r00", "protocol_split": "calibration"},
        {"pair_id": "locked_test_c000_r00", "protocol_split": "locked_test"},
    ]
    paths = {"run": tmp_path / "model_run"}
    valid_state = {
        "completed_pair_ids": ["calibration_c000_r00"],
        "model_outputs_present": False,
    }
    execution._assert_locked_test_render_batch_access_guard(
        paths, rows, valid_state
    )
    with pytest.raises(execution.ContractError, match="complete calibration"):
        execution._assert_locked_test_render_batch_access_guard(
            paths,
            rows,
            {"completed_pair_ids": [], "model_outputs_present": False},
        )
    with pytest.raises(execution.ContractError, match="model output"):
        execution._assert_locked_test_render_batch_access_guard(
            paths,
            rows,
            {
                "completed_pair_ids": ["calibration_c000_r00"],
                "model_outputs_present": True,
            },
        )
    paths["run"].mkdir()
    with pytest.raises(execution.ContractError, match="model run root"):
        execution._assert_locked_test_render_batch_access_guard(
            paths, rows, valid_state
        )


def test_locked_test_render_batch_has_separate_sealed_implementation() -> None:
    first = execution.locked_test_render_batch_implementation_sha256()
    second = execution.locked_test_render_batch_implementation_sha256()
    assert first == second
    assert first not in {
        execution.SEALED_FULL_RENDER_IMPLEMENTATION_SHA256,
        execution.gt_scout_implementation_sha256(),
        execution.calibration_batch_implementation_sha256(),
    }
    assert execution.full_render_implementation_sha256() == (
        execution.SEALED_FULL_RENDER_IMPLEMENTATION_SHA256
    )
    source = execution.inspect.getsource(execution.run_locked_test_render_batch)
    assert "run_gt_scout_candidate" in source
    assert "render_full_pair" in source
    assert "locked_test_prediction_accessed" in source
    assert "locked_test_outcome_accessed" in source
    assert "run_fixture_inference" not in source


def test_calibration_batch_reject_pass_stop_and_resume_are_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full_root = tmp_path / "full"
    docs_root = tmp_path / "docs"
    planning = full_root / "planning"
    planning.mkdir(parents=True)
    ledger_path = planning / "candidate_rejection_ledger_v1.jsonl"
    execution.write_jsonl(ledger_path, [])
    pair_id = "calibration_c000_r02"
    candidates = [
        {
            "candidate_index": 0,
            "candidate_identity_sha256": "1" * 64,
        },
        {
            "candidate_index": 1,
            "candidate_identity_sha256": "2" * 64,
        },
    ]
    row = {
        "pair_id": pair_id,
        "protocol_split": "calibration",
        "evaluator_split": "calibration",
        "pair_slot_identity_sha256": "3" * 64,
        "candidates": candidates,
    }
    published: set[str] = set()
    scout_calls: list[int] = []
    render_calls: list[int] = []

    def fake_state(
        _full_root: Path, state_rows: list[dict[str, object]]
    ) -> dict[str, object]:
        ids = [str(item["pair_id"]) for item in state_rows]
        completed = [item for item in ids if item in published]
        pending = [item for item in ids if item not in published]
        return {
            "planned_pair_count": len(ids),
            "completed_pair_count": len(completed),
            "pending_pair_count": len(pending),
            "completed_pair_ids": completed,
            "pending_pair_ids": pending,
            "interrupted_staging_directories": [],
            "model_outputs_present": False,
        }

    def fake_scout(_config_path: Path, selected_pair_id: str) -> dict[str, object]:
        candidate = execution._next_gt_scout_candidate(full_root, row)
        index = int(candidate["candidate_index"])
        scout_calls.append(index)
        destination = (
            planning
            / "gt_scout_v1/roster"
            / selected_pair_id
            / f"candidate_{index:02d}"
        )
        destination.mkdir(parents=True)
        rejected = index == 0
        decision = {
            "status": (
                "REJECT_FROZEN_GT_ONLY_PREOUTCOME_SYNTHETIC_ONLY"
                if rejected
                else "PASS_GT_ONLY_FULL_RENDER_REQUIRED_SYNTHETIC_ONLY"
            ),
            "rejectable_by_scout": rejected,
            "full_render_still_required_for_acceptance": True,
            "rejection_reasons": (
                ["semantic:mean_weed_fraction_in_range"] if rejected else []
            ),
        }
        execution.write_json(destination / "decision_receipt.json", decision)
        execution.write_json(
            destination / "gt_scout_terminal_receipt.json",
            {
                "status": decision["status"],
                "candidate_identity_sha256": candidate[
                    "candidate_identity_sha256"
                ],
            },
        )
        commit = None
        if rejected:
            rejection = {
                "pair_id": selected_pair_id,
                "candidate_index": index,
                "candidate_identity_sha256": candidate[
                    "candidate_identity_sha256"
                ],
                "reason_type": "GtScoutCandidateRejected",
                "reason": "semantic:mean_weed_fraction_in_range",
                "model_or_outcome_inputs_used": False,
            }
            execution.write_jsonl(ledger_path, [rejection])
            commit = {"appended_by_this_call": True}
        return {
            "status": decision["status"],
            "pair_id": selected_pair_id,
            "candidate_index": index,
            "destination": str(destination),
            "ledger_commit": commit,
            "model_loaded": False,
            "inference_calls": 0,
        }

    def fake_render(_config_path: Path, selected_pair_id: str) -> dict[str, object]:
        candidate = execution._next_gt_scout_candidate(full_root, row)
        index = int(candidate["candidate_index"])
        render_calls.append(index)
        destination = full_root / "pairs/calibration" / selected_pair_id
        destination.mkdir(parents=True)
        terminal = {
            "contract": execution.FULL_PAIR_RECEIPT_CONTRACT,
            "status": "PASS_FULL_PAIR_PREOUTCOME_SYNTHETIC_ONLY",
            "pair_id": selected_pair_id,
            "protocol_split": "calibration",
            "pair_slot_identity_sha256": row["pair_slot_identity_sha256"],
            "selected_candidate_index": index,
            "candidate_identity_sha256": candidate[
                "candidate_identity_sha256"
            ],
            "canonical_gt_sha256": "4" * 64,
            "pair_quality_gates": {"all_preoutcome_gates": True},
            "inventory_sha256": "5" * 64,
            "model_outputs_present_false": True,
        }
        execution.write_json(destination / "full_pair_receipt.json", terminal)
        published.add(selected_pair_id)
        return {
            "status": terminal["status"],
            "pair_id": selected_pair_id,
            "full_pair_receipt_sha256": execution.sha256_file(
                destination / "full_pair_receipt.json"
            ),
            "model_loaded": False,
            "inference_calls": 0,
        }

    monkeypatch.setattr(
        execution,
        "validate_full_plan",
        lambda _path: {"pair_roster_sha256": "6" * 64},
    )
    monkeypatch.setattr(execution, "full_roster_rows", lambda _config: [row])
    monkeypatch.setattr(
        execution,
        "full_paths",
        lambda _config: {
            "synthetic": full_root,
            "docs": docs_root,
            "run": tmp_path / "runs",
        },
    )
    monkeypatch.setattr(
        execution,
        "ensure_calibration_batch_execution_lock",
        lambda _path, _config, _plan: {"sha256": "7" * 64},
    )
    monkeypatch.setattr(execution, "inspect_full_render_state", fake_state)
    monkeypatch.setattr(
        execution,
        "preflight",
        lambda _path, scope: {
            "scope": scope,
            "gpu": {"memory_free_mib": 23000},
        },
    )
    monkeypatch.setattr(
        execution,
        "build_full_capacity_receipt",
        lambda _config, _preflight: {
            "projection": {"passed": True, "required_bytes": 180000000000}
        },
    )
    monkeypatch.setattr(execution, "run_gt_scout_candidate", fake_scout)
    monkeypatch.setattr(execution, "render_full_pair", fake_render)

    first = execution.run_calibration_batch(
        CONFIG, [pair_id], max_new_pairs=1
    )
    assert first["status"] == (
        "PASS_CALIBRATION_BATCH_PREOUTCOME_SYNTHETIC_ONLY"
    )
    assert first["new_pair_ids"] == [pair_id]
    assert scout_calls == [0, 1]
    assert render_calls == [1]
    receipt_path = next(
        (planning / "calibration_batches_v1").glob("*/batch_receipt.json")
    )
    receipt = execution.load_json(receipt_path)
    assert receipt["new_pair_count"] == 1
    assert len(receipt["canonical_rejection_rows"]) == 1
    assert receipt["locked_test_outcome_accessed"] is False
    assert receipt["model_loaded"] is False
    assert receipt["inference_calls"] == 0

    second = execution.run_calibration_batch(
        CONFIG, [pair_id], max_new_pairs=1
    )
    assert second["status"] == (
        "SKIP_EXISTING_PASS_CALIBRATION_BATCH_PREOUTCOME_SYNTHETIC_ONLY"
    )
    assert second["batch_receipt_sha256"] == first["batch_receipt_sha256"]
    assert scout_calls == [0, 1]
    assert render_calls == [1]


def test_locked_test_render_batch_reject_pass_stop_and_resume_are_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full_root = tmp_path / "full"
    docs_root = tmp_path / "docs"
    planning = full_root / "planning"
    planning.mkdir(parents=True)
    ledger_path = planning / "candidate_rejection_ledger_v1.jsonl"
    execution.write_jsonl(ledger_path, [])
    calibration_id = "calibration_c007_r03"
    pair_id = "locked_test_c000_r00"
    candidates = [
        {
            "candidate_index": 0,
            "candidate_identity_sha256": "1" * 64,
        },
        {
            "candidate_index": 1,
            "candidate_identity_sha256": "2" * 64,
        },
    ]
    calibration_row = {
        "pair_id": calibration_id,
        "protocol_split": "calibration",
    }
    row = {
        "pair_id": pair_id,
        "protocol_split": "locked_test",
        "evaluator_split": "test",
        "pair_slot_identity_sha256": "3" * 64,
        "candidates": candidates,
    }
    rows = [calibration_row, row]
    published: set[str] = {calibration_id}
    scout_calls: list[int] = []
    render_calls: list[int] = []

    def fake_state(
        _full_root: Path, state_rows: list[dict[str, object]]
    ) -> dict[str, object]:
        ids = [str(item["pair_id"]) for item in state_rows]
        completed = [item for item in ids if item in published]
        pending = [item for item in ids if item not in published]
        return {
            "planned_pair_count": len(ids),
            "completed_pair_count": len(completed),
            "pending_pair_count": len(pending),
            "completed_pair_ids": completed,
            "pending_pair_ids": pending,
            "interrupted_staging_directories": [],
            "model_outputs_present": False,
        }

    def fake_scout(_config_path: Path, selected_pair_id: str) -> dict[str, object]:
        candidate = execution._next_gt_scout_candidate(full_root, row)
        index = int(candidate["candidate_index"])
        scout_calls.append(index)
        destination = (
            planning
            / "gt_scout_v1/roster"
            / selected_pair_id
            / f"candidate_{index:02d}"
        )
        destination.mkdir(parents=True)
        rejected = index == 0
        decision = {
            "status": (
                "REJECT_FROZEN_GT_ONLY_PREOUTCOME_SYNTHETIC_ONLY"
                if rejected
                else "PASS_GT_ONLY_FULL_RENDER_REQUIRED_SYNTHETIC_ONLY"
            ),
            "rejectable_by_scout": rejected,
            "full_render_still_required_for_acceptance": True,
            "rejection_reasons": (
                ["semantic:mean_weed_fraction_in_range"] if rejected else []
            ),
        }
        execution.write_json(destination / "decision_receipt.json", decision)
        execution.write_json(
            destination / "gt_scout_terminal_receipt.json",
            {
                "status": decision["status"],
                "candidate_identity_sha256": candidate[
                    "candidate_identity_sha256"
                ],
            },
        )
        commit = None
        if rejected:
            rejection = {
                "pair_id": selected_pair_id,
                "candidate_index": index,
                "candidate_identity_sha256": candidate[
                    "candidate_identity_sha256"
                ],
                "reason_type": "GtScoutCandidateRejected",
                "reason": "semantic:mean_weed_fraction_in_range",
                "model_or_outcome_inputs_used": False,
            }
            execution.write_jsonl(ledger_path, [rejection])
            commit = {"appended_by_this_call": True}
        return {
            "status": decision["status"],
            "pair_id": selected_pair_id,
            "candidate_index": index,
            "destination": str(destination),
            "ledger_commit": commit,
            "model_loaded": False,
            "inference_calls": 0,
        }

    def fake_render(_config_path: Path, selected_pair_id: str) -> dict[str, object]:
        candidate = execution._next_gt_scout_candidate(full_root, row)
        index = int(candidate["candidate_index"])
        render_calls.append(index)
        destination = full_root / "pairs/locked_test" / selected_pair_id
        destination.mkdir(parents=True)
        terminal = {
            "contract": execution.FULL_PAIR_RECEIPT_CONTRACT,
            "status": "PASS_FULL_PAIR_PREOUTCOME_SYNTHETIC_ONLY",
            "pair_id": selected_pair_id,
            "protocol_split": "locked_test",
            "pair_slot_identity_sha256": row["pair_slot_identity_sha256"],
            "selected_candidate_index": index,
            "candidate_identity_sha256": candidate[
                "candidate_identity_sha256"
            ],
            "canonical_gt_sha256": "4" * 64,
            "pair_quality_gates": {"all_preoutcome_gates": True},
            "inventory_sha256": "5" * 64,
            "model_outputs_present_false": True,
        }
        execution.write_json(destination / "full_pair_receipt.json", terminal)
        published.add(selected_pair_id)
        return {
            "status": terminal["status"],
            "pair_id": selected_pair_id,
            "full_pair_receipt_sha256": execution.sha256_file(
                destination / "full_pair_receipt.json"
            ),
            "model_loaded": False,
            "inference_calls": 0,
        }

    monkeypatch.setattr(
        execution,
        "validate_full_plan",
        lambda _path: {"pair_roster_sha256": "6" * 64},
    )
    monkeypatch.setattr(execution, "full_roster_rows", lambda _config: rows)
    monkeypatch.setattr(
        execution,
        "full_paths",
        lambda _config: {
            "synthetic": full_root,
            "docs": docs_root,
            "run": tmp_path / "runs",
        },
    )
    monkeypatch.setattr(
        execution,
        "ensure_locked_test_render_batch_execution_lock",
        lambda _path, _config, _plan: {"sha256": "7" * 64},
    )
    monkeypatch.setattr(execution, "inspect_full_render_state", fake_state)
    monkeypatch.setattr(
        execution,
        "preflight",
        lambda _path, scope: {
            "scope": scope,
            "gpu": {"memory_free_mib": 23000},
        },
    )
    monkeypatch.setattr(
        execution,
        "build_full_capacity_receipt",
        lambda _config, _preflight: {
            "projection": {"passed": True, "required_bytes": 180000000000}
        },
    )
    monkeypatch.setattr(execution, "run_gt_scout_candidate", fake_scout)
    monkeypatch.setattr(execution, "render_full_pair", fake_render)

    first = execution.run_locked_test_render_batch(
        CONFIG, [pair_id], max_new_pairs=1
    )
    assert first["status"] == (
        "PASS_LOCKED_TEST_RENDER_BATCH_PREOUTCOME_SYNTHETIC_ONLY"
    )
    assert first["new_pair_ids"] == [pair_id]
    assert scout_calls == [0, 1]
    assert render_calls == [1]
    receipt_path = next(
        (planning / "locked_test_render_batches_v1").glob(
            "*/batch_receipt.json"
        )
    )
    receipt = execution.load_json(receipt_path)
    assert receipt["new_pair_count"] == 1
    assert len(receipt["canonical_rejection_rows"]) == 1
    assert receipt["locked_test_prediction_accessed"] is False
    assert receipt["locked_test_outcome_accessed"] is False
    assert receipt["model_loaded"] is False
    assert receipt["inference_calls"] == 0

    second = execution.run_locked_test_render_batch(
        CONFIG, [pair_id], max_new_pairs=1
    )
    assert second["status"] == (
        "SKIP_EXISTING_PASS_LOCKED_TEST_RENDER_BATCH_"
        "PREOUTCOME_SYNTHETIC_ONLY"
    )
    assert second["batch_receipt_sha256"] == first["batch_receipt_sha256"]
    assert scout_calls == [0, 1]
    assert render_calls == [1]

    parsed = execution.parse_args(
        [
            "full-render-locked-test-batch",
            "--pair-id",
            pair_id,
            "--max-new-pairs",
            "1",
        ]
    )
    assert parsed.command == "full-render-locked-test-batch"
    assert parsed.pair_id == [pair_id]
    assert parsed.max_new_pairs == 1


def _build_extension_test_inputs() -> tuple[
    dict[str, object],
    dict[str, object],
    list[dict[str, object]],
    dict[str, object],
]:
    config = execution.load_config(CONFIG)
    protocol = execution._protocol(config)
    planning = execution.full_paths(config)["synthetic"] / "planning"
    historical = execution.read_jsonl(planning / "pair_roster_v1.jsonl")
    templates = execution.load_json(planning / "template_inventory_v1.json")
    return config, protocol, historical, templates


def test_manager_authorized_extension_preserves_all_historical_v1_bytes() -> None:
    config, _, historical, _ = _build_extension_test_inputs()
    planning = execution.full_paths(config)["synthetic"] / "planning"
    assert execution.sha256_file(CONFIG) == execution.HISTORICAL_V1_BINDINGS[
        "execution_config_sha256"
    ]
    assert execution.sha256_file(
        execution.resolve_path(config["source_locks"]["protocol"]["path"])
    ) == execution.HISTORICAL_V1_BINDINGS["protocol_sha256"]
    assert execution.sha256_file(planning / "pair_roster_v1.jsonl") == (
        execution.HISTORICAL_V1_BINDINGS["pair_roster_sha256"]
    )
    assert len(historical) == 96
    assert all(
        [int(candidate["candidate_index"]) for candidate in row["candidates"]]
        == list(range(10))
        for row in historical
    )
    snapshots = execution._validate_historical_source_snapshots(config)
    assert snapshots["snapshot_count"] == 8
    assert all(
        execution.sha256_file(execution.resolve_path(row["path"]))
        == row["sha256"]
        for row in snapshots["snapshots"]
    )


def test_roster_extension_is_deterministic_complete_unique_and_outcome_free() -> None:
    _, protocol, historical, templates = _build_extension_test_inputs()
    first = execution.build_roster_extension(historical, protocol, templates)
    second = execution.build_roster_extension(historical, protocol, templates)
    assert first == second
    validation = execution.validate_roster_extension_rows(
        first, historical, protocol, templates
    )
    assert validation["pair_count"] == 96
    assert validation["extension_candidate_count"] == 96 * 22
    assert validation["combined_candidate_count"] == 96 * 32
    assert validation["unique_extension_candidate_identity_count"] == 96 * 22
    assert validation["unique_combined_candidate_identity_count"] == 96 * 32
    assert validation["extension_seed_count"] == 96 * 22 * 5
    assert validation["unique_extension_seed_count"] == 96 * 22 * 5
    assert validation["unique_combined_seed_count"] == 96 * 32 * 5
    assert all(
        [int(candidate["candidate_index"]) for candidate in row["candidates"]]
        == list(range(10, 32))
        for row in first
    )
    assert not any(
        candidate["model_outcome_inputs"]
        for row in first
        for candidate in row["candidates"]
    )


def test_roster_extension_seed_uses_exact_historical_formula() -> None:
    _, protocol, _, _ = _build_extension_test_inputs()
    observed = execution.derive_roster_extension_seed(
        protocol,
        split="locked_test",
        cell_id="cell_001",
        replicate_index=0,
        candidate_index=10,
        channel="scene_seed",
    )
    payload = (
        "spot_spray_simulation_video_ab_protocol_v1|locked_test|cell_001|"
        "0|10|scene_seed|540000"
    ).encode("utf-8")
    expected = int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")
    assert observed == expected
    with pytest.raises(execution.ContractError, match="outside sealed extension range"):
        execution.derive_roster_extension_seed(
            protocol,
            split="locked_test",
            cell_id="cell_001",
            replicate_index=0,
            candidate_index=9,
            channel="scene_seed",
        )


@pytest.mark.parametrize(
    "mutation",
    ["partial", "reorder", "identity_collision", "seed_collision", "outcome"],
)
def test_roster_extension_tamper_modes_fail_closed(mutation: str) -> None:
    _, protocol, historical, templates = _build_extension_test_inputs()
    rows = execution.build_roster_extension(historical, protocol, templates)
    tampered = copy.deepcopy(rows)
    if mutation == "partial":
        tampered.pop()
    elif mutation == "reorder":
        tampered[0]["candidates"][0], tampered[0]["candidates"][1] = (
            tampered[0]["candidates"][1],
            tampered[0]["candidates"][0],
        )
    elif mutation == "identity_collision":
        tampered[0]["candidates"][1]["candidate_identity_sha256"] = tampered[0][
            "candidates"
        ][0]["candidate_identity_sha256"]
    elif mutation == "seed_collision":
        tampered[0]["candidates"][1]["seeds"]["scene_seed"] = tampered[0][
            "candidates"
        ][0]["seeds"]["scene_seed"]
    else:
        tampered[0]["candidates"][0]["model_outcome_inputs"] = ["prediction"]
    with pytest.raises(execution.ContractError, match="drift|reorder|collision|partial"):
        execution.validate_roster_extension_rows(
            tampered, historical, protocol, templates
        )


def test_roster_extension_merge_is_append_only_and_candidate10_is_next(
    tmp_path: Path,
) -> None:
    _, protocol, historical, templates = _build_extension_test_inputs()
    extension = execution.build_roster_extension(
        historical, protocol, templates
    )
    merged = execution.merge_full_roster_with_extension(historical, extension)
    historical_row = next(
        row for row in historical if row["pair_id"] == "locked_test_c001_r00"
    )
    merged_row = next(
        row for row in merged if row["pair_id"] == "locked_test_c001_r00"
    )
    assert merged_row["pair_slot_identity_sha256"] == historical_row[
        "pair_slot_identity_sha256"
    ]
    assert merged_row["candidates"][:10] == historical_row["candidates"]
    assert [row["candidate_index"] for row in merged_row["candidates"]] == list(
        range(32)
    )
    planning = tmp_path / "planning"
    execution.write_jsonl(
        planning / "candidate_rejection_ledger_v1.jsonl",
        [
            {
                "pair_id": merged_row["pair_id"],
                "candidate_index": index,
                "candidate_identity_sha256": merged_row["candidates"][index][
                    "candidate_identity_sha256"
                ],
            }
            for index in range(10)
        ],
    )
    selected = execution._next_gt_scout_candidate(tmp_path, merged_row)
    assert selected["candidate_index"] == 10
    execution.write_jsonl(
        planning / "candidate_rejection_ledger_v1.jsonl",
        [
            {
                "pair_id": merged_row["pair_id"],
                "candidate_index": index,
                "candidate_identity_sha256": merged_row["candidates"][index][
                    "candidate_identity_sha256"
                ],
            }
            for index in range(32)
        ],
    )
    with pytest.raises(execution.ContractError, match="attempts exhausted"):
        execution._next_gt_scout_candidate(tmp_path, merged_row)


def test_extension_preserves_historical_render_and_scout_implementation_hashes() -> None:
    assert execution.full_render_implementation_sha256() == (
        "7a28319bb48d087db8620ab18650566a5884a21343cc1cec557a1f9694173751"
    )
    assert execution.gt_scout_implementation_sha256() == (
        "feeb9826103dbe71711b4cdb76dac0e6a828a4c33edba354addb71e1c11c0b46"
    )
    assert execution.locked_test_render_batch_implementation_sha256() == (
        "8fcb95eeac50260068244809db9fe1e34aa208571d81dae137976dd98f423e70"
    )
    assert (
        execution.locked_test_gt_source_cardinality_recovery_implementation_sha256()
        == "20aaccaf74b1d7a9c8c11f9924ede38c31bfafdbc2de0c24c34729ff8373326b"
    )


def test_live_roster_extension_release_and_combined_plan_validate() -> None:
    config = execution.load_config(CONFIG)
    paths = execution.roster_extension_paths(config)
    result = execution._validate_frozen_pass55_release(config)
    assert result["status"] == "PASS_FROZEN_PASS55_PARENT_RELEASE_SYNTHETIC_ONLY"
    assert result["parent_execution_release_identity_sha256"] == (
        execution.ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256
    )
    assert result["model_loaded"] is False
    assert result["inference_calls"] == 0
    extension_config = execution.load_config(paths["extension_config"])
    combined = execution.full_roster_rows(extension_config)
    assert len(combined) == 96
    assert all(len(row["candidates"]) == 32 for row in combined)
    plan = execution.validate_full_plan(paths["extension_config"])
    assert plan["status"] == "PASS_FULL_PLAN_DRY_RUN_SYNTHETIC_ONLY"
    assert plan["candidate_count"] == 960
    assert plan["extension_candidate_count"] == 2112
    assert plan["combined_candidate_count"] == 3072
    assert plan["model_loaded"] is False
    assert plan["inference_calls"] == 0


def test_live_roster_extension_frozen_validation_is_idempotent_and_render_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = execution.load_config(CONFIG)
    paths = execution.roster_extension_paths(config)
    before = {
        relative: execution.sha256_file(paths["synthetic"] / relative)
        for relative in execution._roster_extension_required_relative_files()
    }

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("extension sealing touched candidate GT, rendering, or model")

    monkeypatch.setattr(execution.subprocess, "run", forbidden)
    first = execution._validate_frozen_pass55_release(config)
    second = execution._validate_frozen_pass55_release(config)
    after = {
        relative: execution.sha256_file(paths["synthetic"] / relative)
        for relative in execution._roster_extension_required_relative_files()
    }
    assert first == second
    assert before == after
    assert first["model_loaded"] is False
    assert first["inference_calls"] == 0


def test_roster_extension_cli_is_explicit_and_separate() -> None:
    seal = execution.parse_args(["full-seal-roster-extension"])
    validate = execution.parse_args(
        [
            "--config",
            "data/synthetic/cropcraft/spot_spray_simulation_video_ab_execution_v1/"
            "full_benchmark_v1/planning/roster_extension_v1/"
            "execution_config_v1_plus_roster_extension_v1.yaml",
            "full-roster-extension-validate",
        ]
    )
    assert seal.command == "full-seal-roster-extension"
    assert validate.command == "full-roster-extension-validate"


def test_runtime_compatibility_release_adds_exactly_two_aliases() -> None:
    historical_config = execution.load_config(CONFIG)
    parent_paths = execution.roster_extension_paths(historical_config)
    patch_paths = execution.runtime_compatibility_paths(historical_config)
    result = execution.validate_runtime_compatibility_release(
        patch_paths["config"]
    )
    assert result["status"] == (
        "PASS_RUNTIME_COMPATIBILITY_RELEASE_VALIDATION_SYNTHETIC_ONLY"
    )
    assert result["parent_execution_release_identity_sha256"] == (
        execution.ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256
    )
    assert result["runtime_compatibility_aliases"] == (
        execution.RUNTIME_COMPATIBILITY_ALIASES
    )
    patch_config = execution.load_config(patch_paths["config"])
    parent_config = execution.load_config(parent_paths["extension_config"])
    without_epoch = copy.deepcopy(patch_config)
    without_epoch.pop("runtime_compatibility_epoch")
    assert without_epoch == parent_config

    base_path = (
        parent_paths["execution_locks"]
        / "gt_scout_execution_lock_extension_v1.json"
    )
    base_sha256 = execution.sha256_file(base_path)
    base = execution.load_json(base_path)
    runtime_view = execution._extension_execution_lock(
        patch_config, "gt_scout_execution_lock_extension_v1.json"
    )
    added = set(runtime_view) - set(base) - {"path", "sha256"}
    assert added == set(execution.RUNTIME_COMPATIBILITY_ALIASES)
    assert {name: runtime_view[name] for name in added} == (
        execution.RUNTIME_COMPATIBILITY_ALIASES
    )
    assert execution.sha256_file(base_path) == base_sha256 == (
        "cdeb185a73ef23b9bb575bf4c4a6bd1fee0f87d67a344d0aade6f505bf0027f0"
    )


def test_runtime_compatibility_binds_pass55_snapshots_and_failed_intent() -> None:
    config = execution.load_config(CONFIG)
    paths = execution.runtime_compatibility_paths(config)
    snapshots = execution._runtime_compatibility_source_snapshots(
        config, require_docs_mirror=True
    )
    assert [row["sha256"] for row in snapshots] == [
        execution.PASS55_EXECUTION_SCRIPT_SHA256,
        execution.PASS55_EXECUTION_TEST_SHA256,
    ]
    receipt = execution.load_json(paths["pass58_receipt"])
    immutable = receipt["immutable_parent"]
    assert immutable["pass55_execution_script_sha256"] == (
        execution.PASS55_EXECUTION_SCRIPT_SHA256
    )
    assert immutable["pass55_execution_test_sha256"] == (
        execution.PASS55_EXECUTION_TEST_SHA256
    )
    assert immutable["pass57_failure_receipt_sha256"] == (
        execution.PASS57_FAILURE_RECEIPT_SHA256
    )
    assert immutable["failed_batch_intent_sha256"] == (
        execution.PASS56_FAILED_BATCH_INTENT_SHA256
    )
    assert immutable["bytes_mutated_or_rebound"] is False


def test_runtime_compatibility_config_tamper_modes_fail_closed() -> None:
    config = execution.load_config(CONFIG)
    paths = execution.runtime_compatibility_paths(config)
    canonical = execution.load_config(paths["config"])
    tampered_values = []
    extra = copy.deepcopy(canonical)
    extra["runtime_compatibility_epoch"]["unexpected"] = True
    tampered_values.append(extra)
    alias = copy.deepcopy(canonical)
    alias["runtime_compatibility_epoch"]["added_runtime_aliases"][
        "sealed_full_render_execution_lock_sha256"
    ] = "0" * 64
    tampered_values.append(alias)
    gate = copy.deepcopy(canonical)
    gate["runtime_compatibility_epoch"][
        "gate_threshold_seed_candidate_or_selection_change"
    ] = True
    tampered_values.append(gate)
    outcome = copy.deepcopy(canonical)
    outcome["runtime_compatibility_epoch"]["outcome_inputs"] = ["prediction"]
    tampered_values.append(outcome)
    for tampered in tampered_values:
        with pytest.raises(execution.ContractError, match="config changed"):
            execution._is_runtime_compatibility_config(tampered)


def test_runtime_compatibility_alias_collision_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = execution.load_config(CONFIG)
    parent = execution._validate_frozen_pass55_release(config)
    original = execution.load_json

    def tampered_load(path: Path) -> dict[str, object]:
        value = original(path)
        if Path(path).name == "gt_scout_execution_lock_extension_v1.json":
            value["sealed_full_render_execution_lock_sha256"] = (
                execution.RUNTIME_COMPATIBILITY_ALIASES[
                    "sealed_full_render_execution_lock_sha256"
                ]
            )
        return value

    monkeypatch.setattr(execution, "load_json", tampered_load)
    with pytest.raises(execution.ContractError, match="alias collides"):
        execution._runtime_compatibility_alias_payload(config, parent)


def test_runtime_compatibility_seal_repeat_is_idempotent_and_access_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = execution.load_config(CONFIG)
    paths = execution.runtime_compatibility_paths(config)
    before = {
        relative: execution.sha256_file(paths["synthetic"] / relative)
        for relative in execution._runtime_compatibility_required_relative_files()
    }

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("runtime compatibility sealing touched runtime execution")

    monkeypatch.setattr(execution.subprocess, "run", forbidden)
    first = execution.seal_runtime_compatibility_release(CONFIG)
    second = execution.seal_runtime_compatibility_release(CONFIG)
    after = {
        relative: execution.sha256_file(paths["synthetic"] / relative)
        for relative in execution._runtime_compatibility_required_relative_files()
    }
    assert first == second
    assert before == after
    assert first["candidate_10_started"] is False
    assert first["rendering_calls"] == 0
    assert first["model_loaded"] is False
    assert first["inference_calls"] == 0


def test_runtime_compatibility_partial_release_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    synthetic = tmp_path / "synthetic"
    docs = tmp_path / "docs"
    config_path = synthetic / "release_v1/config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("partial\n", encoding="utf-8")
    docs.mkdir()
    fake = {
        "synthetic": synthetic,
        "docs": docs,
        "config": config_path,
    }
    monkeypatch.setattr(execution, "runtime_compatibility_paths", lambda _config: fake)
    with pytest.raises(execution.ContractError, match="file set changed"):
        execution.validate_runtime_compatibility_release(config_path)


def test_runtime_compatibility_cli_is_explicit_and_separate() -> None:
    seal = execution.parse_args(["full-seal-runtime-compatibility"])
    validate = execution.parse_args(
        [
            "--config",
            "data/synthetic/cropcraft/spot_spray_simulation_video_ab_execution_v1/"
            "full_benchmark_v1/planning/roster_extension_runtime_compatibility_v1/"
            "release_v1/execution_config_v1_plus_roster_extension_v1_"
            "runtime_compatibility_v1.yaml",
            "full-runtime-compatibility-validate",
        ]
    )
    assert seal.command == "full-seal-runtime-compatibility"
    assert validate.command == "full-runtime-compatibility-validate"
