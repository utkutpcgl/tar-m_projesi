#!/usr/bin/env python3
"""Seal, validate, and run the extension-aware locked-test batch adapter.

The adapter is an append-only compatibility epoch.  It never changes the
legacy execution module or the extension-aware validator.  For a real batch it
temporarily replaces only ``execution.validate_full_plan`` in one process,
calls the unchanged batch function, and restores the original callable in a
``finally`` block.
"""

from __future__ import annotations

import argparse
import copy
import inspect
import json
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_spot_spray_simulation_video_ab_execution_v1 as execution
from scripts import validate_spot_spray_simulation_video_ab_extension_aware_v1 as validator


DEFAULT_CONFIG = validator.DEFAULT_CONFIG

CONTRACT = "spot_spray_simulation_video_ab_extension_aware_batch_adapter_v1"
AUTHORIZATION_CONTRACT = f"{CONTRACT}_manager_authorization"
BRIDGE_CONTRACT = f"{CONTRACT}_bridge"
LOCK_CONTRACT = f"{CONTRACT}_lock"
RELEASE_CONTRACT = f"{CONTRACT}_release"
VALIDATION_RECEIPT_CONTRACT = f"{CONTRACT}_pass66_validation"
INTENT_CONTRACT = f"{CONTRACT}_intent"
TERMINAL_RECEIPT_CONTRACT = f"{CONTRACT}_terminal_receipt"

PASS66_EVENT_ID = "scheduled-resume-20260820052759-110f0368f725"
MANAGER_HANDOFF_EVENT_ID = "scheduled-resume-20260820052135-ac610dcf4598"
OWNER_SESSION_ID = "01a0019e-e810-73b3-9f29-ffad14c34ec5"
RUN_ID = "goal-multi-repeat-full-simulation-video-ab-execution-v1-e2dcf4ac8b10"
PORTFOLIO_ID = "goal-multi-repeat-agents-spot-spray-simulation-video-ab-v1-b8e46607aeea"
PORTFOLIO_LANE = "full-simulation-video-ab-execution-v1"
PORTFOLIO_REVISION = 113

LEGACY_EXECUTION_SCRIPT_SHA256 = (
    "200d897efa1400a9dabba1acaf33d1b49db2c00ebcf79768f25fa4a8608bb413"
)
LEGACY_EXECUTION_TEST_SHA256 = (
    "66878530bb4878da29adf5b32da9fa506ccb4f132a508de105a6e11f8a65f9b5"
)
VALIDATOR_SCRIPT_SHA256 = (
    "ac27a2942dcfe68d9a5ae5232462359cec00ae280f9c3d839e1fa4f12f73834b"
)
VALIDATOR_TEST_SHA256 = (
    "0d66e6401d913e7f16b0c62ab66baa238b86237105315ff4030f1ef3c667860d"
)
RUNTIME_CONFIG_SHA256 = validator.RUNTIME_CONFIG_SHA256
RUNTIME_RELEASE_FILE_SHA256 = validator.RUNTIME_RELEASE_FILE_SHA256
RUNTIME_RELEASE_IDENTITY_SHA256 = validator.RUNTIME_RELEASE_IDENTITY_SHA256
VALIDATOR_RELEASE_FILE_SHA256 = (
    "f4474761d3742cda3c009457f194cd61914295b1ee9129dbe2f287b3b78af7ba"
)
VALIDATOR_RELEASE_IDENTITY_SHA256 = (
    "39c782e375352fdcddd62751ff4a3f4577652d111798269e549dae8bdaf066f7"
)
PASS65_RECEIPT_SHA256 = (
    "9c404702c583f27c774c14ba3ebefedc35a9b1510a4aace9e348350e0cb7e154"
)
CURRENT_STATE_SHA256 = validator.CURRENT_STATE_SHA256
LEDGER_SHA256 = validator.LEDGER_SHA256
HISTORICAL_ROSTER_SHA256 = execution.HISTORICAL_V1_BINDINGS[
    "pair_roster_sha256"
]
EXTENSION_MANIFEST_SHA256 = (
    "4ad84f3e4a2dfc2d4d49065826f12854e05c195f05c20e3a407bbc08c88b324d"
)
COMBINED_ROSTER_IDENTITY_SHA256 = (
    "99099d5deeff721fc1007da1f9842117086d3d8379ea1822df6f7fffc55abd9c"
)
LOCKED_TEST_BATCH_FUNCTION_SOURCE_SHA256 = (
    "0eb34c0c82e66a6610e9e7d5ac7c8763e3c5c35762e986b267e1621055a87a82"
)
LOCKED_TEST_BATCH_IMPLEMENTATION_SHA256 = (
    "8fcb95eeac50260068244809db9fe1e34aa208571d81dae137976dd98f423e70"
)

AUTHORIZED_SOURCE_PATH = (
    "scripts/run_spot_spray_simulation_video_ab_extension_aware_batch_v1.py"
)
AUTHORIZED_TEST_PATH = (
    "tests/test_run_spot_spray_simulation_video_ab_extension_aware_batch_v1.py"
)

_ORIGINAL_VALIDATE_FULL_PLAN = execution.validate_full_plan


def adapter_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    paths = execution.full_paths(config)
    synthetic_root = (
        paths["synthetic"] / "planning/extension_aware_batch_adapter_v1"
    )
    docs_root = paths["docs"] / "extension_aware_batch_adapter_v1"
    synthetic_release = synthetic_root / "release_v1"
    docs_release = docs_root / "release_v1"
    return {
        "synthetic_root": synthetic_root,
        "docs_root": docs_root,
        "synthetic_release": synthetic_release,
        "docs_release": docs_release,
        "authorization": synthetic_release / "pass66_manager_authorization_receipt.json",
        "bridge": synthetic_release / "extension_aware_batch_adapter_bridge_v1.json",
        "lock": synthetic_release / "extension_aware_batch_adapter_lock_v1.json",
        "release": synthetic_release / "extension_aware_batch_adapter_release_v1.json",
        "validation_receipt": synthetic_release / "pass66_validation_receipt.json",
        "executions": synthetic_root / "executions",
        "docs_executions": docs_root / "executions",
    }


def _required_release_files() -> list[str]:
    return [
        "extension_aware_batch_adapter_bridge_v1.json",
        "extension_aware_batch_adapter_lock_v1.json",
        "extension_aware_batch_adapter_release_v1.json",
        "pass66_manager_authorization_receipt.json",
        "pass66_validation_receipt.json",
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


def _require_file_sha256(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or execution.sha256_file(path) != expected:
        raise execution.ContractError(f"{label} bytes changed")


def _source_paths() -> dict[str, Path]:
    return {
        "legacy_execution": PROJECT_ROOT
        / "scripts/run_spot_spray_simulation_video_ab_execution_v1.py",
        "legacy_test": PROJECT_ROOT
        / "tests/test_run_spot_spray_simulation_video_ab_execution_v1.py",
        "validator": PROJECT_ROOT
        / "scripts/validate_spot_spray_simulation_video_ab_extension_aware_v1.py",
        "validator_test": PROJECT_ROOT
        / "tests/test_validate_spot_spray_simulation_video_ab_extension_aware_v1.py",
        "adapter": PROJECT_ROOT / AUTHORIZED_SOURCE_PATH,
        "adapter_test": PROJECT_ROOT / AUTHORIZED_TEST_PATH,
    }


def _verify_unchanged_sources() -> dict[str, str]:
    paths = _source_paths()
    expected = {
        "legacy_execution": LEGACY_EXECUTION_SCRIPT_SHA256,
        "legacy_test": LEGACY_EXECUTION_TEST_SHA256,
        "validator": VALIDATOR_SCRIPT_SHA256,
        "validator_test": VALIDATOR_TEST_SHA256,
    }
    for key, digest in expected.items():
        _require_file_sha256(paths[key], digest, key.replace("_", " "))
    function_source_sha256 = execution.stable_sha256(
        inspect.getsource(execution.run_locked_test_render_batch)
    )
    if function_source_sha256 != LOCKED_TEST_BATCH_FUNCTION_SOURCE_SHA256:
        raise execution.ContractError("Locked-test batch function source changed")
    implementation_sha256 = execution.locked_test_render_batch_implementation_sha256()
    if implementation_sha256 != LOCKED_TEST_BATCH_IMPLEMENTATION_SHA256:
        raise execution.ContractError("Locked-test batch implementation changed")
    return {
        "legacy_execution_script_sha256": LEGACY_EXECUTION_SCRIPT_SHA256,
        "legacy_execution_test_sha256": LEGACY_EXECUTION_TEST_SHA256,
        "validator_script_sha256": VALIDATOR_SCRIPT_SHA256,
        "validator_test_sha256": VALIDATOR_TEST_SHA256,
        "locked_test_batch_function_source_sha256": function_source_sha256,
        "locked_test_batch_implementation_sha256": implementation_sha256,
    }


def _validated_extension_boundary(
    config_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config_path = config_path.expanduser().resolve()
    if config_path != DEFAULT_CONFIG.expanduser().resolve():
        raise execution.ContractError("Noncanonical adapter runtime config")
    _require_file_sha256(config_path, RUNTIME_CONFIG_SHA256, "runtime config")
    sources = _verify_unchanged_sources()
    config = execution.load_config(config_path)
    runtime_paths = execution.runtime_compatibility_paths(
        execution.load_config(execution.DEFAULT_CONFIG)
    )
    _require_file_sha256(
        runtime_paths["release"],
        RUNTIME_RELEASE_FILE_SHA256,
        "runtime release",
    )
    validator_paths = validator.validation_paths(config)
    _require_file_sha256(
        validator_paths["release"],
        VALIDATOR_RELEASE_FILE_SHA256,
        "extension-aware validator release",
    )
    pass65_receipt = (
        execution.full_paths(config)["docs"]
        / "locked_test_render_batches/pass65_runtime_patch_execution/"
        "pass65_fail_closed_receipt.json"
    )
    _require_file_sha256(pass65_receipt, PASS65_RECEIPT_SHA256, "Pass65 receipt")

    validation = validator.validate_extension_aware_full_plan(config_path)
    if (
        validation.get("status")
        != "PASS_EXTENSION_AWARE_FULL_PLAN_VALIDATION_SYNTHETIC_ONLY"
        or validation.get("validator_release_identity_sha256")
        != VALIDATOR_RELEASE_IDENTITY_SHA256
        or validation.get("runtime_compatibility_release_identity_sha256")
        != RUNTIME_RELEASE_IDENTITY_SHA256
        or validation.get("completed_pair_count") != 41
        or validation.get("pending_pair_count") != 55
        or validation.get("rendering_calls") != 0
        or validation.get("model_loaded") is not False
        or validation.get("inference_calls") != 0
        or validation.get("outcome_inputs") != []
        or validation.get("field_product_or_chemical_go") is not False
    ):
        raise execution.ContractError("Extension-aware validation boundary changed")

    paths = execution.full_paths(config)
    planning = paths["synthetic"] / "planning"
    state_path = planning / "render_state_v1.json"
    docs_state_path = paths["docs"] / "render_state_v1.json"
    ledger_path = planning / "candidate_rejection_ledger_v1.jsonl"
    _require_file_sha256(state_path, CURRENT_STATE_SHA256, "live render state")
    _require_file_sha256(docs_state_path, CURRENT_STATE_SHA256, "docs render state")
    _require_file_sha256(ledger_path, LEDGER_SHA256, "candidate rejection ledger")
    ledger = execution.read_jsonl(ledger_path)
    if len(ledger) != 111:
        raise execution.ContractError("Candidate rejection ledger length changed")

    historical, combined = validator._rosters(config)
    extension_manifest = execution.roster_extension_paths(config)["manifest"]
    _require_file_sha256(
        extension_manifest, EXTENSION_MANIFEST_SHA256, "extension manifest"
    )
    if (
        execution.stable_sha256(combined) != COMBINED_ROSTER_IDENTITY_SHA256
        or len(historical) != 96
        or len(combined) != 96
        or sum(len(row["candidates"]) for row in combined) != 3072
    ):
        raise execution.ContractError("Combined roster identity changed")

    state = execution.load_json(state_path)
    if (
        state.get("completed_pair_count") != 41
        or state.get("pending_pair_count") != 55
        or state.get("pending_pair_ids", [None])[0] != "locked_test_c001_r01"
        or state.get("interrupted_staging_directories") != []
        or state.get("model_outputs_present") is not False
    ):
        raise execution.ContractError("Adapter live state semantics changed")

    boundary = {
        **sources,
        "runtime_config_sha256": RUNTIME_CONFIG_SHA256,
        "runtime_release_file_sha256": RUNTIME_RELEASE_FILE_SHA256,
        "runtime_release_identity_sha256": RUNTIME_RELEASE_IDENTITY_SHA256,
        "validator_release_file_sha256": VALIDATOR_RELEASE_FILE_SHA256,
        "validator_release_identity_sha256": VALIDATOR_RELEASE_IDENTITY_SHA256,
        "pass65_fail_closed_receipt_sha256": PASS65_RECEIPT_SHA256,
        "historical_roster_sha256": HISTORICAL_ROSTER_SHA256,
        "extension_manifest_sha256": EXTENSION_MANIFEST_SHA256,
        "combined_roster_identity_sha256": COMBINED_ROSTER_IDENTITY_SHA256,
        "render_state_sha256": CURRENT_STATE_SHA256,
        "completed_pair_count": 41,
        "pending_pair_count": 55,
        "first_pending_pair_id": "locked_test_c001_r01",
        "candidate_rejection_ledger_sha256": LEDGER_SHA256,
        "candidate_rejection_ledger_row_count": 111,
        "partial_staging_directories": [],
        "model_outputs_present": False,
    }
    return config, validation, boundary


def _historical_plan_binding(
    config: Mapping[str, Any], validation: Mapping[str, Any]
) -> dict[str, Any]:
    paths = execution.full_paths(config)
    root = paths["synthetic"]
    planning = root / "planning"
    receipt_path = planning / "full_plan_receipt_v1.json"
    receipt = execution.load_json(receipt_path)
    if (
        receipt.get("contract") != execution.FULL_PLAN_CONTRACT
        or receipt.get("status") != "PASS_FULL_PLAN_DRY_RUN_SYNTHETIC_ONLY"
        or receipt.get("protocol_sha256")
        != config["source_locks"]["protocol"]["sha256"]
        or receipt.get("execution_config_sha256")
        != execution.HISTORICAL_V1_BINDINGS["execution_config_sha256"]
        or receipt.get("pair_roster_sha256") != HISTORICAL_ROSTER_SHA256
    ):
        raise execution.ContractError("Immutable historical plan binding changed")
    roster_path = planning / "pair_roster_v1.jsonl"
    _require_file_sha256(roster_path, HISTORICAL_ROSTER_SHA256, "historical roster")
    roster = execution.read_jsonl(roster_path)
    roster_validation = execution.validate_full_roster(
        roster, execution._protocol(config)
    )
    if roster_validation != receipt.get("pair_roster_validation"):
        raise execution.ContractError("Historical roster validation changed")
    for key, name in (
        ("template_inventory_sha256", "template_inventory_v1.json"),
        ("asset_partition_sha256", "asset_partition_v1.json"),
        ("candidate_gate_contract_sha256", "candidate_gate_contract_v1.json"),
        ("atomic_render_state_contract_sha256", "atomic_render_state_contract_v1.json"),
        ("full_capacity_receipt_sha256", "full_capacity_receipt_v1.json"),
    ):
        if execution.sha256_file(planning / name) != receipt.get(key):
            raise execution.ContractError(f"Historical plan artifact changed: {name}")
    capacity = execution.load_json(planning / "full_capacity_receipt_v1.json")
    if capacity.get("passed") is not True:
        raise execution.ContractError("Historical capacity receipt is not passing")
    combined_rows = execution.full_roster_rows(config)
    state = execution.inspect_full_render_state(root, combined_rows)
    if (
        state.get("completed_pair_count") != validation.get("completed_pair_count")
        or state.get("pending_pair_count") != validation.get("pending_pair_count")
        or state.get("model_outputs_present") is not False
    ):
        raise execution.ContractError("Extension-aware plan state changed")
    return {
        "status": receipt["status"],
        "full_root": str(root),
        "docs_root": str(paths["docs"]),
        "pair_roster_sha256": HISTORICAL_ROSTER_SHA256,
        "split_pair_counts": roster_validation["split_pair_counts"],
        "candidate_count": roster_validation["candidate_count"],
        "unique_seed_count": roster_validation["unique_seed_count"],
        "asset_partition_sha256": receipt["asset_partition_sha256"],
        "capacity": capacity["projection"],
        "render_state": state,
        "combined_candidate_count": 3072,
        "validator_release_identity_sha256": VALIDATOR_RELEASE_IDENTITY_SHA256,
        "model_loaded": False,
        "inference_calls": 0,
        "synthetic_only": True,
    }


def extension_aware_validate_full_plan(config_path: Path) -> dict[str, Any]:
    """Named one-process replacement for the legacy validation entrypoint."""
    config, validation, _ = _validated_extension_boundary(config_path)
    return _historical_plan_binding(config, validation)


def _callable_snapshot() -> dict[str, Callable[..., Any]]:
    return {
        name: value
        for name, value in vars(execution).items()
        if callable(value)
    }


def _assert_only_validator_changed(
    before: Mapping[str, Callable[..., Any]],
    expected_validator: Callable[..., Any],
) -> None:
    after = _callable_snapshot()
    if set(after) != set(before):
        raise execution.ContractError("Execution callable set changed")
    for name, original in before.items():
        expected = expected_validator if name == "validate_full_plan" else original
        if after[name] is not expected:
            raise execution.ContractError(
                f"Unauthorized execution callable change: {name}"
            )


def _call_unchanged_batch(
    config_path: Path,
    pair_ids: Sequence[str],
    *,
    max_new_pairs: int,
) -> dict[str, Any]:
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator is not installed before adapter")
    before = _callable_snapshot()
    try:
        execution.validate_full_plan = extension_aware_validate_full_plan
        _assert_only_validator_changed(before, extension_aware_validate_full_plan)
        return execution.run_locked_test_render_batch(
            config_path, pair_ids, max_new_pairs=max_new_pairs
        )
    finally:
        execution.validate_full_plan = _ORIGINAL_VALIDATE_FULL_PLAN
        _assert_only_validator_changed(before, _ORIGINAL_VALIDATE_FULL_PLAN)


def adapter_implementation_sha256() -> str:
    functions = (
        _validated_extension_boundary,
        _historical_plan_binding,
        extension_aware_validate_full_plan,
        _callable_snapshot,
        _assert_only_validator_changed,
        _call_unchanged_batch,
        _validate_static_release_identity,
        _normalize_request,
        _publish_or_resume_intent,
        _validate_terminal_receipt,
        run_extension_aware_batch,
    )
    return execution.stable_sha256(
        {
            "contract": CONTRACT,
            "functions": {
                function.__name__: inspect.getsource(function)
                for function in functions
            },
            "legacy_batch_implementation_sha256": (
                LOCKED_TEST_BATCH_IMPLEMENTATION_SHA256
            ),
            "validator_release_identity_sha256": (
                VALIDATOR_RELEASE_IDENTITY_SHA256
            ),
        }
    )


def _authorization_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": AUTHORIZATION_CONTRACT,
        "status": "PASS_MANAGER_AUTHORIZED_ADAPTER_SCOPE_SYNTHETIC_ONLY",
        "authorization": {
            "manager_handoff_event_id": MANAGER_HANDOFF_EVENT_ID,
            "pass66_event_id": PASS66_EVENT_ID,
            "goal_multi_repeat_run_id": RUN_ID,
            "pass": 66,
            "strategy": "base",
            "owner_session_id": OWNER_SESSION_ID,
            "portfolio_id": PORTFOLIO_ID,
            "portfolio_lane": PORTFOLIO_LANE,
            "portfolio_revision": PORTFOLIO_REVISION,
        },
        "authorized_top_level_source_paths": [
            AUTHORIZED_SOURCE_PATH,
            AUTHORIZED_TEST_PATH,
        ],
        "authorized_release_mirrors": [
            "synthetic/planning/extension_aware_batch_adapter_v1/release_v1",
            (
                "docs/results/spot_spray_simulation_video_ab_execution_v1/"
                "full_benchmark_v1/extension_aware_batch_adapter_v1/release_v1"
            ),
        ],
        "authorized_mechanism": {
            "temporary_execution_global": "validate_full_plan",
            "replacement_callable": "extension_aware_validate_full_plan",
            "try_finally_restore_required": True,
            "unchanged_batch_function_called": True,
            "other_execution_global_or_function_mutation_allowed": False,
        },
        "forbidden_scope": {
            "legacy_runtime_or_validator_byte_mutation": True,
            "real_batch_intent_during_pass66": True,
            "candidate_gt_access_during_pass66": True,
            "rendering_during_pass66": True,
            "model_prediction_outcome_or_target_access": True,
            "external_service_mutation": True,
        },
        "claim_boundary": _claim_boundary(config),
    }


def _bridge_payload(
    config: Mapping[str, Any], boundary: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": BRIDGE_CONTRACT,
        "status": "SEALED_EXTENSION_AWARE_BATCH_BRIDGE_SYNTHETIC_ONLY",
        "pinned_boundary": copy.deepcopy(dict(boundary)),
        "compatibility_mechanism": {
            "validate_release_before_adapter_intent": True,
            "validate_release_before_candidate_gt_access": True,
            "patch_target": "execution.validate_full_plan",
            "patch_scope": "single_process_try_finally",
            "replacement_reruns_sealed_extension_validator": True,
            "replacement_returns_immutable_historical_plan_binding": True,
            "unchanged_batch_function": "run_locked_test_render_batch",
            "original_callable_restored_on_success_and_exception": True,
            "all_other_execution_callables_identity_preserved": True,
        },
        "execution_contract": {
            "intent_contract": INTENT_CONTRACT,
            "terminal_receipt_contract": TERMINAL_RECEIPT_CONTRACT,
            "byte_identical_request_required_for_resume": True,
            "partial_or_unbound_execution_root_fails_closed": True,
            "canonical_earliest_pending_pair_required": True,
            "lowest_unattempted_candidate_wins": True,
            "frozen_gates_and_roster": True,
            "max_new_pairs_required": True,
            "underlying_batch_intent_and_receipt_bound": True,
        },
        "access_guard": {
            "validation_only_during_pass66": True,
            "real_adapter_intents_created": 0,
            "candidate_gt_accessed": False,
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
        "status": "SEALED_EXTENSION_AWARE_BATCH_ADAPTER_LOCK_SYNTHETIC_ONLY",
        "bridge_sha256": execution.require_sha256(
            bridge_sha256, "adapter bridge"
        ),
        "adapter_implementation_sha256": adapter_implementation_sha256(),
        "legacy_execution_script_sha256": LEGACY_EXECUTION_SCRIPT_SHA256,
        "legacy_execution_test_sha256": LEGACY_EXECUTION_TEST_SHA256,
        "locked_test_batch_function_source_sha256": (
            LOCKED_TEST_BATCH_FUNCTION_SOURCE_SHA256
        ),
        "locked_test_batch_implementation_sha256": (
            LOCKED_TEST_BATCH_IMPLEMENTATION_SHA256
        ),
        "runtime_release_identity_sha256": RUNTIME_RELEASE_IDENTITY_SHA256,
        "validator_release_identity_sha256": VALIDATOR_RELEASE_IDENTITY_SHA256,
        "patch_target": "execution.validate_full_plan",
        "other_execution_global_or_function_changes_allowed": False,
        "model_prediction_outcome_or_target_access_allowed": False,
        "claim_boundary": _claim_boundary(config),
    }


def _release_payload(
    config: Mapping[str, Any], *, authorization_sha256: str, bridge_sha256: str, lock_sha256: str
) -> dict[str, Any]:
    sources = _source_paths()
    payload = {
        "schema_version": 1,
        "contract": RELEASE_CONTRACT,
        "status": "SEALED_EXTENSION_AWARE_BATCH_ADAPTER_RELEASE_SYNTHETIC_ONLY",
        "authorization_receipt_sha256": authorization_sha256,
        "bridge_sha256": bridge_sha256,
        "adapter_lock_sha256": lock_sha256,
        "adapter_script_sha256": execution.sha256_file(sources["adapter"]),
        "adapter_test_sha256": execution.sha256_file(sources["adapter_test"]),
        "adapter_implementation_sha256": adapter_implementation_sha256(),
        "legacy_execution_script_sha256": LEGACY_EXECUTION_SCRIPT_SHA256,
        "legacy_execution_test_sha256": LEGACY_EXECUTION_TEST_SHA256,
        "validator_script_sha256": VALIDATOR_SCRIPT_SHA256,
        "validator_test_sha256": VALIDATOR_TEST_SHA256,
        "runtime_config_sha256": RUNTIME_CONFIG_SHA256,
        "runtime_release_file_sha256": RUNTIME_RELEASE_FILE_SHA256,
        "runtime_release_identity_sha256": RUNTIME_RELEASE_IDENTITY_SHA256,
        "validator_release_file_sha256": VALIDATOR_RELEASE_FILE_SHA256,
        "validator_release_identity_sha256": VALIDATOR_RELEASE_IDENTITY_SHA256,
        "pass65_fail_closed_receipt_sha256": PASS65_RECEIPT_SHA256,
        "historical_or_parent_bytes_rewritten_or_rebound": False,
        "legacy_wrapper_semantics_changed": False,
        "pass66_validation_only": True,
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
                if path.is_file() and path.name != "pass66_validation_receipt.json"
            ),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    ]


def _validation_receipt_payload(
    config: Mapping[str, Any],
    root: Path,
    release: Mapping[str, Any],
    boundary: Mapping[str, Any],
) -> dict[str, Any]:
    rows = _artifact_rows(root)
    return {
        "schema_version": 1,
        "contract": VALIDATION_RECEIPT_CONTRACT,
        "status": "PASS_EXTENSION_AWARE_BATCH_ADAPTER_VALIDATION_SYNTHETIC_ONLY",
        "goal_multi_repeat_run_id": RUN_ID,
        "event_id": PASS66_EVENT_ID,
        "pass": 66,
        "adapter_release_identity_sha256": release[
            "release_identity_sha256"
        ],
        "artifact_inventory": {
            "files": rows,
            "file_count": len(rows),
            "inventory_sha256": execution.stable_sha256(rows),
        },
        "validated_boundary": copy.deepcopy(dict(boundary)),
        "pass66_execution": {
            "adapter_intent_count": 0,
            "adapter_terminal_receipt_count": 0,
            "candidate_gt_accessed": False,
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


def _validate_release_file_set(paths: Mapping[str, Path]) -> None:
    required = _required_release_files()
    for key in ("synthetic_release", "docs_release"):
        root = paths[key]
        observed = (
            sorted(
                path.relative_to(root).as_posix()
                for path in root.rglob("*")
                if path.is_file()
            )
            if root.is_dir()
            else []
        )
        if observed != required:
            raise execution.ContractError("Adapter release file set changed")
    for relative in required:
        if execution.sha256_file(
            paths["synthetic_release"] / relative
        ) != execution.sha256_file(paths["docs_release"] / relative):
            raise execution.ContractError("Adapter docs release mirror changed")


def seal_adapter_release(config_path: Path) -> dict[str, Any]:
    config, _, boundary = _validated_extension_boundary(config_path)
    paths = adapter_paths(config)
    synthetic_parent = paths["synthetic_release"].parent
    docs_parent = paths["docs_release"].parent
    partials = list(synthetic_parent.glob(".partial-*")) + list(
        docs_parent.glob(".partial-*")
    )
    if partials:
        raise execution.ContractError("Partial adapter release exists")
    if paths["executions"].exists() or paths["docs_executions"].exists():
        raise execution.ContractError("Pass66 adapter execution artifact exists")
    if paths["synthetic_release"].exists() or paths["docs_release"].exists():
        if not paths["synthetic_release"].is_dir() or not paths[
            "docs_release"
        ].is_dir():
            raise execution.ContractError("Partial adapter release exists")
        return validate_adapter_release(config_path)

    authorization = _authorization_payload(config)
    bridge = _bridge_payload(config, boundary)
    staging = synthetic_parent / f".partial-adapter-release-v1-{uuid.uuid4().hex}"
    docs_staging = docs_parent / f".partial-adapter-release-v1-{uuid.uuid4().hex}"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        execution.write_json(
            staging / "pass66_manager_authorization_receipt.json", authorization
        )
        execution.write_json(
            staging / "extension_aware_batch_adapter_bridge_v1.json", bridge
        )
        lock = _lock_payload(
            config,
            bridge_sha256=execution.sha256_file(
                staging / "extension_aware_batch_adapter_bridge_v1.json"
            ),
        )
        execution.write_json(
            staging / "extension_aware_batch_adapter_lock_v1.json", lock
        )
        release = _release_payload(
            config,
            authorization_sha256=execution.sha256_file(
                staging / "pass66_manager_authorization_receipt.json"
            ),
            bridge_sha256=execution.sha256_file(
                staging / "extension_aware_batch_adapter_bridge_v1.json"
            ),
            lock_sha256=execution.sha256_file(
                staging / "extension_aware_batch_adapter_lock_v1.json"
            ),
        )
        execution.write_json(
            staging / "extension_aware_batch_adapter_release_v1.json", release
        )
        staging.replace(paths["synthetic_release"])
        receipt = _validation_receipt_payload(
            config, paths["synthetic_release"], release, boundary
        )
        execution.write_json(paths["validation_receipt"], receipt)

        docs_staging.mkdir(parents=True, exist_ok=False)
        for relative in _required_release_files():
            shutil.copy2(
                paths["synthetic_release"] / relative,
                docs_staging / relative,
            )
        docs_staging.replace(paths["docs_release"])
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        if docs_staging.exists():
            shutil.rmtree(docs_staging)
        raise
    return validate_adapter_release(config_path)


def validate_adapter_release(config_path: Path) -> dict[str, Any]:
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator was not restored")
    config, validation, boundary = _validated_extension_boundary(config_path)
    paths = adapter_paths(config)
    partials = list(paths["synthetic_release"].parent.glob(".partial-*")) + list(
        paths["docs_release"].parent.glob(".partial-*")
    )
    if partials:
        raise execution.ContractError("Partial adapter release exists")
    _validate_release_file_set(paths)
    authorization = execution.load_json(paths["authorization"])
    if authorization != _authorization_payload(config):
        raise execution.ContractError("Adapter manager authorization changed")
    bridge = execution.load_json(paths["bridge"])
    if bridge != _bridge_payload(config, boundary):
        raise execution.ContractError("Adapter bridge changed")
    lock = execution.load_json(paths["lock"])
    if lock != _lock_payload(
        config, bridge_sha256=execution.sha256_file(paths["bridge"])
    ):
        raise execution.ContractError("Adapter lock changed")
    release = execution.load_json(paths["release"])
    expected_release = _release_payload(
        config,
        authorization_sha256=execution.sha256_file(paths["authorization"]),
        bridge_sha256=execution.sha256_file(paths["bridge"]),
        lock_sha256=execution.sha256_file(paths["lock"]),
    )
    if release != expected_release:
        raise execution.ContractError("Adapter release changed")
    identity_payload = copy.deepcopy(release)
    identity = identity_payload.pop("release_identity_sha256", None)
    if identity != execution.stable_sha256(identity_payload):
        raise execution.ContractError("Adapter release identity changed")
    receipt = execution.load_json(paths["validation_receipt"])
    expected_receipt = _validation_receipt_payload(
        config, paths["synthetic_release"], release, boundary
    )
    if receipt != expected_receipt:
        raise execution.ContractError("Pass66 adapter validation receipt changed")
    return {
        "status": receipt["status"],
        "adapter_release_identity_sha256": identity,
        "runtime_release_identity_sha256": RUNTIME_RELEASE_IDENTITY_SHA256,
        "validator_release_identity_sha256": VALIDATOR_RELEASE_IDENTITY_SHA256,
        "completed_pair_count": validation["completed_pair_count"],
        "pending_pair_count": validation["pending_pair_count"],
        "first_pending_pair_id": boundary["first_pending_pair_id"],
        "candidate_rejection_ledger_row_count": 111,
        "real_adapter_intents_created": 0,
        "candidate_gt_accessed": False,
        "rendering_calls": 0,
        "model_loaded": False,
        "inference_calls": 0,
        "prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "registered_targets_used": False,
        "external_services_modified": False,
        "outcome_inputs": [],
        "synthetic_only": True,
        "field_product_or_chemical_go": False,
    }


def _validate_static_release_identity(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate immutable adapter bytes without requiring the 41/96 state."""
    _verify_unchanged_sources()
    paths = adapter_paths(config)
    _validate_release_file_set(paths)
    _require_file_sha256(
        validator.validation_paths(config)["release"],
        VALIDATOR_RELEASE_FILE_SHA256,
        "extension-aware validator release",
    )
    release = execution.load_json(paths["release"])
    identity_payload = copy.deepcopy(release)
    identity = identity_payload.pop("release_identity_sha256", None)
    if identity != execution.stable_sha256(identity_payload):
        raise execution.ContractError("Adapter release identity changed")
    valid = (
        release.get("status")
        == "SEALED_EXTENSION_AWARE_BATCH_ADAPTER_RELEASE_SYNTHETIC_ONLY"
        and release.get("legacy_execution_script_sha256")
        == LEGACY_EXECUTION_SCRIPT_SHA256
        and release.get("legacy_execution_test_sha256")
        == LEGACY_EXECUTION_TEST_SHA256
        and release.get("validator_script_sha256") == VALIDATOR_SCRIPT_SHA256
        and release.get("validator_test_sha256") == VALIDATOR_TEST_SHA256
        and release.get("runtime_config_sha256") == RUNTIME_CONFIG_SHA256
        and release.get("runtime_release_file_sha256")
        == RUNTIME_RELEASE_FILE_SHA256
        and release.get("runtime_release_identity_sha256")
        == RUNTIME_RELEASE_IDENTITY_SHA256
        and release.get("validator_release_file_sha256")
        == VALIDATOR_RELEASE_FILE_SHA256
        and release.get("validator_release_identity_sha256")
        == VALIDATOR_RELEASE_IDENTITY_SHA256
        and release.get("authorization_receipt_sha256")
        == execution.sha256_file(paths["authorization"])
        and release.get("bridge_sha256") == execution.sha256_file(paths["bridge"])
        and release.get("adapter_lock_sha256")
        == execution.sha256_file(paths["lock"])
        and release.get("historical_or_parent_bytes_rewritten_or_rebound")
        is False
        and release.get("legacy_wrapper_semantics_changed") is False
    )
    if not valid:
        raise execution.ContractError("Static adapter release binding changed")
    return release


def _normalize_request(
    config: Mapping[str, Any],
    release_identity: str,
    pair_ids: Sequence[str],
    max_new_pairs: int,
    *,
    require_earliest_pending: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if (
        not isinstance(max_new_pairs, int)
        or isinstance(max_new_pairs, bool)
        or max_new_pairs <= 0
    ):
        raise execution.ContractError("Adapter max-new-pairs must be positive")
    normalized = [str(value) for value in pair_ids]
    if not normalized or len(normalized) != len(set(normalized)):
        raise execution.ContractError("Adapter pair IDs are empty or duplicate")
    rows = execution.full_roster_rows(config)
    targets = execution._validate_locked_test_render_batch_targets(
        rows, normalized, max_new_pairs
    )
    if require_earliest_pending:
        state = execution.inspect_full_render_state(
            execution.full_paths(config)["synthetic"], rows
        )
        pending_locked_test = [
            str(row["pair_id"])
            for row in rows
            if row["protocol_split"] == "locked_test"
            and row["pair_id"] in state["pending_pair_ids"]
        ]
        if normalized != pending_locked_test[: len(normalized)]:
            raise execution.ContractError(
                "Adapter batch must start at the earliest pending locked-test slot"
            )
    request = {
        "schema_version": 1,
        "contract": CONTRACT,
        "adapter_release_identity_sha256": execution.require_sha256(
            release_identity, "adapter release identity"
        ),
        "runtime_config_sha256": RUNTIME_CONFIG_SHA256,
        "runtime_release_identity_sha256": RUNTIME_RELEASE_IDENTITY_SHA256,
        "validator_release_identity_sha256": VALIDATOR_RELEASE_IDENTITY_SHA256,
        "legacy_batch_implementation_sha256": (
            LOCKED_TEST_BATCH_IMPLEMENTATION_SHA256
        ),
        "target_pair_ids": normalized,
        "max_new_pairs": max_new_pairs,
        "protocol_split": "locked_test",
        "canonical_earliest_pending_required": True,
        "lowest_unattempted_candidate_wins": True,
        "model_access_allowed": False,
        "prediction_access_allowed": False,
        "locked_test_outcome_access_allowed": False,
        "registered_target_access_allowed": False,
        "external_service_mutation_allowed": False,
    }
    return request, targets


def _execution_identity(request: Mapping[str, Any]) -> tuple[str, str]:
    identity = execution.stable_sha256(request)
    first = str(request["target_pair_ids"][0])
    return f"extension_aware_batch_{first}_{identity[:16]}", identity


def _publish_or_resume_intent(
    parent: Path,
    execution_id: str,
    intent: Mapping[str, Any],
) -> tuple[Path, bool]:
    root = parent / execution_id
    if execution.SAFE_ID_RE.fullmatch(execution_id) is None:
        raise execution.ContractError("Unsafe adapter execution identity")
    partials = list(parent.glob(".partial-*")) if parent.exists() else []
    if partials:
        raise execution.ContractError("Partial adapter intent exists")
    intent_path = root / "adapter_intent.json"
    if root.exists():
        if not intent_path.is_file():
            raise execution.ContractError("Adapter execution root has no valid intent")
        if execution.load_json(intent_path) != dict(intent):
            raise execution.ContractError("Existing adapter request changed")
        return root, True
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".partial-{execution_id}-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        execution.write_json(staging / "adapter_intent.json", intent)
        staging.replace(root)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return root, False


def _terminal_payload(
    config: Mapping[str, Any],
    request: Mapping[str, Any],
    request_identity: str,
    execution_id: str,
    intent_path: Path,
    underlying: Mapping[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, Any]:
    full = execution.full_paths(config)
    batch_id = str(underlying["batch_id"])
    batch_root = (
        full["synthetic"]
        / "planning/locked_test_render_batches_v1"
        / batch_id
    )
    batch_intent = batch_root / "batch_intent.json"
    batch_receipt = batch_root / "batch_receipt.json"
    if not batch_intent.is_file() or not batch_receipt.is_file():
        raise execution.ContractError("Underlying batch intent or receipt is missing")
    return {
        "schema_version": 1,
        "contract": TERMINAL_RECEIPT_CONTRACT,
        "status": "PASS_EXTENSION_AWARE_BATCH_ADAPTER_SYNTHETIC_ONLY",
        "execution_id": execution_id,
        "request_identity_sha256": request_identity,
        "request": copy.deepcopy(dict(request)),
        "adapter_intent_sha256": execution.sha256_file(intent_path),
        "adapter_release_identity_sha256": request[
            "adapter_release_identity_sha256"
        ],
        "original_validator_restored": (
            execution.validate_full_plan is _ORIGINAL_VALIDATE_FULL_PLAN
        ),
        "underlying_batch": {
            "batch_id": batch_id,
            "batch_intent_sha256": execution.sha256_file(batch_intent),
            "batch_receipt_sha256": execution.sha256_file(batch_receipt),
            "status": underlying["status"],
            "new_pair_ids": list(underlying["new_pair_ids"]),
        },
        "boundary": {
            "render_state_sha256_before": before["render_state_sha256"],
            "render_state_sha256_after": after["render_state_sha256"],
            "candidate_rejection_ledger_sha256_before": before[
                "candidate_rejection_ledger_sha256"
            ],
            "candidate_rejection_ledger_sha256_after": after[
                "candidate_rejection_ledger_sha256"
            ],
        },
        "access_guard": {
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


def _validate_terminal_receipt(
    config: Mapping[str, Any],
    receipt: Mapping[str, Any],
    request: Mapping[str, Any],
    request_identity: str,
    execution_id: str,
    intent_path: Path,
) -> None:
    batch = receipt.get("underlying_batch")
    boundary = receipt.get("boundary")
    access = receipt.get("access_guard")
    valid = (
        receipt.get("schema_version") == 1
        and receipt.get("contract") == TERMINAL_RECEIPT_CONTRACT
        and receipt.get("status")
        == "PASS_EXTENSION_AWARE_BATCH_ADAPTER_SYNTHETIC_ONLY"
        and receipt.get("execution_id") == execution_id
        and receipt.get("request_identity_sha256") == request_identity
        and receipt.get("request") == dict(request)
        and receipt.get("adapter_intent_sha256")
        == execution.sha256_file(intent_path)
        and receipt.get("adapter_release_identity_sha256")
        == request["adapter_release_identity_sha256"]
        and receipt.get("original_validator_restored") is True
        and isinstance(batch, dict)
        and isinstance(boundary, dict)
        and isinstance(access, dict)
        and access.get("model_loaded") is False
        and access.get("inference_calls") == 0
        and access.get("prediction_accessed") is False
        and access.get("locked_test_outcome_accessed") is False
        and access.get("registered_targets_used") is False
        and access.get("external_services_modified") is False
        and access.get("outcome_inputs") == []
        and receipt.get("claim_boundary") == _claim_boundary(config)
    )
    if not valid:
        raise execution.ContractError("Adapter terminal receipt changed")
    batch_root = (
        execution.full_paths(config)["synthetic"]
        / "planning/locked_test_render_batches_v1"
        / str(batch["batch_id"])
    )
    _require_file_sha256(
        batch_root / "batch_intent.json",
        str(batch["batch_intent_sha256"]),
        "underlying batch intent",
    )
    _require_file_sha256(
        batch_root / "batch_receipt.json",
        str(batch["batch_receipt_sha256"]),
        "underlying batch receipt",
    )


def _live_execution_boundary(config: Mapping[str, Any]) -> dict[str, Any]:
    planning = execution.full_paths(config)["synthetic"] / "planning"
    state_path = planning / "render_state_v1.json"
    ledger_path = planning / "candidate_rejection_ledger_v1.jsonl"
    return {
        "render_state_sha256": execution.sha256_file(state_path),
        "candidate_rejection_ledger_sha256": execution.sha256_file(ledger_path),
    }


def run_extension_aware_batch(
    config_path: Path,
    pair_ids: Sequence[str],
    *,
    max_new_pairs: int = 1,
) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config = execution.load_config(config_path)
    paths = adapter_paths(config)
    if not paths["release"].is_file():
        raise execution.ContractError("Adapter release is missing")
    release = _validate_static_release_identity(config)
    release_identity = execution.require_sha256(
        release.get("release_identity_sha256"), "adapter release identity"
    )
    request, _ = _normalize_request(
        config,
        release_identity,
        pair_ids,
        max_new_pairs,
        require_earliest_pending=False,
    )
    execution_id, request_identity = _execution_identity(request)
    execution_root = paths["executions"] / execution_id
    intent_path = execution_root / "adapter_intent.json"
    terminal_path = execution_root / "adapter_terminal_receipt.json"
    docs_terminal = paths["docs_executions"] / f"{execution_id}.json"

    if terminal_path.is_file():
        intent = execution.load_json(intent_path)
        if intent.get("request") != request:
            raise execution.ContractError("Existing adapter request changed")
        receipt = execution.load_json(terminal_path)
        _validate_terminal_receipt(
            config, receipt, request, request_identity, execution_id, intent_path
        )
        current = _live_execution_boundary(config)
        if current["render_state_sha256"] != receipt["boundary"][
            "render_state_sha256_after"
        ] or current["candidate_rejection_ledger_sha256"] != receipt[
            "boundary"
        ]["candidate_rejection_ledger_sha256_after"]:
            raise execution.ContractError("Adapter terminal live boundary changed")
        execution._write_json_once_atomically(docs_terminal, receipt)
        return {
            "status": "SKIP_EXISTING_PASS_EXTENSION_AWARE_BATCH_ADAPTER_SYNTHETIC_ONLY",
            "execution_id": execution_id,
            "adapter_terminal_receipt_sha256": execution.sha256_file(
                terminal_path
            ),
            "new_pair_ids": receipt["underlying_batch"]["new_pair_ids"],
            "model_loaded": False,
            "inference_calls": 0,
            "synthetic_only": True,
        }

    release_validation = validate_adapter_release(config_path)
    if release_validation["adapter_release_identity_sha256"] != release_identity:
        raise execution.ContractError("Adapter execution release identity changed")
    canonical_request, _ = _normalize_request(
        config,
        release_identity,
        pair_ids,
        max_new_pairs,
        require_earliest_pending=True,
    )
    if canonical_request != request:
        raise execution.ContractError("Adapter request changed during live validation")
    before = _live_execution_boundary(config)
    intent = {
        "schema_version": 1,
        "contract": INTENT_CONTRACT,
        "status": "EXTENSION_AWARE_BATCH_ADAPTER_INTENT_SYNTHETIC_ONLY",
        "execution_id": execution_id,
        "request_identity_sha256": request_identity,
        "request": request,
        "validated_release": release_validation,
        "boundary_at_start": before,
        "model_loaded": False,
        "inference_calls": 0,
        "prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "registered_targets_used": False,
        "external_services_modified": False,
        "outcome_inputs": [],
        "claim_boundary": _claim_boundary(config),
    }
    execution_root, resumed = _publish_or_resume_intent(
        paths["executions"], execution_id, intent
    )
    intent_path = execution_root / "adapter_intent.json"
    if execution.load_json(intent_path) != intent:
        raise execution.ContractError("Adapter intent changed after publication")

    underlying = _call_unchanged_batch(
        config_path, pair_ids, max_new_pairs=max_new_pairs
    )
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator was not restored after batch")
    after = _live_execution_boundary(config)
    receipt = _terminal_payload(
        config,
        request,
        request_identity,
        execution_id,
        intent_path,
        underlying,
        before,
        after,
    )
    receipt["resume"] = {"resumed_from_existing_adapter_intent": resumed}
    _validate_terminal_receipt(
        config, receipt, request, request_identity, execution_id, intent_path
    )
    execution._write_json_once_atomically(terminal_path, receipt)
    execution._write_json_once_atomically(docs_terminal, receipt)
    return {
        "status": receipt["status"],
        "execution_id": execution_id,
        "adapter_terminal_receipt_sha256": execution.sha256_file(terminal_path),
        "underlying_batch_id": receipt["underlying_batch"]["batch_id"],
        "new_pair_ids": receipt["underlying_batch"]["new_pair_ids"],
        "model_loaded": False,
        "inference_calls": 0,
        "synthetic_only": True,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("seal")
    subparsers.add_parser("validate")
    run = subparsers.add_parser("run")
    run.add_argument("--pair-id", action="append", required=True)
    run.add_argument("--max-new-pairs", type=int, default=1)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        if arguments.command == "seal":
            result = seal_adapter_release(arguments.config)
        elif arguments.command == "validate":
            result = validate_adapter_release(arguments.config)
        elif arguments.command == "run":
            result = run_extension_aware_batch(
                arguments.config,
                arguments.pair_id,
                max_new_pairs=arguments.max_new_pairs,
            )
        else:
            raise AssertionError(arguments.command)
    except execution.ContractError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
