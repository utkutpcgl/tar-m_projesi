#!/usr/bin/env python3
"""Seal and run the extension-aware, model-free full-plan validator.

This is an append-only validation epoch.  It deliberately leaves the legacy
full-plan validator and every V1/runtime release byte untouched.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_spot_spray_simulation_video_ab_execution_v1 as execution


DEFAULT_CONFIG = execution.runtime_compatibility_paths(
    execution.load_config(execution.DEFAULT_CONFIG)
)["config"]

CONTRACT = "spot_spray_simulation_video_ab_extension_aware_full_plan_validation_v1"
LOCK_CONTRACT = f"{CONTRACT}_lock"
RELEASE_CONTRACT = f"{CONTRACT}_release"
AUTHORIZATION_CONTRACT = f"{CONTRACT}_manager_authorization"
VALIDATION_RECEIPT_CONTRACT = f"{CONTRACT}_pass64_validation"
PASS64_EVENT_ID = "scheduled-resume-20260820045840-2def69a6294d"
OWNER_SESSION_ID = "01a0019e-e810-73b3-9f29-ffad14c34ec5"
RUN_ID = "goal-multi-repeat-full-simulation-video-ab-execution-v1-e2dcf4ac8b10"
PORTFOLIO_ID = "goal-multi-repeat-agents-spot-spray-simulation-video-ab-v1-b8e46607aeea"
PORTFOLIO_LANE = "full-simulation-video-ab-execution-v1"
PORTFOLIO_REVISION = 110

RUNTIME_CONFIG_SHA256 = (
    "a443af36f5d1345daf3b5234d4b8d7d53cfa73e399e33c6181e5b8288f641339"
)
RUNTIME_RELEASE_FILE_SHA256 = (
    "4acfca1e21051db6aa791efc6bb3a4b1cea3912fd6eced3461bd9747be26094b"
)
RUNTIME_RELEASE_IDENTITY_SHA256 = (
    "5ff230c802392fa114f1dfe52ad505b05b05b3895a5b6f013fa3f69fec6d9446"
)
PASS63_BLOCKER_RECEIPT_SHA256 = (
    "0a549b4951f91a45b1d0be551a1a8b5d6b84d02bbd47bddcce27ec67ab728791"
)
FROZEN_STATE_SHA256 = execution.HISTORICAL_V1_BINDINGS["render_state_sha256"]
CURRENT_STATE_SHA256 = (
    "0e2f0ed5143dca870b3e7d4c9096bd79025b2bc7456d77dc4e1f2d0fbd9457f5"
)
LEDGER_SHA256 = execution.HISTORICAL_V1_BINDINGS[
    "candidate_rejection_ledger_sha256"
]
HISTORICAL_INVENTORY_IDENTITY_SHA256 = (
    "f5ab73a0547b14024fc6e0b908c4c4aef07c65a22f8f1e0ae9e752aab6b92d1d"
)
APPENDED_PAIR_ID = "locked_test_c001_r00"
CANDIDATE_10_IDENTITY_SHA256 = (
    "887f18acce3d4e0a75e7d8670d22d433374898c031724feabdd6561d25ec76a4"
)
CANDIDATE_10_CANONICAL_GT_SHA256 = (
    "fbf72d2a23279c95e82f4e959f21bb190224f69bd4442227f8d143985c2363f4"
)
CANDIDATE_10_FULL_PAIR_RECEIPT_SHA256 = (
    "069312f20781123251a74bc0e7321868b79a7ca037ad3decdbc5193559a1dfe7"
)
CANDIDATE_10_PAIR_RECEIPT_SHA256 = (
    "bee4bfe16e0e6d1e25ceca1cd73e6d84d56e492fdd407189640479cc44e198f5"
)
CANDIDATE_10_BATCH_RECEIPT_SHA256 = (
    "eba74b284befe86d92a21028abdd603b29c2c17f6ca62f67df26186dfe8fd4a2"
)
CANDIDATE_10_CONTACT_SHEET_SHA256 = (
    "98aa0a985b9501dc5058b3cb7879c666a8062531802bec3cb5df3c46f826e8de"
)
CANDIDATE_10_SEEDS = {
    "audit_sample_seed": 8422460394543698405,
    "capture_draw_seed": 8882908064289344753,
    "renderer_seed": 15157628161568229920,
    "scene_seed": 7226111793099446366,
    "trajectory_seed": 12825880541104311247,
}


def validation_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    full = execution.full_paths(config)
    synthetic = (
        full["synthetic"]
        / "planning/extension_aware_full_plan_validation_v1/release_v1"
    )
    docs = full["docs"] / "extension_aware_full_plan_validation_v1/release_v1"
    return {
        "synthetic": synthetic,
        "docs": docs,
        "bridge": synthetic / "extension_aware_full_plan_validation_bridge_v1.json",
        "lock": synthetic / "extension_aware_full_plan_validation_lock_v1.json",
        "release": synthetic / "extension_aware_full_plan_validation_release_v1.json",
        "authorization_receipt": synthetic / "pass64_manager_authorization_receipt.json",
        "validation_receipt": synthetic / "pass64_validation_receipt.json",
    }


def _required_files() -> list[str]:
    return [
        "extension_aware_full_plan_validation_bridge_v1.json",
        "extension_aware_full_plan_validation_lock_v1.json",
        "extension_aware_full_plan_validation_release_v1.json",
        "pass64_manager_authorization_receipt.json",
        "pass64_validation_receipt.json",
    ]


def _claim_boundary(config: Mapping[str, Any]) -> dict[str, Any]:
    policy = copy.deepcopy(dict(config["evidence_policy"]))
    if (
        policy.get("scope") != "synthetic_diagnostic_only"
        or policy.get("field_or_deployment_claim_allowed") is not False
        or policy.get("product_go_allowed") is not False
        or policy.get("chemical_fire_go_allowed") is not False
        or policy.get("synthetic_score_weight_in_real_go_decision") != 0.0
        or policy.get("outcome_target_tuning_forbidden") is not True
    ):
        raise execution.ContractError("Synthetic-only claim boundary changed")
    return policy


def _runtime_parent(config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    config_path = config_path.expanduser().resolve()
    historical = execution.load_config(execution.DEFAULT_CONFIG)
    runtime_paths = execution.runtime_compatibility_paths(historical)
    if config_path != runtime_paths["config"].resolve():
        raise execution.ContractError("Noncanonical extension-aware runtime config")
    if execution.sha256_file(config_path) != RUNTIME_CONFIG_SHA256:
        raise execution.ContractError("Extension-aware runtime config bytes changed")
    if execution.sha256_file(runtime_paths["release"]) != RUNTIME_RELEASE_FILE_SHA256:
        raise execution.ContractError("Runtime compatibility release bytes changed")
    runtime = execution.validate_runtime_compatibility_release(config_path)
    if (
        runtime.get("runtime_compatibility_release_identity_sha256")
        != RUNTIME_RELEASE_IDENTITY_SHA256
        or runtime.get("runtime_compatibility_config_sha256")
        != RUNTIME_CONFIG_SHA256
        or runtime.get("model_loaded") is not False
        or runtime.get("inference_calls") != 0
        or runtime.get("outcome_inputs") != []
    ):
        raise execution.ContractError("Runtime compatibility release binding changed")
    return execution.load_config(config_path), runtime


def _static_inventory_rows(
    rows: Sequence[Mapping[str, Any]], *, mutable_path: str
) -> dict[str, Any]:
    skipped: list[Mapping[str, Any]] = []
    checked = 0
    for row in rows:
        path_text = str(row.get("path", ""))
        if path_text == mutable_path:
            skipped.append(row)
            continue
        path = execution.resolve_path(path_text)
        if (
            not path.is_file()
            or path.stat().st_size != int(row.get("size_bytes", -1))
            or execution.sha256_file(path) != row.get("sha256")
        ):
            raise execution.ContractError(
                f"Immutable historical evidence changed: {path_text}"
            )
        checked += 1
    if len(skipped) != 1 or skipped[0].get("sha256") != FROZEN_STATE_SHA256:
        raise execution.ContractError("Historical live-state inventory bridge changed")
    return {
        "static_file_count": checked,
        "mutable_state_inventory_row_count": 1,
        "frozen_mutable_state_sha256": FROZEN_STATE_SHA256,
    }


def _validate_static_history(config: Mapping[str, Any]) -> dict[str, Any]:
    parent = execution._validate_frozen_pass55_release(config)
    paths = execution.roster_extension_paths(config)
    inventory = execution.load_json(paths["evidence_inventory"])
    rows = inventory.get("files")
    if (
        not isinstance(rows, list)
        or inventory.get("inventory_sha256")
        != HISTORICAL_INVENTORY_IDENTITY_SHA256
        or execution.stable_sha256(rows) != HISTORICAL_INVENTORY_IDENTITY_SHA256
        or inventory.get("file_count") != len(rows)
    ):
        raise execution.ContractError("Historical evidence inventory identity changed")
    mutable = execution.display_path(execution.full_paths(config)["docs"] / "render_state_v1.json")
    result = _static_inventory_rows(rows, mutable_path=mutable)
    return {
        **result,
        "historical_inventory_sha256": execution.sha256_file(
            paths["evidence_inventory"]
        ),
        "historical_inventory_identity_sha256": HISTORICAL_INVENTORY_IDENTITY_SHA256,
        "parent_execution_release_identity_sha256": parent[
            "parent_execution_release_identity_sha256"
        ],
        "all_nonstate_historical_bytes_unchanged": True,
    }


def _rosters(config: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    full = execution.full_paths(config)
    historical_path = full["synthetic"] / "planning/pair_roster_v1.jsonl"
    if execution.sha256_file(historical_path) != execution.HISTORICAL_V1_BINDINGS[
        "pair_roster_sha256"
    ]:
        raise execution.ContractError("Historical V1 roster bytes changed")
    historical = execution.read_jsonl(historical_path)
    extension_path = execution.roster_extension_paths(config)["manifest"]
    extension = execution.read_jsonl(extension_path)
    protocol = execution._protocol(config)
    template_inventory = execution.load_json(
        full["synthetic"] / "planning/template_inventory_v1.json"
    )
    result = execution.validate_roster_extension_rows(
        extension, historical, protocol, template_inventory
    )
    if (
        result.get("all_96_slots_presealed") is not True
        or result.get("combined_candidate_count") != 3072
        or result.get("unique_combined_candidate_identity_count") != 3072
        or result.get("unique_combined_seed_count") != 15360
    ):
        raise execution.ContractError("Sealed combined roster validation changed")
    combined = execution.merge_full_roster_with_extension(historical, extension)
    _validate_combined_roster_epochs(historical, combined)
    return historical, combined


def _validate_combined_roster_epochs(
    historical: Sequence[Mapping[str, Any]], combined: Sequence[Mapping[str, Any]]
) -> None:
    if len(historical) != 96 or len(combined) != 96:
        raise execution.ContractError("Combined roster is partial")
    identities: list[str] = []
    for old, merged in zip(historical, combined, strict=True):
        if (
            old.get("pair_id") != merged.get("pair_id")
            or old.get("pair_slot_identity_sha256")
            != merged.get("pair_slot_identity_sha256")
            or list(merged.get("candidates", []))[:10] != list(old.get("candidates", []))
        ):
            raise execution.ContractError("Historical roster prefix changed")
        candidates = list(merged.get("candidates", []))
        if [row.get("candidate_index") for row in candidates] != list(range(32)):
            raise execution.ContractError("Combined candidate epoch order changed")
        identities.extend(str(row.get("candidate_identity_sha256")) for row in candidates)
    if len(identities) != 3072 or len(set(identities)) != 3072:
        raise execution.ContractError("Combined candidate identities collide")


def _validate_transition(
    frozen: Mapping[str, Any],
    current: Mapping[str, Any],
    roster_pair_ids: Sequence[str],
) -> dict[str, Any]:
    if (
        frozen.get("planned_pair_count") != 96
        or frozen.get("completed_pair_count") != 40
        or frozen.get("pending_pair_count") != 56
        or frozen.get("pending_pair_ids", [None])[0] != APPENDED_PAIR_ID
        or frozen.get("interrupted_staging_directories") != []
        or frozen.get("model_outputs_present") is not False
    ):
        raise execution.ContractError("Frozen 40/96 state semantics changed")
    expected = copy.deepcopy(dict(frozen))
    expected["completed_pair_count"] = 41
    expected["pending_pair_count"] = 55
    expected["completed_pair_ids"] = [
        *list(frozen["completed_pair_ids"]),
        APPENDED_PAIR_ID,
    ]
    expected["pending_pair_ids"] = list(frozen["pending_pair_ids"])[1:]
    if dict(current) != expected:
        raise execution.ContractError("Live render state is not the exact 40-to-41 append")
    if [*current["completed_pair_ids"], *current["pending_pair_ids"]] != list(
        roster_pair_ids
    ):
        raise execution.ContractError("Live render state roster order changed")
    return {
        "from_completed_pair_count": 40,
        "to_completed_pair_count": 41,
        "appended_pair_id": APPENDED_PAIR_ID,
        "first_pending_pair_id": current["pending_pair_ids"][0],
        "historical_completed_prefix_unchanged": True,
        "pending_order_unchanged_except_exact_removal": True,
    }


def _validate_live_boundary(
    config: Mapping[str, Any], combined: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    paths = execution.full_paths(config)
    planning = paths["synthetic"] / "planning"
    snapshot_root = planning / "historical_epoch_v1_source_snapshots"
    frozen_path = snapshot_root / "render_state_v1.ff06d781.json"
    planning_state_path = planning / "render_state_v1.json"
    docs_state_path = paths["docs"] / "render_state_v1.json"
    ledger_path = planning / "candidate_rejection_ledger_v1.jsonl"
    frozen_ledger_path = snapshot_root / "candidate_rejection_ledger_v1.3c60ebab.jsonl"
    if execution.sha256_file(frozen_path) != FROZEN_STATE_SHA256:
        raise execution.ContractError("Frozen 40/96 state bytes changed")
    if (
        execution.sha256_file(planning_state_path) != CURRENT_STATE_SHA256
        or execution.sha256_file(docs_state_path) != CURRENT_STATE_SHA256
    ):
        raise execution.ContractError("Current 41/96 state bytes changed")
    transition = _validate_transition(
        execution.load_json(frozen_path),
        execution.load_json(planning_state_path),
        [str(row["pair_id"]) for row in combined],
    )
    if (
        execution.sha256_file(ledger_path) != LEDGER_SHA256
        or execution.sha256_file(frozen_ledger_path) != LEDGER_SHA256
    ):
        raise execution.ContractError("Candidate rejection ledger bytes changed")
    ledger = execution.read_jsonl(ledger_path)
    if len(ledger) != 111 or ledger != execution.read_jsonl(frozen_ledger_path):
        raise execution.ContractError("Candidate rejection ledger prefix changed")
    partials = sorted(
        execution.display_path(path)
        for root in (paths["synthetic"] / "work", planning / "gt_scout_v1")
        if root.exists()
        for path in root.rglob(".partial-*")
    )
    if partials:
        raise execution.ContractError("Partial render or scout staging exists")
    if paths["run"].exists() and any(path.is_file() for path in paths["run"].rglob("*")):
        raise execution.ContractError("Full benchmark model output exists")
    if any(
        path.is_file() and "prediction" in path.name.lower()
        for path in paths["synthetic"].rglob("*")
    ):
        raise execution.ContractError("Prediction output exists in full benchmark root")
    return {
        **transition,
        "frozen_render_state_sha256": FROZEN_STATE_SHA256,
        "current_render_state_sha256": CURRENT_STATE_SHA256,
        "candidate_rejection_ledger_sha256": LEDGER_SHA256,
        "candidate_rejection_ledger_row_count": 111,
        "interrupted_staging_directories": [],
        "model_outputs_present": False,
    }


def _validate_candidate10_receipt(
    receipt: Mapping[str, Any],
    candidate: Mapping[str, Any],
    roster_row: Mapping[str, Any],
    claim_boundary: Mapping[str, Any],
) -> None:
    execution._validate_publishable_full_pair_receipt(receipt, roster_row)
    if (
        receipt.get("selected_candidate_index") != 10
        or receipt.get("candidate_identity_sha256") != CANDIDATE_10_IDENTITY_SHA256
        or receipt.get("candidate_identity_sha256")
        != candidate.get("candidate_identity_sha256")
        or receipt.get("candidate_seeds") != CANDIDATE_10_SEEDS
        or receipt.get("candidate_seeds") != candidate.get("seeds")
        or receipt.get("canonical_gt_sha256") != CANDIDATE_10_CANONICAL_GT_SHA256
        or receipt.get("outcome_inputs") != []
        or receipt.get("model_loaded") is not False
        or receipt.get("inference_calls") != 0
        or receipt.get("model_outputs_present_false") is not True
        or receipt.get("claim_boundary") != dict(claim_boundary)
        or candidate.get("model_outcome_inputs") != []
    ):
        raise execution.ContractError("Candidate10 extension-epoch receipt binding changed")


def _validate_receipt_epochs(
    config: Mapping[str, Any],
    historical: Sequence[Mapping[str, Any]],
    combined: Sequence[Mapping[str, Any]],
    boundary: Mapping[str, Any],
) -> dict[str, Any]:
    paths = execution.full_paths(config)
    claim = _claim_boundary(config)
    for index, old in enumerate(historical[:40]):
        pair_id = str(old["pair_id"])
        receipt_path = (
            paths["synthetic"]
            / "pairs"
            / str(old["protocol_split"])
            / pair_id
            / "full_pair_receipt.json"
        )
        receipt = execution.load_json(receipt_path)
        execution._validate_publishable_full_pair_receipt(receipt, old)
        selected = receipt.get("selected_candidate_index")
        if not isinstance(selected, int) or isinstance(selected, bool) or not 0 <= selected <= 9:
            raise execution.ContractError(f"Historical receipt uses wrong epoch: {pair_id}")
        if pair_id != boundary.get("completed_pair_ids", [pair_id] * 40)[index]:
            raise execution.ContractError("Historical receipt order changed")

    row = next(row for row in combined if row["pair_id"] == APPENDED_PAIR_ID)
    pair_root = paths["synthetic"] / "pairs/locked_test" / APPENDED_PAIR_ID
    full_receipt_path = pair_root / "full_pair_receipt.json"
    pair_receipt_path = pair_root / "pair_receipt.json"
    contact_sheet_path = pair_root / "preoutcome_audit_contact_sheet.png"
    full_receipt = execution.load_json(full_receipt_path)
    candidate = row["candidates"][10]
    _validate_candidate10_receipt(full_receipt, candidate, row, claim)
    if (
        execution.sha256_file(full_receipt_path)
        != CANDIDATE_10_FULL_PAIR_RECEIPT_SHA256
        or execution.sha256_file(pair_receipt_path)
        != CANDIDATE_10_PAIR_RECEIPT_SHA256
        or execution.sha256_file(contact_sheet_path)
        != CANDIDATE_10_CONTACT_SHEET_SHA256
        or execution.load_json(pair_receipt_path).get("canonical_gt_sha256")
        != CANDIDATE_10_CANONICAL_GT_SHA256
    ):
        raise execution.ContractError("Candidate10 published pair bytes changed")
    batch_path = (
        paths["synthetic"]
        / "planning/locked_test_render_batches_v1/"
        "locked_test_render_batch_locked_test_c001_r00_08e1cd1a2b59a9f7/"
        "batch_receipt.json"
    )
    batch = execution.load_json(batch_path)
    current_state = execution.load_json(
        paths["synthetic"] / "planning/render_state_v1.json"
    )
    if (
        execution.sha256_file(batch_path) != CANDIDATE_10_BATCH_RECEIPT_SHA256
        or batch.get("contract") != execution.LOCKED_TEST_RENDER_BATCH_CONTRACT
        or batch.get("status")
        != "PASS_LOCKED_TEST_RENDER_BATCH_PREOUTCOME_SYNTHETIC_ONLY"
        or batch.get("new_pair_count") != 1
        or batch.get("max_new_pairs") != 1
        or batch.get("render_state") != current_state
        or batch.get("model_loaded") is not False
        or batch.get("inference_calls") != 0
        or batch.get("outcome_inputs") != []
        or batch.get("claim_boundary") != claim
    ):
        raise execution.ContractError("Candidate10 batch receipt binding changed")
    pass63_path = (
        paths["docs"]
        / "locked_test_render_batches/pass61_runtime_patch_execution/"
        "pass63_validation_blocker_receipt.json"
    )
    if execution.sha256_file(pass63_path) != PASS63_BLOCKER_RECEIPT_SHA256:
        raise execution.ContractError("Pass63 blocker receipt bytes changed")
    return {
        "historical_v1_receipt_count": 40,
        "historical_v1_candidate_epoch": [0, 9],
        "extension_receipt_count": 1,
        "extension_candidate_epoch": [10, 31],
        "candidate_10_identity_sha256": CANDIDATE_10_IDENTITY_SHA256,
        "candidate_10_canonical_gt_sha256": CANDIDATE_10_CANONICAL_GT_SHA256,
        "candidate_10_full_pair_receipt_sha256": CANDIDATE_10_FULL_PAIR_RECEIPT_SHA256,
        "candidate_10_pair_receipt_sha256": CANDIDATE_10_PAIR_RECEIPT_SHA256,
        "candidate_10_batch_receipt_sha256": CANDIDATE_10_BATCH_RECEIPT_SHA256,
        "pass63_blocker_receipt_sha256": PASS63_BLOCKER_RECEIPT_SHA256,
        "unsealed_candidate_receipts_accepted": False,
        "correct_epoch_selected_per_receipt": True,
    }


def _live_validation(config: Mapping[str, Any]) -> dict[str, Any]:
    static = _validate_static_history(config)
    historical, combined = _rosters(config)
    boundary = _validate_live_boundary(config, combined)
    state = execution.load_json(
        execution.full_paths(config)["synthetic"] / "planning/render_state_v1.json"
    )
    epochs = _validate_receipt_epochs(config, historical, combined, state)
    return {
        "static_history": static,
        "state_transition": boundary,
        "receipt_epochs": epochs,
        "combined_pair_count": len(combined),
        "combined_candidate_count": sum(len(row["candidates"]) for row in combined),
        "model_loaded": False,
        "inference_calls": 0,
        "rendering_calls": 0,
        "prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "registered_targets_used": False,
        "external_services_modified": False,
        "outcome_inputs": [],
        "claim_boundary": _claim_boundary(config),
    }


def _authorization_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": AUTHORIZATION_CONTRACT,
        "status": "PASS_MANAGER_AUTHORIZED_VALIDATION_ONLY_SYNTHETIC_ONLY",
        "authorization": {
            "event_id": PASS64_EVENT_ID,
            "goal_multi_repeat_run_id": RUN_ID,
            "pass": 64,
            "strategy": "base",
            "owner_session_id": OWNER_SESSION_ID,
            "portfolio_id": PORTFOLIO_ID,
            "portfolio_lane": PORTFOLIO_LANE,
            "portfolio_revision": PORTFOLIO_REVISION,
        },
        "pinned_inputs": {
            "runtime_config_sha256": RUNTIME_CONFIG_SHA256,
            "runtime_release_file_sha256": RUNTIME_RELEASE_FILE_SHA256,
            "runtime_release_identity_sha256": RUNTIME_RELEASE_IDENTITY_SHA256,
            "pass63_blocker_receipt_sha256": PASS63_BLOCKER_RECEIPT_SHA256,
            "frozen_render_state_sha256": FROZEN_STATE_SHA256,
            "current_render_state_sha256": CURRENT_STATE_SHA256,
            "candidate_rejection_ledger_sha256": LEDGER_SHA256,
            "candidate_10_full_pair_receipt_sha256": (
                CANDIDATE_10_FULL_PAIR_RECEIPT_SHA256
            ),
        },
        "authorized_scope": {
            "validation_bridge_only": True,
            "legacy_validator_mutation_allowed": False,
            "historical_or_runtime_release_mutation_allowed": False,
            "candidate_generation_allowed": False,
            "rendering_allowed": False,
            "model_prediction_outcome_or_target_access_allowed": False,
            "external_service_mutation_allowed": False,
        },
        "claim_boundary": _claim_boundary(config),
    }


def _bridge_payload(
    config: Mapping[str, Any], validation: Mapping[str, Any]
) -> dict[str, Any]:
    extension_paths = execution.roster_extension_paths(config)
    return {
        "schema_version": 1,
        "contract": CONTRACT,
        "status": "SEALED_EXTENSION_AWARE_FULL_PLAN_VALIDATION_BRIDGE_SYNTHETIC_ONLY",
        "runtime_parent": {
            "config_sha256": RUNTIME_CONFIG_SHA256,
            "release_file_sha256": RUNTIME_RELEASE_FILE_SHA256,
            "release_identity_sha256": RUNTIME_RELEASE_IDENTITY_SHA256,
            "roster_extension_manifest_sha256": execution.sha256_file(
                extension_paths["manifest"]
            ),
            "roster_extension_release_identity_sha256": (
                execution.ROSTER_EXTENSION_RELEASE_IDENTITY_SHA256
            ),
        },
        "immutable_history": copy.deepcopy(validation["static_history"]),
        "mutable_execution_state": copy.deepcopy(validation["state_transition"]),
        "receipt_epoch_validation": copy.deepcopy(validation["receipt_epochs"]),
        "rules": {
            "historical_candidate_indices": [0, 9],
            "extension_candidate_indices": [10, 31],
            "lowest_unattempted_candidate_wins": True,
            "duplicate_reorder_or_unsealed_candidate_fails_closed": True,
            "legacy_full_plan_validator_remains_fail_closed": True,
            "old_receipts_rewritten_or_rebound": False,
            "live_state_compared_as_mutable_old_boundary_transition": True,
        },
        "access_guard": {
            "validation_only": True,
            "candidate_generation_calls": 0,
            "rendering_calls": 0,
            "model_loaded": False,
            "inference_calls": 0,
            "prediction_accessed": False,
            "locked_test_outcome_accessed": False,
            "registered_targets_used": False,
            "external_services_modified": False,
            "outcome_inputs": [],
        },
        "claim_boundary": _claim_boundary(config),
    }


def _lock_payload(
    config: Mapping[str, Any], *, bridge_sha256: str
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": LOCK_CONTRACT,
        "status": "SEALED_EXTENSION_AWARE_VALIDATION_ONLY_SYNTHETIC_ONLY",
        "bridge_sha256": execution.require_sha256(
            bridge_sha256, "extension-aware validation bridge"
        ),
        "runtime_config_sha256": RUNTIME_CONFIG_SHA256,
        "runtime_release_identity_sha256": RUNTIME_RELEASE_IDENTITY_SHA256,
        "frozen_to_current_state_sha256": execution.stable_sha256(
            [FROZEN_STATE_SHA256, CURRENT_STATE_SHA256]
        ),
        "receipt_epoch_map": {"0-9": "historical_v1", "10-31": "extension_v1"},
        "validation_only": True,
        "candidate_or_render_execution_allowed": False,
        "model_prediction_outcome_or_target_access_allowed": False,
        "claim_boundary": _claim_boundary(config),
    }


def _release_payload(
    config: Mapping[str, Any], *, authorization_sha256: str, bridge_sha256: str, lock_sha256: str
) -> dict[str, Any]:
    test_path = PROJECT_ROOT / "tests/test_validate_spot_spray_simulation_video_ab_extension_aware_v1.py"
    payload = {
        "schema_version": 1,
        "contract": RELEASE_CONTRACT,
        "status": "SEALED_EXTENSION_AWARE_VALIDATOR_RELEASE_SYNTHETIC_ONLY",
        "authorization_receipt_sha256": authorization_sha256,
        "bridge_sha256": bridge_sha256,
        "validation_lock_sha256": lock_sha256,
        "execution_script_sha256": execution.sha256_file(Path(__file__)),
        "execution_test_sha256": execution.sha256_file(test_path),
        "runtime_config_sha256": RUNTIME_CONFIG_SHA256,
        "runtime_release_file_sha256": RUNTIME_RELEASE_FILE_SHA256,
        "runtime_release_identity_sha256": RUNTIME_RELEASE_IDENTITY_SHA256,
        "pass63_blocker_receipt_sha256": PASS63_BLOCKER_RECEIPT_SHA256,
        "candidate_10_full_pair_receipt_sha256": CANDIDATE_10_FULL_PAIR_RECEIPT_SHA256,
        "historical_bytes_rewritten_or_rebound": False,
        "legacy_validator_semantics_changed": False,
        "validation_only": True,
        "claim_boundary": _claim_boundary(config),
    }
    payload["release_identity_sha256"] = execution.stable_sha256(payload)
    return payload


def _artifact_rows(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": execution.sha256_file(path),
        }
        for path in sorted(
            (
                path
                for path in root.rglob("*")
                if path.is_file() and path.name != "pass64_validation_receipt.json"
            ),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    ]


def _validation_receipt_payload(
    config: Mapping[str, Any], root: Path, release: Mapping[str, Any], validation: Mapping[str, Any]
) -> dict[str, Any]:
    rows = _artifact_rows(root)
    return {
        "schema_version": 1,
        "contract": VALIDATION_RECEIPT_CONTRACT,
        "status": "PASS_EXTENSION_AWARE_FULL_PLAN_VALIDATION_SYNTHETIC_ONLY",
        "goal_multi_repeat_run_id": RUN_ID,
        "event_id": PASS64_EVENT_ID,
        "pass": 64,
        "validator_release_identity_sha256": release["release_identity_sha256"],
        "artifact_inventory": {
            "files": rows,
            "file_count": len(rows),
            "inventory_sha256": execution.stable_sha256(rows),
        },
        "validation": copy.deepcopy(dict(validation)),
        "access_guard": {
            "validation_only": True,
            "candidate_generation_calls": 0,
            "rendering_calls": 0,
            "model_loaded": False,
            "inference_calls": 0,
            "prediction_accessed": False,
            "locked_test_outcome_accessed": False,
            "registered_targets_used": False,
            "external_services_modified": False,
            "outcome_inputs": [],
        },
        "claim_boundary": _claim_boundary(config),
    }


def _validate_file_set(paths: Mapping[str, Path]) -> None:
    required = _required_files()
    for key in ("synthetic", "docs"):
        root = paths[key]
        observed = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        ) if root.is_dir() else []
        if observed != required:
            raise execution.ContractError("Extension-aware validator release file set changed")
    if any(
        execution.sha256_file(paths["synthetic"] / relative)
        != execution.sha256_file(paths["docs"] / relative)
        for relative in required
    ):
        raise execution.ContractError("Extension-aware validator docs mirror changed")


def seal_extension_aware_validator(config_path: Path) -> dict[str, Any]:
    config, _ = _runtime_parent(config_path)
    paths = validation_paths(config)
    parent_synthetic = paths["synthetic"].parent
    parent_docs = paths["docs"].parent
    partials = list(parent_synthetic.glob(".partial-*")) + list(parent_docs.glob(".partial-*"))
    if partials:
        raise execution.ContractError("Partial extension-aware validator release exists")
    if paths["synthetic"].exists() or paths["docs"].exists():
        if not paths["synthetic"].is_dir() or not paths["docs"].is_dir():
            raise execution.ContractError("Partial extension-aware validator release exists")
        return validate_extension_aware_full_plan(config_path)

    validation = _live_validation(config)
    authorization = _authorization_payload(config)
    bridge = _bridge_payload(config, validation)
    staging = parent_synthetic / f".partial-extension-aware-validator-v1-{uuid.uuid4().hex}"
    docs_staging = parent_docs / f".partial-extension-aware-validator-v1-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        execution.write_json(staging / "pass64_manager_authorization_receipt.json", authorization)
        execution.write_json(staging / "extension_aware_full_plan_validation_bridge_v1.json", bridge)
        lock = _lock_payload(
            config,
            bridge_sha256=execution.sha256_file(
                staging / "extension_aware_full_plan_validation_bridge_v1.json"
            ),
        )
        execution.write_json(staging / "extension_aware_full_plan_validation_lock_v1.json", lock)
        release = _release_payload(
            config,
            authorization_sha256=execution.sha256_file(
                staging / "pass64_manager_authorization_receipt.json"
            ),
            bridge_sha256=execution.sha256_file(
                staging / "extension_aware_full_plan_validation_bridge_v1.json"
            ),
            lock_sha256=execution.sha256_file(
                staging / "extension_aware_full_plan_validation_lock_v1.json"
            ),
        )
        execution.write_json(staging / "extension_aware_full_plan_validation_release_v1.json", release)
        staging.replace(paths["synthetic"])
        receipt = _validation_receipt_payload(config, paths["synthetic"], release, validation)
        execution.write_json(paths["validation_receipt"], receipt)

        docs_staging.mkdir(parents=True, exist_ok=False)
        for relative in _required_files():
            shutil.copy2(paths["synthetic"] / relative, docs_staging / relative)
        docs_staging.replace(paths["docs"])
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if docs_staging.exists():
            shutil.rmtree(docs_staging)
        raise
    return validate_extension_aware_full_plan(config_path)


def validate_extension_aware_full_plan(config_path: Path) -> dict[str, Any]:
    config, runtime = _runtime_parent(config_path)
    paths = validation_paths(config)
    partials = list(paths["synthetic"].parent.glob(".partial-*")) + list(
        paths["docs"].parent.glob(".partial-*")
    )
    if partials:
        raise execution.ContractError("Partial extension-aware validator release exists")
    _validate_file_set(paths)
    validation = _live_validation(config)

    authorization = execution.load_json(paths["authorization_receipt"])
    if authorization != _authorization_payload(config):
        raise execution.ContractError("Pass64 manager authorization receipt changed")
    bridge = execution.load_json(paths["bridge"])
    if bridge != _bridge_payload(config, validation):
        raise execution.ContractError("Extension-aware validation bridge changed")
    lock = execution.load_json(paths["lock"])
    if lock != _lock_payload(config, bridge_sha256=execution.sha256_file(paths["bridge"])):
        raise execution.ContractError("Extension-aware validation lock changed")
    release = execution.load_json(paths["release"])
    expected_release = _release_payload(
        config,
        authorization_sha256=execution.sha256_file(paths["authorization_receipt"]),
        bridge_sha256=execution.sha256_file(paths["bridge"]),
        lock_sha256=execution.sha256_file(paths["lock"]),
    )
    if release != expected_release:
        raise execution.ContractError("Extension-aware validator release changed")
    identity_payload = copy.deepcopy(release)
    identity = identity_payload.pop("release_identity_sha256", None)
    if identity != execution.stable_sha256(identity_payload):
        raise execution.ContractError("Extension-aware validator release identity changed")
    receipt = execution.load_json(paths["validation_receipt"])
    expected_receipt = _validation_receipt_payload(
        config, paths["synthetic"], release, validation
    )
    if receipt != expected_receipt:
        raise execution.ContractError("Pass64 extension-aware validation receipt changed")
    return {
        "status": receipt["status"],
        "validator_release_identity_sha256": identity,
        "runtime_compatibility_release_identity_sha256": runtime[
            "runtime_compatibility_release_identity_sha256"
        ],
        "historical_completed_pair_count": 40,
        "completed_pair_count": 41,
        "pending_pair_count": 55,
        "appended_pair_id": APPENDED_PAIR_ID,
        "candidate_10_identity_sha256": CANDIDATE_10_IDENTITY_SHA256,
        "candidate_rejection_ledger_row_count": 111,
        "legacy_validator_expected_to_fail_closed": True,
        "rendering_calls": 0,
        "model_loaded": False,
        "inference_calls": 0,
        "outcome_inputs": [],
        "synthetic_only": True,
        "field_product_or_chemical_go": False,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seal")
    subparsers.add_parser("validate")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        if arguments.command == "seal":
            result = seal_extension_aware_validator(arguments.config)
        elif arguments.command == "validate":
            result = validate_extension_aware_full_plan(arguments.config)
        else:
            raise AssertionError(arguments.command)
    except execution.ContractError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
