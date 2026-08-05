#!/usr/bin/env python3
"""Lock a manual review of an unlabeled unseen-sequence model audit."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evaluation_receipt")
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--verdict", choices=("accept_diagnostic", "reject"), required=True)
    parser.add_argument("--strengths", required=True)
    parser.add_argument("--failure-modes", required=True)
    arguments = parser.parse_args()
    evaluation_path = Path(arguments.evaluation_receipt).expanduser().resolve()
    evaluation = load_json(evaluation_path)
    output = evaluation_path.parent / "manual_visual_review.json"
    if output.exists():
        raise FileExistsError(output)
    if evaluation.get("all_automated_quality_gates_passed") is not True:
        raise RuntimeError("Automated unseen-sequence gates did not pass")
    contact = Path(evaluation["contact_sheet"]).resolve()
    video = Path(evaluation["semantic_overlay_video"]).resolve()
    if sha256(contact) != evaluation["contact_sheet_sha256"]:
        raise RuntimeError("Prediction contact sheet changed")
    if sha256(video) != evaluation["semantic_overlay_video_sha256"]:
        raise RuntimeError("Prediction overlay video changed")
    video_receipt_path = Path(evaluation["video_receipt"]).resolve()
    video_receipt = load_json(video_receipt_path)
    if sha256(video_receipt_path) != evaluation["video_receipt_sha256"]:
        raise RuntimeError("Source video receipt changed")
    source_contact = Path(video_receipt["contact_sheet"]["path"]).resolve()
    if sha256(source_contact) != video_receipt["contact_sheet"]["sha256"]:
        raise RuntimeError("Source contact sheet changed")
    for row in evaluation["frames"]:
        for path_key, hash_key in (
            ("source_path", "source_sha256"),
            ("semantic_mask", "semantic_mask_sha256"),
            ("semantic_overlay", "semantic_overlay_sha256"),
            ("policy_overlay", "policy_overlay_sha256"),
        ):
            if sha256(row[path_key]) != row[hash_key]:
                raise RuntimeError(f"Frame artifact changed: {row[path_key]}")
    accepted = arguments.verdict == "accept_diagnostic"
    gates = {
        "evaluation_artifacts_hash_locked": True,
        "source_video_artifacts_hash_locked": True,
        "all_frame_artifacts_hash_locked": True,
        "unlabeled_status_preserved": evaluation["evaluation_policy"][
            "annotations_present"
        ]
        is False,
        "numeric_accuracy_absent": evaluation["evaluation_policy"]["miou"] is None,
        "selection_score_weight_zero": float(
            evaluation["evaluation_policy"]["model_selection_score_weight"]
        )
        == 0.0,
        "manual_diagnostic_acceptance": accepted,
    }
    receipt = {
        "schema_version": 1,
        "evaluation_receipt": str(evaluation_path),
        "evaluation_receipt_sha256": sha256(evaluation_path),
        "source_contact_sheet": str(source_contact),
        "source_contact_sheet_sha256": sha256(source_contact),
        "prediction_contact_sheet": str(contact),
        "prediction_contact_sheet_sha256": sha256(contact),
        "prediction_overlay_video": str(video),
        "prediction_overlay_video_sha256": sha256(video),
        "reviewer": arguments.reviewer,
        "verdict": arguments.verdict,
        "decision_scope": "accept_as_unlabeled_failure-discovery_diagnostic_only",
        "model_performance_acceptance": False,
        "strengths_observed": arguments.strengths,
        "failure_modes_observed": arguments.failure_modes,
        "required_next_step_for_accuracy": (
            "Annotate a frozen representative frame subset with exhaustive common "
            "0/1/2/255 labels before computing mIoU or crop/weed IoU."
        ),
        "quality_gates": gates,
        "passed": all(gates.values()),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if not receipt["passed"]:
        raise RuntimeError(f"Manual unseen-sequence review failed; see {output}")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
