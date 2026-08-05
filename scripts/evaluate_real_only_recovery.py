#!/usr/bin/env python3
"""Evaluate completed real-only recovery arms on the frozen dev matrix."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
import yaml

from agri_seg.engine import evaluate_checkpoint
from agri_seg.manifest import manifest_sha256


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = (
    PROJECT_ROOT / "configs/benchmark/simulation_diversity_real_recovery_v1.yaml"
)


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_mapping(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping: {path}")
    return value


def reusable(path: Path, manifest: Path) -> bool:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return (
            value.get("provenance", {}).get("evaluation_manifest_sha256")
            == manifest_sha256(manifest)
        )
    except (OSError, ValueError, TypeError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--reuse-completed", action="store_true")
    args = parser.parse_args()
    protocol_path = Path(args.protocol).resolve()
    protocol = load_mapping(protocol_path)
    matches = [row for row in protocol["candidates"] if row["name"] == args.candidate]
    if len(matches) != 1:
        raise ValueError(f"Unknown recovery candidate: {args.candidate}")
    seed = int(protocol["screen_seed"])
    run_dir = (
        Path(str(protocol["output_root"])).expanduser()
        / args.candidate
        / f"seed_{seed}"
    )
    checkpoint = run_dir / "best.pt"
    provenance = run_dir / "recovery_provenance.json"
    if not checkpoint.is_file() or not provenance.is_file():
        raise FileNotFoundError(f"Recovery training is incomplete: {run_dir}")
    free, _ = torch.cuda.mem_get_info()
    required = int(protocol["training"]["minimum_free_gpu_bytes"])
    if free < required:
        raise RuntimeError(
            f"GPU capacity gate failed: free={free:,}, required={required:,}; "
            "no external process was modified"
        )

    development = run_dir / "development"
    development.mkdir(parents=True, exist_ok=True)
    artifacts: dict[str, Any] = {
        "real_core_current": {
            "path": str(run_dir / "metrics.json"),
            "sha256": sha256(run_dir / "metrics.json"),
            "kind": "source_validation",
        }
    }
    for panel in protocol["development_evaluations"]:
        name = str(panel["name"])
        manifest = Path(str(panel["manifest"])).resolve()
        output = development / f"{name}.json"
        if output.exists():
            if not args.reuse_completed or not reusable(output, manifest):
                raise FileExistsError(f"Refusing stale/unverified evaluation: {output}")
            status = "reused"
        else:
            evaluate_checkpoint(
                checkpoint_path=checkpoint,
                manifest_path=manifest,
                data_root=protocol["data_root"],
                split=str(panel["split"]),
                output_path=output,
                batch_size=1,
                workers=4,
            )
            status = "evaluated"
        artifacts[name] = {
            "path": str(output),
            "sha256": sha256(output),
            "manifest": str(manifest),
            "manifest_sha256": manifest_sha256(manifest),
            "split": str(panel["split"]),
            "synthetic_diagnostic": bool(panel.get("synthetic_diagnostic", False)),
            "status": status,
        }
        gc.collect()
        torch.cuda.empty_cache()

    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": args.candidate,
        "seed": seed,
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": sha256(checkpoint),
        "artifacts": artifacts,
        "real_numeric_panels": sum(
            not value.get("synthetic_diagnostic", False)
            for key, value in artifacts.items()
            if key != "real_core_current"
        )
        + 1,
        "synthetic_selection_weight": 0.0,
        "external_or_final_test_used": False,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    destination = run_dir / "development_matrix_receipt.json"
    if destination.exists() and not args.reuse_completed:
        raise FileExistsError(destination)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    temporary.replace(destination)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
