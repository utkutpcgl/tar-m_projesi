#!/usr/bin/env python3
"""Audit RiceSEG evaluation roles against the accepted specialist train set."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agri_seg.manifest import manifest_sha256, read_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
TRAIN_MANIFEST = DATA_ROOT / (
    "processed/manifests/"
    "real_sorghum_cropcraft_robust_v3_paddy_riceseg_trainval_v10_r1.csv"
)
PANELS = {
    "training_heldout_development_calibration": (
        DATA_ROOT / "processed/manifests/riceseg_v1.csv",
        "external_calibration",
    ),
    "alternative_country_protocol_external": (
        DATA_ROOT / "processed/manifests/riceseg_country_transfer_v1.csv",
        "external_calibration",
    ),
}
OUTPUT = DATA_ROOT / (
    "processed/audits/intervention_metrics_v1/"
    "riceseg_split_path_overlap_audit.json"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    training = [
        record
        for record in read_manifest(TRAIN_MANIFEST)
        if record.split == "train"
    ]
    training_images = {record.image_path for record in training}
    training_masks = {record.mask_path for record in training}
    panel_results: dict[str, object] = {}
    for name, (manifest, split) in PANELS.items():
        records = [
            record
            for record in read_manifest(manifest)
            if record.split == split
        ]
        image_overlap = [
            record.sample_id
            for record in records
            if record.image_path in training_images
        ]
        mask_overlap = [
            record.sample_id
            for record in records
            if record.mask_path in training_masks
        ]
        panel_results[name] = {
            "manifest": str(manifest),
            "manifest_sha256": manifest_sha256(manifest),
            "split": split,
            "records": len(records),
            "fields": sorted({record.field_id for record in records}),
            "sessions": sorted({record.session_id for record in records}),
            "training_image_path_overlap": len(image_overlap),
            "training_mask_path_overlap": len(mask_overlap),
            "image_overlap_examples": image_overlap[:10],
            "mask_overlap_examples": mask_overlap[:10],
            "eligible_as_specialist_training_heldout": (
                not image_overlap and not mask_overlap
            ),
            "eligible_as_untouched_final_test": False,
            "prior_specialist_selection_used_panel": (
                name == "training_heldout_development_calibration"
            ),
        }
    payload = {
        "schema_version": 2,
        "accepted_specialist_training_manifest": str(TRAIN_MANIFEST),
        "accepted_specialist_training_manifest_sha256": manifest_sha256(
            TRAIN_MANIFEST
        ),
        "training_records": len(training),
        "comparison_unit": "normalized image_path and mask_path strings",
        "panels": panel_results,
        "decision": {
            "primary_specialist_evaluation": (
                "training_heldout_development_calibration"
            ),
            "untouched_final_test_available": False,
            "alternative_country_protocol_external_is_independent": False,
            "reason": (
                "The 604-image panel has zero training-path overlap but was "
                "used by the prior specialist selector, so it is development "
                "calibration rather than untouched final test. The alternative "
                "country protocol is a different partition of the same release "
                "and overlaps accepted specialist training 1254/1254."
            ),
        },
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
