#!/usr/bin/env python3
"""Build frozen training and late-stage evaluation manifests for the V9 A/B."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agri_seg.manifest import SampleRecord, manifest_sha256, read_manifest, write_manifest


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


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def select_reproductive_calibration(
    records: list[SampleRecord], dataset_id: str = "riceseg"
) -> list[SampleRecord]:
    return [
        record
        for record in records
        if record.dataset_id == dataset_id
        and record.split == "external_calibration"
        and record.growth_stage == "reproductive"
    ]


def counts(records: list[SampleRecord], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(getattr(record, field)) for record in records).items()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/benchmark/simulation_reproductive_manifest_v9_r3.yaml"),
    )
    arguments = parser.parse_args()
    config_path = arguments.config.expanduser().resolve()
    config = load_yaml(config_path)
    require_equal("config schema", config.get("schema_version"), 1)
    data_root = Path(str(config["data_root"])).expanduser().resolve()

    sources: dict[str, Path] = {}
    for name, specification in config["locked_inputs"].items():
        path = (data_root / str(specification["path"])).resolve()
        try:
            path.relative_to(data_root)
        except ValueError as exc:
            raise ValueError(f"Input escapes data root: {path}") from exc
        if not path.is_file():
            raise FileNotFoundError(path)
        require_equal(f"input SHA-256 {name}", sha256(path), specification["sha256"])
        sources[name] = path

    control = read_manifest(sources["accepted_training_manifest"])
    reproductive = read_manifest(sources["reproductive_pilot_manifest"])
    calibration = read_manifest(sources["riceseg_calibration_manifest"])
    require_equal("control samples", len(control), int(config["expected"]["control_samples"]))
    require_equal("reproductive samples", len(reproductive), int(config["expected"]["reproductive_samples"]))
    require_equal("real Rice absent from training control", any(record.dataset_id == "riceseg" for record in control), False)
    require_equal("real Rice absent from reproductive pilot", any(record.dataset_id == "riceseg" for record in reproductive), False)

    training = [*control, *reproductive]
    late = select_reproductive_calibration(calibration)
    require_equal("combined training samples", len(training), int(config["expected"]["combined_samples"]))
    require_equal("late calibration samples", len(late), int(config["expected"]["late_calibration_samples"]))
    require_equal("late calibration fields", len({record.field_id for record in late}), int(config["expected"]["late_calibration_fields"]))

    outputs = {
        name: (data_root / str(path)).resolve()
        for name, path in config["outputs"].items()
    }
    for name, path in outputs.items():
        try:
            path.relative_to(data_root)
        except ValueError as exc:
            raise ValueError(f"Output escapes data root ({name}): {path}") from exc
    write_manifest(training, outputs["combined_training_manifest"])
    write_manifest(late, outputs["late_calibration_manifest"])

    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
        "model_results_used": False,
        "external_test_used": False,
        "real_rice_training_exposure": False,
        "locked_inputs": {
            name: {"path": str(path), "sha256": sha256(path)}
            for name, path in sources.items()
        },
        "combined_training": {
            "path": str(outputs["combined_training_manifest"]),
            "sha256": manifest_sha256(outputs["combined_training_manifest"]),
            "samples": len(training),
            "dataset_counts": counts(training, "dataset_id"),
            "split_counts": counts(training, "split"),
        },
        "late_calibration": {
            "path": str(outputs["late_calibration_manifest"]),
            "sha256": manifest_sha256(outputs["late_calibration_manifest"]),
            "samples": len(late),
            "dataset_counts": counts(late, "dataset_id"),
            "split_counts": counts(late, "split"),
            "growth_stage_counts": counts(late, "growth_stage"),
            "field_counts": counts(late, "field_id"),
            "selection": "upstream external_calibration rows with growth_stage exactly reproductive",
        },
    }
    outputs["receipt"].parent.mkdir(parents=True, exist_ok=True)
    outputs["receipt"].write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
