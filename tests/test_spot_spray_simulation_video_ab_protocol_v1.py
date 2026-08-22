from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from yaml.constructor import ConstructorError


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = (
    ROOT / "configs/benchmark/spot_spray_simulation_video_ab_protocol_v1.yaml"
)
DOCUMENT_PATH = ROOT / "docs/research/SPOT_SPRAY_SIMULATION_VIDEO_AB_PROTOCOL_V1.md"
PLAN_PATH = (
    ROOT
    / "docs/plans/part-spot-spray-simulation-video-ab-protocol-adaptive-plan.md"
)

EXPECTED_TOP_LEVEL = {
    "schema_version",
    "protocol_id",
    "scope",
    "source_lock",
    "claim_boundary",
    "registered_hypotheses",
    "pairing_contract",
    "seed_derivation",
    "allocation",
    "shared_latent_envelope",
    "ideal_capture_profile",
    "degraded_capture_profile",
    "preoutcome_gates",
    "gt_contract",
    "inference_contract",
    "tracker_contract",
    "calibration_contract",
    "action_evaluator_binding",
    "segmentation_estimands",
    "tracking_estimands",
    "action_estimands",
    "uncertainty",
    "output_contract",
    "failure_states",
    "stopping_rules",
}


class UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_unique_yaml(path: Path) -> dict[str, Any]:
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    if not isinstance(value, dict):
        raise TypeError(f"Expected YAML mapping: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def derive_seed(
    config: dict[str, Any],
    *,
    split: str,
    cell_id: str,
    replicate_index: int,
    candidate_index: int,
    channel_name: str,
) -> int:
    seed = config["seed_derivation"]
    values = {
        "protocol_id": config["protocol_id"],
        "split": split,
        "cell_id": cell_id,
        "replicate_index": replicate_index,
        "candidate_index": candidate_index,
        "channel_name": channel_name,
        "v12_split_base_seed": seed["split_base_seeds"][split],
    }
    payload = seed["separator"].join(str(values[key]) for key in seed["input_order"])
    return int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")


def cell_ids(config: dict[str, Any]) -> list[str]:
    factors = config["allocation"]["factors"]
    names = list(factors)
    return [
        "__".join(f"{name}={value}" for name, value in zip(names, values))
        for values in itertools.product(*(factors[name] for name in names))
    ]


def assert_pairing_contract(config: dict[str, Any]) -> None:
    contract = config["pairing_contract"]
    assert contract["experimental_unit"] == "complete_latent_video_sequence"
    assert contract["arms"] == ["ideal", "degraded"]
    assert contract["exact_arms_per_pair"] == 2
    assert contract["frames_are_independent_units"] is False
    assert contract["common_random_numbers_across_arms"] is True
    required = set(contract["required_shared_fields"])
    assert {
        "source_scene_graph_identity",
        "crop_and_weed_source_object_ids",
        "camera_mid_exposure_trajectory",
        "encoder_trajectory",
        "frame_clock",
        "gt_classes_instances_tracks_polygons_and_masks",
        "canopy_span_mm",
        "visible_fraction",
        "partial_and_occluded_flags",
        "base_capture_draw_vector",
    } <= required
    allowed = set(contract["allowed_arm_differences"])
    assert allowed == {
        "capture_profile_id",
        "arm_prefixed_frame_and_video_ids",
        "temporal_integration_enabled",
        "pulse_width_us",
        "psf_path_family_and_weights",
        "artificial_light_energy_size_and_warmth",
        "resulting_rgb_pixels_and_hashes",
    }
    forbidden = set(contract["forbidden_arm_differences"])
    assert {
        "latent_scene_or_trajectory",
        "timestamp_or_encoder",
        "camera_mid_exposure_pose",
        "source_object_or_gt_track_identity",
        "gt_geometry_or_action_eligibility_fields",
        "model_checkpoint",
        "inference_or_tracker_configuration",
        "metric_or_threshold_policy",
    } == forbidden
    assert required.isdisjoint(allowed)
    assert contract["mismatch_disposition"] == (
        "invalidate_full_release_never_drop_pair"
    )


@pytest.fixture(scope="module")
def config() -> dict[str, Any]:
    return load_unique_yaml(CONFIG_PATH)


def test_yaml_is_unique_keyed_and_has_exact_closed_top_level_schema(
    config: dict[str, Any],
) -> None:
    assert config["schema_version"] == 1
    assert config["protocol_id"] == "spot_spray_simulation_video_ab_protocol_v1"
    assert set(config) == EXPECTED_TOP_LEVEL
    assert config["scope"]["protocol_status"] == "FROZEN_PRE_EXECUTION_CONTRACT"
    assert config["scope"]["evidence_class"] == "SYNTHETIC_DIAGNOSTIC_ONLY"
    with pytest.raises(ConstructorError, match="duplicate key"):
        yaml.load("schema_version: 1\nschema_version: 2\n", Loader=UniqueKeyLoader)


def test_every_pinned_source_and_external_receipt_matches_current_bytes(
    config: dict[str, Any],
) -> None:
    lock = config["source_lock"]
    assert lock["algorithm"] == "sha256_exact_bytes"
    assert lock["repository"]["implementation_base_commit"] == (
        "9f558b10c6bebfa4c765b395b3dcfc3f5e0e75b9"
    )
    subprocess.run(
        [
            "git",
            "cat-file",
            "-e",
            lock["repository"]["implementation_base_commit"] + "^{commit}",
        ],
        cwd=ROOT,
        check=True,
    )
    assert lock["repository"]["decision_plan_remote_commit"] == (
        "8053f5e9f9f496c4a5a69b21884e9f73031c51c5"
    )
    for collection in ("repository_sources", "external_sources"):
        for source in lock[collection].values():
            path = source_path(source["path"])
            assert path.is_file(), path
            assert sha256(path) == source["sha256"], path

    assert source_path(
        lock["repository_sources"]["decision_plan"]["path"]
    ) == PLAN_PATH
    selection = json.loads(
        source_path(
            lock["external_sources"]["sensor_motion_v7_selection_receipt"][
                "path"
            ]
        ).read_text(encoding="utf-8")
    )
    for key, expected in lock["external_sources"][
        "sensor_motion_v7_selection_receipt"
    ]["required_facts"].items():
        assert selection[key] == expected


def test_architecture_checkpoint_and_action_evaluator_are_exactly_bound(
    config: dict[str, Any],
) -> None:
    sources = config["source_lock"]["repository_sources"]
    architecture = load_unique_yaml(source_path(sources["product_architecture"]["path"]))
    sensor = architecture["baseline"]["sensor_optics"]
    compute = architecture["baseline"]["compute_capture"]
    safety = architecture["baseline"]["safety"]
    shared = config["shared_latent_envelope"]
    assert sensor["camera_count"] == 1
    assert sensor["active_roi_px"] == shared["native_raster_px"] == [2048, 2048]
    assert sensor["full_frame_resize_forbidden"] is True
    assert sensor["acquisition_rate_hz"] == shared["frame_rate_hz"] == 15.0
    assert sensor["outer_abstain_ring_px"] == shared["outer_abstain_ring_px"] == 64
    assert sensor["action_service_class_mm"] == 20.0
    assert sensor["maximum_blur_px"] == config["degraded_capture_profile"][
        "maximum_total_psf_path_px"
    ]
    assert compute["selected_foundation_checkpoint_sha256"] == config[
        "inference_contract"
    ]["checkpoint_sha256"]
    assert safety["same_event_camera_trigger_and_encoder_latch"] is True
    assert architecture["status_axes"]["physical_acceptance"] == "PRE_REAL_NOT_READY"

    action = load_unique_yaml(source_path(sources["frozen_action_contract"]["path"]))
    binding = config["action_evaluator_binding"]["frozen_semantics"]
    assert action["model"]["foundation"]["checkpoint_sha256"] == config[
        "inference_contract"
    ]["checkpoint_sha256"]
    assert action["model"]["evaluated_checkpoint"]["checkpoint"] is None
    assert action["eligible_weed_track"]["minimum_canopy_span_mm"] == binding[
        "eligible_weed_minimum_canopy_span_mm"
    ]
    assert action["eligible_weed_track"]["minimum_visible_fraction"] == binding[
        "eligible_weed_minimum_visible_fraction"
    ]
    assert action["temporal_action"]["minimum_confirmations"] == binding[
        "minimum_confirmations"
    ]
    assert action["temporal_action"]["preferred_window_frames"] == binding[
        "preferred_window_frames"
    ]
    assert action["offline_go_gates"][
        "synthetic_score_weight_in_real_go_decision"
    ] == config["claim_boundary"]["synthetic_score_weight_in_real_go_decision"]


def test_allocation_is_exactly_balanced_and_frames_are_not_pseudoreplicates(
    config: dict[str, Any],
) -> None:
    allocation = config["allocation"]
    cells = cell_ids(config)
    assert len(cells) == allocation["exact_cell_count"] == 8
    assert allocation[
        "ideal_arm_retains_degraded_motion_path_stratum_for_pairing"
    ] is True
    calculated_pairs = 0
    calculated_videos = 0
    calculated_frames = 0
    for split in ("calibration", "locked_test"):
        row = allocation["splits"][split]
        pairs = len(cells) * row["replicates_per_cell"]
        assert pairs == row["pair_count"]
        assert row["arm_count"] == pairs * 2
        assert row["rendered_frame_count"] == row["arm_count"] * row["frames_per_arm"]
        assert row["frames_per_arm"] == config["shared_latent_envelope"]["frame_count"]
        calculated_pairs += pairs
        calculated_videos += row["arm_count"]
        calculated_frames += row["rendered_frame_count"]
    assert allocation["totals"] == {
        "pair_count": calculated_pairs,
        "video_count": calculated_videos,
        "frames_per_video": 30,
        "rendered_frame_count": calculated_frames,
    }
    assert allocation["totals"] == {
        "pair_count": 96,
        "video_count": 192,
        "frames_per_video": 30,
        "rendered_frame_count": 5760,
    }
    assert config["pairing_contract"]["frames_are_independent_units"] is False


def test_seed_streams_include_replicate_are_unique_and_ignore_hypotheses(
    config: dict[str, Any],
) -> None:
    seed = config["seed_derivation"]
    assert seed["input_order"] == [
        "protocol_id",
        "split",
        "cell_id",
        "replicate_index",
        "candidate_index",
        "channel_name",
        "v12_split_base_seed",
    ]
    observed: set[int] = set()
    for split, allocation in config["allocation"]["splits"].items():
        for cell in cell_ids(config):
            for replicate in range(allocation["replicates_per_cell"]):
                for candidate in range(seed["candidate_index_range"][1] + 1):
                    for channel in seed["channels"]:
                        value = derive_seed(
                            config,
                            split=split,
                            cell_id=cell,
                            replicate_index=replicate,
                            candidate_index=candidate,
                            channel_name=channel,
                        )
                        assert value not in observed
                        observed.add(value)
    expected = (32 + 64) * 10 * len(seed["channels"])
    assert len(observed) == expected

    altered = copy.deepcopy(config)
    altered["registered_hypotheses"]["locked_test_action_f1"][
        "ideal_reference"
    ] = 0.01
    altered["registered_hypotheses"]["locked_test_action_f1"][
        "degraded_reference"
    ] = 0.99
    arguments = {
        "split": "locked_test",
        "cell_id": cell_ids(config)[0],
        "replicate_index": 0,
        "candidate_index": 0,
        "channel_name": "scene_seed",
    }
    assert derive_seed(config, **arguments) == derive_seed(altered, **arguments)
    hypotheses = config["registered_hypotheses"]
    assert hypotheses["acceptance_band"] is None
    assert hypotheses["acceptance_gate"] is False
    assert all(
        hypotheses[key] is False
        for key in (
            "influences_sample_size",
            "influences_seed_derivation",
            "influences_candidate_selection",
            "influences_capture_envelopes",
            "influences_threshold_selection",
            "influences_tracker_or_model",
        )
    )


def test_pairing_has_complete_latent_equality_and_a_closed_difference_allowlist(
    config: dict[str, Any],
) -> None:
    assert_pairing_contract(config)
    broken = copy.deepcopy(config)
    broken["pairing_contract"]["required_shared_fields"].remove(
        "camera_mid_exposure_trajectory"
    )
    with pytest.raises(AssertionError):
        assert_pairing_contract(broken)
    broken = copy.deepcopy(config)
    broken["pairing_contract"]["allowed_arm_differences"].append(
        "model_checkpoint"
    )
    with pytest.raises(AssertionError):
        assert_pairing_contract(broken)


def test_v12_profile_intersections_and_subpixel_degradation_are_source_bounded(
    config: dict[str, Any],
) -> None:
    sources = config["source_lock"]["repository_sources"]
    v12 = load_unique_yaml(source_path(sources["cropcraft_v12_contract"]["path"]))
    shared = config["shared_latent_envelope"]
    architecture = load_unique_yaml(source_path(sources["product_architecture"]["path"]))
    product_wd = architecture["baseline"]["sensor_optics"][
        "working_distance_adjustment_mm"
    ]
    v12_wd_mm = [value * 1000 for value in v12["deploy_imaging_contract"]["camera_height_m"]]
    assert shared["working_distance_mm"] == [
        max(product_wd[0], v12_wd_mm[0]),
        min(product_wd[1], v12_wd_mm[1]),
    ]

    source_name_map = {
        "artificial_light_energy_renderer_units": "artificial_light_energy",
        "artificial_light_size_m": "artificial_light_size_m",
        "artificial_light_warmth_proxy": "artificial_light_warmth",
    }
    for profile_name, expected_profile in shared["scene_profiles"].items():
        source_profiles = []
        for split in ("val", "test"):
            rows = v12["splits"][split]["correlated_scene_profiles"]
            source_profiles.append(next(row for row in rows if row["name"] == profile_name))
        for expected_name, expected_range in expected_profile.items():
            source_name = source_name_map.get(expected_name, expected_name)
            left = source_profiles[0]["surface_parameter_ranges"][source_name]
            right = source_profiles[1]["surface_parameter_ranges"][source_name]
            assert expected_range == [max(left[0], right[0]), min(left[1], right[1])]

    degraded = config["degraded_capture_profile"]
    maximum_blur = max(
        speed * pulse * 0.001 / (fov / 2048)
        for speed in shared["travel_speeds_m_s"]
        for pulse in degraded["pulse_width_us"]
        for fov in shared["ground_fov_mm"]
    )
    assert maximum_blur == pytest.approx(0.7345147679324894)
    assert maximum_blur <= degraded["maximum_total_psf_path_px"] == 0.75
    assert degraded["v7_original_kernel_lengths_px_allowed"] is False
    assert min(degraded["v7_original_kernel_range_px"]) > degraded[
        "maximum_total_psf_path_px"
    ]
    assert degraded["random_zero_to_180_degree_angle_allowed"] is False
    assert degraded["post_outcome_rescaling_allowed"] is False
    assert config["ideal_capture_profile"]["achievable_installed_capture_claim"] is False
    assert degraded["absolute_camera_realism_claim"] is False


def test_candidate_selection_and_lock_order_are_strictly_preoutcome(
    config: dict[str, Any],
) -> None:
    gates = config["preoutcome_gates"]
    candidate = gates["candidate_selection"]
    assert candidate["policy"] == (
        "first_candidate_in_derived_order_passing_all_non_model_gates"
    )
    assert candidate["maximum_attempts_per_slot"] == 10
    assert candidate["model_access_before_acceptance"] is False
    assert candidate["human_preference_between_passing_candidates"] is False
    assert set(candidate["forbidden_inputs"]) == {
        "predictions",
        "confidences",
        "segmentation_tracking_or_action_metrics",
        "registered_hypothesis_distance",
    }
    order = gates["mandatory_lock_order"]
    release_index = order.index("seal_release_lock_with_model_outputs_present_false")
    calibration_index = order.index(
        "run_degraded_calibration_inference_and_select_threshold"
    )
    threshold_index = order.index(
        "seal_threshold_lock_with_test_predictions_present_false"
    )
    test_index = order.index("unlock_and_run_both_locked_test_arms_once")
    assert release_index < calibration_index < threshold_index < test_index
    assert gates["pair_integrity"]["any_locked_pair_failure_invalidates_release"] is True
    assert gates["manual_review"]["locked_test_human_review_before_threshold_lock"] is False


def test_persistent_gt_gate_fails_closed_on_current_connected_region_proxy(
    config: dict[str, Any],
) -> None:
    lock = config["source_lock"]
    receipt_source = lock["external_sources"]["cropcraft_v12_proxy_receipt"]
    receipt = json.loads(source_path(receipt_source["path"]).read_text(encoding="utf-8"))
    assert receipt["label_contract"]["botanical_instance_ids_available"] is False
    assert receipt["label_contract"]["interpretation"] == (
        "8-connected visible semantic class region proxy"
    )
    assert any(
        "not botanical instances" in limitation for limitation in receipt["limitations"]
    )
    gt = config["gt_contract"]
    assert gt["authority"] == (
        "persistent_source_scene_objects_not_semantic_connected_regions"
    )
    assert gt["known_current_proxy_limit"]["botanical_instance_ids_available"] is False
    assert gt["known_current_proxy_limit"]["proxy_allowed_as_video_track_gt"] is False
    assert gt["discovery_gate"]["status_before_runtime_binding"] == (
        "UNRESOLVED_FAIL_CLOSED"
    )
    assert gt["discovery_gate"]["failure_status"] == (
        "REPLAN_REQUIRED_GT_TRACK_IDENTITY"
    )
    assert set(gt["forbidden_gt_construction"]) >= {
        "semantic_connected_components",
        "optical_flow_pseudo_tracks",
        "model_predicted_tracker_ids",
    }
    renderer = lock["execution_bindings"]["renderer_export"]
    assert renderer["state"] == "UNRESOLVED_FAIL_CLOSED"
    assert renderer["required_before_render"] is True


def test_degraded_only_calibration_reuses_one_frozen_threshold_and_evaluator(
    config: dict[str, Any],
) -> None:
    sources = config["source_lock"]["repository_sources"]
    action = load_unique_yaml(source_path(sources["frozen_action_contract"]["path"]))
    calibration = config["calibration_contract"]
    assert calibration["sole_threshold_source"] == {
        "split": "calibration",
        "arm": "degraded",
    }
    assert calibration["ideal_calibration_role"] == "post_lock_diagnostic_only"
    assert calibration["test_access_forbidden_until_threshold_lock"] is True
    assert calibration["threshold_grid"] == {
        "start": action["threshold_calibration"]["start"],
        "stop": action["threshold_calibration"]["stop"],
        "step": action["threshold_calibration"]["step"],
    }
    assert calibration["tie_breakers"] == action["threshold_calibration"][
        "tie_breakers"
    ]
    assert calibration["one_shared_threshold_for_ideal_and_degraded_test"] is True
    assert calibration["arm_specific_thresholds_allowed"] is False
    orchestration = config["action_evaluator_binding"]["two_run_orchestration"]
    assert orchestration["shared_validation_bytes"] == (
        "degraded_calibration_predictions"
    )
    assert orchestration["identical_selected_threshold_required"] is True
    assert orchestration["identical_calibration_statistics_required"] is True
    assert config["action_evaluator_binding"]["modification_allowed"] is False


def test_estimands_keep_segmentation_tracking_and_action_roles_separate(
    config: dict[str, Any],
) -> None:
    segmentation = config["segmentation_estimands"]
    assert segmentation["matching"]["minimum_mask_iou"] == 0.50
    assert segmentation["matching"]["same_class_only"] is True
    assert segmentation["partial_unknown_in_primary_denominator"] is False
    assert segmentation["replaces_action_f1"] is False
    assert {
        "instance_mask_precision_iou50",
        "instance_mask_recall_iou50",
        "instance_mask_f1_iou50",
        "mean_matched_mask_iou",
        "unmatched_gt_count",
        "unmatched_prediction_count",
    } <= set(segmentation["metrics"])

    tracking = config["tracking_estimands"]
    assert tracking["confirmation_observations"] == 3
    assert tracking["action_evaluator_remains_fire_and_duplicate_authority"] is True
    assert {
        "track_precision_3",
        "track_recall_3",
        "track_f1_3",
        "eligible_track_fragmentation_rate",
        "id_switch_count",
    } <= set(tracking["metrics"])

    action = config["action_estimands"]
    assert action["primary"] == {
        "name": "delta_action_f1_degraded_minus_ideal",
        "effect": "degraded_minus_ideal",
        "interpretation": "paired_composite_capture_profile_sensitivity",
        "negative_means_degraded_is_worse": True,
    }
    assert action["stratum_acceptance_gates_allowed"] is False
    assert action["sufficient_statistics_retained_per_pair"] is True


def test_uncertainty_resamples_only_paired_video_clusters(
    config: dict[str, Any],
) -> None:
    uncertainty = config["uncertainty"]
    assert uncertainty["sampling_unit"] == "pair_id"
    assert uncertainty["frames_instances_or_actions_resampled_independently"] is False
    assert uncertainty["method"] == "stratified_paired_cluster_bootstrap"
    assert uncertainty["replicates"] == 10000
    assert uncertainty["seed"] == 1729
    assert uncertainty["both_arms_included_per_sampled_pair"] is True
    assert uncertainty["recompute_from_sufficient_counts"] is True
    assert uncertainty["rounded_scalar_bootstrap_forbidden"] is True
    assert uncertainty["threshold_fixed_without_recalibration"] is True
    assert uncertainty["quantiles"] == [0.025, 0.975]
    assert uncertainty["undefined_replicate_policy"] == {
        "value": None,
        "maximum_fraction_before_interval_omitted": 0.01,
        "status": "UNSTABLE_DENOMINATOR",
    }
    assert uncertainty["scope_limit"] == (
        "bounded_synthetic_latent_video_sampling_only"
    )


def test_claims_outputs_failure_states_and_stopping_rules_are_fail_closed(
    config: dict[str, Any],
) -> None:
    claims = config["claim_boundary"]
    false_flags = {
        key
        for key, value in claims.items()
        if isinstance(value, bool) and value is False
    }
    assert {
        "simulation_is_physical_acceptance",
        "simulation_is_field_proof",
        "simulation_is_product_proof",
        "synthetic_pseudo_fields_are_real_fields",
        "controlled_capture_authorized",
        "dry_marker_ready",
        "field_go",
        "product_go",
        "chemical_fire_allowed",
        "deposition_or_crop_injury_proven",
        "purchase_or_fabrication_authorized",
    } <= false_flags
    assert claims["synthetic_score_weight_in_real_go_decision"] == 0.0
    assert set(claims["permitted_terminal_statuses"]) == {
        "SIM_AB_COMPLETE_SYNTHETIC_ONLY",
        "SIM_AB_CALIBRATION_INFEASIBLE_SYNTHETIC_ONLY",
        "SIM_AB_INVALID_FAIL_CLOSED",
        "REPLAN_REQUIRED",
    }

    failures = config["failure_states"]
    assert {
        "SIM_AB_INVALID_SOURCE_DRIFT",
        "SIM_AB_INVALID_PAIR_MISMATCH",
        "SIM_AB_INVALID_SPLIT_LEAKAGE",
        "SIM_AB_INVALID_INSUFFICIENT_PREOUTCOME_CANDIDATES",
        "SIM_AB_INVALID_NONDETERMINISTIC_INFERENCE",
        "SIM_AB_INVALID_PREMATURE_TEST_ACCESS",
        "SIM_AB_INVALID_OUTCOME_CONDITIONED_CHANGE",
        "REPLAN_REQUIRED_GT_TRACK_IDENTITY",
        "REPLAN_REQUIRED_NATIVE_INFERENCE",
        "REPLAN_REQUIRED_TRACKER_CONTRACT",
        "REPLAN_REQUIRED_AMBIGUOUS_INFERENCE_PATH",
    } <= set(failures)
    assert failures["pair_dropping_after_release_lock_allowed"] is False
    assert failures["silent_v1_overwrite_or_repair_allowed"] is False

    outputs = config["output_contract"]
    assert outputs["overwrite_allowed"] is False
    assert outputs["reproduction_requires_byte_identical_canonical_result"] is True
    assert {
        "release_lock_v1.json",
        "threshold_lock_v1.json",
        "ideal_action_result_v1.json",
        "degraded_action_result_v1.json",
        "paired_metric_result_v1.json",
    } <= set(outputs["required_artifacts"])
    stopping = config["stopping_rules"]
    assert "ideal_f1_far_from_0p97" in stopping["complete_after_one_locked_test_even_if"]
    assert "degraded_f1_far_from_0p75" in stopping[
        "complete_after_one_locked_test_even_if"
    ]
    assert "degraded_outperforms_ideal" in stopping[
        "complete_after_one_locked_test_even_if"
    ]


def test_human_protocol_is_consistent_with_machine_contract(
    config: dict[str, Any],
) -> None:
    text = DOCUMENT_PATH.read_text(encoding="utf-8")
    required_phrases = (
        "Synthetic diagnostic only",
        "96 latent pairs",
        "5,760 rendered frames",
        "degraded calibration",
        "one shared threshold",
        "persistent source-object identity",
        "REPLAN_REQUIRED_GT_TRACK_IDENTITY",
        "paired composite capture-profile effect",
        "0.97",
        "0.75",
        "not field proof",
        "10,000",
    )
    for phrase in required_phrases:
        assert phrase in text
    assert "near-0.75 acceptance band" not in text
    assert config["protocol_id"] in text
    assert sha256(PLAN_PATH) == config["source_lock"]["repository_sources"][
        "decision_plan"
    ]["sha256"]
