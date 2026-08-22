from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import run_spot_spray_simulation_video_ab_execution_v1 as execution
from scripts import run_spot_spray_simulation_video_ab_extension_aware_state_chain_recovery_v3 as recovery
from scripts import run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1 as state_chain


RUNTIME_CONFIG = recovery.DEFAULT_CONFIG


def _temporary_paths(tmp_path: Path) -> dict[str, Path]:
    synthetic_root = tmp_path / "synthetic/extension_aware_state_chain_recovery_v3"
    docs_root = tmp_path / "docs/extension_aware_state_chain_recovery_v3"
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


def _live_context() -> tuple[dict, dict, dict]:
    config = execution.load_config(RUNTIME_CONFIG)
    rows = execution.full_roster_rows(config)
    roster = next(row for row in rows if row["pair_id"] == recovery.GENESIS_PAIR_ID)
    candidate = roster["candidates"][recovery.GENESIS_CANDIDATE_INDEX]
    return config, roster, candidate


def _live_boundary() -> dict:
    _, _, boundary = recovery._validate_active_boundary(RUNTIME_CONFIG)
    return boundary


def _request_from_boundary(
    boundary: dict,
    candidate: dict,
    *,
    sequence: int = 1,
    previous: str | None = None,
) -> dict:
    return recovery._request(
        "a" * 64,
        boundary,
        candidate,
        journal_sequence=sequence,
        previous_terminal_receipt_sha256=previous,
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    execution.write_json(path, payload)


def _journal_record(
    config: dict,
    paths: dict[str, Path],
    request: dict,
    *,
    terminal: bool,
) -> tuple[str, str | None]:
    execution_id, identity = recovery._execution_identity(request)
    root = paths["executions"] / execution_id
    intent = recovery._intent_payload(config, request, execution_id, identity)
    intent_path = root / "recovery_bridge_intent.json"
    _write_json(intent_path, intent)
    if not terminal:
        return execution_id, None
    receipt = {
        "schema_version": 1,
        "contract": recovery.TERMINAL_RECEIPT_CONTRACT,
        "status": "PASS_EXACT_ZERO_SOURCE_WEED_REJECTION_V3_SYNTHETIC_ONLY",
        "execution_id": execution_id,
        "request_identity_sha256": identity,
        "request": copy.deepcopy(request),
        "recovery_bridge_intent_sha256": execution.sha256_file(intent_path),
        "original_validator_restored": True,
        "access_guard": recovery._access_guard(),
        "claim_boundary": recovery._claim_boundary(config),
    }
    terminal_path = root / "recovery_bridge_terminal_receipt.json"
    _write_json(terminal_path, receipt)
    docs_path = paths["docs_executions"] / f"{execution_id}.json"
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_bytes(terminal_path.read_bytes())
    return execution_id, execution.sha256_file(terminal_path)


def test_cli_exposes_no_caller_target_selection() -> None:
    assert recovery.parse_args(["seal"]).command == "seal"
    assert recovery.parse_args(["validate"]).command == "validate"
    assert (
        recovery.parse_args(["recover-current-zero-weed"]).command
        == "recover-current-zero-weed"
    )
    with pytest.raises(SystemExit):
        recovery.parse_args(
            ["recover-current-zero-weed", "--pair-id", "locked_test_c999_r99"]
        )
    with pytest.raises(SystemExit):
        recovery.parse_args(["recover-current-zero-weed", "--candidate-index", "9"])


def test_manager_authorization_is_rejection_only_and_validation_only_for_pass108() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    payload = recovery._authorization_payload(config)
    assert payload["authorized_top_level_source_paths"] == [
        recovery.AUTHORIZED_SOURCE_PATH,
        recovery.AUTHORIZED_TEST_PATH,
    ]
    assert payload["operation"] == "recover-current-zero-weed"
    assert payload["caller_selected_pair_batch_execution_or_candidate_allowed"] is False
    assert payload["authority"]["exact_zero_source_weed_rejection_append_allowed"] is True
    assert payload["authority"]["candidate_acceptance_allowed"] is False
    assert payload["authority"]["render_allowed"] is False
    assert payload["authority"]["state_transition_or_pair_publication_allowed"] is False
    assert payload["pass108_real_recovery_or_gt_or_render_allowed"] is False


def test_all_sealed_parent_release_and_terminal_identities_are_exact() -> None:
    config, parent = recovery._verify_immutable_parents(RUNTIME_CONFIG)
    assert parent["parents"]["state_chain_release_identity_sha256"] == (
        recovery.STATE_CHAIN_RELEASE_IDENTITY_SHA256
    )
    assert parent["parents"]["recovery_v1_release_identity_sha256"] == (
        recovery.RECOVERY_V1_RELEASE_IDENTITY_SHA256
    )
    assert parent["parents"]["recovery_v2_release_identity_sha256"] == (
        recovery.RECOVERY_V2_RELEASE_IDENTITY_SHA256
    )
    assert parent["parents"]["recovery_v2_terminal_receipt_sha256"] == (
        recovery.RECOVERY_V2_TERMINAL_SHA256
    )
    assert parent["parents"]["locked_test_recovery_lock_sha256"] == (
        recovery.RECOVERY_LOCK_SHA256
    )
    assert config["evidence_policy"]["field_or_deployment_claim_allowed"] is False


def test_live_validation_derives_exact_initial_candidate8_without_gt_access() -> None:
    boundary = _live_boundary()
    recovery._assert_pass108_initial_boundary(boundary)
    assert boundary["completed_pair_count"] == 45
    assert boundary["pending_pair_count"] == 51
    assert boundary["first_pending_pair_id"] == recovery.GENESIS_PAIR_ID
    assert boundary["state_chain_execution_id"] == (
        recovery.GENESIS_STATE_CHAIN_EXECUTION_ID
    )
    assert boundary["underlying_batch_id"] == recovery.GENESIS_BATCH_ID
    assert boundary["next_candidate_index"] == 8
    assert boundary["next_candidate_identity_sha256"] == (
        recovery.GENESIS_CANDIDATE_IDENTITY_SHA256
    )
    assert boundary["next_source_template"]["sha256"] == (
        recovery.GENESIS_SOURCE_TEMPLATE_SHA256
    )
    assert boundary["v3_execution_count"] == 0
    assert boundary["model_loaded"] is False
    assert boundary["inference_calls"] == 0
    assert boundary["outcome_inputs"] == []


def test_initial_request_binds_every_derived_target_and_no_caller_choice() -> None:
    _, _, candidate = _live_context()
    boundary = _live_boundary()
    request = _request_from_boundary(boundary, candidate)
    assert request["operation"] == "recover-current-zero-weed"
    assert request["caller_selected_target"] is False
    assert request["pair_id"] == recovery.GENESIS_PAIR_ID
    assert request["state_chain_execution_id"] == recovery.GENESIS_STATE_CHAIN_EXECUTION_ID
    assert request["underlying_batch_id"] == recovery.GENESIS_BATCH_ID
    assert request["candidate_index"] == recovery.GENESIS_CANDIDATE_INDEX
    assert request["candidate_identity_sha256"] == (
        recovery.GENESIS_CANDIDATE_IDENTITY_SHA256
    )
    assert request["candidate_seeds"] == recovery.GENESIS_CANDIDATE_SEEDS
    assert request["max_new_pairs"] == 1
    assert request["acceptance_authority"] == "none"
    assert request["render_or_state_transition_authority"] is False


def test_two_sequential_candidates_form_one_hash_linked_pair_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, roster, candidate8 = _live_context()
    paths = _temporary_paths(tmp_path)
    monkeypatch.setattr(recovery, "recovery_bridge_v3_paths", lambda _config: paths)
    boundary = _live_boundary()
    first = _request_from_boundary(boundary, candidate8)
    _, first_sha = _journal_record(config, paths, first, terminal=True)
    candidate9 = roster["candidates"][9]
    second_boundary = copy.deepcopy(boundary)
    second_boundary["candidate_rejection_ledger_row_count"] += 1
    second_boundary["candidate_rejection_ledger_sha256"] = "b" * 64
    second = _request_from_boundary(
        second_boundary, candidate9, sequence=2, previous=first_sha
    )
    _journal_record(config, paths, second, terminal=False)
    records = recovery._scan_v3_journal(config)
    assert [record["sequence"] for record in records] == [1, 2]
    assert records[0]["terminal_present"] is True
    assert records[1]["terminal_present"] is False
    assert records[1]["request"]["previous_terminal_receipt_sha256"] == first_sha


def test_transition_to_second_mocked_canonical_pair_keeps_structural_derivation() -> None:
    _, _, candidate = _live_context()
    boundary = _live_boundary()
    first = _request_from_boundary(boundary, candidate)
    second_boundary = copy.deepcopy(boundary)
    second_boundary.update(
        {
            "pair_id": "locked_test_c001_r06",
            "pair_slot_identity_sha256": "1" * 64,
            "state_chain_execution_id": "state_chain_batch_locked_test_c001_r06_mock",
            "state_chain_intent_sha256": "2" * 64,
            "underlying_batch_id": "locked_test_render_batch_locked_test_c001_r06_mock",
            "underlying_batch_intent_sha256": "3" * 64,
            "render_state_sha256": "4" * 64,
            "chain_head_identity_sha256": "5" * 64,
            "candidate_rejection_ledger_sha256": "6" * 64,
            "candidate_rejection_ledger_row_count": 150,
        }
    )
    second_candidate = copy.deepcopy(candidate)
    second_candidate["candidate_index"] = 0
    second_candidate["candidate_identity_sha256"] = "7" * 64
    second = recovery._request(
        "a" * 64,
        second_boundary,
        second_candidate,
        journal_sequence=2,
        previous_terminal_receipt_sha256="8" * 64,
    )
    assert first["pair_id"] != second["pair_id"]
    assert second["caller_selected_target"] is False
    assert second["journal_sequence"] == 2
    assert second["max_new_pairs"] == 1
    assert second["candidate_index"] == 0


def test_journal_rejects_sequence_skip_and_predecessor_forgery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, roster, candidate8 = _live_context()
    paths = _temporary_paths(tmp_path)
    monkeypatch.setattr(recovery, "recovery_bridge_v3_paths", lambda _config: paths)
    boundary = _live_boundary()
    first = _request_from_boundary(boundary, candidate8)
    _journal_record(config, paths, first, terminal=True)
    candidate9 = roster["candidates"][9]
    second = _request_from_boundary(
        boundary, candidate9, sequence=3, previous="0" * 64
    )
    _journal_record(config, paths, second, terminal=False)
    with pytest.raises(execution.ContractError, match="sequence skipped or reordered"):
        recovery._scan_v3_journal(config)


def test_partial_and_parallel_v3_intents_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, roster, candidate8 = _live_context()
    paths = _temporary_paths(tmp_path)
    monkeypatch.setattr(recovery, "recovery_bridge_v3_paths", lambda _config: paths)
    paths["executions"].mkdir(parents=True)
    (paths["executions"] / ".partial-bad").mkdir()
    with pytest.raises(execution.ContractError, match="Partial V3"):
        recovery._scan_v3_journal(config)
    (paths["executions"] / ".partial-bad").rmdir()
    boundary = _live_boundary()
    first = _request_from_boundary(boundary, candidate8)
    _journal_record(config, paths, first, terminal=False)
    candidate9 = roster["candidates"][9]
    second = _request_from_boundary(boundary, candidate9, sequence=2)
    _journal_record(config, paths, second, terminal=False)
    with pytest.raises(execution.ContractError, match="Parallel or reordered"):
        recovery._scan_v3_journal(config)


def test_publish_or_resume_is_atomic_and_byte_idempotent(tmp_path: Path) -> None:
    config, _, candidate = _live_context()
    request = _request_from_boundary(_live_boundary(), candidate)
    execution_id, identity = recovery._execution_identity(request)
    intent = recovery._intent_payload(config, request, execution_id, identity)
    parent = tmp_path / "executions"
    root, resumed = recovery._publish_or_resume_intent(parent, execution_id, intent)
    first = (root / "recovery_bridge_intent.json").read_bytes()
    same_root, resumed_again = recovery._publish_or_resume_intent(
        parent, execution_id, intent
    )
    assert resumed is False
    assert resumed_again is True
    assert root == same_root
    assert (root / "recovery_bridge_intent.json").read_bytes() == first
    changed = copy.deepcopy(intent)
    changed["request"]["candidate_index"] = 9
    with pytest.raises(execution.ContractError, match="intent changed"):
        recovery._publish_or_resume_intent(parent, execution_id, changed)


def test_matching_batch_rejects_two_open_matches_and_terminal_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    parent = tmp_path / "batches"
    monkeypatch.setattr(recovery, "_batch_parent", lambda _config: parent)

    def write_batch(name: str, *, terminal: bool = False) -> None:
        request = {
            "target_pair_ids": [recovery.GENESIS_PAIR_ID],
            "max_new_pairs": 1,
            "model_access_allowed": False,
            "prediction_access_allowed": False,
            "locked_test_outcome_access_allowed": False,
            "render_and_machine_audit_only": True,
        }
        intent = {
            "batch_id": name,
            "status": "LOCKED_TEST_RENDER_BATCH_INTENT_PREOUTCOME_SYNTHETIC_ONLY",
            "request": request,
            "request_identity_sha256": execution.stable_sha256(request),
        }
        _write_json(parent / name / "batch_intent.json", intent)
        if terminal:
            _write_json(parent / name / "batch_receipt.json", {"status": "done"})

    write_batch("batch_one")
    assert recovery._matching_open_batch(config, recovery.GENESIS_PAIR_ID)["batch_id"] == (
        "batch_one"
    )
    write_batch("batch_two")
    with pytest.raises(execution.ContractError, match="exactly one matching"):
        recovery._matching_open_batch(config, recovery.GENESIS_PAIR_ID)
    _write_json(parent / "batch_one/batch_receipt.json", {"status": "done"})
    _write_json(parent / "batch_two/batch_receipt.json", {"status": "done"})
    with pytest.raises(execution.ContractError, match="exactly one matching"):
        recovery._matching_open_batch(config, recovery.GENESIS_PAIR_ID)


@pytest.mark.parametrize("active_count", [0, 2])
def test_missing_terminal_or_parallel_state_chain_execution_fails_closed(
    monkeypatch: pytest.MonkeyPatch, active_count: int
) -> None:
    monkeypatch.setattr(
        state_chain,
        "_open_intents",
        lambda _paths: [
            {"intent": {"execution_id": f"mock_{index}"}, "root": Path("/tmp")}
            for index in range(active_count)
        ],
    )
    with pytest.raises(execution.ContractError, match="exactly one active"):
        recovery._validate_active_boundary(RUNTIME_CONFIG)


def test_parent_source_hash_drift_fails_before_candidate_access(tmp_path: Path) -> None:
    changed = tmp_path / "changed.py"
    changed.write_text("changed\n", encoding="utf-8")
    with pytest.raises(execution.ContractError, match="bytes changed"):
        recovery._require_file_sha256(changed, "0" * 64, "sealed parent")


def test_partial_legacy_recovery_publication_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, roster, _ = _live_context()
    destination = tmp_path / "candidate_08"
    _write_json(destination / "recovery_terminal_receipt.json", {"status": "partial"})
    monkeypatch.setattr(recovery, "_recovery_destination", lambda *_args: destination)
    with pytest.raises(execution.ContractError, match="evidence is incomplete"):
        recovery._validate_recovery_artifacts(
            config,
            roster,
            recovery.GENESIS_CANDIDATE_INDEX,
            recovery.GENESIS_BATCH_ID,
            recovery.GENESIS_BATCH_INTENT_SHA256,
            require_commit=False,
        )


def test_genesis_ledger_prefix_mutation_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, parent = recovery._verify_immutable_parents(RUNTIME_CONFIG)
    state_path, docs_state_path, live_ledger = state_chain._state_paths(config)
    rows = execution.read_jsonl(live_ledger)
    rows[0] = {**rows[0], "reason": "tampered"}
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        state_chain,
        "_state_paths",
        lambda _config: (state_path, docs_state_path, ledger),
    )
    with pytest.raises(execution.ContractError, match="genesis ledger prefix"):
        recovery._head_ancestry(parent, config)


def test_state_chain_fork_or_rollback_breaks_genesis_ancestry() -> None:
    config, parent = recovery._verify_immutable_parents(RUNTIME_CONFIG)
    tampered = copy.deepcopy(parent)
    target = next(
        commit
        for commit in tampered["state_chain_static"]["commits"]
        if commit["head"]["head_identity_sha256"]
        == recovery.GENESIS_HEAD_IDENTITY_SHA256
    )
    target["head"]["head_identity_sha256"] = "f" * 64
    with pytest.raises(execution.ContractError):
        recovery._head_ancestry(tampered, config)


@pytest.mark.parametrize(
    "field,replacement",
    [
        ("candidate_index", 9),
        ("candidate_identity_sha256", "f" * 64),
        ("candidate_seeds", {"scene_seed": 0}),
        ("pair_id", "locked_test_c999_r99"),
        ("underlying_batch_id", "forged_batch"),
        ("state_chain_execution_id", "forged_state_chain"),
    ],
)
def test_journal_rejects_candidate_skip_identity_seed_or_target_forgery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    replacement: object,
) -> None:
    config, roster, candidate = _live_context()
    boundary = _live_boundary()
    request = _request_from_boundary(boundary, candidate)
    request[field] = replacement
    state_intent = tmp_path / "state_exec/state_chain_intent.json"
    batch_intent = tmp_path / "batch/batch_intent.json"
    _write_json(
        state_intent,
        {
            "execution_id": boundary["state_chain_execution_id"],
            "request": {
                "target_pair_id": boundary["pair_id"],
                "max_new_pairs": 1,
            },
        },
    )
    _write_json(
        batch_intent,
        {
            "batch_id": boundary["underlying_batch_id"],
            "request": {"target_pair_ids": [boundary["pair_id"]], "max_new_pairs": 1},
        },
    )
    request["state_chain_intent_sha256"] = execution.sha256_file(state_intent)
    request["underlying_batch_intent_sha256"] = execution.sha256_file(batch_intent)
    _, request_identity = recovery._execution_identity(request)
    record = {
        "sequence": 1,
        "execution_id": "mock",
        "root": tmp_path,
        "intent": {},
        "intent_path": tmp_path / "intent",
        "request": request,
        "request_identity_sha256": request_identity,
        "terminal": None,
        "terminal_path": tmp_path / "terminal",
        "terminal_present": False,
    }
    ledger_path = state_chain._state_paths(config)[2]
    monkeypatch.setattr(recovery, "_scan_v3_journal", lambda _config: [record])
    monkeypatch.setattr(
        recovery,
        "_head_ancestry",
        lambda _parent, _config: (
            {},
            {
                boundary["chain_head_identity_sha256"]: {
                    "head": {"result_state_sha256": boundary["render_state_sha256"]}
                }
            },
        ),
    )
    monkeypatch.setattr(
        state_chain,
        "_state_paths",
        lambda _config: (tmp_path / "state", tmp_path / "docs_state", ledger_path),
    )
    monkeypatch.setattr(
        state_chain,
        "state_chain_paths",
        lambda _config: {"executions": state_intent.parent.parent},
    )
    monkeypatch.setattr(recovery, "_batch_parent", lambda _config: batch_intent.parent.parent)
    monkeypatch.setattr(execution, "full_roster_rows", lambda _config: [roster])
    monkeypatch.setattr(recovery, "_candidate_by_index", lambda *_args: candidate)
    with pytest.raises(execution.ContractError):
        recovery._validate_v3_journal(
            config,
            {},
            release_identity="a" * 64,
            allow_open_execution_id="mock",
        )


def test_runtime_phase_rejects_state_or_head_advance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config, _, candidate = _live_context()
    boundary = _live_boundary()
    request = _request_from_boundary(boundary, candidate)
    changed = copy.deepcopy(boundary)
    changed["render_state_sha256"] = "f" * 64
    monkeypatch.setattr(
        recovery,
        "_validate_active_boundary",
        lambda *_args, **_kwargs: (config, {}, changed),
    )
    with pytest.raises(execution.ContractError, match="active target changed"):
        recovery._validate_runtime_phase(
            RUNTIME_CONFIG,
            wrapper_execution_id="mock",
            request=request,
            release_identity="a" * 64,
        )


def test_state_or_head_advance_during_recovery_invalidates_terminal(
    tmp_path: Path,
) -> None:
    config, _, candidate = _live_context()
    boundary = _live_boundary()
    request = _request_from_boundary(boundary, candidate)
    execution_id, request_identity = recovery._execution_identity(request)
    intent_path = tmp_path / "recovery_bridge_intent.json"
    _write_json(
        intent_path,
        recovery._intent_payload(config, request, execution_id, request_identity),
    )
    evidence = {
        "recovery_terminal_receipt_sha256": "1" * 64,
        "decision_receipt_sha256": "2" * 64,
        "ledger_commit_receipt_sha256": "3" * 64,
    }
    after = {
        **boundary,
        "render_state_sha256": "f" * 64,
        "candidate_rejection_ledger_sha256": "e" * 64,
        "candidate_rejection_ledger_row_count": (
            request["predecessor_ledger_row_count"] + 1
        ),
        "recovery_evidence": evidence,
    }
    underlying = {
        "status": "REJECT_ZERO_SOURCE_WEED_TRACKS_PREOUTCOME_SYNTHETIC_ONLY",
        "pair_id": request["pair_id"],
        "candidate_index": request["candidate_index"],
        "batch_id": request["underlying_batch_id"],
    }
    terminal = recovery._terminal_payload(
        config,
        request,
        request_identity,
        execution_id,
        intent_path,
        underlying,
        after,
        False,
    )
    with pytest.raises(execution.ContractError, match="terminal receipt changed"):
        recovery._validate_terminal_receipt(
            config,
            terminal,
            request,
            request_identity,
            execution_id,
            intent_path,
            after,
        )


def test_non_zero_weed_result_has_no_rejection_authority() -> None:
    _, _, candidate = _live_context()
    request = _request_from_boundary(_live_boundary(), candidate)
    result = {
        "status": "PASS_NON_ZERO_WEED",
        "pair_id": request["pair_id"],
        "candidate_index": request["candidate_index"],
        "batch_id": request["underlying_batch_id"],
        "model_loaded": False,
        "inference_calls": 0,
        "synthetic_only": True,
    }
    with pytest.raises(execution.ContractError, match="unauthorized evidence"):
        recovery._validate_underlying_result(result, request)


def test_callable_patch_restores_every_callable_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = {
        "state_chain_execution_id": recovery.GENESIS_STATE_CHAIN_EXECUTION_ID,
        "pair_id": recovery.GENESIS_PAIR_ID,
        "candidate_index": recovery.GENESIS_CANDIDATE_INDEX,
        "underlying_batch_id": recovery.GENESIS_BATCH_ID,
    }

    def fake_recovery(*_args, **_kwargs):
        assert isinstance(execution.validate_full_plan, type(recovery.functools.partial(int)))
        return {"status": "ok"}

    original_validator = execution.validate_full_plan
    monkeypatch.setattr(execution, "run_locked_test_gt_source_cardinality_recovery", fake_recovery)
    monkeypatch.setattr(recovery, "_ORIGINAL_RECOVERY_CALLABLE", fake_recovery)
    assert recovery._call_unchanged_recovery(RUNTIME_CONFIG, request) == {"status": "ok"}
    assert execution.validate_full_plan is original_validator
    assert execution.run_locked_test_gt_source_cardinality_recovery is fake_recovery


def test_callable_patch_restores_every_callable_after_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = {
        "state_chain_execution_id": recovery.GENESIS_STATE_CHAIN_EXECUTION_ID,
        "pair_id": recovery.GENESIS_PAIR_ID,
        "candidate_index": recovery.GENESIS_CANDIDATE_INDEX,
        "underlying_batch_id": recovery.GENESIS_BATCH_ID,
    }

    def failing_recovery(*_args, **_kwargs):
        raise RuntimeError("mock failure")

    original_validator = execution.validate_full_plan
    monkeypatch.setattr(
        execution, "run_locked_test_gt_source_cardinality_recovery", failing_recovery
    )
    monkeypatch.setattr(recovery, "_ORIGINAL_RECOVERY_CALLABLE", failing_recovery)
    with pytest.raises(RuntimeError, match="mock failure"):
        recovery._call_unchanged_recovery(RUNTIME_CONFIG, request)
    assert execution.validate_full_plan is original_validator
    assert execution.run_locked_test_gt_source_cardinality_recovery is failing_recovery


def test_callable_tamper_is_detected_and_restored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = {
        "state_chain_execution_id": recovery.GENESIS_STATE_CHAIN_EXECUTION_ID,
        "pair_id": recovery.GENESIS_PAIR_ID,
        "candidate_index": recovery.GENESIS_CANDIDATE_INDEX,
        "underlying_batch_id": recovery.GENESIS_BATCH_ID,
    }
    original_load_json = execution.load_json

    def tampering_recovery(*_args, **_kwargs):
        execution.load_json = lambda _path: {}
        return {"status": "ok"}

    monkeypatch.setattr(
        execution, "run_locked_test_gt_source_cardinality_recovery", tampering_recovery
    )
    monkeypatch.setattr(recovery, "_ORIGINAL_RECOVERY_CALLABLE", tampering_recovery)
    with pytest.raises(execution.ContractError, match="Unauthorized callable change"):
        recovery._call_unchanged_recovery(RUNTIME_CONFIG, request)
    assert execution.load_json is original_load_json


def test_access_guard_and_claim_boundary_are_zero_and_non_deployment() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    assert recovery._access_guard() == {
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
    claim = recovery._claim_boundary(config)
    assert claim["scope"] == "synthetic_diagnostic_only"
    assert claim["field_or_deployment_claim_allowed"] is False
    assert claim["product_go_allowed"] is False
    assert claim["chemical_fire_go_allowed"] is False
    assert claim["synthetic_score_weight_in_real_go_decision"] == 0.0


def test_release_contract_binds_source_test_parents_genesis_and_no_real_execution() -> None:
    config, parent = recovery._verify_immutable_parents(RUNTIME_CONFIG)
    payload = recovery._release_payload(
        config,
        parent["parents"],
        authorization_sha256="a" * 64,
        bridge_sha256="b" * 64,
        lock_sha256="c" * 64,
    )
    assert payload["bridge_script_sha256"] == execution.sha256_file(
        Path(recovery.__file__)
    )
    assert payload["bridge_test_sha256"] == execution.sha256_file(
        recovery.PROJECT_ROOT / recovery.AUTHORIZED_TEST_PATH
    )
    assert payload["genesis"] == recovery._pinned_genesis()
    assert payload["pass108_validation_only"] is True
    assert payload["real_recovery_candidate_gt_or_render_access_during_pass108"] is False
    identity = payload.pop("release_identity_sha256")
    assert identity == execution.stable_sha256(payload)
