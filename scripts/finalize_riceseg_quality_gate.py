#!/usr/bin/env python3
"""Finalize RiceSEG training eligibility after visual and duplicate gates."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image

from agri_seg.manifest import (
    SampleRecord,
    manifest_sha256,
    mask_tree_sha256,
    read_manifest,
    write_manifest,
)
from agri_seg.prepare import _difference_hash


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return value


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def require_inside(path: Path, root: Path, name: str) -> Path:
    resolved = path.expanduser().resolve()
    try:
        resolved.relative_to(root.expanduser().resolve())
    except ValueError as exc:
        raise ValueError(f"{name} must remain below data_root: {resolved}") from exc
    return resolved


def locked_path(root: Path, specification: dict[str, Any], name: str) -> Path:
    path = require_inside(root / str(specification["path"]), root, name)
    if not path.is_file():
        raise FileNotFoundError(path)
    require_equal(f"{name} SHA-256", sha256(path), str(specification["sha256"]))
    return path


def resolve_image(record: SampleRecord, data_root: Path) -> Path:
    path = Path(record.image_path)
    result = (path if path.is_absolute() else data_root / path).resolve()
    if not result.is_file():
        raise FileNotFoundError(result)
    return result


def resolve_mask(record: SampleRecord, data_root: Path) -> Path:
    path = Path(record.mask_path)
    result = (path if path.is_absolute() else data_root / path).resolve()
    if not result.is_file():
        raise FileNotFoundError(result)
    return result


def decoded_difference(left: Path, right: Path, mode: str) -> dict[str, float | int | bool]:
    with Image.open(left) as handle:
        left_array = np.asarray(handle.convert(mode), dtype=np.uint8)
    with Image.open(right) as handle:
        right_array = np.asarray(handle.convert(mode), dtype=np.uint8)
    require_equal("decoded duplicate shapes", left_array.shape, right_array.shape)
    difference = left_array.astype(np.int16) - right_array.astype(np.int16)
    absolute = np.abs(difference)
    return {
        "array_equal": bool(np.array_equal(left_array, right_array)),
        "max_abs": int(absolute.max()),
        "mae": float(absolute.mean()),
        "different_values": int(np.count_nonzero(difference)),
        "total_values": int(difference.size),
    }


def validate_visual_review(
    path: Path, visual: dict[str, Any], contract: dict[str, Any], coverage_sha: str
) -> None:
    require_equal("visual dataset", visual.get("dataset_id"), "riceseg")
    require_equal("visual manifest SHA-256", visual.get("manifest_sha256"), coverage_sha)
    require_equal("visual subdatasets", int(visual["subdatasets"]), int(contract["visual_subdatasets"]))
    require_equal("visual reviewed cells", int(visual["reviewed_cells"]), int(contract["visual_reviewed_cells"]))
    require_equal("visual mapping reverified", visual.get("full_manifest_mapping_reverified"), True)
    require_equal("manual visual verdict", visual["manual_review"].get("verdict"), "pass")
    contact = Path(str(visual["contact_sheet"])).expanduser().resolve()
    if not contact.is_file():
        raise FileNotFoundError(contact)
    require_equal("contact-sheet SHA-256", sha256(contact), visual["contact_sheet_sha256"])
    pages = visual["detail_pages"]
    require_equal("visual detail pages", len(pages), int(contract["visual_subdatasets"]))
    for page in pages:
        page_path = Path(str(page["path"])).expanduser().resolve()
        if not page_path.is_file():
            raise FileNotFoundError(page_path)
        require_equal(
            f"detail-page SHA-256 {page['subdataset']}", sha256(page_path), page["sha256"]
        )
    if path.stat().st_size <= 0:
        raise ValueError("Empty visual-review receipt")


def duplicate_pair_payload(audit: dict[str, Any]) -> dict[str, Any]:
    matches = audit["within_candidate_matches"]
    require_equal("within-candidate duplicate entries", len(matches), 1)
    value = matches[0]
    if not isinstance(value, dict):
        raise ValueError("Invalid within-candidate duplicate entry")
    return value


def output_manifest(
    records: list[SampleRecord], path: Path, data_root: Path
) -> dict[str, Any]:
    write_manifest(records, path)
    return {
        "path": str(path),
        "samples": len(records),
        "role_counts": dict(Counter(record.split for record in records)),
        "sha256": manifest_sha256(path),
        "mask_tree_sha256": mask_tree_sha256(records, data_root),
    }


def finalize(config_path: Path) -> Path:
    config_path = config_path.expanduser().resolve()
    config = load_yaml(config_path)
    require_equal("quality schema", config.get("schema_version"), 1)
    freeze = config["freeze"]
    require_equal("source files deleted", freeze.get("source_files_deleted"), False)
    require_equal("split changed", freeze.get("split_changed_from_metadata_gate"), False)
    require_equal("model results used", freeze.get("model_results_used"), False)
    require_equal("external test created", freeze.get("external_test_created"), False)

    data_root = Path(str(config["data_root"])).expanduser().resolve()
    locked = config["locked_inputs"]
    locked_paths = {
        name: locked_path(data_root, specification, name.replace("_", " "))
        for name, specification in locked.items()
    }
    conversion = load_json(locked_paths["conversion_receipt"])
    audit = load_json(locked_paths["duplicate_audit"])
    visual = load_json(locked_paths["visual_review"])
    contract = config["quality_contract"]
    require_equal("conversion status", conversion.get("status"), "verified")
    require_equal("conversion pass", conversion.get("passed"), True)
    require_equal(
        "conversion samples",
        int(conversion["samples"]),
        int(contract["release_samples_preserved"]),
    )
    coverage_sha = str(locked["coverage_manifest"]["sha256"])
    require_equal(
        "conversion coverage SHA-256",
        conversion["manifests"]["coverage"]["sha256"],
        coverage_sha,
    )
    validate_visual_review(
        locked_paths["visual_review"], visual, contract, coverage_sha
    )

    require_equal("duplicate audit pass", audit.get("passed"), True)
    require_equal(
        "duplicate reference samples",
        int(audit["scope"]["reference_samples"]),
        int(contract["reference_samples"]),
    )
    require_equal(
        "candidate-to-reference matches",
        int(audit["candidate_to_reference_match_count"]),
        int(contract["candidate_to_reference_matches"]),
    )
    require_equal(
        "cross-split matches",
        int(audit["within_candidate_cross_split_match_count"]),
        int(contract["cross_split_matches"]),
    )
    require_equal(
        "allowed same-split matches",
        int(audit["within_candidate_same_split_match_count"]),
        int(contract["allowed_same_split_matches"]),
    )
    pair = duplicate_pair_payload(audit)
    pair_contract = contract["allowed_same_split_pair"]
    expected_ids = {
        str(pair_contract["keep_sample"]), str(pair_contract["quarantine_sample"])
    }
    require_equal(
        "same-split duplicate IDs",
        {str(pair["candidate"]), str(pair["reference"])},
        expected_ids,
    )
    require_equal("same-split duplicate role", pair["candidate_split"], pair["reference_split"])
    require_equal(
        "same-split dHash distance",
        int(pair["dhash_hamming"]),
        int(pair_contract["expected_dhash_hamming"]),
    )
    require_equal("same-split SHA exact", pair["sha256_exact"], False)

    full_records = read_manifest(locked_paths["coverage_manifest"])
    require_equal("full release manifest samples", len(full_records), int(contract["release_samples_preserved"]))
    by_id = {record.sample_id: record for record in full_records}
    require_equal("full release manifest unique IDs", len(by_id), len(full_records))
    keep_id = str(pair_contract["keep_sample"])
    quarantine_id = str(pair_contract["quarantine_sample"])
    if keep_id >= quarantine_id:
        raise ValueError("Duplicate keep decision is not the lexicographically first sample")
    keep = by_id[keep_id]
    quarantined = by_id[quarantine_id]
    require_equal("duplicate split", keep.split, quarantined.split)
    require_equal("duplicate field", keep.field_id, quarantined.field_id)
    require_equal("quarantine is training-only", quarantined.split, "train")
    left_image = resolve_image(keep, data_root)
    right_image = resolve_image(quarantined, data_root)
    actual_dhash = (_difference_hash(left_image) ^ _difference_hash(right_image)).bit_count()
    require_equal(
        "recomputed duplicate dHash",
        actual_dhash,
        int(pair_contract["expected_dhash_hamming"]),
    )
    rgb_difference = decoded_difference(left_image, right_image, "RGB")
    if float(rgb_difference["mae"]) > float(pair_contract["maximum_decoded_rgb_mae"]):
        raise ValueError(f"Duplicate RGB MAE is too large: {rgb_difference}")
    if int(rgb_difference["max_abs"]) > int(pair_contract["maximum_decoded_rgb_max_abs"]):
        raise ValueError(f"Duplicate RGB max difference is too large: {rgb_difference}")
    common_difference = decoded_difference(
        resolve_mask(keep, data_root), resolve_mask(quarantined, data_root), "L"
    )
    if pair_contract["require_common_mask_conflict"] and int(
        common_difference["different_values"]
    ) == 0:
        raise ValueError("Expected conflicting supervision in same-image duplicate pair")

    eligible = [record for record in full_records if record.sample_id != quarantine_id]
    train = [record for record in eligible if record.split == "train"]
    calibration = [record for record in eligible if record.split == "external_calibration"]
    require_equal("eligible samples", len(eligible), int(contract["eligible_samples"]))
    require_equal(
        "eligible roles",
        dict(Counter(record.split for record in eligible)),
        {str(role): int(count) for role, count in contract["eligible_roles"].items()},
    )
    require_equal("quarantine samples", len(full_records) - len(eligible), int(contract["quarantine_samples"]))

    transfer_records = read_manifest(locked_paths["country_transfer_manifest"])
    transfer_quarantine_id = quarantine_id.replace(
        "riceseg:", "riceseg_country_transfer:", 1
    )
    transfer_eligible = [
        record for record in transfer_records if record.sample_id != transfer_quarantine_id
    ]
    require_equal(
        "country-transfer eligible roles",
        dict(Counter(record.split for record in transfer_eligible)),
        {
            str(role): int(count)
            for role, count in contract["country_transfer_roles"].items()
        },
    )

    outputs = config["outputs"]
    output_paths = {
        name: require_inside(data_root / str(recorded), data_root, name.replace("_", " "))
        for name, recorded in outputs.items()
    }
    manifests = {
        "eligible": output_manifest(eligible, output_paths["eligible_manifest"], data_root),
        "train": output_manifest(train, output_paths["train_manifest"], data_root),
        "calibration": output_manifest(
            calibration, output_paths["calibration_manifest"], data_root
        ),
        "quarantine": output_manifest(
            [quarantined], output_paths["quarantine_manifest"], data_root
        ),
        "country_transfer": output_manifest(
            transfer_eligible,
            output_paths["country_transfer_manifest"],
            data_root,
        ),
    }
    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "passed",
        "quality_config": str(config_path),
        "quality_config_sha256": sha256(config_path),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "locked_inputs": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in locked_paths.items()
        },
        "release_samples_preserved": len(full_records),
        "eligible_samples": len(eligible),
        "quality_gates": {
            "conversion": True,
            "visual_review": True,
            "candidate_to_existing_duplicate_free": True,
            "train_calibration_duplicate_free": True,
            "same_train_duplicate_quarantined": True,
        },
        "same_train_duplicate": {
            "keep_sample": keep_id,
            "quarantine_sample": quarantine_id,
            "image_dhash_hamming": actual_dhash,
            "decoded_rgb_difference": rgb_difference,
            "common_mask_difference": common_difference,
            "review_image": str(locked_paths["duplicate_review_image"]),
            "review_image_sha256": sha256(locked_paths["duplicate_review_image"]),
            "decision_rule": pair_contract["deterministic_rule"],
            "files_deleted_or_modified": False,
        },
        "manifests": manifests,
        "training_manifest": str(output_paths["train_manifest"]),
        "calibration_manifest": str(output_paths["calibration_manifest"]),
        "country_transfer_is_alternative_protocol": True,
        "external_test_created": False,
        "model_results_used": False,
        "source_files_preserved": True,
        "passed": True,
    }
    receipt_path = output_paths["quality_receipt"]
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(receipt_path)
    return receipt_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/data/riceseg_quality_gate_v1.yaml"),
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_args()
    receipt = finalize(arguments.config)
    print(
        json.dumps(
            {"quality_receipt": str(receipt), "sha256": sha256(receipt)},
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
