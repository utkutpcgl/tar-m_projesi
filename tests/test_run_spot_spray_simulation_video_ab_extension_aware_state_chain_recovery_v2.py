from __future__ import annotations

import copy
import functools
import json
import shutil
from pathlib import Path

import pytest

from scripts import run_spot_spray_simulation_video_ab_execution_v1 as execution
from scripts import run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v2 as recovery
from scripts import run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1 as state_chain


RUNTIME_CONFIG = recovery.DEFAULT_CONFIG


def _temporary_paths(tmp_path: Path) -> dict[str, Path]:
    synthetic_root = tmp_path / "synthetic/extension_aware_state_chain_recovery_v2"
    docs_root = tmp_path / "docs/extension_aware_state_chain_recovery_v2"
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


def _live_context() -> tuple[dict, list[dict], dict, Path, list[dict]]:
    config = execution.load_config(RUNTIME_CONFIG)
    rows = execution.full_roster_rows(config)
    roster_row = dict(recovery._pair_roster_row(rows))
    ledger_path = state_chain._state_paths(config)[2]
    ledger = execution.read_jsonl(ledger_path)
    return config, rows, roster_row, ledger_path, ledger


def _base_ledger_file(tmp_path: Path, live_ledger_path: Path) -> Path:
    lines = live_ledger_path.read_bytes().splitlines(keepends=True)
    path = tmp_path / "ledger.jsonl"
    path.write_bytes(b"".join(lines[: recovery.BASE_LEDGER_ROW_COUNT]))
    assert execution.sha256_file(path) == recovery.BASE_LEDGER_SHA256
    return path


def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _fixture_recovery_artifacts(
    root: Path,
    config: dict,
    roster_row: dict,
    candidate_index: int,
    *,
    commit: bool,
) -> tuple[Path, Path, dict]:
    candidate = roster_row["candidates"][candidate_index]
    destination = root / f"candidate_{candidate_index:02d}"
    destination.mkdir(parents=True)
    terminal = {
        "contract": execution.LOCKED_TEST_GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
        "status": "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY",
        "pair_id": recovery.PAIR_ID,
        "protocol_split": "locked_test",
        "pair_slot_identity_sha256": recovery.PAIR_SLOT_IDENTITY_SHA256,
        "candidate_index": candidate_index,
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "candidate_seeds": copy.deepcopy(candidate["seeds"]),
        "source_template": copy.deepcopy(candidate["source_template"]),
        "source_template_sha256_exact": True,
        "batch_id": recovery.BATCH_ID,
        "batch_intent_sha256": recovery.BATCH_INTENT_SHA256,
        "recovery_execution_lock_sha256": recovery.RECOVERY_LOCK_SHA256,
        "recovery_implementation_sha256": recovery.RECOVERY_IMPLEMENTATION_SHA256,
        "source_cardinality_audit": {
            "locked_botanical_validator_failure": "Too few source weed tracks: 0",
            "source_weed_track_count": 0,
            "rejection_reason": "eligibility:source_weed_track_present",
            "model_or_outcome_inputs_used": False,
        },
        "model_loaded": False,
        "inference_calls": 0,
        "locked_test_prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "outcome_inputs": [],
        "acceptance_authority": "none",
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    decision = {
        "contract": execution.GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
        "pair_id": recovery.PAIR_ID,
        "rejectable_by_scout": True,
        "rejection_reasons": ["eligibility:source_weed_track_present"],
        "source_cardinality_checks": {
            "source_crop_track_present": True,
            "source_weed_track_present": False,
        },
        "full_render_still_required_for_acceptance": True,
        "recovery_has_acceptance_authority": False,
        "model_or_outcome_inputs_used": False,
        "registered_targets_used": False,
        "locked_test_prediction_accessed": False,
        "locked_test_outcome_accessed": False,
    }
    execution.write_json(destination / "recovery_terminal_receipt.json", terminal)
    execution.write_json(destination / "decision_receipt.json", decision)
    if commit:
        execution.write_json(
            destination / "ledger_commit_receipt.json",
            {
                "pair_id": recovery.PAIR_ID,
                "candidate_index": candidate_index,
                "candidate_identity_sha256": candidate[
                    "candidate_identity_sha256"
                ],
                "model_or_outcome_inputs_used": False,
                "idempotent": True,
            },
        )
    docs = root / f"docs_candidate_{candidate_index:02d}.json"
    docs.write_bytes((destination / "recovery_terminal_receipt.json").read_bytes())
    row = {
        "schema_version": 1,
        "status": "REJECTED_FULL_PAIR_CANDIDATE_PREOUTCOME_SYNTHETIC_ONLY",
        "pair_id": recovery.PAIR_ID,
        "candidate_index": candidate_index,
        "candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "reason_type": "GtScoutCandidateRejected",
        "reason": "eligibility:source_weed_track_present",
        "gt_scout_terminal_receipt_sha256": execution.sha256_file(
            destination / "recovery_terminal_receipt.json"
        ),
        "gt_scout_decision_receipt_sha256": execution.sha256_file(
            destination / "decision_receipt.json"
        ),
        "rejection_families": [
            "frozen_semantic_operability",
            "frozen_eligible_weed_temporal_denominator",
        ],
        "model_or_outcome_inputs_used": False,
        "bulk_payload_retained": False,
    }
    return destination, docs, row


def test_cli_scope_and_reusable_rejection_authority_are_explicit() -> None:
    assert recovery.parse_args(["seal"]).command == "seal"
    assert recovery.parse_args(["validate"]).command == "validate"
    assert recovery.parse_args(["recover"]).command == "recover"
    config = execution.load_config(RUNTIME_CONFIG)
    authorization = recovery._authorization_payload(config)
    assert authorization["authorized_top_level_source_paths"] == [
        recovery.AUTHORIZED_SOURCE_PATH,
        recovery.AUTHORIZED_TEST_PATH,
    ]
    scope = authorization["authorized_candidate_scope"]
    assert scope["first_candidate_index"] == 2
    assert scope["last_candidate_index"] == 31
    assert scope["caller_supplied_candidate_allowed"] is False
    assert scope["derive_exactly_one_with_execution_next_gt_scout_candidate"] is True
    assert authorization["authority"]["candidate_acceptance_allowed"] is False
    assert authorization["authority"]["render_or_pair_publication_allowed"] is False


def test_all_parent_v1_release_intent_terminal_and_lock_identities_are_exact() -> None:
    config, parent = recovery._verify_immutable_parents(RUNTIME_CONFIG)
    assert parent["parents"]["state_chain_release_identity_sha256"] == (
        recovery.STATE_CHAIN_RELEASE_IDENTITY_SHA256
    )
    assert parent["parents"]["recovery_v1_release_identity_sha256"] == (
        recovery.RECOVERY_V1_RELEASE_IDENTITY_SHA256
    )
    assert parent["parents"]["recovery_v1_terminal_receipt_sha256"] == (
        recovery.RECOVERY_V1_TERMINAL_SHA256
    )
    assert parent["parents"]["locked_test_recovery_lock_sha256"] == (
        recovery.RECOVERY_LOCK_SHA256
    )
    assert config["evidence_policy"]["field_or_deployment_claim_allowed"] is False


def test_live_boundary_derives_exact_candidate_two_without_gt_access() -> None:
    _, _, boundary = recovery._validate_open_boundary(RUNTIME_CONFIG)
    assert boundary["completed_pair_count"] == 44
    assert boundary["pending_pair_count"] == 52
    assert boundary["first_pending_pair_id"] == recovery.PAIR_ID
    assert boundary["candidate_rejection_ledger_row_count"] == 123
    assert boundary["candidate_rejection_ledger_sha256"] == recovery.BASE_LEDGER_SHA256
    assert boundary["next_candidate_index"] == 2
    assert boundary["next_candidate_identity_sha256"] == (
        recovery.INITIAL_CANDIDATE_IDENTITY_SHA256
    )
    assert boundary["next_source_template_sha256"] == (
        recovery.INITIAL_SOURCE_TEMPLATE_SHA256
    )
    assert boundary["v2_execution_count"] == 0
    assert boundary["model_loaded"] is False
    assert boundary["inference_calls"] == 0
    assert boundary["outcome_inputs"] == []


@pytest.mark.parametrize(
    "target_key",
    [
        "legacy_execution",
        "state_chain",
        "recovery_v1",
        "recovery_lock",
        "pass90",
        "state_chain_intent",
        "batch_intent",
        "state",
    ],
)
def test_parent_state_head_intent_or_source_drift_fails_before_v2_intent(
    target_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    state_path = state_chain._state_paths(config)[0]
    targets = {
        "legacy_execution": recovery._source_paths()["legacy_execution"],
        "state_chain": recovery._source_paths()["state_chain"],
        "recovery_v1": recovery._source_paths()["recovery_v1"],
        "recovery_lock": recovery._recovery_lock_path(config),
        "pass90": recovery._pass90_receipt_path(config),
        "state_chain_intent": recovery._state_chain_intent_path(config),
        "batch_intent": recovery._batch_root(config) / "batch_intent.json",
        "state": state_path,
    }
    target = targets[target_key].resolve()
    original = execution.sha256_file

    def drifted(path: Path) -> str:
        if Path(path).resolve() == target:
            return "0" * 64
        return original(Path(path))

    monkeypatch.setattr(execution, "sha256_file", drifted)
    with pytest.raises(execution.ContractError):
        recovery._validate_open_boundary(RUNTIME_CONFIG)


def test_state_head_advance_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    original = state_chain.validate_state_chain_release

    def changed(*args: object, **kwargs: object) -> dict:
        result = original(*args, **kwargs)
        result["chain_head_identity_sha256"] = "0" * 64
        return result

    monkeypatch.setattr(state_chain, "validate_state_chain_release", changed)
    with pytest.raises(execution.ContractError, match="boundary changed"):
        recovery._validate_open_boundary(RUNTIME_CONFIG)


@pytest.mark.parametrize("terminal_kind", ["pair", "batch", "state_chain"])
def test_pair_or_parent_terminal_closes_v2_before_candidate_gt(
    terminal_kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    full = execution.full_paths(config)
    targets = {
        "pair": full["synthetic"] / "pairs/locked_test" / recovery.PAIR_ID,
        "batch": recovery._batch_root(config) / "batch_receipt.json",
        "state_chain": (
            state_chain.state_chain_paths(config)["executions"]
            / recovery.STATE_CHAIN_EXECUTION_ID
            / "state_chain_terminal_receipt.json"
        ),
    }
    target = targets[terminal_kind].resolve()
    original_exists = Path.exists

    def exists(path: Path) -> bool:
        if path.resolve() == target:
            return True
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", exists)
    with pytest.raises(execution.ContractError):
        recovery._validate_open_boundary(RUNTIME_CONFIG)


def test_two_sequential_mocked_canonical_recoveries_validate_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, rows, roster_row, live_ledger_path, live_ledger = _live_context()
    destinations: dict[int, Path] = {}
    docs: dict[int, Path] = {}
    appended: list[dict] = []
    for index in (2, 3):
        destination, docs_path, row = _fixture_recovery_artifacts(
            tmp_path, config, roster_row, index, commit=True
        )
        destinations[index] = destination
        docs[index] = docs_path
        appended.append(row)
    monkeypatch.setattr(
        recovery,
        "_recovery_destination",
        lambda _config, index: destinations[index],
    )
    monkeypatch.setattr(
        recovery,
        "_recovery_docs_receipt",
        lambda _config, index: docs[index],
    )
    ledger_path = _base_ledger_file(tmp_path, live_ledger_path)
    ledger = list(live_ledger[: recovery.BASE_LEDGER_ROW_COUNT]) + appended
    _write_ledger(ledger_path, ledger)
    evidence = recovery._validate_appended_rejection_rows(
        config, ledger_path, ledger, rows, roster_row
    )
    assert [item["candidate_index"] for item in evidence] == [2, 3]
    assert [item["candidate_identity_sha256"] for item in evidence] == [
        roster_row["candidates"][2]["candidate_identity_sha256"],
        roster_row["candidates"][3]["candidate_identity_sha256"],
    ]


def test_non_zero_weed_evidence_cannot_append_and_base_ledger_stays_byte_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, rows, roster_row, live_ledger_path, live_ledger = _live_context()
    destination, docs, row = _fixture_recovery_artifacts(
        tmp_path, config, roster_row, 2, commit=True
    )
    terminal_path = destination / "recovery_terminal_receipt.json"
    terminal = execution.load_json(terminal_path)
    terminal["source_cardinality_audit"]["source_weed_track_count"] = 1
    terminal["source_cardinality_audit"]["locked_botanical_validator_failure"] = None
    execution.write_json(terminal_path, terminal)
    row["gt_scout_terminal_receipt_sha256"] = execution.sha256_file(terminal_path)
    docs.write_bytes(terminal_path.read_bytes())
    monkeypatch.setattr(
        recovery, "_recovery_destination", lambda _config, _index: destination
    )
    monkeypatch.setattr(
        recovery, "_recovery_docs_receipt", lambda _config, _index: docs
    )
    ledger_path = _base_ledger_file(tmp_path, live_ledger_path)
    base_before = ledger_path.read_bytes()
    with pytest.raises(execution.ContractError, match="exact recovery evidence"):
        recovery._validate_recovery_artifacts(config, roster_row, 2, require_commit=True)
    assert ledger_path.read_bytes() == base_before
    with pytest.raises(execution.ContractError, match="unauthorized evidence"):
        recovery._validate_underlying_result(
            {
                "status": "PASS_NON_ZERO_WEED",
                "pair_id": recovery.PAIR_ID,
                "candidate_index": 2,
                "batch_id": recovery.BATCH_ID,
                "model_loaded": False,
                "inference_calls": 0,
                "synthetic_only": True,
            },
            2,
        )


@pytest.mark.parametrize("mutation", ["skip", "identity", "reason", "model"])
def test_candidate_skip_forgery_or_gate_row_fails_closed(
    mutation: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, rows, roster_row, live_ledger_path, live_ledger = _live_context()
    index = 3 if mutation == "skip" else 2
    destination, docs, row = _fixture_recovery_artifacts(
        tmp_path, config, roster_row, index, commit=True
    )
    monkeypatch.setattr(
        recovery, "_recovery_destination", lambda _config, _index: destination
    )
    monkeypatch.setattr(
        recovery, "_recovery_docs_receipt", lambda _config, _index: docs
    )
    if mutation == "identity":
        row["candidate_identity_sha256"] = "0" * 64
    elif mutation == "reason":
        row["reason"] = "semantic:relaxed"
    elif mutation == "model":
        row["model_or_outcome_inputs_used"] = True
    ledger_path = _base_ledger_file(tmp_path, live_ledger_path)
    ledger = list(live_ledger[: recovery.BASE_LEDGER_ROW_COUNT]) + [row]
    _write_ledger(ledger_path, ledger)
    with pytest.raises(execution.ContractError):
        recovery._validate_appended_rejection_rows(
            config, ledger_path, ledger, rows, roster_row
        )


@pytest.mark.parametrize("mutation", ["truncate", "rewrite"])
def test_ledger_truncation_or_frozen_prefix_rewrite_fails_closed(
    mutation: str, tmp_path: Path
) -> None:
    config, rows, roster_row, live_ledger_path, live_ledger = _live_context()
    ledger_path = _base_ledger_file(tmp_path, live_ledger_path)
    ledger = list(live_ledger[: recovery.BASE_LEDGER_ROW_COUNT])
    if mutation == "truncate":
        ledger = ledger[:-1]
    else:
        ledger[0] = copy.deepcopy(ledger[0])
        ledger[0]["reason"] = "forged"
    _write_ledger(ledger_path, ledger)
    with pytest.raises(execution.ContractError):
        recovery._validate_appended_rejection_rows(
            config, ledger_path, ledger, rows, roster_row
        )


def test_partial_recovery_publication_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _, roster_row, _, _ = _live_context()
    destination = tmp_path / "candidate_02"
    destination.mkdir()
    execution.write_json(destination / "decision_receipt.json", {})
    monkeypatch.setattr(
        recovery, "_recovery_destination", lambda _config, _index: destination
    )
    with pytest.raises(execution.ContractError, match="incomplete"):
        recovery._validate_recovery_artifacts(config, roster_row, 2, require_commit=False)


def test_only_validator_is_patched_and_all_callables_restore_for_two_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[int] = []

    def fake_recovery(
        config_path: Path,
        pair_id: str,
        *,
        candidate_index: int,
        batch_id: str,
    ) -> dict:
        replacement = execution.validate_full_plan
        assert isinstance(replacement, functools.partial)
        assert replacement.func is state_chain.extension_aware_state_chain_validate_full_plan
        assert replacement.keywords == {
            "allow_open_execution_id": recovery.STATE_CHAIN_EXECUTION_ID
        }
        assert pair_id == recovery.PAIR_ID
        assert batch_id == recovery.BATCH_ID
        observed.append(candidate_index)
        return {"candidate_index": candidate_index}

    monkeypatch.setattr(
        execution, "run_locked_test_gt_source_cardinality_recovery", fake_recovery
    )
    monkeypatch.setattr(recovery, "_ORIGINAL_RECOVERY_CALLABLE", fake_recovery)
    before = recovery._callable_snapshot()
    assert recovery._call_unchanged_recovery(RUNTIME_CONFIG, 2) == {
        "candidate_index": 2
    }
    assert recovery._call_unchanged_recovery(RUNTIME_CONFIG, 3) == {
        "candidate_index": 3
    }
    assert observed == [2, 3]
    assert recovery._callable_snapshot() == before
    assert execution.validate_full_plan is recovery._ORIGINAL_VALIDATE_FULL_PLAN


def test_all_callables_restore_after_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(*args: object, **kwargs: object) -> dict:
        raise RuntimeError("fixture non-zero weed")

    monkeypatch.setattr(
        execution, "run_locked_test_gt_source_cardinality_recovery", failing
    )
    monkeypatch.setattr(recovery, "_ORIGINAL_RECOVERY_CALLABLE", failing)
    before = recovery._callable_snapshot()
    with pytest.raises(RuntimeError, match="non-zero weed"):
        recovery._call_unchanged_recovery(RUNTIME_CONFIG, 2)
    assert recovery._callable_snapshot() == before
    assert execution.validate_full_plan is recovery._ORIGINAL_VALIDATE_FULL_PLAN


def test_callable_tamper_fails_and_restores(monkeypatch: pytest.MonkeyPatch) -> None:
    original_read = execution.read_jsonl

    def tampering(*args: object, **kwargs: object) -> dict:
        execution.read_jsonl = lambda path: []
        return {"status": "fixture"}

    monkeypatch.setattr(
        execution, "run_locked_test_gt_source_cardinality_recovery", tampering
    )
    monkeypatch.setattr(recovery, "_ORIGINAL_RECOVERY_CALLABLE", tampering)
    with pytest.raises(execution.ContractError, match="Unauthorized"):
        recovery._call_unchanged_recovery(RUNTIME_CONFIG, 2)
    assert execution.read_jsonl is original_read
    assert execution.validate_full_plan is recovery._ORIGINAL_VALIDATE_FULL_PLAN


def test_recovery_callable_identity_tamper_fails_before_patch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        execution,
        "run_locked_test_gt_source_cardinality_recovery",
        lambda *args, **kwargs: {},
    )
    with pytest.raises(execution.ContractError, match="callable identity changed"):
        recovery._call_unchanged_recovery(RUNTIME_CONFIG, 2)
    assert execution.validate_full_plan is recovery._ORIGINAL_VALIDATE_FULL_PLAN


def test_intent_publication_is_atomic_idempotent_and_rejects_parallel_or_partial(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "executions"
    request = {
        "candidate_index": 2,
        "contract": recovery.CONTRACT,
    }
    execution_id, identity = recovery._execution_identity(request)
    intent = {"request_identity_sha256": identity, "request": request}
    root, resumed = recovery._publish_or_resume_intent(parent, execution_id, intent)
    assert resumed is False
    repeated, resumed = recovery._publish_or_resume_intent(parent, execution_id, intent)
    assert repeated == root
    assert resumed is True
    changed = copy.deepcopy(intent)
    changed["request"]["candidate_index"] = 3
    with pytest.raises(execution.ContractError, match="intent changed"):
        recovery._publish_or_resume_intent(parent, execution_id, changed)
    other = parent / "state_chain_recovery_v2_other"
    other.mkdir()
    execution.write_json(other / "recovery_bridge_intent.json", {})
    with pytest.raises(execution.ContractError, match="Parallel"):
        recovery._publish_or_resume_intent(parent, execution_id, intent)
    shutil.rmtree(other)
    (parent / ".partial-forged").mkdir()
    with pytest.raises(execution.ContractError, match="Partial"):
        recovery._publish_or_resume_intent(parent, execution_id, intent)


def test_wrapper_roots_reject_parallel_and_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _temporary_paths(tmp_path)
    config = execution.load_config(RUNTIME_CONFIG)
    monkeypatch.setattr(recovery, "recovery_bridge_v2_paths", lambda _config: paths)
    assert recovery._scan_wrapper_execution_roots(config) == []
    (paths["executions"] / ".partial-forged").mkdir(parents=True)
    with pytest.raises(execution.ContractError, match="Partial"):
        recovery._scan_wrapper_execution_roots(config)


def test_release_file_set_rejects_missing_extra_and_mirror_drift(tmp_path: Path) -> None:
    paths = _temporary_paths(tmp_path)
    paths["synthetic_release"].mkdir(parents=True)
    paths["docs_release"].mkdir(parents=True)
    with pytest.raises(execution.ContractError, match="file set changed"):
        recovery._validate_release_file_set(paths)
    for relative in recovery._required_release_files():
        (paths["synthetic_release"] / relative).write_text("{}\n", encoding="utf-8")
        (paths["docs_release"] / relative).write_text("{}\n", encoding="utf-8")
    recovery._validate_release_file_set(paths)
    (paths["docs_release"] / recovery._required_release_files()[0]).write_text(
        '{"drift":true}\n', encoding="utf-8"
    )
    with pytest.raises(execution.ContractError, match="mirror changed"):
        recovery._validate_release_file_set(paths)


def test_implementation_identity_is_deterministic() -> None:
    first = recovery.recovery_bridge_v2_implementation_sha256()
    second = recovery.recovery_bridge_v2_implementation_sha256()
    assert first == second
    assert execution.SHA256_RE.fullmatch(first)


def test_temporary_release_seal_is_byte_stable_and_zero_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _temporary_paths(tmp_path)
    monkeypatch.setattr(recovery, "recovery_bridge_v2_paths", lambda _config: paths)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Pass91 validation invoked an external process")

    monkeypatch.setattr(execution.subprocess, "run", forbidden)
    first = recovery.seal_recovery_bridge_v2_release(RUNTIME_CONFIG)
    before = {
        relative: execution.sha256_file(paths["synthetic_release"] / relative)
        for relative in recovery._required_release_files()
    }
    second = recovery.seal_recovery_bridge_v2_release(RUNTIME_CONFIG)
    after = {
        relative: execution.sha256_file(paths["synthetic_release"] / relative)
        for relative in recovery._required_release_files()
    }
    assert first == second
    assert before == after
    assert first["status"] == "READY_FOR_MANAGER_VALIDATION_SYNTHETIC_ONLY"
    assert first["candidate_rejection_ledger_row_count"] == 123
    assert first["next_candidate_index"] == 2
    assert first["real_recovery_bridge_intents_created_during_validation"] == 0
    assert first["candidate_gt_accessed"] is False
    assert first["rendering_calls"] == 0
    assert first["model_loaded"] is False
    assert first["inference_calls"] == 0
    assert first["outcome_inputs"] == []
    assert first["field_product_or_chemical_go"] is False
    assert not paths["executions"].exists()


def test_terminal_receipt_rejects_state_advance_or_forbidden_access(
    tmp_path: Path,
) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    candidate = execution.full_roster_rows(config)[44]["candidates"][2]
    boundary = {
        "candidate_rejection_ledger_row_count": 123,
        "candidate_rejection_ledger_sha256": recovery.BASE_LEDGER_SHA256,
        "next_candidate_index": 2,
        "next_candidate_identity_sha256": candidate["candidate_identity_sha256"],
        "next_source_template_sha256": candidate["source_template"]["sha256"],
    }
    request = recovery._request("1" * 64, boundary, candidate)
    execution_id, identity = recovery._execution_identity(request)
    intent_path = tmp_path / "intent.json"
    execution.write_json(intent_path, {"request": request})
    after = {
        "render_state_sha256": recovery.CURRENT_STATE_SHA256,
        "chain_head_identity_sha256": recovery.CURRENT_HEAD_IDENTITY_SHA256,
        "candidate_rejection_ledger_sha256": "2" * 64,
        "candidate_rejection_ledger_row_count": 124,
        "recovery_evidence": {
            "recovery_terminal_receipt_sha256": "3" * 64,
            "decision_receipt_sha256": "4" * 64,
            "ledger_commit_receipt_sha256": "5" * 64,
        },
    }
    underlying = {
        "status": "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY",
        "pair_id": recovery.PAIR_ID,
        "candidate_index": 2,
        "batch_id": recovery.BATCH_ID,
    }
    receipt = recovery._terminal_payload(
        config,
        request,
        identity,
        execution_id,
        intent_path,
        underlying,
        boundary,
        after,
        False,
    )
    recovery._validate_terminal_receipt(
        config, receipt, request, identity, execution_id, intent_path, after
    )
    changed = copy.deepcopy(receipt)
    changed["boundary"]["render_state_sha256_after"] = "6" * 64
    with pytest.raises(execution.ContractError, match="terminal receipt changed"):
        recovery._validate_terminal_receipt(
            config, changed, request, identity, execution_id, intent_path, after
        )
    changed = copy.deepcopy(receipt)
    changed["access_guard"]["inference_calls"] = 1
    with pytest.raises(execution.ContractError, match="terminal receipt changed"):
        recovery._validate_terminal_receipt(
            config, changed, request, identity, execution_id, intent_path, after
        )


def test_live_release_validates_twice_without_real_recovery_when_sealed() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    paths = recovery.recovery_bridge_v2_paths(config)
    if not paths["release"].is_file():
        pytest.skip("Pass91 V2 release is sealed after pre-seal regressions")
    first = recovery.validate_recovery_bridge_v2_release(RUNTIME_CONFIG)
    second = recovery.validate_recovery_bridge_v2_release(RUNTIME_CONFIG)
    assert first == second
    assert first["status"] == "READY_FOR_MANAGER_VALIDATION_SYNTHETIC_ONLY"
    assert first["candidate_rejection_ledger_row_count"] == 123
    assert first["next_candidate_index"] == 2
    assert first["v2_execution_count"] == 0
    assert first["candidate_gt_accessed"] is False
    assert first["rendering_calls"] == 0
    assert first["model_loaded"] is False
    assert first["field_product_or_chemical_go"] is False


def test_live_release_mirrors_are_exact_and_no_execution_exists_when_sealed() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    paths = recovery.recovery_bridge_v2_paths(config)
    if not paths["release"].is_file():
        pytest.skip("Pass91 V2 release is sealed after pre-seal regressions")
    assert not paths["executions"].exists()
    assert not paths["docs_executions"].exists()
    for relative in recovery._required_release_files():
        assert execution.sha256_file(
            paths["synthetic_release"] / relative
        ) == execution.sha256_file(paths["docs_release"] / relative)
    receipt = execution.load_json(paths["validation_receipt"])
    assert receipt["pass91_access_guard"]["validation_only"] is True
    assert receipt["pass91_access_guard"]["candidate_gt_accessed"] is False
    assert receipt["pass91_access_guard"]["external_services_modified"] is False
