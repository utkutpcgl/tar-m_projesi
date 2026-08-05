#!/usr/bin/env python3
"""Finalize the frozen Sugar Beets holdout after visual and leakage review."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


EXPECTED_TRAINING_MANIFEST_SHA256 = (
    "26fc38b99d224f4c2ded75a28513436f90c36bb51b8420f77272563aa5889a7f"
)
EXPECTED_TRAINING_ROWS = 5_951


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def require(name: str, condition: bool) -> None:
    if not condition:
        raise ValueError(f"Failed gate: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", default="configs/data/sugarbeets2016_multiclass_holdout_v1.yaml"
    )
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[1]
    config_path = (project_root / args.config).resolve()
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    data_root = (project_root / "data").resolve()
    outputs = config["outputs"]
    conversion_path = data_root / outputs["conversion_report"]
    duplicate_path = data_root / outputs["duplicate_audit"]
    contact_path = data_root / outputs["contact_sheet"]
    output = data_root / outputs["manual_visual_review"]
    if output.exists():
        raise FileExistsError(output)

    conversion = load_json(conversion_path)
    duplicate = load_json(duplicate_path)
    require(
        "conversion config hash",
        conversion["provenance"]["config_sha256"] == sha256(config_path),
    )
    require(
        "automated conversion",
        conversion.get("all_automated_conversion_gates_passed") is True,
    )
    require("frame count", conversion.get("frames") == 283)
    require("one field/session unit", conversion.get("field_session_units") == 1)
    require(
        "contact sheet hash",
        conversion["derived"]["contact_sheet_sha256"] == sha256(contact_path),
    )
    require("duplicate audit pass", duplicate.get("passed") is True)
    require(
        "zero training matches",
        duplicate.get("candidate_to_reference_match_count") == 0,
    )
    require(
        "zero cross-split internal matches",
        duplicate.get("within_candidate_cross_split_match_count") == 0,
    )
    references = duplicate["scope"]["reference_manifests"]
    require("one frozen training reference", len(references) == 1)
    require(
        "training reference SHA-256",
        references[0]["sha256"] == EXPECTED_TRAINING_MANIFEST_SHA256,
    )
    require(
        "training reference rows",
        duplicate["scope"]["reference_samples"] == EXPECTED_TRAINING_ROWS,
    )
    require(
        "candidate manifest hash",
        duplicate["scope"]["candidate_manifest_sha256"]
        == conversion["derived"]["manifest_sha256"],
    )

    inspected = conversion["manual_contact_indices"]
    require("twelve frozen visual pairs", len(inspected) == 12)
    receipt = {
        "schema_version": 1,
        "dataset_id": config["dataset_id"],
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "reviewer": {
            "type": "coding_agent_visual_inspection",
            "human_agronomist_review": False,
            "scope": "twelve frozen RGB/common-mask overlay pairs",
        },
        "inspected_frame_indices": inspected,
        "contact_sheet": str(contact_path),
        "contact_sheet_sha256": sha256(contact_path),
        "visual_observations": {
            "sugar_beet_contours_follow_broadleaf_pixels": True,
            "weed_contours_include_broadleaf_and_thin_grass_pixels": True,
            "obvious_rgb_mask_spatial_offset": False,
            "obvious_crop_weed_class_inversion": False,
            "empty_or_corrupt_review_pair": False,
            "soil_and_residue_remain_background": True,
        },
        "visual_gate_passed": True,
        "automated_conversion_gate_passed": True,
        "training_duplicate_gate_passed": True,
        "training_duplicate_matches": 0,
        "training_nearest_dhash_hamming": duplicate[
            "candidate_to_reference_nearest_hamming"
        ],
        "frozen_training_reference": references[0],
        "policy": {
            "role": "target_like_real_field_session_holdout",
            "training_allowed": False,
            "model_evaluation_had_occurred_before_freeze": False,
            "model_artifacts_accessed_by_this_finalizer": False,
            "one_sequence_equals_one_field_session_vote": True,
            "283_frames_do_not_equal_283_independent_votes": True,
            "eligible_for_frozen_v2_model_comparison": True,
            "standalone_final_or_deployment_claim": False,
        },
        "limitations": [
            "All 283 frames are temporally correlated members of one field, date, and robot session.",
            "The coding-agent visual review is not a human agronomist species audit.",
            "The primary publication supports red=sugar beet and other colours=weed; individual weed species are intentionally collapsed.",
            "This panel improves field/session disjointness but cannot alone establish geographic, seasonal, or deployment safety generalization.",
        ],
        "provenance": {
            "config": str(config_path),
            "config_sha256": sha256(config_path),
            "conversion_report": str(conversion_path),
            "conversion_report_sha256": sha256(conversion_path),
            "duplicate_report": str(duplicate_path),
            "duplicate_report_sha256": sha256(duplicate_path),
            "finalizer": str(Path(__file__).resolve()),
            "finalizer_sha256": sha256(Path(__file__).resolve()),
        },
        "all_release_gates_passed": True,
        "holdout_release_accepted": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
