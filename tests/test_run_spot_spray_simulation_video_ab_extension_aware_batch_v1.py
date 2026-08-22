from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts import run_spot_spray_simulation_video_ab_execution_v1 as execution
from scripts import run_spot_spray_simulation_video_ab_extension_aware_batch_v1 as adapter


RUNTIME_CONFIG = adapter.DEFAULT_CONFIG


def _temporary_paths(tmp_path: Path) -> dict[str, Path]:
    synthetic_root = tmp_path / "synthetic/extension_aware_batch_adapter_v1"
    docs_root = tmp_path / "docs/extension_aware_batch_adapter_v1"
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


def test_cli_is_explicit_and_separate() -> None:
    assert adapter.parse_args(["seal"]).command == "seal"
    assert adapter.parse_args(["validate"]).command == "validate"
    run = adapter.parse_args(
        ["run", "--pair-id", "locked_test_c001_r01", "--max-new-pairs", "1"]
    )
    assert run.command == "run"
    assert run.pair_id == ["locked_test_c001_r01"]
    assert run.max_new_pairs == 1


def test_legacy_wrapper_still_fails_closed_before_intent() -> None:
    with pytest.raises(
        execution.ContractError,
        match=r"Invalid published full pair receipts: \['locked_test_c001_r00'\]",
    ):
        execution.run_locked_test_render_batch(
            RUNTIME_CONFIG, ["locked_test_c001_r01"], max_new_pairs=1
        )


def test_named_adapter_validator_returns_historical_plan_binding() -> None:
    result = adapter.extension_aware_validate_full_plan(RUNTIME_CONFIG)
    assert result["status"] == "PASS_FULL_PLAN_DRY_RUN_SYNTHETIC_ONLY"
    assert result["pair_roster_sha256"] == adapter.HISTORICAL_ROSTER_SHA256
    assert result["combined_candidate_count"] == 3072
    assert result["render_state"]["completed_pair_count"] == 41
    assert result["render_state"]["pending_pair_ids"][0] == (
        "locked_test_c001_r01"
    )
    assert result["model_loaded"] is False
    assert result["inference_calls"] == 0


def test_all_preexisting_source_and_function_identities_are_exact() -> None:
    result = adapter._verify_unchanged_sources()
    assert result["legacy_execution_script_sha256"] == (
        adapter.LEGACY_EXECUTION_SCRIPT_SHA256
    )
    assert result["legacy_execution_test_sha256"] == (
        adapter.LEGACY_EXECUTION_TEST_SHA256
    )
    assert result["validator_script_sha256"] == adapter.VALIDATOR_SCRIPT_SHA256
    assert result["validator_test_sha256"] == adapter.VALIDATOR_TEST_SHA256
    assert result["locked_test_batch_function_source_sha256"] == (
        adapter.LOCKED_TEST_BATCH_FUNCTION_SOURCE_SHA256
    )
    assert result["locked_test_batch_implementation_sha256"] == (
        adapter.LOCKED_TEST_BATCH_IMPLEMENTATION_SHA256
    )


def test_manager_authorization_scope_is_exactly_two_source_paths() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    payload = adapter._authorization_payload(config)
    assert payload["authorized_top_level_source_paths"] == [
        adapter.AUTHORIZED_SOURCE_PATH,
        adapter.AUTHORIZED_TEST_PATH,
    ]
    assert payload["authorized_mechanism"] == {
        "temporary_execution_global": "validate_full_plan",
        "replacement_callable": "extension_aware_validate_full_plan",
        "try_finally_restore_required": True,
        "unchanged_batch_function_called": True,
        "other_execution_global_or_function_mutation_allowed": False,
    }
    assert all(payload["forbidden_scope"].values())


def test_request_is_canonical_earliest_pending_and_model_free() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    request, targets = adapter._normalize_request(
        config,
        "1" * 64,
        ["locked_test_c001_r01"],
        1,
    )
    assert [row["pair_id"] for row in targets] == ["locked_test_c001_r01"]
    assert request["target_pair_ids"] == ["locked_test_c001_r01"]
    assert request["max_new_pairs"] == 1
    assert request["model_access_allowed"] is False
    assert request["prediction_access_allowed"] is False
    assert request["locked_test_outcome_access_allowed"] is False
    assert request["registered_target_access_allowed"] is False
    assert request["external_service_mutation_allowed"] is False


def test_terminal_idempotence_can_rebuild_the_same_static_request() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    request, targets = adapter._normalize_request(
        config,
        "1" * 64,
        ["locked_test_c001_r00"],
        1,
        require_earliest_pending=False,
    )
    assert request["target_pair_ids"] == ["locked_test_c001_r00"]
    assert [row["pair_id"] for row in targets] == ["locked_test_c001_r00"]
    with pytest.raises(execution.ContractError, match="earliest pending"):
        adapter._normalize_request(
            config,
            "1" * 64,
            ["locked_test_c001_r00"],
            1,
            require_earliest_pending=True,
        )


@pytest.mark.parametrize(
    ("pair_ids", "limit", "message"),
    [
        ([], 1, "empty or duplicate"),
        (["locked_test_c001_r01", "locked_test_c001_r01"], 1, "duplicate"),
        (["locked_test_c001_r02"], 1, "earliest pending"),
        (["locked_test_c001_r01"], 0, "positive"),
    ],
)
def test_noncanonical_adapter_request_fails_closed(
    pair_ids: list[str], limit: int, message: str
) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    with pytest.raises(execution.ContractError, match=message):
        adapter._normalize_request(config, "1" * 64, pair_ids, limit)


def test_only_validator_callable_changes_and_is_restored_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = execution.validate_full_plan

    def fake_batch(
        _config_path: Path, _pair_ids: list[str], *, max_new_pairs: int
    ) -> dict:
        assert execution.validate_full_plan is adapter.extension_aware_validate_full_plan
        assert max_new_pairs == 1
        return {"status": "MOCK_PASS"}

    monkeypatch.setattr(execution, "run_locked_test_render_batch", fake_batch)
    result = adapter._call_unchanged_batch(
        RUNTIME_CONFIG, ["locked_test_c001_r01"], max_new_pairs=1
    )
    assert result == {"status": "MOCK_PASS"}
    assert execution.validate_full_plan is original


def test_original_validator_is_restored_after_underlying_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = execution.validate_full_plan

    def failing_batch(*_args: object, **_kwargs: object) -> dict:
        assert execution.validate_full_plan is adapter.extension_aware_validate_full_plan
        raise RuntimeError("mock terminal failure")

    monkeypatch.setattr(execution, "run_locked_test_render_batch", failing_batch)
    with pytest.raises(RuntimeError, match="mock terminal failure"):
        adapter._call_unchanged_batch(
            RUNTIME_CONFIG, ["locked_test_c001_r01"], max_new_pairs=1
        )
    assert execution.validate_full_plan is original


def test_any_second_execution_callable_change_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_render = execution.render_full_pair

    def changed_render(*_args: object, **_kwargs: object) -> dict:
        return {}

    def corrupting_batch(*_args: object, **_kwargs: object) -> dict:
        execution.render_full_pair = changed_render
        return {"status": "MOCK_PASS"}

    monkeypatch.setattr(execution, "run_locked_test_render_batch", corrupting_batch)
    try:
        with pytest.raises(
            execution.ContractError, match="Unauthorized execution callable change"
        ):
            adapter._call_unchanged_batch(
                RUNTIME_CONFIG, ["locked_test_c001_r01"], max_new_pairs=1
            )
    finally:
        execution.render_full_pair = original_render


def test_adapter_intent_is_atomic_exact_and_idempotent(tmp_path: Path) -> None:
    parent = tmp_path / "executions"
    request = {"target_pair_ids": ["locked_test_c001_r01"], "max_new_pairs": 1}
    intent = {
        "schema_version": 1,
        "contract": adapter.INTENT_CONTRACT,
        "request": request,
    }
    root, resumed = adapter._publish_or_resume_intent(
        parent, "extension_aware_batch_locked_test_c001_r01_0123456789abcdef", intent
    )
    assert resumed is False
    assert execution.load_json(root / "adapter_intent.json") == intent
    same_root, resumed = adapter._publish_or_resume_intent(
        parent, "extension_aware_batch_locked_test_c001_r01_0123456789abcdef", intent
    )
    assert same_root == root
    assert resumed is True
    changed = copy.deepcopy(intent)
    changed["request"]["max_new_pairs"] = 2
    with pytest.raises(execution.ContractError, match="request changed"):
        adapter._publish_or_resume_intent(
            parent,
            "extension_aware_batch_locked_test_c001_r01_0123456789abcdef",
            changed,
        )


def test_partial_or_unbound_adapter_intent_fails_closed(tmp_path: Path) -> None:
    parent = tmp_path / "executions"
    parent.mkdir()
    partial = parent / ".partial-forbidden"
    partial.mkdir()
    with pytest.raises(execution.ContractError, match="Partial adapter intent"):
        adapter._publish_or_resume_intent(
            parent,
            "extension_aware_batch_locked_test_c001_r01_0123456789abcdef",
            {"request": {}},
        )
    partial.rmdir()
    unbound = parent / "extension_aware_batch_locked_test_c001_r01_0123456789abcdef"
    unbound.mkdir()
    with pytest.raises(execution.ContractError, match="no valid intent"):
        adapter._publish_or_resume_intent(
            parent,
            "extension_aware_batch_locked_test_c001_r01_0123456789abcdef",
            {"request": {}},
        )


def test_material_source_hash_drift_fails_closed_before_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = execution.sha256_file
    legacy_path = adapter._source_paths()["legacy_execution"].resolve()

    def drifted(path: Path) -> str:
        if Path(path).resolve() == legacy_path:
            return "0" * 64
        return original(Path(path))

    monkeypatch.setattr(execution, "sha256_file", drifted)
    with pytest.raises(execution.ContractError, match="legacy execution bytes changed"):
        adapter._verify_unchanged_sources()


@pytest.mark.parametrize(
    ("target_kind", "message"),
    [
        ("runtime_config", "runtime config bytes changed"),
        ("runtime_release", "runtime release bytes changed"),
        ("validator_release", "validator release bytes changed"),
        ("render_state", "state bytes changed"),
        ("ledger", "[Cc]andidate rejection ledger bytes changed"),
        (
            "extension_manifest",
            "Frozen Pass55 docs mirror changed|extension manifest bytes changed",
        ),
    ],
)
def test_release_state_ledger_or_roster_hash_drift_fails_before_intent(
    target_kind: str,
    message: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    full = execution.full_paths(config)
    targets = {
        "runtime_config": Path(RUNTIME_CONFIG).resolve(),
        "runtime_release": execution.runtime_compatibility_paths(
            execution.load_config(execution.DEFAULT_CONFIG)
        )["release"].resolve(),
        "validator_release": adapter.validator.validation_paths(config)[
            "release"
        ].resolve(),
        "render_state": (full["synthetic"] / "planning/render_state_v1.json").resolve(),
        "ledger": (
            full["synthetic"]
            / "planning/candidate_rejection_ledger_v1.jsonl"
        ).resolve(),
        "extension_manifest": execution.roster_extension_paths(config)[
            "manifest"
        ].resolve(),
    }
    original = execution.sha256_file
    target = targets[target_kind]

    def drifted(path: Path) -> str:
        if Path(path).resolve() == target:
            return "0" * 64
        return original(Path(path))

    monkeypatch.setattr(execution, "sha256_file", drifted)
    with pytest.raises(execution.ContractError, match=message):
        adapter._validated_extension_boundary(RUNTIME_CONFIG)
    assert not adapter.adapter_paths(config)["executions"].exists()


def test_release_file_set_rejects_partial_extra_and_mirror_drift(
    tmp_path: Path,
) -> None:
    paths = _temporary_paths(tmp_path)
    paths["synthetic_release"].mkdir(parents=True)
    paths["docs_release"].mkdir(parents=True)
    with pytest.raises(execution.ContractError, match="file set changed"):
        adapter._validate_release_file_set(paths)
    for relative in adapter._required_release_files():
        (paths["synthetic_release"] / relative).write_text("{}\n", encoding="utf-8")
        (paths["docs_release"] / relative).write_text("{}\n", encoding="utf-8")
    adapter._validate_release_file_set(paths)
    (paths["docs_release"] / adapter._required_release_files()[0]).write_text(
        '{"changed":true}\n', encoding="utf-8"
    )
    with pytest.raises(execution.ContractError, match="mirror changed"):
        adapter._validate_release_file_set(paths)


def test_terminal_receipt_binds_underlying_intent_receipt_and_zero_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    synthetic = tmp_path / "synthetic"
    batch_root = (
        synthetic
        / "planning/locked_test_render_batches_v1/mock_underlying_batch"
    )
    batch_root.mkdir(parents=True)
    execution.write_json(batch_root / "batch_intent.json", {"intent": "bound"})
    execution.write_json(batch_root / "batch_receipt.json", {"receipt": "bound"})
    intent_path = tmp_path / "adapter_intent.json"
    execution.write_json(intent_path, {"adapter": "intent"})
    monkeypatch.setattr(
        execution,
        "full_paths",
        lambda _config: {"synthetic": synthetic, "docs": tmp_path / "docs"},
    )
    request = {
        "adapter_release_identity_sha256": "1" * 64,
        "target_pair_ids": ["locked_test_c001_r01"],
        "max_new_pairs": 1,
    }
    underlying = {
        "batch_id": "mock_underlying_batch",
        "status": "PASS_LOCKED_TEST_RENDER_BATCH_PREOUTCOME_SYNTHETIC_ONLY",
        "new_pair_ids": ["locked_test_c001_r01"],
    }
    before = {
        "render_state_sha256": "2" * 64,
        "candidate_rejection_ledger_sha256": "3" * 64,
    }
    after = {
        "render_state_sha256": "4" * 64,
        "candidate_rejection_ledger_sha256": "5" * 64,
    }
    receipt = adapter._terminal_payload(
        config,
        request,
        "6" * 64,
        "extension_aware_batch_locked_test_c001_r01_0123456789abcdef",
        intent_path,
        underlying,
        before,
        after,
    )
    adapter._validate_terminal_receipt(
        config,
        receipt,
        request,
        "6" * 64,
        "extension_aware_batch_locked_test_c001_r01_0123456789abcdef",
        intent_path,
    )
    assert receipt["access_guard"]["model_loaded"] is False
    assert receipt["access_guard"]["inference_calls"] == 0
    assert receipt["access_guard"]["outcome_inputs"] == []
    changed = copy.deepcopy(receipt)
    changed["access_guard"]["inference_calls"] = 1
    with pytest.raises(execution.ContractError, match="terminal receipt changed"):
        adapter._validate_terminal_receipt(
            config,
            changed,
            request,
            "6" * 64,
            "extension_aware_batch_locked_test_c001_r01_0123456789abcdef",
            intent_path,
        )


def test_adapter_implementation_identity_is_deterministic() -> None:
    assert adapter.adapter_implementation_sha256() == (
        adapter.adapter_implementation_sha256()
    )


def test_temporary_release_seal_repeat_is_byte_stable_and_zero_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _temporary_paths(tmp_path)
    monkeypatch.setattr(adapter, "adapter_paths", lambda _config: paths)

    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("validate-only adapter invoked an external process")

    monkeypatch.setattr(execution.subprocess, "run", forbidden)
    first = adapter.seal_adapter_release(RUNTIME_CONFIG)
    before = {
        relative: execution.sha256_file(paths["synthetic_release"] / relative)
        for relative in adapter._required_release_files()
    }
    second = adapter.seal_adapter_release(RUNTIME_CONFIG)
    after = {
        relative: execution.sha256_file(paths["synthetic_release"] / relative)
        for relative in adapter._required_release_files()
    }
    assert first == second
    assert before == after
    assert first["real_adapter_intents_created"] == 0
    assert first["candidate_gt_accessed"] is False
    assert first["rendering_calls"] == 0
    assert first["model_loaded"] is False
    assert first["inference_calls"] == 0
    assert first["outcome_inputs"] == []
    assert first["field_product_or_chemical_go"] is False
    assert not paths["executions"].exists()


def test_execution_validation_failure_occurs_before_adapter_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    paths = adapter.adapter_paths(config)
    assert paths["release"].is_file()

    def blocked(_config_path: Path) -> dict:
        raise execution.ContractError("mock release drift")

    def forbidden(*_args: object, **_kwargs: object) -> tuple[Path, bool]:
        raise AssertionError("intent was created after failed validation")

    monkeypatch.setattr(adapter, "validate_adapter_release", blocked)
    monkeypatch.setattr(adapter, "_publish_or_resume_intent", forbidden)
    with pytest.raises(execution.ContractError, match="mock release drift"):
        adapter.run_extension_aware_batch(
            RUNTIME_CONFIG, ["locked_test_c001_r01"], max_new_pairs=1
        )


def test_live_adapter_release_validates_repeatedly_without_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("validate-only adapter invoked an external process")

    monkeypatch.setattr(execution.subprocess, "run", forbidden)
    first = adapter.validate_adapter_release(RUNTIME_CONFIG)
    second = adapter.validate_adapter_release(RUNTIME_CONFIG)
    assert first == second
    assert first["status"] == (
        "PASS_EXTENSION_AWARE_BATCH_ADAPTER_VALIDATION_SYNTHETIC_ONLY"
    )
    assert first["completed_pair_count"] == 41
    assert first["pending_pair_count"] == 55
    assert first["first_pending_pair_id"] == "locked_test_c001_r01"
    assert first["real_adapter_intents_created"] == 0
    assert first["candidate_gt_accessed"] is False
    assert first["rendering_calls"] == 0
    assert first["model_loaded"] is False
    assert first["inference_calls"] == 0
    assert first["prediction_accessed"] is False
    assert first["locked_test_outcome_accessed"] is False
    assert first["registered_targets_used"] is False
    assert first["external_services_modified"] is False
    assert first["outcome_inputs"] == []
    assert first["field_product_or_chemical_go"] is False


def test_live_release_is_mirrored_and_no_real_adapter_intent_exists() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    paths = adapter.adapter_paths(config)
    adapter._validate_release_file_set(paths)
    assert not paths["executions"].exists()
    assert not paths["docs_executions"].exists()
    release = execution.load_json(paths["release"])
    assert release["legacy_execution_script_sha256"] == (
        adapter.LEGACY_EXECUTION_SCRIPT_SHA256
    )
    assert release["legacy_execution_test_sha256"] == (
        adapter.LEGACY_EXECUTION_TEST_SHA256
    )
    assert release["validator_script_sha256"] == adapter.VALIDATOR_SCRIPT_SHA256
    assert release["validator_test_sha256"] == adapter.VALIDATOR_TEST_SHA256
    assert release["historical_or_parent_bytes_rewritten_or_rebound"] is False
    assert release["legacy_wrapper_semantics_changed"] is False
    assert release["pass66_validation_only"] is True
