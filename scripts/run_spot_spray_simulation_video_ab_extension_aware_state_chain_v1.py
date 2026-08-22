#!/usr/bin/env python3
"""Seal, validate, and run the extension-aware monotonic state-chain adapter.

This is a separate, append-only compatibility epoch.  It preserves the
legacy renderer, the extension-aware full-plan validator, and the Pass66 batch
adapter byte-for-byte.  The only execution bridge temporarily replaces
``execution.validate_full_plan`` while calling the unchanged model-free
``run_locked_test_render_batch`` function, then restores the original callable
in a ``finally`` block.

The transition journal is a directory of immutable atomic commits.  Every
commit contains one transition record, the exact result state, the exact
append-only rejection ledger, and a hash-linked head.  A batch intent may
exist while the unchanged renderer is running; no later request is admitted
until that exact intent is either committed or resumed idempotently.
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
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_spot_spray_simulation_video_ab_execution_v1 as execution
from scripts import run_spot_spray_simulation_video_ab_extension_aware_batch_v1 as adapter
from scripts import validate_spot_spray_simulation_video_ab_extension_aware_v1 as validator


DEFAULT_CONFIG = adapter.DEFAULT_CONFIG

CONTRACT = "spot_spray_simulation_video_ab_extension_aware_state_chain_v1"
AUTHORIZATION_CONTRACT = f"{CONTRACT}_manager_authorization"
ROOT_CONTRACT = f"{CONTRACT}_root"
LOCK_CONTRACT = f"{CONTRACT}_lock"
RELEASE_CONTRACT = f"{CONTRACT}_release"
VALIDATION_RECEIPT_CONTRACT = f"{CONTRACT}_pass70_validation"
TRANSITION_CONTRACT = f"{CONTRACT}_transition"
HEAD_CONTRACT = f"{CONTRACT}_head"
COMMIT_CONTRACT = f"{CONTRACT}_atomic_commit"
INTENT_CONTRACT = f"{CONTRACT}_intent"
TERMINAL_RECEIPT_CONTRACT = f"{CONTRACT}_terminal_receipt"

PASS70_EVENT_ID = "scheduled-resume-20260820071103-366db80fd093"
PASS69_EVENT_ID = "scheduled-resume-20260820065636-42b8053e32b4"
OWNER_SESSION_ID = "01a0019e-e810-73b3-9f29-ffad14c34ec5"
RUN_ID = "goal-multi-repeat-full-simulation-video-ab-execution-v1-e2dcf4ac8b10"
PORTFOLIO_ID = "goal-multi-repeat-agents-spot-spray-simulation-video-ab-v1-b8e46607aeea"
PORTFOLIO_LANE = "full-simulation-video-ab-execution-v1"

AUTHORIZED_SOURCE_PATH = (
    "scripts/run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1.py"
)
AUTHORIZED_TEST_PATH = (
    "tests/test_run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1.py"
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
RUNTIME_CONFIG_SHA256 = adapter.RUNTIME_CONFIG_SHA256
RUNTIME_RELEASE_FILE_SHA256 = adapter.RUNTIME_RELEASE_FILE_SHA256
RUNTIME_RELEASE_IDENTITY_SHA256 = adapter.RUNTIME_RELEASE_IDENTITY_SHA256
VALIDATOR_RELEASE_FILE_SHA256 = adapter.VALIDATOR_RELEASE_FILE_SHA256
VALIDATOR_RELEASE_IDENTITY_SHA256 = adapter.VALIDATOR_RELEASE_IDENTITY_SHA256
ADAPTER_RELEASE_FILE_SHA256 = (
    "759ddf0f17d2e6a2ac5637dc55b5f0f8360b0ced71ec89637aec61917cf5d96e"
)
ADAPTER_RELEASE_IDENTITY_SHA256 = (
    "5708c05e2421f32f5012d4990f70ecff74cef2c2687055432ac434d8738f33af"
)
HISTORICAL_ROSTER_SHA256 = adapter.HISTORICAL_ROSTER_SHA256
EXTENSION_MANIFEST_SHA256 = adapter.EXTENSION_MANIFEST_SHA256
COMBINED_ROSTER_IDENTITY_SHA256 = adapter.COMBINED_ROSTER_IDENTITY_SHA256
LOCKED_TEST_BATCH_FUNCTION_SOURCE_SHA256 = (
    adapter.LOCKED_TEST_BATCH_FUNCTION_SOURCE_SHA256
)
LOCKED_TEST_BATCH_IMPLEMENTATION_SHA256 = (
    adapter.LOCKED_TEST_BATCH_IMPLEMENTATION_SHA256
)

ROOT_PREDECESSOR_STATE_SHA256 = (
    "0e2f0ed5143dca870b3e7d4c9096bd79025b2bc7456d77dc4e1f2d0fbd9457f5"
)
ROOT_RESULT_STATE_SHA256 = (
    "7ab698a03479c2e7899c17d17e7abf0a2d08a0556585abf10769c14993efcbce"
)
ROOT_LEDGER_SHA256 = (
    "3c60ebab9c892418a0a3edd144eb372db2614162dcdc8999451ec4cd2b2ee81a"
)
ROOT_LEDGER_ROW_COUNT = 111
ROOT_TRANSITION_PAIR_ID = "locked_test_c001_r01"
ROOT_TRANSITION_CANDIDATE_INDEX = 0
ROOT_TRANSITION_CANDIDATE_IDENTITY_SHA256 = (
    "7b408747b0700dec122a69328eb5c6e20fcdc5309802da80760310a9eedc3e63"
)
ROOT_CANONICAL_GT_SHA256 = (
    "a6ea2e1d2d9f9aa9f5890aee2931676a045c5046276f6d5991a4900781929604"
)
PASS69_PUBLICATION_RECEIPT_SHA256 = (
    "243a640d122a8de8ad5726511d5e8604c57e314171aa5a5502ef7631b19ad360"
)
PASS69_BLOCKER_RECEIPT_SHA256 = (
    "4edb0c28fd0a00d84193c5e41035780b4a3200919bbb034417cd9fab6029e0db"
)
ROOT_FULL_PAIR_RECEIPT_SHA256 = (
    "979af2af4698440fa1571f94f575157ccf9bc46fbf857573c26fabbde1d54d7f"
)
ROOT_PAIR_RECEIPT_SHA256 = (
    "80aad23ff27e02df1fe680b72d7458ffa048f91b06aa5d72d0c7b3f6d3f34932"
)
ROOT_BATCH_RECEIPT_SHA256 = (
    "03df232fdafe05f5f4d4a545a6672f505b6c1cfe91feb6098ff714d91b5905d2"
)
ROOT_BATCH_INTENT_SHA256 = (
    "7c2dafd4fda1c5314f633e8fbbd09e63dd87b62b979b29a2c7ccb84ba3d60114"
)
ROOT_ADAPTER_TERMINAL_SHA256 = (
    "d358ad0f259c87208536848618c065d1c367cf4ce2ff885ed0afcd98e850af4a"
)
ROOT_ADAPTER_INTENT_SHA256 = (
    "bf8dd36ef75699103534e4d4c45a0ffdad8581c844fbf576bd5d208e326c8523"
)
ROOT_CONTACT_SHEET_SHA256 = (
    "6e98758e84c4605fb9b68cd063c8ee0c409a2894cc87c1759da9e1a2db3d7442"
)

ROOT_ADAPTER_EXECUTION_ID = (
    "extension_aware_batch_locked_test_c001_r01_48b730ee3678d4c1"
)
ROOT_BATCH_ID = "locked_test_render_batch_locked_test_c001_r01_4e96fb208fd0a54f"

_ORIGINAL_VALIDATE_FULL_PLAN = execution.validate_full_plan


def state_chain_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    full = execution.full_paths(config)
    synthetic_root = full["synthetic"] / "planning/extension_aware_state_chain_v1"
    docs_root = full["docs"] / "extension_aware_state_chain_v1"
    return {
        "synthetic_root": synthetic_root,
        "docs_root": docs_root,
        "release": synthetic_root / "release_v1",
        "docs_release": docs_root / "release_v1",
        "authorization": synthetic_root
        / "release_v1/pass70_manager_authorization_receipt.json",
        "chain_root": synthetic_root / "release_v1/monotonic_state_chain_root_v1.json",
        "lock": synthetic_root / "release_v1/monotonic_state_chain_lock_v1.json",
        "release_file": synthetic_root
        / "release_v1/extension_aware_state_chain_release_v1.json",
        "validation_receipt": synthetic_root / "release_v1/pass70_validation_receipt.json",
        "commits": synthetic_root / "transition_chain_v1/commits",
        "docs_commits": docs_root / "transition_chain_v1/commits",
        "executions": synthetic_root / "executions",
        "docs_executions": docs_root / "executions",
    }


def _required_release_files() -> list[str]:
    return [
        "extension_aware_state_chain_release_v1.json",
        "monotonic_state_chain_lock_v1.json",
        "monotonic_state_chain_root_v1.json",
        "pass70_manager_authorization_receipt.json",
        "pass70_validation_receipt.json",
    ]


def _required_commit_files() -> list[str]:
    return [
        "commit_manifest.json",
        "head.json",
        "result_ledger.jsonl",
        "result_state.json",
        "transition_record.json",
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


def _parent_source_paths() -> dict[str, Path]:
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
    }


def _verify_immutable_parents(config_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    resolved = config_path.expanduser().resolve()
    if resolved != DEFAULT_CONFIG.expanduser().resolve():
        raise execution.ContractError("Noncanonical state-chain runtime config")
    _require_file_sha256(resolved, RUNTIME_CONFIG_SHA256, "runtime config")
    expected_sources = {
        "legacy_execution": LEGACY_EXECUTION_SCRIPT_SHA256,
        "legacy_test": LEGACY_EXECUTION_TEST_SHA256,
        "validator": VALIDATOR_SCRIPT_SHA256,
        "validator_test": VALIDATOR_TEST_SHA256,
        "adapter": ADAPTER_SCRIPT_SHA256,
        "adapter_test": ADAPTER_TEST_SHA256,
    }
    for name, path in _parent_source_paths().items():
        _require_file_sha256(path, expected_sources[name], name.replace("_", " "))
    if execution.stable_sha256(
        inspect.getsource(execution.run_locked_test_render_batch)
    ) != LOCKED_TEST_BATCH_FUNCTION_SOURCE_SHA256:
        raise execution.ContractError("Locked-test batch function source changed")
    if (
        execution.locked_test_render_batch_implementation_sha256()
        != LOCKED_TEST_BATCH_IMPLEMENTATION_SHA256
    ):
        raise execution.ContractError("Locked-test batch implementation changed")

    config = execution.load_config(resolved)
    runtime_paths = execution.runtime_compatibility_paths(
        execution.load_config(execution.DEFAULT_CONFIG)
    )
    _require_file_sha256(
        runtime_paths["release"], RUNTIME_RELEASE_FILE_SHA256, "runtime release"
    )
    validator_paths = validator.validation_paths(config)
    _require_file_sha256(
        validator_paths["release"],
        VALIDATOR_RELEASE_FILE_SHA256,
        "extension-aware validator release",
    )
    adapter_paths = adapter.adapter_paths(config)
    _require_file_sha256(
        adapter_paths["release"],
        ADAPTER_RELEASE_FILE_SHA256,
        "extension-aware batch adapter release",
    )
    adapter_release = adapter._validate_static_release_identity(config)
    if (
        adapter_release.get("release_identity_sha256")
        != ADAPTER_RELEASE_IDENTITY_SHA256
    ):
        raise execution.ContractError("Adapter parent release identity changed")

    historical, combined = validator._rosters(config)
    if (
        len(historical) != 96
        or len(combined) != 96
        or execution.stable_sha256(combined) != COMBINED_ROSTER_IDENTITY_SHA256
    ):
        raise execution.ContractError("Combined roster identity changed")
    _require_file_sha256(
        execution.roster_extension_paths(config)["manifest"],
        EXTENSION_MANIFEST_SHA256,
        "roster extension manifest",
    )
    parents = {
        **expected_sources,
        "runtime_config_sha256": RUNTIME_CONFIG_SHA256,
        "runtime_release_file_sha256": RUNTIME_RELEASE_FILE_SHA256,
        "runtime_release_identity_sha256": RUNTIME_RELEASE_IDENTITY_SHA256,
        "validator_release_file_sha256": VALIDATOR_RELEASE_FILE_SHA256,
        "validator_release_identity_sha256": VALIDATOR_RELEASE_IDENTITY_SHA256,
        "adapter_release_file_sha256": ADAPTER_RELEASE_FILE_SHA256,
        "adapter_release_identity_sha256": ADAPTER_RELEASE_IDENTITY_SHA256,
        "historical_roster_sha256": HISTORICAL_ROSTER_SHA256,
        "extension_manifest_sha256": EXTENSION_MANIFEST_SHA256,
        "combined_roster_identity_sha256": COMBINED_ROSTER_IDENTITY_SHA256,
        "locked_test_batch_function_source_sha256": (
            LOCKED_TEST_BATCH_FUNCTION_SOURCE_SHA256
        ),
        "locked_test_batch_implementation_sha256": (
            LOCKED_TEST_BATCH_IMPLEMENTATION_SHA256
        ),
    }
    return config, {"parents": parents, "historical": historical, "combined": combined}


def _state_paths(config: Mapping[str, Any]) -> tuple[Path, Path, Path]:
    full = execution.full_paths(config)
    return (
        full["synthetic"] / "planning/render_state_v1.json",
        full["docs"] / "render_state_v1.json",
        full["synthetic"] / "planning/candidate_rejection_ledger_v1.jsonl",
    )


def _canonical_pair_ids(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(row["pair_id"]) for row in rows]


def _validate_state_shape(
    state: Mapping[str, Any], pair_ids: Sequence[str], *, minimum_completed: int = 42
) -> dict[str, Any]:
    required = {
        "planned_pair_count",
        "completed_pair_count",
        "pending_pair_count",
        "completed_pair_ids",
        "pending_pair_ids",
        "interrupted_staging_directories",
        "model_outputs_present",
    }
    if set(state) != required:
        raise execution.ContractError("Render state field set changed")
    completed = state.get("completed_pair_count")
    pending = state.get("pending_pair_count")
    if (
        not isinstance(completed, int)
        or isinstance(completed, bool)
        or not isinstance(pending, int)
        or isinstance(pending, bool)
        or completed < minimum_completed
        or completed > len(pair_ids)
        or pending != len(pair_ids) - completed
        or state.get("planned_pair_count") != len(pair_ids)
        or list(state.get("completed_pair_ids", [])) != list(pair_ids[:completed])
        or list(state.get("pending_pair_ids", [])) != list(pair_ids[completed:])
        or state.get("interrupted_staging_directories") != []
        or state.get("model_outputs_present") is not False
    ):
        raise execution.ContractError("Render state is not a canonical monotonic prefix")
    return {
        "completed_pair_count": completed,
        "pending_pair_count": pending,
        "last_completed_pair_id": pair_ids[completed - 1] if completed else None,
        "first_pending_pair_id": pair_ids[completed] if pending else None,
    }


def _validate_state_transition(
    predecessor: Mapping[str, Any],
    result: Mapping[str, Any],
    pair_ids: Sequence[str],
    pair_id: str,
) -> dict[str, Any]:
    before = _validate_state_shape(predecessor, pair_ids, minimum_completed=41)
    after = _validate_state_shape(result, pair_ids, minimum_completed=42)
    if (
        after["completed_pair_count"] != before["completed_pair_count"] + 1
        or pair_id != before["first_pending_pair_id"]
        or after["last_completed_pair_id"] != pair_id
        or list(result["completed_pair_ids"])
        != [*list(predecessor["completed_pair_ids"]), pair_id]
        or list(result["pending_pair_ids"])
        != list(predecessor["pending_pair_ids"])[1:]
    ):
        raise execution.ContractError("State transition is not one canonical append")
    return {
        "from_completed_pair_count": before["completed_pair_count"],
        "to_completed_pair_count": after["completed_pair_count"],
        "appended_pair_id": pair_id,
        "first_pending_pair_id": after["first_pending_pair_id"],
    }


def _validate_ledger_rows(
    rows: Sequence[Mapping[str, Any]], roster: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    by_pair = {str(row["pair_id"]): row for row in roster}
    identities: set[tuple[str, int]] = set()
    indices: dict[str, list[int]] = defaultdict(list)
    pair_positions = {str(row["pair_id"]): index for index, row in enumerate(roster)}
    last_position = -1
    for ledger_row in rows:
        pair_id = str(ledger_row.get("pair_id", ""))
        if pair_id not in by_pair:
            raise execution.ContractError("Ledger row escaped the sealed roster")
        candidate_index = ledger_row.get("candidate_index")
        if (
            not isinstance(candidate_index, int)
            or isinstance(candidate_index, bool)
            or candidate_index < 0
            or candidate_index >= 32
        ):
            raise execution.ContractError("Ledger candidate index is noncanonical")
        identity = (pair_id, candidate_index)
        if identity in identities:
            raise execution.ContractError("Ledger candidate identity is duplicated")
        identities.add(identity)
        candidate = by_pair[pair_id]["candidates"][candidate_index]
        if (
            ledger_row.get("schema_version") != 1
            or ledger_row.get("candidate_identity_sha256")
            != candidate["candidate_identity_sha256"]
            or ledger_row.get("model_or_outcome_inputs_used") is not False
            or ledger_row.get("reason_type")
            not in {"CandidateRejected", "GtScoutCandidateRejected"}
        ):
            raise execution.ContractError("Ledger rejection row binding changed")
        position = pair_positions[pair_id]
        if position < last_position:
            raise execution.ContractError("Ledger pair order rolled back")
        last_position = position
        indices[pair_id].append(candidate_index)
    for pair_id, observed in indices.items():
        if observed != list(range(len(observed))):
            raise execution.ContractError(
                f"Ledger candidate order is not a zero-based prefix: {pair_id}"
            )
    return {
        "row_count": len(rows),
        "unique_candidate_rejection_count": len(identities),
        "candidate_indices_by_pair": dict(indices),
    }


def _validate_ledger_extension(
    predecessor: Sequence[Mapping[str, Any]],
    result: Sequence[Mapping[str, Any]],
    roster: Sequence[Mapping[str, Any]],
    pair_id: str,
) -> dict[str, Any]:
    _validate_ledger_rows(predecessor, roster)
    summary = _validate_ledger_rows(result, roster)
    if list(result[: len(predecessor)]) != list(predecessor):
        raise execution.ContractError("Candidate rejection ledger prefix changed")
    appended = list(result[len(predecessor) :])
    if any(str(row["pair_id"]) != pair_id for row in appended):
        raise execution.ContractError("Ledger append escaped the active pair")
    return {
        **summary,
        "appended_row_count": len(appended),
        "append_only_prefix_preserved": True,
    }


def _pair_root(
    config: Mapping[str, Any], roster_row: Mapping[str, Any]
) -> Path:
    return (
        execution.full_paths(config)["synthetic"]
        / "pairs"
        / str(roster_row["protocol_split"])
        / str(roster_row["pair_id"])
    )


def _validate_published_pair(
    config: Mapping[str, Any],
    historical_row: Mapping[str, Any],
    combined_row: Mapping[str, Any],
    ledger_indices: Sequence[int],
) -> dict[str, Any]:
    root = _pair_root(config, combined_row)
    full_receipt_path = root / "full_pair_receipt.json"
    pair_receipt_path = root / "pair_receipt.json"
    if not full_receipt_path.is_file() or not pair_receipt_path.is_file():
        raise execution.ContractError("Published pair receipt is missing")
    full_receipt = execution.load_json(full_receipt_path)
    execution._validate_publishable_full_pair_receipt(full_receipt, combined_row)
    selected = full_receipt.get("selected_candidate_index")
    if not isinstance(selected, int) or isinstance(selected, bool) or not 0 <= selected <= 31:
        raise execution.ContractError("Published pair selected an unsealed candidate")
    if list(ledger_indices) != list(range(selected)):
        raise execution.ContractError("Published pair did not select the lowest passing candidate")
    candidate = combined_row["candidates"][selected]
    historical_epoch = selected <= 9
    if historical_epoch:
        if candidate != historical_row["candidates"][selected]:
            raise execution.ContractError("Historical candidate receipt was rebound")
    elif len(historical_row["candidates"]) != 10:
        raise execution.ContractError("Extension candidate epoch is ambiguous")
    if (
        full_receipt.get("candidate_identity_sha256")
        != candidate["candidate_identity_sha256"]
        or full_receipt.get("candidate_seeds") != candidate["seeds"]
        or full_receipt.get("source_template") != candidate["source_template"]
        or full_receipt.get("model_loaded") is not False
        or full_receipt.get("inference_calls") != 0
        or full_receipt.get("outcome_inputs") != []
        or full_receipt.get("claim_boundary") != _claim_boundary(config)
        or not all(full_receipt.get("pair_quality_gates", {}).values())
    ):
        raise execution.ContractError("Published pair epoch or access binding changed")
    if execution.sha256_file(pair_receipt_path) != full_receipt.get("pair_receipt_sha256"):
        raise execution.ContractError("Published pair receipt hash changed")
    pair_receipt = execution.load_json(pair_receipt_path)
    arm_gt = pair_receipt.get("arm_gt_identity", {})
    if (
        pair_receipt.get("pair_id") != combined_row["pair_id"]
        or pair_receipt.get("canonical_gt_sha256")
        != full_receipt.get("canonical_gt_sha256")
        or arm_gt.get("byte_identical") is not True
        or arm_gt.get("shared_paths") is not True
        or arm_gt.get("ideal") != pair_receipt.get("canonical_gt_sha256")
        or arm_gt.get("degraded") != pair_receipt.get("canonical_gt_sha256")
        or pair_receipt.get("frame_count_per_arm") != 30
        or pair_receipt.get("frame_rate_hz") != 15
        or pair_receipt.get("native_dimensions_px") != [2048, 2048]
        or not all(pair_receipt.get("quality_gates", {}).values())
    ):
        raise execution.ContractError("Published pair GT or native contract changed")
    video_hashes: dict[str, str] = {}
    for arm, relative_root in (
        ("ideal", root / "ideal"),
        ("degraded", root / "degraded"),
        ("side_by_side", root),
    ):
        media = pair_receipt.get("videos", {}).get(arm, {})
        path = relative_root / str(media.get("path", ""))
        digest = str(media.get("sha256", ""))
        if (
            not path.is_file()
            or execution.sha256_file(path) != digest
            or media.get("decoded_frame_count") != 30
            or media.get("average_frame_rate") != "15/1"
        ):
            raise execution.ContractError("Published native video receipt changed")
        video_hashes[arm] = digest
    return {
        "pair_id": combined_row["pair_id"],
        "protocol_split": combined_row["protocol_split"],
        "pair_slot_identity_sha256": combined_row["pair_slot_identity_sha256"],
        "receipt_epoch": "historical_v1" if historical_epoch else "extension_v1",
        "selected_candidate_index": selected,
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "canonical_gt_sha256": full_receipt["canonical_gt_sha256"],
        "full_pair_receipt_sha256": execution.sha256_file(full_receipt_path),
        "pair_receipt_sha256": execution.sha256_file(pair_receipt_path),
        "video_sha256": video_hashes,
        "identical_arm_gt": True,
        "all_frozen_pair_gates_passed": True,
    }


def _validate_all_published_pairs(
    config: Mapping[str, Any],
    historical: Sequence[Mapping[str, Any]],
    combined: Sequence[Mapping[str, Any]],
    state: Mapping[str, Any],
    ledger: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    indices: dict[str, list[int]] = defaultdict(list)
    for row in ledger:
        indices[str(row["pair_id"])].append(int(row["candidate_index"]))
    evidence: list[dict[str, Any]] = []
    for index, pair_id in enumerate(state["completed_pair_ids"]):
        if pair_id != combined[index]["pair_id"]:
            raise execution.ContractError("Completed pair prefix order changed")
        evidence.append(
            _validate_published_pair(
                config, historical[index], combined[index], indices.get(pair_id, [])
            )
        )
    completed = set(state["completed_pair_ids"])
    pending_ledger_pairs = sorted(
        pair_id for pair_id in indices if pair_id not in completed
    )
    if pending_ledger_pairs:
        raise execution.ContractError("Uncommitted pending-pair ledger rows exist")
    return evidence


def _root_evidence_paths(config: Mapping[str, Any]) -> dict[str, Path]:
    full = execution.full_paths(config)
    pair_root = full["synthetic"] / "pairs/locked_test" / ROOT_TRANSITION_PAIR_ID
    batch_root = (
        full["synthetic"] / "planning/locked_test_render_batches_v1" / ROOT_BATCH_ID
    )
    adapter_root = (
        adapter.adapter_paths(config)["executions"] / ROOT_ADAPTER_EXECUTION_ID
    )
    pass69_root = (
        full["docs"]
        / "locked_test_render_batches/pass67_extension_aware_adapter_execution"
    )
    return {
        "pass69_publication": pass69_root / "pass69_publication_validation_receipt.json",
        "pass69_blocker": pass69_root / "pass69_next_state_blocker_receipt.json",
        "full_pair_receipt": pair_root / "full_pair_receipt.json",
        "pair_receipt": pair_root / "pair_receipt.json",
        "contact_sheet": pair_root / "preoutcome_audit_contact_sheet.png",
        "batch_intent": batch_root / "batch_intent.json",
        "batch_receipt": batch_root / "batch_receipt.json",
        "adapter_intent": adapter_root / "adapter_intent.json",
        "adapter_terminal": adapter_root / "adapter_terminal_receipt.json",
    }


def _verify_root_evidence(config: Mapping[str, Any]) -> dict[str, str]:
    expected = {
        "pass69_publication": PASS69_PUBLICATION_RECEIPT_SHA256,
        "pass69_blocker": PASS69_BLOCKER_RECEIPT_SHA256,
        "full_pair_receipt": ROOT_FULL_PAIR_RECEIPT_SHA256,
        "pair_receipt": ROOT_PAIR_RECEIPT_SHA256,
        "contact_sheet": ROOT_CONTACT_SHEET_SHA256,
        "batch_intent": ROOT_BATCH_INTENT_SHA256,
        "batch_receipt": ROOT_BATCH_RECEIPT_SHA256,
        "adapter_intent": ROOT_ADAPTER_INTENT_SHA256,
        "adapter_terminal": ROOT_ADAPTER_TERMINAL_SHA256,
    }
    for name, path in _root_evidence_paths(config).items():
        _require_file_sha256(path, expected[name], f"root evidence {name}")
    publication = execution.load_json(_root_evidence_paths(config)["pass69_publication"])
    transition = publication.get("atomic_state_transition", {})
    pair = publication.get("pair_publication", {})
    access = publication.get("access_guard", {})
    if (
        publication.get("status")
        != "PASS_ATOMIC_LOCKED_TEST_PAIR_PUBLICATION_SYNTHETIC_ONLY"
        or transition.get("render_state_sha256_before")
        != ROOT_PREDECESSOR_STATE_SHA256
        or transition.get("render_state_sha256_after") != ROOT_RESULT_STATE_SHA256
        or transition.get("candidate_rejection_ledger_sha256_before")
        != ROOT_LEDGER_SHA256
        or transition.get("candidate_rejection_ledger_sha256_after")
        != ROOT_LEDGER_SHA256
        or pair.get("pair_id") != ROOT_TRANSITION_PAIR_ID
        or pair.get("selected_candidate_index") != ROOT_TRANSITION_CANDIDATE_INDEX
        or pair.get("candidate_identity_sha256")
        != ROOT_TRANSITION_CANDIDATE_IDENTITY_SHA256
        or pair.get("canonical_gt_sha256") != ROOT_CANONICAL_GT_SHA256
        or any(
            (
                access.get("model_loaded") is not False,
                access.get("inference_calls") != 0,
                access.get("prediction_accessed") is not False,
                access.get("locked_test_outcome_accessed") is not False,
                access.get("registered_targets_used") is not False,
                access.get("external_processes_modified") is not False,
                access.get("outcome_inputs") != [],
            )
        )
    ):
        raise execution.ContractError("Accepted 41-to-42 root evidence changed")
    return expected


def _reconstruct_predecessor_state(result: Mapping[str, Any]) -> dict[str, Any]:
    predecessor = copy.deepcopy(dict(result))
    if (
        predecessor.get("completed_pair_count") != 42
        or predecessor.get("completed_pair_ids", [None])[-1]
        != ROOT_TRANSITION_PAIR_ID
    ):
        raise execution.ContractError("Cannot reconstruct immutable 41/96 root")
    predecessor["completed_pair_count"] = 41
    predecessor["pending_pair_count"] = 55
    predecessor["completed_pair_ids"] = list(predecessor["completed_pair_ids"][:-1])
    predecessor["pending_pair_ids"] = [
        ROOT_TRANSITION_PAIR_ID,
        *list(predecessor["pending_pair_ids"]),
    ]
    return predecessor


def _json_sha256(value: Mapping[str, Any]) -> str:
    encoded = (
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _authorization_payload(config: Mapping[str, Any], parents: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": AUTHORIZATION_CONTRACT,
        "status": "PASS_MANAGER_AUTHORIZED_MONOTONIC_STATE_CHAIN_SCOPE_SYNTHETIC_ONLY",
        "authorization": {
            "pass70_event_id": PASS70_EVENT_ID,
            "accepted_pass69_event_id": PASS69_EVENT_ID,
            "goal_multi_repeat_run_id": RUN_ID,
            "pass": 70,
            "strategy": "base",
            "owner_session_id": OWNER_SESSION_ID,
            "portfolio_id": PORTFOLIO_ID,
            "portfolio_lane": PORTFOLIO_LANE,
        },
        "authorized_top_level_source_paths": [
            AUTHORIZED_SOURCE_PATH,
            AUTHORIZED_TEST_PATH,
        ],
        "authorized_scope": {
            "append_only_state_chain_release": True,
            "canonical_single_pair_transitions_authorized_from_completed_42_through_96": True,
            "unchanged_model_free_batch_semantics_only": True,
            "max_new_pairs": 1,
            "candidate_generation_or_rendering_in_pass70_allowed": False,
            "model_prediction_outcome_target_access_allowed": False,
            "external_service_mutation_allowed": False,
            "parent_source_test_or_release_mutation_allowed": False,
        },
        "accepted_root": {
            "predecessor_state_sha256": ROOT_PREDECESSOR_STATE_SHA256,
            "result_state_sha256": ROOT_RESULT_STATE_SHA256,
            "ledger_sha256": ROOT_LEDGER_SHA256,
            "pass69_publication_receipt_sha256": PASS69_PUBLICATION_RECEIPT_SHA256,
            "pass69_next_state_blocker_receipt_sha256": PASS69_BLOCKER_RECEIPT_SHA256,
        },
        "immutable_parents": copy.deepcopy(dict(parents)),
        "claim_boundary": _claim_boundary(config),
    }


def _chain_root_payload(
    config: Mapping[str, Any],
    parents: Mapping[str, Any],
    predecessor_state: Mapping[str, Any],
    root_pair_evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if _json_sha256(predecessor_state) != ROOT_PREDECESSOR_STATE_SHA256:
        raise execution.ContractError("Reconstructed 41/96 state bytes changed")
    payload = {
        "schema_version": 1,
        "contract": ROOT_CONTRACT,
        "status": "SEALED_MONOTONIC_STATE_CHAIN_ROOT_41_TO_42_SYNTHETIC_ONLY",
        "immutable_predecessor_state_sha256": ROOT_PREDECESSOR_STATE_SHA256,
        "immutable_predecessor_state": copy.deepcopy(dict(predecessor_state)),
        "accepted_result_state_sha256": ROOT_RESULT_STATE_SHA256,
        "accepted_ledger_sha256": ROOT_LEDGER_SHA256,
        "accepted_ledger_row_count": ROOT_LEDGER_ROW_COUNT,
        "accepted_transition_pair_id": ROOT_TRANSITION_PAIR_ID,
        "accepted_transition_candidate_index": ROOT_TRANSITION_CANDIDATE_INDEX,
        "accepted_transition_candidate_identity_sha256": (
            ROOT_TRANSITION_CANDIDATE_IDENTITY_SHA256
        ),
        "accepted_transition_canonical_gt_sha256": ROOT_CANONICAL_GT_SHA256,
        "immutable_completed_41_pair_receipts": copy.deepcopy(
            list(root_pair_evidence[:41])
        ),
        "parent_bindings": copy.deepcopy(dict(parents)),
        "rules": {
            "completed_pair_ids_are_exact_roster_prefix": True,
            "pending_pair_ids_are_exact_roster_suffix": True,
            "one_earliest_pending_pair_per_transition": True,
            "lowest_unattempted_sealed_candidate_wins": True,
            "candidate_indices_allowed": [0, 31],
            "ledger_is_exact_append_only_gt_rejection_prefix": True,
            "atomic_immutable_transition_commits": True,
            "parallel_intents_allowed": False,
            "crash_safe_same_intent_resume": True,
            "rollback_skip_delete_reorder_or_rewrite_allowed": False,
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
    payload["chain_root_identity_sha256"] = execution.stable_sha256(payload)
    return payload


def _transition_record_payload(
    *,
    sequence: int,
    chain_root_identity: str,
    predecessor_head_identity: str,
    predecessor_state_sha256: str,
    result_state_sha256: str,
    predecessor_ledger_sha256: str,
    result_ledger_sha256: str,
    pair_evidence: Mapping[str, Any],
    execution_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": TRANSITION_CONTRACT,
        "status": "PASS_CANONICAL_MONOTONIC_PAIR_TRANSITION_SYNTHETIC_ONLY",
        "sequence": sequence,
        "chain_root_identity_sha256": execution.require_sha256(
            chain_root_identity, "chain root identity"
        ),
        "predecessor_head_identity_sha256": execution.require_sha256(
            predecessor_head_identity, "predecessor head identity"
        ),
        "predecessor_state_sha256": execution.require_sha256(
            predecessor_state_sha256, "predecessor state"
        ),
        "result_state_sha256": execution.require_sha256(
            result_state_sha256, "result state"
        ),
        "predecessor_ledger_sha256": execution.require_sha256(
            predecessor_ledger_sha256, "predecessor ledger"
        ),
        "result_ledger_sha256": execution.require_sha256(
            result_ledger_sha256, "result ledger"
        ),
        "pair": copy.deepcopy(dict(pair_evidence)),
        "execution_evidence": copy.deepcopy(dict(execution_evidence)),
        "invariants": {
            "canonical_earliest_pending_pair": True,
            "max_new_pairs": 1,
            "lowest_unattempted_sealed_candidate": True,
            "identical_arm_gt": True,
            "frozen_pair_gates": True,
            "ledger_append_only": True,
            "model_loaded": False,
            "inference_calls": 0,
            "prediction_accessed": False,
            "locked_test_outcome_accessed": False,
            "registered_targets_used": False,
            "external_services_modified": False,
            "outcome_inputs": [],
        },
    }


def _head_payload(record: Mapping[str, Any], record_sha256: str) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "contract": HEAD_CONTRACT,
        "status": "SEALED_MONOTONIC_STATE_CHAIN_HEAD_SYNTHETIC_ONLY",
        "sequence": record["sequence"],
        "pair_id": record["pair"]["pair_id"],
        "chain_root_identity_sha256": record["chain_root_identity_sha256"],
        "predecessor_head_identity_sha256": record[
            "predecessor_head_identity_sha256"
        ],
        "transition_record_sha256": execution.require_sha256(
            record_sha256, "transition record"
        ),
        "result_state_sha256": record["result_state_sha256"],
        "result_ledger_sha256": record["result_ledger_sha256"],
    }
    payload["head_identity_sha256"] = execution.stable_sha256(payload)
    return payload


def _commit_manifest_payload(root: Path, head: Mapping[str, Any]) -> dict[str, Any]:
    files = []
    for name in (
        "head.json",
        "result_ledger.jsonl",
        "result_state.json",
        "transition_record.json",
    ):
        path = root / name
        files.append(
            {
                "path": name,
                "size_bytes": path.stat().st_size,
                "sha256": execution.sha256_file(path),
            }
        )
    payload = {
        "schema_version": 1,
        "contract": COMMIT_CONTRACT,
        "status": "PASS_ATOMIC_IMMUTABLE_TRANSITION_COMMIT_SYNTHETIC_ONLY",
        "sequence": head["sequence"],
        "pair_id": head["pair_id"],
        "head_identity_sha256": head["head_identity_sha256"],
        "files": files,
        "files_identity_sha256": execution.stable_sha256(files),
    }
    payload["commit_identity_sha256"] = execution.stable_sha256(payload)
    return payload


def _commit_name(sequence: int, pair_id: str, head_identity: str) -> str:
    name = f"transition_{sequence:06d}_{pair_id}_{head_identity[:16]}"
    if execution.SAFE_ID_RE.fullmatch(name) is None:
        raise execution.ContractError("Unsafe transition commit name")
    return name


def _validate_commit_directory(path: Path) -> dict[str, Any]:
    observed = sorted(
        item.name for item in path.iterdir() if item.is_file()
    ) if path.is_dir() and not path.is_symlink() else []
    if observed != _required_commit_files():
        raise execution.ContractError("Transition commit file set changed")
    manifest = execution.load_json(path / "commit_manifest.json")
    head = execution.load_json(path / "head.json")
    record = execution.load_json(path / "transition_record.json")
    expected_manifest = _commit_manifest_payload(path, head)
    if manifest != expected_manifest:
        raise execution.ContractError("Transition commit manifest changed")
    record_payload = copy.deepcopy(record)
    record_sha256 = execution.sha256_file(path / "transition_record.json")
    expected_head = _head_payload(record_payload, record_sha256)
    if head != expected_head:
        raise execution.ContractError("Transition chain head changed")
    if path.name != _commit_name(
        int(head["sequence"]), str(head["pair_id"]), str(head["head_identity_sha256"])
    ):
        raise execution.ContractError("Transition commit path identity changed")
    return {
        "path": path,
        "manifest": manifest,
        "head": head,
        "record": record,
        "state": execution.load_json(path / "result_state.json"),
        "ledger": execution.read_jsonl(path / "result_ledger.jsonl"),
    }


def _mirror_commit(source: Path, destination_parent: Path) -> Path:
    destination = destination_parent / source.name
    if destination.exists():
        source_files = {
            path.name: execution.sha256_file(path)
            for path in source.iterdir()
            if path.is_file()
        }
        destination_files = {
            path.name: execution.sha256_file(path)
            for path in destination.iterdir()
            if path.is_file()
        } if destination.is_dir() else {}
        if source_files != destination_files:
            raise execution.ContractError("Transition docs mirror changed")
        return destination
    destination_parent.mkdir(parents=True, exist_ok=True)
    staging = destination_parent / f".partial-{source.name}-{uuid.uuid4().hex}"
    try:
        shutil.copytree(source, staging)
        staging.replace(destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return destination


def _publish_transition_commit(
    commits_parent: Path,
    docs_parent: Path,
    record: Mapping[str, Any],
    result_state: Mapping[str, Any],
    result_ledger: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    parent = commits_parent
    parent.mkdir(parents=True, exist_ok=True)
    partials = list(parent.glob(".partial-*"))
    if partials:
        raise execution.ContractError("Partial transition commit exists")
    staging = parent / f".partial-transition-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        execution.write_json(staging / "transition_record.json", record)
        execution.write_json(staging / "result_state.json", result_state)
        execution.write_jsonl(staging / "result_ledger.jsonl", result_ledger)
        head = _head_payload(
            record, execution.sha256_file(staging / "transition_record.json")
        )
        execution.write_json(staging / "head.json", head)
        manifest = _commit_manifest_payload(staging, head)
        execution.write_json(staging / "commit_manifest.json", manifest)
        name = _commit_name(
            int(head["sequence"]), str(head["pair_id"]), str(head["head_identity_sha256"])
        )
        destination = parent / name
        if destination.exists():
            existing = _validate_commit_directory(destination)
            if existing["manifest"] != manifest:
                raise execution.ContractError("Existing transition commit changed")
            shutil.rmtree(staging)
        else:
            staging.replace(destination)
        _validate_commit_directory(destination)
        docs_destination = _mirror_commit(destination, docs_parent)
        _validate_commit_directory(docs_destination)
        return {
            "commit_path": execution.display_path(destination),
            "commit_name": destination.name,
            "commit_identity_sha256": manifest["commit_identity_sha256"],
            "commit_manifest_sha256": execution.sha256_file(
                destination / "commit_manifest.json"
            ),
            "head_identity_sha256": head["head_identity_sha256"],
        }
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def _list_commits(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    parent = paths["commits"]
    docs_parent = paths["docs_commits"]
    partials = list(parent.glob(".partial-*")) if parent.exists() else []
    docs_partials = list(docs_parent.glob(".partial-*")) if docs_parent.exists() else []
    if partials or docs_partials:
        raise execution.ContractError("Partial transition chain commit exists")
    names = sorted(path.name for path in parent.iterdir() if path.is_dir()) if parent.is_dir() else []
    docs_names = sorted(path.name for path in docs_parent.iterdir() if path.is_dir()) if docs_parent.is_dir() else []
    if names != docs_names:
        raise execution.ContractError("Transition chain mirror directory set changed")
    commits = []
    for name in names:
        commit = _validate_commit_directory(parent / name)
        mirrored = _validate_commit_directory(docs_parent / name)
        if commit["manifest"] != mirrored["manifest"]:
            raise execution.ContractError("Transition chain docs mirror changed")
        commits.append(commit)
    return commits


def _genesis_execution_evidence(root_evidence: Mapping[str, str]) -> dict[str, Any]:
    return {
        "epoch": "accepted_pass66_adapter_transition",
        "pass69_publication_receipt_sha256": root_evidence["pass69_publication"],
        "pass69_next_state_blocker_receipt_sha256": root_evidence["pass69_blocker"],
        "adapter_execution_id": ROOT_ADAPTER_EXECUTION_ID,
        "adapter_intent_sha256": root_evidence["adapter_intent"],
        "adapter_terminal_receipt_sha256": root_evidence["adapter_terminal"],
        "underlying_batch_id": ROOT_BATCH_ID,
        "underlying_batch_intent_sha256": root_evidence["batch_intent"],
        "underlying_batch_receipt_sha256": root_evidence["batch_receipt"],
        "contact_sheet_sha256": root_evidence["contact_sheet"],
        "original_validator_restored": True,
    }


def _authorization_root_anchor(root: Mapping[str, Any]) -> str:
    return execution.stable_sha256(
        {
            "contract": CONTRACT,
            "chain_root_identity_sha256": root["chain_root_identity_sha256"],
            "predecessor_state_sha256": ROOT_PREDECESSOR_STATE_SHA256,
            "result_state_sha256": ROOT_RESULT_STATE_SHA256,
            "ledger_sha256": ROOT_LEDGER_SHA256,
            "marker": "GENESIS_PREDECESSOR_HEAD",
        }
    )


def _lock_payload(
    config: Mapping[str, Any],
    root: Mapping[str, Any],
    genesis: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": LOCK_CONTRACT,
        "status": "SEALED_MONOTONIC_STATE_CHAIN_BATCH_LOCK_SYNTHETIC_ONLY",
        "chain_root_identity_sha256": root["chain_root_identity_sha256"],
        "genesis_commit_identity_sha256": genesis["commit_identity_sha256"],
        "genesis_commit_manifest_sha256": genesis["commit_manifest_sha256"],
        "genesis_head_identity_sha256": genesis["head_identity_sha256"],
        "authorized_completed_count_range": [42, 96],
        "one_pair_transition_only": True,
        "max_new_pairs": 1,
        "canonical_earliest_pending_required": True,
        "lowest_unattempted_candidate_required": True,
        "candidate_epoch_map": {"0-9": "historical_v1", "10-31": "extension_v1"},
        "append_only_ledger_required": True,
        "atomic_immutable_commit_required": True,
        "same_intent_crash_recovery_required": True,
        "parallel_intent_allowed": False,
        "legacy_execution_mutation_allowed": False,
        "model_prediction_outcome_or_target_access_allowed": False,
        "external_service_mutation_allowed": False,
        "claim_boundary": _claim_boundary(config),
    }


def _release_payload(
    config: Mapping[str, Any],
    parents: Mapping[str, Any],
    *,
    authorization_sha256: str,
    root_sha256: str,
    lock_sha256: str,
    genesis: Mapping[str, Any],
) -> dict[str, Any]:
    test_path = PROJECT_ROOT / AUTHORIZED_TEST_PATH
    payload = {
        "schema_version": 1,
        "contract": RELEASE_CONTRACT,
        "status": "SEALED_EXTENSION_AWARE_MONOTONIC_STATE_CHAIN_RELEASE_SYNTHETIC_ONLY",
        "authorization_receipt_sha256": authorization_sha256,
        "chain_root_sha256": root_sha256,
        "state_chain_lock_sha256": lock_sha256,
        "state_chain_script_sha256": execution.sha256_file(Path(__file__)),
        "state_chain_test_sha256": execution.sha256_file(test_path),
        "immutable_parents": copy.deepcopy(dict(parents)),
        "genesis_commit_identity_sha256": genesis["commit_identity_sha256"],
        "genesis_commit_manifest_sha256": genesis["commit_manifest_sha256"],
        "genesis_head_identity_sha256": genesis["head_identity_sha256"],
        "root_predecessor_state_sha256": ROOT_PREDECESSOR_STATE_SHA256,
        "root_result_state_sha256": ROOT_RESULT_STATE_SHA256,
        "root_ledger_sha256": ROOT_LEDGER_SHA256,
        "parent_or_historical_bytes_rewritten_or_rebound": False,
        "pass70_validation_only_no_candidate_or_render": True,
        "claim_boundary": _claim_boundary(config),
    }
    payload["release_identity_sha256"] = execution.stable_sha256(payload)
    return payload


def _validation_receipt_payload(
    config: Mapping[str, Any],
    release: Mapping[str, Any],
    genesis: Mapping[str, Any],
    root_pair_evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "contract": VALIDATION_RECEIPT_CONTRACT,
        "status": "READY_FOR_MANAGER_VALIDATION",
        "goal_multi_repeat_run_id": RUN_ID,
        "event_id": PASS70_EVENT_ID,
        "pass": 70,
        "state_chain_release_identity_sha256": release[
            "release_identity_sha256"
        ],
        "genesis_commit_identity_sha256": genesis["commit_identity_sha256"],
        "genesis_head_identity_sha256": genesis["head_identity_sha256"],
        "validated_root": {
            "predecessor_completed_pair_count": 41,
            "result_completed_pair_count": 42,
            "pending_pair_count": 54,
            "appended_pair_id": ROOT_TRANSITION_PAIR_ID,
            "predecessor_state_sha256": ROOT_PREDECESSOR_STATE_SHA256,
            "result_state_sha256": ROOT_RESULT_STATE_SHA256,
            "ledger_sha256": ROOT_LEDGER_SHA256,
            "ledger_row_count": ROOT_LEDGER_ROW_COUNT,
            "published_pair_receipt_count": len(root_pair_evidence),
            "published_pair_receipt_inventory_sha256": execution.stable_sha256(
                root_pair_evidence
            ),
        },
        "regression_contract": {
            "root_current_predecessor_result_tamper_fails_closed": True,
            "rollback_skip_reorder_or_prefix_suffix_drift_fails_closed": True,
            "pair_receipt_forgery_fails_closed": True,
            "ledger_mutation_truncation_or_noncanonical_append_fails_closed": True,
            "duplicate_or_parallel_intent_fails_closed": True,
            "atomic_failure_is_crash_safe_and_idempotent": True,
            "patched_callable_is_always_restored": True,
        },
        "access_guard": {
            "validation_only": True,
            "real_batch_intents_created": 0,
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
    for key in ("release", "docs_release"):
        root = paths[key]
        observed = sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file()
        ) if root.is_dir() else []
        if observed != required:
            raise execution.ContractError("State-chain release file set changed")
    for relative in required:
        if execution.sha256_file(paths["release"] / relative) != execution.sha256_file(
            paths["docs_release"] / relative
        ):
            raise execution.ContractError("State-chain release docs mirror changed")


def _validate_static_release(
    config: Mapping[str, Any], parents: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    paths = state_chain_paths(config)
    _validate_release_file_set(paths)
    authorization = execution.load_json(paths["authorization"])
    if authorization != _authorization_payload(config, parents):
        raise execution.ContractError("Pass70 manager authorization receipt changed")
    root = execution.load_json(paths["chain_root"])
    root_identity_payload = copy.deepcopy(root)
    root_identity = root_identity_payload.pop("chain_root_identity_sha256", None)
    if root_identity != execution.stable_sha256(root_identity_payload):
        raise execution.ContractError("State-chain root identity changed")
    commits = _list_commits(paths)
    if not commits:
        raise execution.ContractError("State-chain genesis commit is missing")
    genesis = commits[0]
    lock = execution.load_json(paths["lock"])
    expected_lock = _lock_payload(config, root, {
        "commit_identity_sha256": genesis["manifest"]["commit_identity_sha256"],
        "commit_manifest_sha256": execution.sha256_file(genesis["path"] / "commit_manifest.json"),
        "head_identity_sha256": genesis["head"]["head_identity_sha256"],
    })
    if lock != expected_lock:
        raise execution.ContractError("State-chain lock changed")
    release = execution.load_json(paths["release_file"])
    expected_release = _release_payload(
        config,
        parents,
        authorization_sha256=execution.sha256_file(paths["authorization"]),
        root_sha256=execution.sha256_file(paths["chain_root"]),
        lock_sha256=execution.sha256_file(paths["lock"]),
        genesis={
            "commit_identity_sha256": genesis["manifest"]["commit_identity_sha256"],
            "commit_manifest_sha256": execution.sha256_file(genesis["path"] / "commit_manifest.json"),
            "head_identity_sha256": genesis["head"]["head_identity_sha256"],
        },
    )
    if release != expected_release:
        raise execution.ContractError("State-chain release changed")
    return root, release, {"paths": paths, "commits": commits}


def _open_intents(paths: Mapping[str, Path]) -> list[dict[str, Any]]:
    parent = paths["executions"]
    if not parent.exists():
        return []
    partials = list(parent.glob(".partial-*"))
    if partials:
        raise execution.ContractError("Partial state-chain intent exists")
    active: list[dict[str, Any]] = []
    for root in sorted(path for path in parent.iterdir() if path.is_dir()):
        intent_path = root / "state_chain_intent.json"
        terminal_path = root / "state_chain_terminal_receipt.json"
        if not intent_path.is_file():
            raise execution.ContractError("State-chain execution has no valid intent")
        intent = execution.load_json(intent_path)
        if terminal_path.is_file():
            continue
        active.append({"root": root, "intent": intent})
    if len(active) > 1:
        raise execution.ContractError("Parallel state-chain intents exist")
    return active


def _validate_commit_chain(
    root: Mapping[str, Any],
    commits: Sequence[Mapping[str, Any]],
    combined: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    pair_ids = _canonical_pair_ids(combined)
    if not commits:
        raise execution.ContractError("Transition chain is empty")
    predecessor_state = root["immutable_predecessor_state"]
    predecessor_ledger: list[dict[str, Any]] = []
    predecessor_head = _authorization_root_anchor(root)
    for index, commit in enumerate(commits):
        record = commit["record"]
        state = commit["state"]
        ledger = commit["ledger"]
        sequence = int(record.get("sequence", -1))
        if sequence != 42 + index:
            raise execution.ContractError("Transition chain sequence skipped or reordered")
        pair_id = pair_ids[sequence - 1]
        if (
            record.get("contract") != TRANSITION_CONTRACT
            or record.get("status")
            != "PASS_CANONICAL_MONOTONIC_PAIR_TRANSITION_SYNTHETIC_ONLY"
            or record.get("chain_root_identity_sha256")
            != root["chain_root_identity_sha256"]
            or record.get("predecessor_head_identity_sha256") != predecessor_head
            or record.get("predecessor_state_sha256")
            != _json_sha256(predecessor_state)
            or record.get("result_state_sha256") != _json_sha256(state)
            or record.get("pair", {}).get("pair_id") != pair_id
        ):
            raise execution.ContractError("Transition predecessor/result binding changed")
        expected_record = _transition_record_payload(
            sequence=sequence,
            chain_root_identity=str(record["chain_root_identity_sha256"]),
            predecessor_head_identity=str(
                record["predecessor_head_identity_sha256"]
            ),
            predecessor_state_sha256=str(record["predecessor_state_sha256"]),
            result_state_sha256=str(record["result_state_sha256"]),
            predecessor_ledger_sha256=str(record["predecessor_ledger_sha256"]),
            result_ledger_sha256=str(record["result_ledger_sha256"]),
            pair_evidence=record["pair"],
            execution_evidence=record["execution_evidence"],
        )
        if record != expected_record:
            raise execution.ContractError("Transition record contract changed")
        _validate_state_transition(predecessor_state, state, pair_ids, pair_id)
        ledger_summary = _validate_ledger_rows(ledger, combined)
        if index == 0:
            if (
                record["predecessor_state_sha256"] != ROOT_PREDECESSOR_STATE_SHA256
                or record["result_state_sha256"] != ROOT_RESULT_STATE_SHA256
                or record["predecessor_ledger_sha256"] != ROOT_LEDGER_SHA256
                or record["result_ledger_sha256"] != ROOT_LEDGER_SHA256
                or ledger_summary["row_count"] != ROOT_LEDGER_ROW_COUNT
            ):
                raise execution.ContractError("Genesis transition boundary changed")
            predecessor_ledger = list(ledger)
        else:
            if (
                record.get("predecessor_ledger_sha256")
                != execution.sha256_file(commits[index - 1]["path"] / "result_ledger.jsonl")
            ):
                raise execution.ContractError("Transition ledger predecessor changed")
            _validate_ledger_extension(predecessor_ledger, ledger, combined, pair_id)
        if record.get("result_ledger_sha256") != execution.sha256_file(
            commit["path"] / "result_ledger.jsonl"
        ):
            raise execution.ContractError("Transition result ledger hash changed")
        predecessor_state = state
        predecessor_ledger = list(ledger)
        predecessor_head = commit["head"]["head_identity_sha256"]
    return {
        "commit_count": len(commits),
        "head_sequence": int(commits[-1]["head"]["sequence"]),
        "head_identity_sha256": commits[-1]["head"]["head_identity_sha256"],
        "head_state_sha256": commits[-1]["head"]["result_state_sha256"],
        "head_ledger_sha256": commits[-1]["head"]["result_ledger_sha256"],
        "head_state": commits[-1]["state"],
        "head_ledger": commits[-1]["ledger"],
    }


def _validate_live_against_chain(
    config: Mapping[str, Any],
    historical: Sequence[Mapping[str, Any]],
    combined: Sequence[Mapping[str, Any]],
    chain: Mapping[str, Any],
    paths: Mapping[str, Path],
    *,
    allow_open_execution_id: str | None = None,
) -> dict[str, Any]:
    state_path, docs_state_path, ledger_path = _state_paths(config)
    if not state_path.is_file() or not docs_state_path.is_file() or not ledger_path.is_file():
        raise execution.ContractError("Live state or ledger is missing")
    if execution.sha256_file(state_path) != execution.sha256_file(docs_state_path):
        raise execution.ContractError("Live render-state mirror changed")
    state = execution.load_json(state_path)
    ledger = execution.read_jsonl(ledger_path)
    pair_ids = _canonical_pair_ids(combined)
    state_summary = _validate_state_shape(state, pair_ids)
    _validate_ledger_rows(ledger, combined)

    active = _open_intents(paths)
    if active:
        execution_id = str(active[0]["intent"].get("execution_id", ""))
        if allow_open_execution_id != execution_id:
            raise execution.ContractError("An unresolved state-chain intent blocks validation")
    elif allow_open_execution_id is not None:
        raise execution.ContractError("Expected state-chain intent is missing")

    head_state = chain["head_state"]
    head_ledger = chain["head_ledger"]
    head_count = int(head_state["completed_pair_count"])
    if not active:
        if (
            execution.sha256_file(state_path) != chain["head_state_sha256"]
            or execution.sha256_file(ledger_path) != chain["head_ledger_sha256"]
            or state != head_state
            or ledger != head_ledger
        ):
            raise execution.ContractError("Live state or ledger drifted from chain head")
    else:
        intent = active[0]["intent"]
        target = str(intent.get("request", {}).get("target_pair_id", ""))
        if (
            intent.get("predecessor_head_identity_sha256")
            != chain["head_identity_sha256"]
            or target != pair_ids[head_count]
            or state_summary["completed_pair_count"] not in {head_count, head_count + 1}
        ):
            raise execution.ContractError("Open intent does not extend the exact chain head")
        if list(ledger[: len(head_ledger)]) != list(head_ledger):
            raise execution.ContractError("Open-intent ledger prefix changed")
        _validate_ledger_extension(head_ledger, ledger, combined, target)
        if state_summary["completed_pair_count"] == head_count and state != head_state:
            raise execution.ContractError("Open intent changed state without publication")
        if state_summary["completed_pair_count"] == head_count + 1:
            _validate_state_transition(head_state, state, pair_ids, target)

    inspected = execution.inspect_full_render_state(
        execution.full_paths(config)["synthetic"], combined
    )
    comparable = copy.deepcopy(inspected)
    comparable["interrupted_staging_directories"] = []
    inventory_state = state
    if comparable != state:
        if not active:
            raise execution.ContractError("Published-pair inventory differs from live state")
        target = str(active[0]["intent"].get("request", {}).get("target_pair_id", ""))
        _validate_state_transition(head_state, comparable, pair_ids, target)
        if state != head_state:
            raise execution.ContractError(
                "Open intent has a noncanonical live-state/inventory mismatch"
            )
        inventory_state = comparable
    if execution.full_paths(config)["run"].exists():
        raise execution.ContractError("Full benchmark model output root exists")

    # For an accepted but not-yet-committed open transition, pending ledger rows
    # are allowed only for that exact target.  Otherwise every completed pair
    # and the absence of pending ledger evidence is verified here.
    validation_ledger = ledger
    if (
        active
        and state_summary["completed_pair_count"] == head_count
        and inventory_state is state
    ):
        validation_ledger = head_ledger
    pair_evidence = _validate_all_published_pairs(
        config, historical, combined, inventory_state, validation_ledger
    )
    inventory_summary = _validate_state_shape(inventory_state, pair_ids)
    return {
        **state_summary,
        "inventory_completed_pair_count": inventory_summary[
            "completed_pair_count"
        ],
        "inventory_pending_pair_count": inventory_summary["pending_pair_count"],
        "render_state_sha256": execution.sha256_file(state_path),
        "candidate_rejection_ledger_sha256": execution.sha256_file(ledger_path),
        "candidate_rejection_ledger_row_count": len(ledger),
        "published_pair_evidence": pair_evidence,
        "published_pair_evidence_identity_sha256": execution.stable_sha256(pair_evidence),
        "active_execution_id": (
            str(active[0]["intent"]["execution_id"]) if active else None
        ),
        "model_outputs_present": False,
    }


def seal_state_chain_release(config_path: Path) -> dict[str, Any]:
    config, roster = _verify_immutable_parents(config_path)
    paths = state_chain_paths(config)
    if any(
        path.exists()
        for path in (paths["release"], paths["docs_release"], paths["commits"], paths["docs_commits"])
    ):
        return validate_state_chain_release(config_path)
    root_evidence = _verify_root_evidence(config)
    state_path, docs_state_path, ledger_path = _state_paths(config)
    _require_file_sha256(state_path, ROOT_RESULT_STATE_SHA256, "42/96 render state")
    _require_file_sha256(docs_state_path, ROOT_RESULT_STATE_SHA256, "42/96 docs render state")
    _require_file_sha256(ledger_path, ROOT_LEDGER_SHA256, "root rejection ledger")
    state = execution.load_json(state_path)
    ledger = execution.read_jsonl(ledger_path)
    pair_ids = _canonical_pair_ids(roster["combined"])
    _validate_state_shape(state, pair_ids)
    ledger_summary = _validate_ledger_rows(ledger, roster["combined"])
    if ledger_summary["row_count"] != ROOT_LEDGER_ROW_COUNT:
        raise execution.ContractError("Root rejection ledger row count changed")
    pair_evidence = _validate_all_published_pairs(
        config, roster["historical"], roster["combined"], state, ledger
    )
    predecessor = _reconstruct_predecessor_state(state)
    _validate_state_transition(predecessor, state, pair_ids, ROOT_TRANSITION_PAIR_ID)

    authorization = _authorization_payload(config, roster["parents"])
    root_payload = _chain_root_payload(
        config, roster["parents"], predecessor, pair_evidence
    )
    root_pair = pair_evidence[-1]
    if (
        root_pair["pair_id"] != ROOT_TRANSITION_PAIR_ID
        or root_pair["selected_candidate_index"] != ROOT_TRANSITION_CANDIDATE_INDEX
        or root_pair["full_pair_receipt_sha256"] != ROOT_FULL_PAIR_RECEIPT_SHA256
    ):
        raise execution.ContractError("Root transition pair evidence changed")
    genesis_record = _transition_record_payload(
        sequence=42,
        chain_root_identity=root_payload["chain_root_identity_sha256"],
        predecessor_head_identity=_authorization_root_anchor(root_payload),
        predecessor_state_sha256=ROOT_PREDECESSOR_STATE_SHA256,
        result_state_sha256=ROOT_RESULT_STATE_SHA256,
        predecessor_ledger_sha256=ROOT_LEDGER_SHA256,
        result_ledger_sha256=ROOT_LEDGER_SHA256,
        pair_evidence=root_pair,
        execution_evidence=_genesis_execution_evidence(root_evidence),
    )
    genesis = _publish_transition_commit(
        paths["commits"], paths["docs_commits"], genesis_record, state, ledger
    )
    lock = _lock_payload(config, root_payload, genesis)

    release_parent = paths["release"].parent
    docs_parent = paths["docs_release"].parent
    release_parent.mkdir(parents=True, exist_ok=True)
    docs_parent.mkdir(parents=True, exist_ok=True)
    staging = release_parent / f".partial-state-chain-release-{uuid.uuid4().hex}"
    docs_staging = docs_parent / f".partial-state-chain-release-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        execution.write_json(
            staging / "pass70_manager_authorization_receipt.json", authorization
        )
        execution.write_json(staging / "monotonic_state_chain_root_v1.json", root_payload)
        execution.write_json(staging / "monotonic_state_chain_lock_v1.json", lock)
        release = _release_payload(
            config,
            roster["parents"],
            authorization_sha256=execution.sha256_file(
                staging / "pass70_manager_authorization_receipt.json"
            ),
            root_sha256=execution.sha256_file(
                staging / "monotonic_state_chain_root_v1.json"
            ),
            lock_sha256=execution.sha256_file(
                staging / "monotonic_state_chain_lock_v1.json"
            ),
            genesis=genesis,
        )
        execution.write_json(
            staging / "extension_aware_state_chain_release_v1.json", release
        )
        receipt = _validation_receipt_payload(config, release, genesis, pair_evidence)
        execution.write_json(staging / "pass70_validation_receipt.json", receipt)
        staging.replace(paths["release"])
        shutil.copytree(paths["release"], docs_staging)
        docs_staging.replace(paths["docs_release"])
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if docs_staging.exists():
            shutil.rmtree(docs_staging)
    return validate_state_chain_release(config_path)


def validate_state_chain_release(
    config_path: Path, *, allow_open_execution_id: str | None = None
) -> dict[str, Any]:
    config, roster = _verify_immutable_parents(config_path)
    root, release, static = _validate_static_release(config, roster["parents"])
    chain = _validate_commit_chain(root, static["commits"], roster["combined"])
    root_evidence = _verify_root_evidence(config)
    if static["commits"][0]["record"].get("execution_evidence") != (
        _genesis_execution_evidence(root_evidence)
    ):
        raise execution.ContractError("Genesis execution evidence changed")
    live = _validate_live_against_chain(
        config,
        roster["historical"],
        roster["combined"],
        chain,
        static["paths"],
        allow_open_execution_id=allow_open_execution_id,
    )
    expected_root = _chain_root_payload(
        config,
        roster["parents"],
        _reconstruct_predecessor_state(static["commits"][0]["state"]),
        live["published_pair_evidence"],
    )
    if root != expected_root:
        raise execution.ContractError("Monotonic state-chain root contract changed")
    if root["immutable_completed_41_pair_receipts"] != live[
        "published_pair_evidence"
    ][:41]:
        raise execution.ContractError("Immutable 41-pair receipt prefix changed")
    for commit in static["commits"]:
        pair_index = int(commit["record"]["sequence"]) - 1
        if commit["record"]["pair"] != live["published_pair_evidence"][pair_index]:
            raise execution.ContractError("Transition pair receipt evidence changed")
    genesis = static["commits"][0]
    expected_genesis_record = _transition_record_payload(
        sequence=42,
        chain_root_identity=root["chain_root_identity_sha256"],
        predecessor_head_identity=_authorization_root_anchor(root),
        predecessor_state_sha256=ROOT_PREDECESSOR_STATE_SHA256,
        result_state_sha256=ROOT_RESULT_STATE_SHA256,
        predecessor_ledger_sha256=ROOT_LEDGER_SHA256,
        result_ledger_sha256=ROOT_LEDGER_SHA256,
        pair_evidence=live["published_pair_evidence"][41],
        execution_evidence=_genesis_execution_evidence(root_evidence),
    )
    if genesis["record"] != expected_genesis_record:
        raise execution.ContractError("Genesis transition record changed")
    receipt = execution.load_json(static["paths"]["validation_receipt"])
    genesis_summary = {
        "commit_identity_sha256": genesis["manifest"]["commit_identity_sha256"],
        "head_identity_sha256": genesis["head"]["head_identity_sha256"],
    }
    expected_receipt = _validation_receipt_payload(
        config,
        release,
        genesis_summary,
        [*root["immutable_completed_41_pair_receipts"], genesis["record"]["pair"]],
    )
    if receipt != expected_receipt:
        raise execution.ContractError("Pass70 validation receipt changed")
    return {
        "status": "PASS_EXTENSION_AWARE_MONOTONIC_STATE_CHAIN_VALIDATION_SYNTHETIC_ONLY",
        "state_chain_release_identity_sha256": release[
            "release_identity_sha256"
        ],
        "chain_root_identity_sha256": root["chain_root_identity_sha256"],
        "chain_head_identity_sha256": chain["head_identity_sha256"],
        "transition_commit_count": chain["commit_count"],
        "completed_pair_count": live["completed_pair_count"],
        "pending_pair_count": live["pending_pair_count"],
        "inventory_completed_pair_count": live[
            "inventory_completed_pair_count"
        ],
        "inventory_pending_pair_count": live["inventory_pending_pair_count"],
        "first_pending_pair_id": live["first_pending_pair_id"],
        "render_state_sha256": live["render_state_sha256"],
        "candidate_rejection_ledger_sha256": live[
            "candidate_rejection_ledger_sha256"
        ],
        "candidate_rejection_ledger_row_count": live[
            "candidate_rejection_ledger_row_count"
        ],
        "published_pair_receipt_count": len(live["published_pair_evidence"]),
        "active_execution_id": live["active_execution_id"],
        "candidate_gt_accessed_during_validation": False,
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


def extension_aware_state_chain_validate_full_plan(
    config_path: Path, *, allow_open_execution_id: str | None = None
) -> dict[str, Any]:
    validation = validate_state_chain_release(
        config_path, allow_open_execution_id=allow_open_execution_id
    )
    config = execution.load_config(config_path.expanduser().resolve())
    plan_boundary = copy.deepcopy(validation)
    plan_boundary["completed_pair_count"] = validation.get(
        "inventory_completed_pair_count", validation["completed_pair_count"]
    )
    plan_boundary["pending_pair_count"] = validation.get(
        "inventory_pending_pair_count", validation["pending_pair_count"]
    )
    return adapter._historical_plan_binding(config, plan_boundary)


def _callable_snapshot() -> dict[str, Callable[..., Any]]:
    return {
        name: value for name, value in vars(execution).items() if callable(value)
    }


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


def _call_unchanged_batch(
    config_path: Path,
    pair_id: str,
    *,
    execution_id: str,
) -> dict[str, Any]:
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator is not installed before bridge")
    replacement = functools.partial(
        extension_aware_state_chain_validate_full_plan,
        allow_open_execution_id=execution_id,
    )
    before = _callable_snapshot()
    try:
        execution.validate_full_plan = replacement
        _assert_only_validator_changed(before, replacement)
        return execution.run_locked_test_render_batch(
            config_path, [pair_id], max_new_pairs=1
        )
    finally:
        execution.validate_full_plan = _ORIGINAL_VALIDATE_FULL_PLAN
        _assert_only_validator_changed(before, _ORIGINAL_VALIDATE_FULL_PLAN)


def _normalize_request(
    validation: Mapping[str, Any], release_identity: str, pair_ids: Sequence[str], max_new_pairs: int
) -> dict[str, Any]:
    normalized = [str(pair_id) for pair_id in pair_ids]
    if (
        max_new_pairs != 1
        or normalized != [validation.get("first_pending_pair_id")]
        or normalized[0] is None
    ):
        raise execution.ContractError(
            "State-chain batch must target exactly the earliest pending pair with max-new-pairs=1"
        )
    return {
        "schema_version": 1,
        "contract": CONTRACT,
        "state_chain_release_identity_sha256": execution.require_sha256(
            release_identity, "state-chain release identity"
        ),
        "predecessor_head_identity_sha256": validation[
            "chain_head_identity_sha256"
        ],
        "predecessor_state_sha256": validation["render_state_sha256"],
        "predecessor_ledger_sha256": validation[
            "candidate_rejection_ledger_sha256"
        ],
        "target_pair_id": normalized[0],
        "max_new_pairs": 1,
        "canonical_earliest_pending_required": True,
        "lowest_unattempted_sealed_candidate_wins": True,
        "model_access_allowed": False,
        "prediction_access_allowed": False,
        "locked_test_outcome_access_allowed": False,
        "registered_target_access_allowed": False,
        "external_service_mutation_allowed": False,
    }


def _execution_identity(request: Mapping[str, Any]) -> tuple[str, str]:
    identity = execution.stable_sha256(request)
    execution_id = f"state_chain_batch_{request['target_pair_id']}_{identity[:16]}"
    if execution.SAFE_ID_RE.fullmatch(execution_id) is None:
        raise execution.ContractError("Unsafe state-chain execution identity")
    return execution_id, identity


def _publish_or_resume_intent(
    parent: Path, execution_id: str, intent: Mapping[str, Any]
) -> tuple[Path, bool]:
    parent.mkdir(parents=True, exist_ok=True)
    partials = list(parent.glob(".partial-*"))
    if partials:
        raise execution.ContractError("Partial state-chain intent exists")
    active = []
    for root in parent.iterdir():
        if not root.is_dir() or root.name == execution_id:
            continue
        if (root / "state_chain_intent.json").is_file() and not (
            root / "state_chain_terminal_receipt.json"
        ).is_file():
            active.append(root.name)
    if active:
        raise execution.ContractError("Parallel state-chain intent exists")
    root = parent / execution_id
    intent_path = root / "state_chain_intent.json"
    if root.exists():
        if not intent_path.is_file() or execution.load_json(intent_path) != dict(intent):
            raise execution.ContractError("Existing state-chain intent changed")
        return root, True
    staging = parent / f".partial-{execution_id}-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    try:
        execution.write_json(staging / "state_chain_intent.json", intent)
        staging.replace(root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return root, False


def _terminal_payload(
    config: Mapping[str, Any],
    intent: Mapping[str, Any],
    intent_path: Path,
    transition: Mapping[str, Any],
    underlying_batch: Mapping[str, Any],
    resumed: bool,
) -> dict[str, Any]:
    batch_id = str(underlying_batch["batch_id"])
    batch_root = (
        execution.full_paths(config)["synthetic"]
        / "planning/locked_test_render_batches_v1"
        / batch_id
    )
    return {
        "schema_version": 1,
        "contract": TERMINAL_RECEIPT_CONTRACT,
        "status": "PASS_EXTENSION_AWARE_STATE_CHAIN_BATCH_SYNTHETIC_ONLY",
        "execution_id": intent["execution_id"],
        "request_identity_sha256": intent["request_identity_sha256"],
        "request": copy.deepcopy(intent["request"]),
        "state_chain_intent_sha256": execution.sha256_file(intent_path),
        "transition": copy.deepcopy(dict(transition)),
        "underlying_batch": {
            "batch_id": batch_id,
            "batch_intent_sha256": execution.sha256_file(batch_root / "batch_intent.json"),
            "batch_receipt_sha256": execution.sha256_file(batch_root / "batch_receipt.json"),
            "new_pair_ids": list(underlying_batch["new_pair_ids"]),
        },
        "resume": {"resumed_from_existing_state_chain_intent": resumed},
        "original_validator_restored": execution.validate_full_plan is _ORIGINAL_VALIDATE_FULL_PLAN,
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
    intent: Mapping[str, Any],
    intent_path: Path,
    paths: Mapping[str, Path],
) -> None:
    access = receipt.get("access_guard", {})
    batch = receipt.get("underlying_batch", {})
    transition = receipt.get("transition", {})
    valid = (
        receipt.get("schema_version") == 1
        and receipt.get("contract") == TERMINAL_RECEIPT_CONTRACT
        and receipt.get("status")
        == "PASS_EXTENSION_AWARE_STATE_CHAIN_BATCH_SYNTHETIC_ONLY"
        and receipt.get("execution_id") == intent.get("execution_id")
        and receipt.get("request_identity_sha256")
        == intent.get("request_identity_sha256")
        and receipt.get("request") == intent.get("request")
        and receipt.get("state_chain_intent_sha256")
        == execution.sha256_file(intent_path)
        and receipt.get("original_validator_restored") is True
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
        raise execution.ContractError("State-chain terminal receipt changed")
    batch_root = (
        execution.full_paths(config)["synthetic"]
        / "planning/locked_test_render_batches_v1"
        / str(batch.get("batch_id", ""))
    )
    _require_file_sha256(
        batch_root / "batch_intent.json",
        str(batch.get("batch_intent_sha256", "")),
        "terminal underlying batch intent",
    )
    _require_file_sha256(
        batch_root / "batch_receipt.json",
        str(batch.get("batch_receipt_sha256", "")),
        "terminal underlying batch receipt",
    )
    commit_name = str(transition.get("commit_name", ""))
    commit = _validate_commit_directory(paths["commits"] / commit_name)
    if (
        commit["manifest"].get("commit_identity_sha256")
        != transition.get("commit_identity_sha256")
        or execution.sha256_file(commit["path"] / "commit_manifest.json")
        != transition.get("commit_manifest_sha256")
        or commit["head"].get("head_identity_sha256")
        != transition.get("head_identity_sha256")
    ):
        raise execution.ContractError("Terminal transition commit binding changed")


def run_state_chain_batch(
    config_path: Path, pair_ids: Sequence[str], *, max_new_pairs: int = 1
) -> dict[str, Any]:
    config_path = config_path.expanduser().resolve()
    config, roster = _verify_immutable_parents(config_path)
    root, release, static = _validate_static_release(config, roster["parents"])
    normalized_pair_ids = [str(pair_id) for pair_id in pair_ids]
    if max_new_pairs != 1 or len(normalized_pair_ids) != 1:
        raise execution.ContractError(
            "State-chain batch requires one explicit pair and max-new-pairs=1"
        )

    # A completed identical request is idempotent even after the chain head has
    # advanced and that pair is no longer pending.
    executions_parent = static["paths"]["executions"]
    if executions_parent.is_dir():
        for prior_root in sorted(path for path in executions_parent.iterdir() if path.is_dir()):
            prior_intent_path = prior_root / "state_chain_intent.json"
            prior_terminal_path = prior_root / "state_chain_terminal_receipt.json"
            if not prior_intent_path.is_file() or not prior_terminal_path.is_file():
                continue
            prior_intent = execution.load_json(prior_intent_path)
            if prior_intent.get("request", {}).get("target_pair_id") != normalized_pair_ids[0]:
                continue
            prior_receipt = execution.load_json(prior_terminal_path)
            _validate_terminal_receipt(
                config, prior_receipt, prior_intent, prior_intent_path, static["paths"]
            )
            final = validate_state_chain_release(config_path)
            docs_terminal = (
                static["paths"]["docs_executions"] / f"{prior_root.name}.json"
            )
            execution._write_json_once_atomically(docs_terminal, prior_receipt)
            return {
                "status": "SKIP_EXISTING_PASS_EXTENSION_AWARE_STATE_CHAIN_BATCH_SYNTHETIC_ONLY",
                "execution_id": prior_root.name,
                "state_chain_terminal_receipt_sha256": execution.sha256_file(
                    prior_terminal_path
                ),
                "completed_pair_count": final["completed_pair_count"],
                "new_pair_ids": prior_receipt["underlying_batch"]["new_pair_ids"],
                "model_loaded": False,
                "inference_calls": 0,
                "synthetic_only": True,
            }

    active = _open_intents(static["paths"])
    if active:
        intent = active[0]["intent"]
        execution_root = active[0]["root"]
        execution_id = str(intent.get("execution_id", ""))
        request = intent.get("request", {})
        request_identity = execution.stable_sha256(request)
        if (
            request.get("target_pair_id") != normalized_pair_ids[0]
            or request.get("max_new_pairs") != 1
            or intent.get("request_identity_sha256") != request_identity
            or execution_root.name != execution_id
            or request.get("state_chain_release_identity_sha256")
            != release["release_identity_sha256"]
        ):
            raise execution.ContractError("Existing state-chain resume request changed")
        open_validation = validate_state_chain_release(
            config_path, allow_open_execution_id=execution_id
        )
        if (
            request.get("predecessor_head_identity_sha256")
            != open_validation["chain_head_identity_sha256"]
        ):
            raise execution.ContractError("Existing intent predecessor head changed")
        initial = {
            "completed_pair_count": int(intent["boundary_at_start"]["completed_pair_count"]),
            "chain_head_identity_sha256": intent[
                "predecessor_head_identity_sha256"
            ],
            "render_state_sha256": intent["boundary_at_start"][
                "render_state_sha256"
            ],
            "candidate_rejection_ledger_sha256": intent["boundary_at_start"][
                "candidate_rejection_ledger_sha256"
            ],
            "candidate_rejection_ledger_row_count": intent["boundary_at_start"][
                "candidate_rejection_ledger_row_count"
            ],
        }
        resumed = True
    else:
        # A clean validation is required before any new intent or GT access.
        initial = validate_state_chain_release(config_path)
        request = _normalize_request(
            initial,
            release["release_identity_sha256"],
            normalized_pair_ids,
            max_new_pairs,
        )
        execution_id, request_identity = _execution_identity(request)
        intent = {
            "schema_version": 1,
            "contract": INTENT_CONTRACT,
            "status": "EXTENSION_AWARE_STATE_CHAIN_BATCH_INTENT_SYNTHETIC_ONLY",
            "execution_id": execution_id,
            "request_identity_sha256": request_identity,
            "request": request,
            "predecessor_head_identity_sha256": initial[
                "chain_head_identity_sha256"
            ],
            "boundary_at_start": {
                "render_state_sha256": initial["render_state_sha256"],
                "candidate_rejection_ledger_sha256": initial[
                    "candidate_rejection_ledger_sha256"
                ],
                "candidate_rejection_ledger_row_count": initial[
                    "candidate_rejection_ledger_row_count"
                ],
                "completed_pair_count": initial["completed_pair_count"],
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
        execution_root, resumed = _publish_or_resume_intent(
            executions_parent, execution_id, intent
        )
        open_validation = validate_state_chain_release(
            config_path, allow_open_execution_id=execution_id
        )

    intent_path = execution_root / "state_chain_intent.json"
    terminal_path = execution_root / "state_chain_terminal_receipt.json"
    docs_terminal = static["paths"]["docs_executions"] / f"{execution_id}.json"
    head_count = initial["completed_pair_count"]
    if open_validation["completed_pair_count"] == head_count:
        underlying = _call_unchanged_batch(
            config_path, request["target_pair_id"], execution_id=execution_id
        )
    elif open_validation["completed_pair_count"] == head_count + 1:
        # Exact crash recovery after the unchanged batch published and sealed
        # its receipt but before the state-chain commit was written.
        rows = execution.full_roster_rows(config)
        historical_plan = adapter._historical_plan_binding(config, open_validation)
        lock = execution.ensure_locked_test_render_batch_execution_lock(
            config_path, config, historical_plan
        )
        batch_request = {
            "schema_version": 1,
            "contract": execution.LOCKED_TEST_RENDER_BATCH_CONTRACT,
            "execution_config_sha256": execution.sha256_file(config_path),
            "pair_roster_sha256": historical_plan["pair_roster_sha256"],
            "batch_execution_lock_sha256": lock["sha256"],
            "target_pair_ids": [request["target_pair_id"]],
            "max_new_pairs": 1,
            "protocol_split": "locked_test",
            "render_and_machine_audit_only": True,
            "model_access_allowed": False,
            "prediction_access_allowed": False,
            "locked_test_outcome_access_allowed": False,
        }
        batch_identity = execution.stable_sha256(batch_request)
        batch_id = f"locked_test_render_batch_{request['target_pair_id']}_{batch_identity[:16]}"
        batch_receipt = (
            execution.full_paths(config)["synthetic"]
            / "planning/locked_test_render_batches_v1"
            / batch_id
            / "batch_receipt.json"
        )
        receipt = execution.load_json(batch_receipt)
        execution._validate_locked_test_render_batch_receipt(
            receipt, batch_identity, [request["target_pair_id"]]
        )
        underlying = {
            "batch_id": batch_id,
            "new_pair_ids": receipt["new_pair_ids"],
        }
    else:
        raise execution.ContractError("Open state-chain intent advanced by more than one pair")
    if execution.validate_full_plan is not _ORIGINAL_VALIDATE_FULL_PLAN:
        raise execution.ContractError("Legacy validator was not restored")

    state_path, _, ledger_path = _state_paths(config)
    result_state = execution.load_json(state_path)
    result_ledger = execution.read_jsonl(ledger_path)
    predecessor_commit = _list_commits(static["paths"])[-1]
    _validate_state_transition(
        predecessor_commit["state"],
        result_state,
        _canonical_pair_ids(roster["combined"]),
        request["target_pair_id"],
    )
    _validate_ledger_extension(
        predecessor_commit["ledger"],
        result_ledger,
        roster["combined"],
        request["target_pair_id"],
    )
    pair_index = int(result_state["completed_pair_count"]) - 1
    ledger_by_pair: dict[str, list[int]] = defaultdict(list)
    for row in result_ledger:
        ledger_by_pair[str(row["pair_id"])].append(int(row["candidate_index"]))
    pair_evidence = _validate_published_pair(
        config,
        roster["historical"][pair_index],
        roster["combined"][pair_index],
        ledger_by_pair.get(request["target_pair_id"], []),
    )
    batch_id = str(underlying["batch_id"])
    batch_root = (
        execution.full_paths(config)["synthetic"]
        / "planning/locked_test_render_batches_v1"
        / batch_id
    )
    record = _transition_record_payload(
        sequence=int(result_state["completed_pair_count"]),
        chain_root_identity=root["chain_root_identity_sha256"],
        predecessor_head_identity=predecessor_commit["head"]["head_identity_sha256"],
        predecessor_state_sha256=execution.sha256_file(
            predecessor_commit["path"] / "result_state.json"
        ),
        result_state_sha256=execution.sha256_file(state_path),
        predecessor_ledger_sha256=execution.sha256_file(
            predecessor_commit["path"] / "result_ledger.jsonl"
        ),
        result_ledger_sha256=execution.sha256_file(ledger_path),
        pair_evidence=pair_evidence,
        execution_evidence={
            "epoch": "extension_aware_state_chain_v1",
            "state_chain_execution_id": execution_id,
            "state_chain_intent_sha256": execution.sha256_file(intent_path),
            "underlying_batch_id": batch_id,
            "underlying_batch_intent_sha256": execution.sha256_file(
                batch_root / "batch_intent.json"
            ),
            "underlying_batch_receipt_sha256": execution.sha256_file(
                batch_root / "batch_receipt.json"
            ),
            "original_validator_restored": True,
        },
    )
    transition = _publish_transition_commit(
        static["paths"]["commits"],
        static["paths"]["docs_commits"],
        record,
        result_state,
        result_ledger,
    )
    terminal = _terminal_payload(
        config, intent, intent_path, transition, underlying, resumed
    )
    _validate_terminal_receipt(
        config, terminal, intent, intent_path, static["paths"]
    )
    execution._write_json_once_atomically(terminal_path, terminal)
    execution._write_json_once_atomically(docs_terminal, terminal)
    final = validate_state_chain_release(config_path)
    return {
        "status": terminal["status"],
        "execution_id": execution_id,
        "state_chain_terminal_receipt_sha256": execution.sha256_file(terminal_path),
        "transition_commit_identity_sha256": transition["commit_identity_sha256"],
        "new_pair_ids": list(underlying["new_pair_ids"]),
        "completed_pair_count": final["completed_pair_count"],
        "pending_pair_count": final["pending_pair_count"],
        "model_loaded": False,
        "inference_calls": 0,
        "synthetic_only": True,
    }


def state_chain_implementation_sha256() -> str:
    functions = (
        _verify_immutable_parents,
        _validate_state_shape,
        _validate_state_transition,
        _validate_ledger_rows,
        _validate_ledger_extension,
        _validate_published_pair,
        _validate_commit_directory,
        _publish_transition_commit,
        _validate_commit_chain,
        _validate_live_against_chain,
        extension_aware_state_chain_validate_full_plan,
        _call_unchanged_batch,
        _publish_or_resume_intent,
        run_state_chain_batch,
    )
    return execution.stable_sha256(
        {
            "contract": CONTRACT,
            "functions": {
                function.__name__: inspect.getsource(function) for function in functions
            },
            "immutable_parent_batch_implementation_sha256": (
                LOCKED_TEST_BATCH_IMPLEMENTATION_SHA256
            ),
            "immutable_adapter_release_identity_sha256": (
                ADAPTER_RELEASE_IDENTITY_SHA256
            ),
        }
    )


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
            result = seal_state_chain_release(arguments.config)
        elif arguments.command == "validate":
            result = validate_state_chain_release(arguments.config)
        elif arguments.command == "run":
            result = run_state_chain_batch(
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
