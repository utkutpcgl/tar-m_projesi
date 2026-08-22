from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts import run_spot_spray_simulation_video_ab_execution_v1 as execution
from scripts import validate_spot_spray_simulation_video_ab_extension_aware_v1 as validator


RUNTIME_CONFIG = validator.DEFAULT_CONFIG


def _live_inputs() -> tuple[dict, dict, list[str]]:
    config = execution.load_config(RUNTIME_CONFIG)
    paths = execution.full_paths(config)
    frozen = execution.load_json(
        paths["synthetic"]
        / "planning/historical_epoch_v1_source_snapshots/render_state_v1.ff06d781.json"
    )
    current = execution.load_json(paths["synthetic"] / "planning/render_state_v1.json")
    pair_ids = [row["pair_id"] for row in execution.full_roster_rows(config)]
    return frozen, current, pair_ids


def test_extension_aware_cli_is_explicit_and_separate() -> None:
    assert validator.parse_args(["seal"]).command == "seal"
    parsed = validator.parse_args(["--config", str(RUNTIME_CONFIG), "validate"])
    assert parsed.command == "validate"
    assert parsed.config == RUNTIME_CONFIG


def test_exact_40_to_41_transition_passes() -> None:
    frozen, current, pair_ids = _live_inputs()
    result = validator._validate_transition(frozen, current, pair_ids)
    assert result["from_completed_pair_count"] == 40
    assert result["to_completed_pair_count"] == 41
    assert result["appended_pair_id"] == "locked_test_c001_r00"
    assert result["first_pending_pair_id"] == "locked_test_c001_r01"


@pytest.mark.parametrize(
    "mutation",
    [
        "historical_prefix",
        "wrong_append",
        "pending_reorder",
        "wrong_count",
        "staging",
        "model_output",
    ],
)
def test_noncanonical_40_to_41_transition_fails_closed(mutation: str) -> None:
    frozen, current, pair_ids = _live_inputs()
    changed = copy.deepcopy(current)
    if mutation == "historical_prefix":
        changed["completed_pair_ids"][0] = "locked_test_c007_r07"
    elif mutation == "wrong_append":
        changed["completed_pair_ids"][-1] = "locked_test_c001_r01"
    elif mutation == "pending_reorder":
        changed["pending_pair_ids"][0:2] = reversed(changed["pending_pair_ids"][0:2])
    elif mutation == "wrong_count":
        changed["completed_pair_count"] = 42
    elif mutation == "staging":
        changed["interrupted_staging_directories"] = [".partial-forbidden"]
    elif mutation == "model_output":
        changed["model_outputs_present"] = True
    with pytest.raises(execution.ContractError, match="40-to-41"):
        validator._validate_transition(frozen, changed, pair_ids)


def test_combined_roster_epoch_order_and_uniqueness_fail_closed() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    historical, combined = validator._rosters(config)
    validator._validate_combined_roster_epochs(historical, combined)

    reordered = copy.deepcopy(combined)
    reordered[0]["candidates"][10], reordered[0]["candidates"][11] = (
        reordered[0]["candidates"][11],
        reordered[0]["candidates"][10],
    )
    with pytest.raises(execution.ContractError, match="epoch order"):
        validator._validate_combined_roster_epochs(historical, reordered)

    duplicate = copy.deepcopy(combined)
    duplicate[0]["candidates"][11]["candidate_identity_sha256"] = duplicate[0][
        "candidates"
    ][10]["candidate_identity_sha256"]
    with pytest.raises(execution.ContractError, match="collide"):
        validator._validate_combined_roster_epochs(historical, duplicate)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("selected_candidate_index", 32),
        ("candidate_identity_sha256", "0" * 64),
        ("candidate_seeds", {}),
        ("canonical_gt_sha256", "0" * 64),
        ("outcome_inputs", ["forbidden"]),
        ("model_loaded", True),
        ("inference_calls", 1),
    ],
)
def test_candidate10_material_receipt_drift_fails_closed(field: str, value: object) -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    _, combined = validator._rosters(config)
    row = next(row for row in combined if row["pair_id"] == validator.APPENDED_PAIR_ID)
    receipt_path = (
        execution.full_paths(config)["synthetic"]
        / "pairs/locked_test/locked_test_c001_r00/full_pair_receipt.json"
    )
    receipt = execution.load_json(receipt_path)
    receipt[field] = value
    with pytest.raises(execution.ContractError):
        validator._validate_candidate10_receipt(
            receipt,
            row["candidates"][10],
            row,
            config["evidence_policy"],
        )


def test_claim_boundary_go_drift_fails_closed() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    changed = copy.deepcopy(config)
    changed["evidence_policy"]["chemical_fire_go_allowed"] = True
    with pytest.raises(execution.ContractError, match="claim boundary"):
        validator._claim_boundary(changed)


def test_static_inventory_exempts_only_frozen_live_state(tmp_path: Path) -> None:
    protected = tmp_path / "protected.json"
    protected.write_text("{}\n", encoding="utf-8")
    mutable = "docs/example/render_state_v1.json"
    rows = [
        {
            "path": str(protected),
            "size_bytes": protected.stat().st_size,
            "sha256": execution.sha256_file(protected),
        },
        {
            "path": mutable,
            "size_bytes": 2910,
            "sha256": validator.FROZEN_STATE_SHA256,
        },
    ]
    result = validator._static_inventory_rows(rows, mutable_path=mutable)
    assert result["static_file_count"] == 1
    protected.write_text("changed\n", encoding="utf-8")
    with pytest.raises(execution.ContractError, match="historical evidence changed"):
        validator._static_inventory_rows(rows, mutable_path=mutable)


def test_partial_or_extra_validator_release_fails_closed(tmp_path: Path) -> None:
    synthetic = tmp_path / "synthetic"
    docs = tmp_path / "docs"
    synthetic.mkdir()
    docs.mkdir()
    (synthetic / "pass64_validation_receipt.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(execution.ContractError, match="file set changed"):
        validator._validate_file_set({"synthetic": synthetic, "docs": docs})


def test_legacy_validator_remains_fail_closed_and_new_validator_passes() -> None:
    with pytest.raises(
        execution.ContractError,
        match=r"Invalid published full pair receipts: \['locked_test_c001_r00'\]",
    ):
        execution.validate_full_plan(RUNTIME_CONFIG)
    result = validator.validate_extension_aware_full_plan(RUNTIME_CONFIG)
    assert result["status"] == (
        "PASS_EXTENSION_AWARE_FULL_PLAN_VALIDATION_SYNTHETIC_ONLY"
    )
    assert result["completed_pair_count"] == 41
    assert result["pending_pair_count"] == 55
    assert result["model_loaded"] is False
    assert result["inference_calls"] == 0
    assert result["field_product_or_chemical_go"] is False


def test_validator_seal_repeat_is_byte_stable_and_zero_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("validation-only bridge invoked an external process")

    monkeypatch.setattr(execution.subprocess, "run", forbidden)
    config = execution.load_config(RUNTIME_CONFIG)
    paths = validator.validation_paths(config)
    before = {
        relative: execution.sha256_file(paths["synthetic"] / relative)
        for relative in validator._required_files()
    }
    first = validator.seal_extension_aware_validator(RUNTIME_CONFIG)
    second = validator.seal_extension_aware_validator(RUNTIME_CONFIG)
    after = {
        relative: execution.sha256_file(paths["synthetic"] / relative)
        for relative in validator._required_files()
    }
    assert first == second
    assert before == after
    assert first["rendering_calls"] == 0
    assert first["model_loaded"] is False
    assert first["inference_calls"] == 0
    assert first["outcome_inputs"] == []


def test_old_sealed_parent_hashes_remain_exact() -> None:
    config = execution.load_config(RUNTIME_CONFIG)
    runtime = execution.runtime_compatibility_paths(config)
    assert execution.sha256_file(RUNTIME_CONFIG) == validator.RUNTIME_CONFIG_SHA256
    assert execution.sha256_file(runtime["release"]) == (
        validator.RUNTIME_RELEASE_FILE_SHA256
    )
    assert execution.sha256_file(
        execution.roster_extension_paths(config)["release"]
    ) == execution.ROSTER_EXTENSION_RELEASE_FILE_SHA256
    assert execution.sha256_file(
        execution.full_paths(config)["synthetic"] / "planning/render_state_v1.json"
    ) == validator.CURRENT_STATE_SHA256
    assert execution.sha256_file(
        execution.full_paths(config)["synthetic"]
        / "planning/candidate_rejection_ledger_v1.jsonl"
    ) == validator.LEDGER_SHA256
