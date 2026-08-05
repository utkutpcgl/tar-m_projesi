#!/usr/bin/env python3
"""Remove objective temporal near-duplicates from the Naio source selection."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from select_online_video_unseen_gallery import render_sheet


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARENT = PROJECT_ROOT / "data/processed/audits/online_unseen_naio_oz_v1/selection/selection_receipt.json"
EXPECTED_PARENT_SHA256 = "f9f04cbd2f0b73a315d570610aa780f6f01e2da0cfba7090677508adf8c21a9a"
EXCLUDED_LABELS = {"t=00:20", "t=04:30"}


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent", default=str(DEFAULT_PARENT))
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "data/processed/audits/online_unseen_naio_oz_v1/selection_v2"),
    )
    args = parser.parse_args()
    parent_path = Path(args.parent).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        raise FileExistsError(output)
    if sha256(parent_path) != EXPECTED_PARENT_SHA256:
        raise RuntimeError("Parent Naio selection receipt changed")
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    selected = [row for row in parent["selected_frames"] if row["label"] not in EXCLUDED_LABELS]
    if len(selected) != 10:
        raise RuntimeError("Naio v2 must retain exactly ten frames")
    distances = [
        (int(selected[left]["dhash64"], 16) ^ int(selected[right]["dhash64"], 16)).bit_count()
        for left in range(len(selected)) for right in range(left + 1, len(selected))
    ]
    if min(distances) <= 2:
        raise RuntimeError("Naio v2 still contains a dHash<=2 temporal near duplicate")
    output.mkdir(parents=True, exist_ok=False)
    contact = output / "source_contact_sheet.jpg"
    render_sheet(selected, contact)
    receipt = {
        "schema_version": 2,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "parent_selection": str(parent_path),
        "parent_selection_sha256": EXPECTED_PARENT_SHA256,
        "derivation": {
            "excluded_labels": sorted(EXCLUDED_LABELS),
            "reason": "remove model-uninformed temporal near-duplicates and improve visual coverage density",
            "no_model_predictions_inspected": True,
        },
        "selected_count": len(selected),
        "selected_frames": selected,
        "source_contact_sheets": [{"path": str(contact), "sha256": sha256(contact)}],
        "minimum_selected_pair_dhash_distance": min(distances),
        "training_manifest": parent["training_manifest"],
        "training_manifest_sha256": parent["training_manifest_sha256"],
        "training_unique_image_count_audited": parent["training_unique_image_count_audited"],
        "training_exposure": False,
        "target_crop_id": parent["target_crop_id"],
        "crop_species": parent["crop_species"],
        "class_interpretation": parent["class_interpretation"],
        "numeric_segmentation_accuracy_authorized": False,
        "model_selection_score_weight": 0.0,
        "redistribution_authorized": False,
        "all_quality_gates_passed": True,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    destination = output / "selection_receipt.json"
    destination.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "receipt": str(destination),
        "selected_count": len(selected),
        "minimum_selected_pair_dhash_distance": min(distances),
        "contact_sheet": str(contact),
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
