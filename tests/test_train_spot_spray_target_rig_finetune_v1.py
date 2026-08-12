import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

import scripts.train_spot_spray_target_rig_finetune_v1 as finetune
from scripts.evaluate_spot_spray_target_rig_action_v1 import ContractError, load_manifest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/benchmark/spot_spray_target_rig_finetune_v1.yaml"
ACTION_CONFIG = ROOT / "configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml"
SCHEMA = ROOT / "configs/data/spot_spray_capture_manifest_v1.schema.json"
FIXTURES = ROOT / "tests/fixtures/spot_spray_target_rig_model_v1"
MANIFEST = FIXTURES / "finetune_capture_manifest_v1.json"
AUDIT = FIXTURES / "finetune_capture_audit_v1.json"


def test_config_pins_foundation_capture_sources_and_test_isolation() -> None:
    config, foundation = finetune.validate_config(CONFIG)
    assert finetune.sha256(foundation) == finetune.SELECTED_FOUNDATION_SHA256
    assert config["foundation"]["checkpoint_sha256"] == (
        "3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100"
    )
    for source in config["capture_interface"]["sources"].values():
        assert finetune.sha256(ROOT / source["path"]) == source["sha256"]
    assert finetune.capture_manager_accepted(config) is False
    assert config["dataset"]["forbidden_training_splits"] == ["test", "unassigned"]
    assert config["selection"]["final_checkpoint"] == "last.pt"
    assert config["selection"]["best_checkpoint_used_for_final"] is False


def test_capture_manager_acceptance_requires_status_and_identity() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    acceptance = config["capture_interface"]["manager_acceptance"]
    acceptance["status"] = "accepted"
    with pytest.raises(ContractError, match="acceptance_id"):
        finetune.capture_manager_accepted(config)
    acceptance["acceptance_id"] = "manager_capture_release_v1"
    assert finetune.capture_manager_accepted(config) is True


def test_finetune_fixture_matches_current_schema_and_preserves_provenance() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
    action_config = yaml.safe_load(ACTION_CONFIG.read_text(encoding="utf-8"))
    manifest = load_manifest(MANIFEST, action_config)
    assert manifest.rig_acceptance is not None
    assert manifest.rig_acceptance.result_path == (
        "receipts/synthetic_fixture_only.json"
    )
    frame = next(item for item in manifest.frames if item.frame_id == "train_known_frame")
    assert frame.image_sha256 == (
        "e99c0fc58cc3e0696ded5dc51214bc15f3f82251b9446db9424c7e77fbac27aa"
    )
    assert frame.camera_frame_counter == 100
    assert frame.camera_timestamp_ns == 1000000100
    assert frame.white_balance is not None and frame.white_balance.mode == "manual"
    assert frame.native_width_px == 1024 and frame.native_height_px == 1024
    assert frame.pixel_format == "RGB8"
    assert frame.camera_id == "fixture_camera" and frame.rig_id == "fixture_rig"
    assert frame.capture_profile_id == "fixture_profile"
    assert frame.strobe_settings is not None
    assert frame.strobe_settings.profile_id == frame.strobe_profile_id


def test_fixture_audit_is_exactly_bound_but_never_real_proof() -> None:
    manifest, audit = finetune.load_capture_inputs(MANIFEST, AUDIT, FIXTURES)
    receipt = json.loads(AUDIT.read_text(encoding="utf-8"))
    assert manifest.evidence_scope == "synthetic_fixture"
    assert audit.evidence_scope == "synthetic_fixture"
    assert audit.synthetic_fixture is True
    assert audit.real_proof_accepted is False
    assert Path(audit.data_root) == FIXTURES.resolve()
    assert receipt["inputs"]["manifest_sha256"] == finetune.sha256(MANIFEST)
    implementation = ROOT / receipt["implementation"]["script"]
    assert receipt["implementation"]["script_sha256"] == finetune.sha256(
        implementation
    )
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert receipt["implementation"]["script_sha256"] == config[
        "capture_interface"
    ]["sources"]["audit_implementation"]["sha256"]


def test_fixture_preparation_materializes_only_train_and_validation(
    tmp_path: Path,
) -> None:
    output = tmp_path / "prepared"
    preparation, config, foundation = finetune.prepare_dataset(
        CONFIG,
        MANIFEST,
        AUDIT,
        FIXTURES,
        output,
        fixture_mode=True,
    )
    assert preparation.fixture_only is True
    assert preparation.real_training_ready is False
    assert finetune.sha256(foundation) == config["foundation"]["checkpoint_sha256"]
    dataset_yaml = yaml.safe_load(preparation.dataset_yaml.read_text(encoding="utf-8"))
    assert set(dataset_yaml) == {"path", "train", "val", "names"}
    assert dataset_yaml["train"] == "images/train"
    assert dataset_yaml["val"] == "images/validation"
    assert "test" not in dataset_yaml
    assert sorted(path.name for path in (output / "images/train").iterdir()) == [
        "train_known_frame.jpg"
    ]
    assert sorted(path.name for path in (output / "images/validation").iterdir()) == [
        "validation_known_frame.jpg"
    ]
    assert not (output / "images/test").exists()
    assert not (output / "labels/test").exists()
    assert not (output / "images/train/train_partial_unknown.jpg").exists()
    assert not (output / "labels/train/train_partial_unknown.txt").exists()

    train_label = (output / "labels/train/train_known_frame.txt").read_text(
        encoding="utf-8"
    )
    assert train_label.splitlines()[0].startswith("0 ")
    assert train_label.splitlines()[1].startswith("1 ")
    index = json.loads(preparation.dataset_index.read_text(encoding="utf-8"))
    assert {entry["frame_id"] for entry in index["entries"]} == {
        "train_known_frame",
        "validation_known_frame",
    }
    assert index["test_entries"] == []
    assert index["quarantined_partial_unknown_frames"] == [
        {
            "frame_id": "train_partial_unknown",
            "reason": "contains_partial_unknown_entire_frame_quarantined",
            "split": "train",
        }
    ]
    receipt = json.loads(preparation.dataset_receipt.read_text(encoding="utf-8"))
    assert receipt["status"] == "FIXTURE_ONLY"
    assert receipt["counts"]["materialized_train_frames"] == 1
    assert receipt["counts"]["materialized_validation_frames"] == 1
    assert receipt["counts"]["quarantined_partial_unknown_frames"] == 1
    assert receipt["counts"]["excluded_test_frames"] == 1
    assert receipt["test_isolation"] == {
        "test_image_bytes_read": False,
        "test_images_materialized": False,
        "test_labels_materialized": False,
        "test_manifest_metadata_used_only_to_count_exclusion": True,
        "test_used_for_checkpoint_selection": False,
        "test_used_for_training": False,
    }


def test_preparation_never_reads_test_or_quarantined_image_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_sha256 = finetune.sha256
    forbidden = {"test_secret.jpg", "train_unknown.jpg"}

    def guarded_sha256(path: str | Path) -> str:
        candidate = Path(path)
        if candidate.name in forbidden:
            raise AssertionError(f"forbidden image bytes read: {candidate.name}")
        return original_sha256(candidate)

    monkeypatch.setattr(finetune, "sha256", guarded_sha256)
    finetune.prepare_dataset(
        CONFIG,
        MANIFEST,
        AUDIT,
        FIXTURES,
        tmp_path / "prepared",
        fixture_mode=True,
    )


def test_fixture_cli_emits_three_non_evidence_receipts_and_exit_four(
    tmp_path: Path,
) -> None:
    output = tmp_path / "prepared"
    result, exit_code = finetune.run_cli(
        finetune.parse_args(
            [
                "--config",
                str(CONFIG),
                "--manifest",
                str(MANIFEST),
                "--capture-audit",
                str(AUDIT),
                "--data-root",
                str(FIXTURES),
                "--output-directory",
                str(output),
                "--fixture-mode",
            ]
        )
    )
    assert exit_code == 4
    assert result["status"] == "FIXTURE_ONLY"
    assert result["training_executed"] is False
    assert result["real_training_ready"] is False
    dataset = json.loads((output / "dataset_receipt.json").read_text(encoding="utf-8"))
    training = json.loads((output / "training_receipt.json").read_text(encoding="utf-8"))
    final = json.loads(
        (output / "final_checkpoint_receipt.json").read_text(encoding="utf-8")
    )
    assert dataset["status"] == "FIXTURE_ONLY"
    assert training["status"] == "FIXTURE_ONLY_DRY_RUN"
    assert training["training_executed"] is False
    assert training["test_access"] == {
        "checkpoint_selection": False,
        "threshold_calibration": False,
        "training": False,
    }
    assert final["status"] == "NOT_PRODUCED_DRY_RUN"
    assert final["checkpoint"] is None and final["checkpoint_sha256"] is None


def test_execute_training_is_rejected_before_output_for_any_fixture(
    tmp_path: Path,
) -> None:
    output = tmp_path / "must_not_exist"
    result, exit_code = finetune.run_cli(
        finetune.parse_args(
            [
                "--config",
                str(CONFIG),
                "--manifest",
                str(MANIFEST),
                "--capture-audit",
                str(AUDIT),
                "--data-root",
                str(FIXTURES),
                "--output-directory",
                str(output),
                "--execute-training",
            ]
        )
    )
    assert exit_code == 5
    assert result["status"] == "CONTRACT_ERROR"
    assert result["training_executed"] is False
    assert not output.exists()


def test_fixture_mode_cannot_relabel_unproven_real_evidence(
    tmp_path: Path,
) -> None:
    manifest, audit = _write_real_claim_without_physical_proof(tmp_path)
    output = tmp_path / "must_not_exist"
    result, exit_code = finetune.run_cli(
        finetune.parse_args(
            [
                "--manifest",
                str(manifest),
                "--capture-audit",
                str(audit),
                "--data-root",
                str(FIXTURES),
                "--output-directory",
                str(output),
                "--fixture-mode",
            ]
        )
    )
    assert exit_code == 5
    assert result["status"] == "CONTRACT_ERROR"
    assert "only for explicitly synthetic" in result["reason"]
    assert not output.exists()


def test_manifest_and_audit_evidence_scopes_must_match(
    tmp_path: Path,
) -> None:
    manifest_payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_payload["evidence_scope"] = "real_target_rig"
    manifest = tmp_path / "relabeled_manifest.json"
    manifest.write_text(json.dumps(manifest_payload) + "\n", encoding="utf-8")
    audit_payload = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit_payload["inputs"]["manifest"] = str(manifest.resolve())
    audit_payload["inputs"]["manifest_sha256"] = finetune.sha256(manifest)
    audit = tmp_path / "synthetic_audit.json"
    audit.write_text(json.dumps(audit_payload) + "\n", encoding="utf-8")
    output = tmp_path / "must_not_exist"
    result, exit_code = finetune.run_cli(
        finetune.parse_args(
            [
                "--manifest",
                str(manifest),
                "--capture-audit",
                str(audit),
                "--data-root",
                str(FIXTURES),
                "--output-directory",
                str(output),
            ]
        )
    )
    assert exit_code == 5
    assert result["status"] == "CONTRACT_ERROR"
    assert "evidence scopes must match" in result["reason"]
    assert not output.exists()


def test_default_cli_is_not_ready_without_inputs() -> None:
    result, exit_code = finetune.run_cli(finetune.parse_args(["--config", str(CONFIG)]))
    assert exit_code == 2
    assert result["status"] == "NOT_READY"
    assert result["training_executed"] is False


def _write_real_claim_without_physical_proof(tmp_path: Path) -> tuple[Path, Path]:
    manifest_payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_payload["evidence_scope"] = "real_target_rig"
    manifest = tmp_path / "real_claim_manifest.json"
    manifest.write_text(json.dumps(manifest_payload) + "\n", encoding="utf-8")

    audit_payload = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit_payload.update({"status": "READY", "valid": True, "ready": True})
    audit_payload["evidence"].update(
        {
            "scope": "real_target_rig",
            "synthetic_fixture": False,
            "counts_as_real_target_rig_evidence": False,
        }
    )
    audit_payload["readiness_reasons"] = []
    audit_payload["inputs"]["manifest"] = str(manifest.resolve())
    audit_payload["inputs"]["manifest_sha256"] = finetune.sha256(manifest)
    audit = tmp_path / "unproven_real_audit.json"
    audit.write_text(json.dumps(audit_payload) + "\n", encoding="utf-8")
    return manifest, audit


def test_real_claim_is_blocked_by_manager_and_physical_readiness(
    tmp_path: Path,
) -> None:
    manifest, audit = _write_real_claim_without_physical_proof(tmp_path)
    output = tmp_path / "must_not_exist"
    result, exit_code = finetune.run_cli(
        finetune.parse_args(
            [
                "--config",
                str(CONFIG),
                "--manifest",
                str(manifest),
                "--capture-audit",
                str(audit),
                "--data-root",
                str(FIXTURES),
                "--output-directory",
                str(output),
            ]
        )
    )
    assert exit_code == 2
    assert result["status"] == "NOT_READY"
    assert "capture_lane_manager_acceptance" in result["reason"]
    assert "physical_READY_capture_audit" in result["reason"]
    assert not output.exists()


def test_manifest_or_audit_hash_drift_fails_before_output(tmp_path: Path) -> None:
    audit_payload = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit_payload["inputs"]["manifest_sha256"] = "0" * 64
    bad_audit = tmp_path / "bad_audit.json"
    bad_audit.write_text(json.dumps(audit_payload) + "\n", encoding="utf-8")
    output = tmp_path / "must_not_exist"
    result, exit_code = finetune.run_cli(
        finetune.parse_args(
            [
                "--manifest",
                str(MANIFEST),
                "--capture-audit",
                str(bad_audit),
                "--data-root",
                str(FIXTURES),
                "--output-directory",
                str(output),
                "--fixture-mode",
            ]
        )
    )
    assert exit_code == 5
    assert result["status"] == "CONTRACT_ERROR"
    assert "manifest hash" in result["reason"]
    assert not output.exists()


def test_source_image_hash_drift_fails_before_materialization(tmp_path: Path) -> None:
    manifest_payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_payload["frames"][0]["image_sha256"] = "0" * 64
    manifest = tmp_path / "bad_image_manifest.json"
    manifest.write_text(json.dumps(manifest_payload) + "\n", encoding="utf-8")
    audit_payload = json.loads(AUDIT.read_text(encoding="utf-8"))
    audit_payload["inputs"]["manifest"] = str(manifest.resolve())
    audit_payload["inputs"]["manifest_sha256"] = finetune.sha256(manifest)
    audit = tmp_path / "bound_audit.json"
    audit.write_text(json.dumps(audit_payload) + "\n", encoding="utf-8")
    output = tmp_path / "must_not_exist"
    result, exit_code = finetune.run_cli(
        finetune.parse_args(
            [
                "--manifest",
                str(manifest),
                "--capture-audit",
                str(audit),
                "--data-root",
                str(FIXTURES),
                "--output-directory",
                str(output),
                "--fixture-mode",
            ]
        )
    )
    assert exit_code == 5
    assert "Source image SHA-256 mismatch" in result["reason"]
    assert not output.exists()


def test_partial_unknown_policy_and_foundation_hash_cannot_be_weakened(
    tmp_path: Path,
) -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["dataset"]["partial_unknown"]["policy"] = "treat_as_background"
    unsafe = tmp_path / "unsafe_partial.yaml"
    unsafe.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(ContractError, match="partial_unknown quarantine"):
        finetune.validate_config(unsafe)

    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["foundation"]["checkpoint_sha256"] = "0" * 64
    unsafe = tmp_path / "unsafe_foundation.yaml"
    unsafe.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(ContractError, match="foundation SHA-256 drift"):
        finetune.validate_config(unsafe)

    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["training"]["epochs"] = 1
    unsafe = tmp_path / "unsafe_epoch.yaml"
    unsafe.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(ContractError, match="Frozen training protocol drift"):
        finetune.validate_config(unsafe)

    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["output"]["dataset_receipt"] = "../escaped.json"
    unsafe = tmp_path / "unsafe_output.yaml"
    unsafe.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    with pytest.raises(ContractError, match="Derived-output names"):
        finetune.validate_config(unsafe)


def test_dataset_index_and_labels_are_reproducible_across_output_roots(
    tmp_path: Path,
) -> None:
    first, _, _ = finetune.prepare_dataset(
        CONFIG, MANIFEST, AUDIT, FIXTURES, tmp_path / "first", fixture_mode=True
    )
    second, _, _ = finetune.prepare_dataset(
        CONFIG, MANIFEST, AUDIT, FIXTURES, tmp_path / "second", fixture_mode=True
    )
    assert finetune.sha256(first.dataset_index) == finetune.sha256(second.dataset_index)
    for relative in (
        Path("labels/train/train_known_frame.txt"),
        Path("labels/validation/validation_known_frame.txt"),
    ):
        assert finetune.sha256(first.output_directory / relative) == finetune.sha256(
            second.output_directory / relative
        )


def test_prepared_dataset_verification_detects_symlink_or_label_drift(
    tmp_path: Path,
) -> None:
    first, _, _ = finetune.prepare_dataset(
        CONFIG, MANIFEST, AUDIT, FIXTURES, tmp_path / "first", fixture_mode=True
    )
    finetune.verify_prepared_dataset(first)
    image = first.output_directory / "images/train/train_known_frame.jpg"
    image.unlink()
    image.symlink_to(FIXTURES / "finetune_images/validation_known.jpg")
    with pytest.raises(ContractError, match="image symlink drift"):
        finetune.verify_prepared_dataset(first)

    second, _, _ = finetune.prepare_dataset(
        CONFIG, MANIFEST, AUDIT, FIXTURES, tmp_path / "second", fixture_mode=True
    )
    label = second.output_directory / "labels/train/train_known_frame.txt"
    label.write_text(label.read_text(encoding="utf-8") + "0 0 0 1 0 0 1\n", encoding="utf-8")
    with pytest.raises(ContractError, match="label hash drift"):
        finetune.verify_prepared_dataset(second)


def test_training_results_require_an_exact_contiguous_epoch_sequence(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results.csv"
    results.write_text("epoch,metric\n1,0.1\n2,0.2\n3,0.3\n", encoding="utf-8")
    assert finetune._completed_epoch_sequence(results) == [1, 2, 3]
    results.write_text("epoch,metric\n1,0.1\n3,0.3\n", encoding="utf-8")
    assert finetune._completed_epoch_sequence(results) != [1, 2, 3]
    results.write_text("metric\n0.1\n", encoding="utf-8")
    with pytest.raises(ContractError, match="epoch column"):
        finetune._completed_epoch_sequence(results)


def test_real_manifest_missing_current_provenance_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    payload["evidence_scope"] = "real_target_rig"
    del payload["rig_acceptance"]
    del payload["frames"][0]["camera_frame_counter"]
    path = tmp_path / "missing_real_provenance.json"
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    action_config = yaml.safe_load(ACTION_CONFIG.read_text(encoding="utf-8"))
    with pytest.raises(ContractError, match="rig_acceptance"):
        load_manifest(path, action_config)
