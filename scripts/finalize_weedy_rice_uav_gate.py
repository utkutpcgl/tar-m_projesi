#!/usr/bin/env python3
"""Finalize the Weedy Rice UAV quality gate from locked audit artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agri_seg.manifest import read_manifest


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


def validate_duplicate_audit(
    audit: dict[str, Any], expected_candidate: int, expected_reference: int
) -> dict[str, int | bool]:
    scope = audit["scope"]
    exact_within = sum(
        bool(match["sha256_exact"])
        for match in audit["within_candidate_matches"]
    )
    checks: dict[str, int | bool] = {
        "candidate_samples": int(scope["candidate_samples"]),
        "reference_samples": int(scope["reference_samples"]),
        "candidate_to_reference_matches": int(
            audit["candidate_to_reference_match_count"]
        ),
        "within_candidate_exact_duplicates": exact_within,
        "cross_role_exact_or_near_duplicates": int(
            audit["within_candidate_cross_split_match_count"]
        ),
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
    data_root = Path(str(gate["data_root"])).expanduser().resolve()
    outputs = gate["outputs"]
    conversion_path = (data_root / str(outputs["conversion_receipt"])).resolve()
    content_path = (data_root / str(outputs["content_audit"])).resolve()
    duplicate_path = (data_root / str(outputs["duplicate_audit"])).resolve()
    contact_path = (data_root / str(outputs["contact_sheet"])).resolve()
    contact_receipt_path = (data_root / str(outputs["contact_sheet_receipt"])).resolve()
    final_path = (data_root / str(outputs["quality_audit"])).resolve()
    for path in (
        conversion_path,
        content_path,
        duplicate_path,
        contact_path,
        contact_receipt_path,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    conversion = load_json(conversion_path)
    content = load_json(content_path)
    duplicate = load_json(duplicate_path)
    contact = load_json(contact_receipt_path)
    require_equal("conversion gate config SHA", conversion["gate_config_sha256"], sha256(gate_path))
    require_equal("content gate config SHA", content["gate_config_sha256"], sha256(gate_path))
    require_equal("conversion content-audit SHA", conversion["content_audit_sha256"], sha256(content_path))
    require_equal("automated content gate", content["automated_content_gate_passed"], True)
    require_equal("content external test", content["external_test_used"], False)
    require_equal("content model selection", content["model_selection_used"], False)
    converter_path = Path(str(conversion["converter"])).resolve()
    require_equal("converter self-lock", conversion["converter_sha256"], sha256(converter_path))

    manifest_path = Path(
        str(conversion["derived"]["binary_manifest"]["path"])
    ).resolve()
    require_equal(
        "binary manifest SHA",
        conversion["derived"]["binary_manifest"]["sha256"],
        sha256(manifest_path),
    )
    records = read_manifest(manifest_path)
    require_equal("manifest samples", len(records), int(gate["expected_release"]["rgb_images"]))
    require_equal("manifest datasets", {record.dataset_id for record in records}, {gate["manifest_dataset_id"]})
    require_equal("manifest annotation exhaustiveness", {record.annotation_exhaustive for record in records}, {False})
    require_equal("manifest external-test rows", sum(record.split == "external_test" for record in records), 0)

    duplicate_script = (project_root / "scripts/audit_candidate_duplicates.py").resolve()
    require_equal("duplicate script lock", duplicate["script_sha256"], sha256(duplicate_script))
    require_equal("duplicate candidate manifest", Path(duplicate["scope"]["candidate_manifest"]).resolve(), manifest_path)
    require_equal("duplicate candidate manifest SHA", duplicate["scope"]["candidate_manifest_sha256"], sha256(manifest_path))
    duplicate_checks = validate_duplicate_audit(
        duplicate,
        int(gate["expected_release"]["rgb_images"]),
        int(gate["quality_gate"]["require_reference_samples"]),
    )

    require_equal("contact-sheet manifest", Path(contact["manifest"]).resolve(), manifest_path)
    require_equal("contact-sheet manifest SHA", contact["manifest_sha256"], sha256(manifest_path))
    require_equal("contact-sheet SHA", contact["contact_sheet_sha256"], sha256(contact_path))
    require_equal("contact capture sessions", contact["capture_sessions"], 4)
    require_equal("contact manual verdict", contact["manual_review"]["verdict"], "pass")
    require_equal("contact dataset", contact["dataset_id"], gate["manifest_dataset_id"])
    contact_script = Path(str(contact["script"])).resolve()
    require_equal("contact script lock", contact["script_sha256"], sha256(contact_script))
    require_equal("contact detail-page count", len(contact["detail_pages"]), 4)
    for page in contact["detail_pages"]:
        page_path = Path(str(page["path"])).resolve()
        require_equal(f"contact detail-page SHA {page_path}", page["sha256"], sha256(page_path))
    expected_contact_bins = {
        key.removesuffix("_percent"): int(value)
        for key, value in gate["expected_mask_coverage_bins"].items()
        if key not in {"mean_percent_reference", "mean_percent_absolute_tolerance"}
    }
    require_equal("contact coverage-bin inventory", contact["coverage_bins"], expected_contact_bins)
    if int(contact["selected_cells"]) < 4:
        raise ValueError("Contact sheet does not cover all capture sessions")

    acquisition_path = (
        project_root / str(gate["locked_inputs"]["acquisition_receipt"])
    ).resolve()
    acquisition = load_json(acquisition_path)
    require_equal("acquisition status", acquisition["status"], "verified")
    require_equal("outer CRC", acquisition["outer_archive"]["full_crc_passed"], True)
    require_equal("nested CRC", acquisition["nested_archive"]["full_crc_passed"], True)

    final = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset_id": gate["manifest_dataset_id"],
        "all_quality_gates_passed": True,
        "gate_config": str(gate_path),
        "gate_config_sha256": sha256(gate_path),
        "acquisition": {
            "receipt": str(acquisition_path),
            "receipt_sha256": sha256(acquisition_path),
            "outer_archive_sha256": acquisition["outer_archive"]["sha256"],
            "nested_archive_sha256": acquisition["nested_archive"]["sha256"],
            "full_crc_passed": True,
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
            "same_role_near_pairs_reported_not_rejected": int(
                duplicate["within_candidate_same_split_match_count"]
            ),
        },
        "manual_visual_review": {
            "contact_sheet": str(contact_path),
            "contact_sheet_sha256": sha256(contact_path),
            "receipt": str(contact_receipt_path),
            "receipt_sha256": sha256(contact_receipt_path),
            "verdict": "pass",
            "note": contact["manual_review"]["note"],
            "selected_cells": int(contact["selected_cells"]),
            "detail_pages": contact["detail_pages"],
        },
        "samples": len(records),
        "split_counts": dict(content["split_counts"]),
        "capture_event_counts": dict(content["capture_event_counts"]),
        "capture_group_count": int(content["capture_group_count"]),
        "derived": conversion["derived"],
        "ontology": content["ontology"],
        "publisher_split_rejected": content["publisher_split_rejected"],
        "article_metadata_time_discrepancy": content["metadata"][
            "article_metadata_time_discrepancy"
        ],
        "external_test_used": False,
        "model_selection_used": False,
        "common_model_training_allowed": False,
        "training_unlock_requires": load_yaml(
            (project_root / gate["locked_inputs"]["split_protocol"]["path"]).resolve()
        )["usage_policy"]["training_unlock_requires"],
        "finalizer": str(Path(__file__).resolve()),
        "finalizer_sha256": sha256(Path(__file__).resolve()),
    }
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_text(json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return final_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gate-config",
        type=Path,
        default=Path("configs/data/weedy_rice_uav_real_gate_v1.yaml"),
    )
    arguments = parser.parse_args()
    output = finalize(arguments.gate_config)
    print(json.dumps({"quality_audit": str(output), "sha256": sha256(output)}, indent=2))


if __name__ == "__main__":
    main()
