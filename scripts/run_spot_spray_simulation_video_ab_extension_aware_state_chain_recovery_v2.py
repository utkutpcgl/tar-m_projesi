#!/usr/bin/env python3
"""Seal and run the reusable state-chain-aware rejection-only recovery bridge.

This append-only V2 epoch preserves every parent byte and derives exactly one
canonical candidate from the frozen roster and rejection ledger.  It may invoke
the unchanged locked-test source-cardinality recovery only while the exact
``locked_test_c001_r04`` state-chain execution remains open at 44/96.  Its sole
authority is to commit the legacy validator's exact zero-source-weed rejection.

Pass 91 is validation-only.  ``recover`` is intentionally present for a later
same-run pass; sealing and validation never access candidate GT or a renderer.
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
from scripts import run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1 as state_chain


DEFAULT_CONFIG = state_chain.DEFAULT_CONFIG

CONTRACT = "spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v2"
AUTHORIZATION_CONTRACT = f"{CONTRACT}_manager_authorization"
BRIDGE_CONTRACT = f"{CONTRACT}_bridge"
LOCK_CONTRACT = f"{CONTRACT}_lock"
RELEASE_CONTRACT = f"{CONTRACT}_release"
VALIDATION_RECEIPT_CONTRACT = f"{CONTRACT}_pass91_validation"
INTENT_CONTRACT = f"{CONTRACT}_intent"
TERMINAL_RECEIPT_CONTRACT = f"{CONTRACT}_terminal_receipt"

PASS91_EVENT_ID = "scheduled-resume-20260821013702-cdb86c816d7c"
MANAGER_HANDOFF_EVENT_ID = "scheduled-resume-20260821013117-cc95003b577f"
MANAGER_SESSION_ID = "019fb346-5ead-7600-8068-40b32b0daa06"
OWNER_SESSION_ID = "01a0019e-e810-73b3-9f29-ffad14c34ec5"
RUN_ID = "goal-multi-repeat-full-simulation-video-ab-execution-v1-e2dcf4ac8b10"
PORTFOLIO_ID = "goal-multi-repeat-agents-spot-spray-simulation-video-ab-v1-b8e46607aeea"
PORTFOLIO_LANE = "full-simulation-video-ab-execution-v1"
PORTFOLIO_REVISION = 145

AUTHORIZED_SOURCE_PATH = (
    "scripts/run_spot_spray_simulation_video_ab_extension_aware_"
    "state_chain_recovery_v2.py"
)
AUTHORIZED_TEST_PATH = (
    "tests/test_run_spot_spray_simulation_video_ab_extension_aware_"
    "state_chain_recovery_v2.py"
)

LEGACY_EXECUTION_SCRIPT_SHA256 = (
    "200d897efa1400a9dabba1acaf33d1b49db2c00ebcf79768f25fa4a8608bb413"
)
LEGACY_EXECUTION_TEST_SHA256 = (
    "66878530bb4878da29adf5b32da9fa506ccb4f132a508de105a6e11f8a65f9b5"
)
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
RECOVERY_V1_SCRIPT_SHA256 = (
    "6c35f6635b8cd6720271bc3fc246b48ae24ba3a70869e526e18c5c33afb8d2d9"
)
RECOVERY_V1_TEST_SHA256 = (
    "003f42bf83d48073803a77920bebc1313f6f8240e8c141a851a5332d55638c72"
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

RECOVERY_V1_RELEASE_FILE_SHA256 = (
    "f11f72ed131cf04c2352de35e50e8c1a8677546568ea969681f005f967f62e82"
)
RECOVERY_V1_RELEASE_IDENTITY_SHA256 = (
    "dd33482b9a1f8bbbc06358100c7760d6f61ead5f94da5c3f5bfc143a27d6a4fa"
)
RECOVERY_V1_AUTHORIZATION_SHA256 = (
    "945a2724349b0592baa0e1f7d2c51682b5411f41d057e03bdfae3a57329ac5f6"
)
RECOVERY_V1_BRIDGE_SHA256 = (
    "133fb573d3c6c51713648bf3c52e6c2cb25f67d240b0aed372d4d63ef7d7c14e"
)
RECOVERY_V1_LOCK_SHA256 = (
    "c779c9fef1da11c52634885acb554051cc338bcf6aab317685c61187c5887a48"
)
RECOVERY_V1_VALIDATION_SHA256 = (
    "c84adc4bb8fd7e487a105ee788931ffeb8f7e02d558e7ce243df2034e250fd55"
)
RECOVERY_V1_EXECUTION_ID = (
    "state_chain_recovery_locked_test_c001_r04_candidate_01_63e81f0e1073e954"
)
RECOVERY_V1_INTENT_SHA256 = (
    "f268d5cdf934f91d13cd04c3cb0712b5ef13794a8f11f573a2a4b594fccc99b4"
)
RECOVERY_V1_TERMINAL_SHA256 = (
    "790047b6aa5bede8cf08bee9e2a20ce75788bb8a686ef61238d94b88289b62fd"
)
PASS90_RECEIPT_SHA256 = (
    "d622909a735a14871e4713488f971d929c569155fdd88e520ffbfcda83ba9333"
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
PAIR_SLOT_IDENTITY_SHA256 = (
    "c84738918147c52362d2c5261ce35d3acf28bc6596e961615b281cb993ff6e49"
)
CURRENT_STATE_SHA256 = (
    "ff5b4b4ce495f7b515b00fa1402fab1dbf11db9bf2b204e1cc2dc858adcc7e5b"
)
CURRENT_HEAD_IDENTITY_SHA256 = (
    "04074c9cdc8eef7599de90966847fb274ddf7e80202372f1a7bb992010782f01"
)
BASE_LEDGER_SHA256 = (
    "e03687ee2345e745e8f594ad83af40a08009ed868422bba5029b5411aeff63db"
)
BASE_LEDGER_ROW_COUNT = 123
CURRENT_COMPLETED_PAIR_COUNT = 44
CURRENT_PENDING_PAIR_COUNT = 52
MIN_CANDIDATE_INDEX = 2
MAX_CANDIDATE_INDEX = 31
INITIAL_CANDIDATE_IDENTITY_SHA256 = (
    "766cb27eb634b44cc627e569b2d030848c7296e9933d653ed0341ec0f79eab93"
)
INITIAL_SOURCE_TEMPLATE_SHA256 = (
    "674ac8146691aa2f6bca7b3f7382ae4790c6b8676e6db4450fabd12d26e6c76e"
)

_ORIGINAL_VALIDATE_FULL_PLAN = execution.validate_full_plan
_ORIGINAL_RECOVERY_CALLABLE = execution.run_locked_test_gt_source_cardinality_recovery


def recovery_bridge_v2_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    full = execution.full_paths(config)
    synthetic_root = (
        full["synthetic"] / "planning/extension_aware_state_chain_recovery_v2"
    )
    docs_root = full["docs"] / "extension_aware_state_chain_recovery_v2"
    synthetic_release = synthetic_root / "release_v2"
    docs_release = docs_root / "release_v2"
    return {
        "synthetic_root": synthetic_root,
        "docs_root": docs_root,
        "synthetic_release": synthetic_release,
        "docs_release": docs_release,
        "authorization": synthetic_release / "pass91_manager_authorization_receipt.json",
        "bridge": synthetic_release / "state_chain_recovery_bridge_v2.json",
        "lock": synthetic_release / "state_chain_recovery_bridge_lock_v2.json",
        "release": synthetic_release / "state_chain_recovery_bridge_release_v2.json",
        "validation_receipt": synthetic_release / "pass91_validation_receipt.json",
        "executions": synthetic_root / "executions",
        "docs_executions": docs_root / "executions",
    }


def _required_release_files() -> list[str]:
    return [
        "pass91_manager_authorization_receipt.json",
        "pass91_validation_receipt.json",
        "state_chain_recovery_bridge_lock_v2.json",
        "state_chain_recovery_bridge_release_v2.json",
        "state_chain_recovery_bridge_v2.json",
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
        "recovery_v1": PROJECT_ROOT
        / "scripts/run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v1.py",
        "recovery_v1_test": PROJECT_ROOT
        / "tests/test_run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v1.py",
        "bridge_v2": PROJECT_ROOT / AUTHORIZED_SOURCE_PATH,
        "bridge_v2_test": PROJECT_ROOT / AUTHORIZED_TEST_PATH,
    }


def _recovery_lock_path(config: Mapping[str, Any]) -> Path:
    return (
        execution.roster_extension_paths(config)["execution_locks"]
        / "locked_test_recovery_execution_lock_extension_v1.json"
    )


def _pass90_receipt_path(config: Mapping[str, Any]) -> Path:
    return (
        execution.full_paths(config)["docs"]
        / "locked_test_render_batches/pass89_state_chain_resume/"
        "pass90_fail_closed_receipt.json"
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


def _recovery_destination(config: Mapping[str, Any], candidate_index: int) -> Path:
    return (
        execution.full_paths(config)["synthetic"]
        / "planning/locked_test_gt_source_cardinality_recovery_v1/roster"
        / PAIR_ID
        / f"candidate_{candidate_index:02d}"
    )


def _recovery_docs_receipt(config: Mapping[str, Any], candidate_index: int) -> Path:
    return (
        execution.full_paths(config)["docs"]
        / "gt_scout_v1"
        / f"locked_test_source_cardinality_recovery_{PAIR_ID}_candidate_"
        f"{candidate_index:02d}.json"
    )


def _recovery_v1_execution_paths(config: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    paths = recovery_v1.recovery_bridge_paths(config)
    root = paths["executions"] / RECOVERY_V1_EXECUTION_ID
    return (
        root / "recovery_bridge_intent.json",
        root / "recovery_bridge_terminal_receipt.json",
        paths["docs_executions"] / f"{RECOVERY_V1_EXECUTION_ID}.json",
    )


def _verify_immutable_parents(
    config_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = config_path.expanduser().resolve()
    if resolved != DEFAULT_CONFIG.expanduser().resolve():
        raise execution.ContractError("Noncanonical V2 state-chain recovery config")
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

    config, roster = state_chain._verify_immutable_parents(resolved)
    root, state_release, static = state_chain._validate_static_release(
        config, roster["parents"]
    )
    _require_file_sha256(
        static["paths"]["release_file"],
        STATE_CHAIN_RELEASE_FILE_SHA256,
        "state-chain release",
    )
    if state_release.get("release_identity_sha256") != STATE_CHAIN_RELEASE_IDENTITY_SHA256:
        raise execution.ContractError("State-chain release identity changed")

    v1_config, _, v1_release = recovery_v1._validate_static_release_identity(resolved)
    if v1_config != config:
        raise execution.ContractError("V1 recovery config binding changed")
    v1_paths = recovery_v1.recovery_bridge_paths(config)
    for key, digest in (
        ("authorization", RECOVERY_V1_AUTHORIZATION_SHA256),
        ("bridge", RECOVERY_V1_BRIDGE_SHA256),
        ("lock", RECOVERY_V1_LOCK_SHA256),
        ("release", RECOVERY_V1_RELEASE_FILE_SHA256),
        ("validation_receipt", RECOVERY_V1_VALIDATION_SHA256),
    ):
        _require_file_sha256(v1_paths[key], digest, f"V1 recovery {key}")
    if v1_release.get("release_identity_sha256") != RECOVERY_V1_RELEASE_IDENTITY_SHA256:
        raise execution.ContractError("V1 recovery release identity changed")

    v1_intent, v1_terminal, v1_docs_terminal = _recovery_v1_execution_paths(config)
    _require_file_sha256(v1_intent, RECOVERY_V1_INTENT_SHA256, "V1 recovery intent")
    _require_file_sha256(
        v1_terminal, RECOVERY_V1_TERMINAL_SHA256, "V1 recovery terminal"
    )
    _require_file_sha256(
        v1_docs_terminal,
        RECOVERY_V1_TERMINAL_SHA256,
        "V1 recovery docs terminal",
    )
    terminal = execution.load_json(v1_terminal)
    if (
        terminal.get("status")
        != "PASS_EXACT_ZERO_SOURCE_WEED_REJECTION_SYNTHETIC_ONLY"
        or terminal.get("request", {}).get("candidate_index") != 1
        or terminal.get("boundary", {}).get(
            "candidate_rejection_ledger_row_count_after"
        )
        != BASE_LEDGER_ROW_COUNT
        or terminal.get("boundary", {}).get(
            "candidate_rejection_ledger_sha256_after"
        )
        != BASE_LEDGER_SHA256
        or terminal.get("original_validator_restored") is not True
    ):
        raise execution.ContractError("V1 recovery terminal binding changed")
    v1_evidence = recovery_v1._validate_recovery_artifacts(
        config, require_commit=True
    )
    if (
        v1_evidence.get("recovery_terminal_receipt_sha256")
        != execution.load_json(v1_terminal)["legacy_recovery"][
            "recovery_terminal_receipt_sha256"
        ]
    ):
        raise execution.ContractError("V1 legacy recovery evidence changed")

    lock_path = _recovery_lock_path(config)
    _require_file_sha256(lock_path, RECOVERY_LOCK_SHA256, "recovery lock")
    lock = execution.load_json(lock_path)
    if (
        lock.get("recovery_implementation_sha256") != RECOVERY_IMPLEMENTATION_SHA256
        or lock.get("rejection_authority")
        != "exact_locked_validator_zero_source_weed_failure_only"
        or lock.get("acceptance_authority") != "none"
        or lock.get("model_access_allowed") is not False
        or lock.get("outcome_inputs_allowed") is not False
        or lock.get("registered_targets_allowed") is not False
    ):
        raise execution.ContractError("Recovery lock authority changed")
    _require_file_sha256(
        _pass90_receipt_path(config), PASS90_RECEIPT_SHA256, "Pass90 blocker receipt"
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
        "recovery_v1_script_sha256": RECOVERY_V1_SCRIPT_SHA256,
        "recovery_v1_test_sha256": RECOVERY_V1_TEST_SHA256,
        "recovery_v1_release_file_sha256": RECOVERY_V1_RELEASE_FILE_SHA256,
        "recovery_v1_release_identity_sha256": RECOVERY_V1_RELEASE_IDENTITY_SHA256,
        "recovery_v1_terminal_receipt_sha256": RECOVERY_V1_TERMINAL_SHA256,
        "pass90_blocker_receipt_sha256": PASS90_RECEIPT_SHA256,
    }
    return config, {
        "parents": parents,
        "roster": roster,
        "state_chain_root": root,
        "state_chain_static": static,
        "recovery_v1_release": v1_release,
    }


def _pinned_initial_boundary() -> dict[str, Any]:
    return {
        "completed_pair_count": CURRENT_COMPLETED_PAIR_COUNT,
        "pending_pair_count": CURRENT_PENDING_PAIR_COUNT,
        "first_pending_pair_id": PAIR_ID,
        "render_state_sha256": CURRENT_STATE_SHA256,
        "chain_head_identity_sha256": CURRENT_HEAD_IDENTITY_SHA256,
        "candidate_rejection_ledger_sha256": BASE_LEDGER_SHA256,
        "candidate_rejection_ledger_row_count": BASE_LEDGER_ROW_COUNT,
        "state_chain_execution_id": STATE_CHAIN_EXECUTION_ID,
        "state_chain_intent_sha256": STATE_CHAIN_INTENT_SHA256,
        "underlying_batch_id": BATCH_ID,
        "underlying_batch_intent_sha256": BATCH_INTENT_SHA256,
        "pair_id": PAIR_ID,
        "pair_slot_identity_sha256": PAIR_SLOT_IDENTITY_SHA256,
        "first_authorized_candidate_index": MIN_CANDIDATE_INDEX,
        "first_authorized_candidate_identity_sha256": (
            INITIAL_CANDIDATE_IDENTITY_SHA256
        ),
        "first_authorized_source_template_sha256": INITIAL_SOURCE_TEMPLATE_SHA256,
        "last_authorized_candidate_index": MAX_CANDIDATE_INDEX,
        "recovery_v1_release_identity_sha256": (
            RECOVERY_V1_RELEASE_IDENTITY_SHA256
        ),
        "recovery_v1_terminal_receipt_sha256": RECOVERY_V1_TERMINAL_SHA256,
        "recovery_lock_sha256": RECOVERY_LOCK_SHA256,
        "state_chain_terminal_receipt_present": False,
        "batch_terminal_receipt_present": False,
        "pair_publication_present": False,
    }


def _ledger_prefix_sha256(path: Path, row_count: int) -> str:
    lines = path.read_bytes().splitlines(keepends=True)
    if len(lines) < row_count:
        raise execution.ContractError("Candidate rejection ledger was truncated")
    return hashlib.sha256(b"".join(lines[:row_count])).hexdigest()


def _pair_roster_row(
    roster_rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    matches = [row for row in roster_rows if str(row.get("pair_id")) == PAIR_ID]
    if len(matches) != 1:
        raise execution.ContractError("Recovery pair escaped the sealed roster")
    row = matches[0]
    if (
        row.get("protocol_split") != "locked_test"
        or row.get("pair_slot_identity_sha256") != PAIR_SLOT_IDENTITY_SHA256
        or len(row.get("candidates", [])) != 32
    ):
        raise execution.ContractError("Recovery pair-slot binding changed")
    return row


def _canonical_candidate(
    config: Mapping[str, Any], full_root: Path, roster_row: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    try:
        candidate = execution._next_gt_scout_candidate(full_root, roster_row)
    except execution.ContractError as error:
        if str(error) == f"GT scout candidate attempts exhausted: {PAIR_ID}":
            return None
        raise
    index = candidate.get("candidate_index")
    if (
        not isinstance(index, int)
        or isinstance(index, bool)
        or index < MIN_CANDIDATE_INDEX
        or index > MAX_CANDIDATE_INDEX
        or roster_row["candidates"][index] != candidate
        or candidate.get("model_outcome_inputs") != []
    ):
        raise execution.ContractError("Derived V2 recovery candidate is noncanonical")
    source = execution.full_candidate_source_path(config, roster_row, candidate)
    if (
        not source.is_file()
        or execution.sha256_file(source)
        != candidate.get("source_template", {}).get("sha256")
    ):
        raise execution.ContractError("Derived candidate source-template bytes changed")
    return candidate


def _candidate_by_index(
    config: Mapping[str, Any], roster_row: Mapping[str, Any], candidate_index: int
) -> Mapping[str, Any]:
    if candidate_index < MIN_CANDIDATE_INDEX or candidate_index > MAX_CANDIDATE_INDEX:
        raise execution.ContractError("V2 recovery candidate escaped authorized range")
    candidate = roster_row["candidates"][candidate_index]
    if (
        candidate.get("candidate_index") != candidate_index
        or candidate.get("model_outcome_inputs") != []
    ):
        raise execution.ContractError("V2 recovery candidate roster binding changed")
    source = execution.full_candidate_source_path(config, roster_row, candidate)
    if (
        not source.is_file()
        or execution.sha256_file(source)
        != candidate.get("source_template", {}).get("sha256")
    ):
        raise execution.ContractError("V2 candidate source-template bytes changed")
    return candidate


def _validate_recovery_artifacts(
    config: Mapping[str, Any],
    roster_row: Mapping[str, Any],
    candidate_index: int,
    *,
    require_commit: bool,
) -> dict[str, Any]:
    candidate = _candidate_by_index(config, roster_row, candidate_index)
    identity = candidate["candidate_identity_sha256"]
    destination = _recovery_destination(config, candidate_index)
    terminal_path = destination / "recovery_terminal_receipt.json"
    decision_path = destination / "decision_receipt.json"
    if not terminal_path.is_file() or not decision_path.is_file():
        raise execution.ContractError(
            f"Candidate {candidate_index} recovery evidence is incomplete"
        )
    terminal = execution.load_json(terminal_path)
    decision = execution.load_json(decision_path)
    audit = terminal.get("source_cardinality_audit", {})
    valid = (
        terminal.get("contract")
        == execution.LOCKED_TEST_GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT
        and terminal.get("status")
        == "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY"
        and terminal.get("pair_id") == PAIR_ID
        and terminal.get("protocol_split") == "locked_test"
        and terminal.get("pair_slot_identity_sha256") == PAIR_SLOT_IDENTITY_SHA256
        and terminal.get("candidate_index") == candidate_index
        and terminal.get("candidate_identity_sha256") == identity
        and terminal.get("candidate_seeds") == candidate["seeds"]
        and terminal.get("source_template") == candidate["source_template"]
        and terminal.get("source_template_sha256_exact") is True
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
        and audit.get("locked_botanical_validator_failure")
        == "Too few source weed tracks: 0"
        and audit.get("source_weed_track_count") == 0
        and audit.get("rejection_reason")
        == "eligibility:source_weed_track_present"
        and audit.get("model_or_outcome_inputs_used") is False
        and decision.get("contract")
        == execution.GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT
        and decision.get("pair_id") == PAIR_ID
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
        raise execution.ContractError(
            f"Candidate {candidate_index} exact recovery evidence changed"
        )
    if (destination / "source_scene").exists():
        raise execution.ContractError("Recovery retained a bulk source scene")
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
            or commit.get("candidate_index") != candidate_index
            or commit.get("candidate_identity_sha256") != identity
            or commit.get("model_or_outcome_inputs_used") is not False
            or commit.get("idempotent") is not True
        ):
            raise execution.ContractError("Recovery ledger commit receipt changed")
        docs_receipt = _recovery_docs_receipt(config, candidate_index)
        _require_file_sha256(
            docs_receipt,
            execution.sha256_file(terminal_path),
            "recovery docs receipt",
        )
    elif commit is not None:
        if (
            commit.get("pair_id") != PAIR_ID
            or commit.get("candidate_index") != candidate_index
            or commit.get("candidate_identity_sha256") != identity
        ):
            raise execution.ContractError("Uncommitted recovery receipt changed")
    return {
        "candidate_index": candidate_index,
        "candidate_identity_sha256": identity,
        "source_template_sha256": candidate["source_template"]["sha256"],
        "recovery_terminal_receipt_sha256": execution.sha256_file(terminal_path),
        "decision_receipt_sha256": execution.sha256_file(decision_path),
        "ledger_commit_receipt_sha256": (
            execution.sha256_file(commit_path) if commit_path.is_file() else None
        ),
    }


def _validate_appended_rejection_rows(
    config: Mapping[str, Any],
    ledger_path: Path,
    ledger: Sequence[Mapping[str, Any]],
    roster_rows: Sequence[Mapping[str, Any]],
    roster_row: Mapping[str, Any],
    *,
    allow_uncommitted_candidate_index: int | None = None,
) -> list[dict[str, Any]]:
    if len(ledger) < BASE_LEDGER_ROW_COUNT:
        raise execution.ContractError("Candidate rejection ledger was truncated")
    if _ledger_prefix_sha256(ledger_path, BASE_LEDGER_ROW_COUNT) != BASE_LEDGER_SHA256:
        raise execution.ContractError("Frozen 123-row rejection ledger prefix changed")
    prefix = list(ledger[:BASE_LEDGER_ROW_COUNT])
    state_chain._validate_ledger_extension(prefix, ledger, roster_rows, PAIR_ID)
    appended = list(ledger[BASE_LEDGER_ROW_COUNT:])
    evidence: list[dict[str, Any]] = []
    for offset, row in enumerate(appended):
        expected_index = MIN_CANDIDATE_INDEX + offset
        if expected_index > MAX_CANDIDATE_INDEX:
            raise execution.ContractError("V2 recovery ledger exceeded candidate 31")
        candidate = _candidate_by_index(config, roster_row, expected_index)
        if (
            row.get("schema_version") != 1
            or row.get("status")
            != "REJECTED_FULL_PAIR_CANDIDATE_PREOUTCOME_SYNTHETIC_ONLY"
            or row.get("pair_id") != PAIR_ID
            or row.get("candidate_index") != expected_index
            or row.get("candidate_identity_sha256")
            != candidate["candidate_identity_sha256"]
            or row.get("reason_type") != "GtScoutCandidateRejected"
            or row.get("reason") != "eligibility:source_weed_track_present"
            or row.get("rejection_families")
            != [
                "frozen_semantic_operability",
                "frozen_eligible_weed_temporal_denominator",
            ]
            or row.get("model_or_outcome_inputs_used") is not False
            or row.get("bulk_payload_retained") is not False
        ):
            raise execution.ContractError("V2 recovery ledger append changed")
        artifact = _validate_recovery_artifacts(
            config,
            roster_row,
            expected_index,
            require_commit=expected_index != allow_uncommitted_candidate_index,
        )
        if (
            row.get("gt_scout_terminal_receipt_sha256")
            != artifact["recovery_terminal_receipt_sha256"]
            or row.get("gt_scout_decision_receipt_sha256")
            != artifact["decision_receipt_sha256"]
        ):
            raise execution.ContractError("V2 ledger-to-recovery receipt binding changed")
        evidence.append(artifact)
    return evidence


def _execution_identity(request: Mapping[str, Any]) -> tuple[str, str]:
    identity = execution.stable_sha256(request)
    index = request.get("candidate_index")
    if not isinstance(index, int) or isinstance(index, bool):
        raise execution.ContractError("Recovery request candidate index is invalid")
    execution_id = (
        f"state_chain_recovery_v2_{PAIR_ID}_candidate_{index:02d}_{identity[:16]}"
    )
    if execution.SAFE_ID_RE.fullmatch(execution_id) is None:
        raise execution.ContractError("Unsafe V2 recovery execution identity")
    return execution_id, identity


def _scan_wrapper_execution_roots(
    config: Mapping[str, Any],
) -> list[dict[str, Any]]:
    paths = recovery_bridge_v2_paths(config)
    parent = paths["executions"]
    docs_parent = paths["docs_executions"]
    if not parent.exists():
        if docs_parent.exists() and any(docs_parent.iterdir()):
            raise execution.ContractError("V2 docs execution exists without source")
        return []
    if list(parent.glob(".partial-*")):
        raise execution.ContractError("Partial V2 recovery intent exists")
    if docs_parent.exists() and list(docs_parent.glob(".partial-*")):
        raise execution.ContractError("Partial V2 docs receipt exists")
    records: list[dict[str, Any]] = []
    for root in sorted(path for path in parent.iterdir() if path.is_dir()):
        intent_path = root / "recovery_bridge_intent.json"
        if not intent_path.is_file():
            raise execution.ContractError("V2 recovery execution has no intent")
        intent = execution.load_json(intent_path)
        request = intent.get("request", {})
        expected_id, request_identity = _execution_identity(request)
        if (
            root.name != expected_id
            or intent.get("schema_version") != 1
            or intent.get("contract") != INTENT_CONTRACT
            or intent.get("status")
            != "STATE_CHAIN_RECOVERY_V2_INTENT_SYNTHETIC_ONLY"
            or intent.get("execution_id") != root.name
            or intent.get("request_identity_sha256") != request_identity
            or request.get("contract") != CONTRACT
            or request.get("pair_id") != PAIR_ID
            or request.get("state_chain_execution_id") != STATE_CHAIN_EXECUTION_ID
            or request.get("underlying_batch_id") != BATCH_ID
            or request.get("acceptance_authority") != "none"
            or request.get("rejection_authority")
            != "exact_locked_validator_zero_source_weed_failure_only"
            or request.get(
                "model_prediction_outcome_target_or_external_access_allowed"
            )
            is not False
            or intent.get("access_guard")
            != {
                "model_loaded": False,
                "inference_calls": 0,
                "prediction_accessed": False,
                "locked_test_outcome_accessed": False,
                "registered_targets_used": False,
                "external_services_modified": False,
                "outcome_inputs": [],
            }
            or intent.get("claim_boundary") != _claim_boundary(config)
        ):
            raise execution.ContractError("V2 recovery intent binding changed")
        terminal_path = root / "recovery_bridge_terminal_receipt.json"
        docs_terminal = docs_parent / f"{root.name}.json"
        if terminal_path.is_file():
            terminal = execution.load_json(terminal_path)
            access = terminal.get("access_guard", {})
            if (
                terminal.get("contract") != TERMINAL_RECEIPT_CONTRACT
                or terminal.get("status")
                != "PASS_EXACT_ZERO_SOURCE_WEED_REJECTION_V2_SYNTHETIC_ONLY"
                or terminal.get("execution_id") != root.name
                or terminal.get("request") != request
                or terminal.get("request_identity_sha256") != request_identity
                or terminal.get("original_validator_restored") is not True
                or terminal.get("claim_boundary") != _claim_boundary(config)
                or access
                != {
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
            ):
                raise execution.ContractError("V2 recovery terminal binding changed")
            _require_file_sha256(
                docs_terminal,
                execution.sha256_file(terminal_path),
                "V2 docs terminal receipt",
            )
        elif docs_terminal.exists():
            raise execution.ContractError("V2 docs terminal exists before source terminal")
        records.append(
            {
                "execution_id": root.name,
                "root": root,
                "intent": intent,
                "intent_path": intent_path,
                "request": request,
                "request_identity_sha256": request_identity,
                "terminal_path": terminal_path,
                "terminal_present": terminal_path.is_file(),
            }
        )
    indices = [int(record["request"]["candidate_index"]) for record in records]
    if indices != list(range(MIN_CANDIDATE_INDEX, MIN_CANDIDATE_INDEX + len(indices))):
        raise execution.ContractError("V2 recovery execution candidate order changed")
    return records


def _validate_wrapper_execution_roots(
    config: Mapping[str, Any],
    ledger_path: Path,
    appended_indices: Sequence[int],
    *,
    allow_open_execution_id: str | None,
    release_identity: str | None,
) -> list[dict[str, Any]]:
    records = _scan_wrapper_execution_roots(config)
    open_records = [record for record in records if not record["terminal_present"]]
    if len(open_records) > 1:
        raise execution.ContractError("Parallel V2 recovery intents exist")
    if allow_open_execution_id is None:
        if open_records:
            raise execution.ContractError("Open V2 recovery intent is not authorized")
    elif (
        len(open_records) != 1
        or open_records[0]["execution_id"] != allow_open_execution_id
    ):
        raise execution.ContractError("Wrong V2 recovery intent is open")

    appended = list(appended_indices)
    for record in records:
        request = record["request"]
        index = int(request["candidate_index"])
        roster_row = _pair_roster_row(execution.full_roster_rows(config))
        candidate = _candidate_by_index(config, roster_row, index)
        predecessor_count = BASE_LEDGER_ROW_COUNT + (index - MIN_CANDIDATE_INDEX)
        if (
            request.get("state_chain_release_identity_sha256")
            != STATE_CHAIN_RELEASE_IDENTITY_SHA256
            or request.get("state_chain_intent_sha256") != STATE_CHAIN_INTENT_SHA256
            or request.get("underlying_batch_intent_sha256") != BATCH_INTENT_SHA256
            or request.get("predecessor_state_sha256") != CURRENT_STATE_SHA256
            or request.get("predecessor_head_identity_sha256")
            != CURRENT_HEAD_IDENTITY_SHA256
            or request.get("predecessor_ledger_row_count") != predecessor_count
            or request.get("predecessor_ledger_sha256")
            != _ledger_prefix_sha256(ledger_path, predecessor_count)
            or request.get("recovery_lock_sha256") != RECOVERY_LOCK_SHA256
            or request.get("candidate_identity_sha256")
            != candidate["candidate_identity_sha256"]
            or request.get("source_template_sha256")
            != candidate["source_template"]["sha256"]
            or (
                release_identity is not None
                and request.get("recovery_bridge_v2_release_identity_sha256")
                != release_identity
            )
        ):
            raise execution.ContractError("V2 recovery request predecessor changed")
        if record["terminal_present"] and index not in appended:
            raise execution.ContractError("V2 terminal exists without ledger append")
        if not record["terminal_present"] and index not in {
            *appended,
            MIN_CANDIDATE_INDEX + len(appended),
        }:
            raise execution.ContractError("Open V2 intent candidate is noncanonical")
    terminal_indices = [
        int(record["request"]["candidate_index"])
        for record in records
        if record["terminal_present"]
    ]
    missing_terminal = [index for index in appended if index not in terminal_indices]
    if missing_terminal:
        if (
            len(missing_terminal) != 1
            or not open_records
            or int(open_records[0]["request"]["candidate_index"])
            != missing_terminal[0]
        ):
            raise execution.ContractError("Committed V2 rejection lacks terminal receipt")
    return records


def _validate_open_boundary(
    config_path: Path,
    *,
    allow_open_v2_execution_id: str | None = None,
    release_identity: str | None = None,
    require_next_candidate: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config, parent = _verify_immutable_parents(config_path)
    full = execution.full_paths(config)
    chain_paths = state_chain.state_chain_paths(config)
    state_path, docs_state_path, ledger_path = state_chain._state_paths(config)

    records_before = _scan_wrapper_execution_roots(config)
    open_before = [record for record in records_before if not record["terminal_present"]]
    if len(open_before) > 1:
        raise execution.ContractError("Parallel V2 recovery intents exist")
    if allow_open_v2_execution_id is None:
        if open_before:
            raise execution.ContractError("Unexpected open V2 recovery intent exists")
    elif (
        len(open_before) != 1
        or open_before[0]["execution_id"] != allow_open_v2_execution_id
    ):
        raise execution.ContractError("Wrong V2 recovery intent is open")
    open_candidate_index = (
        int(open_before[0]["request"]["candidate_index"])
        if open_before
        else None
    )

    validation = state_chain.validate_state_chain_release(
        config_path, allow_open_execution_id=STATE_CHAIN_EXECUTION_ID
    )
    required_validation = {
        "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
        "chain_head_identity_sha256": CURRENT_HEAD_IDENTITY_SHA256,
        "completed_pair_count": CURRENT_COMPLETED_PAIR_COUNT,
        "pending_pair_count": CURRENT_PENDING_PAIR_COUNT,
        "first_pending_pair_id": PAIR_ID,
        "render_state_sha256": CURRENT_STATE_SHA256,
        "active_execution_id": STATE_CHAIN_EXECUTION_ID,
    }
    if any(validation.get(key) != value for key, value in required_validation.items()):
        raise execution.ContractError("Open V2 state-chain boundary changed")
    for key, expected in (
        ("model_loaded", False),
        ("inference_calls", 0),
        ("prediction_accessed", False),
        ("locked_test_outcome_accessed", False),
        ("registered_targets_used", False),
        ("external_services_modified", False),
        ("outcome_inputs", []),
    ):
        if validation.get(key) != expected:
            raise execution.ContractError("Open V2 state-chain access guard changed")

    _require_file_sha256(state_path, CURRENT_STATE_SHA256, "44/96 render state")
    _require_file_sha256(docs_state_path, CURRENT_STATE_SHA256, "44/96 docs state")
    state = execution.load_json(state_path)
    if (
        state.get("completed_pair_count") != CURRENT_COMPLETED_PAIR_COUNT
        or state.get("pending_pair_count") != CURRENT_PENDING_PAIR_COUNT
        or state.get("pending_pair_ids", [None])[0] != PAIR_ID
        or state.get("model_outputs_present") is not False
        or state.get("interrupted_staging_directories") != []
    ):
        raise execution.ContractError("44/96 render-state structure changed")

    intent_path = _state_chain_intent_path(config)
    _require_file_sha256(intent_path, STATE_CHAIN_INTENT_SHA256, "state-chain intent")
    state_intent = execution.load_json(intent_path)
    state_execution_root = intent_path.parent
    if (
        state_intent.get("execution_id") != STATE_CHAIN_EXECUTION_ID
        or state_intent.get("request", {}).get("target_pair_id") != PAIR_ID
        or state_intent.get("request", {}).get("max_new_pairs") != 1
        or state_intent.get("predecessor_head_identity_sha256")
        != CURRENT_HEAD_IDENTITY_SHA256
        or (state_execution_root / "state_chain_terminal_receipt.json").exists()
    ):
        raise execution.ContractError("Open state-chain intent binding changed")

    batch_root = _batch_root(config)
    batch_intent_path = batch_root / "batch_intent.json"
    _require_file_sha256(batch_intent_path, BATCH_INTENT_SHA256, "batch intent")
    batch_intent = execution.load_json(batch_intent_path)
    request = batch_intent.get("request", {})
    if (
        batch_intent.get("batch_id") != BATCH_ID
        or batch_intent.get("status")
        != "LOCKED_TEST_RENDER_BATCH_INTENT_PREOUTCOME_SYNTHETIC_ONLY"
        or batch_intent.get("request_identity_sha256") != execution.stable_sha256(request)
        or PAIR_ID not in request.get("target_pair_ids", [])
        or request.get("max_new_pairs") != 1
        or request.get("model_access_allowed") is not False
        or request.get("prediction_access_allowed") is not False
        or request.get("locked_test_outcome_access_allowed") is not False
        or (batch_root / "batch_receipt.json").exists()
    ):
        raise execution.ContractError("Open underlying batch intent changed")

    pair_root = full["synthetic"] / "pairs/locked_test" / PAIR_ID
    if pair_root.exists():
        raise execution.ContractError("Recovery pair was already published")
    if (
        chain_paths["executions"]
        / STATE_CHAIN_EXECUTION_ID
        / "state_chain_terminal_receipt.json"
    ).exists():
        raise execution.ContractError("State-chain execution became terminal")

    ledger = execution.read_jsonl(ledger_path)
    roster_rows = execution.full_roster_rows(config)
    roster_row = _pair_roster_row(roster_rows)
    appended_evidence = _validate_appended_rejection_rows(
        config,
        ledger_path,
        ledger,
        roster_rows,
        roster_row,
        allow_uncommitted_candidate_index=(
            open_candidate_index
            if open_candidate_index is not None
            and len(ledger) > BASE_LEDGER_ROW_COUNT
            and int(ledger[-1].get("candidate_index", -1)) == open_candidate_index
            else None
        ),
    )
    appended_indices = [
        int(row["candidate_index"]) for row in ledger[BASE_LEDGER_ROW_COUNT:]
    ]
    records = _validate_wrapper_execution_roots(
        config,
        ledger_path,
        appended_indices,
        allow_open_execution_id=allow_open_v2_execution_id,
        release_identity=release_identity,
    )

    recovery_root = (
        full["synthetic"] / "planning/locked_test_gt_source_cardinality_recovery_v1"
    )
    if recovery_root.exists() and list(recovery_root.glob(f".partial-{PAIR_ID}-candidate-*-*")):
        raise execution.ContractError("Partial V2 candidate recovery staging exists")

    next_candidate = _canonical_candidate(config, full["synthetic"], roster_row)
    if require_next_candidate and next_candidate is None:
        raise execution.ContractError("V2 recovery candidate roster exhausted")
    if not appended_indices and next_candidate is not None:
        if (
            next_candidate.get("candidate_index") != MIN_CANDIDATE_INDEX
            or next_candidate.get("candidate_identity_sha256")
            != INITIAL_CANDIDATE_IDENTITY_SHA256
            or next_candidate.get("source_template", {}).get("sha256")
            != INITIAL_SOURCE_TEMPLATE_SHA256
        ):
            raise execution.ContractError("Initial candidate-2 binding changed")

    boundary = {
        "completed_pair_count": CURRENT_COMPLETED_PAIR_COUNT,
        "pending_pair_count": CURRENT_PENDING_PAIR_COUNT,
        "first_pending_pair_id": PAIR_ID,
        "render_state_sha256": execution.sha256_file(state_path),
        "chain_head_identity_sha256": validation["chain_head_identity_sha256"],
        "candidate_rejection_ledger_prefix_sha256": BASE_LEDGER_SHA256,
        "candidate_rejection_ledger_sha256": execution.sha256_file(ledger_path),
        "candidate_rejection_ledger_row_count": len(ledger),
        "v2_appended_candidate_indices": appended_indices,
        "v2_appended_recovery_evidence": appended_evidence,
        "next_candidate_index": (
            int(next_candidate["candidate_index"]) if next_candidate is not None else None
        ),
        "next_candidate_identity_sha256": (
            next_candidate["candidate_identity_sha256"]
            if next_candidate is not None
            else None
        ),
        "next_source_template_sha256": (
            next_candidate["source_template"]["sha256"]
            if next_candidate is not None
            else None
        ),
        "state_chain_execution_id": STATE_CHAIN_EXECUTION_ID,
        "state_chain_intent_sha256": STATE_CHAIN_INTENT_SHA256,
        "underlying_batch_id": BATCH_ID,
        "underlying_batch_intent_sha256": BATCH_INTENT_SHA256,
        "open_v2_execution_id": allow_open_v2_execution_id,
        "v2_execution_count": len(records),
        "model_loaded": False,
        "inference_calls": 0,
        "prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "registered_targets_used": False,
        "external_services_modified": False,
        "outcome_inputs": [],
    }
    return config, parent, boundary


def _authorization_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": AUTHORIZATION_CONTRACT,
        "status": (
            "PASS_MANAGER_AUTHORIZED_REUSABLE_STATE_CHAIN_RECOVERY_V2_"
            "SYNTHETIC_ONLY"
        ),
        "authorization": {
            "manager_handoff_event_id": MANAGER_HANDOFF_EVENT_ID,
            "pass91_event_id": PASS91_EVENT_ID,
            "manager_session_id": MANAGER_SESSION_ID,
            "owner_session_id": OWNER_SESSION_ID,
            "goal_multi_repeat_run_id": RUN_ID,
            "pass": 91,
            "strategy": "base",
            "portfolio_id": PORTFOLIO_ID,
            "portfolio_lane": PORTFOLIO_LANE,
            "portfolio_revision": PORTFOLIO_REVISION,
        },
        "authorized_top_level_source_paths": [
            AUTHORIZED_SOURCE_PATH,
            AUTHORIZED_TEST_PATH,
        ],
        "authorized_open_execution": {
            "state_chain_execution_id": STATE_CHAIN_EXECUTION_ID,
            "underlying_batch_id": BATCH_ID,
            "pair_id": PAIR_ID,
            "fixed_state_sha256": CURRENT_STATE_SHA256,
            "fixed_head_identity_sha256": CURRENT_HEAD_IDENTITY_SHA256,
            "base_ledger_row_count": BASE_LEDGER_ROW_COUNT,
            "base_ledger_sha256": BASE_LEDGER_SHA256,
        },
        "authorized_candidate_scope": {
            "first_candidate_index": MIN_CANDIDATE_INDEX,
            "last_candidate_index": MAX_CANDIDATE_INDEX,
            "derive_exactly_one_with_execution_next_gt_scout_candidate": True,
            "caller_supplied_candidate_allowed": False,
            "lowest_unattempted_candidate_only": True,
            "sequential_same_pair_reuse_only": True,
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
            "model_prediction_outcome_or_target_access_allowed": False,
            "external_service_mutation_allowed": False,
        },
        "pass91_validation_only": True,
        "claim_boundary": _claim_boundary(config),
    }


def _bridge_payload(config: Mapping[str, Any], parents: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": BRIDGE_CONTRACT,
        "status": (
            "SEALED_REUSABLE_STATE_CHAIN_ZERO_SOURCE_WEED_RECOVERY_V2_"
            "SYNTHETIC_ONLY"
        ),
        "immutable_parents": copy.deepcopy(dict(parents)),
        "pinned_initial_boundary": _pinned_initial_boundary(),
        "canonical_derivation": {
            "function": "execution._next_gt_scout_candidate",
            "derive_after_all_parent_state_intent_and_ledger_checks": True,
            "one_candidate_per_invocation": True,
            "candidate_indices": list(
                range(MIN_CANDIDATE_INDEX, MAX_CANDIDATE_INDEX + 1)
            ),
            "candidate_identity_and_source_template_match_frozen_roster": True,
            "skip_or_arbitrary_identity_forbidden": True,
        },
        "ledger_contract": {
            "frozen_prefix_row_count": BASE_LEDGER_ROW_COUNT,
            "frozen_prefix_sha256": BASE_LEDGER_SHA256,
            "later_rows_same_pair_only": PAIR_ID,
            "later_candidate_indices_are_contiguous_from_two": True,
            "reason": "eligibility:source_weed_track_present",
            "legacy_terminal_and_decision_receipt_hashes_required": True,
            "append_only_and_idempotent": True,
        },
        "compatibility_mechanism": {
            "validate_before_wrapper_intent": True,
            "validate_before_candidate_gt_access": True,
            "patch_target": "execution.validate_full_plan",
            "replacement": (
                "functools.partial(extension_aware_state_chain_validate_full_plan, "
                f"allow_open_execution_id={STATE_CHAIN_EXECUTION_ID})"
            ),
            "unchanged_recovery_callable": True,
            "restore_full_callable_snapshot_in_finally": True,
            "reject_unexpected_callable_change": True,
        },
        "closure_conditions": {
            "render_state_or_chain_head_advance": True,
            "pair_publication": True,
            "state_chain_or_batch_terminal": True,
            "candidate_31_exhaustion": True,
        },
        "execution_contract": {
            "intent_contract": INTENT_CONTRACT,
            "terminal_receipt_contract": TERMINAL_RECEIPT_CONTRACT,
            "byte_identical_resume_only": True,
            "atomic_intent_and_terminal_receipt": True,
            "partial_or_parallel_intent_fails_closed": True,
            "published_or_ledger_committed_crash_resume_supported": True,
        },
        "pass91_access_guard": {
            "validation_only": True,
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


def _call_unchanged_recovery(
    config_path: Path, candidate_index: int
) -> dict[str, Any]:
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator is not installed before V2 bridge")
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
            candidate_index=candidate_index,
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


def recovery_bridge_v2_implementation_sha256() -> str:
    functions = (
        _verify_immutable_parents,
        _canonical_candidate,
        _validate_recovery_artifacts,
        _validate_appended_rejection_rows,
        _scan_wrapper_execution_roots,
        _validate_wrapper_execution_roots,
        _validate_open_boundary,
        _callable_snapshot,
        _assert_only_validator_changed,
        _restore_callable_snapshot,
        _call_unchanged_recovery,
        _publish_or_resume_intent,
        _validate_runtime_phase,
        _validate_terminal_receipt,
        run_state_chain_recovery_v2,
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
            "recovery_v1_release_identity_sha256": (
                RECOVERY_V1_RELEASE_IDENTITY_SHA256
            ),
            "recovery_implementation_sha256": RECOVERY_IMPLEMENTATION_SHA256,
            "recovery_lock_sha256": RECOVERY_LOCK_SHA256,
            "frozen_ledger_prefix_sha256": BASE_LEDGER_SHA256,
        }
    )


def _lock_payload(config: Mapping[str, Any], *, bridge_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": LOCK_CONTRACT,
        "status": "SEALED_REUSABLE_STATE_CHAIN_RECOVERY_V2_LOCK_SYNTHETIC_ONLY",
        "bridge_sha256": execution.require_sha256(bridge_sha256, "V2 bridge"),
        "bridge_implementation_sha256": recovery_bridge_v2_implementation_sha256(),
        "legacy_execution_script_sha256": LEGACY_EXECUTION_SCRIPT_SHA256,
        "state_chain_script_sha256": STATE_CHAIN_SCRIPT_SHA256,
        "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
        "recovery_v1_script_sha256": RECOVERY_V1_SCRIPT_SHA256,
        "recovery_v1_release_identity_sha256": RECOVERY_V1_RELEASE_IDENTITY_SHA256,
        "recovery_v1_terminal_receipt_sha256": RECOVERY_V1_TERMINAL_SHA256,
        "recovery_function_source_sha256": RECOVERY_FUNCTION_SOURCE_SHA256,
        "recovery_implementation_sha256": RECOVERY_IMPLEMENTATION_SHA256,
        "recovery_execution_lock_sha256": RECOVERY_LOCK_SHA256,
        "frozen_ledger_prefix_sha256": BASE_LEDGER_SHA256,
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
        "status": "SEALED_REUSABLE_STATE_CHAIN_RECOVERY_V2_RELEASE_SYNTHETIC_ONLY",
        "authorization_receipt_sha256": authorization_sha256,
        "bridge_sha256": bridge_sha256,
        "bridge_lock_sha256": lock_sha256,
        "bridge_script_sha256": execution.sha256_file(sources["bridge_v2"]),
        "bridge_test_sha256": execution.sha256_file(sources["bridge_v2_test"]),
        "bridge_implementation_sha256": recovery_bridge_v2_implementation_sha256(),
        "immutable_parents": copy.deepcopy(dict(parents)),
        "pinned_initial_boundary": _pinned_initial_boundary(),
        "authorized_candidate_indices": list(
            range(MIN_CANDIDATE_INDEX, MAX_CANDIDATE_INDEX + 1)
        ),
        "pass91_validation_only": True,
        "historical_parent_intent_receipt_pair_state_or_ledger_prefix_rewritten": False,
        "real_recovery_candidate_gt_or_render_access_during_pass91": False,
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
                if path.is_file() and path.name != "pass91_validation_receipt.json"
            ),
            key=lambda value: value.relative_to(root).as_posix(),
        )
    ]


def _pass91_boundary_receipt() -> dict[str, Any]:
    return {
        **_pinned_initial_boundary(),
        "candidate_rejection_ledger_prefix_sha256": BASE_LEDGER_SHA256,
        "v2_appended_candidate_indices": [],
        "next_candidate_index": MIN_CANDIDATE_INDEX,
        "next_candidate_identity_sha256": INITIAL_CANDIDATE_IDENTITY_SHA256,
        "next_source_template_sha256": INITIAL_SOURCE_TEMPLATE_SHA256,
        "v2_execution_count": 0,
        "open_v2_execution_id": None,
    }


def _validation_receipt_payload(
    config: Mapping[str, Any], release_root: Path, release: Mapping[str, Any]
) -> dict[str, Any]:
    rows = _artifact_rows(release_root)
    return {
        "schema_version": 1,
        "contract": VALIDATION_RECEIPT_CONTRACT,
        "status": "READY_FOR_MANAGER_VALIDATION_SYNTHETIC_ONLY",
        "goal_multi_repeat_run_id": RUN_ID,
        "event_id": PASS91_EVENT_ID,
        "pass": 91,
        "recovery_bridge_v2_release_identity_sha256": release[
            "release_identity_sha256"
        ],
        "validated_initial_open_boundary": _pass91_boundary_receipt(),
        "artifact_inventory": {
            "files": rows,
            "file_count": len(rows),
            "inventory_sha256": execution.stable_sha256(rows),
        },
        "pass91_access_guard": {
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
            raise execution.ContractError("V2 recovery release file set changed")
    for relative in required:
        if execution.sha256_file(
            paths["synthetic_release"] / relative
        ) != execution.sha256_file(paths["docs_release"] / relative):
            raise execution.ContractError("V2 recovery docs mirror changed")


def _validate_static_release_identity(
    config_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    config, parent = _verify_immutable_parents(config_path)
    paths = recovery_bridge_v2_paths(config)
    _validate_release_file_set(paths)
    authorization = execution.load_json(paths["authorization"])
    if authorization != _authorization_payload(config):
        raise execution.ContractError("V2 manager authorization changed")
    bridge = execution.load_json(paths["bridge"])
    if bridge != _bridge_payload(config, parent["parents"]):
        raise execution.ContractError("V2 recovery bridge changed")
    lock = execution.load_json(paths["lock"])
    if lock != _lock_payload(config, bridge_sha256=execution.sha256_file(paths["bridge"])):
        raise execution.ContractError("V2 recovery bridge lock changed")
    release = execution.load_json(paths["release"])
    expected_release = _release_payload(
        config,
        parent["parents"],
        authorization_sha256=execution.sha256_file(paths["authorization"]),
        bridge_sha256=execution.sha256_file(paths["bridge"]),
        lock_sha256=execution.sha256_file(paths["lock"]),
    )
    if release != expected_release:
        raise execution.ContractError("V2 recovery bridge release changed")
    identity_payload = copy.deepcopy(release)
    identity = identity_payload.pop("release_identity_sha256", None)
    if identity != execution.stable_sha256(identity_payload):
        raise execution.ContractError("V2 recovery release identity changed")
    receipt = execution.load_json(paths["validation_receipt"])
    if receipt != _validation_receipt_payload(config, paths["synthetic_release"], release):
        raise execution.ContractError("Pass91 V2 validation receipt changed")
    return config, parent, release


def _assert_pass91_initial_boundary(boundary: Mapping[str, Any]) -> None:
    expected = _pass91_boundary_receipt()
    observed = {
        key: boundary.get(key)
        for key in expected
        if key not in {
            "state_chain_terminal_receipt_present",
            "batch_terminal_receipt_present",
            "pair_publication_present",
            "recovery_v1_release_identity_sha256",
            "recovery_v1_terminal_receipt_sha256",
            "recovery_lock_sha256",
            "pair_id",
            "pair_slot_identity_sha256",
            "first_authorized_candidate_index",
            "first_authorized_candidate_identity_sha256",
            "first_authorized_source_template_sha256",
            "last_authorized_candidate_index",
        }
    }
    expected_observed = {key: expected[key] for key in observed}
    if observed != expected_observed or boundary.get("v2_appended_recovery_evidence") != []:
        raise execution.ContractError("Pass91 initial V2 boundary changed")


def seal_recovery_bridge_v2_release(config_path: Path) -> dict[str, Any]:
    config, parent, boundary = _validate_open_boundary(config_path)
    _assert_pass91_initial_boundary(boundary)
    paths = recovery_bridge_v2_paths(config)
    partials = list(paths["synthetic_release"].parent.glob(".partial-*")) + list(
        paths["docs_release"].parent.glob(".partial-*")
    )
    if partials:
        raise execution.ContractError("Partial V2 recovery release exists")
    if paths["executions"].exists() or paths["docs_executions"].exists():
        raise execution.ContractError("Pass91 V2 execution artifact exists")
    if paths["synthetic_release"].exists() or paths["docs_release"].exists():
        return validate_recovery_bridge_v2_release(config_path)

    synthetic_parent = paths["synthetic_release"].parent
    docs_parent = paths["docs_release"].parent
    synthetic_parent.mkdir(parents=True, exist_ok=True)
    docs_parent.mkdir(parents=True, exist_ok=True)
    staging = synthetic_parent / f".partial-recovery-v2-{uuid.uuid4().hex}"
    docs_staging = docs_parent / f".partial-recovery-v2-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        authorization = _authorization_payload(config)
        bridge = _bridge_payload(config, parent["parents"])
        execution.write_json(
            staging / "pass91_manager_authorization_receipt.json", authorization
        )
        execution.write_json(staging / "state_chain_recovery_bridge_v2.json", bridge)
        lock = _lock_payload(
            config,
            bridge_sha256=execution.sha256_file(
                staging / "state_chain_recovery_bridge_v2.json"
            ),
        )
        execution.write_json(staging / "state_chain_recovery_bridge_lock_v2.json", lock)
        release = _release_payload(
            config,
            parent["parents"],
            authorization_sha256=execution.sha256_file(
                staging / "pass91_manager_authorization_receipt.json"
            ),
            bridge_sha256=execution.sha256_file(
                staging / "state_chain_recovery_bridge_v2.json"
            ),
            lock_sha256=execution.sha256_file(
                staging / "state_chain_recovery_bridge_lock_v2.json"
            ),
        )
        execution.write_json(
            staging / "state_chain_recovery_bridge_release_v2.json", release
        )
        staging.replace(paths["synthetic_release"])
        receipt = _validation_receipt_payload(
            config, paths["synthetic_release"], release
        )
        execution.write_json(paths["validation_receipt"], receipt)
        shutil.copytree(paths["synthetic_release"], docs_staging)
        docs_staging.replace(paths["docs_release"])
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if docs_staging.exists():
            shutil.rmtree(docs_staging)
    return validate_recovery_bridge_v2_release(config_path)


def validate_recovery_bridge_v2_release(
    config_path: Path, *, allow_open_v2_execution_id: str | None = None
) -> dict[str, Any]:
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator was not restored")
    config, _, release = _validate_static_release_identity(config_path)
    _, _, boundary = _validate_open_boundary(
        config_path,
        allow_open_v2_execution_id=allow_open_v2_execution_id,
        release_identity=release["release_identity_sha256"],
        require_next_candidate=False,
    )
    paths = recovery_bridge_v2_paths(config)
    partials = list(paths["synthetic_release"].parent.glob(".partial-*")) + list(
        paths["docs_release"].parent.glob(".partial-*")
    )
    if partials:
        raise execution.ContractError("Partial V2 recovery release exists")
    return {
        "status": "READY_FOR_MANAGER_VALIDATION_SYNTHETIC_ONLY",
        "recovery_bridge_v2_release_identity_sha256": release[
            "release_identity_sha256"
        ],
        "completed_pair_count": boundary["completed_pair_count"],
        "pending_pair_count": boundary["pending_pair_count"],
        "first_pending_pair_id": boundary["first_pending_pair_id"],
        "candidate_rejection_ledger_row_count": boundary[
            "candidate_rejection_ledger_row_count"
        ],
        "candidate_rejection_ledger_sha256": boundary[
            "candidate_rejection_ledger_sha256"
        ],
        "next_candidate_index": boundary["next_candidate_index"],
        "next_candidate_identity_sha256": boundary[
            "next_candidate_identity_sha256"
        ],
        "v2_execution_count": boundary["v2_execution_count"],
        "real_recovery_bridge_intents_created_during_validation": 0,
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
) -> dict[str, Any]:
    candidate_index = int(candidate["candidate_index"])
    predecessor_count = BASE_LEDGER_ROW_COUNT + (
        candidate_index - MIN_CANDIDATE_INDEX
    )
    if (
        boundary.get("candidate_rejection_ledger_row_count") != predecessor_count
        or boundary.get("next_candidate_index") != candidate_index
        or boundary.get("next_candidate_identity_sha256")
        != candidate["candidate_identity_sha256"]
        or boundary.get("next_source_template_sha256")
        != candidate["source_template"]["sha256"]
    ):
        raise execution.ContractError("V2 request candidate is not the current canonical next")
    return {
        "schema_version": 1,
        "contract": CONTRACT,
        "recovery_bridge_v2_release_identity_sha256": execution.require_sha256(
            release_identity, "V2 recovery release identity"
        ),
        "state_chain_release_identity_sha256": STATE_CHAIN_RELEASE_IDENTITY_SHA256,
        "state_chain_execution_id": STATE_CHAIN_EXECUTION_ID,
        "state_chain_intent_sha256": STATE_CHAIN_INTENT_SHA256,
        "underlying_batch_id": BATCH_ID,
        "underlying_batch_intent_sha256": BATCH_INTENT_SHA256,
        "pair_id": PAIR_ID,
        "pair_slot_identity_sha256": PAIR_SLOT_IDENTITY_SHA256,
        "candidate_index": candidate_index,
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "source_template_sha256": candidate["source_template"]["sha256"],
        "predecessor_state_sha256": CURRENT_STATE_SHA256,
        "predecessor_head_identity_sha256": CURRENT_HEAD_IDENTITY_SHA256,
        "predecessor_ledger_sha256": boundary[
            "candidate_rejection_ledger_sha256"
        ],
        "predecessor_ledger_row_count": predecessor_count,
        "recovery_lock_sha256": RECOVERY_LOCK_SHA256,
        "rejection_authority": "exact_locked_validator_zero_source_weed_failure_only",
        "acceptance_authority": "none",
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
        "status": "STATE_CHAIN_RECOVERY_V2_INTENT_SYNTHETIC_ONLY",
        "execution_id": execution_id,
        "request_identity_sha256": request_identity,
        "request": copy.deepcopy(dict(request)),
        "boundary_at_start": {
            "render_state_sha256": CURRENT_STATE_SHA256,
            "chain_head_identity_sha256": CURRENT_HEAD_IDENTITY_SHA256,
            "candidate_rejection_ledger_sha256": request[
                "predecessor_ledger_sha256"
            ],
            "candidate_rejection_ledger_row_count": request[
                "predecessor_ledger_row_count"
            ],
            "completed_pair_count": CURRENT_COMPLETED_PAIR_COUNT,
            "pending_pair_count": CURRENT_PENDING_PAIR_COUNT,
            "first_pending_pair_id": PAIR_ID,
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


def _publish_or_resume_intent(
    parent: Path, execution_id: str, intent: Mapping[str, Any]
) -> tuple[Path, bool]:
    parent.mkdir(parents=True, exist_ok=True)
    if list(parent.glob(".partial-*")):
        raise execution.ContractError("Partial V2 recovery intent exists")
    roots = sorted(path for path in parent.iterdir() if path.is_dir())
    for other in roots:
        if other.name == execution_id:
            continue
        if not (other / "recovery_bridge_terminal_receipt.json").is_file():
            raise execution.ContractError("Parallel V2 recovery intent exists")
    root = parent / execution_id
    intent_path = root / "recovery_bridge_intent.json"
    if root.exists():
        if not intent_path.is_file() or execution.load_json(intent_path) != dict(intent):
            raise execution.ContractError("Existing V2 recovery intent changed")
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
    config, parent, boundary = _validate_open_boundary(
        config_path,
        allow_open_v2_execution_id=wrapper_execution_id,
        release_identity=release_identity,
        require_next_candidate=False,
    )
    candidate_index = int(request["candidate_index"])
    roster_row = _pair_roster_row(execution.full_roster_rows(config))
    candidate = _candidate_by_index(config, roster_row, candidate_index)
    if (
        request.get("candidate_identity_sha256")
        != candidate["candidate_identity_sha256"]
        or request.get("source_template_sha256")
        != candidate["source_template"]["sha256"]
    ):
        raise execution.ContractError("V2 runtime candidate binding changed")
    predecessor_count = int(request["predecessor_ledger_row_count"])
    current_count = int(boundary["candidate_rejection_ledger_row_count"])
    destination = _recovery_destination(config, candidate_index)
    evidence: dict[str, Any] = {}
    if current_count == predecessor_count:
        if (
            boundary["candidate_rejection_ledger_sha256"]
            != request["predecessor_ledger_sha256"]
            or boundary["next_candidate_index"] != candidate_index
        ):
            raise execution.ContractError("V2 recovery predecessor ledger changed")
        if destination.exists():
            evidence = _validate_recovery_artifacts(
                config, roster_row, candidate_index, require_commit=False
            )
            if evidence.get("ledger_commit_receipt_sha256") is not None:
                raise execution.ContractError(
                    "Recovery commit receipt exists without its ledger append"
                )
            phase = "published_uncommitted"
        else:
            if _recovery_docs_receipt(config, candidate_index).exists():
                raise execution.ContractError("Recovery docs receipt exists before recovery")
            phase = "ready"
    elif current_count == predecessor_count + 1:
        ledger_path = state_chain._state_paths(config)[2]
        ledger = execution.read_jsonl(ledger_path)
        last = ledger[-1]
        if (
            last.get("pair_id") != PAIR_ID
            or last.get("candidate_index") != candidate_index
            or last.get("candidate_identity_sha256")
            != candidate["candidate_identity_sha256"]
            or last.get("reason") != "eligibility:source_weed_track_present"
        ):
            raise execution.ContractError("V2 committed recovery row changed")
        evidence = _validate_recovery_artifacts(
            config, roster_row, candidate_index, require_commit=True
        )
        phase = "committed"
    else:
        raise execution.ContractError("V2 recovery ledger advanced by a noncanonical amount")
    return config, {
        **boundary,
        "candidate_index": candidate_index,
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "recovery_evidence": evidence,
    }, phase


def _validate_underlying_result(
    result: Mapping[str, Any], candidate_index: int
) -> None:
    if (
        result.get("status")
        not in {
            "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY",
            "SKIP_EXISTING_REJECT_ZERO_SOURCE_WEED_TRACKS_LOCKED_TEST_PREOUTCOME_SYNTHETIC_ONLY",
        }
        or result.get("pair_id") != PAIR_ID
        or result.get("candidate_index") != candidate_index
        or result.get("batch_id") != BATCH_ID
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
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    resumed: bool,
) -> dict[str, Any]:
    evidence = after["recovery_evidence"]
    return {
        "schema_version": 1,
        "contract": TERMINAL_RECEIPT_CONTRACT,
        "status": "PASS_EXACT_ZERO_SOURCE_WEED_REJECTION_V2_SYNTHETIC_ONLY",
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
            "recovery_terminal_receipt_sha256": evidence[
                "recovery_terminal_receipt_sha256"
            ],
            "decision_receipt_sha256": evidence["decision_receipt_sha256"],
            "ledger_commit_receipt_sha256": evidence[
                "ledger_commit_receipt_sha256"
            ],
        },
        "boundary": {
            "render_state_sha256_before": CURRENT_STATE_SHA256,
            "render_state_sha256_after": after["render_state_sha256"],
            "chain_head_identity_sha256_before": CURRENT_HEAD_IDENTITY_SHA256,
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
        "resume": {"resumed_from_existing_v2_intent": resumed},
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
    evidence = current.get("recovery_evidence", {})
    candidate_index = int(request["candidate_index"])
    valid = (
        receipt.get("schema_version") == 1
        and receipt.get("contract") == TERMINAL_RECEIPT_CONTRACT
        and receipt.get("status")
        == "PASS_EXACT_ZERO_SOURCE_WEED_REJECTION_V2_SYNTHETIC_ONLY"
        and receipt.get("execution_id") == execution_id
        and receipt.get("request_identity_sha256") == request_identity
        and receipt.get("request") == dict(request)
        and receipt.get("recovery_bridge_intent_sha256")
        == execution.sha256_file(intent_path)
        and receipt.get("state_chain_intent_sha256") == STATE_CHAIN_INTENT_SHA256
        and receipt.get("underlying_batch_intent_sha256") == BATCH_INTENT_SHA256
        and receipt.get("original_validator_restored") is True
        and legacy.get("pair_id") == PAIR_ID
        and legacy.get("candidate_index") == candidate_index
        and legacy.get("batch_id") == BATCH_ID
        and legacy.get("recovery_terminal_receipt_sha256")
        == evidence.get("recovery_terminal_receipt_sha256")
        and legacy.get("decision_receipt_sha256")
        == evidence.get("decision_receipt_sha256")
        and legacy.get("ledger_commit_receipt_sha256")
        == evidence.get("ledger_commit_receipt_sha256")
        and boundary.get("render_state_sha256_before") == CURRENT_STATE_SHA256
        and boundary.get("render_state_sha256_after") == CURRENT_STATE_SHA256
        and boundary.get("chain_head_identity_sha256_before")
        == CURRENT_HEAD_IDENTITY_SHA256
        and boundary.get("chain_head_identity_sha256_after")
        == CURRENT_HEAD_IDENTITY_SHA256
        and boundary.get("candidate_rejection_ledger_sha256_before")
        == request["predecessor_ledger_sha256"]
        and boundary.get("candidate_rejection_ledger_sha256_after")
        == current["candidate_rejection_ledger_sha256"]
        and boundary.get("candidate_rejection_ledger_row_count_before")
        == request["predecessor_ledger_row_count"]
        and boundary.get("candidate_rejection_ledger_row_count_after")
        == request["predecessor_ledger_row_count"] + 1
        and access
        == {
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
        and receipt.get("claim_boundary") == _claim_boundary(config)
    )
    if not valid:
        raise execution.ContractError("V2 recovery terminal receipt changed")


def _discover_open_v2_execution(config: Mapping[str, Any]) -> dict[str, Any] | None:
    records = _scan_wrapper_execution_roots(config)
    open_records = [record for record in records if not record["terminal_present"]]
    if len(open_records) > 1:
        raise execution.ContractError("Parallel V2 recovery intents exist")
    return open_records[0] if open_records else None


def run_state_chain_recovery_v2(config_path: Path) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config, _, release = _validate_static_release_identity(config_path)
    release_identity = release["release_identity_sha256"]
    paths = recovery_bridge_v2_paths(config)
    open_record = _discover_open_v2_execution(config)

    if open_record is None:
        validation = validate_recovery_bridge_v2_release(config_path)
        _, _, boundary = _validate_open_boundary(
            config_path,
            release_identity=release_identity,
            require_next_candidate=True,
        )
        candidate_index = boundary["next_candidate_index"]
        if candidate_index is None:
            raise execution.ContractError("V2 recovery candidate roster exhausted")
        roster_row = _pair_roster_row(execution.full_roster_rows(config))
        candidate = _candidate_by_index(config, roster_row, int(candidate_index))
        request = _request(release_identity, boundary, candidate)
        execution_id, request_identity = _execution_identity(request)
        intent = _intent_payload(
            config, request, execution_id, request_identity
        )
        execution_root, resumed = _publish_or_resume_intent(
            paths["executions"], execution_id, intent
        )
        if validation["recovery_bridge_v2_release_identity_sha256"] != release_identity:
            raise execution.ContractError("V2 release identity changed before intent")
    else:
        execution_id = open_record["execution_id"]
        request = open_record["request"]
        request_identity = open_record["request_identity_sha256"]
        expected_id, expected_identity = _execution_identity(request)
        if (
            expected_id != execution_id
            or expected_identity != request_identity
            or request.get("recovery_bridge_v2_release_identity_sha256")
            != release_identity
        ):
            raise execution.ContractError("Existing V2 recovery request changed")
        execution_root = open_record["root"]
        resumed = True

    intent_path = execution_root / "recovery_bridge_intent.json"
    terminal_path = execution_root / "recovery_bridge_terminal_receipt.json"
    docs_terminal = paths["docs_executions"] / f"{execution_id}.json"
    expected_intent = _intent_payload(config, request, execution_id, request_identity)
    if execution.load_json(intent_path) != expected_intent:
        raise execution.ContractError("V2 recovery intent changed after publication")

    _, before, phase_before = _validate_runtime_phase(
        config_path,
        wrapper_execution_id=execution_id,
        request=request,
        release_identity=release_identity,
    )
    candidate_index = int(request["candidate_index"])
    if phase_before == "committed":
        underlying = {
            "status": (
                "SKIP_EXISTING_REJECT_ZERO_SOURCE_WEED_TRACKS_"
                "LOCKED_TEST_PREOUTCOME_SYNTHETIC_ONLY"
            ),
            "pair_id": PAIR_ID,
            "candidate_index": candidate_index,
            "batch_id": BATCH_ID,
            "model_loaded": False,
            "inference_calls": 0,
            "synthetic_only": True,
        }
    else:
        underlying = _call_unchanged_recovery(config_path, candidate_index)
    _validate_underlying_result(underlying, candidate_index)
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator was not restored after V2 recovery")
    _, after, phase_after = _validate_runtime_phase(
        config_path,
        wrapper_execution_id=execution_id,
        request=request,
        release_identity=release_identity,
    )
    if phase_after != "committed":
        raise execution.ContractError("V2 rejection was not atomically committed")

    terminal = _terminal_payload(
        config,
        request,
        request_identity,
        execution_id,
        intent_path,
        underlying,
        before,
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
        "candidate_index": candidate_index,
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
    subparsers.add_parser("recover")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "seal":
            result = seal_recovery_bridge_v2_release(args.config)
        elif args.command == "validate":
            result = validate_recovery_bridge_v2_release(args.config)
        else:
            result = run_state_chain_recovery_v2(args.config)
    except execution.ContractError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
