#!/usr/bin/env python3
"""Finalize CamelinaWeed from the frozen automated and manual gate artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agri_seg.constants import IGNORE, WEED
from agri_seg.manifest import mask_tree_sha256, read_manifest


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return value


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def resolve(project_root: Path, recorded: str) -> Path:
    path = Path(recorded).expanduser()
    return (path if path.is_absolute() else project_root / path).resolve()


def validate_duplicate_audit(
    audit: dict[str, Any], expected_candidate: int, expected_reference: int
) -> dict[str, int | bool | dict[str, int | float]]:
    scope = audit["scope"]
    exact_within = sum(
        bool(match["sha256_exact"]) for match in audit["within_candidate_matches"]
    )
    checks: dict[str, int | bool | dict[str, int | float]] = {
        "candidate_samples": int(scope["candidate_samples"]),
        "reference_samples": int(scope["reference_samples"]),
        "candidate_to_reference_matches": int(audit["candidate_to_reference_match_count"]),
        "within_candidate_exact_duplicates": exact_within,
        "within_candidate_near_pairs": int(audit["within_candidate_match_count"]),
        "cross_role_exact_or_near_duplicates": int(audit["within_candidate_cross_split_match_count"]),
        "nearest_reference_hamming": dict(audit["candidate_to_reference_nearest_hamming"]),
        "audit_passed": bool(audit["passed"]),
    }
    require_equal("duplicate candidate samples", checks["candidate_samples"], expected_candidate)
    require_equal("duplicate reference samples", checks["reference_samples"], expected_reference)
    require_equal("candidate/reference exact or near matches", checks["candidate_to_reference_matches"], 0)
    require_equal("within-candidate exact duplicates", exact_within, 0)
    require_equal("cross-role exact or near duplicates", checks["cross_role_exact_or_near_duplicates"], 0)
    require_equal("duplicate audit passed", checks["audit_passed"], True)
    return checks


def finalize(gate_path: Path) -> Path:
    gate_path = gate_path.expanduser().resolve()
    project_root = gate_path.parents[2]
    gate = load_yaml(gate_path)
    gate_hash = sha256(gate_path)
    expected = gate["expected_release"]
    quality = gate["quality_gate"]
    outputs = gate["outputs"]
    data_root = resolve(project_root, str(gate["data_root"]))

    conversion_path = resolve(project_root, str(outputs["conversion_receipt"]))
    content_path = resolve(project_root, str(outputs["content_audit"]))
    duplicate_path = resolve(project_root, str(outputs["duplicate_audit"]))
    contact_path = resolve(project_root, str(outputs["contact_sheet"]))
    contact_receipt_path = resolve(project_root, str(outputs["contact_sheet_receipt"]))
    final_path = resolve(project_root, str(outputs["final_quality_receipt"]))
    for path in (conversion_path, content_path, duplicate_path, contact_path, contact_receipt_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    conversion = load_json(conversion_path)
    content = load_json(content_path)
    duplicate = load_json(duplicate_path)
    contact = load_json(contact_receipt_path)
    require_equal("conversion status", conversion["status"], "verified")
    require_equal("conversion gate SHA", conversion["gate_config_sha256"], gate_hash)
    require_equal("content gate SHA", content["gate_config_sha256"], gate_hash)
    require_equal("conversion content SHA", conversion["content_audit_sha256"], sha256(content_path))
    require_equal("automated content gate", content["automated_content_gate_passed"], True)
    require_equal("content external-test use", content["external_test_used"], False)
    require_equal("content model-selection use", content["model_selection_used"], False)
    require_equal("content common-model permission", content["common_three_class_training_allowed"], False)
    require_equal("content partial-objective permission", content["positive_only_partial_label_training_allowed"], False)
    converter_path = Path(str(conversion["converter"])).resolve()
    require_equal("converter self-lock", conversion["converter_sha256"], sha256(converter_path))
    require_equal("content converter lock", content["converter_sha256"], sha256(converter_path))

    derived_manifests = conversion["derived"]["manifests"]
    manifest_path = Path(str(derived_manifests["all"]["path"])).resolve()
    train_path = Path(str(derived_manifests["train_candidate"]["path"])).resolve()
    calibration_path = Path(str(derived_manifests["external_calibration"]["path"])).resolve()
    require_equal("all manifest path", manifest_path, resolve(project_root, str(outputs["manifest"])))
    require_equal("train manifest path", train_path, resolve(project_root, str(outputs["train_manifest"])))
    require_equal("calibration manifest path", calibration_path, resolve(project_root, str(outputs["calibration_manifest"])))
    for name, path in (("all", manifest_path), ("train_candidate", train_path), ("external_calibration", calibration_path)):
        require_equal(f"{name} manifest SHA", derived_manifests[name]["sha256"], sha256(path))
    records = read_manifest(manifest_path)
    train_records = read_manifest(train_path)
    calibration_records = read_manifest(calibration_path)
    require_equal("all manifest samples", len(records), int(expected["accepted_images"]))
    require_equal("train manifest samples", len(train_records), int(expected["train_images"]))
    require_equal("calibration manifest samples", len(calibration_records), int(expected["external_calibration_images"]))
    require_equal("dataset IDs", {record.dataset_id for record in records}, {gate["dataset_id"]})
    require_equal("annotation exhaustiveness", {record.annotation_exhaustive for record in records}, {False})
    require_equal("manifest split counts", dict(Counter(record.split for record in records)), {"train": int(expected["train_images"]), "external_calibration": int(expected["external_calibration_images"])})
    require_equal("external-test rows", sum(record.split == "external_test" for record in records), 0)
    require_equal(
        "train/calibration field overlap",
        len({record.field_id for record in train_records} & {record.field_id for record in calibration_records}),
        int(expected["train_calibration_location_overlap"]),
    )
    mask_hash = mask_tree_sha256(records, data_root)
    require_equal("derived mask tree SHA", conversion["derived"]["normalized_partial_mask_tree_sha256"], mask_hash)
    require_equal("content mask tree SHA", content["partial_mask"]["mask_tree_sha256"], mask_hash)
    require_equal("partial-mask palette", content["partial_mask"]["palette"], [WEED, IGNORE])
    require_equal("content accepted images", content["counts"]["manifest_images"], int(expected["accepted_images"]))
    require_equal("content canonical images", content["counts"]["canonical_images"], int(expected["canonical_images"]))
    require_equal("content annotations", content["counts"]["canonical_annotations"], int(expected["canonical_annotations"]))
    require_equal("content accepted annotations", content["counts"]["accepted_positive_annotations"], int(expected["accepted_positive_annotations"]))
    require_equal("content ignored empty", content["counts"]["ignored_empty_annotations"], int(expected["empty_segmentation_annotations_to_ignore"]))
    require_equal("content ignored k", content["counts"]["ignored_ambiguous_k_annotations"], int(expected["ambiguous_category_k_annotations_to_ignore"]))
    require_equal("content excluded images", content["counts"]["excluded_images_without_accepted_positive"], int(expected["images_without_accepted_positive_to_exclude"]))

    duplicate_script = (project_root / "scripts/audit_candidate_duplicates.py").resolve()
    require_equal("duplicate script lock", duplicate["script_sha256"], sha256(duplicate_script))
    require_equal("duplicate candidate manifest", Path(str(duplicate["scope"]["candidate_manifest"])).resolve(), manifest_path)
    require_equal("duplicate candidate manifest SHA", duplicate["scope"]["candidate_manifest_sha256"], sha256(manifest_path))
    require_equal("duplicate Hamming threshold", duplicate["max_hamming"], int(quality["require_near_duplicate_hamming_threshold"]))
    duplicate_checks = validate_duplicate_audit(
        duplicate,
        int(expected["accepted_images"]),
        int(quality["existing_real_reference_count"]),
    )

    require_equal("contact gate SHA", contact["gate_config_sha256"], gate_hash)
    require_equal("contact manifest", Path(str(contact["manifest"])).resolve(), manifest_path)
    require_equal("contact manifest SHA", contact["manifest_sha256"], sha256(manifest_path))
    require_equal("contact samples", contact["samples"], int(expected["accepted_images"]))
    require_equal("contact quantiles", contact["quantiles"], [float(value) for value in quality["manual_sample_quantiles"]])
    require_equal("contact group count", len(contact["group_counts"]), len(gate["canonical_groups"]))
    expected_group_counts = {str(group["id"]): int(group["accepted_images"]) for group in gate["canonical_groups"]}
    require_equal("contact group inventory", contact["group_counts"], expected_group_counts)
    require_equal("contact selected samples", contact["selected_samples"], len(expected_group_counts) * len(contact["quantiles"]))
    require_equal("contact manual verdict", contact["manual_review"]["verdict"], "pass")
    if not str(contact["manual_review"]["note"]).strip():
        raise ValueError("Manual review pass requires a non-empty note")
    require_equal("contact-sheet SHA", contact["contact_sheet_sha256"], sha256(contact_path))
    contact_script = Path(str(contact["script"])).resolve()
    require_equal("contact script lock", contact["script_sha256"], sha256(contact_script))
    require_equal("contact detail-page count", len(contact["detail_pages"]), len(expected_group_counts))
    for page in contact["detail_pages"]:
        page_path = Path(str(page["path"])).resolve()
        require_equal(f"contact detail SHA {page_path}", page["sha256"], sha256(page_path))
    expected_contact_keys = {
        (group_id, float(quantile))
        for group_id in expected_group_counts
        for quantile in contact["quantiles"]
    }
    actual_contact_keys = {(str(row["group_id"]), float(row["quantile"])) for row in contact["rows"]}
    require_equal("contact row inventory", actual_contact_keys, expected_contact_keys)

    locked_receipt_spec = gate["locked_inputs"]["annotated_range_receipt"]
    acquisition_path = resolve(project_root, str(locked_receipt_spec["path"]))
    require_equal("locked acquisition receipt SHA", sha256(acquisition_path), str(locked_receipt_spec["sha256"]))
    acquisition = load_json(acquisition_path)
    require_equal("acquisition status", acquisition["status"], "verified")
    require_equal("acquisition mode", acquisition["mode"], "annotated")
    require_equal("acquisition ZIP CRC", acquisition["zip_crc_verified_by_read"], True)
    require_equal("acquisition external-test use", acquisition["external_test_used"], False)
    require_equal("acquisition model-selection use", acquisition["model_selection_used"], False)

    final = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": gate["dataset_id"],
        "all_quality_gates_passed": True,
        "gate_config": str(gate_path),
        "gate_config_sha256": gate_hash,
        "acquisition": {
            "receipt": str(acquisition_path),
            "receipt_sha256": sha256(acquisition_path),
            "selected_files": int(acquisition["extraction"]["files"]),
            "selected_bytes": int(acquisition["extraction"]["bytes"]),
            "selected_tree_sha256": acquisition["extraction"]["tree_sha256"],
            "zip_crc_verified_by_read": True,
        },
        "conversion": {
            "receipt": str(conversion_path),
            "receipt_sha256": sha256(conversion_path),
            "content_audit": str(content_path),
            "content_audit_sha256": sha256(content_path),
            "automated_content_gate_passed": True,
        },
        "duplicates": {
            "audit": str(duplicate_path),
            "audit_sha256": sha256(duplicate_path),
            **duplicate_checks,
        },
        "manual_visual_review": {
            "contact_sheet": str(contact_path),
            "contact_sheet_sha256": sha256(contact_path),
            "receipt": str(contact_receipt_path),
            "receipt_sha256": sha256(contact_receipt_path),
            "verdict": "pass",
            "note": contact["manual_review"]["note"],
            "selected_samples": int(contact["selected_samples"]),
            "detail_pages": contact["detail_pages"],
        },
        "samples": len(records),
        "split_counts": dict(sorted(Counter(record.split for record in records).items())),
        "groups": len(expected_group_counts),
        "locations": sorted({record.field_id for record in records}),
        "normalized_partial_mask_tree_sha256": mask_hash,
        "source_manifest_image_tree_sha256": content["source_manifest_image_tree_sha256"],
        "positive_coverage_fraction": content["partial_mask"]["positive_coverage_fraction"],
        "ontology": content["ontology"],
        "usage_policy": {
            "common_three_class_training_allowed": False,
            "positive_only_partial_label_training_allowed": False,
            "all_non_polygon_pixels_are_ignore": True,
            "external_calibration_is_not_external_test": True,
            "training_unlock_requires": conversion["usage_policy"]["unlock_requires"],
        },
        "external_test_used": False,
        "model_selection_used": False,
        "finalizer": str(Path(__file__).resolve()),
        "finalizer_sha256": sha256(Path(__file__).resolve()),
    }
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return final_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-config", type=Path, default=Path("configs/data/camelinaweed_partial_label_gate_v1.yaml"))
    arguments = parser.parse_args()
    output = finalize(arguments.gate_config)
    print(json.dumps({"quality_receipt": str(output), "sha256": sha256(output)}, indent=2))


if __name__ == "__main__":
    main()
