#!/usr/bin/env python3
"""Materialize real development metrics for fixed-epoch ``last.pt`` files."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agri_seg.engine import evaluate_checkpoint


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def validated_epoch(history_path: Path, epoch: int) -> None:
    matches = 0
    with history_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if int(record.get("epoch", -1)) == epoch:
                if not isinstance(record.get("val"), dict):
                    raise ValueError(f"Epoch {epoch} has no validation: {history_path}")
                matches += 1
    if matches != 1:
        raise ValueError(f"Expected one validated epoch {epoch}: {history_path}")


def existing_metrics(path: Path, checkpoint: Path) -> dict[str, Any]:
    metrics = load_object(path)
    calibration = metrics.get("calibration_source", {})
    if Path(calibration.get("checkpoint", "")).resolve() != checkpoint:
        raise ValueError(f"Existing metrics use another checkpoint: {path}")
    if calibration.get("external_threshold_sweep_performed") is not False:
        raise ValueError(f"Existing metrics swept thresholds: {path}")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate_dir")
    parser.add_argument("--seeds", nargs="+", type=int, required=True)
    parser.add_argument("--fixed-epoch", type=int, required=True)
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--cwfid-manifest", required=True)
    parser.add_argument("--sorghum-manifest", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reuse-completed", action="store_true")
    args = parser.parse_args()

    candidate_dir = Path(args.candidate_dir).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    manifests = {
        "cwfid": (
            Path(args.cwfid_manifest).expanduser().resolve(),
            "external_calibration",
        ),
        "sorghum_weed": (
            Path(args.sorghum_manifest).expanduser().resolve(),
            "external_calibration",
        ),
    }
    seeds = sorted(set(args.seeds))
    if len(seeds) != len(args.seeds):
        raise ValueError("Seeds must be unique")
    records: list[dict[str, Any]] = []
    for seed in seeds:
        run_dir = candidate_dir / f"seed_{seed}"
        checkpoint = (run_dir / "last.pt").resolve()
        summary_path = run_dir / "summary.json"
        history_path = run_dir / "history.jsonl"
        if not checkpoint.is_file():
            raise FileNotFoundError(checkpoint)
        summary = load_object(summary_path)
        if summary.get("status") != "complete" or int(
            summary.get("epochs", -1)
        ) != args.fixed_epoch:
            raise ValueError(f"Run is not complete at fixed epoch: {run_dir}")
        validated_epoch(history_path, args.fixed_epoch)
        output_dir = run_dir / f"development_fixed_epoch{args.fixed_epoch}"
        artifacts: dict[str, Any] = {}
        for name, (manifest, split) in manifests.items():
            output = output_dir / f"{name}.json"
            if output.exists():
                if not args.reuse_completed:
                    raise FileExistsError(output)
                metrics = existing_metrics(output, checkpoint)
                reused = True
            else:
                metrics = evaluate_checkpoint(
                    checkpoint,
                    manifest,
                    data_root,
                    split,
                    output,
                    batch_size=1,
                    workers=args.workers,
                )
                reused = False
            artifacts[name] = {
                "path": str(output),
                "sha256": sha256(output),
                "manifest": str(manifest),
                "manifest_sha256": sha256(manifest),
                "split": split,
                "reused": reused,
                "mean_iou": metrics["mean_iou"],
                "crop_iou": metrics["iou"]["target_crop"],
                "weed_iou": metrics["iou"]["other_vegetation"],
            }
        records.append(
            {
                "seed": seed,
                "run_dir": str(run_dir),
                "checkpoint": str(checkpoint),
                "checkpoint_sha256": sha256(checkpoint),
                "summary_sha256": sha256(summary_path),
                "history_sha256": sha256(history_path),
                "artifacts": artifacts,
            }
        )

    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "role": "declared_real_development_only",
        "external_test_used": False,
        "candidate_dir": str(candidate_dir),
        "fixed_epoch": args.fixed_epoch,
        "seeds": seeds,
        "runs": records,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    receipt_path = candidate_dir / (
        f"development_fixed_epoch{args.fixed_epoch}_evaluations.json"
    )
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
