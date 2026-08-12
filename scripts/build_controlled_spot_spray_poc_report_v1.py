#!/usr/bin/env python3
"""Build readable controlled spot-spray PoC reports from frozen evidence."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw
import yaml

IMPORT_ROOT = Path(__file__).resolve().parents[1]
if str(IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPORT_ROOT))

from scripts.build_intervention_reports import (
    BG,
    BLUE,
    DARK_GREEN,
    GREEN,
    INK,
    LIGHT_BLUE,
    LIGHT_GREEN,
    LIGHT_ORANGE,
    LIGHT_RED,
    LINE,
    MUTED,
    ORANGE,
    RED,
    WHITE,
    add_text,
    base_page,
    bullet_list,
    card,
    draw_table,
    finalize_pages,
    metric_card,
    paste_contain,
    save_pdf,
    sha256,
)


ROOT = Path(__file__).resolve().parents[1]
DATA = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
DEFAULT_OUTPUT = ROOT / "docs/results/kontrollu_spot_spray_poc_v1"
ACTION = DATA / "runs/phenobench_cropcraft_deploy_action_ab_v1/action_ab_metrics.json"
SYNTHETIC = DATA / "runs/cropcraft_deploy_synthetic_diagnostic_v1/synthetic_diagnostic_metrics.json"
EXTERNAL = DATA / "runs/sugarbeets2016_yolo_segment_external_v1/external_action_metrics.json"
AB_RECEIPT = DATA / "processed/phenobench_cropcraft_deploy_ab_v1/dataset_receipt.json"
SYNTHETIC_RECEIPT = DATA / "processed/cropcraft_deploy_segment_proxy_v12/dataset_receipt.json"
SYNTHETIC_RELEASE = DATA / "synthetic/cropcraft/deploy_constrained_pilot_v12/release_receipt.json"
COMPUTE = ROOT / "docs/results/spot_spray_deploy_compute_summary_v1.json"
COMPUTE_HALO = ROOT / "docs/results/spot_spray_deploy_compute_halo_summary_v1.json"
CAPTURE_V2 = ROOT / "docs/results/controlled_capture_optimization_v2.json"
PRE_REAL_RESULT = ROOT / "docs/results/pre_real_data_ceiling_result_v1.json"
PRE_REAL_DIAGNOSTICS = DATA / "runs/pre_real_data_ceiling_action_diagnostics_v1/diagnostics.json"
PRE_REAL_GALLERY = DATA / "runs/pre_real_data_ceiling_gallery_v1"
PRE_REAL_GALLERY_RECEIPT = PRE_REAL_GALLERY / "gallery_receipt.json"
SYNTHETIC_GALLERY = DATA / "runs/cropcraft_deploy_synthetic_diagnostic_v1/gallery"
RIG_ACCEPTANCE = ROOT / "configs/deploy/spot_spray_rig_acceptance_v1.yaml"
RIG_ACCEPTANCE_IMPL = ROOT / "scripts/evaluate_spot_spray_rig_acceptance_v1.py"
RIG_ACCEPTANCE_RUNBOOK = ROOT / "docs/SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md"
CAPTURE_SCHEMA = ROOT / "configs/data/spot_spray_capture_manifest_v1.schema.json"
CAPTURE_POLICY = ROOT / "configs/data/spot_spray_capture_audit_v1.yaml"
CAPTURE_AUDIT_IMPL = ROOT / "scripts/audit_spot_spray_capture_v1.py"
CAPTURE_ANNOTATION_DOC = ROOT / "docs/SPOT_SPRAY_DATA_CAPTURE_AND_ANNOTATION_V1.md"
FINETUNE_CONTRACT = ROOT / "configs/benchmark/spot_spray_target_rig_finetune_v1.yaml"
FINETUNE_IMPL = ROOT / "scripts/train_spot_spray_target_rig_finetune_v1.py"
ACTION_EVAL_CONTRACT = ROOT / "configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml"
ACTION_EVAL_IMPL = ROOT / "scripts/evaluate_spot_spray_target_rig_action_v1.py"
TARGET_RIG_MODEL_DOC = ROOT / "docs/SPOT_SPRAY_TARGET_RIG_MODEL_PIPELINE_V1.md"

MODELS = {
    "base_e50": "Başlangıç e50",
    "control_real_replay": "Kontrol: gerçek tekrarı",
    "challenger_real_synthetic": "Aday: gerçek + sentetik",
}

SELECTED_MODEL = "challenger_real_robot_native"
SELECTED_MODEL_LABEL = "Aday: gerçek + ROSE native"


def load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping: {path}")
    return value


def pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"%{100.0 * float(value):.{digits}f}".replace(".", ",")


def pp(value: float, digits: int = 2) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{100.0 * value:.{digits}f} puan".replace(".", ",")


def action_view(data: Mapping[str, Any], model: str, size: int) -> Mapping[str, Any]:
    return data["results"][model]["methods"]["segment_crop_safe_excess_green"][
        "eligible_size_views"
    ][str(size)]["test"]


def synthetic_view(
    data: Mapping[str, Any], model: str, image_size: int, size: int
) -> Mapping[str, Any]:
    return data["results"][model][str(image_size)]["methods"][
        "segment_crop_safe_excess_green"
    ]["eligible_size_views"][str(size)]["test"]


def compact(item: Mapping[str, Any]) -> dict[str, Any]:
    names = (
        "tp",
        "fp",
        "fn",
        "precision",
        "recall",
        "f1",
        "attempted_actions",
        "crop_collision",
        "crop_collision_rate_per_attempt",
        "soil_action",
        "soil_action_rate_per_attempt",
        "duplicate_action",
    )
    return {name: item[name] for name in names if name in item}


def build_summary(inputs: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    action = inputs["action"]
    synthetic = inputs["synthetic"]
    external = inputs["external"]
    synth_receipt = inputs["synthetic_receipt"]
    synth_release = inputs["synthetic_release"]
    compute = inputs["compute"]
    compute_halo = inputs["compute_halo"]
    capture_v2 = inputs["capture_v2"]
    pre_real = inputs["pre_real_result"]
    pre_diag = inputs["pre_real_diagnostics"]
    pre_gallery = inputs["pre_real_gallery"]
    rig_acceptance = inputs["rig_acceptance"]
    capture_schema = inputs["capture_schema"]
    capture_policy = inputs["capture_policy"]
    finetune = inputs["finetune_contract"]
    action_eval = inputs["action_eval_contract"]
    if pre_real["result"]["selected_pre_real_model"] != SELECTED_MODEL:
        raise ValueError("Pre-real result does not select the expected checkpoint")
    if pre_real["result"]["field_fire_go"] is not False:
        raise ValueError("Report must remain fail-closed")
    if pre_real["primary_metrics"]["synthetic_fixed_pheno_threshold"][
        "real_model_selection_score_weight"
    ] != 0.0:
        raise ValueError("Synthetic score entered the real decision")
    if pre_gallery["model"]["sha256"] != pre_real["fairness"][
        "challenger_checkpoint_sha256"
    ]:
        raise ValueError("Gallery and selected checkpoint differ")
    selected_checkpoint_sha256 = pre_real["fairness"][
        "challenger_checkpoint_sha256"
    ]
    foundation = finetune["foundation"]
    action_foundation = action_eval["model"]["foundation"]
    if foundation["checkpoint_sha256"] != selected_checkpoint_sha256:
        raise ValueError("Fine-tune foundation and selected checkpoint differ")
    if action_foundation["checkpoint_sha256"] != selected_checkpoint_sha256:
        raise ValueError("Action-eval foundation and selected checkpoint differ")
    if action_eval["model"]["evaluated_checkpoint"]["checkpoint"] is not None:
        raise ValueError("A real target-rig checkpoint unexpectedly exists")
    if action_eval["model"]["evaluated_checkpoint"]["checkpoint_sha256"] is not None:
        raise ValueError("A real target-rig checkpoint hash unexpectedly exists")
    if finetune["status"] != "blocked_before_physical_ready_real_capture":
        raise ValueError("Fine-tune status is no longer fail-closed")
    manager_acceptance = finetune["capture_interface"]["manager_acceptance"]
    if manager_acceptance["status"] != "pending_manager_acceptance":
        raise ValueError("Report expects pending capture-manager acceptance")
    if action_eval["status"] != "frozen_before_real_target_rig_data":
        raise ValueError("Action evaluator is no longer in the pre-real state")
    if rig_acceptance["decision_policy"]["chemical_fire_allowed"] is not False:
        raise ValueError("Chemical fire must remain disabled")
    trusted_capture_sources = finetune["capture_interface"]["sources"]
    current_capture_hashes = {
        "schema": sha256(CAPTURE_SCHEMA),
        "policy": sha256(CAPTURE_POLICY),
        "audit_implementation": sha256(CAPTURE_AUDIT_IMPL),
    }
    for role, expected in trusted_capture_sources.items():
        if expected["sha256"] != current_capture_hashes[role]:
            raise ValueError(f"Fine-tune capture source pin drifted: {role}")
    if capture_schema["properties"]["schema_version"]["const"] != "capture_manifest_v1":
        raise ValueError("Unexpected capture manifest contract")
    capture_decision = capture_v2["decision"]
    optics = capture_v2["optical_proof"]
    tiling = capture_v2["tiling_and_scalable_swath"]
    baseline_camera = next(
        camera
        for camera in capture_v2["camera_price_performance"]["shortlist"]
        if camera["role"] == "baseline"
    )
    baseline_compute = next(
        item
        for item in tiling["compute_consequence"]
        if item["camera_count"] == 1
        and item["frame_rate_hz_each"] == capture_decision["baseline_frame_rate_hz"]
    )
    one_mps_motion = next(
        item
        for item in capture_v2["motion_and_track_observation"]
        if item["speed_m_s"] == 1.0
    )
    size = 82
    control = action_view(action, "control_real_replay", size)
    challenger = action_view(action, "challenger_real_synthetic", size)
    result: dict[str, Any] = {
        "schema_version": 5,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "decision": {
            "foundation": "instance_segmentation",
            "primary_intervention": "chemical_spot_spray",
            "selected_development_model": SELECTED_MODEL,
            "selected_development_model_label": SELECTED_MODEL_LABEL,
            "field_fire_status": "NO-GO",
            "reason": "The selected foundation has directional public-panel gains, but no physical A-E acceptance, audited real target-rig capture, target-rig fine-tune, or track-action result exists.",
        },
        "field_gate": {
            "track_precision_minimum": 0.98,
            "track_recall_minimum": 0.95,
            "track_f1_minimum": 0.965,
            "crop_hit_maximum": 0.005,
            "duplicate_shot_maximum": 0.01,
        },
        "fair_ab": {
            "shared_unique_real_train_frames": 1407,
            "samples_per_epoch_per_arm": 1487,
            "control_extra": "80 deterministic real replays",
            "challenger_extra": "80 V12 synthetic train tiles",
            "epochs": 8,
            "input_size_px": 1024,
            "seed": 41,
            "one_seed_directional_only": True,
        },
        "pre_real_ceiling": {
            "role": "directional model selection before own-rig data; not deployment evidence",
            "selected_model": SELECTED_MODEL,
            "selected_model_label": SELECTED_MODEL_LABEL,
            "checkpoint_sha256": selected_checkpoint_sha256,
            "matched_difference": pre_real["fairness"]["bounded_difference"],
            "training": {
                key: pre_real["fairness"][key]
                for key in (
                    "train_images_per_epoch",
                    "epochs",
                    "batch",
                    "seed",
                    "image_size",
                )
            },
            "phenobench": pre_real["primary_metrics"]["phenobench"],
            "bonirob": pre_real["primary_metrics"]["bonirob"],
            "synthetic_fixed_pheno_threshold": pre_real["primary_metrics"][
                "synthetic_fixed_pheno_threshold"
            ],
            "paired_bootstrap_phenobench": pre_real[
                "paired_bootstrap_phenobench_primary"
            ],
            "decision_checks": pre_real["decision_checks"],
            "field_fire_go": False,
            "limitations": pre_real["integration_or_blocker_risk"],
            "gallery": pre_gallery,
        },
        "phenobench": {
            "role": "consumed real source/development panel; UAV; not target-rig or field proof",
            "eligibility": "sqrt exact GT weed box area at native 1024; not physical mm",
            "primary_size_px": size,
            "primary_by_model": {
                model: compact(action_view(action, model, size)) for model in MODELS
            },
            "challenger_by_size_px": {
                str(view): compact(action_view(action, "challenger_real_synthetic", view))
                for view in (0, 28, 42, 56, 82)
            },
            "selected": compact(
                action_view(pre_diag["phenobench"], SELECTED_MODEL, size)
            ),
            "selected_by_size_px": {
                str(view): compact(
                    action_view(pre_diag["phenobench"], SELECTED_MODEL, view)
                )
                for view in (0, 28, 42, 56, 82)
            },
            "challenger_minus_control_f1": challenger["f1"] - control["f1"],
            "paired_bootstrap": action["paired_bootstrap_at_primary_service"],
        },
        "bonirob": {
            "role": "fixed-threshold external robot-view development panel; one previously consumed field/session; not deployment proof",
            "frames": external["frames"],
            "weed_region_proxies": external["region_proxy_counts"]["weed"],
            "primary_size_px": size,
            "primary_by_model": {
                model: compact(action_view(external, model, size)) for model in MODELS
            },
            "selected": compact(
                action_view(pre_diag["bonirob"], SELECTED_MODEL, size)
            ),
            "selected_tissue": pre_diag["bonirob"]["results"][SELECTED_MODEL][
                "primary_service"
            ]["tissue"],
        },
        "synthetic": {
            "role": "diagnostic only; real model-selection weight is zero",
            "train_tiles": synth_receipt["counts"]["train"]["images"],
            "val_tiles": synth_receipt["counts"]["val"]["images"],
            "test_tiles": synth_receipt["counts"]["test"]["images"],
            "primary_size_px": size,
            "selected_by_inference_size_px": {
                str(image_size): compact(
                    synthetic_view(
                        synthetic, "challenger_real_synthetic", image_size, size
                    )
                )
                for image_size in (512, 768, 1024, 1152)
            },
            "control_1024": compact(
                synthetic_view(synthetic, "control_real_replay", 1024, size)
            ),
            "selected_fixed_pheno_threshold": compact(
                action_view(pre_diag["synthetic"], SELECTED_MODEL, size)
            ),
            "all_raw_gates_passed": synth_release["all_quality_gates_passed"],
            "all_processed_gates_passed": synth_receipt["all_quality_gates_passed"],
            "polygon_reconstruction_iou_p05": synth_receipt[
                "polygon_reconstruction_iou"
            ]["p05"],
            "green_dominant_fraction": synth_receipt["appearance_calibration"][
                "green_dominant_fraction"
            ],
            "limitations": synth_receipt["limitations"],
        },
        "capture_contract": {
            "source_contract": capture_v2["contract"],
            "baseline_camera": capture_decision["baseline_camera"],
            "baseline_lens": capture_decision["lens"],
            "raster_px": baseline_camera["active_roi_px"],
            "roi_offset_px": baseline_camera["active_roi_offset_px"],
            "ground_fov_range_mm": optics["FOV_range_mm"],
            "gsd_range_mm_per_px": optics["GSD_range_mm_px"],
            "worst_case_10_mm_span_px": optics["worst_case_10_mm_span_px"],
            "worst_case_20_mm_span_px": optics["worst_case_20_mm_span_px"],
            "working_distance_adjustment_mm": capture_decision[
                "working_distance_adjustment_mm"
            ],
            "nominal_working_distance_ground_mm": capture_decision[
                "nominal_working_distance_ground_mm"
            ],
            "aperture_f_number": optics["aperture_f_number"],
            "frozen_exposure_us": capture_decision["frozen_exposure_us"],
            "blur_px_at_1_m_s": one_mps_motion["blur_px_at_frozen_exposure"],
            "action_safe_width_range_mm": optics["action_safe_width_range_mm"],
            "proof_camera_count": capture_decision["proof_camera_count"],
            "no_halo_module_fps": compute["timing_by_batch_size"]["4"][
                "estimated_module_frames_per_second"
            ],
            "halo_64px_module_mean_fps": tiling["measured_mean_module_capacity_hz"],
            "halo_64px_module_p95_fps": tiling["measured_p95_module_capacity_hz"],
            "compute_p95_service_utilization_at_baseline": baseline_compute[
                "p95_service_utilization_fraction"
            ],
            "compute_p95_remaining_budget_ms": baseline_compute[
                "p95_remaining_budget_ms_per_cycle"
            ],
            "initial_poc_fps": capture_decision["baseline_frame_rate_hz"],
            "unproven_challenger_fps": 20,
            "model_input_px": tiling["model_input_px"],
            "tile_core_px": tiling["tile_core_px"],
            "halo_px": tiling["halo_px"],
            "outer_edge_abstain_px": tiling["outer_edge_abstain_px"],
            "bom_budget": capture_v2["bom_budget"],
            "baseline_analytic_checks_pass": capture_v2[
                "baseline_analytic_checks_pass"
            ],
        },
        "target_rig_contracts": {
            "overall_status": "PRE_REAL_NOT_READY",
            "field_fire_status": "NO-GO",
            "chemical_fire_status": "NO-GO_UNSUPPORTED",
            "status_reason": (
                "No physical A-E rig-acceptance result, audited real target-rig "
                "manifest, executed target-rig fine-tune, frozen evaluated checkpoint, "
                "or real track-action result exists."
            ),
            "selected_foundation": {
                "role": foundation["role"],
                "checkpoint": foundation["checkpoint"],
                "checkpoint_sha256": selected_checkpoint_sha256,
                "is_target_rig_finetuned_checkpoint": False,
                "is_deployment_proof": False,
            },
            "rig_acceptance": {
                "contract_id": rig_acceptance["contract_id"],
                "contract_status": rig_acceptance["status"],
                "physical_result_exists": False,
                "current_controlled_data_collection_allowed": False,
                "current_dry_marker_allowed": False,
                "controlled_data_collection_gate": "physical A-E PASS",
                "dry_marker_gate": "physical A-F PASS",
                "chemical_fire_allowed": False,
                "chemical_fire_blocker": rig_acceptance["decision_policy"][
                    "chemical_fire_blocker"
                ],
            },
            "capture": {
                "manifest_contract": capture_policy["manifest_contract"],
                "real_manifest_exists": False,
                "current_audit_status": "NOT_READY",
                "evidence_scope_required": capture_policy["evidence_scope"]["real"],
                "rig_acceptance_binding": {
                    "contract_id": capture_policy["rig_acceptance"]["contract_id"],
                    "contract_identity_id": capture_policy["rig_acceptance"].get(
                        "contract_identity_id"
                    ),
                    "contract_exact_byte_sha256": capture_policy[
                        "rig_acceptance"
                    ].get("contract_exact_byte_sha256"),
                    "contract_canonical_policy_sha256": capture_policy[
                        "rig_acceptance"
                    ].get("contract_canonical_policy_sha256"),
                    "evaluator_sha256": capture_policy["rig_acceptance"].get(
                        "evaluator_sha256"
                    ),
                },
                "minimum_fields": capture_policy["readiness"]["minimum_fields"],
                "minimum_field_sessions": capture_policy["readiness"][
                    "minimum_sessions"
                ],
                "split_roles": capture_policy["split"]["roles"],
                "split_target_fractions": capture_policy["split"][
                    "target_fractions"
                ],
                "split_seed": capture_policy["split"]["deterministic_seed"],
                "split_isolation": capture_policy["split"][
                    "role_exclusive_levels"
                ],
                "adjacent_frame_max_gap": capture_policy["split"][
                    "adjacent_frame_max_gap"
                ],
                "required_real_frame_provenance": capture_policy[
                    "real_capture_provenance"
                ]["required_frame_fields"],
                "instance_classes": capture_policy["annotation"]["classes"],
                "stem_or_keypoint_labels_allowed": capture_policy["annotation"][
                    "stem_or_keypoint_labels_allowed"
                ],
                "synthetic_fixture_can_be_ready": capture_policy[
                    "evidence_scope"
                ]["synthetic_fixture_can_be_ready"],
            },
            "fine_tune": {
                "contract": finetune["contract"],
                "status": finetune["status"],
                "manager_acceptance_status": manager_acceptance["status"],
                "real_training_started": False,
                "epochs": finetune["training"]["epochs"],
                "image_size_px": finetune["training"]["image_size"],
                "batch": finetune["training"]["batch"],
                "seed": finetune["training"]["seed"],
                "final_checkpoint_rule": finetune["selection"]["rule"],
                "test_role": finetune["selection"]["test_role"],
                "fixture_can_produce_checkpoint": False,
            },
            "track_action_evaluation": {
                "contract": action_eval["contract"],
                "status": action_eval["status"],
                "current_evaluation_status": "NOT_READY",
                "evaluated_checkpoint": None,
                "evaluated_checkpoint_sha256": None,
                "minimum_canopy_span_mm": action_eval["eligible_weed_track"][
                    "minimum_canopy_span_mm"
                ],
                "minimum_visible_fraction": action_eval["eligible_weed_track"][
                    "minimum_visible_fraction"
                ],
                "minimum_confirmations": action_eval["temporal_action"][
                    "minimum_confirmations"
                ],
                "preferred_window_frames": action_eval["temporal_action"][
                    "preferred_window_frames"
                ],
                "fire_once_per_predicted_track": action_eval["temporal_action"][
                    "fire_once_per_predicted_track"
                ],
                "threshold_source_split": action_eval["threshold_calibration"][
                    "source_split"
                ],
                "test_access_forbidden_during_calibration": action_eval[
                    "threshold_calibration"
                ]["test_access_forbidden"],
                "offline_go_gates": action_eval["offline_go_gates"],
                "synthetic_fixture_status": "FIXTURE_ONLY",
                "synthetic_score_weight_in_real_go_decision": action_eval[
                    "offline_go_gates"
                ]["synthetic_score_weight_in_real_go_decision"],
                "chemical_fire_go": False,
            },
            "next_physical_proof": [
                "Generate one hash-bound physical-bench A-E PASS rig receipt.",
                "Collect and audit real target-rig RGB data across at least 3 fields and 4 field/session groups.",
                "Freeze deterministic field-level train/validation/test roles with no video-track or adjacent-frame leakage.",
                "After manager acceptance, fine-tune the selected foundation with the frozen 30-epoch protocol and freeze last.pt.",
                "Calibrate on validation only and read the separate test once for pooled and every-field track-action gates.",
                "Keep chemical fire disabled; physical A-F can authorize only a separate nonchemical dry-marker step.",
            ],
        },
        "evidence_scope": {
            "real_target_rig_result_exists": False,
            "physical_rig_acceptance_result_exists": False,
            "real_capture_audit_result_exists": False,
            "target_rig_finetune_result_exists": False,
            "real_track_action_result_exists": False,
            "synthetic_fixture_is_deployment_evidence": False,
            "displayed_action_metric_unit": "single-frame connected-region action proxy",
            "displayed_action_metric_is_not": [
                "segmentation IoU",
                "botanical-instance metric",
                "track-level field metric",
            ],
            "size_82_px_definition": "sqrt(exact ground-truth weed bounding-box area) at native 1024 raster; not weed diameter or physical millimetres",
            "crop_hit_denominator": "crop-colliding attempted actions / all attempted actions",
            "future_track_gate_f1": 0.965,
            "frame_and_track_f1_directly_comparable": False,
            "measured_compute_path": [
                "preprocessing",
                "model forward pass",
                "NMS",
                "mask construction",
                "result transfer",
            ],
            "excluded_from_compute_gate": [
                "camera acquisition",
                "tracking",
                "scheduling",
                "actuation",
                "spray physics",
            ],
        },
        "protocol_observation": (
            "Ultralytics ran the same automatic post-training validation report for both arms "
            "despite val:false. It did not feed gradients or select last.pt; test was not read. "
            "The historical status string is too strong for validation, but A/B fairness is intact."
        ),
        "locked_models": action["locked_models"],
        "input_sha256": {
            "action_metrics": sha256(ACTION),
            "synthetic_metrics": sha256(SYNTHETIC),
            "external_metrics": sha256(EXTERNAL),
            "ab_receipt": sha256(AB_RECEIPT),
            "synthetic_receipt": sha256(SYNTHETIC_RECEIPT),
            "synthetic_release": sha256(SYNTHETIC_RELEASE),
            "compute": sha256(COMPUTE),
            "compute_halo": sha256(COMPUTE_HALO),
            "capture_v2": sha256(CAPTURE_V2),
            "pre_real_result": sha256(PRE_REAL_RESULT),
            "pre_real_diagnostics": sha256(PRE_REAL_DIAGNOSTICS),
            "pre_real_gallery_receipt": sha256(PRE_REAL_GALLERY_RECEIPT),
            "rig_acceptance_contract": sha256(RIG_ACCEPTANCE),
            "rig_acceptance_implementation": sha256(RIG_ACCEPTANCE_IMPL),
            "rig_acceptance_runbook": sha256(RIG_ACCEPTANCE_RUNBOOK),
            "capture_manifest_schema": sha256(CAPTURE_SCHEMA),
            "capture_audit_policy": sha256(CAPTURE_POLICY),
            "capture_audit_implementation": sha256(CAPTURE_AUDIT_IMPL),
            "capture_annotation_document": sha256(CAPTURE_ANNOTATION_DOC),
            "target_rig_finetune_contract": sha256(FINETUNE_CONTRACT),
            "target_rig_finetune_implementation": sha256(FINETUNE_IMPL),
            "target_rig_action_eval_contract": sha256(ACTION_EVAL_CONTRACT),
            "target_rig_action_eval_implementation": sha256(ACTION_EVAL_IMPL),
            "target_rig_model_document": sha256(TARGET_RIG_MODEL_DOC),
        },
    }
    return result


def cover(summary: Mapping[str, Any], detailed: bool) -> Image.Image:
    pheno = summary["phenobench"]["selected"]
    bonirob = summary["bonirob"]["selected"]
    complete_gate_page = "17'de" if detailed else "6'da"
    page = Image.new("RGB", (1920, 1080), DARK_GREEN)
    draw = ImageDraw.Draw(page)
    card(draw, (65, 48, 1855, 1015), fill=BG, outline=BG, radius=42)
    add_text(
        draw,
        (120, 92),
        "Kontrollü spot-spray segmentasyon PoC'si",
        54,
        bold=True,
        fill=DARK_GREEN,
    )
    add_text(
        draw,
        (124, 166),
        "Sonuç: temel doğru, mevcut model saha için NO-GO",
        34,
        bold=True,
        fill=RED,
    )
    label = "Detaylı teknik rapor" if detailed else "6 sayfalık sade karar raporu"
    add_text(draw, (125, 225), f"{label} • 12 Ağustos 2026", 23, fill=MUTED)
    add_text(
        draw,
        (125, 270),
        "GERÇEK TARGET-RIG PERFORMANSI HENÜZ ÖLÇÜLMEDİ",
        23,
        bold=True,
        fill=RED,
    )
    metric_card(
        page,
        (120, 330, 620, 610),
        pct(pheno["f1"]),
        "PhenoBench frame-action F1",
        "Tüketilmiş UAV kaynak/geliştirme paneli; target-rig değil.",
        accent=ORANGE,
    )
    metric_card(
        page,
        (710, 330, 1210, 610),
        pct(bonirob["f1"]),
        "BoniRob frame-action F1",
        "Dış robot-view geliştirme paneli; tüketilmiş tek tarla/session.",
        accent=RED,
    )
    metric_card(
        page,
        (1300, 330, 1800, 610),
        "%96,5",
        "Track F1: gerekli, tek başına GO değil",
        f"Ayrı target-rig testi; tam offline güvenlik kapısı sayfa {complete_gate_page}.",
        accent=GREEN,
    )
    card(draw, (120, 700, 1800, 910), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (165, 735), "TEK CÜMLELİK KARAR", 26, bold=True, fill=BLUE)
    add_text(
        draw,
        (165, 782),
        "Seçilen ROSE-native temel 3aba4b19…; fiziksel A–E receipt ve gerçek "
        "capture henüz yok. Sıradaki adım: A–E bench → ≥3 tarla / ≥4 session pilot.",
        29,
        bold=True,
        width=94,
    )
    return page


def outcome_page(summary: Mapping[str, Any]) -> Image.Image:
    pheno = summary["phenobench"]["selected"]
    synthetic = summary["synthetic"]["selected_fixed_pheno_threshold"]
    bonirob = summary["bonirob"]["selected"]
    page = base_page(
        "Kanıt rolleri ve metrik anahtarı",
        "Gerçek target-rig sonucu yok: aşağıdaki üç sayı geliştirme/tanı panellerine aittir.",
    )
    metric_card(
        page,
        (80, 250, 575, 535),
        pct(pheno["f1"]),
        "PhenoBench gerçek kaynak paneli",
        f"P {pct(pheno['precision'])} • R {pct(pheno['recall'])} • crop hit {pct(pheno['crop_collision_rate_per_attempt'])}",
        accent=ORANGE,
    )
    metric_card(
        page,
        (712, 250, 1207, 535),
        pct(synthetic["f1"]),
        "Unseen sentetik tanı",
        f"P {pct(synthetic['precision'])} • R {pct(synthetic['recall'])}; fixed-real eşikte çöktü, seçim ağırlığı 0.",
        accent=RED,
    )
    metric_card(
        page,
        (1344, 250, 1839, 535),
        pct(bonirob["f1"]),
        "BoniRob dış robot-view paneli",
        f"P {pct(bonirob['precision'])} • R {pct(bonirob['recall'])} • crop hit {pct(bonirob['crop_collision_rate_per_attempt'])}",
        accent=RED,
    )
    draw = ImageDraw.Draw(page)
    card(draw, (100, 610, 1820, 960), fill=WHITE, outline=LINE)
    add_text(draw, (145, 642), "METRİK ANAHTARI", 25, bold=True, fill=DARK_GREEN)
    bullet_list(
        page,
        [
            "P/R/F1: tek-kare connected-region aksiyon proxy'si; IoU, botanik instance veya track metriği değil.",
            "≥82 px = sqrt(exact GT weed kutu alanı), native 1024; weed çapı veya fiziksel mm değil.",
            "Crop hit = crop'a çarpan atış denemesi / tüm atış denemeleri.",
            "%96,5 ayrı bir gelecek track-level GO kapısıdır; bu frame F1'larla doğrudan kıyaslanmaz.",
            "Sonraki kanıt: aynı kontrollü rig'den gerçek mask+track verisi ve session-ayrı test.",
        ],
        (145, 688),
        width=118,
        size=21,
        line_gap=7,
    )
    return page


def fair_ab_page(summary: Mapping[str, Any]) -> Image.Image:
    pheno = summary["phenobench"]
    rows = []
    for model in ("base_e50", "control_real_replay", "challenger_real_synthetic"):
        item = pheno["primary_by_model"][model]
        rows.append(
            [
                MODELS[model],
                pct(item["precision"]),
                pct(item["recall"]),
                pct(item["f1"]),
                pct(item["crop_collision_rate_per_attempt"]),
            ]
        )
    page = base_page(
        "Adil A/B: sentetik eklemek gerçekte ne kazandırdı?",
        "İki kol aynı 1.407 gerçek kareyi ve epoch başına 1.487 örneği gördü; fark yalnız ek 80 maruziyet.",
    )
    draw_table(
        page,
        (45, 255, 1875, 565),
        ("Model", "Precision", "Recall", "F1", "Crop hit"),
        rows,
        (0.39, 0.15, 0.15, 0.14, 0.17),
        font_size=22,
        row_height=74,
        align_right=(1, 2, 3, 4),
    )
    bootstrap = pheno["paired_bootstrap"]
    metric_card(
        page,
        (90, 650, 590, 900),
        pp(pheno["challenger_minus_control_f1"]),
        "Sentetik kol F1 farkı",
        "82 px görünümünde gerçek-tekrarı kontrolüne karşı.",
        accent=GREEN,
    )
    metric_card(
        page,
        (710, 650, 1210, 900),
        (
            f"[{100.0 * bootstrap['ci95'][0]:+.2f}; "
            f"{100.0 * bootstrap['ci95'][1]:+.2f}]"
        ).replace(".", ","),
        "%95 bootstrap aralığı",
        "Sıfırı kesiyor; tek seed ile kesin kazanç denemez.",
        accent=ORANGE,
    )
    metric_card(
        page,
        (1330, 650, 1830, 900),
        pct(bootstrap["probability_challenger_higher"]),
        "Adayın daha iyi olma olasılığı",
        "Olumlu yön sinyali; saha kararı değil.",
        accent=BLUE,
    )
    draw = ImageDraw.Draw(page)
    add_text(
        draw,
        (115, 942),
        "Karar: V12 sentetiği sınırlı çeşitlilik kaynağı olarak tut; gerçek hedef verinin yerine koyma.",
        22,
        bold=True,
        fill=DARK_GREEN,
        width=120,
    )
    return page


def pre_real_ceiling_page(summary: Mapping[str, Any]) -> Image.Image:
    ceiling = summary["pre_real_ceiling"]
    pheno = ceiling["phenobench"]
    bonirob = ceiling["bonirob"]
    synthetic = ceiling["synthetic_fixed_pheno_threshold"]
    rows = [
        [
            "Önceki: gerçek + V12",
            pct(pheno["current_best"]["f1"]),
            pct(pheno["current_best"]["crop_hit_rate"]),
            pct(bonirob["current_best"]["f1"]),
            pct(bonirob["current_best"]["crop_hit_rate"]),
            pct(synthetic["current_best"]["f1"]),
        ],
        [
            "Seçilen: gerçek + ROSE",
            pct(pheno["challenger"]["f1"]),
            pct(pheno["challenger"]["crop_hit_rate"]),
            pct(bonirob["challenger"]["f1"]),
            pct(bonirob["challenger"]["crop_hit_rate"]),
            pct(synthetic["challenger"]["f1"]),
        ],
    ]
    page = base_page(
        "Pre-real seçim: native robot detayı yönü iyileştirdi",
        "Eş checkpoint/bütçe: 80 V12 sentetik karo yerine 80 native 1024² ROSE robot crop'u; tek seed, yönsel kanıt.",
    )
    draw_table(
        page,
        (30, 235, 1890, 500),
        ("Model", "Pheno F1", "Pheno crop", "BoniRob F1", "BoniRob crop", "V12 F1"),
        rows,
        (0.34, 0.13, 0.13, 0.14, 0.14, 0.12),
        font_size=21,
        row_height=78,
        align_right=(1, 2, 3, 4, 5),
    )
    bootstrap = ceiling["paired_bootstrap_phenobench"]
    metric_card(
        page,
        (80, 580, 575, 840),
        pp(pheno["challenger"]["f1"] - pheno["current_best"]["f1"]),
        "PhenoBench F1 farkı",
        "Recall +4,95 puan; crop-hit oranı −0,86 puan.",
        accent=GREEN,
    )
    metric_card(
        page,
        (712, 580, 1207, 840),
        pp(bonirob["challenger"]["f1"] - bonirob["current_best"]["f1"]),
        "BoniRob F1 farkı",
        "Hâlâ yalnız %9,0 F1: gerçek saha için ağır NO-GO.",
        accent=ORANGE,
    )
    metric_card(
        page,
        (1344, 580, 1839, 840),
        (
            f"[{100.0 * bootstrap['ci95'][0]:+.2f}; "
            f"{100.0 * bootstrap['ci95'][1]:+.2f}]"
        ).replace(".", ","),
        "%95 Pheno paired aralığı",
        "Sıfırı kesiyor; kesin genelleme kazancı değildir.",
        accent=ORANGE,
    )
    draw = ImageDraw.Draw(page)
    card(draw, (95, 890, 1825, 970), fill=LIGHT_RED, outline=RED)
    add_text(
        draw,
        (135, 910),
        "Karar: directional pre-real aday değişti; spray GO değişmedi. V12 sentetik çöküşü domain uzmanlaşması uyarısıdır.",
        23,
        bold=True,
        fill=RED,
        width=120,
    )
    return page


def size_page(summary: Mapping[str, Any]) -> Image.Image:
    views = summary["phenobench"]["selected_by_size_px"]
    rows = []
    for size in (0, 28, 42, 56, 82):
        item = views[str(size)]
        rows.append(
            [
                f"≥{size} px" if size else "Tüm boyutlar",
                str(item["tp"] + item["fn"]),
                pct(item["precision"]),
                pct(item["recall"]),
                pct(item["f1"]),
                pct(item["crop_collision_rate_per_attempt"]),
            ]
        )
    page = base_page(
        "Küçük obje önemli; fakat tek sebep değil",
        "Tüketilmiş PhenoBench geliştirme paneli; ≥px = sqrt(GT weed kutu alanı), fiziksel mm değil.",
    )
    draw_table(
        page,
        (35, 235, 1885, 690),
        ("Uygun weed", "Adet", "Precision", "Recall", "F1", "Crop hit"),
        rows,
        (0.24, 0.10, 0.16, 0.16, 0.14, 0.20),
        font_size=21,
        row_height=68,
        align_right=(1, 2, 3, 4, 5),
    )
    draw = ImageDraw.Draw(page)
    card(draw, (95, 775, 1825, 935), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(
        draw,
        (140, 810),
        "82 px grubu daha büyük olmasına rağmen F1 %75,4'e düşüyor. Bu alt küme "
        "yalnız 202 örnek ve crop'a yakın/karmaşık büyük otlar içeriyor. Optik ayrıntı "
        "gerekir, ama domain ve crop–weed ayrımı da kritiktir.",
        27,
        bold=True,
        fill=ORANGE,
        width=105,
    )
    return page


def external_page(summary: Mapping[str, Any]) -> Image.Image:
    external = summary["bonirob"]
    rows = []
    for model in ("base_e50", "control_real_replay", "challenger_real_synthetic"):
        item = external["primary_by_model"][model]
        rows.append(
            [
                MODELS[model],
                pct(item["precision"]),
                pct(item["recall"]),
                pct(item["f1"]),
                pct(item["crop_collision_rate_per_attempt"]),
                pct(item["soil_action_rate_per_attempt"]),
            ]
        )
    selected = external["selected"]
    rows.append(
        [
            SELECTED_MODEL_LABEL,
            pct(selected["precision"]),
            pct(selected["recall"]),
            pct(selected["f1"]),
            pct(selected["crop_collision_rate_per_attempt"]),
            pct(selected["soil_action_rate_per_attempt"]),
        ]
    )
    page = base_page(
        "Dış robot-view panelinde iyileşme var; açık hâlâ çok büyük",
        "BoniRob: tüketilmiş 283 kare/tek tarla-session; model başına sabit Pheno eşiği, BoniRob tuning'i yok.",
    )
    draw_table(
        page,
        (30, 225, 1890, 610),
        ("Model", "Precision", "Recall", "F1", "Crop hit", "Toprak"),
        rows,
        (0.34, 0.14, 0.14, 0.12, 0.13, 0.13),
        font_size=21,
        row_height=70,
        align_right=(1, 2, 3, 4, 5),
    )
    tissue = external["selected_tissue"]["weed"]
    metric_card(
        page,
        (80, 650, 575, 900),
        pct(selected["recall"]),
        "82 px weed action recall",
        f"781 uygun region proxy'sinden yalnız {selected['tp']} doğru temas.",
        accent=RED,
    )
    metric_card(
        page,
        (712, 650, 1207, 900),
        pct(tissue["dice"]),
        "Weed doku Dice",
        "Yeni adayda da weed doku ayrımı saha için yetersiz.",
        accent=RED,
    )
    metric_card(
        page,
        (1344, 650, 1839, 900),
        pct(selected["soil_action_rate_per_attempt"]),
        "Atışların toprağa oranı",
        "Canlı aktüatör için tartışmasız NO-GO.",
        accent=RED,
    )
    return page


def visual_page(
    path: Path,
    title: str,
    subtitle: str,
    note: str,
    accent: tuple[int, int, int],
) -> Image.Image:
    page = base_page(title, subtitle)
    paste_contain(page, path, (65, 205, 1855, 835))
    draw = ImageDraw.Draw(page)
    card(draw, (100, 875, 1820, 965), fill=WHITE, outline=accent)
    add_text(draw, (140, 897), note, 23, bold=True, fill=accent, width=120)
    return page


def synthetic_resolution_page(summary: Mapping[str, Any]) -> Image.Image:
    views = summary["synthetic"]["selected_by_inference_size_px"]
    rows = []
    for image_size in (512, 768, 1024, 1152):
        item = views[str(image_size)]
        rows.append(
            [
                str(image_size),
                pct(item["precision"]),
                pct(item["recall"]),
                pct(item["f1"]),
                pct(item["crop_collision_rate_per_attempt"]),
            ]
        )
    page = base_page(
        "Sentetik unseen test: çözünürlük yardım ediyor, mucize yaratmıyor",
        "16 test karosu, 28 adet ≥82 px region proxy; sentetik skorun gerçek seçim ağırlığı sıfır.",
    )
    draw_table(
        page,
        (110, 250, 1810, 615),
        ("Inference px", "Precision", "Recall", "F1", "Crop hit"),
        rows,
        (0.27, 0.18, 0.18, 0.17, 0.20),
        font_size=23,
        row_height=72,
        align_right=(0, 1, 2, 3, 4),
    )
    draw = ImageDraw.Draw(page)
    card(draw, (105, 680, 1815, 995), fill=LIGHT_BLUE, outline=BLUE)
    bullet_list(
        page,
        [
            "1024→1152 F1 artışı yalnız +2,93 puan; 1152 aynı pikseli yeniden örnekler, optik ayrıntı yaratmaz.",
            "Bu tablo önceki V12-destekli modelindir: sentetik görmeyen kontrol %32,4, V12-destekli kol %75,8 F1 verdi.",
            "Yeni ROSE-native aday fixed-real eşikte %0,0 F1 verdi; domain uzmanlaşması açık, sentetik seçim ağırlığı yine sıfır.",
            "BoniRob yalnız yön sinyali verir; native sensör GSD + bağımsız hedef-rig verisi hâlâ zorunlu.",
        ],
        (150, 710),
        width=112,
        size=21,
        line_gap=5,
    )
    return page


def synthetic_quality_page(summary: Mapping[str, Any]) -> Image.Image:
    synth = summary["synthetic"]
    page = base_page(
        "V12 sentetik paket gate'i geçti; botanik gerçeklik sınırı var",
        "80 train + 16 validation + 16 test; seed/asset/toprak/HDRI rolleri ayrık.",
    )
    metric_card(
        page,
        (80, 245, 575, 515),
        pct(synth["polygon_reconstruction_iou_p05"], 2),
        "Polygon reconstruction p05",
        "Maske→YOLO poligonu bilgi kaybı düşük.",
        accent=GREEN,
    )
    metric_card(
        page,
        (712, 245, 1207, 515),
        pct(synth["green_dominant_fraction"]["crop"]),
        "Crop yeşil-dominant piksel",
        "HSV köprüsü yalnız kilitli gerçek train referansından.",
        accent=GREEN,
    )
    metric_card(
        page,
        (1344, 245, 1839, 515),
        pct(synth["green_dominant_fraction"]["weed"]),
        "Weed yeşil-dominant piksel",
        "Arka plan pikselleri değiştirilmedi.",
        accent=GREEN,
    )
    draw = ImageDraw.Draw(page)
    card(draw, (95, 620, 1825, 930), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (140, 654), "DÜRÜST SINIR", 27, bold=True, fill=ORANGE)
    bullet_list(
        page,
        [
            "Bazı prosedürel bitki geometrileri hâlâ basit; connected region botanik instance değil.",
            "Işık renderer proxy'si; fiziksel lux, polarizasyon veya gerçek lens/MTF kalibrasyonu değil.",
            "İlk HSV paketi manuel kontrolde mavi/mor bitki hatası nedeniyle reddedildi; dönüşüm düzeltildi ve yeşil-dominance testi eklendi.",
            "Kullanım: eğitim çeşitliliği ve kamera tanısı. Gerçek GO puanına katılmaz.",
        ],
        (140, 712),
        width=108,
        size=23,
        line_gap=9,
    )
    return page


def rig_page(summary: Mapping[str, Any]) -> Image.Image:
    contract = summary["capture_contract"]
    page = base_page(
        "Dondurulan tek-modül baseline: kontrollü görüntü, güvenli hesap",
        "Tasarım ve model-compute kanıtı var; fiziksel A–E kabul receipt'i olmadığı için veri toplama henüz kapalı.",
    )
    draw = ImageDraw.Draw(page)
    boxes = [
        ((60, 270, 405, 525), "KAPALI HOOD", "600×600 mm; çift mat esnek etek"),
        ((435, 270, 780, 525), "4-BÖLGE STROBE", "150 µs pulse; 170 µs poz içinde"),
        ((810, 270, 1155, 525), "BASLER PRO", "a2A2464-77ucPRO; 5 MP global shutter"),
        ((1185, 270, 1530, 525), "8 MM / f5,6", "474–484 mm FOV; fokus kilitli"),
        ((1560, 270, 1905, 525), "NATIVE + VETO", "2048²; 4 karo + 64 px abstain"),
    ]
    for index, (box, title, note) in enumerate(boxes):
        card(draw, box, fill=WHITE, outline=GREEN)
        add_text(draw, (box[0] + 22, box[1] + 26), title, 25, bold=True, fill=DARK_GREEN)
        add_text(draw, (box[0] + 22, box[1] + 83), note, 21, width=24, fill=MUTED)
        if index < len(boxes) - 1:
            draw.polygon(
                [(box[2] + 27, 388), (box[2] + 9, 378), (box[2] + 9, 398)],
                fill=GREEN,
            )
    metric_card(
        page,
        (80, 650, 575, 910),
        "0,231–0,236 mm/px",
        "Ölçülecek GSD zarfı",
        f"10 mm ≥{contract['worst_case_10_mm_span_px']:.1f} px; 20 mm ≥{contract['worst_case_20_mm_span_px']:.1f} px.".replace(".", ","),
        accent=GREEN,
    )
    metric_card(
        page,
        (712, 650, 1207, 910),
        f"{contract['frozen_exposure_us']:.0f} µs",
        "1,0 m/s sabit pozlama",
        f"Analitik blur {contract['blur_px_at_1_m_s']:.2f} px; fizik gate ≤0,75 px.".replace(".", ","),
        accent=BLUE,
    )
    metric_card(
        page,
        (1344, 650, 1839, 910),
        "1 kamera / 15 Hz",
        "Ölçülen model yolu p95 %79",
        "Acquisition, tracking, scheduling ve actuation dahil değil.",
        accent=BLUE,
    )
    budget = contract["bom_budget"]["subtotal_range"]
    add_text(
        draw,
        (105, 930),
        "Bugünkü durum: physical A–E sonucu yok → collection kapalı; A–F sonucu yok → dry-marker kapalı; kimyasal kapı desteklenmiyor.",
        18,
        bold=True,
        fill=RED,
        width=145,
    )
    add_text(
        draw,
        (105, 975),
        f"Baseline BOM: {budget[0]:,.0f}–{budget[1]:,.0f} USD (RTX 3090 yeniden kullanım, vergi/kargo hariç). Ayrıntı: CONTROLLED_CAPTURE_OPTIMIZATION_V2.md".replace(",", "."),
        18,
        bold=True,
        fill=MUTED,
        width=145,
    )
    return page


def rig_acceptance_page(summary: Mapping[str, Any]) -> Image.Image:
    rig = summary["target_rig_contracts"]["rig_acceptance"]
    page = base_page(
        "A–E veri toplama, A–F dry-marker; kimyasal kapı yok",
        "Fiziksel receipt yok: collection ve dry-marker bugün kapalı, chemical fire her durumda unsupported.",
    )
    rows = [
        ["A", "Kimlik + satın alma", "Exact renkli PRO/BAS varyantı, lens, IR-cut ve güncel teklif"],
        ["B", "Transport + termal", "10.000 trigger: 0 kayıp; 120 dk soak; jitter ve bus droop geçer"],
        ["C", "Optik 27 hücre", "3×3 bölge × 3 yükseklik: GSD, MTF50 ve reprojection ayrı geçer"],
        ["D", "Hood + ışık", "Off/on ≤0,10; uniformity ≥0,75; SNR ≥20 dB; glare A/B"],
        ["E", "Hareket + E2E", "Acquisition+tracking+transfer dahil 15 Hz p95; frame drop/deadline miss yok"],
        ["F", "Kayıt + nozzle", "Ayrı nonchemical dry-marker: p95 ≤5 mm; fault injection no-fire"],
    ]
    draw_table(
        page,
        (55, 235, 1865, 790),
        ("Gate", "Ne doğrulanır?", "Geçiş kanıtı"),
        rows,
        (0.09, 0.27, 0.64),
        font_size=20,
        row_height=75,
    )
    draw = ImageDraw.Draw(page)
    card(draw, (90, 855, 1830, 970), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(
        draw,
        (135, 883),
        f"Durum: collection={str(rig['current_controlled_data_collection_allowed']).lower()}, "
        f"dry-marker={str(rig['current_dry_marker_allowed']).lower()}, chemical={str(rig['chemical_fire_allowed']).lower()}. "
        "F geçse bile frozen V2'de nicel deposition/crop-injury eşiği yoktur; kimyasal ateş açılamaz.",
        25,
        bold=True,
        fill=ORANGE,
        width=110,
    )
    return page


def target_rig_readiness_page(summary: Mapping[str, Any]) -> Image.Image:
    target = summary["target_rig_contracts"]
    capture = target["capture"]
    finetune = target["fine_tune"]
    action = target["track_action_evaluation"]
    rows = [
        [
            "1. Fiziksel rig",
            "NOT_READY",
            "A–E physical receipt yok",
            "Hash-bound A–E PASS → yalnız RGB collection",
        ],
        [
            "2. Capture",
            capture["current_audit_status"],
            "Real manifest/audit yok",
            "≥3 tarla / ≥4 session; image SHA + exact metadata",
        ],
        [
            "3. Fine-tune",
            "BLOCKED",
            finetune["manager_acceptance_status"],
            "30 epoch, 1024, seed 41; fixed last.pt; test izole",
        ],
        [
            "4. Track action",
            action["current_evaluation_status"],
            "evaluated_checkpoint = null",
            "Validation threshold; test bir kez; pooled + her tarla",
        ],
        [
            "5. Ateşleme",
            "NO-GO",
            "Real action/physical sonuç yok",
            "A–F yalnız dry-marker; chemical gate unsupported",
        ],
    ]
    page = base_page(
        "Pre-real target-rig zinciri: sözleşmeler hazır, gerçek kanıt yok",
        "Her aşama önceki hash-bound çıktıyı tüketir; fixture veya yeniden etiketleme READY üretemez.",
    )
    draw_table(
        page,
        (30, 225, 1890, 720),
        ("Aşama", "Bugün", "Blokaj", "Açılma koşulu"),
        rows,
        (0.19, 0.14, 0.25, 0.42),
        font_size=19,
        row_height=80,
    )
    draw = ImageDraw.Draw(page)
    card(draw, (90, 790, 1830, 955), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (135, 820), "SEÇİLEN BAŞLANGIÇ", 24, bold=True, fill=BLUE)
    add_text(
        draw,
        (135, 865),
        "YOLO26s-seg ROSE-native directional foundation • SHA-256 "
        f"{target['selected_foundation']['checkpoint_sha256'][:16]}… • hedef-rig fine-tune veya deployment modeli değil.",
        24,
        bold=True,
        fill=INK,
        width=112,
    )
    return page


def tracking_page(summary: Mapping[str, Any]) -> Image.Image:
    selected_bonirob = summary["bonirob"]["selected"]
    page = base_page(
        "Track-action metriği: validation seçer, test bir kez okunur",
        "Uygun denominator etiketten önce donar; evaluator stable track ID'leri tüketir, association'ı onarmaz.",
    )
    draw = ImageDraw.Draw(page)
    steps = [
        ("1", "Uygun GT track", "≥20 mm, visible ≥0,70, non-partial gözlem"),
        ("2", "Stable predicted ID", "Field/session/video içinde sabit; evaluator repair etmez"),
        ("3", "3/5 onay", "Üç qualifying gözlem / beş frame index"),
        ("4", "Crop safety veto", "Action point qualifying crop maskesinde ise ateş yok"),
        ("5", "Bir track / bir atış", "Fragmentation duplicate FP; tüm atışlar safety paydasında"),
    ]
    y = 235
    for number, title, note in steps:
        draw.ellipse((85, y, 155, y + 70), fill=DARK_GREEN)
        add_text(draw, (108, y + 12), number, 32, bold=True, fill=WHITE)
        card(draw, (185, y - 8, 1820, y + 82), fill=WHITE, outline=LINE)
        add_text(draw, (225, y + 9), title, 26, bold=True, fill=DARK_GREEN)
        add_text(draw, (720, y + 12), note, 23, fill=MUTED, width=70)
        y += 142
    card(draw, (110, 930, 1790, 990), fill=LIGHT_RED, outline=RED)
    add_text(
        draw,
        (145, 945),
        f"Bugünkü BoniRob recall {pct(selected_bonirob['recall'])}; gerçek evaluated checkpoint yok. Tracking görünmeyen weed'i yaratamaz.",
        23,
        bold=True,
        fill=RED,
        width=120,
    )
    return page


def diagnosis_page(summary: Mapping[str, Any]) -> Image.Image:
    selected_bonirob = summary["bonirob"]["selected"]
    page = base_page(
        "Başarıyı uçuracak kaldıraçların önceliği",
        "İki ana etken doğru: domain uyumu ve kontrollü optik. Uygulama sırası önemli.",
    )
    rows = [
        [
            "1",
            "Domain uyumu",
            f"BoniRob F1 {pct(selected_bonirob['f1'])}",
            "Aynı rig'den gerçek train/val; hard-negative",
        ],
        ["2", "Optik bilgi", "10 mm hedef 41 px", "Yakın FOV, fokus/MTF, global shutter"],
        ["3", "Işık kontrolü", "Açık hava varyansı", "Mat hood + diffuse tetikli strobe"],
        ["4", "Temporal karar", "Tek-kare gürültüsü", "3/5 onay + tek track/tek atış"],
        ["5", "Veri dengesi", "Crop-yakın hata", "Evre, ıslak/kuru toprak, gölge strata"],
        ["6", "Model/modalite", "Ancak tavan kalırsa", "Büyük backbone veya NIR/red-edge A/B"],
    ]
    draw_table(
        page,
        (30, 225, 1890, 770),
        ("Sıra", "Etken", "Bugünkü kanıt", "Uygulama"),
        rows,
        (0.08, 0.22, 0.27, 0.43),
        font_size=21,
        row_height=74,
    )
    draw = ImageDraw.Draw(page)
    card(draw, (105, 840, 1815, 955), fill=LIGHT_BLUE, outline=BLUE)
    add_text(
        draw,
        (150, 872),
        "Detection'a geçmek crop/weed domain uyumu sorununu çözmedi. Segmentasyon; "
        "crop veto, footprint ve ileride lazer/mekanik genişleme için doğru temel olarak kalıyor.",
        25,
        bold=True,
        fill=BLUE,
        width=108,
    )
    return page


def proof_plan_page() -> Image.Image:
    page = base_page(
        "Sıradaki fiziksel kanıt zinciri — adım atlama yok",
        "İlk açılacak kapı fiziksel A–E'dir; bugünkü public/synthetic paneller collection izni vermez.",
    )
    rows = [
        ["1. Physical A–E", "Hash-bound bench PASS", "Collection ancak bundan sonra açılır"],
        ["2. Gerçek capture", "≥3 tarla / ≥4 field-session", "Mask + track + image SHA + exact hardware metadata"],
        ["3. Split + audit", "Field 60/20/20", "Session/video-track/adjacent frame sızıntısı yok"],
        ["4. Fine-tune", "30 epoch / 1024 / seed 41", "Manager acceptance; fixed epoch-30 last.pt; test yok"],
        [
            "5. Track test",
            "P≥%98 • R≥%95 • F1≥%96,5",
            "Crop-hit oranı + zorunlu Wilson üst %95 ≤%0,5; "
            "duplicate-shot ≤%1; pooled PASS + her-field PASS",
        ],
        ["6. Physical action", "A–F yalnız dry-marker", "Chemical kapı yeni deposition/crop-injury eşiği olmadan kapalı"],
    ]
    draw_table(
        page,
        (40, 225, 1880, 760),
        ("Aşama", "Geçiş kapısı", "Kanıt"),
        rows,
        (0.22, 0.30, 0.48),
        font_size=20,
        row_height=76,
    )
    draw = ImageDraw.Draw(page)
    card(draw, (95, 835, 1825, 955), fill=LIGHT_GREEN, outline=GREEN)
    add_text(
        draw,
        (140, 867),
        "Şimdi yapılacak tek adım: gerçek Basler proof modülünde A–E receipt'i üretmek. "
        "PASS yoksa capture, training, offline GO ve herhangi bir ateşleme ilerlemez.",
        25,
        bold=True,
        fill=DARK_GREEN,
        width=106,
    )
    return page


def competitor_page() -> Image.Image:
    rows = [
        ["Ecorobotix ARA", "Gündüz/gece, alt koruyucu örtü", "RGB+3D; aynı P/R/F1 yok"],
        ["Greeneye", "%95,7 weed detection (vendor trial)", "Action F1/crop-hit ile aynı değil"],
        ["Bilberry", ">%90 hit; >5 cm weed (FAQ)", "Boyut/payda bizim gate'ten farklı"],
        ["Verdant", "Yüksek çözünürlük + spatial tracking", "Karşılaştırılabilir P/R/F1 yok"],
    ]
    page = base_page(
        "Piyasa ceiling'i var; vendor yüzdeleri aynı metrik değil",
        "Ortak ticari desen: kontrollü görüntüleme, çoklu aydınlatma ve temporal konumlama.",
    )
    draw_table(
        page,
        (45, 245, 1875, 655),
        ("Sistem", "Yayımlanan iddia/özellik", "Dürüst yorum"),
        rows,
        (0.22, 0.36, 0.42),
        font_size=21,
        row_height=84,
    )
    draw = ImageDraw.Draw(page)
    card(draw, (90, 745, 1830, 935), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (135, 778), "CEILING KARARI", 27, bold=True, fill=ORANGE)
    add_text(
        draw,
        (135, 828),
        "Vision açısından yapılabilir bir ürün sınıfı var; fakat rakip claim'leri bizim "
        "≥20 mm track-action P/R/F1 ve crop-hit sözleşmemizi geçmiş sayılmaz. Kendi kapalı "
        "testimizi kurmamız gerekiyor.",
        25,
        bold=True,
        fill=ORANGE,
        width=108,
    )
    return page


def limitations_page() -> Image.Image:
    page = base_page(
        "Neyi kanıtladık, neyi kanıtlamadık?",
        "Sayılar geliştirme kararı içindir; henüz ürün performans iddiası değildir.",
    )
    draw = ImageDraw.Draw(page)
    card(draw, (65, 235, 920, 900), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (110, 275), "KANITLANDI", 31, bold=True, fill=GREEN)
    bullet_list(
        page,
        [
            "Instance segmentation adil detection kıyasından daha iyi PoC temeli.",
            "Rig, capture, fine-tune ve track-action sözleşmeleri executable ve fail-closed.",
            "ROSE-native aday PhenoBench/BoniRob'da yönsel F1 ve crop-hit kazanımı verdi.",
            "Native robot detayı yararlı; domain uyumu hâlâ ana darboğaz.",
            "RTX 3090 model katmanı tek kamera / 15 Hz halo baseline'ını p95'te taşıyor.",
        ],
        (110, 345),
        width=47,
        size=23,
        line_gap=14,
    )
    card(draw, (1000, 235, 1855, 900), fill=LIGHT_RED, outline=RED)
    add_text(draw, (1045, 275), "KANITLANMADI", 31, bold=True, fill=RED)
    bullet_list(
        page,
        [
            "Fiziksel A–E receipt, gerçek capture READY ve %96,5 track-action F1.",
            "Farklı tarla/session'larda worst-field genelleme.",
            "Target-rig fine-tune checkpoint'i veya tracking'in net katkısı.",
            "Nozul footprint, deposition, weed kill veya crop injury.",
            "Sentetik assetlerin tam botanik/fiziksel gerçekliği.",
            "Tek-seed ROSE katkısının istatistiksel kesinliği veya ticari kullanım hakkı.",
        ],
        (1045, 345),
        width=47,
        size=23,
        line_gap=14,
    )
    add_text(
        draw,
        (100, 945),
        "Protokol notu: iki eğitim kolunda aynı otomatik final-validation raporu çalıştı; gradient/checkpoint seçimi yapmadı, test okunmadı.",
        21,
        fill=MUTED,
        width=125,
    )
    return page


def provenance_page(summary: Mapping[str, Any]) -> Image.Image:
    hashes = summary["input_sha256"]
    page = base_page(
        "Tekrarlanabilirlik makbuzu",
        "Tam JSON yolları, checkpoint hashleri ve deney configleri kilitli.",
    )
    rows = [
        ["Pheno action metrics", hashes["action_metrics"][:16] + "…"],
        ["BoniRob external", hashes["external_metrics"][:16] + "…"],
        ["Synthetic diagnostic", hashes["synthetic_metrics"][:16] + "…"],
        ["Pre-real selection", hashes["pre_real_result"][:16] + "…"],
        ["Rig acceptance contract", hashes["rig_acceptance_contract"][:16] + "…"],
        ["Capture manifest schema", hashes["capture_manifest_schema"][:16] + "…"],
        ["Capture audit policy", hashes["capture_audit_policy"][:16] + "…"],
        ["Capture audit CLI", hashes["capture_audit_implementation"][:16] + "…"],
        ["Target-rig fine-tune", hashes["target_rig_finetune_contract"][:16] + "…"],
        ["Fine-tune CLI", hashes["target_rig_finetune_implementation"][:16] + "…"],
        ["Track-action evaluator", hashes["target_rig_action_eval_contract"][:16] + "…"],
    ]
    draw_table(
        page,
        (150, 190, 1770, 820),
        ("Artefakt", "SHA-256 (kısaltılmış)"),
        rows,
        (0.50, 0.50),
        font_size=19,
        row_height=49,
    )
    draw = ImageDraw.Draw(page)
    card(draw, (110, 855, 1810, 980), fill=LIGHT_BLUE, outline=BLUE)
    add_text(
        draw,
        (150, 880),
        "Tam hashler metrics_summary.json içindedir. Seçilen foundation 3aba4b19…; "
        "evaluated target-rig checkpoint hâlâ null ve gerçek result receipt yoktur.",
        24,
        bold=True,
        fill=BLUE,
        width=110,
    )
    return page


def markdown_report(summary: Mapping[str, Any]) -> str:
    pheno = summary["phenobench"]
    bonirob = summary["bonirob"]
    synthetic = summary["synthetic"]
    ceiling = summary["pre_real_ceiling"]
    target = summary["target_rig_contracts"]
    p = pheno["selected"]
    b = bonirob["selected"]
    bootstrap = pheno["paired_bootstrap"]
    ceiling_bootstrap = ceiling["paired_bootstrap_phenobench"]
    lines = [
        "# Kontrollü spot-spray segmentasyon PoC'si — detaylı rapor",
        "",
        "**Karar: Instance segmentation temeli korunur; mevcut model ile saha ateşlemesi NO-GO'dur.**",
        "",
        "**Gerçek target-rig performansı henüz ölçülmedi.** PhenoBench tüketilmiş bir UAV kaynak/geliştirme paneli; BoniRob sabit eşikli, daha önce tüketilmiş tek tarla/session dış robot-view geliştirme panelidir. İkisi de önerilen hood, strobe, optik ve GSD düzeninin saha kanıtı değildir.",
        "",
        "En önemli bulgu, küçük obje çözünürlüğünün tek darboğaz olmadığıdır. "
        f"Seçilen model PhenoBench ≥82 px görünümünde P/R/F1 `{p['precision']:.4f}/{p['recall']:.4f}/{p['f1']:.4f}` verirken, "
        f"aynı kilitli eşiklerle BoniRob'da `{b['precision']:.4f}/{b['recall']:.4f}/{b['f1']:.4f}` seviyesine düştü. "
        "Öncelik sırası domain uyumu, kontrollü optik/ışık ve temporal safety'dir.",
        "",
        "## 0. Güncel target-rig hazırlık durumu",
        "",
        f"Seçilen fine-tune temeli `{target['selected_foundation']['checkpoint']}` ve SHA-256 `{target['selected_foundation']['checkpoint_sha256']}` değeridir. Bu checkpoint yönsel pre-real ROSE-native adaydır; target-rig fine-tune, deployment veya kimyasal ateşleme modeli değildir.",
        "",
        "| Aşama | Bugünkü durum | Neden açılmadı? |",
        "|---|---|---|",
        "| Fiziksel rig | `NOT_READY` | Hash-bound physical A–E kabul sonucu yok; controlled RGB collection kapalı. |",
        "| Capture/audit | `NOT_READY` | Gerçek `capture_manifest_v1`, doğrulanmış image SHA/content ve ≥3 tarla/≥4 field-session yok. |",
        f"| Fine-tune | `{target['fine_tune']['status']}` | Manager acceptance `{target['fine_tune']['manager_acceptance_status']}`; gerçek READY audit yok; training başlamadı. |",
        "| Track-action eval | `NOT_READY` | `evaluated_checkpoint` ve SHA-256 `null`; gerçek prediction/result receipt yok. |",
        "| Saha / kimyasal | `NO-GO` / `NO-GO_UNSUPPORTED` | Offline ve fiziksel sonuç yok; frozen V2 nicel deposition/crop-injury eşiği tanımlamıyor. |",
        "",
        "Sözleşme ve fixture testlerinin geçmesi gerçek performans değildir. Sentetik fixture `FIXTURE_ONLY`/`NOT_READY` kalır; public PhenoBench/BoniRob ve V12 panelleri collection, training, offline GO veya ateşleme izni vermez.",
        "",
        "## 1. Gerçek saha başarı sözleşmesi",
        "",
        "Spot spray için ana metrik mIoU değil, uygun bir weed track'inde güvenli atış kararıdır:",
        "",
        "- track action precision `≥0.98`; recall `≥0.95`; F1 `≥0.965`;",
        "- crop-hit / attempted action `≤0.005` ve zorunlu Wilson üst %95 sınırı `≤0.005`;",
        "- duplicate shot `≤0.01`; pooled test ve her test tarlası ayrı ayrı `PASS`;",
        "- sentetik skorun gerçek GO kararındaki ağırlığı `0`.",
        "",
        "Bu gate geçse bile nozzle deposition, weed kill ve crop injury ayrı fiziksel deneydir.",
        "",
        "Gösterilen P/R/F1 değerleri **tek-kare connected-region aksiyon proxy'sidir**; segmentation IoU, botanik-instance veya track metriği değildir. `≥82 px`, native 1024 rasterda `sqrt(exact GT weed bounding-box area)` tanımıdır; weed çapı veya fiziksel mm değildir. `Crop hit`, crop'a çarpan atış denemelerinin tüm atış denemelerine oranıdır. Gelecekteki `0,965` track F1 yalnız bir gerekli koşuldur, tek başına GO değildir; bu frame-level F1 değerleriyle de doğrudan kıyaslanmaz.",
        "",
        "## 2. Pre-real model-ceiling seçimi",
        "",
        "Aynı başlangıç checkpoint'i, 1.487 örnek/epoch, 8 epoch, 1024 px, batch 3 ve seed 41 korundu. Tek fark, önceki adayın 80 V12 sentetik train karosu yerine 80 benzersiz native 1024×1024 ROSE robot-view train crop'u görmesidir.",
        "",
        "| Panel | Model | Precision | Recall | F1 | Crop hit |",
        "|---|---|---:|---:|---:|---:|",
        f"| PhenoBench | Önceki V12 | {ceiling['phenobench']['current_best']['precision']:.4f} | {ceiling['phenobench']['current_best']['recall']:.4f} | {ceiling['phenobench']['current_best']['f1']:.4f} | {ceiling['phenobench']['current_best']['crop_hit_rate']:.4f} |",
        f"| PhenoBench | Seçilen ROSE-native | {ceiling['phenobench']['challenger']['precision']:.4f} | {ceiling['phenobench']['challenger']['recall']:.4f} | {ceiling['phenobench']['challenger']['f1']:.4f} | {ceiling['phenobench']['challenger']['crop_hit_rate']:.4f} |",
        f"| BoniRob | Önceki V12 | {ceiling['bonirob']['current_best']['precision']:.4f} | {ceiling['bonirob']['current_best']['recall']:.4f} | {ceiling['bonirob']['current_best']['f1']:.4f} | {ceiling['bonirob']['current_best']['crop_hit_rate']:.4f} |",
        f"| BoniRob | Seçilen ROSE-native | {ceiling['bonirob']['challenger']['precision']:.4f} | {ceiling['bonirob']['challenger']['recall']:.4f} | {ceiling['bonirob']['challenger']['f1']:.4f} | {ceiling['bonirob']['challenger']['crop_hit_rate']:.4f} |",
        "",
        f"PhenoBench F1 farkı `{ceiling['phenobench']['challenger']['f1'] - ceiling['phenobench']['current_best']['f1']:+.4f}`; paired bootstrap medyanı `{ceiling_bootstrap['median_difference']:+.4f}`, %95 aralığı `[{ceiling_bootstrap['ci95'][0]:+.4f}, {ceiling_bootstrap['ci95'][1]:+.4f}]`. Aralık sıfırı keser. BoniRob F1 artışı yönsel olarak daha büyüktür fakat panel tüketilmiş tek session'dır. Seçilen model fixed-real eşikte V12 sentetik testte `{ceiling['synthetic_fixed_pheno_threshold']['challenger']['f1']:.4f}` F1 ve sıfır atış verdi. Sentetik ağırlık `0`; spray kararı NO-GO olarak değişmedi.",
        "",
        "## 3. Adil gerçek-tekrarı / gerçek+sentetik A/B (önceki aşama)",
        "",
        "İki kol aynı başlangıç checkpoint'inden başladı, aynı 1.407 gerçek train karesini gördü ve epoch başına 1.487 örnek aldı. Kontrol 80 gerçek kareyi deterministik tekrar etti; aday bunun yerine 80 V12 sentetik train karesi gördü. İki kol 8 epoch, 1024 px ve seed 41 ile çalıştı.",
        "",
        "| Model | Precision | Recall | F1 | Crop hit |",
        "|---|---:|---:|---:|---:|",
    ]
    for model in ("base_e50", "control_real_replay", "challenger_real_synthetic"):
        item = pheno["primary_by_model"][model]
        lines.append(
            f"| {MODELS[model]} | {item['precision']:.4f} | {item['recall']:.4f} | {item['f1']:.4f} | {item['crop_collision_rate_per_attempt']:.4f} |"
        )
    lines.extend(
        [
            "",
            f"Aday–kontrol F1 farkı `{pheno['challenger_minus_control_f1']:+.4f}`. Paired bootstrap medyanı `{bootstrap['median_difference']:+.4f}`, %95 aralığı `[{bootstrap['ci95'][0]:+.4f}, {bootstrap['ci95'][1]:+.4f}]`; adayın daha iyi olma olasılığı `{bootstrap['probability_challenger_higher']:.3f}`. Aralık sıfırı kestiği ve tek seed olduğu için bu kesin kazanç değil, olumlu yön sinyalidir.",
            "",
            "Ultralytics `val:false` talebine rağmen her iki kolda aynı otomatik final-validation raporunu çalıştırdı. Bu rapor gradientlere girmedi, sabit `last.pt` checkpoint'ini seçmedi ve test verisini okumadı. Tarihsel receipt'teki `real_val_test_not_touched` ifadesi validation için fazla güçlüdür; A/B adilliği korunmuştur.",
            "",
            "## 4. Boyut tek açıklama değil",
            "",
            "Boyut `sqrt(exact GT weed bounding-box area)` olarak native 1024 rasterda hesaplanır; fiziksel mm değildir.",
            "",
            "| Alt boyut | Uygun weed | Precision | Recall | F1 | Crop hit |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for size in (0, 28, 42, 56, 82):
        item = pheno["selected_by_size_px"][str(size)]
        lines.append(
            f"| {size} px | {item['tp'] + item['fn']} | {item['precision']:.4f} | {item['recall']:.4f} | {item['f1']:.4f} | {item['crop_collision_rate_per_attempt']:.4f} |"
        )
    lines.extend(
        [
            "",
            "≥82 px grubu daha iyi değildir; yalnız 202 örnektir ve crop'a yakın/karmaşık büyük otları da içerir. Optik ayrıntı gereklidir fakat domain ve crop–weed ayrımı aynı derecede kritiktir.",
            "",
            "## 5. BoniRob dış robot-view geliştirme paneli",
            "",
            "BoniRob paneli 283 ardışık kare, tek tarla ve tek session'dan gelir ve daha önce geliştirme çalışmalarında tüketilmiştir. Deployment/final saha kanıtı değildir. PhenoBench'te kilitlenen eşiklere BoniRob tuning'i yapılmamıştır.",
            "",
            "| Model | Precision | Recall | F1 | Crop hit | Toprak |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for model in ("base_e50", "control_real_replay", "challenger_real_synthetic"):
        item = bonirob["primary_by_model"][model]
        lines.append(
            f"| {MODELS[model]} | {item['precision']:.4f} | {item['recall']:.4f} | {item['f1']:.4f} | {item['crop_collision_rate_per_attempt']:.4f} | {item['soil_action_rate_per_attempt']:.4f} |"
        )
    lines.append(
        f"| {SELECTED_MODEL_LABEL} | {b['precision']:.4f} | {b['recall']:.4f} | {b['f1']:.4f} | {b['crop_collision_rate_per_attempt']:.4f} | {b['soil_action_rate_per_attempt']:.4f} |"
    )
    tissue = bonirob["selected_tissue"]["weed"]
    lines.extend(
        [
            "",
            f"Seçilen modelin weed doku Dice/IoU değeri `{tissue['dice']:.4f}/{tissue['iou']:.4f}`. ≥82 px regionlarda action recall `{b['recall']:.4f}`. Görseller ara sıra doğru weed temasını ve ayrı bir safety hatasını birlikte gösterir; toplam panel sonucu hâlâ ağır domain açığıdır.",
            "",
            "![BoniRob kaçırma örneği](figures/bonirob_000.jpg)",
            "",
            "## 6. V12 sentetik kalite ve unseen test",
            "",
            f"V12: `{synthetic['train_tiles']}/{synthetic['val_tiles']}/{synthetic['test_tiles']}` train/val/test karesi; rol seedleri ve asset/yüzey kaynakları ayrık. Poligon reconstruction IoU p05 `{synthetic['polygon_reconstruction_iou_p05']:.4f}`; crop/weed yeşil-dominant oranları `{synthetic['green_dominant_fraction']['crop']:.4f}/{synthetic['green_dominant_fraction']['weed']:.4f}`.",
            "",
            "İlk HSV paketi manuel kontrolde mavi/mor bitki ürettiği için reddedildi. Dönüşüm düzeltildi, yeşil-dominance regression testi eklendi ve paket yeniden üretildi. Final pakette bu hata yoktur.",
            "",
            "Connected region botanik instance değildir; bazı prosedürel bitkiler basit ve ışık fiziksel radyometriye kalibre değildir. Bu yüzden sentetik skor gerçek model seçiminde kullanılmaz.",
            "",
            "| Inference boyutu | Precision | Recall | F1 | Crop hit |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for image_size in (512, 768, 1024, 1152):
        item = synthetic["selected_by_inference_size_px"][str(image_size)]
        lines.append(
            f"| {image_size} | {item['precision']:.4f} | {item['recall']:.4f} | {item['f1']:.4f} | {item['crop_collision_rate_per_attempt']:.4f} |"
        )
    lines.extend(
        [
            "",
            f"1152 yazılım resize'ıdır ve yeni optik ayrıntı yaratmaz. Bu tablo önceki V12-destekli modelindir; seçilen ROSE-native aday fixed-real eşikte V12 ≥82 px testinde `{synthetic['selected_fixed_pheno_threshold']['f1']:.4f}` F1 verdi. Bu domain uzmanlaşması uyarısıdır.",
            "",
            "![Unseen sentetik örnek](figures/synthetic_test_10.jpg)",
            "",
            "## 7. Dondurulacak inference ortamı",
            "",
            "- Basler `a2A2464-77ucPRO` 5 MP renkli global-shutter + fabrika IR-cut;",
            "- Basler `C23-0824-5M-P` 8,06 mm lens, `f/5,6`, fokus/iris kilitli;",
            "- merkezlenmiş native `2048×2048` ROI; `(200,0)` ofset; dijital resize yok;",
            "- ölçülmüş `474–484 mm` FOV: GSD `0,231–0,236 mm/px`; 10 mm `≥42,3 px`, 20 mm `≥84,6 px`;",
            "- `520–590 mm` ayarlı çalışma mesafesi; nominal `555,6 mm`;",
            "- tek kamera, `15 Hz`, `170 µs` poz; 1,0 m/s'de analitik blur `0,719 px`;",
            "- dört diffuse LED bölgesi, kamera ExposureActive ile `150 µs` strobe;",
            "- `600×600 mm` mat hood, çift esnek etek/labirent ve değiştirilebilir eğik AR pencere;",
            "- dört native 1024 core + gerçek komşu pikselden 64 px halo; dış 64 px no-fire/abstain;",
            "- dünya koordinatında distance + mask-IoU tracking, 3/5 onay, crop veto, tek track/tek atış.",
            "",
            "Bu baseline henüz fiziksel kabul değildir. Dondurulmuş A–E kapıları procurement/identity, transport-trigger-thermal, 27-hücre optik, hood/ışık ve acquisition+tracking+transfer dahil motion/E2E ölçümlerini fiziksel artifact SHA'larıyla ister. Yalnız physical A–E PASS kontrollü RGB collection açabilir. A–F PASS ayrı, kimyasal içermeyen dry-marker kapısıdır. Frozen V2 nicel deposition/crop-injury kabul eşiği tanımlamadığı için F geçse bile chemical fire kapalıdır.",
            "",
            "RTX 3090 halo benchmark'ında batch-4 p95 servis süresi `52,68 ms` oldu. Ölçülen model yolu preprocessing, forward pass, NMS, mask construction ve result transfer'ı kapsar. Tek kamera 15 Hz satırı p95 `%79,0` compute kullanımı ve `13,99 ms` compute-only artıkla geçer; 20 Hz `%105,4` ile geçmez. Kamera acquisition, tracking, scheduling, actuation ve spray fiziği dahil değildir. Bu zincirle 15 Hz E2E tekrar geçmeden baseline sistem düzeyinde kanıtlanmış sayılmaz. İkinci kamera aynı RTX 3090'a eklenmez; her yeni bay ayrı USB root ve bağımsız kanıtlı accelerator kapasitesi ister.",
            "",
            "Baseline incremental BOM `3.115–6.545 USD`, `%15` contingency ile `3.582–7.527 USD`'dir; mevcut RTX 3090 yeniden kullanılır, vergi/kargo dahil değildir. Exact BOM ve optik türetim [`CONTROLLED_CAPTURE_OPTIMIZATION_V2.md`](../../CONTROLLED_CAPTURE_OPTIMIZATION_V2.md) ile makine-okunur [`controlled_capture_optimization_v2.json`](../controlled_capture_optimization_v2.json) içindedir. Fiziksel kabul sözleşmesi [`SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md`](../../SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md) içindedir.",
            "",
            "Kaynaklar: [Basler PRO teknik dokümanı](https://docs.baslerweb.com/a2a2464-77ucpro), [C23 lens teknik dokümanı](https://docs.baslerweb.com/c23-0824-5m-p), [Basler triggered acquisition](https://docs.baslerweb.com/triggered-image-acquisition), [FLIR challenger spec](https://softwareservices.flir.com/BFS-U3-51S5/latest/Model/spec.html), [polarizasyon](https://www.edmundoptics.com/knowledge-center/application-notes/imaging/machine-vision-filter-technology/).",
            "",
            "## 8. Segmentasyon ve tracking kararı",
            "",
            "Adil target-trained detection/segmentation kıyasındaki action sonucu segmentasyonu tercih ettirdi. Segmentasyon crop veto, nozzle footprint ve ileride lazer/mekanik için daha zengin geometri taşır. Detection'a dönmek domain uyumu sorununu çözmez.",
            "",
            f"Tracking geçici false-positive'leri ve duplicate atışı azaltabilir. Fakat BoniRob'taki `{pct(b['recall'])}` recall sistematik sınıf kaçırmasıdır; tracking görünmeyen weed'i yaratamaz. Kazanç gerçek video track testiyle ölçülmeli, varsayılmamalıdır.",
            "",
            "Gerçek capture sözleşmesi her görüntüyü exact image SHA-256, hardware frame counter/camera timestamp, exposure/gain/manual WB, working distance, native dimensions/pixel format, camera+rig+profile kimliği ve exact strobe binding ile taşır. Crop/weed/partial_unknown instance maskeleri ile stable track ID korunur; stem/keypoint V1'de ertelenmiştir. Deterministik `60/20/20` roller fiziksel field düzeyinde atanır; field, session, video-track ve komşu kareler roller arasında geçemez.",
            "",
            "Fine-tune bugün fail-closed blokludur: physical `READY` audit ve açık manager acceptance olmadan çalışmaz. Açıldığında seçilen foundation'dan `30 epoch / 1024 / batch 3 / seed 41` ile gider, yalnız fixed epoch-30 `last.pt` seçilir; test görüntüsü veya etiketi training datasetine materialize edilmez. Final checkpoint yine `NOT_EVALUATED` kalır.",
            "",
            "Track-action evaluator stable predicted track ID'leri tüketir. Uygun GT weed denominator'ı ≥20 mm, visible fraction ≥0,70 ve non-partial gözlemle etiketten donar. Üç qualifying gözlem beş frame index içinde tek atış üretir; crop veto ve fragmentation duplicate FP önce uygulanır. Confidence threshold yalnız validation'da seçilir; test o eşikte bir kez okunur. Pooled ve her tarla P/R/F1, crop-hit Wilson üst %95 sınırı ve duplicate gate'leri birlikte geçmeden offline model GO yoktur.",
            "",
            "## 9. En etkili sonraki kanıt",
            "",
            "1. Gerçek Basler proof modülünde A–E'yi fiziksel artifact/receipt SHA'larıyla geçir; bu ilk ve mevcut tek unblock adımıdır.",
            "2. Collection açılırsa aynı donanımla en az 3 tarla ve 4 field/session grubu topla; exact image/provenance metadata ile instance mask + track ID etiketle.",
            "3. Deterministik field `60/20/20` splitini dondur; session/video-track/komşu kare leakage auditini `READY` geçir.",
            "4. Manager acceptance sonrası seçilen ROSE-native foundation'ı frozen 30-epoch tarifle fine-tune et; fixed `last.pt` path/SHA'yı receipt'e bağla.",
            "5. Validation'da threshold seç, test'i bir kez aç; pooled + her-field track P/R/F1, crop-hit Wilson üst sınırı ve duplicate gate'lerini raporla.",
            "6. Ayrı physical A–F ile yalnız nonchemical dry-marker'ı değerlendir. Chemical fire, yeni nicel deposition/crop-injury sözleşmesi ve gerçek kanıt olmadan kapalı kalır.",
            "7. Kontrollü RGB tavanı gerçek testte kalırsa ancak o zaman daha büyük backbone veya NIR/red-edge A/B aç.",
            "",
            "## 10. Rakip ceiling'i",
            "",
            "[Ecorobotix ARA](https://ecorobotix.com/crop-care/ara-620-uhp-sprayer/) gündüz/gece, alt koruyucu örtü ve RGB+3D modüller kullanıyor. [Greeneye](https://greeneye.ag/trials/) vendor deneyinde %95,7 weed detection; [Bilberry](https://bilberry.io/faq/) >5 cm weed için >%90 hit bildiriyor. [Verdant](https://www.verdantrobotics.com/faqs) yüksek çözünürlük, spatial tracking ve hareket telafisini vurguluyor. Payda, action F1, crop-hit ve güven aralığı aynı olmadığı için bunlar bizim gate ile bire bir kıyas değildir; kontrollü görüntüleme + temporal konumlamanın doğru ticari desen olduğunu destekler.",
            "",
            "## 11. Son karar",
            "",
            "Mevcut model saha için yeterli değildir. Segmentasyon temeli, compute kapasitesi ve fail-closed rig/capture/fine-tune/action sözleşmeleri hazırdır; bunların fixture başarısı gerçek READY değildir. Eksik ilk parça fiziksel A–E receipt'tir; ardından aynı rig'den provenance-bound gerçek crop/weed track verisi gerekir. En yüksek getirili adım yeni model aramak değil, A–E bench → audited pilot → frozen fine-tune → ayrı track-action test zinciridir. Chemical fire kapalıdır.",
            "",
            "Tam değerler ve SHA-256 makbuzları [`metrics_summary.json`](metrics_summary.json) içindedir.",
        ]
    )
    return "\n".join(lines) + "\n"


def package_readme(summary: Mapping[str, Any]) -> str:
    pheno = summary["phenobench"]["selected"]
    bonirob = summary["bonirob"]["selected"]
    target = summary["target_rig_contracts"]
    return f"""# Kontrollü spot-spray PoC sonucu

Buradan başlayın:

- [6 sayfalık sade karar PDF'i](BASLA_BURADAN_KONTROLLU_SPOT_SPRAY_POC_V1.pdf)
- [Açıklamalı detaylı PDF](DETAYLI_KONTROLLU_SPOT_SPRAY_POC_V1.pdf)
- [Aranabilir detaylı rapor](DETAYLI_RAPOR.md)
- [Makine-okunur exact metrikler](metrics_summary.json)
- [Seçili self-sufficient görseller](figures/README.md)
- [Exact kamera/lens/ışık/hız/BOM baseline'ı](../../CONTROLLED_CAPTURE_OPTIMIZATION_V2.md)
- [Fiziksel A–F rig kabul runbook'u](../../SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md)
- [Capture/annotation/split sözleşmesi](../../SPOT_SPRAY_DATA_CAPTURE_AND_ANNOTATION_V1.md)
- [Fail-closed fine-tune ve track-action hattı](../../SPOT_SPRAY_TARGET_RIG_MODEL_PIPELINE_V1.md)

Kısa karar: instance segmentation temel olarak kalıyor; mevcut model saha
ateşlemesi için **NO-GO**. Henüz gerçek target-rig sonucu yoktur. Tüketilmiş
PhenoBench UAV geliştirme panelinde ≥82 px frame-action F1 `{pct(pheno['f1'])}`, tüketilmiş
tek-session BoniRob dış robot-view geliştirme panelinde `{pct(bonirob['f1'])}` oldu.
Seçilen model, eş bütçeli `80 V12 sentetik → 80 native ROSE robot crop'u`
deneyinin yönsel adayıdır; SHA-256
`{target['selected_foundation']['checkpoint_sha256']}` ile yalnız fine-tune
foundation'ıdır. Fiziksel A–E receipt, gerçek `capture_manifest_v1`, target-rig
fine-tune checkpoint'i ve track-action sonucu yoktur; bu yüzden pipeline
`PRE_REAL_NOT_READY` kalır. Sıradaki tek unblock, physical A–E PASS'tir;
ardından en az 3 tarla / 4 field-session, deterministic field split ve ayrı
track-action testi gelir. A–F yalnız nonchemical dry-marker açabilir; chemical
fire frozen V2'de unsupported ve kapalıdır.
"""


def figure_readme() -> str:
    return """# Görsel kanıtlar

Her görsel kendi başlığı ve legend'i ile tek başına okunabilir:

- `bonirob_000.jpg`: seçilen ROSE-native adayda bir doğru temas ve kalan kaçışlar.
- `bonirob_150.jpg`: seçilen ROSE-native adayda action-level safety hatası.
- `synthetic_test_10.jpg`: unseen sentetik holdout ve atış noktası örneği.
- `synthetic_test_00.jpg`: ikinci sentetik toprak/bitki örneği.

Legend: gerçek maske yeşil=mahsul, kırmızı=yabani ot; tahmin
yeşil=mahsul, mor=yabani ot; mavi nokta=güvenli weed teması,
sarı/çarpı=hatalı müdahale.

Kanıt rolleri: BoniRob görselleri seçilen `3aba4b19…` ROSE-native foundation'ın
daha önce tüketilmiş tek tarla/session dış robot-view geliştirme panelidir;
target-rig, bağımsız field veya deployment kanıtı değildir. Sentetik görseller
asset/seed-ayrık tanı fixture'larıdır ve gerçek model/GO karar ağırlıkları
`0`dır. Hiçbir görsel physical A–E kabulü, real capture READY, target-rig
fine-tune, track-action GO, dry-marker veya chemical-fire izni göstermez.
"""


def build_pages(
    summary: Mapping[str, Any], figures: Mapping[str, Path]
) -> tuple[list[Image.Image], list[Image.Image]]:
    concise = [
        cover(summary, detailed=False),
        outcome_page(summary),
        pre_real_ceiling_page(summary),
        visual_page(
            figures["bonirob_000"],
            "Seçilen ROSE-native aday: BoniRob örneği",
            "Tüketilmiş tek tarla/session; sabit Pheno eşiği, target-rig veya deployment kanıtı değil.",
            "Aday bu karede bir weed'i güvenli yakalıyor; panel toplamı yine yalnız %5,8 recall / %9,0 F1.",
            ORANGE,
        ),
        rig_page(summary),
        proof_plan_page(),
    ]
    detailed = [
        cover(summary, detailed=True),
        outcome_page(summary),
        pre_real_ceiling_page(summary),
        fair_ab_page(summary),
        size_page(summary),
        external_page(summary),
        visual_page(
            figures["bonirob_000"],
            "Seçilen aday: yakalanan weed, kaçan bölgeler",
            "Önceden tüketilmiş BoniRob session'ı; sabit eşik, target-rig testi değil.",
            "Bir doğru temas var; geniş weed bölgelerinin çoğu hâlâ kaçıyor. Küçük obje tek darboğaz değil.",
            ORANGE,
        ),
        visual_page(
            figures["bonirob_150"],
            "Seçilen aday: sınıf ayrımı iyileşti, safety hatası sürüyor",
            "Aynı tüketilmiş tek-session panel; target-rig veya bağımsız holdout değil.",
            "Crop ve weed maskeleri görünür; sarı çarpı action-level hatanın hâlâ neden ayrı ölçüldüğünü gösteriyor.",
            RED,
        ),
        synthetic_quality_page(summary),
        synthetic_resolution_page(summary),
        visual_page(
            figures["synthetic_test_10"],
            "Unseen sentetik holdout örneği",
            "Train/validation'dan seed, asset ve yüzey rolü ayrık test karesi.",
            "Sentetik pipeline çalışıyor; bu gerçek saha GO kanıtı değildir.",
            GREEN,
        ),
        diagnosis_page(summary),
        rig_page(summary),
        rig_acceptance_page(summary),
        target_rig_readiness_page(summary),
        tracking_page(summary),
        proof_plan_page(),
        competitor_page(),
        limitations_page(),
        provenance_page(summary),
    ]
    return concise, detailed


def write_package(output: Path) -> dict[str, Any]:
    inputs = {
        "action": load(ACTION),
        "synthetic": load(SYNTHETIC),
        "external": load(EXTERNAL),
        "ab_receipt": load(AB_RECEIPT),
        "synthetic_receipt": load(SYNTHETIC_RECEIPT),
        "synthetic_release": load(SYNTHETIC_RELEASE),
        "compute": load(COMPUTE),
        "compute_halo": load(COMPUTE_HALO),
        "capture_v2": load(CAPTURE_V2),
        "pre_real_result": load(PRE_REAL_RESULT),
        "pre_real_diagnostics": load(PRE_REAL_DIAGNOSTICS),
        "pre_real_gallery": load(PRE_REAL_GALLERY_RECEIPT),
        "rig_acceptance": load_yaml(RIG_ACCEPTANCE),
        "capture_schema": load(CAPTURE_SCHEMA),
        "capture_policy": load_yaml(CAPTURE_POLICY),
        "finetune_contract": load_yaml(FINETUNE_CONTRACT),
        "action_eval_contract": load_yaml(ACTION_EVAL_CONTRACT),
    }
    summary = build_summary(inputs)
    output.mkdir(parents=True, exist_ok=True)
    figures_dir = output / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    sources = {
        "bonirob_000": PRE_REAL_GALLERY / "bonirob_000.jpg",
        "bonirob_150": PRE_REAL_GALLERY / "bonirob_150.jpg",
        "synthetic_test_10": SYNTHETIC_GALLERY / "synthetic_test_10.jpg",
        "synthetic_test_00": SYNTHETIC_GALLERY / "synthetic_test_00.jpg",
    }
    figures: dict[str, Path] = {}
    for key, source in sources.items():
        if not source.is_file():
            raise FileNotFoundError(source)
        destination = figures_dir / source.name
        shutil.copy2(source, destination)
        figures[key] = destination

    (output / "metrics_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output / "DETAYLI_RAPOR.md").write_text(
        markdown_report(summary), encoding="utf-8"
    )
    (output / "README.md").write_text(package_readme(summary), encoding="utf-8")
    (figures_dir / "README.md").write_text(figure_readme(), encoding="utf-8")

    concise, detailed = build_pages(summary, figures)
    concise_name = "Kontrollü spot-spray PoC — sade karar"
    detailed_name = "Kontrollü spot-spray PoC — detaylı kanıt"
    finalize_pages(concise, concise_name)
    finalize_pages(detailed, detailed_name)
    concise_pdf = output / "BASLA_BURADAN_KONTROLLU_SPOT_SPRAY_POC_V1.pdf"
    detailed_pdf = output / "DETAYLI_KONTROLLU_SPOT_SPRAY_POC_V1.pdf"
    save_pdf(concise, concise_pdf, title=concise_name)
    save_pdf(detailed, detailed_pdf, title=detailed_name)

    receipt: dict[str, Any] = {
        "schema_version": 2,
        "status": "report_package_complete_pre_real_target_rig_not_ready",
        "decision": {
            "selected_foundation_checkpoint_sha256": summary[
                "target_rig_contracts"
            ]["selected_foundation"]["checkpoint_sha256"],
            "target_rig_status": summary["target_rig_contracts"]["overall_status"],
            "field_fire_status": summary["target_rig_contracts"][
                "field_fire_status"
            ],
            "chemical_fire_status": summary["target_rig_contracts"][
                "chemical_fire_status"
            ],
        },
        "pdf_pages": {
            "BASLA_BURADAN_KONTROLLU_SPOT_SPRAY_POC_V1.pdf": len(concise),
            "DETAYLI_KONTROLLU_SPOT_SPRAY_POC_V1.pdf": len(detailed),
        },
        "target_rig_source_sha256": {
            key: summary["input_sha256"][key]
            for key in (
                "rig_acceptance_contract",
                "rig_acceptance_implementation",
                "capture_manifest_schema",
                "capture_audit_policy",
                "capture_audit_implementation",
                "target_rig_finetune_contract",
                "target_rig_finetune_implementation",
                "target_rig_action_eval_contract",
                "target_rig_action_eval_implementation",
            )
        },
        "output": str(output),
        "files": {},
    }
    for path in sorted(item for item in output.rglob("*") if item.is_file()):
        if path.name == "report_receipt.json":
            continue
        receipt["files"][str(path.relative_to(output))] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    (output / "report_receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return receipt


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    receipt = write_package(args.output.resolve())
    print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
