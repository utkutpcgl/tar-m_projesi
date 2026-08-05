#!/usr/bin/env python3
"""Run one matched real-only recovery arm from a locked warm checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import torch
import yaml

from agri_seg import engine
from agri_seg.data import DomainBalancedSampler
from agri_seg.manifest import read_manifest


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


def load_mapping(path: str | Path) -> dict[str, Any]:
    value = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected mapping: {path}")
    return value


def candidate_by_name(protocol: Mapping[str, Any], name: str) -> dict[str, Any]:
    matches = [item for item in protocol["candidates"] if item["name"] == name]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one recovery candidate named {name!r}")
    return dict(matches[0])


def validate_protocol(
    protocol: Mapping[str, Any], protocol_path: Path, candidate: Mapping[str, Any]
) -> dict[str, Any]:
    if int(protocol.get("schema_version", 0)) != 1:
        raise ValueError("Recovery protocol must be schema-v1")
    manifest = Path(str(protocol["manifest"])).resolve()
    if sha256(manifest) != str(protocol["manifest_sha256"]):
        raise RuntimeError("Locked recovery manifest hash changed")
    initial = Path(str(candidate["initial_checkpoint"])).resolve()
    if sha256(initial) != str(candidate["initial_checkpoint_sha256"]):
        raise RuntimeError("Locked initial checkpoint hash changed")
    records = read_manifest(manifest)
    train_split = str(protocol["training"].get("train_split", "train"))
    train_records = [record for record in records if record.split == train_split]
    observed = {record.dataset_id for record in train_records}
    weights = {
        str(key): float(value)
        for key, value in protocol["training"]["dataset_weights"].items()
    }
    if set(weights) != observed:
        raise ValueError(
            f"Recovery weights/manifest mismatch: weights={sorted(weights)}, "
            f"observed={sorted(observed)}"
        )
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-12):
        raise ValueError("Recovery dataset weights must sum to exactly one")
    forbidden = [name for name in observed if "cropcraft" in name or "synthetic" in name]
    if forbidden:
        raise ValueError(f"Synthetic datasets found in real-only recovery: {forbidden}")
    fairness = protocol["fairness"]
    required_true = (
        "identical_real_manifest",
        "identical_real_draws",
        "identical_augmentation",
        "identical_optimizer_and_schedule",
        "fresh_optimizer_for_both_arms",
        "no_synthetic_rows_during_recovery",
        "existing_direct_mixture_results_are_read_only",
    )
    if not all(fairness.get(key) is True for key in required_true):
        raise ValueError("A required recovery fairness contract is not true")
    if fairness.get("external_or_final_test_used") is not False:
        raise ValueError("Recovery protocol must not use external/final test data")
    return {
        "protocol": str(protocol_path),
        "protocol_sha256": sha256(protocol_path),
        "manifest": str(manifest),
        "manifest_sha256": sha256(manifest),
        "initial_checkpoint": str(initial),
        "initial_checkpoint_sha256": sha256(initial),
        "train_records": len(train_records),
        "train_dataset_ids": sorted(observed),
        "dataset_weights": weights,
    }


def draw_stream_evidence(
    protocol: Mapping[str, Any], manifest: str | Path
) -> dict[str, Any]:
    training = protocol["training"]
    records = [
        record
        for record in read_manifest(manifest)
        if record.split == str(training.get("train_split", "train"))
    ]
    sampler = DomainBalancedSampler(
        records,
        num_samples=int(training["samples_per_epoch"]),
        seed=int(protocol["screen_seed"]),
        dataset_weights=training["dataset_weights"],
    )
    epochs: list[dict[str, Any]] = []
    for epoch in range(int(training["epochs"])):
        sampler.set_epoch(epoch)
        digest = hashlib.sha256()
        counts: dict[str, int] = {}
        for index in sampler:
            record = records[index]
            digest.update(record.sample_id.encode("utf-8"))
            digest.update(b"\0")
            counts[record.dataset_id] = counts.get(record.dataset_id, 0) + 1
        epochs.append(
            {
                "epoch": epoch + 1,
                "sample_id_stream_sha256": digest.hexdigest(),
                "dataset_draw_counts": dict(sorted(counts.items())),
            }
        )
    return {
        "seed": int(protocol["screen_seed"]),
        "epochs": epochs,
        "same_for_every_candidate": True,
        "augmentation_rng_contract": (
            "Each arm starts in a fresh process; set_reproducibility uses the "
            "same deterministic seed before loader construction and training."
        ),
    }


def resolved_training_config(
    protocol: Mapping[str, Any], candidate: Mapping[str, Any], evidence: Mapping[str, Any]
) -> dict[str, Any]:
    initial_payload = torch.load(
        str(candidate["initial_checkpoint"]), map_location="cpu", weights_only=False
    )
    initial_config = initial_payload.get("config")
    initial_metadata = initial_payload.get("metadata")
    if not isinstance(initial_config, Mapping) or not isinstance(initial_metadata, Mapping):
        raise RuntimeError("Initial checkpoint lacks config/provenance metadata")
    if initial_metadata.get("source_tree_sha256") != engine.source_tree_sha256():
        raise RuntimeError("Initial checkpoint source-tree provenance changed")
    if not isinstance(initial_payload.get("validation"), Mapping):
        raise RuntimeError("Initial checkpoint is not source-calibrated")

    config = deepcopy(dict(initial_config))
    config.update(
        {
            "experiment": str(candidate["name"]),
            "seed": int(protocol["screen_seed"]),
            "manifest": str(protocol["manifest"]),
            "data_root": str(protocol["data_root"]),
            "output_root": str(protocol["output_root"]),
            "deterministic": True,
            "commercial_only": False,
        }
    )
    training = deepcopy(dict(config["training"]))
    training.update(dict(protocol["training"]))
    training.pop("minimum_free_gpu_bytes", None)
    training["validate_every"] = int(training["epochs"])
    config["training"] = training
    config["recovery"] = {
        "role": str(candidate["role"]),
        "warm_start_checkpoint": evidence["initial_checkpoint"],
        "warm_start_checkpoint_sha256": evidence["initial_checkpoint_sha256"],
        "warm_start_experiment": initial_config.get("experiment"),
        "warm_start_seed": initial_config.get("seed"),
        "warm_start_source_tree_sha256": initial_metadata.get("source_tree_sha256"),
        "fresh_optimizer": True,
        "protocol": evidence["protocol"],
        "protocol_sha256": evidence["protocol_sha256"],
        "real_only": True,
        "screen_only": True,
    }
    return config


def gpu_capacity_gate(required_free_bytes: int) -> dict[str, Any]:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for recovery training")
    free, total = torch.cuda.mem_get_info()
    report = {
        "required_free_bytes": int(required_free_bytes),
        "observed_free_bytes": int(free),
        "total_bytes": int(total),
        "passed": int(free) >= int(required_free_bytes),
    }
    if not report["passed"]:
        raise RuntimeError(
            "Recovery GPU capacity gate failed: "
            f"free={free:,}, required={required_free_bytes:,}. "
            "No external GPU process was modified."
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--reuse-completed", action="store_true")
    args = parser.parse_args()

    protocol_path = Path(args.protocol).resolve()
    protocol = load_mapping(protocol_path)
    candidate = candidate_by_name(protocol, args.candidate)
    evidence = validate_protocol(protocol, protocol_path, candidate)
    output = (
        Path(str(protocol["output_root"])).expanduser()
        / str(candidate["name"])
        / f"seed_{int(protocol['screen_seed'])}"
    )
    if args.reuse_completed and (output / "summary.json").exists():
        summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        if summary.get("status") != "complete":
            raise RuntimeError("Existing recovery run is not complete")
        print(json.dumps({"reused": True, "run_dir": str(output)}, indent=2))
        return

    required = int(protocol["training"]["minimum_free_gpu_bytes"])
    capacity = gpu_capacity_gate(required)
    stream = draw_stream_evidence(protocol, evidence["manifest"])
    config = resolved_training_config(protocol, candidate, evidence)
    resolved_root = (
        Path(str(protocol["data_root"]))
        / "processed/benchmark/simulation_diversity_real_recovery_v1/resolved_configs"
    )
    resolved_root.mkdir(parents=True, exist_ok=True)
    resolved_path = resolved_root / f"{candidate['name']}_seed_{protocol['screen_seed']}.yaml"
    if resolved_path.exists():
        raise FileExistsError(f"Refusing existing resolved config: {resolved_path}")
    resolved_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    device = torch.device("cuda")
    warm_model, warm_checkpoint = engine.load_checkpoint(
        candidate["initial_checkpoint"], device
    )
    if warm_checkpoint["metadata"]["source_tree_sha256"] != engine.source_tree_sha256():
        raise RuntimeError("Warm-start model provenance changed during load")
    original_builder = engine.build_model

    def use_warm_model(_: object) -> torch.nn.Module:
        return warm_model

    engine.build_model = use_warm_model
    try:
        run_dir = engine.train_from_config(resolved_path)
    finally:
        engine.build_model = original_builder

    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": candidate,
        "validation_evidence": evidence,
        "gpu_capacity_gate": capacity,
        "draw_stream_evidence": stream,
        "resolved_config": str(resolved_path),
        "resolved_config_sha256": sha256(resolved_path),
        "run_dir": str(run_dir),
        "best_checkpoint_sha256": sha256(run_dir / "best.pt"),
        "last_checkpoint_sha256": sha256(run_dir / "last.pt"),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
        "fresh_optimizer_verified_by_training_entrypoint": True,
        "synthetic_rows_in_recovery": 0,
    }
    engine._write_json(receipt, run_dir / "recovery_provenance.json")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
