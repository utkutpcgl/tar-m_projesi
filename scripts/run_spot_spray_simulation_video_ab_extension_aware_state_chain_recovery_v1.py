#!/usr/bin/env python3
"""Seal and run the exact state-chain-aware zero-source-weed recovery bridge.

This append-only compatibility epoch leaves every parent implementation and
release byte unchanged.  During the one authorized recovery call it replaces
only ``execution.validate_full_plan`` with the already-sealed state-chain
validator, partially bound to the exact open execution.  Every execution
callable is restored to its pre-call identity in ``finally``.

Pass 87 is validation-only.  The ``recover`` entrypoint exists for the next
same-run pass and is restricted to the exact open candidate-1 failure bound
below; it has rejection authority only and can never publish a pair.
"""

from __future__ import annotations

import argparse
import copy
import functools
import hashlib
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
from scripts import run_spot_spray_simulation_video_ab_extension_aware_batch_v1 as adapter
from scripts import run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1 as state_chain
from scripts import validate_spot_spray_simulation_video_ab_extension_aware_v1 as validator


DEFAULT_CONFIG = state_chain.DEFAULT_CONFIG

CONTRACT = "spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v1"
AUTHORIZATION_CONTRACT = f"{CONTRACT}_manager_authorization"
BRIDGE_CONTRACT = f"{CONTRACT}_bridge"
LOCK_CONTRACT = f"{CONTRACT}_lock"
RELEASE_CONTRACT = f"{CONTRACT}_release"
VALIDATION_RECEIPT_CONTRACT = f"{CONTRACT}_pass87_validation"
INTENT_CONTRACT = f"{CONTRACT}_intent"
TERMINAL_RECEIPT_CONTRACT = f"{CONTRACT}_terminal_receipt"

PASS87_EVENT_ID = "scheduled-resume-20260821004140-55e0bf4310cc"
MANAGER_HANDOFF_EVENT_ID = "scheduled-resume-20260821003556-0eadf61abd17"
MANAGER_SESSION_ID = "019fb346-5ead-7600-8068-40b32b0daa06"
OWNER_SESSION_ID = "01a0019e-e810-73b3-9f29-ffad14c34ec5"
RUN_ID = "goal-multi-repeat-full-simulation-video-ab-execution-v1-e2dcf4ac8b10"
PORTFOLIO_ID = "goal-multi-repeat-agents-spot-spray-simulation-video-ab-v1-b8e46607aeea"
PORTFOLIO_LANE = "full-simulation-video-ab-execution-v1"
PORTFOLIO_REVISION = 140

AUTHORIZED_SOURCE_PATH = (
    "scripts/run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v1.py"
)
AUTHORIZED_TEST_PATH = (
    "tests/test_run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v1.py"
)

LEGACY_EXECUTION_SCRIPT_SHA256 = (
    "200d897efa1400a9dabba1acaf33d1b49db2c00ebcf79768f25fa4a8608bb413"
)
LEGACY_EXECUTION_TEST_SHA256 = state_chain.LEGACY_EXECUTION_TEST_SHA256
VALIDATOR_SCRIPT_SHA256 = state_chain.VALIDATOR_SCRIPT_SHA256
VALIDATOR_TEST_SHA256 = state_chain.VALIDATOR_TEST_SHA256
ADAPTER_SCRIPT_SHA256 = state_chain.ADAPTER_SCRIPT_SHA256
ADAPTER_TEST_SHA256 = state_chain.ADAPTER_TEST_SHA256
STATE_CHAIN_SCRIPT_SHA256 = (
    "bfbe269feddbd92413663c9345e57b50b119617e10bf695784d09317f74b870b"
)
STATE_CHAIN_TEST_SHA256 = (
    "c014b263862de4b91f5d20cb1d2f92d0d526914de720a03bdaa2d60b82e61121"
)
RUNTIME_CONFIG_SHA256 = state_chain.RUNTIME_CONFIG_SHA256
RUNTIME_RELEASE_FILE_SHA256 = state_chain.RUNTIME_RELEASE_FILE_SHA256
RUNTIME_RELEASE_IDENTITY_SHA256 = state_chain.RUNTIME_RELEASE_IDENTITY_SHA256
VALIDATOR_RELEASE_FILE_SHA256 = state_chain.VALIDATOR_RELEASE_FILE_SHA256
VALIDATOR_RELEASE_IDENTITY_SHA256 = state_chain.VALIDATOR_RELEASE_IDENTITY_SHA256
ADAPTER_RELEASE_FILE_SHA256 = state_chain.ADAPTER_RELEASE_FILE_SHA256
ADAPTER_RELEASE_IDENTITY_SHA256 = state_chain.ADAPTER_RELEASE_IDENTITY_SHA256
STATE_CHAIN_RELEASE_FILE_SHA256 = (
    "4c68888c43a09fb4afe4c0c56a365e36d6707c068f250deb891b2765c23f19bd"
)
STATE_CHAIN_RELEASE_IDENTITY_SHA256 = (
    "aa41111d922634b0d9a32a69fa411f0723f30b879dd8039d7dcd1595380213a0"
)
STATE_CHAIN_IMPLEMENTATION_SHA256 = (
    "efb220e893f6d23db2b95a22bd422d033390fa129140702438a09cdf498fb2c1"
)
RECOVERY_FUNCTION_SOURCE_SHA256 = (
    "6f14b47118388514b034b16e147672eb99993c88a9cc2489e2a2f968ed4aac6a"
)
RECOVERY_IMPLEMENTATION_SHA256 = (
    "20aaccaf74b1d7a9c8c11f9924ede38c31bfafdbc2de0c24c34729ff8373326b"
)
RECOVERY_LOCK_SHA256 = (
    "5af1af3dc8792bc91411072b7eeb22bf6e6b22dd00383747a1265a818192ae49"
)
PASS86_RECEIPT_SHA256 = (
    "83b1703bffec1579f0dae149a4a66b0856f76af3cc4a7fea6317fdee47959138"
)

STATE_CHAIN_EXECUTION_ID = "state_chain_batch_locked_test_c001_r04_9362ff91c24928a2"
STATE_CHAIN_INTENT_SHA256 = (
    "cd5755de3799cb75e484760c23d37dc21891924534098f36a05f3514fbfbe8f7"
)
BATCH_ID = "locked_test_render_batch_locked_test_c001_r04_f180ac33c6690a60"
BATCH_INTENT_SHA256 = (
    "7f18c45d97269dc2522c86f8f279aa332fa3c53eda5653927036ad5bbb7cb403"
)
PAIR_ID = "locked_test_c001_r04"
CANDIDATE_INDEX = 1
CANDIDATE_IDENTITY_SHA256 = (
    "b7bdbcc20e110ff85c44f1108d206ad550797c2816ee08484f8cb8472e6bc95f"
)
PAIR_SLOT_IDENTITY_SHA256 = (
    "c84738918147c52362d2c5261ce35d3acf28bc6596e961615b281cb993ff6e49"
)
CURRENT_STATE_SHA256 = (
    "ff5b4b4ce495f7b515b00fa1402fab1dbf11db9bf2b204e1cc2dc858adcc7e5b"
)
CURRENT_HEAD_IDENTITY_SHA256 = (
    "04074c9cdc8eef7599de90966847fb274ddf7e80202372f1a7bb992010782f01"
)
CURRENT_LEDGER_SHA256 = (
    "bad33ba0f3a9737195b41eafc83dd81304fa8e52ba83c64c5fb101ee083073ca"
)
CURRENT_LEDGER_ROW_COUNT = 122
CURRENT_COMPLETED_PAIR_COUNT = 44
CURRENT_PENDING_PAIR_COUNT = 52

_ORIGINAL_VALIDATE_FULL_PLAN = execution.validate_full_plan
_ORIGINAL_RECOVERY_CALLABLE = execution.run_locked_test_gt_source_cardinality_recovery


def recovery_bridge_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    full = execution.full_paths(config)
    synthetic_root = (
        full["synthetic"] / "planning/extension_aware_state_chain_recovery_v1"
    )
    docs_root = full["docs"] / "extension_aware_state_chain_recovery_v1"
    synthetic_release = synthetic_root / "release_v1"
    docs_release = docs_root / "release_v1"
    return {
        "synthetic_root": synthetic_root,
        "docs_root": docs_root,
        "synthetic_release": synthetic_release,
        "docs_release": docs_release,
        "authorization": synthetic_release / "pass87_manager_authorization_receipt.json",
        "bridge": synthetic_release / "state_chain_recovery_bridge_v1.json",
        "lock": synthetic_release / "state_chain_recovery_bridge_lock_v1.json",
        "release": synthetic_release / "state_chain_recovery_bridge_release_v1.json",
        "validation_receipt": synthetic_release / "pass87_validation_receipt.json",
        "executions": synthetic_root / "executions",
        "docs_executions": docs_root / "executions",
    }


def _required_release_files() -> list[str]:
    return [
        "pass87_manager_authorization_receipt.json",
        "pass87_validation_receipt.json",
        "state_chain_recovery_bridge_lock_v1.json",
        "state_chain_recovery_bridge_release_v1.json",
        "state_chain_recovery_bridge_v1.json",
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
        "adapter": PROJECT_ROOT
        / "scripts/run_spot_spray_simulation_video_ab_extension_aware_batch_v1.py",
        "adapter_test": PROJECT_ROOT
        / "tests/test_run_spot_spray_simulation_video_ab_extension_aware_batch_v1.py",
        "state_chain": PROJECT_ROOT
        / "scripts/run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1.py",
        "state_chain_test": PROJECT_ROOT
        / "tests/test_run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1.py",
        "bridge": PROJECT_ROOT / AUTHORIZED_SOURCE_PATH,
        "bridge_test": PROJECT_ROOT / AUTHORIZED_TEST_PATH,
    }


def _recovery_lock_path(config: Mapping[str, Any]) -> Path:
    return (
        execution.roster_extension_paths(config)["execution_locks"]
        / "locked_test_recovery_execution_lock_extension_v1.json"
    )


def _pass86_receipt_path(config: Mapping[str, Any]) -> Path:
    return (
        execution.full_paths(config)["docs"]
        / "locked_test_render_batches/pass85_state_chain_execution/"
        "pass86_fail_closed_receipt.json"
    )


def _state_chain_intent_path(config: Mapping[str, Any]) -> Path:
    return (
        state_chain.state_chain_paths(config)["executions"]
        / STATE_CHAIN_EXECUTION_ID
        / "state_chain_intent.json"
    )


def _batch_root(config: Mapping[str, Any]) -> Path:
    return (
        execution.full_paths(config)["synthetic"]
        / "planning/locked_test_render_batches_v1"
        / BATCH_ID
    )


def _recovery_destination(config: Mapping[str, Any]) -> Path:
    return (
        execution.full_paths(config)["synthetic"]
        / "planning/locked_test_gt_source_cardinality_recovery_v1/roster"
        / PAIR_ID
        / f"candidate_{CANDIDATE_INDEX:02d}"
    )


def _recovery_docs_receipt(config: Mapping[str, Any]) -> Path:
    return (
        execution.full_paths(config)["docs"]
        / "gt_scout_v1"
        / f"locked_test_source_cardinality_recovery_{PAIR_ID}_candidate_{CANDIDATE_INDEX:02d}.json"
    )


def _verify_immutable_parents(
    config_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = config_path.expanduser().resolve()
    if resolved != DEFAULT_CONFIG.expanduser().resolve():
        raise execution.ContractError("Noncanonical state-chain recovery config")
    _require_file_sha256(resolved, RUNTIME_CONFIG_SHA256, "runtime config")
    expected = {
        "legacy_execution": LEGACY_EXECUTION_SCRIPT_SHA256,
        "legacy_test": LEGACY_EXECUTION_TEST_SHA256,
        "validator": VALIDATOR_SCRIPT_SHA256,
        "validator_test": VALIDATOR_TEST_SHA256,
        "adapter": ADAPTER_SCRIPT_SHA256,
        "adapter_test": ADAPTER_TEST_SHA256,
        "state_chain": STATE_CHAIN_SCRIPT_SHA256,
        "state_chain_test": STATE_CHAIN_TEST_SHA256,
    }
    sources = _source_paths()
    for name, digest in expected.items():
        _require_file_sha256(sources[name], digest, name.replace("_", " "))

    if execution.stable_sha256(
        inspect.getsource(execution.run_locked_test_gt_source_cardinality_recovery)
    ) != RECOVERY_FUNCTION_SOURCE_SHA256:
        raise execution.ContractError("Locked-test recovery function source changed")
    if (
        execution.locked_test_gt_source_cardinality_recovery_implementation_sha256()
        != RECOVERY_IMPLEMENTATION_SHA256
    ):
        raise execution.ContractError("Locked-test recovery implementation changed")
    if state_chain.state_chain_implementation_sha256() != STATE_CHAIN_IMPLEMENTATION_SHA256:
        raise execution.ContractError("State-chain implementation changed")

    config, roster = state_chain._verify_immutable_parents(resolved)
    root, release, static = state_chain._validate_static_release(
        config, roster["parents"]
    )
    _require_file_sha256(
        static["paths"]["release_file"],
        STATE_CHAIN_RELEASE_FILE_SHA256,
        "state-chain release",
    )
    if release.get("release_identity_sha256") != STATE_CHAIN_RELEASE_IDENTITY_SHA256:
        raise execution.ContractError("State-chain release identity changed")
    if root.get("chain_root_identity_sha256") != (
        "ef2db36fe123d3398c75c4473a9398a64cfe6b0d8d4438a44dcc176323f26e76"
    ):
        raise execution.ContractError("State-chain root identity changed")

    lock_path = _recovery_lock_path(config)
    _require_file_sha256(lock_path, RECOVERY_LOCK_SHA256, "recovery lock")
    lock = execution.load_json(lock_path)
    if (
        lock.get("recovery_implementation_sha256") != RECOVERY_IMPLEMENTATION_SHA256
        or lock.get("rejection_authority")
        != "exact_locked_validator_zero_source_weed_failure_only"
        or lock.get("acceptance_authority") != "none"
        or lock.get("model_access_allowed") is not False
        or lock.get("prediction_access_allowed") is not False
        or lock.get("outcome_inputs_allowed") is not False
    ):
        raise execution.ContractError("Recovery lock authority changed")
    _require_file_sha256(
        _pass86_receipt_path(config), PASS86_RECEIPT_SHA256, "Pass86 blocker receipt"
    )
    parents = {
        **copy.deepcopy(roster["parents"]),
        "state_chain_script_sha256": STATE_CHAIN_SCRIPT_SHA256,
        "state_chain_test_sha256": STATE_CHAIN_TEST_SHA256,
        "state_chain_release_file_sha256": STATE_CHAIN_RELEASE_FILE_SHA256,
        "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
        "state_chain_implementation_sha256": STATE_CHAIN_IMPLEMENTATION_SHA256,
        "locked_test_recovery_function_source_sha256": RECOVERY_FUNCTION_SOURCE_SHA256,
        "locked_test_recovery_implementation_sha256": RECOVERY_IMPLEMENTATION_SHA256,
        "locked_test_recovery_lock_sha256": RECOVERY_LOCK_SHA256,
        "pass86_blocker_receipt_sha256": PASS86_RECEIPT_SHA256,
    }
    return config, {"parents": parents, "roster": roster, "static": static}


def _pinned_boundary() -> dict[str, Any]:
    return {
        "completed_pair_count": CURRENT_COMPLETED_PAIR_COUNT,
        "pending_pair_count": CURRENT_PENDING_PAIR_COUNT,
        "first_pending_pair_id": PAIR_ID,
        "render_state_sha256": CURRENT_STATE_SHA256,
        "chain_head_identity_sha256": CURRENT_HEAD_IDENTITY_SHA256,
        "candidate_rejection_ledger_sha256": CURRENT_LEDGER_SHA256,
        "candidate_rejection_ledger_row_count": CURRENT_LEDGER_ROW_COUNT,
        "state_chain_execution_id": STATE_CHAIN_EXECUTION_ID,
        "state_chain_intent_sha256": STATE_CHAIN_INTENT_SHA256,
        "underlying_batch_id": BATCH_ID,
        "underlying_batch_intent_sha256": BATCH_INTENT_SHA256,
        "pair_id": PAIR_ID,
        "pair_slot_identity_sha256": PAIR_SLOT_IDENTITY_SHA256,
        "candidate_index": CANDIDATE_INDEX,
        "candidate_identity_sha256": CANDIDATE_IDENTITY_SHA256,
        "recovery_lock_sha256": RECOVERY_LOCK_SHA256,
        "state_chain_terminal_receipt_present": False,
        "batch_terminal_receipt_present": False,
        "candidate_recovery_staging_present": False,
        "candidate_recovery_output_present": False,
    }


def _ledger_prefix_sha256(path: Path, row_count: int) -> str:
    lines = path.read_bytes().splitlines(keepends=True)
    if len(lines) < row_count:
        raise execution.ContractError("Candidate rejection ledger was truncated")
    return hashlib.sha256(b"".join(lines[:row_count])).hexdigest()


def _validate_wrapper_execution_roots(
    config: Mapping[str, Any], *, allow_execution_id: str | None
) -> None:
    parent = recovery_bridge_paths(config)["executions"]
    if not parent.exists():
        if allow_execution_id is not None:
            raise execution.ContractError("Expected recovery-bridge intent is missing")
        return
    partials = list(parent.glob(".partial-*"))
    if partials:
        raise execution.ContractError("Partial recovery-bridge intent exists")
    roots = sorted(path for path in parent.iterdir() if path.is_dir())
    if allow_execution_id is None:
        if roots:
            raise execution.ContractError("Pass87 recovery-bridge execution artifact exists")
        return
    if [root.name for root in roots] != [allow_execution_id]:
        raise execution.ContractError("Wrong or parallel recovery-bridge intent exists")
    if not (roots[0] / "recovery_bridge_intent.json").is_file():
        raise execution.ContractError("Recovery-bridge execution has no intent")


def _validate_open_parent_boundary(
    config_path: Path, *, allow_wrapper_execution_id: str | None = None
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config, parent = _verify_immutable_parents(config_path)
    paths = execution.full_paths(config)
    chain_paths = state_chain.state_chain_paths(config)
    _validate_wrapper_execution_roots(
        config, allow_execution_id=allow_wrapper_execution_id
    )

    chain_validation = state_chain.validate_state_chain_release(
        config_path, allow_open_execution_id=STATE_CHAIN_EXECUTION_ID
    )
    required_validation = {
        "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
        "chain_head_identity_sha256": CURRENT_HEAD_IDENTITY_SHA256,
        "completed_pair_count": CURRENT_COMPLETED_PAIR_COUNT,
        "pending_pair_count": CURRENT_PENDING_PAIR_COUNT,
        "first_pending_pair_id": PAIR_ID,
        "render_state_sha256": CURRENT_STATE_SHA256,
        "candidate_rejection_ledger_sha256": CURRENT_LEDGER_SHA256,
        "candidate_rejection_ledger_row_count": CURRENT_LEDGER_ROW_COUNT,
        "active_execution_id": STATE_CHAIN_EXECUTION_ID,
    }
    if any(chain_validation.get(key) != value for key, value in required_validation.items()):
        raise execution.ContractError("Open state-chain boundary changed")
    for key, expected in (
        ("model_loaded", False),
        ("inference_calls", 0),
        ("prediction_accessed", False),
        ("locked_test_outcome_accessed", False),
        ("registered_targets_used", False),
        ("external_services_modified", False),
        ("outcome_inputs", []),
    ):
        if chain_validation.get(key) != expected:
            raise execution.ContractError("Open state-chain access guard changed")

    state_path, docs_state_path, ledger_path = state_chain._state_paths(config)
    _require_file_sha256(state_path, CURRENT_STATE_SHA256, "44/96 render state")
    _require_file_sha256(docs_state_path, CURRENT_STATE_SHA256, "44/96 docs state")
    _require_file_sha256(ledger_path, CURRENT_LEDGER_SHA256, "122-row rejection ledger")
    if len(execution.read_jsonl(ledger_path)) != CURRENT_LEDGER_ROW_COUNT:
        raise execution.ContractError("Candidate rejection ledger row count changed")

    intent_path = _state_chain_intent_path(config)
    _require_file_sha256(intent_path, STATE_CHAIN_INTENT_SHA256, "state-chain intent")
    intent = execution.load_json(intent_path)
    state_root = intent_path.parent
    if (
        intent.get("execution_id") != STATE_CHAIN_EXECUTION_ID
        or intent.get("request", {}).get("target_pair_id") != PAIR_ID
        or intent.get("request", {}).get("max_new_pairs") != 1
        or intent.get("predecessor_head_identity_sha256")
        != CURRENT_HEAD_IDENTITY_SHA256
        or (state_root / "state_chain_terminal_receipt.json").exists()
    ):
        raise execution.ContractError("Open state-chain intent binding changed")

    batch_root = _batch_root(config)
    batch_intent_path = batch_root / "batch_intent.json"
    _require_file_sha256(batch_intent_path, BATCH_INTENT_SHA256, "batch intent")
    if (batch_root / "batch_receipt.json").exists():
        raise execution.ContractError("Recovery cannot target a terminal batch")
    rows = execution.full_roster_rows(config)
    roster_row, batch_intent, state, observed_batch_root = (
        execution._validate_locked_test_zero_source_recovery_context(
            config, paths, rows, PAIR_ID, BATCH_ID
        )
    )
    if observed_batch_root != batch_root or batch_intent != execution.load_json(
        batch_intent_path
    ):
        raise execution.ContractError("Underlying batch context changed")
    if state.get("completed_pair_count") != CURRENT_COMPLETED_PAIR_COUNT:
        raise execution.ContractError("Open batch render state changed")
    if roster_row.get("pair_slot_identity_sha256") != PAIR_SLOT_IDENTITY_SHA256:
        raise execution.ContractError("Recovery pair slot identity changed")
    candidate = roster_row["candidates"][CANDIDATE_INDEX]
    next_candidate = execution._next_gt_scout_candidate(paths["synthetic"], roster_row)
    if (
        candidate.get("candidate_identity_sha256") != CANDIDATE_IDENTITY_SHA256
        or next_candidate != candidate
        or int(next_candidate.get("candidate_index", -1)) != CANDIDATE_INDEX
    ):
        raise execution.ContractError("Candidate 1 is not the canonical successor")

    commits = state_chain._list_commits(chain_paths)
    if commits[-1]["head"].get("head_identity_sha256") != CURRENT_HEAD_IDENTITY_SHA256:
        raise execution.ContractError("State-chain head changed")
    destination = _recovery_destination(config)
    recovery_root = destination.parents[2]
    partials = (
        list(recovery_root.glob(f".partial-{PAIR_ID}-candidate-{CANDIDATE_INDEX:02d}-*"))
        if recovery_root.exists()
        else []
    )
    if destination.exists() or partials or _recovery_docs_receipt(config).exists():
        raise execution.ContractError("Candidate 1 recovery output or staging exists")
    if paths["run"].exists():
        raise execution.ContractError("Full benchmark model output root exists")

    boundary = {
        **_pinned_boundary(),
        "candidate_rejection_ledger_prefix_sha256": _ledger_prefix_sha256(
            ledger_path, CURRENT_LEDGER_ROW_COUNT
        ),
        "model_loaded": False,
        "inference_calls": 0,
        "prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "registered_targets_used": False,
        "external_services_modified": False,
        "outcome_inputs": [],
    }
    if boundary["candidate_rejection_ledger_prefix_sha256"] != CURRENT_LEDGER_SHA256:
        raise execution.ContractError("Ledger prefix identity changed")
    return config, parent, boundary


def _authorization_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": AUTHORIZATION_CONTRACT,
        "status": "PASS_MANAGER_AUTHORIZED_STATE_CHAIN_RECOVERY_BRIDGE_SYNTHETIC_ONLY",
        "authorization": {
            "manager_handoff_event_id": MANAGER_HANDOFF_EVENT_ID,
            "pass87_event_id": PASS87_EVENT_ID,
            "manager_session_id": MANAGER_SESSION_ID,
            "owner_session_id": OWNER_SESSION_ID,
            "goal_multi_repeat_run_id": RUN_ID,
            "pass": 87,
            "strategy": "base",
            "portfolio_id": PORTFOLIO_ID,
            "portfolio_lane": PORTFOLIO_LANE,
            "portfolio_revision": PORTFOLIO_REVISION,
        },
        "authorized_top_level_source_paths": [
            AUTHORIZED_SOURCE_PATH,
            AUTHORIZED_TEST_PATH,
        ],
        "authorized_target": {
            "state_chain_execution_id": STATE_CHAIN_EXECUTION_ID,
            "batch_id": BATCH_ID,
            "pair_id": PAIR_ID,
            "candidate_index": CANDIDATE_INDEX,
            "candidate_identity_sha256": CANDIDATE_IDENTITY_SHA256,
        },
        "authorized_mechanism": {
            "temporary_execution_global": "validate_full_plan",
            "replacement_callable": (
                "extension_aware_state_chain_validate_full_plan"
            ),
            "replacement_partial_allow_open_execution_id": STATE_CHAIN_EXECUTION_ID,
            "unchanged_recovery_callable": (
                "run_locked_test_gt_source_cardinality_recovery"
            ),
            "try_finally_restore_all_callable_identities": True,
            "other_parent_source_or_callable_mutation_allowed": False,
        },
        "authority": {
            "exact_zero_source_weed_rejection_only": True,
            "candidate_acceptance_allowed": False,
            "candidate_skip_allowed": False,
            "gate_relaxation_allowed": False,
            "render_or_pair_publication_allowed": False,
        },
        "pass87_validation_only": True,
        "claim_boundary": _claim_boundary(config),
    }


def _bridge_payload(config: Mapping[str, Any], parents: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": BRIDGE_CONTRACT,
        "status": "SEALED_STATE_CHAIN_AWARE_ZERO_SOURCE_WEED_RECOVERY_BRIDGE_SYNTHETIC_ONLY",
        "immutable_parents": copy.deepcopy(dict(parents)),
        "pinned_open_boundary": _pinned_boundary(),
        "compatibility_mechanism": {
            "validate_before_wrapper_intent": True,
            "validate_before_candidate_gt_access": True,
            "patch_target": "execution.validate_full_plan",
            "replacement": (
                "functools.partial(extension_aware_state_chain_validate_full_plan, "
                f"allow_open_execution_id={STATE_CHAIN_EXECUTION_ID})"
            ),
            "unchanged_recovery_callable": True,
            "restore_snapshot_in_finally": True,
            "reject_unexpected_callable_change": True,
        },
        "execution_contract": {
            "intent_contract": INTENT_CONTRACT,
            "terminal_receipt_contract": TERMINAL_RECEIPT_CONTRACT,
            "byte_identical_resume_only": True,
            "atomic_intent_and_terminal_receipt": True,
            "partial_or_parallel_intent_fails_closed": True,
            "published_uncommitted_recovery_is_resumable": True,
            "ledger_commit_is_append_only_and_idempotent": True,
            "state_and_chain_head_must_not_advance": True,
        },
        "access_guard": {
            "candidate_gt_accessed_during_pass87": False,
            "rendering_calls_during_pass87": 0,
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


def _callable_snapshot() -> dict[str, Callable[..., Any]]:
    return {name: value for name, value in vars(execution).items() if callable(value)}


def _assert_only_validator_changed(
    before: Mapping[str, Callable[..., Any]], expected: Callable[..., Any]
) -> None:
    after = _callable_snapshot()
    if set(after) != set(before):
        raise execution.ContractError("Execution callable set changed")
    for name, original in before.items():
        required = expected if name == "validate_full_plan" else original
        if after[name] is not required:
            raise execution.ContractError(f"Unauthorized execution callable change: {name}")


def _restore_callable_snapshot(before: Mapping[str, Callable[..., Any]]) -> None:
    current = _callable_snapshot()
    for name in set(current) - set(before):
        delattr(execution, name)
    for name, original in before.items():
        setattr(execution, name, original)
    restored = _callable_snapshot()
    if set(restored) != set(before) or any(
        restored[name] is not original for name, original in before.items()
    ):
        raise execution.ContractError("Execution callable snapshot was not restored")


def _call_unchanged_recovery(config_path: Path) -> dict[str, Any]:
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator is not installed before bridge")
    if execution.run_locked_test_gt_source_cardinality_recovery is not (
        _ORIGINAL_RECOVERY_CALLABLE
    ):
        raise execution.ContractError("Locked-test recovery callable identity changed")
    replacement = functools.partial(
        state_chain.extension_aware_state_chain_validate_full_plan,
        allow_open_execution_id=STATE_CHAIN_EXECUTION_ID,
    )
    before = _callable_snapshot()
    unauthorized_error: execution.ContractError | None = None
    try:
        execution.validate_full_plan = replacement
        _assert_only_validator_changed(before, replacement)
        result = execution.run_locked_test_gt_source_cardinality_recovery(
            config_path,
            PAIR_ID,
            candidate_index=CANDIDATE_INDEX,
            batch_id=BATCH_ID,
        )
        try:
            _assert_only_validator_changed(before, replacement)
        except execution.ContractError as error:
            unauthorized_error = error
        if unauthorized_error is not None:
            raise unauthorized_error
        return result
    finally:
        try:
            _assert_only_validator_changed(before, replacement)
        except execution.ContractError as error:
            unauthorized_error = error
        _restore_callable_snapshot(before)
        if unauthorized_error is not None and sys.exc_info()[0] is None:
            raise unauthorized_error


def recovery_bridge_implementation_sha256() -> str:
    functions = (
        _verify_immutable_parents,
        _validate_open_parent_boundary,
        _callable_snapshot,
        _assert_only_validator_changed,
        _restore_callable_snapshot,
        _call_unchanged_recovery,
        _publish_or_resume_intent,
        _validate_recovery_artifacts,
        _validate_runtime_phase,
        _validate_terminal_receipt,
        run_state_chain_recovery,
    )
    return execution.stable_sha256(
        {
            "contract": CONTRACT,
            "functions": {
                function.__name__: inspect.getsource(function) for function in functions
            },
            "state_chain_release_identity_sha256": (
                STATE_CHAIN_RELEASE_IDENTITY_SHA256
            ),
            "recovery_implementation_sha256": RECOVERY_IMPLEMENTATION_SHA256,
            "recovery_lock_sha256": RECOVERY_LOCK_SHA256,
        }
    )


def _lock_payload(
    config: Mapping[str, Any], *, bridge_sha256: str
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": LOCK_CONTRACT,
        "status": "SEALED_STATE_CHAIN_RECOVERY_BRIDGE_LOCK_SYNTHETIC_ONLY",
        "bridge_sha256": execution.require_sha256(bridge_sha256, "recovery bridge"),
        "bridge_implementation_sha256": recovery_bridge_implementation_sha256(),
        "legacy_execution_script_sha256": LEGACY_EXECUTION_SCRIPT_SHA256,
        "state_chain_script_sha256": STATE_CHAIN_SCRIPT_SHA256,
        "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
        "recovery_function_source_sha256": RECOVERY_FUNCTION_SOURCE_SHA256,
        "recovery_implementation_sha256": RECOVERY_IMPLEMENTATION_SHA256,
        "recovery_execution_lock_sha256": RECOVERY_LOCK_SHA256,
        "rejection_authority": "exact_locked_validator_zero_source_weed_failure_only",
        "acceptance_authority": "none",
        "patch_target": "execution.validate_full_plan",
        "all_callable_identities_restored_in_finally": True,
        "model_prediction_outcome_target_or_external_access_allowed": False,
        "claim_boundary": _claim_boundary(config),
    }


def _release_payload(
    config: Mapping[str, Any],
    parents: Mapping[str, Any],
    *,
    authorization_sha256: str,
    bridge_sha256: str,
    lock_sha256: str,
) -> dict[str, Any]:
    sources = _source_paths()
    payload = {
        "schema_version": 1,
        "contract": RELEASE_CONTRACT,
        "status": "SEALED_STATE_CHAIN_RECOVERY_BRIDGE_RELEASE_SYNTHETIC_ONLY",
        "authorization_receipt_sha256": authorization_sha256,
        "bridge_sha256": bridge_sha256,
        "bridge_lock_sha256": lock_sha256,
        "bridge_script_sha256": execution.sha256_file(sources["bridge"]),
        "bridge_test_sha256": execution.sha256_file(sources["bridge_test"]),
        "bridge_implementation_sha256": recovery_bridge_implementation_sha256(),
        "immutable_parents": copy.deepcopy(dict(parents)),
        "pinned_open_boundary": _pinned_boundary(),
        "pass87_validation_only": True,
        "historical_parent_intent_receipt_or_pair_bytes_rewritten": False,
        "real_recovery_or_candidate_gt_access_during_pass87": False,
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
                if path.is_file() and path.name != "pass87_validation_receipt.json"
            ),
            key=lambda value: value.relative_to(root).as_posix(),
        )
    ]


def _validation_receipt_payload(
    config: Mapping[str, Any],
    release_root: Path,
    release: Mapping[str, Any],
    boundary: Mapping[str, Any],
) -> dict[str, Any]:
    rows = _artifact_rows(release_root)
    return {
        "schema_version": 1,
        "contract": VALIDATION_RECEIPT_CONTRACT,
        "status": "READY_FOR_STATE_CHAIN_RECOVERY_EXECUTION_SYNTHETIC_ONLY",
        "goal_multi_repeat_run_id": RUN_ID,
        "event_id": PASS87_EVENT_ID,
        "pass": 87,
        "recovery_bridge_release_identity_sha256": release[
            "release_identity_sha256"
        ],
        "validated_open_boundary": copy.deepcopy(dict(boundary)),
        "artifact_inventory": {
            "files": rows,
            "file_count": len(rows),
            "inventory_sha256": execution.stable_sha256(rows),
        },
        "pass87_access_guard": {
            "validation_only": True,
            "real_recovery_bridge_intents_created": 0,
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
            raise execution.ContractError("Recovery-bridge release file set changed")
    for relative in required:
        if execution.sha256_file(
            paths["synthetic_release"] / relative
        ) != execution.sha256_file(paths["docs_release"] / relative):
            raise execution.ContractError("Recovery-bridge docs mirror changed")


def _validate_static_release_identity(
    config_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config, parent = _verify_immutable_parents(config_path)
    paths = recovery_bridge_paths(config)
    _validate_release_file_set(paths)
    authorization = execution.load_json(paths["authorization"])
    if authorization != _authorization_payload(config):
        raise execution.ContractError("Recovery-bridge manager authorization changed")
    bridge = execution.load_json(paths["bridge"])
    if bridge != _bridge_payload(config, parent["parents"]):
        raise execution.ContractError("State-chain recovery bridge changed")
    lock = execution.load_json(paths["lock"])
    if lock != _lock_payload(config, bridge_sha256=execution.sha256_file(paths["bridge"])):
        raise execution.ContractError("State-chain recovery bridge lock changed")
    release = execution.load_json(paths["release"])
    expected_release = _release_payload(
        config,
        parent["parents"],
        authorization_sha256=execution.sha256_file(paths["authorization"]),
        bridge_sha256=execution.sha256_file(paths["bridge"]),
        lock_sha256=execution.sha256_file(paths["lock"]),
    )
    if release != expected_release:
        raise execution.ContractError("State-chain recovery bridge release changed")
    identity_payload = copy.deepcopy(release)
    identity = identity_payload.pop("release_identity_sha256", None)
    if identity != execution.stable_sha256(identity_payload):
        raise execution.ContractError("Recovery-bridge release identity changed")
    return config, parent, release


def seal_recovery_bridge_release(config_path: Path) -> dict[str, Any]:
    config, parent, boundary = _validate_open_parent_boundary(config_path)
    paths = recovery_bridge_paths(config)
    partials = list(paths["synthetic_release"].parent.glob(".partial-*")) + list(
        paths["docs_release"].parent.glob(".partial-*")
    )
    if partials:
        raise execution.ContractError("Partial recovery-bridge release exists")
    if paths["executions"].exists() or paths["docs_executions"].exists():
        raise execution.ContractError("Pass87 recovery-bridge execution artifact exists")
    if paths["synthetic_release"].exists() or paths["docs_release"].exists():
        return validate_recovery_bridge_release(config_path)

    synthetic_parent = paths["synthetic_release"].parent
    docs_parent = paths["docs_release"].parent
    synthetic_parent.mkdir(parents=True, exist_ok=True)
    docs_parent.mkdir(parents=True, exist_ok=True)
    staging = synthetic_parent / f".partial-recovery-bridge-{uuid.uuid4().hex}"
    docs_staging = docs_parent / f".partial-recovery-bridge-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        authorization = _authorization_payload(config)
        bridge = _bridge_payload(config, parent["parents"])
        execution.write_json(
            staging / "pass87_manager_authorization_receipt.json", authorization
        )
        execution.write_json(staging / "state_chain_recovery_bridge_v1.json", bridge)
        lock = _lock_payload(
            config,
            bridge_sha256=execution.sha256_file(
                staging / "state_chain_recovery_bridge_v1.json"
            ),
        )
        execution.write_json(staging / "state_chain_recovery_bridge_lock_v1.json", lock)
        release = _release_payload(
            config,
            parent["parents"],
            authorization_sha256=execution.sha256_file(
                staging / "pass87_manager_authorization_receipt.json"
            ),
            bridge_sha256=execution.sha256_file(
                staging / "state_chain_recovery_bridge_v1.json"
            ),
            lock_sha256=execution.sha256_file(
                staging / "state_chain_recovery_bridge_lock_v1.json"
            ),
        )
        execution.write_json(
            staging / "state_chain_recovery_bridge_release_v1.json", release
        )
        staging.replace(paths["synthetic_release"])
        receipt = _validation_receipt_payload(
            config, paths["synthetic_release"], release, boundary
        )
        execution.write_json(paths["validation_receipt"], receipt)
        shutil.copytree(paths["synthetic_release"], docs_staging)
        docs_staging.replace(paths["docs_release"])
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if docs_staging.exists():
            shutil.rmtree(docs_staging)
    return validate_recovery_bridge_release(config_path)


def validate_recovery_bridge_release(config_path: Path) -> dict[str, Any]:
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator was not restored")
    config, _, boundary = _validate_open_parent_boundary(config_path)
    _, _, release = _validate_static_release_identity(config_path)
    paths = recovery_bridge_paths(config)
    partials = list(paths["synthetic_release"].parent.glob(".partial-*")) + list(
        paths["docs_release"].parent.glob(".partial-*")
    )
    if partials:
        raise execution.ContractError("Partial recovery-bridge release exists")
    receipt = execution.load_json(paths["validation_receipt"])
    expected = _validation_receipt_payload(
        config, paths["synthetic_release"], release, boundary
    )
    if receipt != expected:
        raise execution.ContractError("Pass87 validation receipt changed")
    return {
        "status": receipt["status"],
        "recovery_bridge_release_identity_sha256": release[
            "release_identity_sha256"
        ],
        "completed_pair_count": CURRENT_COMPLETED_PAIR_COUNT,
        "pending_pair_count": CURRENT_PENDING_PAIR_COUNT,
        "first_pending_pair_id": PAIR_ID,
        "candidate_rejection_ledger_row_count": CURRENT_LEDGER_ROW_COUNT,
        "candidate_index": CANDIDATE_INDEX,
        "real_recovery_bridge_intents_created": 0,
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


def _request(release_identity: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": CONTRACT,
        "recovery_bridge_release_identity_sha256": execution.require_sha256(
            release_identity, "recovery-bridge release identity"
        ),
        "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
        "state_chain_execution_id": STATE_CHAIN_EXECUTION_ID,
        "state_chain_intent_sha256": STATE_CHAIN_INTENT_SHA256,
        "underlying_batch_id": BATCH_ID,
        "underlying_batch_intent_sha256": BATCH_INTENT_SHA256,
        "pair_id": PAIR_ID,
        "candidate_index": CANDIDATE_INDEX,
        "candidate_identity_sha256": CANDIDATE_IDENTITY_SHA256,
        "predecessor_state_sha256": CURRENT_STATE_SHA256,
        "predecessor_head_identity_sha256": CURRENT_HEAD_IDENTITY_SHA256,
        "predecessor_ledger_sha256": CURRENT_LEDGER_SHA256,
        "recovery_lock_sha256": RECOVERY_LOCK_SHA256,
        "rejection_authority": "exact_locked_validator_zero_source_weed_failure_only",
        "acceptance_authority": "none",
        "model_prediction_outcome_target_or_external_access_allowed": False,
    }


def _execution_identity(request: Mapping[str, Any]) -> tuple[str, str]:
    identity = execution.stable_sha256(request)
    execution_id = f"state_chain_recovery_{PAIR_ID}_candidate_01_{identity[:16]}"
    if execution.SAFE_ID_RE.fullmatch(execution_id) is None:
        raise execution.ContractError("Unsafe recovery-bridge execution identity")
    return execution_id, identity


def _publish_or_resume_intent(
    parent: Path, execution_id: str, intent: Mapping[str, Any]
) -> tuple[Path, bool]:
    parent.mkdir(parents=True, exist_ok=True)
    partials = list(parent.glob(".partial-*"))
    if partials:
        raise execution.ContractError("Partial recovery-bridge intent exists")
    roots = sorted(path for path in parent.iterdir() if path.is_dir())
    others = [root for root in roots if root.name != execution_id]
    if others:
        raise execution.ContractError("Wrong or parallel recovery-bridge intent exists")
    root = parent / execution_id
    intent_path = root / "recovery_bridge_intent.json"
    if root.exists():
        if not intent_path.is_file() or execution.load_json(intent_path) != dict(intent):
            raise execution.ContractError("Existing recovery-bridge intent changed")
        return root, True
    staging = parent / f".partial-{execution_id}-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        execution.write_json(staging / "recovery_bridge_intent.json", intent)
        staging.replace(root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return root, False


def _validate_recovery_artifacts(
    config: Mapping[str, Any], *, require_commit: bool
) -> dict[str, Any]:
    destination = _recovery_destination(config)
    terminal_path = destination / "recovery_terminal_receipt.json"
    decision_path = destination / "decision_receipt.json"
    if not terminal_path.is_file() or not decision_path.is_file():
        raise execution.ContractError("Candidate 1 recovery evidence is incomplete")
    terminal = execution.load_json(terminal_path)
    decision = execution.load_json(decision_path)
    valid = (
        terminal.get("contract")
        == execution.LOCKED_TEST_GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT
        and terminal.get("status")
        == "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY"
        and terminal.get("pair_id") == PAIR_ID
        and terminal.get("candidate_index") == CANDIDATE_INDEX
        and terminal.get("candidate_identity_sha256") == CANDIDATE_IDENTITY_SHA256
        and terminal.get("batch_id") == BATCH_ID
        and terminal.get("batch_intent_sha256") == BATCH_INTENT_SHA256
        and terminal.get("recovery_execution_lock_sha256") == RECOVERY_LOCK_SHA256
        and terminal.get("recovery_implementation_sha256")
        == RECOVERY_IMPLEMENTATION_SHA256
        and terminal.get("model_loaded") is False
        and terminal.get("inference_calls") == 0
        and terminal.get("locked_test_prediction_accessed") is False
        and terminal.get("locked_test_outcome_accessed") is False
        and terminal.get("outcome_inputs") == []
        and terminal.get("acceptance_authority") == "none"
        and terminal.get("claim_boundary") == _claim_boundary(config)
        and decision.get("rejection_reasons")
        == ["eligibility:source_weed_track_present"]
        and decision.get("recovery_has_acceptance_authority") is False
        and decision.get("model_or_outcome_inputs_used") is False
        and decision.get("registered_targets_used") is False
        and decision.get("locked_test_prediction_accessed") is False
        and decision.get("locked_test_outcome_accessed") is False
    )
    if not valid:
        raise execution.ContractError("Candidate 1 recovery evidence changed")
    if (destination / "source_scene").exists():
        raise execution.ContractError("Candidate 1 recovery retained bulk source scene")
    inventory = execution.artifact_inventory(destination)
    if any("prediction" in row["path"].lower() for row in inventory):
        raise execution.ContractError("Prediction output exists in recovery evidence")
    commit_path = destination / "ledger_commit_receipt.json"
    commit = execution.load_json(commit_path) if commit_path.is_file() else None
    if require_commit:
        if not isinstance(commit, dict):
            raise execution.ContractError("Recovery ledger commit receipt is missing")
        if (
            commit.get("pair_id") != PAIR_ID
            or commit.get("candidate_index") != CANDIDATE_INDEX
            or commit.get("candidate_identity_sha256") != CANDIDATE_IDENTITY_SHA256
            or commit.get("model_or_outcome_inputs_used") is not False
            or commit.get("idempotent") is not True
        ):
            raise execution.ContractError("Recovery ledger commit receipt changed")
        docs_receipt = _recovery_docs_receipt(config)
        _require_file_sha256(
            docs_receipt,
            execution.sha256_file(terminal_path),
            "recovery docs receipt",
        )
    return {
        "recovery_terminal_receipt_sha256": execution.sha256_file(terminal_path),
        "decision_receipt_sha256": execution.sha256_file(decision_path),
        "ledger_commit_receipt_sha256": (
            execution.sha256_file(commit_path) if commit_path.is_file() else None
        ),
    }


def _validate_runtime_phase(
    config_path: Path, *, wrapper_execution_id: str
) -> tuple[dict[str, Any], dict[str, Any], str]:
    config, parent = _verify_immutable_parents(config_path)
    _validate_wrapper_execution_roots(
        config, allow_execution_id=wrapper_execution_id
    )
    validation = state_chain.validate_state_chain_release(
        config_path, allow_open_execution_id=STATE_CHAIN_EXECUTION_ID
    )
    if (
        validation.get("state_chain_release_identity_sha256")
        != STATE_CHAIN_RELEASE_IDENTITY_SHA256
        or validation.get("chain_head_identity_sha256")
        != CURRENT_HEAD_IDENTITY_SHA256
        or validation.get("completed_pair_count") != CURRENT_COMPLETED_PAIR_COUNT
        or validation.get("pending_pair_count") != CURRENT_PENDING_PAIR_COUNT
        or validation.get("first_pending_pair_id") != PAIR_ID
        or validation.get("render_state_sha256") != CURRENT_STATE_SHA256
        or validation.get("active_execution_id") != STATE_CHAIN_EXECUTION_ID
    ):
        raise execution.ContractError("Recovery runtime state or chain head changed")
    _require_file_sha256(
        _state_chain_intent_path(config),
        STATE_CHAIN_INTENT_SHA256,
        "recovery runtime state-chain intent",
    )
    _require_file_sha256(
        _batch_root(config) / "batch_intent.json",
        BATCH_INTENT_SHA256,
        "recovery runtime batch intent",
    )
    state_path, docs_state_path, ledger_path = state_chain._state_paths(config)
    _require_file_sha256(state_path, CURRENT_STATE_SHA256, "recovery runtime state")
    _require_file_sha256(docs_state_path, CURRENT_STATE_SHA256, "recovery docs state")
    if _ledger_prefix_sha256(ledger_path, CURRENT_LEDGER_ROW_COUNT) != CURRENT_LEDGER_SHA256:
        raise execution.ContractError("Recovery ledger prefix changed")
    ledger = execution.read_jsonl(ledger_path)
    rows = execution.full_roster_rows(config)
    roster_row = next(row for row in rows if row["pair_id"] == PAIR_ID)
    destination = _recovery_destination(config)
    recovery_root = destination.parents[2]
    partials = (
        list(recovery_root.glob(f".partial-{PAIR_ID}-candidate-{CANDIDATE_INDEX:02d}-*"))
        if recovery_root.exists()
        else []
    )
    if partials:
        raise execution.ContractError("Partial candidate 1 recovery staging exists")

    if len(ledger) == CURRENT_LEDGER_ROW_COUNT:
        state_chain._validate_ledger_rows(ledger, rows)
        phase = "ready" if not destination.exists() else "published_uncommitted"
        evidence = (
            _validate_recovery_artifacts(config, require_commit=False)
            if destination.exists()
            else {}
        )
        if evidence.get("ledger_commit_receipt_sha256") is not None:
            raise execution.ContractError(
                "Recovery commit receipt exists without its ledger append"
            )
        if not destination.exists() and _recovery_docs_receipt(config).exists():
            raise execution.ContractError("Recovery docs receipt exists before recovery")
    elif len(ledger) == CURRENT_LEDGER_ROW_COUNT + 1:
        summary = state_chain._validate_ledger_extension(
            ledger[:CURRENT_LEDGER_ROW_COUNT], ledger, rows, PAIR_ID
        )
        appended = ledger[-1]
        if (
            summary.get("appended_row_count") != 1
            or appended.get("candidate_index") != CANDIDATE_INDEX
            or appended.get("candidate_identity_sha256")
            != CANDIDATE_IDENTITY_SHA256
            or appended.get("reason") != "eligibility:source_weed_track_present"
            or appended.get("reason_type") != "GtScoutCandidateRejected"
            or appended.get("model_or_outcome_inputs_used") is not False
        ):
            raise execution.ContractError("Candidate 1 ledger rejection changed")
        evidence = _validate_recovery_artifacts(config, require_commit=True)
        phase = "committed"
    else:
        raise execution.ContractError("Recovery ledger advanced by a noncanonical amount")
    if roster_row["candidates"][CANDIDATE_INDEX][
        "candidate_identity_sha256"
    ] != CANDIDATE_IDENTITY_SHA256:
        raise execution.ContractError("Recovery candidate identity changed")
    if (_batch_root(config) / "batch_receipt.json").exists():
        raise execution.ContractError("Recovery unexpectedly terminalized the batch")
    if (
        state_chain.state_chain_paths(config)["executions"]
        / STATE_CHAIN_EXECUTION_ID
        / "state_chain_terminal_receipt.json"
    ).exists():
        raise execution.ContractError("Recovery unexpectedly terminalized state chain")
    return config, {
        "render_state_sha256": execution.sha256_file(state_path),
        "chain_head_identity_sha256": validation["chain_head_identity_sha256"],
        "candidate_rejection_ledger_sha256": execution.sha256_file(ledger_path),
        "candidate_rejection_ledger_row_count": len(ledger),
        "first_pending_pair_id": validation["first_pending_pair_id"],
        "recovery_evidence": evidence,
        "model_loaded": False,
        "inference_calls": 0,
        "prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "registered_targets_used": False,
        "external_services_modified": False,
        "outcome_inputs": [],
    }, phase


def _terminal_payload(
    config: Mapping[str, Any],
    request: Mapping[str, Any],
    request_identity: str,
    execution_id: str,
    intent_path: Path,
    underlying: Mapping[str, Any],
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    resumed: bool,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": TERMINAL_RECEIPT_CONTRACT,
        "status": "PASS_EXACT_ZERO_SOURCE_WEED_REJECTION_SYNTHETIC_ONLY",
        "execution_id": execution_id,
        "request_identity_sha256": request_identity,
        "request": copy.deepcopy(dict(request)),
        "recovery_bridge_intent_sha256": execution.sha256_file(intent_path),
        "state_chain_intent_sha256": STATE_CHAIN_INTENT_SHA256,
        "underlying_batch_intent_sha256": BATCH_INTENT_SHA256,
        "legacy_recovery": {
            "status": underlying.get("status"),
            "pair_id": underlying.get("pair_id"),
            "candidate_index": underlying.get("candidate_index"),
            "batch_id": underlying.get("batch_id"),
            "recovery_terminal_receipt_sha256": after["recovery_evidence"][
                "recovery_terminal_receipt_sha256"
            ],
            "decision_receipt_sha256": after["recovery_evidence"][
                "decision_receipt_sha256"
            ],
            "ledger_commit_receipt_sha256": after["recovery_evidence"][
                "ledger_commit_receipt_sha256"
            ],
        },
        "boundary": {
            "render_state_sha256_before": before["render_state_sha256"],
            "render_state_sha256_after": after["render_state_sha256"],
            "chain_head_identity_sha256_before": before[
                "chain_head_identity_sha256"
            ],
            "chain_head_identity_sha256_after": after[
                "chain_head_identity_sha256"
            ],
            "candidate_rejection_ledger_sha256_before": before[
                "candidate_rejection_ledger_sha256"
            ],
            "candidate_rejection_ledger_sha256_after": after[
                "candidate_rejection_ledger_sha256"
            ],
            "candidate_rejection_ledger_row_count_before": before[
                "candidate_rejection_ledger_row_count"
            ],
            "candidate_rejection_ledger_row_count_after": after[
                "candidate_rejection_ledger_row_count"
            ],
        },
        "resume": {"resumed_from_existing_bridge_intent": resumed},
        "original_validator_restored": execution.validate_full_plan
        is _ORIGINAL_VALIDATE_FULL_PLAN,
        "access_guard": {
            "candidate_acceptance_or_pair_publication": False,
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


def _validate_terminal_receipt(
    config: Mapping[str, Any],
    receipt: Mapping[str, Any],
    request: Mapping[str, Any],
    request_identity: str,
    execution_id: str,
    intent_path: Path,
    current: Mapping[str, Any],
) -> None:
    access = receipt.get("access_guard", {})
    boundary = receipt.get("boundary", {})
    legacy = receipt.get("legacy_recovery", {})
    valid = (
        receipt.get("schema_version") == 1
        and receipt.get("contract") == TERMINAL_RECEIPT_CONTRACT
        and receipt.get("status")
        == "PASS_EXACT_ZERO_SOURCE_WEED_REJECTION_SYNTHETIC_ONLY"
        and receipt.get("execution_id") == execution_id
        and receipt.get("request_identity_sha256") == request_identity
        and receipt.get("request") == dict(request)
        and receipt.get("recovery_bridge_intent_sha256")
        == execution.sha256_file(intent_path)
        and receipt.get("state_chain_intent_sha256") == STATE_CHAIN_INTENT_SHA256
        and receipt.get("underlying_batch_intent_sha256") == BATCH_INTENT_SHA256
        and receipt.get("original_validator_restored") is True
        and legacy.get("pair_id") == PAIR_ID
        and legacy.get("candidate_index") == CANDIDATE_INDEX
        and legacy.get("batch_id") == BATCH_ID
        and legacy.get("recovery_terminal_receipt_sha256")
        == current["recovery_evidence"]["recovery_terminal_receipt_sha256"]
        and legacy.get("decision_receipt_sha256")
        == current["recovery_evidence"]["decision_receipt_sha256"]
        and legacy.get("ledger_commit_receipt_sha256")
        == current["recovery_evidence"]["ledger_commit_receipt_sha256"]
        and boundary.get("render_state_sha256_before") == CURRENT_STATE_SHA256
        and boundary.get("render_state_sha256_after") == CURRENT_STATE_SHA256
        and boundary.get("chain_head_identity_sha256_before")
        == CURRENT_HEAD_IDENTITY_SHA256
        and boundary.get("chain_head_identity_sha256_after")
        == CURRENT_HEAD_IDENTITY_SHA256
        and boundary.get("candidate_rejection_ledger_sha256_before")
        == CURRENT_LEDGER_SHA256
        and boundary.get("candidate_rejection_ledger_sha256_after")
        == current["candidate_rejection_ledger_sha256"]
        and boundary.get("candidate_rejection_ledger_row_count_before")
        == CURRENT_LEDGER_ROW_COUNT
        and boundary.get("candidate_rejection_ledger_row_count_after")
        == CURRENT_LEDGER_ROW_COUNT + 1
        and access.get("candidate_acceptance_or_pair_publication") is False
        and access.get("rendering_calls") == 0
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
        raise execution.ContractError("Recovery-bridge terminal receipt changed")


def run_state_chain_recovery(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config, _, release = _validate_static_release_identity(config_path)
    request = _request(release["release_identity_sha256"])
    execution_id, request_identity = _execution_identity(request)
    paths = recovery_bridge_paths(config)
    execution_root = paths["executions"] / execution_id
    intent_path = execution_root / "recovery_bridge_intent.json"
    terminal_path = execution_root / "recovery_bridge_terminal_receipt.json"
    docs_terminal = paths["docs_executions"] / f"{execution_id}.json"

    if terminal_path.is_file():
        intent = execution.load_json(intent_path)
        if intent.get("request") != request:
            raise execution.ContractError("Existing recovery-bridge request changed")
        _, current, phase = _validate_runtime_phase(
            config_path, wrapper_execution_id=execution_id
        )
        if phase != "committed":
            raise execution.ContractError("Terminal recovery is not ledger-committed")
        receipt = execution.load_json(terminal_path)
        _validate_terminal_receipt(
            config,
            receipt,
            request,
            request_identity,
            execution_id,
            intent_path,
            current,
        )
        execution._write_json_once_atomically(docs_terminal, receipt)
        return {
            "status": "SKIP_EXISTING_PASS_EXACT_ZERO_SOURCE_WEED_REJECTION_SYNTHETIC_ONLY",
            "execution_id": execution_id,
            "recovery_bridge_terminal_receipt_sha256": execution.sha256_file(
                terminal_path
            ),
            "candidate_rejection_ledger_row_count": CURRENT_LEDGER_ROW_COUNT + 1,
            "model_loaded": False,
            "inference_calls": 0,
            "synthetic_only": True,
        }

    if execution_root.exists():
        intent = execution.load_json(intent_path)
        expected_intent = {
            "schema_version": 1,
            "contract": INTENT_CONTRACT,
            "status": "STATE_CHAIN_RECOVERY_BRIDGE_INTENT_SYNTHETIC_ONLY",
            "execution_id": execution_id,
            "request_identity_sha256": request_identity,
            "request": request,
            "boundary_at_start": _pinned_boundary(),
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
        if intent != expected_intent:
            raise execution.ContractError("Existing recovery-bridge intent changed")
        resumed = True
    else:
        validation = validate_recovery_bridge_release(config_path)
        if validation["recovery_bridge_release_identity_sha256"] != release[
            "release_identity_sha256"
        ]:
            raise execution.ContractError("Recovery-bridge release identity changed")
        intent = {
            "schema_version": 1,
            "contract": INTENT_CONTRACT,
            "status": "STATE_CHAIN_RECOVERY_BRIDGE_INTENT_SYNTHETIC_ONLY",
            "execution_id": execution_id,
            "request_identity_sha256": request_identity,
            "request": request,
            "boundary_at_start": _pinned_boundary(),
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
        execution_root, resumed = _publish_or_resume_intent(
            paths["executions"], execution_id, intent
        )
        intent_path = execution_root / "recovery_bridge_intent.json"
    if execution.load_json(intent_path) != intent:
        raise execution.ContractError("Recovery-bridge intent changed after publication")

    _, before, phase_before = _validate_runtime_phase(
        config_path, wrapper_execution_id=execution_id
    )
    if phase_before not in {"ready", "published_uncommitted", "committed"}:
        raise execution.ContractError("Unknown recovery resume phase")
    if phase_before == "ready" and before[
        "candidate_rejection_ledger_sha256"
    ] != CURRENT_LEDGER_SHA256:
        raise execution.ContractError("Recovery start ledger changed")
    underlying = _call_unchanged_recovery(config_path)
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator was not restored after recovery")
    _, after, phase_after = _validate_runtime_phase(
        config_path, wrapper_execution_id=execution_id
    )
    if phase_after != "committed":
        raise execution.ContractError("Candidate 1 rejection was not atomically committed")
    terminal = _terminal_payload(
        config,
        request,
        request_identity,
        execution_id,
        intent_path,
        underlying,
        {
            **before,
            "render_state_sha256": CURRENT_STATE_SHA256,
            "chain_head_identity_sha256": CURRENT_HEAD_IDENTITY_SHA256,
            "candidate_rejection_ledger_sha256": CURRENT_LEDGER_SHA256,
            "candidate_rejection_ledger_row_count": CURRENT_LEDGER_ROW_COUNT,
        },
        after,
        resumed,
    )
    _validate_terminal_receipt(
        config,
        terminal,
        request,
        request_identity,
        execution_id,
        intent_path,
        after,
    )
    execution._write_json_once_atomically(terminal_path, terminal)
    execution._write_json_once_atomically(docs_terminal, terminal)
    return {
        "status": terminal["status"],
        "execution_id": execution_id,
        "recovery_bridge_terminal_receipt_sha256": execution.sha256_file(
            terminal_path
        ),
        "candidate_rejection_ledger_row_count": CURRENT_LEDGER_ROW_COUNT + 1,
        "state_unchanged": True,
        "chain_head_unchanged": True,
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
    subparsers.add_parser("recover")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        if arguments.command == "seal":
            result = seal_recovery_bridge_release(arguments.config)
        elif arguments.command == "validate":
            result = validate_recovery_bridge_release(arguments.config)
        elif arguments.command == "recover":
            result = run_state_chain_recovery(arguments.config)
        else:
            raise AssertionError(arguments.command)
    except execution.ContractError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
