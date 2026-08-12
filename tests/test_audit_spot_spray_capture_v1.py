from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from scripts.audit_spot_spray_capture_v1 import (
    EXIT_INVALID,
    EXIT_NOT_READY,
    assign_deterministic_splits,
    audit_capture,
    deterministic_field_splits,
    load_json_object,
    load_yaml_mapping,
    sha256,
    validate_json_schema,
    validate_policy,
    validate_schema_contract,
)


REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests/fixtures/spot_spray_capture_v1"
CONFIG = REPO / "configs/data/spot_spray_capture_audit_v1.yaml"
SCHEMA = REPO / "configs/data/spot_spray_capture_manifest_v1.schema.json"
SCRIPT = REPO / "scripts/audit_spot_spray_capture_v1.py"


def fixture_audit(name: str) -> dict:
    return audit_capture(
        FIXTURES / name,
        CONFIG,
        data_root=FIXTURES,
        repo_root=REPO,
    )


def error_codes(report: dict) -> set[str]:
    return {entry["code"] for entry in report["errors"]}


def readiness_codes(report: dict) -> set[str]:
    return {entry["code"] for entry in report["readiness_reasons"]}


def write_manifest(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def write_real_scope_candidate_with_synthetic_receipt(
    tmp_path: Path,
) -> tuple[Path, dict, Path]:
    payload = load_json_object(FIXTURES / "valid_complete_synthetic.json")
    payload["evidence_scope"] = "real_target_rig"
    for index, frame in enumerate(payload["frames"]):
        relative_image = Path("images") / f"{frame['frame_id']}.png"
        image_path = tmp_path / relative_image
        image_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 6), (index * 20, 100, 40)).save(image_path)
        frame.update(
            {
                "image_path": relative_image.as_posix(),
                "image_sha256": sha256(image_path),
                "camera_frame_counter": 1000 + int(frame["frame_index"]),
                "camera_timestamp_ns": int(frame["timestamp_ns"]) + 10,
                "exposure_us": 170.0,
                "gain_db": 2.0,
                "white_balance": {
                    "mode": "manual",
                    "red_gain": 1.25,
                    "green_gain": 1.0,
                    "blue_gain": 1.4,
                },
                "working_distance_mm": 480.0,
                "native_width_px": 8,
                "native_height_px": 6,
                "pixel_format": "RGB8",
                "camera_id": "SYNTHETIC-CAMERA-NOT-HARDWARE",
                "rig_id": "SYNTHETIC-RIG-NOT-HARDWARE",
                "capture_profile_id": "synthetic_profile_not_hardware",
                "strobe_settings": {
                    "profile_id": frame["strobe_profile_id"],
                    "pulse_width_us": 150.0,
                    "peak_current_a": 5.0,
                },
            }
        )
    result_path = tmp_path / "rig_acceptance_synthetic.json"
    result_path.write_text(
        (FIXTURES / "rig_acceptance_synthetic.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    payload["rig_acceptance"] = {
        "result_path": result_path.name,
        "result_sha256": sha256(result_path),
    }
    return write_manifest(tmp_path, payload), payload, result_path


def run_cli(
    manifest: Path,
    data_root: Path,
    *,
    config: Path = CONFIG,
    repo_root: Path = REPO,
    extra: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--config",
            str(config),
            "--repo-root",
            str(repo_root),
            "--data-root",
            str(data_root),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def isolated_sources(tmp_path: Path) -> tuple[Path, Path, Path, Path, list[Path]]:
    repo_root = tmp_path / "repo"
    config = repo_root / "configs/data/spot_spray_capture_audit_v1.yaml"
    schema = repo_root / "configs/data/spot_spray_capture_manifest_v1.schema.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_bytes(CONFIG.read_bytes())
    schema.write_bytes(SCHEMA.read_bytes())

    data_root = tmp_path / "data"
    image_root = data_root / "images"
    image_root.mkdir(parents=True, exist_ok=True)
    image_paths: list[Path] = []
    for source in sorted((FIXTURES / "images").glob("*")):
        target = image_root / source.name
        target.write_bytes(source.read_bytes())
        image_paths.append(target)
    manifest = data_root / "manifest.json"
    manifest.write_bytes((FIXTURES / "valid_complete_synthetic.json").read_bytes())
    return repo_root, config, schema, manifest, image_paths


def test_frozen_json_schema_accepts_the_complete_fixture() -> None:
    schema = load_json_object(SCHEMA)
    manifest = load_json_object(FIXTURES / "valid_complete_synthetic.json")

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["schema_version"]["const"] == "capture_manifest_v1"
    assert set(schema["properties"]["evidence_scope"]["enum"]) == {
        "real_target_rig",
        "synthetic_fixture",
    }
    assert set(schema["properties"]["rig_acceptance"]["required"]) == {
        "result_path",
        "result_sha256",
    }
    frame_properties = schema["properties"]["frames"]["items"]["properties"]
    assert {
        "image_sha256",
        "camera_frame_counter",
        "camera_timestamp_ns",
        "white_balance",
        "native_width_px",
        "native_height_px",
        "pixel_format",
        "camera_id",
        "rig_id",
        "capture_profile_id",
        "strobe_settings",
    } <= set(frame_properties)
    assert validate_json_schema(manifest, schema) == []


def test_policy_rejects_relaxed_fractions_seed_polygon_and_other_drift() -> None:
    frozen = load_yaml_mapping(CONFIG)
    attacks = []

    fractions = copy.deepcopy(frozen)
    fractions["split"]["target_fractions"] = {
        "train": 0.98,
        "validation": 0.01,
        "test": 0.01,
    }
    attacks.append(fractions)

    seed = copy.deepcopy(frozen)
    seed["split"]["deterministic_seed"] = "attacker_selected_seed"
    attacks.append(seed)

    polygon = copy.deepcopy(frozen)
    polygon["annotation"]["minimum_normalized_polygon_area"] = -1.0
    attacks.append(polygon)

    other_drift = copy.deepcopy(frozen)
    other_drift["metadata_bounds"]["gain_db"]["maximum"] = 4800.0
    attacks.append(other_drift)

    validate_policy(frozen)
    for changed in attacks:
        with pytest.raises(ValueError):
            validate_policy(changed)


def test_duplicate_yaml_and_json_keys_are_rejected(tmp_path: Path) -> None:
    duplicate_yaml = tmp_path / "duplicate.yaml"
    duplicate_yaml.write_text(
        "schema_version: 1\nsplit:\n  roles: [train]\n  roles: [test]\n",
        encoding="utf-8",
    )
    duplicate_json = tmp_path / "duplicate.json"
    duplicate_json.write_text('{"schema_version": 1, "schema_version": 2}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate YAML key"):
        load_yaml_mapping(duplicate_yaml)
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_json_object(duplicate_json)


def test_policy_and_schema_require_exact_file_and_semantic_identity(tmp_path: Path) -> None:
    schema = load_json_object(SCHEMA)
    changed_schema = copy.deepcopy(schema)
    changed_schema["title"] = "drifted title"
    with pytest.raises(ValueError, match="schema semantics drifted"):
        validate_schema_contract(changed_schema)

    repo_root, config, isolated_schema, manifest, _ = isolated_sources(tmp_path)
    config.write_bytes(config.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="policy file identity drifted"):
        audit_capture(manifest, config, data_root=manifest.parent, repo_root=repo_root)

    config.write_bytes(CONFIG.read_bytes())
    isolated_schema.write_text(
        json.dumps(schema, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema file identity drifted"):
        audit_capture(manifest, config, data_root=manifest.parent, repo_root=repo_root)


def test_complete_synthetic_fixture_is_valid_but_never_ready() -> None:
    report = fixture_audit("valid_complete_synthetic.json")

    assert report["status"] == "NOT_READY"
    assert report["valid"] is True
    assert report["ready"] is False
    assert report["errors"] == []
    assert readiness_codes(report) == {"readiness.synthetic_fixture_only"}
    assert report["statistics"]["fields"] == 3
    assert report["statistics"]["sessions"] == 4
    assert set(report["statistics"]["split_counts"]) == {"train", "validation", "test"}
    assert report["evidence"] == {
        "scope": "synthetic_fixture",
        "synthetic_fixture": True,
        "counts_as_real_target_rig_evidence": False,
        "fixture_can_unlock_ready": False,
    }
    assert report["audit_scope"]["image_files_read"] is False
    assert report["audit_scope"]["real_field_evidence_inferred_from_fixtures"] is False


def test_insufficient_coverage_is_explicitly_not_ready() -> None:
    report = fixture_audit("insufficient_coverage_synthetic.json")

    assert report["status"] == "NOT_READY"
    assert report["valid"] is True
    assert {
        "readiness.minimum_fields_not_met",
        "readiness.minimum_sessions_not_met",
        "readiness.split_roles_missing",
        "readiness.synthetic_fixture_only",
    } == readiness_codes(report)


def test_required_capture_metadata_is_fail_closed() -> None:
    report = fixture_audit("missing_metadata_synthetic.json")

    assert report["status"] == "INVALID"
    assert "schema.required" in error_codes(report)
    assert any(entry["path"].endswith(".exposure_us") for entry in report["errors"])


def test_polygon_geometry_rejects_bow_tie_masks() -> None:
    report = fixture_audit("invalid_polygon_synthetic.json")

    assert report["status"] == "INVALID"
    assert {"polygon.area_too_small", "polygon.self_intersection"} <= error_codes(report)


def test_cross_frame_track_class_must_be_stable() -> None:
    report = fixture_audit("track_identity_conflict_synthetic.json")

    assert report["status"] == "INVALID"
    assert "track.class_conflict" in error_codes(report)


def test_adjacent_frames_and_hierarchical_groups_cannot_cross_roles() -> None:
    report = fixture_audit("adjacent_leakage_synthetic.json")

    assert report["status"] == "INVALID"
    assert {
        "split.adjacent_frame_leakage",
        "split.field_leakage",
        "split.session_leakage",
        "split.video_track_leakage",
    } <= error_codes(report)


def test_deterministic_split_is_stable_and_field_exclusive() -> None:
    config = load_yaml_mapping(CONFIG)
    source = load_json_object(FIXTURES / "valid_complete_synthetic.json")
    for frame in source["frames"]:
        frame["split"] = "unassigned"

    first = assign_deterministic_splits(source, config)
    second = assign_deterministic_splits(source, config)

    assert first == second
    expected = {"field_a": "validation", "field_b": "test", "field_c": "train"}
    assert deterministic_field_splits(expected, config["split"]) == expected
    observed: dict[str, set[str]] = {}
    for frame in first["frames"]:
        observed.setdefault(frame["field_id"], set()).add(frame["split"])
    assert observed == {field: {role} for field, role in expected.items()}


def test_split_cli_writes_a_derived_manifest_without_overwriting_source(tmp_path: Path) -> None:
    source = load_json_object(FIXTURES / "valid_complete_synthetic.json")
    for frame in source["frames"]:
        frame["split"] = "unassigned"
    manifest = write_manifest(tmp_path, source)
    assigned = tmp_path / "assigned.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
            "--config",
            str(CONFIG),
            "--repo-root",
            str(REPO),
            "--data-root",
            str(FIXTURES),
            "--assign-splits",
            str(assigned),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == EXIT_NOT_READY
    report = json.loads(completed.stdout)
    assert report["status"] == "NOT_READY"
    assert report["derived_manifest"]["path"] == str(assigned.resolve())
    assert load_json_object(manifest)["frames"][0]["split"] == "unassigned"
    assert all(frame["split"] != "unassigned" for frame in load_json_object(assigned)["frames"])


def test_existing_output_requires_explicit_overwrite_and_is_atomic(tmp_path: Path) -> None:
    output = tmp_path / "audit.json"
    original = CONFIG.read_bytes()
    output.write_bytes(original)
    original_sha = sha256(output)

    refused = run_cli(
        FIXTURES / "valid_complete_synthetic.json",
        FIXTURES,
        extra=("--output", str(output)),
    )

    assert refused.returncode == EXIT_INVALID
    assert output.read_bytes() == original
    assert sha256(output) == original_sha
    assert "without explicit --overwrite" in json.loads(refused.stderr)["error"]

    replaced = run_cli(
        FIXTURES / "valid_complete_synthetic.json",
        FIXTURES,
        extra=("--output", str(output), "--overwrite"),
    )

    assert replaced.returncode == EXIT_NOT_READY
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "NOT_READY"
    assert not list(tmp_path.glob(f".{output.name}.*.tmp"))


def test_existing_derived_manifest_requires_the_same_overwrite_flag(tmp_path: Path) -> None:
    source = load_json_object(FIXTURES / "valid_complete_synthetic.json")
    for frame in source["frames"]:
        frame["split"] = "unassigned"
    manifest = write_manifest(tmp_path, source)
    assigned = tmp_path / "assigned.json"
    original = b"derived-sentinel-must-survive"
    assigned.write_bytes(original)

    refused = run_cli(
        manifest,
        FIXTURES,
        extra=("--assign-splits", str(assigned)),
    )
    assert refused.returncode == EXIT_INVALID
    assert assigned.read_bytes() == original

    replaced = run_cli(
        manifest,
        FIXTURES,
        extra=("--assign-splits", str(assigned), "--overwrite"),
    )
    assert replaced.returncode == EXIT_NOT_READY
    assert all(frame["split"] != "unassigned" for frame in load_json_object(assigned)["frames"])
    assert not list(tmp_path.glob(f".{assigned.name}.*.tmp"))


def test_overwrite_never_allows_capture_source_or_target_collisions(tmp_path: Path) -> None:
    repo_root, config, schema, manifest, images = isolated_sources(tmp_path)
    protected = {
        "manifest": manifest,
        "config": config,
        "schema": schema,
        "image": images[0],
    }
    for role, target in protected.items():
        original_sha = sha256(target)
        completed = run_cli(
            manifest,
            manifest.parent,
            config=config,
            repo_root=repo_root,
            extra=("--output", str(target), "--overwrite"),
        )
        assert completed.returncode == EXIT_INVALID, role
        assert "protected capture input" in json.loads(completed.stderr)["error"]
        assert sha256(target) == original_sha, role

    derived_source_collision = run_cli(
        manifest,
        manifest.parent,
        config=config,
        repo_root=repo_root,
        extra=("--assign-splits", str(manifest), "--overwrite"),
    )
    assert derived_source_collision.returncode == EXIT_INVALID
    assert "protected capture input" in json.loads(derived_source_collision.stderr)[
        "error"
    ]

    manifest_alias = tmp_path / "manifest-alias.json"
    manifest_alias.symlink_to(manifest)
    manifest_sha = sha256(manifest)
    alias_collision = run_cli(
        manifest,
        manifest.parent,
        config=config,
        repo_root=repo_root,
        extra=("--output", str(manifest_alias), "--overwrite"),
    )
    assert alias_collision.returncode == EXIT_INVALID
    assert sha256(manifest) == manifest_sha
    assert manifest_alias.is_symlink()

    assigned = manifest.parent / "assigned.json"
    target_collision = run_cli(
        manifest,
        manifest.parent,
        config=config,
        repo_root=repo_root,
        extra=(
            "--assign-splits",
            str(assigned),
            "--output",
            str(assigned),
            "--overwrite",
        ),
    )
    assert target_collision.returncode == EXIT_INVALID
    assert "targets must be distinct" in json.loads(target_collision.stderr)["error"]
    assert not assigned.exists()


def test_rig_receipt_is_a_protected_source_even_with_overwrite(tmp_path: Path) -> None:
    repo_root, config, _, _, _ = isolated_sources(tmp_path / "isolated")
    manifest, _, receipt = write_real_scope_candidate_with_synthetic_receipt(
        tmp_path / "capture"
    )
    original_sha = sha256(receipt)

    completed = run_cli(
        manifest,
        manifest.parent,
        config=config,
        repo_root=repo_root,
        extra=("--output", str(receipt), "--overwrite"),
    )

    assert completed.returncode == EXIT_INVALID
    assert "protected capture input" in json.loads(completed.stderr)["error"]
    assert sha256(receipt) == original_sha


def test_invalid_escaping_references_remain_protected_publish_targets(
    tmp_path: Path,
) -> None:
    repo_root, config, _, manifest, _ = isolated_sources(tmp_path)
    payload = load_json_object(manifest)
    outside_image = manifest.parent.parent / "outside-image.jpg"
    outside_image.write_bytes(b"must-survive")
    payload["frames"][0]["image_path"] = "../outside-image.jpg"
    manifest.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    image_collision = run_cli(
        manifest,
        manifest.parent,
        config=config,
        repo_root=repo_root,
        extra=("--output", str(outside_image), "--overwrite"),
    )
    assert image_collision.returncode == EXIT_INVALID
    assert outside_image.read_bytes() == b"must-survive"

    outside_receipt = manifest.parent.parent / "outside-receipt.json"
    outside_receipt.write_bytes(b"receipt-must-survive")
    payload["frames"][0]["image_path"] = "images/frame_a1_000.jpg"
    payload["rig_acceptance"] = {
        "result_path": "../outside-receipt.json",
        "result_sha256": "0" * 64,
    }
    manifest.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    receipt_collision = run_cli(
        manifest,
        manifest.parent,
        config=config,
        repo_root=repo_root,
        extra=("--output", str(outside_receipt), "--overwrite"),
    )
    assert receipt_collision.returncode == EXIT_INVALID
    assert outside_receipt.read_bytes() == b"receipt-must-survive"


def test_cli_returns_invalid_exit_for_schema_failure() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(FIXTURES / "missing_metadata_synthetic.json"),
            "--config",
            str(CONFIG),
            "--repo-root",
            str(REPO),
            "--data-root",
            str(FIXTURES),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == EXIT_INVALID
    assert json.loads(completed.stdout)["status"] == "INVALID"


def test_paths_and_deferred_keypoints_are_rejected(tmp_path: Path) -> None:
    path_payload = load_json_object(FIXTURES / "valid_complete_synthetic.json")
    path_payload["frames"][0]["image_path"] = "../outside.jpg"
    path_report = audit_capture(
        write_manifest(tmp_path, path_payload), CONFIG, data_root=FIXTURES, repo_root=REPO
    )

    keypoint_payload = load_json_object(FIXTURES / "valid_complete_synthetic.json")
    keypoint_payload["frames"][0]["instances"][0]["keypoints"] = [[0.1, 0.2]]
    keypoint_report = audit_capture(
        write_manifest(tmp_path, keypoint_payload), CONFIG, data_root=FIXTURES, repo_root=REPO
    )

    assert path_report["status"] == "INVALID"
    assert "image.path_traversal" in error_codes(path_report)
    assert keypoint_report["status"] == "INVALID"
    assert "schema.additional_property" in error_codes(keypoint_report)


def test_annotation_semantics_require_eligible_canopy_measurement(tmp_path: Path) -> None:
    payload = load_json_object(FIXTURES / "valid_complete_synthetic.json")
    payload["frames"][0]["instances"][0]["canopy_span_mm"] = None
    report = audit_capture(
        write_manifest(tmp_path, payload), CONFIG, data_root=FIXTURES, repo_root=REPO
    )

    assert report["status"] == "INVALID"
    assert "annotation.eligible_canopy_span_missing" in error_codes(report)


def test_known_class_conflict_on_one_track_is_rejected(tmp_path: Path) -> None:
    payload = load_json_object(FIXTURES / "valid_complete_synthetic.json")
    payload["frames"][1]["instances"][0]["class_name"] = "crop"
    report = audit_capture(
        write_manifest(tmp_path, payload), CONFIG, data_root=FIXTURES, repo_root=REPO
    )

    assert report["status"] == "INVALID"
    assert "track.class_conflict" in error_codes(report)


def test_non_deterministic_manual_field_assignment_is_rejected(tmp_path: Path) -> None:
    payload = load_json_object(FIXTURES / "valid_complete_synthetic.json")
    changed = copy.deepcopy(payload)
    for frame in changed["frames"]:
        if frame["field_id"] == "field_a":
            frame["split"] = "train"
        elif frame["field_id"] == "field_c":
            frame["split"] = "validation"
    report = audit_capture(
        write_manifest(tmp_path, changed), CONFIG, data_root=FIXTURES, repo_root=REPO
    )

    assert report["status"] == "INVALID"
    assert "split.non_deterministic_assignment" in error_codes(report)


def test_one_field_relabel_and_placeholder_bytes_never_unlock_ready(tmp_path: Path) -> None:
    payload = load_json_object(FIXTURES / "valid_complete_synthetic.json")
    payload["evidence_scope"] = "real_target_rig"
    manifest = write_manifest(tmp_path, payload)

    report = audit_capture(manifest, CONFIG, data_root=FIXTURES, repo_root=REPO)
    completed = run_cli(manifest, FIXTURES)

    assert report["status"] == "INVALID"
    assert report["ready"] is False
    assert report["evidence"]["counts_as_real_target_rig_evidence"] is False
    assert "image.content_invalid" in error_codes(report)
    assert completed.returncode == EXIT_INVALID


def test_synthetic_rig_evaluation_cannot_authorize_real_collection(tmp_path: Path) -> None:
    manifest, _, _ = write_real_scope_candidate_with_synthetic_receipt(tmp_path)

    report = audit_capture(manifest, CONFIG, data_root=tmp_path, repo_root=REPO)
    completed = run_cli(manifest, tmp_path)

    assert report["valid"] is True
    assert report["status"] == "NOT_READY"
    assert report["ready"] is False
    assert report["integrity"]["rig_acceptance"]["status"] == "NOT_READY"
    assert report["integrity"]["rig_acceptance"]["physical_collection_allowed"] is False
    assert "readiness.rig_acceptance_not_physical" in readiness_codes(report)
    assert report["evidence"]["counts_as_real_target_rig_evidence"] is False
    assert completed.returncode == EXIT_NOT_READY


def test_missing_or_unmeasured_rig_acceptance_remains_not_ready(tmp_path: Path) -> None:
    manifest, payload, result_path = write_real_scope_candidate_with_synthetic_receipt(tmp_path)
    del payload["rig_acceptance"]
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    missing_report = audit_capture(manifest, CONFIG, data_root=tmp_path, repo_root=REPO)

    result = load_json_object(result_path)
    result["stage_results"]["C_optics_and_window"] = {
        "measurement_status": "not_measured",
        "status": "NOT_MEASURED",
    }
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    payload["rig_acceptance"] = {
        "result_path": result_path.name,
        "result_sha256": sha256(result_path),
    }
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    unmeasured_report = audit_capture(manifest, CONFIG, data_root=tmp_path, repo_root=REPO)

    assert missing_report["status"] == "NOT_READY"
    assert "readiness.rig_acceptance_missing" in readiness_codes(missing_report)
    assert unmeasured_report["status"] == "NOT_READY"
    assert "readiness.rig_acceptance_stages_not_pass" in readiness_codes(
        unmeasured_report
    )


def test_mutated_image_bytes_fail_declared_sha256_and_cli(tmp_path: Path) -> None:
    manifest, payload, _ = write_real_scope_candidate_with_synthetic_receipt(tmp_path)
    image_path = tmp_path / payload["frames"][0]["image_path"]
    image_path.write_bytes(image_path.read_bytes() + b"post-manifest-mutation")

    report = audit_capture(manifest, CONFIG, data_root=tmp_path, repo_root=REPO)
    completed = run_cli(manifest, tmp_path)

    assert report["status"] == "INVALID"
    assert "image.sha256_mismatch" in error_codes(report)
    assert report["evidence"]["counts_as_real_target_rig_evidence"] is False
    assert completed.returncode == EXIT_INVALID


def test_missing_frozen_real_metadata_is_not_ready_not_success(tmp_path: Path) -> None:
    manifest, payload, _ = write_real_scope_candidate_with_synthetic_receipt(tmp_path)
    del payload["frames"][0]["white_balance"]
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    report = audit_capture(manifest, CONFIG, data_root=tmp_path, repo_root=REPO)
    completed = run_cli(manifest, tmp_path)

    assert report["valid"] is True
    assert report["status"] == "NOT_READY"
    assert "readiness.real_capture_metadata_missing" in readiness_codes(report)
    assert report["evidence"]["counts_as_real_target_rig_evidence"] is False
    assert completed.returncode == EXIT_NOT_READY


def test_acceptance_result_hash_drift_is_invalid_and_not_success(tmp_path: Path) -> None:
    manifest, _, result_path = write_real_scope_candidate_with_synthetic_receipt(tmp_path)
    result_path.write_text(result_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    report = audit_capture(manifest, CONFIG, data_root=tmp_path, repo_root=REPO)
    completed = run_cli(manifest, tmp_path)

    assert report["status"] == "INVALID"
    assert "rig_acceptance.sha256_mismatch" in error_codes(report)
    assert report["evidence"]["counts_as_real_target_rig_evidence"] is False
    assert completed.returncode == EXIT_INVALID


def test_acceptance_result_path_escape_is_invalid(tmp_path: Path) -> None:
    manifest, payload, _ = write_real_scope_candidate_with_synthetic_receipt(tmp_path)
    payload["rig_acceptance"]["result_path"] = "../outside.json"
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    report = audit_capture(manifest, CONFIG, data_root=tmp_path, repo_root=REPO)

    assert report["status"] == "INVALID"
    assert "rig_acceptance.path_traversal" in error_codes(report)


def test_real_camera_counter_and_profile_integrity_are_fail_closed(tmp_path: Path) -> None:
    manifest, payload, _ = write_real_scope_candidate_with_synthetic_receipt(tmp_path)
    payload["frames"][1]["camera_frame_counter"] = 1003
    payload["frames"][1]["camera_timestamp_ns"] = payload["frames"][0][
        "camera_timestamp_ns"
    ]
    payload["frames"][1]["strobe_settings"]["pulse_width_us"] = 160.0
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    report = audit_capture(manifest, CONFIG, data_root=tmp_path, repo_root=REPO)

    assert report["status"] == "INVALID"
    assert {
        "video.frame_counter_delta_mismatch",
        "video.camera_timestamp_not_increasing",
        "metadata.capture_profile_drift",
    } <= error_codes(report)


def test_positive_collection_decision_on_synthetic_result_is_inconsistent(
    tmp_path: Path,
) -> None:
    manifest, payload, result_path = write_real_scope_candidate_with_synthetic_receipt(tmp_path)
    result = load_json_object(result_path)
    result["decision"]["controlled_data_collection_allowed"] = True
    result["decision"]["deployment_evidence_eligible"] = True
    result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    payload["rig_acceptance"]["result_sha256"] = sha256(result_path)
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    report = audit_capture(manifest, CONFIG, data_root=tmp_path, repo_root=REPO)

    assert report["status"] == "INVALID"
    assert "rig_acceptance.content_inconsistent" in error_codes(report)
