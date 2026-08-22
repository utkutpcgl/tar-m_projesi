from __future__ import annotations

import copy
import hashlib
import shutil
from pathlib import Path

import pytest

from scripts import run_spot_spray_simulation_video_ab_execution_v1 as execution
from scripts import run_spot_spray_simulation_video_ab_extension_aware_batch_v1 as adapter
from scripts import run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1 as chain


def _pair_ids() -> list[str]:
    return [f"pair_{index:03d}" for index in range(96)]


def _state(completed: int) -> dict:
    pair_ids = _pair_ids()
    return {
        "planned_pair_count": 96,
        "completed_pair_count": completed,
        "pending_pair_count": 96 - completed,
        "completed_pair_ids": pair_ids[:completed],
        "pending_pair_ids": pair_ids[completed:],
        "interrupted_staging_directories": [],
        "model_outputs_present": False,
    }


def _candidate_identity(pair_id: str, index: int) -> str:
    return hashlib.sha256(f"{pair_id}:{index}".encode()).hexdigest()


def _roster() -> list[dict]:
    rows = []
    for position, pair_id in enumerate(_pair_ids()):
        rows.append(
            {
                "pair_id": pair_id,
                "protocol_split": "calibration" if position < 32 else "locked_test",
                "pair_slot_identity_sha256": hashlib.sha256(pair_id.encode()).hexdigest(),
                "candidates": [
                    {
                        "candidate_index": index,
                        "candidate_identity_sha256": _candidate_identity(pair_id, index),
                        "seeds": {},
                        "source_template": {},
                    }
                    for index in range(32)
                ],
            }
        )
    return rows


def _ledger_row(pair_id: str, index: int) -> dict:
    return {
        "schema_version": 1,
        "pair_id": pair_id,
        "candidate_index": index,
        "candidate_identity_sha256": _candidate_identity(pair_id, index),
        "reason_type": "GtScoutCandidateRejected",
        "reason": "frozen GT-only gate",
        "model_or_outcome_inputs_used": False,
    }


def _minimal_record(sequence: int = 42) -> dict:
    pair_id = _pair_ids()[sequence - 1]
    return chain._transition_record_payload(
        sequence=sequence,
        chain_root_identity="1" * 64,
        predecessor_head_identity="2" * 64,
        predecessor_state_sha256="3" * 64,
        result_state_sha256="4" * 64,
        predecessor_ledger_sha256="5" * 64,
        result_ledger_sha256="6" * 64,
        pair_evidence={
            "pair_id": pair_id,
            "selected_candidate_index": 0,
            "candidate_identity_sha256": "7" * 64,
            "canonical_gt_sha256": "8" * 64,
            "identical_arm_gt": True,
            "all_frozen_pair_gates_passed": True,
        },
        execution_evidence={"fixture": True},
    )


def test_cli_and_manager_scope_are_explicit_and_separate() -> None:
    parsed = chain.parse_args(["validate"])
    assert parsed.command == "validate"
    assert chain.AUTHORIZED_SOURCE_PATH.endswith("extension_aware_state_chain_v1.py")
    assert chain.AUTHORIZED_TEST_PATH.endswith("extension_aware_state_chain_v1.py")
    assert [chain.AUTHORIZED_SOURCE_PATH, chain.AUTHORIZED_TEST_PATH] == [
        "scripts/run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1.py",
        "tests/test_run_spot_spray_simulation_video_ab_extension_aware_state_chain_v1.py",
    ]


def test_canonical_state_prefix_and_suffix_pass() -> None:
    summary = chain._validate_state_shape(_state(42), _pair_ids())
    assert summary["completed_pair_count"] == 42
    assert summary["first_pending_pair_id"] == "pair_042"


@pytest.mark.parametrize(
    "mutation",
    [
        "root_count",
        "current_count",
        "completed_reorder",
        "pending_skip",
        "rollback",
        "extra_field",
        "model_output",
        "staging",
    ],
)
def test_root_current_prefix_suffix_rollback_and_skip_fail_closed(
    mutation: str,
) -> None:
    state = _state(42)
    if mutation == "root_count":
        state["planned_pair_count"] = 95
    elif mutation == "current_count":
        state["completed_pair_count"] = 43
    elif mutation == "completed_reorder":
        state["completed_pair_ids"][-2:] = reversed(state["completed_pair_ids"][-2:])
    elif mutation == "pending_skip":
        state["pending_pair_ids"] = state["pending_pair_ids"][1:]
    elif mutation == "rollback":
        state["completed_pair_ids"] = state["completed_pair_ids"][:-1]
    elif mutation == "extra_field":
        state["unsealed"] = True
    elif mutation == "model_output":
        state["model_outputs_present"] = True
    elif mutation == "staging":
        state["interrupted_staging_directories"] = [".partial-forged"]
    with pytest.raises(execution.ContractError):
        chain._validate_state_shape(state, _pair_ids())


def test_exact_single_state_transition_passes() -> None:
    result = chain._validate_state_transition(
        _state(41), _state(42), _pair_ids(), "pair_041"
    )
    assert result == {
        "from_completed_pair_count": 41,
        "to_completed_pair_count": 42,
        "appended_pair_id": "pair_041",
        "first_pending_pair_id": "pair_042",
    }


@pytest.mark.parametrize("kind", ["skip", "rollback", "wrong_pair", "reorder"])
def test_predecessor_result_transition_tampering_fails_closed(kind: str) -> None:
    predecessor = _state(41)
    result = _state(42)
    pair_id = "pair_041"
    if kind == "skip":
        result = _state(43)
    elif kind == "rollback":
        predecessor = _state(42)
        result = _state(41)
    elif kind == "wrong_pair":
        pair_id = "pair_042"
    elif kind == "reorder":
        result["completed_pair_ids"][-2:] = reversed(result["completed_pair_ids"][-2:])
    with pytest.raises(execution.ContractError):
        chain._validate_state_transition(predecessor, result, _pair_ids(), pair_id)


def test_canonical_ledger_and_append_only_extension_pass() -> None:
    roster = _roster()
    before = [_ledger_row("pair_000", 0)]
    after = [*before, _ledger_row("pair_001", 0), _ledger_row("pair_001", 1)]
    summary = chain._validate_ledger_extension(before, after, roster, "pair_001")
    assert summary["appended_row_count"] == 2
    assert summary["append_only_prefix_preserved"] is True


@pytest.mark.parametrize(
    "kind",
    [
        "mutation",
        "truncation",
        "candidate_skip",
        "duplicate",
        "identity",
        "wrong_pair_append",
        "model_access",
        "pair_reorder",
    ],
)
def test_ledger_mutation_truncation_and_noncanonical_append_fail_closed(
    kind: str,
) -> None:
    roster = _roster()
    before = [_ledger_row("pair_000", 0)]
    after = [*before, _ledger_row("pair_001", 0)]
    if kind == "mutation":
        after[0] = {**after[0], "reason": "rewritten"}
    elif kind == "truncation":
        after = []
    elif kind == "candidate_skip":
        after[-1] = _ledger_row("pair_001", 1)
    elif kind == "duplicate":
        after.append(copy.deepcopy(after[-1]))
    elif kind == "identity":
        after[-1]["candidate_identity_sha256"] = "f" * 64
    elif kind == "wrong_pair_append":
        after[-1] = _ledger_row("pair_002", 0)
    elif kind == "model_access":
        after[-1]["model_or_outcome_inputs_used"] = True
    elif kind == "pair_reorder":
        before = [_ledger_row("pair_002", 0)]
        after = [*before, _ledger_row("pair_001", 0)]
    with pytest.raises(execution.ContractError):
        chain._validate_ledger_extension(before, after, roster, "pair_001")


def test_atomic_transition_commit_is_idempotent_and_mirrored(tmp_path: Path) -> None:
    commits = tmp_path / "commits"
    docs = tmp_path / "docs"
    record = _minimal_record()
    first = chain._publish_transition_commit(
        commits, docs, record, _state(42), [_ledger_row("pair_000", 0)]
    )
    second = chain._publish_transition_commit(
        commits, docs, record, _state(42), [_ledger_row("pair_000", 0)]
    )
    assert first == second
    assert len(list(commits.iterdir())) == 1
    assert len(list(docs.iterdir())) == 1
    validated = chain._validate_commit_directory(commits / first["commit_name"])
    assert validated["manifest"]["commit_identity_sha256"] == first[
        "commit_identity_sha256"
    ]


def test_atomic_transition_failure_removes_partial_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = execution.write_json

    def fail_on_head(path: Path, value: object) -> None:
        if path.name == "head.json":
            raise OSError("simulated atomic failure")
        original(path, value)

    monkeypatch.setattr(execution, "write_json", fail_on_head)
    with pytest.raises(OSError, match="simulated atomic failure"):
        chain._publish_transition_commit(
            tmp_path / "commits",
            tmp_path / "docs",
            _minimal_record(),
            _state(42),
            [],
        )
    assert not list((tmp_path / "commits").glob(".partial-*"))
    assert not [path for path in (tmp_path / "commits").glob("*") if path.is_dir()]


def test_commit_result_or_head_tamper_fails_closed(tmp_path: Path) -> None:
    result = chain._publish_transition_commit(
        tmp_path / "commits",
        tmp_path / "docs",
        _minimal_record(),
        _state(42),
        [],
    )
    root = tmp_path / "commits" / result["commit_name"]
    changed = _state(42)
    changed["pending_pair_ids"] = changed["pending_pair_ids"][1:]
    execution.write_json(root / "result_state.json", changed)
    with pytest.raises(execution.ContractError, match="manifest"):
        chain._validate_commit_directory(root)


def test_intent_publication_is_atomic_exact_and_idempotent(tmp_path: Path) -> None:
    intent = {
        "execution_id": "state_chain_batch_pair_042_0123456789abcdef",
        "request": {"target_pair_id": "pair_042"},
    }
    root, resumed = chain._publish_or_resume_intent(
        tmp_path, intent["execution_id"], intent
    )
    assert resumed is False
    repeated, resumed = chain._publish_or_resume_intent(
        tmp_path, intent["execution_id"], intent
    )
    assert repeated == root
    assert resumed is True
    with pytest.raises(execution.ContractError, match="changed"):
        chain._publish_or_resume_intent(
            tmp_path, intent["execution_id"], {**intent, "request": {"changed": True}}
        )


def test_duplicate_parallel_or_partial_intent_fails_closed(tmp_path: Path) -> None:
    first = {
        "execution_id": "state_chain_batch_pair_042_0123456789abcdef",
        "request": {"target_pair_id": "pair_042"},
    }
    chain._publish_or_resume_intent(tmp_path, first["execution_id"], first)
    second = {
        "execution_id": "state_chain_batch_pair_043_fedcba9876543210",
        "request": {"target_pair_id": "pair_043"},
    }
    with pytest.raises(execution.ContractError, match="Parallel"):
        chain._publish_or_resume_intent(tmp_path, second["execution_id"], second)
    partial = tmp_path / ".partial-forged"
    partial.mkdir()
    with pytest.raises(execution.ContractError, match="Partial"):
        chain._publish_or_resume_intent(tmp_path, first["execution_id"], first)


def test_request_requires_exact_earliest_pending_and_one_pair() -> None:
    validation = {
        "first_pending_pair_id": "locked_test_c001_r02",
        "chain_head_identity_sha256": "1" * 64,
        "render_state_sha256": "2" * 64,
        "candidate_rejection_ledger_sha256": "3" * 64,
    }
    request = chain._normalize_request(
        validation, "4" * 64, ["locked_test_c001_r02"], 1
    )
    assert request["target_pair_id"] == "locked_test_c001_r02"
    assert request["max_new_pairs"] == 1
    for pair_ids, limit in ((["locked_test_c001_r03"], 1), ([], 1), (["locked_test_c001_r02"], 2)):
        with pytest.raises(execution.ContractError):
            chain._normalize_request(validation, "4" * 64, pair_ids, limit)


def test_only_validator_callable_changes_and_restores_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed = {}

    def fake_batch(config_path: Path, pair_ids: list[str], *, max_new_pairs: int) -> dict:
        observed["validator"] = execution.validate_full_plan
        observed["pair_ids"] = pair_ids
        observed["limit"] = max_new_pairs
        return {"status": "fixture"}

    monkeypatch.setattr(execution, "run_locked_test_render_batch", fake_batch)
    result = chain._call_unchanged_batch(
        chain.DEFAULT_CONFIG,
        "locked_test_c001_r02",
        execution_id="state_chain_batch_locked_test_c001_r02_fixture",
    )
    assert result == {"status": "fixture"}
    assert observed["validator"] is not chain._ORIGINAL_VALIDATE_FULL_PLAN
    assert observed["pair_ids"] == ["locked_test_c001_r02"]
    assert observed["limit"] == 1
    assert execution.validate_full_plan is chain._ORIGINAL_VALIDATE_FULL_PLAN


def test_validator_callable_restores_after_underlying_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_batch(*args: object, **kwargs: object) -> dict:
        raise RuntimeError("fixture batch failure")

    monkeypatch.setattr(execution, "run_locked_test_render_batch", failing_batch)
    with pytest.raises(RuntimeError, match="fixture batch failure"):
        chain._call_unchanged_batch(
            chain.DEFAULT_CONFIG,
            "locked_test_c001_r02",
            execution_id="state_chain_batch_locked_test_c001_r02_fixture",
        )
    assert execution.validate_full_plan is chain._ORIGINAL_VALIDATE_FULL_PLAN


def test_second_execution_callable_change_fails_closed_and_validator_restores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read = execution.read_jsonl

    def corrupting_batch(*args: object, **kwargs: object) -> dict:
        execution.read_jsonl = lambda path: []
        return {"status": "fixture"}

    monkeypatch.setattr(execution, "run_locked_test_render_batch", corrupting_batch)
    with pytest.raises(execution.ContractError, match="Unauthorized"):
        chain._call_unchanged_batch(
            chain.DEFAULT_CONFIG,
            "locked_test_c001_r02",
            execution_id="state_chain_batch_locked_test_c001_r02_fixture",
        )
    execution.read_jsonl = original_read
    assert execution.validate_full_plan is chain._ORIGINAL_VALIDATE_FULL_PLAN


def test_pair_receipt_forgery_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = execution.load_config(chain.DEFAULT_CONFIG)
    _, roster = chain._verify_immutable_parents(chain.DEFAULT_CONFIG)
    index = 41
    historical = roster["historical"][index]
    combined = roster["combined"][index]
    live_root = chain._pair_root(config, combined)
    fixture_full = tmp_path / "full"
    fixture_pair = fixture_full / "pairs/locked_test" / combined["pair_id"]
    (fixture_pair / "ideal").mkdir(parents=True)
    (fixture_pair / "degraded").mkdir(parents=True)
    for relative in (
        "full_pair_receipt.json",
        "pair_receipt.json",
        "ideal/rgb.mp4",
        "degraded/rgb.mp4",
        "side_by_side.mp4",
    ):
        destination = fixture_pair / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(live_root / relative, destination)
    real_paths = execution.full_paths

    def fixture_paths(value: dict) -> dict[str, Path]:
        paths = real_paths(value)
        return {**paths, "synthetic": fixture_full}

    monkeypatch.setattr(execution, "full_paths", fixture_paths)
    evidence = chain._validate_published_pair(config, historical, combined, [])
    assert evidence["identical_arm_gt"] is True
    forged = execution.load_json(fixture_pair / "pair_receipt.json")
    forged["arm_gt_identity"]["byte_identical"] = False
    execution.write_json(fixture_pair / "pair_receipt.json", forged)
    with pytest.raises(execution.ContractError, match="receipt hash"):
        chain._validate_published_pair(config, historical, combined, [])


def test_parent_sources_and_releases_are_still_exact() -> None:
    config, roster = chain._verify_immutable_parents(chain.DEFAULT_CONFIG)
    assert len(roster["historical"]) == 96
    assert len(roster["combined"]) == 96
    assert roster["parents"]["adapter"] == chain.ADAPTER_SCRIPT_SHA256
    assert roster["parents"]["validator"] == chain.VALIDATOR_SCRIPT_SHA256
    assert roster["parents"]["legacy_execution"] == chain.LEGACY_EXECUTION_SCRIPT_SHA256
    assert config["evidence_policy"]["field_or_deployment_claim_allowed"] is False


def test_legacy_pass66_adapter_remains_fail_closed_at_42() -> None:
    with pytest.raises(execution.ContractError, match="Current 41/96 state bytes changed"):
        adapter.validate_adapter_release(chain.DEFAULT_CONFIG)


def test_state_chain_implementation_identity_is_deterministic() -> None:
    first = chain.state_chain_implementation_sha256()
    second = chain.state_chain_implementation_sha256()
    assert first == second
    assert execution.SHA256_RE.fullmatch(first)


def test_live_release_validates_repeatedly_without_execution() -> None:
    config = execution.load_config(chain.DEFAULT_CONFIG)
    paths = chain.state_chain_paths(config)
    if not paths["release_file"].is_file():
        pytest.skip("Pass70 release is sealed after pre-seal unit regressions")
    before_executions = sorted(paths["executions"].rglob("*")) if paths["executions"].exists() else []
    first = chain.validate_state_chain_release(chain.DEFAULT_CONFIG)
    second = chain.validate_state_chain_release(chain.DEFAULT_CONFIG)
    after_executions = sorted(paths["executions"].rglob("*")) if paths["executions"].exists() else []
    assert first == second
    assert first["status"] == (
        "PASS_EXTENSION_AWARE_MONOTONIC_STATE_CHAIN_VALIDATION_SYNTHETIC_ONLY"
    )
    assert first["completed_pair_count"] == 42
    assert first["pending_pair_count"] == 54
    assert first["candidate_rejection_ledger_row_count"] == 111
    assert before_executions == after_executions == []
    assert first["model_loaded"] is False
    assert first["inference_calls"] == 0
    assert first["field_product_or_chemical_go"] is False


def test_live_release_and_genesis_are_exactly_mirrored() -> None:
    config = execution.load_config(chain.DEFAULT_CONFIG)
    paths = chain.state_chain_paths(config)
    if not paths["release_file"].is_file():
        pytest.skip("Pass70 release is sealed after pre-seal unit regressions")
    for relative in chain._required_release_files():
        assert execution.sha256_file(paths["release"] / relative) == execution.sha256_file(
            paths["docs_release"] / relative
        )
    commits = chain._list_commits(paths)
    assert len(commits) == 1
    assert commits[0]["record"]["sequence"] == 42
    assert commits[0]["record"]["pair"]["pair_id"] == "locked_test_c001_r01"
    assert commits[0]["record"]["result_state_sha256"] == chain.ROOT_RESULT_STATE_SHA256
    assert commits[0]["record"]["result_ledger_sha256"] == chain.ROOT_LEDGER_SHA256


def test_pass70_receipt_is_validation_only_and_zero_access() -> None:
    config = execution.load_config(chain.DEFAULT_CONFIG)
    paths = chain.state_chain_paths(config)
    if not paths["validation_receipt"].is_file():
        pytest.skip("Pass70 release is sealed after pre-seal unit regressions")
    receipt = execution.load_json(paths["validation_receipt"])
    assert receipt["status"] == "READY_FOR_MANAGER_VALIDATION"
    assert receipt["validated_root"]["result_completed_pair_count"] == 42
    assert receipt["validated_root"]["published_pair_receipt_count"] == 42
    assert receipt["access_guard"] == {
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
    }
    assert receipt["claim_boundary"]["field_or_deployment_claim_allowed"] is False
    assert receipt["claim_boundary"]["product_go_allowed"] is False
    assert receipt["claim_boundary"]["chemical_fire_go_allowed"] is False
