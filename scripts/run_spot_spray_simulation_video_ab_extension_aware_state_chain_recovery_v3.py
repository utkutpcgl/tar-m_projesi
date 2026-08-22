#!/usr/bin/env python3
"""Seal and run the canonical-active-pair zero-weed recovery bridge.

Recovery V3 is an append-only compatibility epoch.  It never accepts caller
selected pair, batch, execution, or candidate identifiers.  Instead it derives
the sole active state-chain execution, its matching legacy batch, the canonical
first-pending locked-test pair, and the lowest unattempted frozen-roster
candidate.  Its only mutation authority is the unchanged legacy recovery's
exact zero-source-weed rejection append.

Pass 108 is validation-only.  ``recover-current-zero-weed`` is intentionally
available for a later same-run pass; sealing and validation do not access
candidate GT, invoke a renderer, or touch model/outcome inputs.
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
from scripts import run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v1 as recovery_v1
from scripts import run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v2 as recovery_v2
from scripts import run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1 as state_chain


DEFAULT_CONFIG = state_chain.DEFAULT_CONFIG

CONTRACT = "spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v3"
AUTHORIZATION_CONTRACT = f"{CONTRACT}_manager_authorization"
BRIDGE_CONTRACT = f"{CONTRACT}_bridge"
LOCK_CONTRACT = f"{CONTRACT}_lock"
RELEASE_CONTRACT = f"{CONTRACT}_release"
VALIDATION_RECEIPT_CONTRACT = f"{CONTRACT}_pass108_validation"
INTENT_CONTRACT = f"{CONTRACT}_intent"
TERMINAL_RECEIPT_CONTRACT = f"{CONTRACT}_terminal_receipt"

PASS108_EVENT_ID = "scheduled-resume-20260821060145-11a730c2599a"
MANAGER_HANDOFF_EVENT_ID = "scheduled-resume-20260821055719-95edab2a9737"
MANAGER_SESSION_ID = "019fb346-5ead-7600-8068-40b32b0daa06"
OWNER_SESSION_ID = "01a0019e-e810-73b3-9f29-ffad14c34ec5"
RUN_ID = "goal-multi-repeat-full-simulation-video-ab-execution-v1-e2dcf4ac8b10"
PORTFOLIO_ID = "goal-multi-repeat-agents-spot-spray-simulation-video-ab-v1-b8e46607aeea"
PORTFOLIO_LANE = "full-simulation-video-ab-execution-v1"
PORTFOLIO_REVISION = 163

AUTHORIZED_SOURCE_PATH = (
    "scripts/run_spot_spray_simulation_video_ab_extension_aware_"
    "state_chain_recovery_v3.py"
)
AUTHORIZED_TEST_PATH = (
    "tests/test_run_spot_spray_simulation_video_ab_extension_aware_"
    "state_chain_recovery_v3.py"
)

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
ADAPTER_SCRIPT_SHA256 = (
    "c4e74ce3b04ea9954c6e92fdccc5405036dad3b460cbb8b1f99068740418947e"
)
ADAPTER_TEST_SHA256 = (
    "50e6183c2f0e4878c0bed4f01049c6a0997b2ce6c2a46e24cf99ce571aa5f1a5"
)
STATE_CHAIN_SCRIPT_SHA256 = (
    "bfbe269feddbd92413663c9345e57b50b119617e10bf695784d09317f74b870b"
)
STATE_CHAIN_TEST_SHA256 = (
    "c014b263862de4b91f5d20cb1d2f92d0d526914de720a03bdaa2d60b82e61121"
)
RECOVERY_V1_SCRIPT_SHA256 = (
    "6c35f6635b8cd6720271bc3fc246b48ae24ba3a70869e526e18c5c33afb8d2d9"
)
RECOVERY_V1_TEST_SHA256 = (
    "003f42bf83d48073803a77920bebc1313f6f8240e8c141a851a5332d55638c72"
)
RECOVERY_V2_SCRIPT_SHA256 = (
    "0cd1bcf21b27aad8723736a0cf015c79aa66432abcf35cd54fdb65809f93e72f"
)
RECOVERY_V2_TEST_SHA256 = (
    "1fff0ce98899c7d8b5cd33364e1e3afaad6484c1be5013267b8c2c81bc34c0fb"
)

RUNTIME_CONFIG_SHA256 = state_chain.RUNTIME_CONFIG_SHA256
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
RECOVERY_V1_RELEASE_FILE_SHA256 = (
    "f11f72ed131cf04c2352de35e50e8c1a8677546568ea969681f005f967f62e82"
)
RECOVERY_V1_RELEASE_IDENTITY_SHA256 = (
    "dd33482b9a1f8bbbc06358100c7760d6f61ead5f94da5c3f5bfc143a27d6a4fa"
)
RECOVERY_V1_TERMINAL_SHA256 = (
    "790047b6aa5bede8cf08bee9e2a20ce75788bb8a686ef61238d94b88289b62fd"
)
RECOVERY_V2_RELEASE_FILE_SHA256 = (
    "4985ba64cfd39d9291820ef843f75cc6bc65d41b605c0f00ececcf2ded350667"
)
RECOVERY_V2_RELEASE_IDENTITY_SHA256 = (
    "27a74f1bea57710f6eed48c48389e3a6af34a3cfc1d8c92fd6a79dbe23883f8f"
)
RECOVERY_V2_INTENT_SHA256 = (
    "8afff61b0e718d3e73ada3b9779289e530050a8b23af49ffbd1ed7ce835928da"
)
RECOVERY_V2_TERMINAL_SHA256 = (
    "8c7a490dce976ee861c5c6820e81b5dfaf4e69fc4c8225b410b3adf4c9587f51"
)
RECOVERY_V2_EXECUTION_ID = (
    "state_chain_recovery_v2_locked_test_c001_r04_candidate_02_4efd48dca69c9e0d"
)
PASS107_RECEIPT_SHA256 = (
    "2e9f04d01f7fb4d6bf4a617089bdde5c11b1e705705eb295311e7506db4990ee"
)

GENESIS_COMPLETED_PAIR_COUNT = 45
GENESIS_PENDING_PAIR_COUNT = 51
GENESIS_STATE_SHA256 = (
    "f811c3e3d5622bbc741e4c84951db4c3287181f2ed219ef45c8d0877c7a12553"
)
GENESIS_HEAD_IDENTITY_SHA256 = (
    "34acee5f2fb322fa839ffd9bfc0edf9722e1556d6085d56cb145d65fd56bab71"
)
GENESIS_LEDGER_ROW_COUNT = 142
GENESIS_LEDGER_SHA256 = (
    "4320f0f486eb62bd52f5b5696125bc5f9d7e8a7a6b49e150203636d4f0432f2c"
)
GENESIS_PAIR_ID = "locked_test_c001_r05"
GENESIS_PAIR_SLOT_IDENTITY_SHA256 = (
    "7ba56a1f3fd43925be890183fe4894df9d182b44bded6d5fa7cac26e56be981f"
)
GENESIS_STATE_CHAIN_EXECUTION_ID = (
    "state_chain_batch_locked_test_c001_r05_fe3a9bf5ccf9db11"
)
GENESIS_STATE_CHAIN_INTENT_SHA256 = (
    "fa987a19efaf6f3932978beb368694c22a6501642e6f69f441ac55edbd76359c"
)
GENESIS_BATCH_ID = "locked_test_render_batch_locked_test_c001_r05_65e15722fcb2d69c"
GENESIS_BATCH_INTENT_SHA256 = (
    "09c278a49ed3457dace1e0e306d84dd6dd4024b1f6a09cba216c65e236eb2e20"
)
GENESIS_CANDIDATE_INDEX = 8
GENESIS_CANDIDATE_IDENTITY_SHA256 = (
    "bdd323a826c030fe90c7f15c19a22d7c57bdfb5e093b167414d09154e6f14d4d"
)
GENESIS_SOURCE_TEMPLATE_SHA256 = (
    "56f1d8c93e532056d4fc81c8f489c8a0acc5c9fcb1005c2e2b8db1ab516b7103"
)
GENESIS_CANDIDATE_SEEDS = {
    "audit_sample_seed": 2400516433143543872,
    "capture_draw_seed": 13295599353326517286,
    "renderer_seed": 1919497406732620603,
    "scene_seed": 6476986474311257924,
    "trajectory_seed": 698958362770305116,
}

_ORIGINAL_VALIDATE_FULL_PLAN = execution.validate_full_plan
_ORIGINAL_RECOVERY_CALLABLE = execution.run_locked_test_gt_source_cardinality_recovery


def recovery_bridge_v3_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    full = execution.full_paths(config)
    synthetic_root = (
        full["synthetic"] / "planning/extension_aware_state_chain_recovery_v3"
    )
    docs_root = full["docs"] / "extension_aware_state_chain_recovery_v3"
    synthetic_release = synthetic_root / "release_v3"
    docs_release = docs_root / "release_v3"
    return {
        "synthetic_root": synthetic_root,
        "docs_root": docs_root,
        "synthetic_release": synthetic_release,
        "docs_release": docs_release,
        "authorization": synthetic_release / "pass108_manager_authorization_receipt.json",
        "bridge": synthetic_release / "state_chain_recovery_bridge_v3.json",
        "lock": synthetic_release / "state_chain_recovery_bridge_lock_v3.json",
        "release": synthetic_release / "state_chain_recovery_bridge_release_v3.json",
        "validation_receipt": synthetic_release / "pass108_validation_receipt.json",
        "executions": synthetic_root / "executions",
        "docs_executions": docs_root / "executions",
    }


def _required_release_files() -> list[str]:
    return [
        "pass108_manager_authorization_receipt.json",
        "pass108_validation_receipt.json",
        "state_chain_recovery_bridge_lock_v3.json",
        "state_chain_recovery_bridge_release_v3.json",
        "state_chain_recovery_bridge_v3.json",
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


def _access_guard() -> dict[str, Any]:
    return {
        "candidate_acceptance_or_pair_publication": False,
        "rendering_calls": 0,
        "model_loaded": False,
        "inference_calls": 0,
        "prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "registered_targets_used": False,
        "external_services_modified": False,
        "outcome_inputs": [],
    }


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
        "recovery_v1": PROJECT_ROOT
        / "scripts/run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v1.py",
        "recovery_v1_test": PROJECT_ROOT
        / "tests/test_run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v1.py",
        "recovery_v2": PROJECT_ROOT
        / "scripts/run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v2.py",
        "recovery_v2_test": PROJECT_ROOT
        / "tests/test_run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v2.py",
        "bridge_v3": PROJECT_ROOT / AUTHORIZED_SOURCE_PATH,
        "bridge_v3_test": PROJECT_ROOT / AUTHORIZED_TEST_PATH,
    }


def _recovery_lock_path(config: Mapping[str, Any]) -> Path:
    return (
        execution.roster_extension_paths(config)["execution_locks"]
        / "locked_test_recovery_execution_lock_extension_v1.json"
    )


def _pass107_receipt_path(config: Mapping[str, Any]) -> Path:
    return (
        execution.full_paths(config)["docs"]
        / "locked_test_render_batches/pass102_state_chain_execution/"
        "pass107_fail_closed_receipt.json"
    )


def _recovery_v2_execution_paths(config: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    paths = recovery_v2.recovery_bridge_v2_paths(config)
    root = paths["executions"] / RECOVERY_V2_EXECUTION_ID
    return (
        root / "recovery_bridge_intent.json",
        root / "recovery_bridge_terminal_receipt.json",
        paths["docs_executions"] / f"{RECOVERY_V2_EXECUTION_ID}.json",
    )


def _verify_immutable_parents(
    config_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = config_path.expanduser().resolve()
    if resolved != DEFAULT_CONFIG.expanduser().resolve():
        raise execution.ContractError("Noncanonical V3 state-chain recovery config")
    _require_file_sha256(resolved, RUNTIME_CONFIG_SHA256, "runtime config")
    expected_sources = {
        "legacy_execution": LEGACY_EXECUTION_SCRIPT_SHA256,
        "legacy_test": LEGACY_EXECUTION_TEST_SHA256,
        "validator": VALIDATOR_SCRIPT_SHA256,
        "validator_test": VALIDATOR_TEST_SHA256,
        "adapter": ADAPTER_SCRIPT_SHA256,
        "adapter_test": ADAPTER_TEST_SHA256,
        "state_chain": STATE_CHAIN_SCRIPT_SHA256,
        "state_chain_test": STATE_CHAIN_TEST_SHA256,
        "recovery_v1": RECOVERY_V1_SCRIPT_SHA256,
        "recovery_v1_test": RECOVERY_V1_TEST_SHA256,
        "recovery_v2": RECOVERY_V2_SCRIPT_SHA256,
        "recovery_v2_test": RECOVERY_V2_TEST_SHA256,
    }
    sources = _source_paths()
    for name, digest in expected_sources.items():
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

    config, v2_parent, v2_release = recovery_v2._validate_static_release_identity(
        resolved
    )
    if v2_release.get("release_identity_sha256") != RECOVERY_V2_RELEASE_IDENTITY_SHA256:
        raise execution.ContractError("Recovery V2 release identity changed")
    v2_paths = recovery_v2.recovery_bridge_v2_paths(config)
    _require_file_sha256(
        v2_paths["release"], RECOVERY_V2_RELEASE_FILE_SHA256, "Recovery V2 release"
    )
    v2_intent, v2_terminal, v2_docs_terminal = _recovery_v2_execution_paths(config)
    _require_file_sha256(v2_intent, RECOVERY_V2_INTENT_SHA256, "Recovery V2 intent")
    _require_file_sha256(
        v2_terminal, RECOVERY_V2_TERMINAL_SHA256, "Recovery V2 terminal"
    )
    _require_file_sha256(
        v2_docs_terminal, RECOVERY_V2_TERMINAL_SHA256, "Recovery V2 docs terminal"
    )
    v2_terminal_payload = execution.load_json(v2_terminal)
    if (
        v2_terminal_payload.get("status")
        != "PASS_EXACT_ZERO_SOURCE_WEED_REJECTION_V2_SYNTHETIC_ONLY"
        or v2_terminal_payload.get("original_validator_restored") is not True
        or v2_terminal_payload.get("access_guard") != _access_guard()
    ):
        raise execution.ContractError("Recovery V2 terminal authority changed")

    state_static = v2_parent["state_chain_static"]
    state_release = execution.load_json(state_static["paths"]["release_file"])
    _require_file_sha256(
        state_static["paths"]["release_file"],
        STATE_CHAIN_RELEASE_FILE_SHA256,
        "state-chain release",
    )
    if state_release.get("release_identity_sha256") != STATE_CHAIN_RELEASE_IDENTITY_SHA256:
        raise execution.ContractError("State-chain release identity changed")

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
        or lock.get("registered_targets_allowed") is not False
    ):
        raise execution.ContractError("Recovery lock authority changed")
    _require_file_sha256(
        _pass107_receipt_path(config), PASS107_RECEIPT_SHA256, "Pass107 receipt"
    )

    parents = {
        **copy.deepcopy(v2_parent["parents"]),
        "state_chain_script_sha256": STATE_CHAIN_SCRIPT_SHA256,
        "state_chain_test_sha256": STATE_CHAIN_TEST_SHA256,
        "state_chain_release_file_sha256": STATE_CHAIN_RELEASE_FILE_SHA256,
        "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
        "state_chain_implementation_sha256": STATE_CHAIN_IMPLEMENTATION_SHA256,
        "locked_test_recovery_function_source_sha256": RECOVERY_FUNCTION_SOURCE_SHA256,
        "locked_test_recovery_implementation_sha256": RECOVERY_IMPLEMENTATION_SHA256,
        "locked_test_recovery_lock_sha256": RECOVERY_LOCK_SHA256,
        "recovery_v1_script_sha256": RECOVERY_V1_SCRIPT_SHA256,
        "recovery_v1_test_sha256": RECOVERY_V1_TEST_SHA256,
        "recovery_v1_release_file_sha256": RECOVERY_V1_RELEASE_FILE_SHA256,
        "recovery_v1_release_identity_sha256": RECOVERY_V1_RELEASE_IDENTITY_SHA256,
        "recovery_v1_terminal_receipt_sha256": RECOVERY_V1_TERMINAL_SHA256,
        "recovery_v2_script_sha256": RECOVERY_V2_SCRIPT_SHA256,
        "recovery_v2_test_sha256": RECOVERY_V2_TEST_SHA256,
        "recovery_v2_release_file_sha256": RECOVERY_V2_RELEASE_FILE_SHA256,
        "recovery_v2_release_identity_sha256": RECOVERY_V2_RELEASE_IDENTITY_SHA256,
        "recovery_v2_intent_sha256": RECOVERY_V2_INTENT_SHA256,
        "recovery_v2_terminal_receipt_sha256": RECOVERY_V2_TERMINAL_SHA256,
        "pass107_receipt_sha256": PASS107_RECEIPT_SHA256,
    }
    return config, {
        "parents": parents,
        "roster": v2_parent["roster"],
        "state_chain_root": v2_parent["state_chain_root"],
        "state_chain_static": state_static,
        "recovery_v2_release": v2_release,
    }


def _ledger_prefix_sha256(path: Path, row_count: int) -> str:
    lines = path.read_bytes().splitlines(keepends=True)
    if len(lines) < row_count:
        raise execution.ContractError("Candidate rejection ledger was truncated")
    return hashlib.sha256(b"".join(lines[:row_count])).hexdigest()


def _pair_roster_row(
    roster_rows: Sequence[Mapping[str, Any]], pair_id: str
) -> Mapping[str, Any]:
    matches = [row for row in roster_rows if str(row.get("pair_id")) == pair_id]
    if len(matches) != 1:
        raise execution.ContractError("Active recovery pair escaped the sealed roster")
    row = matches[0]
    if row.get("protocol_split") != "locked_test" or len(row.get("candidates", [])) != 32:
        raise execution.ContractError("Active recovery pair-slot binding changed")
    return row


def _candidate_by_index(
    config: Mapping[str, Any], roster_row: Mapping[str, Any], candidate_index: int
) -> Mapping[str, Any]:
    candidates = roster_row.get("candidates", [])
    if (
        not isinstance(candidate_index, int)
        or isinstance(candidate_index, bool)
        or candidate_index < 0
        or candidate_index >= len(candidates)
    ):
        raise execution.ContractError("V3 recovery candidate escaped frozen roster")
    candidate = candidates[candidate_index]
    if (
        candidate.get("candidate_index") != candidate_index
        or candidate.get("model_outcome_inputs") != []
    ):
        raise execution.ContractError("V3 recovery candidate roster binding changed")
    source = execution.full_candidate_source_path(config, roster_row, candidate)
    if (
        not source.is_file()
        or execution.sha256_file(source)
        != candidate.get("source_template", {}).get("sha256")
    ):
        raise execution.ContractError("V3 candidate source-template bytes changed")
    return candidate


def _canonical_candidate(
    config: Mapping[str, Any], full_root: Path, roster_row: Mapping[str, Any]
) -> Mapping[str, Any]:
    candidate = execution._next_gt_scout_candidate(full_root, roster_row)
    index = candidate.get("candidate_index")
    if not isinstance(index, int) or isinstance(index, bool):
        raise execution.ContractError("Derived V3 candidate index is invalid")
    sealed = _candidate_by_index(config, roster_row, index)
    if candidate != sealed:
        raise execution.ContractError("Derived V3 candidate is noncanonical")
    return sealed


def _batch_parent(config: Mapping[str, Any]) -> Path:
    return (
        execution.full_paths(config)["synthetic"]
        / "planning/locked_test_render_batches_v1"
    )


def _matching_open_batch(
    config: Mapping[str, Any], pair_id: str
) -> dict[str, Any]:
    parent = _batch_parent(config)
    if not parent.is_dir() or list(parent.glob(".partial-*")):
        raise execution.ContractError("Batch execution root is missing or partial")
    matches: list[dict[str, Any]] = []
    for root in sorted(path for path in parent.iterdir() if path.is_dir()):
        intent_path = root / "batch_intent.json"
        if not intent_path.is_file():
            raise execution.ContractError("Batch execution has no immutable intent")
        intent = execution.load_json(intent_path)
        request = intent.get("request", {})
        if request.get("target_pair_ids") != [pair_id]:
            continue
        if (root / "batch_receipt.json").is_file():
            continue
        if (
            intent.get("batch_id") != root.name
            or intent.get("status")
            != "LOCKED_TEST_RENDER_BATCH_INTENT_PREOUTCOME_SYNTHETIC_ONLY"
            or intent.get("request_identity_sha256") != execution.stable_sha256(request)
            or request.get("max_new_pairs") != 1
            or request.get("model_access_allowed") is not False
            or request.get("prediction_access_allowed") is not False
            or request.get("locked_test_outcome_access_allowed") is not False
            or request.get("render_and_machine_audit_only") is not True
        ):
            raise execution.ContractError("Matching open batch intent changed")
        matches.append(
            {
                "batch_id": root.name,
                "root": root,
                "intent": intent,
                "intent_path": intent_path,
                "intent_sha256": execution.sha256_file(intent_path),
            }
        )
    if len(matches) != 1:
        raise execution.ContractError("Expected exactly one matching open batch")
    return matches[0]


def _recovery_destination(
    config: Mapping[str, Any], pair_id: str, candidate_index: int
) -> Path:
    return (
        execution.full_paths(config)["synthetic"]
        / "planning/locked_test_gt_source_cardinality_recovery_v1/roster"
        / pair_id
        / f"candidate_{candidate_index:02d}"
    )


def _recovery_docs_receipt(
    config: Mapping[str, Any], pair_id: str, candidate_index: int
) -> Path:
    return (
        execution.full_paths(config)["docs"]
        / "gt_scout_v1"
        / f"locked_test_source_cardinality_recovery_{pair_id}_candidate_"
        f"{candidate_index:02d}.json"
    )


def _validate_recovery_artifacts(
    config: Mapping[str, Any],
    roster_row: Mapping[str, Any],
    candidate_index: int,
    batch_id: str,
    batch_intent_sha256: str,
    *,
    require_commit: bool,
) -> dict[str, Any]:
    pair_id = str(roster_row["pair_id"])
    candidate = _candidate_by_index(config, roster_row, candidate_index)
    destination = _recovery_destination(config, pair_id, candidate_index)
    terminal_path = destination / "recovery_terminal_receipt.json"
    decision_path = destination / "decision_receipt.json"
    if not terminal_path.is_file() or not decision_path.is_file():
        raise execution.ContractError("V3 recovery evidence is incomplete")
    terminal = execution.load_json(terminal_path)
    decision = execution.load_json(decision_path)
    audit = terminal.get("source_cardinality_audit", {})
    valid = (
        terminal.get("contract")
        == execution.LOCKED_TEST_GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT
        and terminal.get("status")
        == "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY"
        and terminal.get("pair_id") == pair_id
        and terminal.get("protocol_split") == "locked_test"
        and terminal.get("pair_slot_identity_sha256")
        == roster_row["pair_slot_identity_sha256"]
        and terminal.get("candidate_index") == candidate_index
        and terminal.get("candidate_identity_sha256")
        == candidate["candidate_identity_sha256"]
        and terminal.get("candidate_seeds") == candidate["seeds"]
        and terminal.get("source_template") == candidate["source_template"]
        and terminal.get("source_template_sha256_exact") is True
        and terminal.get("batch_id") == batch_id
        and terminal.get("batch_intent_sha256") == batch_intent_sha256
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
        and audit.get("locked_botanical_validator_failure")
        == "Too few source weed tracks: 0"
        and audit.get("source_weed_track_count") == 0
        and audit.get("rejection_reason") == "eligibility:source_weed_track_present"
        and audit.get("model_or_outcome_inputs_used") is False
        and decision.get("contract") == execution.GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT
        and decision.get("pair_id") == pair_id
        and decision.get("rejectable_by_scout") is True
        and decision.get("rejection_reasons")
        == ["eligibility:source_weed_track_present"]
        and decision.get("source_cardinality_checks")
        == {"source_crop_track_present": True, "source_weed_track_present": False}
        and decision.get("full_render_still_required_for_acceptance") is True
        and decision.get("recovery_has_acceptance_authority") is False
        and decision.get("model_or_outcome_inputs_used") is False
        and decision.get("registered_targets_used") is False
        and decision.get("locked_test_prediction_accessed") is False
        and decision.get("locked_test_outcome_accessed") is False
    )
    if not valid:
        raise execution.ContractError("V3 exact recovery evidence changed")
    if (destination / "source_scene").exists():
        raise execution.ContractError("V3 recovery retained a bulk source scene")
    if any(
        "prediction" in row["path"].lower()
        for row in execution.artifact_inventory(destination)
    ):
        raise execution.ContractError("Prediction output exists in V3 recovery evidence")

    commit_path = destination / "ledger_commit_receipt.json"
    commit = execution.load_json(commit_path) if commit_path.is_file() else None
    if require_commit:
        if not isinstance(commit, dict):
            raise execution.ContractError("V3 ledger commit receipt is missing")
        if (
            commit.get("pair_id") != pair_id
            or commit.get("candidate_index") != candidate_index
            or commit.get("candidate_identity_sha256")
            != candidate["candidate_identity_sha256"]
            or commit.get("model_or_outcome_inputs_used") is not False
            or commit.get("idempotent") is not True
        ):
            raise execution.ContractError("V3 ledger commit receipt changed")
        _require_file_sha256(
            _recovery_docs_receipt(config, pair_id, candidate_index),
            execution.sha256_file(terminal_path),
            "V3 legacy recovery docs receipt",
        )
    elif commit is not None and (
        commit.get("pair_id") != pair_id
        or commit.get("candidate_index") != candidate_index
        or commit.get("candidate_identity_sha256")
        != candidate["candidate_identity_sha256"]
    ):
        raise execution.ContractError("Uncommitted V3 recovery receipt changed")
    return {
        "candidate_index": candidate_index,
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "source_template_sha256": candidate["source_template"]["sha256"],
        "recovery_terminal_receipt_sha256": execution.sha256_file(terminal_path),
        "decision_receipt_sha256": execution.sha256_file(decision_path),
        "ledger_commit_receipt_sha256": (
            execution.sha256_file(commit_path) if commit_path.is_file() else None
        ),
    }


def _validate_rejection_row(
    row: Mapping[str, Any],
    roster_row: Mapping[str, Any],
    candidate: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> None:
    valid = (
        row.get("status") == "REJECTED_FULL_PAIR_CANDIDATE_PREOUTCOME_SYNTHETIC_ONLY"
        and row.get("pair_id") == roster_row["pair_id"]
        and row.get("candidate_index") == candidate["candidate_index"]
        and row.get("candidate_identity_sha256")
        == candidate["candidate_identity_sha256"]
        and row.get("reason_type") == "GtScoutCandidateRejected"
        and row.get("reason") == "eligibility:source_weed_track_present"
        and row.get("gt_scout_terminal_receipt_sha256")
        == evidence["recovery_terminal_receipt_sha256"]
        and row.get("gt_scout_decision_receipt_sha256")
        == evidence["decision_receipt_sha256"]
        and row.get("model_or_outcome_inputs_used") is False
        and row.get("bulk_payload_retained") is False
    )
    if not valid:
        raise execution.ContractError("V3 canonical rejection ledger row changed")


def _execution_identity(request: Mapping[str, Any]) -> tuple[str, str]:
    identity = execution.stable_sha256(request)
    pair_id = str(request.get("pair_id", ""))
    index = request.get("candidate_index")
    if (
        execution.SAFE_ID_RE.fullmatch(pair_id) is None
        or not isinstance(index, int)
        or isinstance(index, bool)
    ):
        raise execution.ContractError("V3 recovery request target identity is invalid")
    execution_id = f"state_chain_recovery_v3_{pair_id}_candidate_{index:02d}_{identity[:16]}"
    if execution.SAFE_ID_RE.fullmatch(execution_id) is None:
        raise execution.ContractError("Unsafe V3 recovery execution identity")
    return execution_id, identity


def _scan_v3_journal(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    paths = recovery_bridge_v3_paths(config)
    parent = paths["executions"]
    docs_parent = paths["docs_executions"]
    if not parent.exists():
        if docs_parent.exists() and any(docs_parent.iterdir()):
            raise execution.ContractError("V3 docs journal exists without source")
        return []
    if list(parent.glob(".partial-*")):
        raise execution.ContractError("Partial V3 recovery intent exists")
    if docs_parent.exists() and list(docs_parent.glob(".partial-*")):
        raise execution.ContractError("Partial V3 docs terminal exists")
    records: list[dict[str, Any]] = []
    for root in sorted(path for path in parent.iterdir() if path.is_dir()):
        observed_files = sorted(
            path.name for path in root.iterdir() if path.is_file()
        )
        if observed_files not in (
            ["recovery_bridge_intent.json"],
            ["recovery_bridge_intent.json", "recovery_bridge_terminal_receipt.json"],
        ):
            raise execution.ContractError("V3 recovery execution file set changed")
        intent_path = root / "recovery_bridge_intent.json"
        intent = execution.load_json(intent_path)
        request = intent.get("request", {})
        expected_id, request_identity = _execution_identity(request)
        if (
            root.name != expected_id
            or intent.get("schema_version") != 1
            or intent.get("contract") != INTENT_CONTRACT
            or intent.get("status")
            != "CANONICAL_ACTIVE_PAIR_RECOVERY_V3_INTENT_SYNTHETIC_ONLY"
            or intent.get("execution_id") != root.name
            or intent.get("request_identity_sha256") != request_identity
            or intent.get("request") != request
            or intent.get("access_guard") != _access_guard()
            or intent.get("claim_boundary") != _claim_boundary(config)
        ):
            raise execution.ContractError("V3 recovery intent binding changed")
        terminal_path = root / "recovery_bridge_terminal_receipt.json"
        docs_terminal = docs_parent / f"{root.name}.json"
        terminal = execution.load_json(terminal_path) if terminal_path.is_file() else None
        if terminal is not None:
            if (
                terminal.get("schema_version") != 1
                or terminal.get("contract") != TERMINAL_RECEIPT_CONTRACT
                or terminal.get("status")
                != "PASS_EXACT_ZERO_SOURCE_WEED_REJECTION_V3_SYNTHETIC_ONLY"
                or terminal.get("execution_id") != root.name
                or terminal.get("request_identity_sha256") != request_identity
                or terminal.get("request") != request
                or terminal.get("recovery_bridge_intent_sha256")
                != execution.sha256_file(intent_path)
                or terminal.get("original_validator_restored") is not True
                or terminal.get("access_guard") != _access_guard()
                or terminal.get("claim_boundary") != _claim_boundary(config)
            ):
                raise execution.ContractError("V3 recovery terminal binding changed")
            _require_file_sha256(
                docs_terminal,
                execution.sha256_file(terminal_path),
                "V3 docs terminal receipt",
            )
        elif docs_terminal.exists():
            raise execution.ContractError("V3 docs terminal exists before source terminal")
        records.append(
            {
                "sequence": request.get("journal_sequence"),
                "execution_id": root.name,
                "root": root,
                "intent": intent,
                "intent_path": intent_path,
                "request": request,
                "request_identity_sha256": request_identity,
                "terminal": terminal,
                "terminal_path": terminal_path,
                "terminal_present": terminal is not None,
            }
        )
    records.sort(key=lambda record: int(record["sequence"] or -1))
    if [record["sequence"] for record in records] != list(range(1, len(records) + 1)):
        raise execution.ContractError("V3 journal sequence skipped or reordered")
    open_records = [record for record in records if not record["terminal_present"]]
    if len(open_records) > 1 or (open_records and open_records[0] is not records[-1]):
        raise execution.ContractError("Parallel or reordered V3 recovery intent exists")
    previous_terminal_sha: str | None = None
    for record in records:
        if record["request"].get("previous_terminal_receipt_sha256") != previous_terminal_sha:
            raise execution.ContractError("V3 journal predecessor changed")
        if record["terminal_present"]:
            previous_terminal_sha = execution.sha256_file(record["terminal_path"])
    return records


def _head_ancestry(
    parent: Mapping[str, Any], config: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Mapping[str, Any]]]:
    static = parent["state_chain_static"]
    chain = state_chain._validate_commit_chain(
        parent["state_chain_root"],
        static["commits"],
        parent["roster"]["combined"],
    )
    heads = {commit["head"]["head_identity_sha256"]: commit for commit in static["commits"]}
    genesis = heads.get(GENESIS_HEAD_IDENTITY_SHA256)
    if (
        genesis is None
        or genesis["head"].get("sequence") != GENESIS_COMPLETED_PAIR_COUNT
        or genesis["head"].get("result_state_sha256") != GENESIS_STATE_SHA256
    ):
        raise execution.ContractError("V3 state-chain genesis ancestry changed")
    state_path, _, ledger_path = state_chain._state_paths(config)
    if _ledger_prefix_sha256(ledger_path, GENESIS_LEDGER_ROW_COUNT) != GENESIS_LEDGER_SHA256:
        raise execution.ContractError("V3 genesis ledger prefix changed")
    if not state_path.is_file():
        raise execution.ContractError("Live render state is missing")
    return chain, heads


def _validate_v3_journal(
    config: Mapping[str, Any],
    parent: Mapping[str, Any],
    *,
    release_identity: str | None,
    allow_open_execution_id: str | None,
) -> list[dict[str, Any]]:
    records = _scan_v3_journal(config)
    open_records = [record for record in records if not record["terminal_present"]]
    if allow_open_execution_id is None:
        if open_records:
            raise execution.ContractError("Open V3 recovery intent is not authorized")
    elif (
        len(open_records) != 1
        or open_records[0]["execution_id"] != allow_open_execution_id
    ):
        raise execution.ContractError("Wrong V3 recovery intent is open")

    _, heads = _head_ancestry(parent, config)
    state_path, _, ledger_path = state_chain._state_paths(config)
    ledger = execution.read_jsonl(ledger_path)
    roster_rows = execution.full_roster_rows(config)
    for record in records:
        request = record["request"]
        pair_id = str(request.get("pair_id", ""))
        candidate_index = request.get("candidate_index")
        if not isinstance(candidate_index, int) or isinstance(candidate_index, bool):
            raise execution.ContractError("V3 journal candidate index changed")
        roster_row = _pair_roster_row(roster_rows, pair_id)
        candidate = _candidate_by_index(config, roster_row, candidate_index)
        head = heads.get(request.get("predecessor_head_identity_sha256"))
        state_intent_path = (
            state_chain.state_chain_paths(config)["executions"]
            / str(request.get("state_chain_execution_id", ""))
            / "state_chain_intent.json"
        )
        batch_root = _batch_parent(config) / str(request.get("underlying_batch_id", ""))
        batch_intent_path = batch_root / "batch_intent.json"
        if (
            request.get("contract") != CONTRACT
            or request.get("operation") != "recover-current-zero-weed"
            or request.get("caller_selected_target") is not False
            or request.get("state_chain_release_identity_sha256")
            != STATE_CHAIN_RELEASE_IDENTITY_SHA256
            or request.get("recovery_v1_release_identity_sha256")
            != RECOVERY_V1_RELEASE_IDENTITY_SHA256
            or request.get("recovery_v2_release_identity_sha256")
            != RECOVERY_V2_RELEASE_IDENTITY_SHA256
            or (
                release_identity is not None
                and request.get("recovery_bridge_v3_release_identity_sha256")
                != release_identity
            )
            or request.get("recovery_lock_sha256") != RECOVERY_LOCK_SHA256
            or request.get("pair_slot_identity_sha256")
            != roster_row["pair_slot_identity_sha256"]
            or request.get("candidate_identity_sha256")
            != candidate["candidate_identity_sha256"]
            or request.get("candidate_seeds") != candidate["seeds"]
            or request.get("source_template") != candidate["source_template"]
            or request.get("max_new_pairs") != 1
            or request.get("rejection_authority")
            != "exact_locked_validator_zero_source_weed_failure_only"
            or request.get("acceptance_authority") != "none"
            or request.get("render_or_state_transition_authority") is not False
            or request.get("model_prediction_outcome_target_or_external_access_allowed")
            is not False
            or head is None
            or head["head"].get("result_state_sha256")
            != request.get("predecessor_state_sha256")
            or not state_intent_path.is_file()
            or execution.sha256_file(state_intent_path)
            != request.get("state_chain_intent_sha256")
            or not batch_intent_path.is_file()
            or execution.sha256_file(batch_intent_path)
            != request.get("underlying_batch_intent_sha256")
        ):
            raise execution.ContractError("V3 journal immutable request binding changed")
        state_intent = execution.load_json(state_intent_path)
        batch_intent = execution.load_json(batch_intent_path)
        if (
            state_intent.get("execution_id") != request["state_chain_execution_id"]
            or state_intent.get("request", {}).get("target_pair_id") != pair_id
            or state_intent.get("request", {}).get("max_new_pairs") != 1
            or batch_intent.get("batch_id") != request["underlying_batch_id"]
            or batch_intent.get("request", {}).get("target_pair_ids") != [pair_id]
            or batch_intent.get("request", {}).get("max_new_pairs") != 1
        ):
            raise execution.ContractError("V3 journal parent intent binding changed")
        before_count = request.get("predecessor_ledger_row_count")
        if (
            not isinstance(before_count, int)
            or isinstance(before_count, bool)
            or before_count < GENESIS_LEDGER_ROW_COUNT
            or _ledger_prefix_sha256(ledger_path, before_count)
            != request.get("predecessor_ledger_sha256")
        ):
            raise execution.ContractError("V3 journal ledger predecessor changed")

        if record["terminal_present"]:
            terminal = record["terminal"]
            evidence = _validate_recovery_artifacts(
                config,
                roster_row,
                candidate_index,
                request["underlying_batch_id"],
                request["underlying_batch_intent_sha256"],
                require_commit=True,
            )
            if len(ledger) <= before_count:
                raise execution.ContractError("V3 terminal exists without ledger append")
            _validate_rejection_row(ledger[before_count], roster_row, candidate, evidence)
            after_sha = _ledger_prefix_sha256(ledger_path, before_count + 1)
            boundary = terminal.get("boundary", {})
            legacy = terminal.get("legacy_recovery", {})
            if (
                boundary.get("render_state_sha256_before")
                != request["predecessor_state_sha256"]
                or boundary.get("render_state_sha256_after")
                != request["predecessor_state_sha256"]
                or boundary.get("chain_head_identity_sha256_before")
                != request["predecessor_head_identity_sha256"]
                or boundary.get("chain_head_identity_sha256_after")
                != request["predecessor_head_identity_sha256"]
                or boundary.get("candidate_rejection_ledger_sha256_before")
                != request["predecessor_ledger_sha256"]
                or boundary.get("candidate_rejection_ledger_sha256_after") != after_sha
                or boundary.get("candidate_rejection_ledger_row_count_before")
                != before_count
                or boundary.get("candidate_rejection_ledger_row_count_after")
                != before_count + 1
                or legacy.get("pair_id") != pair_id
                or legacy.get("candidate_index") != candidate_index
                or legacy.get("batch_id") != request["underlying_batch_id"]
                or legacy.get("recovery_terminal_receipt_sha256")
                != evidence["recovery_terminal_receipt_sha256"]
                or legacy.get("decision_receipt_sha256")
                != evidence["decision_receipt_sha256"]
                or legacy.get("ledger_commit_receipt_sha256")
                != evidence["ledger_commit_receipt_sha256"]
            ):
                raise execution.ContractError("V3 terminal evidence chain changed")
        elif len(ledger) not in {before_count, before_count + 1}:
            raise execution.ContractError("Open V3 ledger advanced by a noncanonical amount")
        elif len(ledger) == before_count + 1:
            evidence = _validate_recovery_artifacts(
                config,
                roster_row,
                candidate_index,
                request["underlying_batch_id"],
                request["underlying_batch_intent_sha256"],
                require_commit=True,
            )
            _validate_rejection_row(ledger[before_count], roster_row, candidate, evidence)
    return records


def _validate_active_boundary(
    config_path: Path,
    *,
    release_identity: str | None = None,
    allow_open_v3_execution_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config, parent = _verify_immutable_parents(config_path)
    chain_paths = state_chain.state_chain_paths(config)
    active = state_chain._open_intents(chain_paths)
    if len(active) != 1:
        raise execution.ContractError("Expected exactly one active state-chain execution")
    state_intent = active[0]["intent"]
    state_execution_id = str(state_intent.get("execution_id", ""))
    state_execution_root = active[0]["root"]
    validation = state_chain.validate_state_chain_release(
        config_path, allow_open_execution_id=state_execution_id
    )
    if (
        validation.get("status")
        != "PASS_EXTENSION_AWARE_MONOTONIC_STATE_CHAIN_VALIDATION_SYNTHETIC_ONLY"
        or validation.get("state_chain_release_identity_sha256")
        != STATE_CHAIN_RELEASE_IDENTITY_SHA256
        or validation.get("active_execution_id") != state_execution_id
        or validation.get("model_loaded") is not False
        or validation.get("inference_calls") != 0
        or validation.get("prediction_accessed") is not False
        or validation.get("locked_test_outcome_accessed") is not False
        or validation.get("registered_targets_used") is not False
        or validation.get("external_services_modified") is not False
        or validation.get("outcome_inputs") != []
    ):
        raise execution.ContractError("Active V3 state-chain validation changed")

    chain, _ = _head_ancestry(parent, config)
    state_path, docs_state_path, ledger_path = state_chain._state_paths(config)
    if (
        validation.get("chain_head_identity_sha256") != chain["head_identity_sha256"]
        or validation.get("render_state_sha256") != chain["head_state_sha256"]
        or execution.sha256_file(state_path) != chain["head_state_sha256"]
        or execution.sha256_file(docs_state_path) != chain["head_state_sha256"]
        or validation.get("completed_pair_count") != chain["head_sequence"]
    ):
        raise execution.ContractError("Recovery attempted outside the committed chain head")
    state = execution.load_json(state_path)
    pair_id = str(validation.get("first_pending_pair_id", ""))
    if (
        not pair_id.startswith("locked_test_")
        or state.get("pending_pair_ids", [None])[0] != pair_id
        or state.get("completed_pair_count") != chain["head_sequence"]
        or state.get("model_outputs_present") is not False
        or state.get("interrupted_staging_directories") != []
    ):
        raise execution.ContractError("Canonical active-pair state boundary changed")
    request = state_intent.get("request", {})
    state_intent_path = state_execution_root / "state_chain_intent.json"
    if (
        request.get("target_pair_id") != pair_id
        or request.get("max_new_pairs") != 1
        or request.get("predecessor_head_identity_sha256")
        != chain["head_identity_sha256"]
        or request.get("predecessor_state_sha256") != chain["head_state_sha256"]
        or request.get("state_chain_release_identity_sha256")
        != STATE_CHAIN_RELEASE_IDENTITY_SHA256
        or (state_execution_root / "state_chain_terminal_receipt.json").exists()
    ):
        raise execution.ContractError("Active state-chain intent is noncanonical")
    batch = _matching_open_batch(config, pair_id)
    full = execution.full_paths(config)
    pair_root = full["synthetic"] / "pairs/locked_test" / pair_id
    if pair_root.exists():
        raise execution.ContractError("Active recovery pair is already published")

    records = _validate_v3_journal(
        config,
        parent,
        release_identity=release_identity,
        allow_open_execution_id=allow_open_v3_execution_id,
    )
    roster_rows = execution.full_roster_rows(config)
    roster_row = _pair_roster_row(roster_rows, pair_id)
    candidate = _canonical_candidate(config, full["synthetic"], roster_row)
    recovery_root = (
        full["synthetic"] / "planning/locked_test_gt_source_cardinality_recovery_v1"
    )
    if recovery_root.exists() and list(
        recovery_root.glob(f".partial-{pair_id}-candidate-*-*")
    ):
        raise execution.ContractError("Partial canonical candidate recovery staging exists")
    boundary = {
        "completed_pair_count": validation["completed_pair_count"],
        "pending_pair_count": validation["pending_pair_count"],
        "first_pending_pair_id": pair_id,
        "render_state_sha256": execution.sha256_file(state_path),
        "chain_head_identity_sha256": chain["head_identity_sha256"],
        "candidate_rejection_ledger_prefix_sha256": GENESIS_LEDGER_SHA256,
        "candidate_rejection_ledger_sha256": execution.sha256_file(ledger_path),
        "candidate_rejection_ledger_row_count": len(execution.read_jsonl(ledger_path)),
        "state_chain_execution_id": state_execution_id,
        "state_chain_intent_sha256": execution.sha256_file(state_intent_path),
        "underlying_batch_id": batch["batch_id"],
        "underlying_batch_intent_sha256": batch["intent_sha256"],
        "pair_id": pair_id,
        "pair_slot_identity_sha256": roster_row["pair_slot_identity_sha256"],
        "next_candidate_index": candidate["candidate_index"],
        "next_candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "next_candidate_seeds": copy.deepcopy(candidate["seeds"]),
        "next_source_template": copy.deepcopy(candidate["source_template"]),
        "v3_execution_count": len(records),
        "open_v3_execution_id": allow_open_v3_execution_id,
        "model_loaded": False,
        "inference_calls": 0,
        "prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "registered_targets_used": False,
        "external_services_modified": False,
        "outcome_inputs": [],
    }
    return config, parent, boundary


def _pinned_genesis() -> dict[str, Any]:
    return {
        "completed_pair_count": GENESIS_COMPLETED_PAIR_COUNT,
        "pending_pair_count": GENESIS_PENDING_PAIR_COUNT,
        "render_state_sha256": GENESIS_STATE_SHA256,
        "chain_head_identity_sha256": GENESIS_HEAD_IDENTITY_SHA256,
        "candidate_rejection_ledger_sha256": GENESIS_LEDGER_SHA256,
        "candidate_rejection_ledger_row_count": GENESIS_LEDGER_ROW_COUNT,
        "first_pending_pair_id": GENESIS_PAIR_ID,
        "pair_slot_identity_sha256": GENESIS_PAIR_SLOT_IDENTITY_SHA256,
        "state_chain_execution_id": GENESIS_STATE_CHAIN_EXECUTION_ID,
        "state_chain_intent_sha256": GENESIS_STATE_CHAIN_INTENT_SHA256,
        "underlying_batch_id": GENESIS_BATCH_ID,
        "underlying_batch_intent_sha256": GENESIS_BATCH_INTENT_SHA256,
        "next_candidate_index": GENESIS_CANDIDATE_INDEX,
        "next_candidate_identity_sha256": GENESIS_CANDIDATE_IDENTITY_SHA256,
        "next_candidate_seeds": copy.deepcopy(GENESIS_CANDIDATE_SEEDS),
        "next_source_template_sha256": GENESIS_SOURCE_TEMPLATE_SHA256,
        "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
        "recovery_v1_release_identity_sha256": RECOVERY_V1_RELEASE_IDENTITY_SHA256,
        "recovery_v2_release_identity_sha256": RECOVERY_V2_RELEASE_IDENTITY_SHA256,
        "recovery_lock_sha256": RECOVERY_LOCK_SHA256,
    }


def _assert_pass108_initial_boundary(boundary: Mapping[str, Any]) -> None:
    expected = _pinned_genesis()
    observed = {
        "completed_pair_count": boundary.get("completed_pair_count"),
        "pending_pair_count": boundary.get("pending_pair_count"),
        "render_state_sha256": boundary.get("render_state_sha256"),
        "chain_head_identity_sha256": boundary.get("chain_head_identity_sha256"),
        "candidate_rejection_ledger_sha256": boundary.get(
            "candidate_rejection_ledger_sha256"
        ),
        "candidate_rejection_ledger_row_count": boundary.get(
            "candidate_rejection_ledger_row_count"
        ),
        "first_pending_pair_id": boundary.get("first_pending_pair_id"),
        "pair_slot_identity_sha256": boundary.get("pair_slot_identity_sha256"),
        "state_chain_execution_id": boundary.get("state_chain_execution_id"),
        "state_chain_intent_sha256": boundary.get("state_chain_intent_sha256"),
        "underlying_batch_id": boundary.get("underlying_batch_id"),
        "underlying_batch_intent_sha256": boundary.get(
            "underlying_batch_intent_sha256"
        ),
        "next_candidate_index": boundary.get("next_candidate_index"),
        "next_candidate_identity_sha256": boundary.get(
            "next_candidate_identity_sha256"
        ),
        "next_candidate_seeds": boundary.get("next_candidate_seeds"),
        "next_source_template_sha256": boundary.get("next_source_template", {}).get(
            "sha256"
        ),
        "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
        "recovery_v1_release_identity_sha256": RECOVERY_V1_RELEASE_IDENTITY_SHA256,
        "recovery_v2_release_identity_sha256": RECOVERY_V2_RELEASE_IDENTITY_SHA256,
        "recovery_lock_sha256": RECOVERY_LOCK_SHA256,
    }
    if observed != expected or boundary.get("v3_execution_count") != 0:
        raise execution.ContractError("Pass108 V3 genesis boundary changed")


def _authorization_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": AUTHORIZATION_CONTRACT,
        "status": "AUTHORIZED_CANONICAL_ACTIVE_PAIR_RECOVERY_V3_SYNTHETIC_ONLY",
        "manager_session_id": MANAGER_SESSION_ID,
        "manager_handoff_event_id": MANAGER_HANDOFF_EVENT_ID,
        "owner_session_id": OWNER_SESSION_ID,
        "run_id": RUN_ID,
        "portfolio_id": PORTFOLIO_ID,
        "portfolio_lane": PORTFOLIO_LANE,
        "manager_observed_portfolio_revision": PORTFOLIO_REVISION,
        "pass108_event_id": PASS108_EVENT_ID,
        "authorized_top_level_source_paths": [
            AUTHORIZED_SOURCE_PATH,
            AUTHORIZED_TEST_PATH,
        ],
        "operation": "recover-current-zero-weed",
        "caller_selected_pair_batch_execution_or_candidate_allowed": False,
        "canonical_derivation": {
            "sole_open_state_chain_execution": True,
            "current_first_pending_locked_test_pair": True,
            "exactly_one_matching_open_batch": True,
            "max_new_pairs": 1,
            "lowest_unattempted_frozen_roster_candidate": True,
            "derive_with_execution_next_gt_scout_candidate": True,
            "valid_hash_linked_descendant_of_genesis_required": True,
        },
        "authority": {
            "exact_zero_source_weed_rejection_append_allowed": True,
            "candidate_acceptance_allowed": False,
            "candidate_skip_allowed": False,
            "gate_relaxation_allowed": False,
            "render_allowed": False,
            "state_transition_or_pair_publication_allowed": False,
            "model_prediction_outcome_or_registered_target_access_allowed": False,
            "external_service_mutation_allowed": False,
        },
        "pass108_real_recovery_or_gt_or_render_allowed": False,
        "sealed_parent_bytes_rewritten": False,
        "claim_boundary": _claim_boundary(config),
    }


def _bridge_payload(config: Mapping[str, Any], parents: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": BRIDGE_CONTRACT,
        "status": "FROZEN_CANONICAL_ACTIVE_PAIR_RECOVERY_V3_BRIDGE_SYNTHETIC_ONLY",
        "immutable_parents": copy.deepcopy(dict(parents)),
        "genesis": _pinned_genesis(),
        "validation_order": [
            "exact-hash immutable parents and releases",
            "state-chain release and exact genesis ancestry",
            "append-only 142-row genesis ledger prefix",
            "sole open canonical state-chain execution",
            "current first-pending locked-test pair",
            "exactly one matching open max-new-pairs=1 batch",
            "lowest-unattempted candidate from frozen roster",
            "append-only V3 intent/terminal journal",
            "exact zero-source legacy recovery evidence only",
        ],
        "compatibility_patch": {
            "only_callable_replaced": "execution.validate_full_plan",
            "replacement": (
                "state_chain.extension_aware_state_chain_validate_full_plan"
                "(allow_open_execution_id=<derived>)"
            ),
            "unchanged_callable": (
                "execution.run_locked_test_gt_source_cardinality_recovery"
            ),
            "all_execution_callables_snapshotted": True,
            "all_execution_callables_restored_in_finally": True,
        },
        "journal": {
            "immutable_atomic_intent_and_terminal_pairs": True,
            "hash_linked_terminal_predecessor": True,
            "ordinary_frozen_gt_rows_tolerated_only_after_state_chain_validation": True,
            "ordinary_state_chain_commits_tolerated_only_after_ancestry_validation": True,
            "partial_parallel_fork_rollback_or_reorder_allowed": False,
            "idempotent_resume": True,
        },
        "rejection_authority": "exact_locked_validator_zero_source_weed_failure_only",
        "acceptance_authority": "none",
        "claim_boundary": _claim_boundary(config),
    }


def _callable_snapshot() -> dict[str, Callable[..., Any]]:
    return {name: value for name, value in vars(execution).items() if callable(value)}


def _assert_only_validator_changed(
    before: Mapping[str, Callable[..., Any]], replacement: Callable[..., Any]
) -> None:
    after = _callable_snapshot()
    if set(after) != set(before):
        raise execution.ContractError("Execution callable inventory changed")
    for name, value in before.items():
        expected = replacement if name == "validate_full_plan" else value
        if after[name] is not expected:
            raise execution.ContractError(f"Unauthorized callable change: {name}")


def _restore_callable_snapshot(before: Mapping[str, Callable[..., Any]]) -> None:
    for name, value in before.items():
        setattr(execution, name, value)
    after = _callable_snapshot()
    if set(after) != set(before) or any(after[name] is not value for name, value in before.items()):
        raise execution.ContractError("Execution callable snapshot was not restored")


def _call_unchanged_recovery(
    config_path: Path, request: Mapping[str, Any]
) -> dict[str, Any]:
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator was already replaced")
    if execution.run_locked_test_gt_source_cardinality_recovery is not _ORIGINAL_RECOVERY_CALLABLE:
        raise execution.ContractError("Legacy recovery callable changed")
    before = _callable_snapshot()
    replacement = functools.partial(
        state_chain.extension_aware_state_chain_validate_full_plan,
        allow_open_execution_id=request["state_chain_execution_id"],
    )
    unauthorized_error: execution.ContractError | None = None
    execution.validate_full_plan = replacement
    try:
        _assert_only_validator_changed(before, replacement)
        result = execution.run_locked_test_gt_source_cardinality_recovery(
            config_path,
            request["pair_id"],
            candidate_index=int(request["candidate_index"]),
            batch_id=request["underlying_batch_id"],
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


def recovery_bridge_v3_implementation_sha256() -> str:
    functions = (
        _verify_immutable_parents,
        _matching_open_batch,
        _canonical_candidate,
        _validate_recovery_artifacts,
        _scan_v3_journal,
        _validate_v3_journal,
        _head_ancestry,
        _validate_active_boundary,
        _callable_snapshot,
        _assert_only_validator_changed,
        _restore_callable_snapshot,
        _call_unchanged_recovery,
        _publish_or_resume_intent,
        _validate_runtime_phase,
        _validate_terminal_receipt,
        run_current_zero_weed_recovery_v3,
    )
    return execution.stable_sha256(
        {
            "contract": CONTRACT,
            "functions": {
                function.__name__: inspect.getsource(function) for function in functions
            },
            "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
            "recovery_v1_release_identity_sha256": RECOVERY_V1_RELEASE_IDENTITY_SHA256,
            "recovery_v2_release_identity_sha256": RECOVERY_V2_RELEASE_IDENTITY_SHA256,
            "recovery_implementation_sha256": RECOVERY_IMPLEMENTATION_SHA256,
            "recovery_lock_sha256": RECOVERY_LOCK_SHA256,
            "genesis": _pinned_genesis(),
        }
    )


def _lock_payload(config: Mapping[str, Any], *, bridge_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": LOCK_CONTRACT,
        "status": "SEALED_CANONICAL_ACTIVE_PAIR_RECOVERY_V3_LOCK_SYNTHETIC_ONLY",
        "bridge_sha256": execution.require_sha256(bridge_sha256, "V3 bridge"),
        "bridge_implementation_sha256": recovery_bridge_v3_implementation_sha256(),
        "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
        "recovery_v1_release_identity_sha256": RECOVERY_V1_RELEASE_IDENTITY_SHA256,
        "recovery_v2_release_identity_sha256": RECOVERY_V2_RELEASE_IDENTITY_SHA256,
        "recovery_function_source_sha256": RECOVERY_FUNCTION_SOURCE_SHA256,
        "recovery_implementation_sha256": RECOVERY_IMPLEMENTATION_SHA256,
        "recovery_execution_lock_sha256": RECOVERY_LOCK_SHA256,
        "genesis_ledger_prefix_sha256": GENESIS_LEDGER_SHA256,
        "operation": "recover-current-zero-weed",
        "caller_target_input_allowed": False,
        "patch_target": "execution.validate_full_plan",
        "all_callable_identities_restored_in_finally": True,
        "rejection_authority": "exact_locked_validator_zero_source_weed_failure_only",
        "acceptance_render_transition_or_publication_authority": "none",
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
        "status": "SEALED_CANONICAL_ACTIVE_PAIR_RECOVERY_V3_RELEASE_SYNTHETIC_ONLY",
        "authorization_receipt_sha256": authorization_sha256,
        "bridge_sha256": bridge_sha256,
        "bridge_lock_sha256": lock_sha256,
        "bridge_script_sha256": execution.sha256_file(sources["bridge_v3"]),
        "bridge_test_sha256": execution.sha256_file(sources["bridge_v3_test"]),
        "bridge_implementation_sha256": recovery_bridge_v3_implementation_sha256(),
        "immutable_parents": copy.deepcopy(dict(parents)),
        "genesis": _pinned_genesis(),
        "continuing_scope": (
            "canonical first-pending locked-test pair under valid state-chain descendants"
        ),
        "pass108_validation_only": True,
        "historical_parent_or_execution_bytes_rewritten": False,
        "real_recovery_candidate_gt_or_render_access_during_pass108": False,
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
                if path.is_file() and path.name != "pass108_validation_receipt.json"
            ),
            key=lambda value: value.relative_to(root).as_posix(),
        )
    ]


def _validation_receipt_payload(
    config: Mapping[str, Any], release_root: Path, release: Mapping[str, Any]
) -> dict[str, Any]:
    rows = _artifact_rows(release_root)
    return {
        "schema_version": 1,
        "contract": VALIDATION_RECEIPT_CONTRACT,
        "status": "READY_FOR_MANAGER_VALIDATION_SYNTHETIC_ONLY",
        "pass108_event_id": PASS108_EVENT_ID,
        "run_id": RUN_ID,
        "recovery_bridge_v3_release_identity_sha256": release[
            "release_identity_sha256"
        ],
        "release_artifact_inventory": rows,
        "release_artifact_inventory_sha256": execution.stable_sha256(rows),
        "validated_genesis": _pinned_genesis(),
        "focused_regression_contracts": [
            "initial_candidate8",
            "two_sequential_candidates_one_pair",
            "transition_to_second_canonical_pair",
            "state_chain_fork_or_rollback",
            "genesis_prefix_mutation",
            "parallel_state_chain_batch_or_v3_intent",
            "caller_target_injection",
            "candidate_skip_identity_or_seed_forgery",
            "non_zero_weed_no_append",
            "state_or_head_advance_during_recovery",
            "terminal_pair_or_batch",
            "callable_tamper_and_exception_restoration",
            "idempotent_resume",
            "zero_forbidden_access",
        ],
        "real_v3_intents_created_during_validation": 0,
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
            raise execution.ContractError("V3 recovery release file set changed")
    for relative in required:
        if execution.sha256_file(
            paths["synthetic_release"] / relative
        ) != execution.sha256_file(paths["docs_release"] / relative):
            raise execution.ContractError("V3 recovery docs release mirror changed")


def _validate_static_release_identity(
    config_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config, parent = _verify_immutable_parents(config_path)
    paths = recovery_bridge_v3_paths(config)
    _validate_release_file_set(paths)
    authorization = execution.load_json(paths["authorization"])
    if authorization != _authorization_payload(config):
        raise execution.ContractError("V3 manager authorization changed")
    bridge = execution.load_json(paths["bridge"])
    if bridge != _bridge_payload(config, parent["parents"]):
        raise execution.ContractError("V3 recovery bridge changed")
    lock = execution.load_json(paths["lock"])
    if lock != _lock_payload(config, bridge_sha256=execution.sha256_file(paths["bridge"])):
        raise execution.ContractError("V3 recovery bridge lock changed")
    release = execution.load_json(paths["release"])
    expected = _release_payload(
        config,
        parent["parents"],
        authorization_sha256=execution.sha256_file(paths["authorization"]),
        bridge_sha256=execution.sha256_file(paths["bridge"]),
        lock_sha256=execution.sha256_file(paths["lock"]),
    )
    if release != expected:
        raise execution.ContractError("V3 recovery bridge release changed")
    identity_payload = copy.deepcopy(release)
    identity = identity_payload.pop("release_identity_sha256", None)
    if identity != execution.stable_sha256(identity_payload):
        raise execution.ContractError("V3 recovery release identity changed")
    receipt = execution.load_json(paths["validation_receipt"])
    if receipt != _validation_receipt_payload(config, paths["synthetic_release"], release):
        raise execution.ContractError("Pass108 V3 validation receipt changed")
    return config, parent, release


def seal_recovery_bridge_v3_release(config_path: Path) -> dict[str, Any]:
    config, parent, boundary = _validate_active_boundary(config_path)
    _assert_pass108_initial_boundary(boundary)
    paths = recovery_bridge_v3_paths(config)
    partials = list(paths["synthetic_release"].parent.glob(".partial-*")) + list(
        paths["docs_release"].parent.glob(".partial-*")
    )
    if partials:
        raise execution.ContractError("Partial V3 recovery release exists")
    if paths["executions"].exists() or paths["docs_executions"].exists():
        raise execution.ContractError("Pass108 V3 execution artifact exists")
    if paths["synthetic_release"].exists() or paths["docs_release"].exists():
        return validate_recovery_bridge_v3_release(config_path)

    synthetic_parent = paths["synthetic_release"].parent
    docs_parent = paths["docs_release"].parent
    synthetic_parent.mkdir(parents=True, exist_ok=True)
    docs_parent.mkdir(parents=True, exist_ok=True)
    staging = synthetic_parent / f".partial-recovery-v3-{uuid.uuid4().hex}"
    docs_staging = docs_parent / f".partial-recovery-v3-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        execution.write_json(
            staging / "pass108_manager_authorization_receipt.json",
            _authorization_payload(config),
        )
        execution.write_json(
            staging / "state_chain_recovery_bridge_v3.json",
            _bridge_payload(config, parent["parents"]),
        )
        lock = _lock_payload(
            config,
            bridge_sha256=execution.sha256_file(
                staging / "state_chain_recovery_bridge_v3.json"
            ),
        )
        execution.write_json(
            staging / "state_chain_recovery_bridge_lock_v3.json", lock
        )
        release = _release_payload(
            config,
            parent["parents"],
            authorization_sha256=execution.sha256_file(
                staging / "pass108_manager_authorization_receipt.json"
            ),
            bridge_sha256=execution.sha256_file(
                staging / "state_chain_recovery_bridge_v3.json"
            ),
            lock_sha256=execution.sha256_file(
                staging / "state_chain_recovery_bridge_lock_v3.json"
            ),
        )
        execution.write_json(
            staging / "state_chain_recovery_bridge_release_v3.json", release
        )
        staging.replace(paths["synthetic_release"])
        execution.write_json(
            paths["validation_receipt"],
            _validation_receipt_payload(
                config, paths["synthetic_release"], release
            ),
        )
        shutil.copytree(paths["synthetic_release"], docs_staging)
        docs_staging.replace(paths["docs_release"])
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if docs_staging.exists():
            shutil.rmtree(docs_staging)
    return validate_recovery_bridge_v3_release(config_path)


def validate_recovery_bridge_v3_release(config_path: Path) -> dict[str, Any]:
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator was not restored")
    config, _, release = _validate_static_release_identity(config_path)
    _, _, boundary = _validate_active_boundary(
        config_path, release_identity=release["release_identity_sha256"]
    )
    paths = recovery_bridge_v3_paths(config)
    partials = list(paths["synthetic_release"].parent.glob(".partial-*")) + list(
        paths["docs_release"].parent.glob(".partial-*")
    )
    if partials:
        raise execution.ContractError("Partial V3 recovery release exists")
    return {
        "status": "READY_FOR_MANAGER_VALIDATION_SYNTHETIC_ONLY",
        "recovery_bridge_v3_release_identity_sha256": release[
            "release_identity_sha256"
        ],
        "completed_pair_count": boundary["completed_pair_count"],
        "pending_pair_count": boundary["pending_pair_count"],
        "first_pending_pair_id": boundary["first_pending_pair_id"],
        "chain_head_identity_sha256": boundary["chain_head_identity_sha256"],
        "render_state_sha256": boundary["render_state_sha256"],
        "candidate_rejection_ledger_row_count": boundary[
            "candidate_rejection_ledger_row_count"
        ],
        "candidate_rejection_ledger_sha256": boundary[
            "candidate_rejection_ledger_sha256"
        ],
        "state_chain_execution_id": boundary["state_chain_execution_id"],
        "underlying_batch_id": boundary["underlying_batch_id"],
        "next_candidate_index": boundary["next_candidate_index"],
        "next_candidate_identity_sha256": boundary[
            "next_candidate_identity_sha256"
        ],
        "v3_execution_count": boundary["v3_execution_count"],
        "real_v3_intents_created_during_validation": 0,
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


def _request(
    release_identity: str,
    boundary: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    journal_sequence: int,
    previous_terminal_receipt_sha256: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": CONTRACT,
        "operation": "recover-current-zero-weed",
        "journal_sequence": journal_sequence,
        "previous_terminal_receipt_sha256": previous_terminal_receipt_sha256,
        "caller_selected_target": False,
        "recovery_bridge_v3_release_identity_sha256": release_identity,
        "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
        "recovery_v1_release_identity_sha256": RECOVERY_V1_RELEASE_IDENTITY_SHA256,
        "recovery_v2_release_identity_sha256": RECOVERY_V2_RELEASE_IDENTITY_SHA256,
        "recovery_lock_sha256": RECOVERY_LOCK_SHA256,
        "state_chain_execution_id": boundary["state_chain_execution_id"],
        "state_chain_intent_sha256": boundary["state_chain_intent_sha256"],
        "underlying_batch_id": boundary["underlying_batch_id"],
        "underlying_batch_intent_sha256": boundary[
            "underlying_batch_intent_sha256"
        ],
        "pair_id": boundary["pair_id"],
        "pair_slot_identity_sha256": boundary["pair_slot_identity_sha256"],
        "candidate_index": candidate["candidate_index"],
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "candidate_seeds": copy.deepcopy(candidate["seeds"]),
        "source_template": copy.deepcopy(candidate["source_template"]),
        "predecessor_state_sha256": boundary["render_state_sha256"],
        "predecessor_head_identity_sha256": boundary[
            "chain_head_identity_sha256"
        ],
        "predecessor_ledger_sha256": boundary[
            "candidate_rejection_ledger_sha256"
        ],
        "predecessor_ledger_row_count": boundary[
            "candidate_rejection_ledger_row_count"
        ],
        "max_new_pairs": 1,
        "rejection_authority": "exact_locked_validator_zero_source_weed_failure_only",
        "acceptance_authority": "none",
        "render_or_state_transition_authority": False,
        "model_prediction_outcome_target_or_external_access_allowed": False,
    }


def _intent_payload(
    config: Mapping[str, Any],
    request: Mapping[str, Any],
    execution_id: str,
    request_identity: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": INTENT_CONTRACT,
        "status": "CANONICAL_ACTIVE_PAIR_RECOVERY_V3_INTENT_SYNTHETIC_ONLY",
        "execution_id": execution_id,
        "request_identity_sha256": request_identity,
        "request": copy.deepcopy(dict(request)),
        "access_guard": _access_guard(),
        "claim_boundary": _claim_boundary(config),
    }


def _publish_or_resume_intent(
    parent: Path, execution_id: str, intent: Mapping[str, Any]
) -> tuple[Path, bool]:
    parent.mkdir(parents=True, exist_ok=True)
    if list(parent.glob(".partial-*")):
        raise execution.ContractError("Partial V3 recovery intent exists")
    roots = sorted(path for path in parent.iterdir() if path.is_dir())
    for other in roots:
        if other.name == execution_id:
            continue
        if not (other / "recovery_bridge_terminal_receipt.json").is_file():
            raise execution.ContractError("Parallel V3 recovery intent exists")
    root = parent / execution_id
    intent_path = root / "recovery_bridge_intent.json"
    if root.exists():
        if not intent_path.is_file() or execution.load_json(intent_path) != dict(intent):
            raise execution.ContractError("Existing V3 recovery intent changed")
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


def _validate_runtime_phase(
    config_path: Path,
    *,
    wrapper_execution_id: str,
    request: Mapping[str, Any],
    release_identity: str,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    config, parent, boundary = _validate_active_boundary(
        config_path,
        release_identity=release_identity,
        allow_open_v3_execution_id=wrapper_execution_id,
    )
    pair_id = str(request["pair_id"])
    candidate_index = int(request["candidate_index"])
    roster_row = _pair_roster_row(execution.full_roster_rows(config), pair_id)
    candidate = _candidate_by_index(config, roster_row, candidate_index)
    if (
        request.get("candidate_identity_sha256")
        != candidate["candidate_identity_sha256"]
        or request.get("candidate_seeds") != candidate["seeds"]
        or request.get("source_template") != candidate["source_template"]
        or boundary.get("state_chain_execution_id")
        != request.get("state_chain_execution_id")
        or boundary.get("state_chain_intent_sha256")
        != request.get("state_chain_intent_sha256")
        or boundary.get("underlying_batch_id") != request.get("underlying_batch_id")
        or boundary.get("underlying_batch_intent_sha256")
        != request.get("underlying_batch_intent_sha256")
        or boundary.get("pair_id") != pair_id
        or boundary.get("render_state_sha256")
        != request.get("predecessor_state_sha256")
        or boundary.get("chain_head_identity_sha256")
        != request.get("predecessor_head_identity_sha256")
    ):
        raise execution.ContractError("V3 runtime active target changed")
    predecessor_count = int(request["predecessor_ledger_row_count"])
    current_count = int(boundary["candidate_rejection_ledger_row_count"])
    destination = _recovery_destination(config, pair_id, candidate_index)
    evidence: dict[str, Any] = {}
    if current_count == predecessor_count:
        if (
            boundary["candidate_rejection_ledger_sha256"]
            != request["predecessor_ledger_sha256"]
            or boundary["next_candidate_index"] != candidate_index
            or boundary["next_candidate_identity_sha256"]
            != candidate["candidate_identity_sha256"]
        ):
            raise execution.ContractError("V3 recovery predecessor ledger changed")
        if destination.exists():
            evidence = _validate_recovery_artifacts(
                config,
                roster_row,
                candidate_index,
                request["underlying_batch_id"],
                request["underlying_batch_intent_sha256"],
                require_commit=False,
            )
            if evidence.get("ledger_commit_receipt_sha256") is not None:
                raise execution.ContractError(
                    "Recovery commit receipt exists without ledger append"
                )
            phase = "published_uncommitted"
        else:
            if _recovery_docs_receipt(config, pair_id, candidate_index).exists():
                raise execution.ContractError("Recovery docs receipt exists before recovery")
            phase = "ready"
    elif current_count == predecessor_count + 1:
        ledger_path = state_chain._state_paths(config)[2]
        ledger = execution.read_jsonl(ledger_path)
        evidence = _validate_recovery_artifacts(
            config,
            roster_row,
            candidate_index,
            request["underlying_batch_id"],
            request["underlying_batch_intent_sha256"],
            require_commit=True,
        )
        _validate_rejection_row(ledger[predecessor_count], roster_row, candidate, evidence)
        phase = "committed"
    else:
        raise execution.ContractError("V3 recovery ledger advanced by a noncanonical amount")
    return config, {
        **boundary,
        "candidate_index": candidate_index,
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "recovery_evidence": evidence,
    }, phase


def _validate_underlying_result(
    result: Mapping[str, Any], request: Mapping[str, Any]
) -> None:
    if (
        result.get("status")
        not in {
            "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY",
            "SKIP_EXISTING_REJECT_ZERO_SOURCE_WEED_TRACKS_LOCKED_TEST_PREOUTCOME_SYNTHETIC_ONLY",
        }
        or result.get("pair_id") != request["pair_id"]
        or result.get("candidate_index") != request["candidate_index"]
        or result.get("batch_id") != request["underlying_batch_id"]
        or result.get("model_loaded") is not False
        or result.get("inference_calls") != 0
        or result.get("synthetic_only") is not True
    ):
        raise execution.ContractError("Unchanged recovery returned unauthorized evidence")


def _terminal_payload(
    config: Mapping[str, Any],
    request: Mapping[str, Any],
    request_identity: str,
    execution_id: str,
    intent_path: Path,
    underlying: Mapping[str, Any],
    after: Mapping[str, Any],
    resumed: bool,
) -> dict[str, Any]:
    evidence = after["recovery_evidence"]
    return {
        "schema_version": 1,
        "contract": TERMINAL_RECEIPT_CONTRACT,
        "status": "PASS_EXACT_ZERO_SOURCE_WEED_REJECTION_V3_SYNTHETIC_ONLY",
        "execution_id": execution_id,
        "request_identity_sha256": request_identity,
        "request": copy.deepcopy(dict(request)),
        "recovery_bridge_intent_sha256": execution.sha256_file(intent_path),
        "legacy_recovery": {
            "status": underlying.get("status"),
            "pair_id": underlying.get("pair_id"),
            "candidate_index": underlying.get("candidate_index"),
            "batch_id": underlying.get("batch_id"),
            "recovery_terminal_receipt_sha256": evidence[
                "recovery_terminal_receipt_sha256"
            ],
            "decision_receipt_sha256": evidence["decision_receipt_sha256"],
            "ledger_commit_receipt_sha256": evidence[
                "ledger_commit_receipt_sha256"
            ],
        },
        "boundary": {
            "render_state_sha256_before": request["predecessor_state_sha256"],
            "render_state_sha256_after": after["render_state_sha256"],
            "chain_head_identity_sha256_before": request[
                "predecessor_head_identity_sha256"
            ],
            "chain_head_identity_sha256_after": after[
                "chain_head_identity_sha256"
            ],
            "candidate_rejection_ledger_sha256_before": request[
                "predecessor_ledger_sha256"
            ],
            "candidate_rejection_ledger_sha256_after": after[
                "candidate_rejection_ledger_sha256"
            ],
            "candidate_rejection_ledger_row_count_before": request[
                "predecessor_ledger_row_count"
            ],
            "candidate_rejection_ledger_row_count_after": after[
                "candidate_rejection_ledger_row_count"
            ],
        },
        "resume": {"resumed_from_existing_v3_intent": resumed},
        "original_validator_restored": execution.validate_full_plan
        is _ORIGINAL_VALIDATE_FULL_PLAN,
        "access_guard": _access_guard(),
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
    evidence = current.get("recovery_evidence", {})
    boundary = receipt.get("boundary", {})
    legacy = receipt.get("legacy_recovery", {})
    valid = (
        receipt.get("schema_version") == 1
        and receipt.get("contract") == TERMINAL_RECEIPT_CONTRACT
        and receipt.get("status")
        == "PASS_EXACT_ZERO_SOURCE_WEED_REJECTION_V3_SYNTHETIC_ONLY"
        and receipt.get("execution_id") == execution_id
        and receipt.get("request_identity_sha256") == request_identity
        and receipt.get("request") == dict(request)
        and receipt.get("recovery_bridge_intent_sha256")
        == execution.sha256_file(intent_path)
        and receipt.get("original_validator_restored") is True
        and receipt.get("access_guard") == _access_guard()
        and receipt.get("claim_boundary") == _claim_boundary(config)
        and legacy.get("pair_id") == request["pair_id"]
        and legacy.get("candidate_index") == request["candidate_index"]
        and legacy.get("batch_id") == request["underlying_batch_id"]
        and legacy.get("recovery_terminal_receipt_sha256")
        == evidence.get("recovery_terminal_receipt_sha256")
        and legacy.get("decision_receipt_sha256")
        == evidence.get("decision_receipt_sha256")
        and legacy.get("ledger_commit_receipt_sha256")
        == evidence.get("ledger_commit_receipt_sha256")
        and boundary.get("render_state_sha256_before")
        == request["predecessor_state_sha256"]
        and boundary.get("render_state_sha256_after")
        == request["predecessor_state_sha256"]
        and boundary.get("chain_head_identity_sha256_before")
        == request["predecessor_head_identity_sha256"]
        and boundary.get("chain_head_identity_sha256_after")
        == request["predecessor_head_identity_sha256"]
        and boundary.get("candidate_rejection_ledger_sha256_before")
        == request["predecessor_ledger_sha256"]
        and boundary.get("candidate_rejection_ledger_sha256_after")
        == current["candidate_rejection_ledger_sha256"]
        and boundary.get("candidate_rejection_ledger_row_count_before")
        == request["predecessor_ledger_row_count"]
        and boundary.get("candidate_rejection_ledger_row_count_after")
        == request["predecessor_ledger_row_count"] + 1
    )
    if not valid:
        raise execution.ContractError("V3 recovery terminal receipt changed")


def _discover_open_v3_execution(config: Mapping[str, Any]) -> dict[str, Any] | None:
    records = _scan_v3_journal(config)
    open_records = [record for record in records if not record["terminal_present"]]
    if len(open_records) > 1:
        raise execution.ContractError("Parallel V3 recovery intents exist")
    return open_records[0] if open_records else None


def run_current_zero_weed_recovery_v3(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config, _, release = _validate_static_release_identity(config_path)
    release_identity = release["release_identity_sha256"]
    paths = recovery_bridge_v3_paths(config)
    open_record = _discover_open_v3_execution(config)

    if open_record is None:
        validation = validate_recovery_bridge_v3_release(config_path)
        _, _, boundary = _validate_active_boundary(
            config_path, release_identity=release_identity
        )
        roster_row = _pair_roster_row(
            execution.full_roster_rows(config), boundary["pair_id"]
        )
        candidate = _canonical_candidate(
            config, execution.full_paths(config)["synthetic"], roster_row
        )
        records = _scan_v3_journal(config)
        previous_sha = (
            execution.sha256_file(records[-1]["terminal_path"]) if records else None
        )
        request = _request(
            release_identity,
            boundary,
            candidate,
            journal_sequence=len(records) + 1,
            previous_terminal_receipt_sha256=previous_sha,
        )
        execution_id, request_identity = _execution_identity(request)
        intent = _intent_payload(config, request, execution_id, request_identity)
        execution_root, resumed = _publish_or_resume_intent(
            paths["executions"], execution_id, intent
        )
        if validation["recovery_bridge_v3_release_identity_sha256"] != release_identity:
            raise execution.ContractError("V3 release identity changed before intent")
    else:
        execution_id = open_record["execution_id"]
        request = open_record["request"]
        request_identity = open_record["request_identity_sha256"]
        expected_id, expected_identity = _execution_identity(request)
        if (
            expected_id != execution_id
            or expected_identity != request_identity
            or request.get("recovery_bridge_v3_release_identity_sha256")
            != release_identity
        ):
            raise execution.ContractError("Existing V3 recovery request changed")
        execution_root = open_record["root"]
        resumed = True

    intent_path = execution_root / "recovery_bridge_intent.json"
    terminal_path = execution_root / "recovery_bridge_terminal_receipt.json"
    docs_terminal = paths["docs_executions"] / f"{execution_id}.json"
    expected_intent = _intent_payload(config, request, execution_id, request_identity)
    if execution.load_json(intent_path) != expected_intent:
        raise execution.ContractError("V3 recovery intent changed after publication")

    _, _, phase_before = _validate_runtime_phase(
        config_path,
        wrapper_execution_id=execution_id,
        request=request,
        release_identity=release_identity,
    )
    if phase_before == "committed":
        underlying = {
            "status": (
                "SKIP_EXISTING_REJECT_ZERO_SOURCE_WEED_TRACKS_"
                "LOCKED_TEST_PREOUTCOME_SYNTHETIC_ONLY"
            ),
            "pair_id": request["pair_id"],
            "candidate_index": request["candidate_index"],
            "batch_id": request["underlying_batch_id"],
            "model_loaded": False,
            "inference_calls": 0,
            "synthetic_only": True,
        }
    else:
        underlying = _call_unchanged_recovery(config_path, request)
    _validate_underlying_result(underlying, request)
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator was not restored after V3 recovery")
    _, after, phase_after = _validate_runtime_phase(
        config_path,
        wrapper_execution_id=execution_id,
        request=request,
        release_identity=release_identity,
    )
    if phase_after != "committed":
        raise execution.ContractError("V3 rejection was not atomically committed")
    terminal = _terminal_payload(
        config,
        request,
        request_identity,
        execution_id,
        intent_path,
        underlying,
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
        "pair_id": request["pair_id"],
        "candidate_index": request["candidate_index"],
        "candidate_identity_sha256": request["candidate_identity_sha256"],
        "recovery_bridge_terminal_receipt_sha256": execution.sha256_file(
            terminal_path
        ),
        "candidate_rejection_ledger_row_count": request[
            "predecessor_ledger_row_count"
        ]
        + 1,
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
    subparsers.add_parser("recover-current-zero-weed")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "seal":
            result = seal_recovery_bridge_v3_release(args.config)
        elif args.command == "validate":
            result = validate_recovery_bridge_v3_release(args.config)
        else:
            result = run_current_zero_weed_recovery_v3(args.config)
    except execution.ContractError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
