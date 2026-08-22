from __future__ import annotations

import copy
import functools
import shutil
from pathlib import Path

import pytest

from scripts import run_spot_spray_simulation_video_ab_execution_v1 as execution
from scripts import run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v1 as recovery
from scripts import run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1 as state_chain


RUNTIME_CONFIG = recovery.DEFAULT_CONFIG


def _temporary_paths(tmp_path: Path) -> dict[str, Path]:
    synthetic_root = tmp_path / "synthetic/extension_aware_state_chain_recovery_v1"
    docs_root = tmp_path / "docs/extension_aware_state_chain_recovery_v1"
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


def _fixture_recovery_artifacts(root: Path, config: dict, *, commit: bool) -> dict[str, Path]:
    destination = root / "candidate_01"
    destination.mkdir(parents=True)
    terminal = {
        "contract": execution.LOCKED_TEST_GT_SOURCE_CARDINALITY_RECOVERY_CONTRACT,
        "status": "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY",
        "pair_id": recovery.PAIR_ID,
        "candidate_index": recovery.CANDIDATE_INDEX,
        "candidate_identity_sha256": recovery.CANDIDATE_IDENTITY_SHA256,
        "batch_id": recovery.BATCH_ID,
        "batch_intent_sha256": recovery.BATCH_INTENT_SHA256,
        "recovery_execution_lock_sha256": recovery.RECOVERY_LOCK_SHA256,
        "recovery_implementation_sha256": recovery.RECOVERY_IMPLEMENTATION_SHA256,
        "model_loaded": False,
        "inference_calls": 0,
        "locked_test_prediction_accessed": False,
        "locked_test_outcome_accessed": False,
        "outcome_inputs": [],
        "acceptance_authority": "none",
        "claim_boundary": copy.deepcopy(config["evidence_policy"]),
    }
    decision = {
        "rejection_reasons": ["eligibility:source_weed_track_present"],
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
                "candidate_index": recovery.CANDIDATE_INDEX,
                "candidate_identity_sha256": recovery.CANDIDATE_IDENTITY_SHA256,
                "model_or_outcome_inputs_used": False,
                "idempotent": True,
            },
        )
    return {"destination": destination}


def test_cli_scope_and_exact_target_are_explicit() -> None:
    assert recovery.parse_args(["seal"]).command == "seal"
    assert recovery.parse_args(["validate"]).command == "validate"
    assert recovery.parse_args(["recover"]).command == "recover"
    config = execution.load_config(RUNTIME_CONFIG)
    authorization = recovery._authorization_payload(config)
    assert authorization["authorized_top_level_source_paths"] == [
        recovery.AUTHORIZED_SOURCE_PATH,
        recovery.AUTHORIZED_TEST_PATH,
    ]
    assert authorization["authorized_target"] == {
        "state_chain_execution_id": recovery.STATE_CHAIN_EXECUTION_ID,
        "batch_id": recovery.BATCH_ID,
        "pair_id": recovery.PAIR_ID,
        "candidate_index": 1,
        "candidate_identity_sha256": recovery.CANDIDATE_IDENTITY_SHA256,
    }
    assert authorization["authority"]["candidate_acceptance_allowed"] is False
    assert authorization["authority"]["gate_relaxation_allowed"] is False


def test_all_parent_source_release_and_recovery_identities_are_exact() -> None:
    config, parent = recovery._verify_immutable_parents(RUNTIME_CONFIG)
    assert parent["parents"]["state_chain_script_sha256"] == (
        recovery.STATE_CHAIN_SCRIPT_SHA256
    )
    assert parent["parents"]["state_chain_release_identity_sha256"] == (
        recovery.STATE_CHAIN_RELEASE_IDENTITY_SHA256
    )
    assert parent["parents"]["locked_test_recovery_lock_sha256"] == (
        recovery.RECOVERY_LOCK_SHA256
    )
    assert config["evidence_policy"]["field_or_deployment_claim_allowed"] is False


def test_live_open_boundary_binds_exact_candidate_and_zero_access() -> None:
    _, _, boundary = recovery._validate_open_parent_boundary(RUNTIME_CONFIG)
    assert boundary["completed_pair_count"] == 44
    assert boundary["pending_pair_count"] == 52
    assert boundary["first_pending_pair_id"] == recovery.PAIR_ID
    assert boundary["candidate_rejection_ledger_row_count"] == 122
    assert boundary["candidate_index"] == 1
    assert boundary["candidate_identity_sha256"] == recovery.CANDIDATE_IDENTITY_SHA256
    assert boundary["model_loaded"] is False
    assert boundary["inference_calls"] == 0
    assert boundary["outcome_inputs"] == []


@pytest.mark.parametrize(
    "target_kind",
    [
        "legacy_source",
        "state_chain_source",
        "state_chain_release",
        "recovery_lock",
        "pass86_receipt",
        "state_chain_intent",
        "batch_intent",
        "state",
        "ledger",
    ],
)
def test_parent_state_head_ledger_or_intent_hash_drift_fails_before_wrapper_intent(
    target_kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    state_path, _, ledger_path = state_chain._state_paths(config)
    targets = {
        "legacy_source": recovery._source_paths()["legacy_execution"],
        "state_chain_source": recovery._source_paths()["state_chain"],
        "state_chain_release": state_chain.state_chain_paths(config)["release_file"],
        "recovery_lock": recovery._recovery_lock_path(config),
        "pass86_receipt": recovery._pass86_receipt_path(config),
        "state_chain_intent": recovery._state_chain_intent_path(config),
        "batch_intent": recovery._batch_root(config) / "batch_intent.json",
        "state": state_path,
        "ledger": ledger_path,
    }
    target = targets[target_kind].resolve()
    original = execution.sha256_file

    def drifted(path: Path) -> str:
        if Path(path).resolve() == target:
            return "0" * 64
        return original(Path(path))

    monkeypatch.setattr(execution, "sha256_file", drifted)
    with pytest.raises(execution.ContractError):
        recovery._validate_open_parent_boundary(RUNTIME_CONFIG)


def test_wrong_or_parallel_open_state_chain_intent_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = state_chain.validate_state_chain_release

    def changed(*args: object, **kwargs: object) -> dict:
        result = original(*args, **kwargs)
        result["active_execution_id"] = "state_chain_batch_wrong"
        return result

    monkeypatch.setattr(state_chain, "validate_state_chain_release", changed)
    with pytest.raises(execution.ContractError, match="boundary changed"):
        recovery._validate_open_parent_boundary(RUNTIME_CONFIG)


def test_request_is_fixed_to_one_rejection_only_candidate() -> None:
    request = recovery._request("1" * 64)
    assert request["pair_id"] == recovery.PAIR_ID
    assert request["candidate_index"] == 1
    assert request["candidate_identity_sha256"] == recovery.CANDIDATE_IDENTITY_SHA256
    assert request["rejection_authority"] == (
        "exact_locked_validator_zero_source_weed_failure_only"
    )
    assert request["acceptance_authority"] == "none"
    assert request["model_prediction_outcome_target_or_external_access_allowed"] is False


def test_only_validator_is_partially_bound_and_all_callables_restore_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_recovery = execution.run_locked_test_gt_source_cardinality_recovery
    observed: dict[str, object] = {}

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
        observed.update(
            config_path=config_path,
            pair_id=pair_id,
            candidate_index=candidate_index,
            batch_id=batch_id,
        )
        return {"status": "fixture"}

    monkeypatch.setattr(execution, "run_locked_test_gt_source_cardinality_recovery", fake_recovery)
    monkeypatch.setattr(recovery, "_ORIGINAL_RECOVERY_CALLABLE", fake_recovery)
    before = recovery._callable_snapshot()
    result = recovery._call_unchanged_recovery(RUNTIME_CONFIG)
    assert result == {"status": "fixture"}
    assert observed["pair_id"] == recovery.PAIR_ID
    assert observed["candidate_index"] == 1
    assert observed["batch_id"] == recovery.BATCH_ID
    assert execution.validate_full_plan is recovery._ORIGINAL_VALIDATE_FULL_PLAN
    assert recovery._callable_snapshot() == before
    monkeypatch.setattr(execution, "run_locked_test_gt_source_cardinality_recovery", original_recovery)


def test_all_callables_restore_after_recovery_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(*args: object, **kwargs: object) -> dict:
        raise RuntimeError("fixture zero-source failure")

    monkeypatch.setattr(execution, "run_locked_test_gt_source_cardinality_recovery", failing)
    monkeypatch.setattr(recovery, "_ORIGINAL_RECOVERY_CALLABLE", failing)
    before = recovery._callable_snapshot()
    with pytest.raises(RuntimeError, match="fixture zero-source failure"):
        recovery._call_unchanged_recovery(RUNTIME_CONFIG)
    assert recovery._callable_snapshot() == before
    assert execution.validate_full_plan is recovery._ORIGINAL_VALIDATE_FULL_PLAN


def test_callable_tampering_fails_closed_and_is_restored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read = execution.read_jsonl

    def tampering(*args: object, **kwargs: object) -> dict:
        execution.read_jsonl = lambda path: []
        return {"status": "fixture"}

    monkeypatch.setattr(execution, "run_locked_test_gt_source_cardinality_recovery", tampering)
    monkeypatch.setattr(recovery, "_ORIGINAL_RECOVERY_CALLABLE", tampering)
    with pytest.raises(execution.ContractError, match="Unauthorized"):
        recovery._call_unchanged_recovery(RUNTIME_CONFIG)
    assert execution.read_jsonl is original_read
    assert execution.validate_full_plan is recovery._ORIGINAL_VALIDATE_FULL_PLAN


def test_recovery_callable_identity_tampering_fails_before_patch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        execution,
        "run_locked_test_gt_source_cardinality_recovery",
        lambda *args, **kwargs: {},
    )
    with pytest.raises(execution.ContractError, match="callable identity changed"):
        recovery._call_unchanged_recovery(RUNTIME_CONFIG)
    assert execution.validate_full_plan is recovery._ORIGINAL_VALIDATE_FULL_PLAN


def test_intent_is_atomic_exact_idempotent_and_rejects_parallel_or_partial(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "executions"
    request = recovery._request("1" * 64)
    execution_id, identity = recovery._execution_identity(request)
    intent = {"request_identity_sha256": identity, "request": request}
    root, resumed = recovery._publish_or_resume_intent(parent, execution_id, intent)
    assert resumed is False
    repeated, resumed = recovery._publish_or_resume_intent(parent, execution_id, intent)
    assert repeated == root
    assert resumed is True
    changed = copy.deepcopy(intent)
    changed["request"]["candidate_index"] = 2
    with pytest.raises(execution.ContractError, match="intent changed"):
        recovery._publish_or_resume_intent(parent, execution_id, changed)
    other = parent / "state_chain_recovery_other_0123456789abcdef"
    other.mkdir()
    execution.write_json(other / "recovery_bridge_intent.json", {"request": {}})
    with pytest.raises(execution.ContractError, match="parallel"):
        recovery._publish_or_resume_intent(parent, execution_id, intent)
    shutil_target = other
    for child in shutil_target.iterdir():
        child.unlink()
    shutil_target.rmdir()
    (parent / ".partial-forged").mkdir()
    with pytest.raises(execution.ContractError, match="Partial"):
        recovery._publish_or_resume_intent(parent, execution_id, intent)


def test_wrapper_execution_root_validation_rejects_wrong_and_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _temporary_paths(tmp_path)
    config = execution.load_config(RUNTIME_CONFIG)
    monkeypatch.setattr(recovery, "recovery_bridge_paths", lambda _config: paths)
    recovery._validate_wrapper_execution_roots(config, allow_execution_id=None)
    wrong = paths["executions"] / "wrong_execution"
    wrong.mkdir(parents=True)
    execution.write_json(wrong / "recovery_bridge_intent.json", {})
    with pytest.raises(execution.ContractError, match="Wrong or parallel"):
        recovery._validate_wrapper_execution_roots(
            config, allow_execution_id="expected_execution"
        )
    (paths["executions"] / ".partial-forged").mkdir()
    with pytest.raises(execution.ContractError, match="Partial"):
        recovery._validate_wrapper_execution_roots(config, allow_execution_id=None)


def test_recovery_artifact_validation_accepts_only_exact_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    fixture = _fixture_recovery_artifacts(tmp_path, config, commit=True)
    docs = tmp_path / "docs_receipt.json"
    terminal = fixture["destination"] / "recovery_terminal_receipt.json"
    docs.write_bytes(terminal.read_bytes())
    monkeypatch.setattr(recovery, "_recovery_destination", lambda _config: fixture["destination"])
    monkeypatch.setattr(recovery, "_recovery_docs_receipt", lambda _config: docs)
    evidence = recovery._validate_recovery_artifacts(config, require_commit=True)
    assert evidence["recovery_terminal_receipt_sha256"] == execution.sha256_file(terminal)
    changed = execution.load_json(fixture["destination"] / "decision_receipt.json")
    changed["recovery_has_acceptance_authority"] = True
    execution.write_json(fixture["destination"] / "decision_receipt.json", changed)
    with pytest.raises(execution.ContractError, match="evidence changed"):
        recovery._validate_recovery_artifacts(config, require_commit=True)


def test_partial_recovery_publication_fails_closed_when_terminal_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    destination = tmp_path / "candidate_01"
    destination.mkdir()
    execution.write_json(destination / "decision_receipt.json", {})
    monkeypatch.setattr(recovery, "_recovery_destination", lambda _config: destination)
    with pytest.raises(execution.ContractError, match="incomplete"):
        recovery._validate_recovery_artifacts(config, require_commit=False)


def test_release_file_set_rejects_extra_missing_and_mirror_drift(tmp_path: Path) -> None:
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
        '{"changed":true}\n', encoding="utf-8"
    )
    with pytest.raises(execution.ContractError, match="mirror changed"):
        recovery._validate_release_file_set(paths)


def test_implementation_identity_is_deterministic() -> None:
    first = recovery.recovery_bridge_implementation_sha256()
    second = recovery.recovery_bridge_implementation_sha256()
    assert first == second
    assert execution.SHA256_RE.fullmatch(first)


def test_temporary_release_seal_is_byte_stable_and_zero_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _temporary_paths(tmp_path)
    monkeypatch.setattr(recovery, "recovery_bridge_paths", lambda _config: paths)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Pass87 validation invoked an external process")

    monkeypatch.setattr(execution.subprocess, "run", forbidden)
    first = recovery.seal_recovery_bridge_release(RUNTIME_CONFIG)
    before = {
        relative: execution.sha256_file(paths["synthetic_release"] / relative)
        for relative in recovery._required_release_files()
    }
    second = recovery.seal_recovery_bridge_release(RUNTIME_CONFIG)
    after = {
        relative: execution.sha256_file(paths["synthetic_release"] / relative)
        for relative in recovery._required_release_files()
    }
    assert first == second
    assert before == after
    assert first["status"] == "READY_FOR_STATE_CHAIN_RECOVERY_EXECUTION_SYNTHETIC_ONLY"
    assert first["real_recovery_bridge_intents_created"] == 0
    assert first["candidate_gt_accessed"] is False
    assert first["rendering_calls"] == 0
    assert first["model_loaded"] is False
    assert first["inference_calls"] == 0
    assert first["outcome_inputs"] == []
    assert first["field_product_or_chemical_go"] is False
    assert not paths["executions"].exists()


def test_terminal_receipt_rejects_state_advance_or_forbidden_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    request = recovery._request("1" * 64)
    execution_id, identity = recovery._execution_identity(request)
    intent_path = tmp_path / "intent.json"
    execution.write_json(intent_path, {"request": request})
    current = {
        "candidate_rejection_ledger_sha256": "2" * 64,
        "recovery_evidence": {
            "recovery_terminal_receipt_sha256": "3" * 64,
            "decision_receipt_sha256": "4" * 64,
            "ledger_commit_receipt_sha256": "5" * 64,
        },
    }
    underlying = {
        "status": "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY",
        "pair_id": recovery.PAIR_ID,
        "candidate_index": 1,
        "batch_id": recovery.BATCH_ID,
    }
    before = {
        "render_state_sha256": recovery.CURRENT_STATE_SHA256,
        "chain_head_identity_sha256": recovery.CURRENT_HEAD_IDENTITY_SHA256,
        "candidate_rejection_ledger_sha256": recovery.CURRENT_LEDGER_SHA256,
        "candidate_rejection_ledger_row_count": recovery.CURRENT_LEDGER_ROW_COUNT,
    }
    after = {
        **before,
        "candidate_rejection_ledger_sha256": "2" * 64,
        "candidate_rejection_ledger_row_count": recovery.CURRENT_LEDGER_ROW_COUNT + 1,
        "recovery_evidence": current["recovery_evidence"],
    }
    receipt = recovery._terminal_payload(
        config,
        request,
        identity,
        execution_id,
        intent_path,
        underlying,
        before,
        after,
        False,
    )
    recovery._validate_terminal_receipt(
        config, receipt, request, identity, execution_id, intent_path, current
    )
    changed = copy.deepcopy(receipt)
    changed["boundary"]["render_state_sha256_after"] = "6" * 64
    with pytest.raises(execution.ContractError, match="terminal receipt changed"):
        recovery._validate_terminal_receipt(
            config, changed, request, identity, execution_id, intent_path, current
        )
    changed = copy.deepcopy(receipt)
    changed["access_guard"]["inference_calls"] = 1
    with pytest.raises(execution.ContractError, match="terminal receipt changed"):
        recovery._validate_terminal_receipt(
            config, changed, request, identity, execution_id, intent_path, current
        )


def test_live_release_validates_repeatedly_without_recovery_when_sealed() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    paths = recovery.recovery_bridge_paths(config)
    if not paths["release"].is_file():
        pytest.skip("Pass87 release is sealed after pre-seal regressions")
    first = recovery.validate_recovery_bridge_release(RUNTIME_CONFIG)
    second = recovery.validate_recovery_bridge_release(RUNTIME_CONFIG)
    assert first == second
    assert first["status"] == "READY_FOR_STATE_CHAIN_RECOVERY_EXECUTION_SYNTHETIC_ONLY"
    assert first["completed_pair_count"] == 44
    assert first["candidate_rejection_ledger_row_count"] == 122
    assert first["real_recovery_bridge_intents_created"] == 0
    assert first["candidate_gt_accessed"] is False
    assert first["rendering_calls"] == 0
    assert first["model_loaded"] is False
    assert first["inference_calls"] == 0
    assert first["field_product_or_chemical_go"] is False


def test_live_release_is_exactly_mirrored_and_has_no_execution_when_sealed() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    paths = recovery.recovery_bridge_paths(config)
    if not paths["release"].is_file():
        pytest.skip("Pass87 release is sealed after pre-seal regressions")
    assert not paths["executions"].exists()
    assert not paths["docs_executions"].exists()
    for relative in recovery._required_release_files():
        assert execution.sha256_file(
            paths["synthetic_release"] / relative
        ) == execution.sha256_file(paths["docs_release"] / relative)
    receipt = execution.load_json(paths["validation_receipt"])
    assert receipt["pass87_access_guard"]["validation_only"] is True
    assert receipt["pass87_access_guard"]["candidate_gt_accessed"] is False
    assert receipt["pass87_access_guard"]["external_services_modified"] is False
