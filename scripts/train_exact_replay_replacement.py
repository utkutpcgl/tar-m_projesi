#!/usr/bin/env python3
"""Train one fixed-compute candidate with exact baseline-index replacement."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

import yaml
from torch.utils.data import Sampler

from agri_seg import engine
from agri_seg.data import DomainBalancedSampler as LegacyDomainBalancedSampler
from agri_seg.manifest import SampleRecord, read_manifest


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stream_sha256(records: Sequence[SampleRecord]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.sample_id.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def replacement_positions(total: int, replacements: int) -> list[int]:
    if total <= 0:
        raise ValueError("total must be positive")
    if replacements <= 0 or replacements >= total:
        raise ValueError("replacements must be in [1, total - 1]")
    positions = [
        ((2 * index + 1) * total) // (2 * replacements)
        for index in range(replacements)
    ]
    if len(set(positions)) != replacements:
        raise ValueError("Replacement positions are not unique")
    return positions


class ExactIndexReplayReplacementSampler(Sampler[int]):
    """Replay the legacy base stream and replace fixed, evenly spaced indices."""

    def __init__(
        self,
        records: Sequence[SampleRecord],
        num_samples: int,
        seed: int,
        dataset_weights: Mapping[str, float] | None,
        replay: Mapping[str, Any],
    ) -> None:
        self.records = list(records)
        self.num_samples = int(num_samples)
        self.seed = int(seed)
        self.epoch = 0
        self.target_dataset_id = str(replay["target_dataset_id"])
        self.replacements = int(replay["replacements_per_epoch"])
        self.target_seed_offset = int(replay["target_seed_offset"])
        self.positions = replacement_positions(
            self.num_samples, self.replacements
        )
        self.position_set = set(self.positions)

        indexed_base = [
            (index, record)
            for index, record in enumerate(self.records)
            if record.dataset_id != self.target_dataset_id
        ]
        indexed_target = [
            (index, record)
            for index, record in enumerate(self.records)
            if record.dataset_id == self.target_dataset_id
        ]
        if not indexed_base or not indexed_target:
            raise ValueError("Both base and target records are required")
        self.base_original_indices = [item[0] for item in indexed_base]
        self.target_original_indices = [item[0] for item in indexed_target]
        base_records = [item[1] for item in indexed_base]
        target_records = [item[1] for item in indexed_target]

        base_weights = {
            str(name): float(value)
            for name, value in replay["baseline_dataset_weights"].items()
        }
        base_datasets = {record.dataset_id for record in base_records}
        if set(base_weights) != base_datasets:
            raise ValueError(
                "baseline_dataset_weights do not match non-target datasets"
            )
        if not math.isclose(sum(base_weights.values()), 1.0, abs_tol=1e-12):
            raise ValueError("baseline_dataset_weights must sum to one")

        configured = {
            str(name): float(value)
            for name, value in (dataset_weights or {}).items()
        }
        observed = base_datasets | {self.target_dataset_id}
        if set(configured) != observed:
            raise ValueError("Candidate dataset_weights do not match manifest datasets")
        target_fraction = self.replacements / self.num_samples
        if not math.isclose(
            configured[self.target_dataset_id], target_fraction, abs_tol=1e-12
        ):
            raise ValueError("Configured target weight differs from exact replacement rate")
        for name, baseline_weight in base_weights.items():
            expected = baseline_weight * (1.0 - target_fraction)
            if not math.isclose(configured[name], expected, abs_tol=1e-12):
                raise ValueError(f"Scaled baseline weight mismatch: {name}")

        self.base_sampler = LegacyDomainBalancedSampler(
            base_records,
            num_samples=self.num_samples,
            seed=self.seed,
            dataset_weights=base_weights,
        )
        self.target_sampler = LegacyDomainBalancedSampler(
            target_records,
            num_samples=self.replacements,
            seed=self.seed + self.target_seed_offset,
            dataset_weights={self.target_dataset_id: 1.0},
        )

    def __iter__(self) -> Iterator[int]:
        self.base_sampler.set_epoch(self.epoch)
        self.target_sampler.set_epoch(self.epoch)
        base = [
            self.base_original_indices[index] for index in self.base_sampler
        ]
        target = iter(
            self.target_original_indices[index] for index in self.target_sampler
        )
        for position, base_index in enumerate(base):
            yield next(target) if position in self.position_set else base_index

    def __len__(self) -> int:
        return self.num_samples

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)


def load_mapping(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.suffix.lower() == ".json":
        value = json.loads(source.read_text(encoding="utf-8"))
    else:
        value = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a mapping: {source}")
    return value


def resolve_matrix_candidate(
    matrix_path: Path, candidate_name: str, seed: int
) -> tuple[dict[str, Any], Path]:
    matrix = load_mapping(matrix_path)
    base_path = (matrix_path.parent / str(matrix["base_config"])).resolve()
    config = deepcopy(load_mapping(base_path))
    matches = [
        candidate
        for candidate in matrix["candidates"]
        if str(candidate["name"]) == candidate_name
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one candidate named {candidate_name}")
    candidate = matches[0]
    config["seed"] = int(seed)
    config["experiment"] = candidate_name
    for key in ("manifest", "data_root", "commercial_only"):
        if key in matrix:
            config[key] = matrix[key]
        if key in candidate:
            config[key] = candidate[key]
    for section in ("model", "training", "loss", "safety"):
        config[section].update(matrix.get(section, {}))
        config[section].update(candidate.get(section, {}))
    generated = Path(str(matrix["work_dir"])).expanduser() / "resolved_configs"
    generated.mkdir(parents=True, exist_ok=True)
    resolved = generated / f"{candidate_name}_seed_{seed}.yaml"
    resolved.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config, resolved


def train_records(config: Mapping[str, Any]) -> list[SampleRecord]:
    training = config["training"]
    records = [
        record
        for record in read_manifest(str(config["manifest"]))
        if record.split == str(training.get("train_split", "train"))
        and (
            not bool(config.get("commercial_only", True))
            or record.commercial_allowed
        )
    ]
    limit = training.get("limit_train_samples")
    return records if limit is None else records[: int(limit)]


def sampler_evidence(
    candidate_config: Mapping[str, Any], epochs: int
) -> dict[str, Any]:
    training = candidate_config["training"]
    replay = training["exact_replay_replacement"]
    baseline_config_path = Path(str(replay["baseline_resolved_config"])).resolve()
    baseline_config = load_mapping(baseline_config_path)
    if int(baseline_config["seed"]) != int(candidate_config["seed"]):
        raise ValueError("Baseline and candidate seeds differ")
    baseline_records = train_records(baseline_config)
    candidate_records = train_records(candidate_config)
    baseline_sampler = LegacyDomainBalancedSampler(
        baseline_records,
        num_samples=int(baseline_config["training"]["samples_per_epoch"]),
        seed=int(baseline_config["seed"]),
        dataset_weights=baseline_config["training"]["dataset_weights"],
    )
    candidate_sampler = ExactIndexReplayReplacementSampler(
        candidate_records,
        num_samples=int(training["samples_per_epoch"]),
        seed=int(candidate_config["seed"]),
        dataset_weights=training["dataset_weights"],
        replay=replay,
    )
    if len(baseline_sampler) != len(candidate_sampler):
        raise ValueError("Fixed-compute baseline and candidate lengths differ")

    positions = candidate_sampler.position_set
    target_id = candidate_sampler.target_dataset_id
    per_epoch: list[dict[str, Any]] = []
    target_groups: Counter[str] = Counter()
    for epoch in range(epochs):
        baseline_sampler.set_epoch(epoch)
        candidate_sampler.set_epoch(epoch)
        baseline_epoch = [baseline_records[index] for index in baseline_sampler]
        candidate_epoch = [candidate_records[index] for index in candidate_sampler]
        target = [record for record in candidate_epoch if record.dataset_id == target_id]
        target_groups.update(record.group_id for record in target)
        wrong_target_positions = [
            position
            for position, record in enumerate(candidate_epoch)
            if (record.dataset_id == target_id) != (position in positions)
        ]
        kept_matches = sum(
            candidate_epoch[position].sample_id == baseline_epoch[position].sample_id
            for position in range(len(baseline_epoch))
            if position not in positions
        )
        expected_kept = len(baseline_epoch) - len(positions)
        per_epoch.append(
            {
                "epoch": epoch,
                "baseline_stream_sha256": stream_sha256(baseline_epoch),
                "candidate_stream_sha256": stream_sha256(candidate_epoch),
                "draws": len(candidate_epoch),
                "target_draws": len(target),
                "kept_baseline_positions": expected_kept,
                "exact_kept_position_matches": kept_matches,
                "all_non_replaced_positions_match": kept_matches == expected_kept,
                "target_position_contract_passed": not wrong_target_positions,
                "wrong_target_positions": wrong_target_positions,
            }
        )
    passed = all(
        item["all_non_replaced_positions_match"]
        and item["target_position_contract_passed"]
        and item["target_draws"] == candidate_sampler.replacements
        for item in per_epoch
    )
    return {
        "passed": passed,
        "baseline_resolved_config": str(baseline_config_path),
        "baseline_resolved_config_sha256": sha256(baseline_config_path),
        "baseline_manifest": str(Path(str(baseline_config["manifest"])).resolve()),
        "baseline_manifest_sha256": sha256(str(baseline_config["manifest"])),
        "candidate_manifest": str(Path(str(candidate_config["manifest"])).resolve()),
        "candidate_manifest_sha256": sha256(str(candidate_config["manifest"])),
        "epochs": epochs,
        "draws_per_epoch": candidate_sampler.num_samples,
        "replacements_per_epoch": candidate_sampler.replacements,
        "target_exposure": candidate_sampler.replacements / candidate_sampler.num_samples,
        "replacement_positions": sorted(positions),
        "replacement_positions_sha256": hashlib.sha256(
            json.dumps(sorted(positions), separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "position_policy": "evenly_spaced_bin_centers",
        "target_group_draws_all_epochs": dict(sorted(target_groups.items())),
        "target_group_draw_min": min(target_groups.values()),
        "target_group_draw_max": max(target_groups.values()),
        "per_epoch": per_epoch,
    }


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()

    matrix_path = args.matrix.resolve()
    config, resolved_path = resolve_matrix_candidate(
        matrix_path, args.candidate, args.seed
    )
    replay = config["training"].get("exact_replay_replacement")
    if not isinstance(replay, dict) or replay.get("enabled") is not True:
        raise ValueError("Candidate has no enabled exact_replay_replacement contract")
    epochs = int(config["training"]["epochs"])
    evidence = sampler_evidence(config, epochs)
    if evidence["passed"] is not True:
        raise RuntimeError("Exact replay replacement audit failed before training")

    output_root = Path(str(config["output_root"])).expanduser()
    run_dir = output_root / str(config["experiment"]) / f"seed_{args.seed}"
    receipt_path = run_dir / "exact_replay_replacement_receipt.json"
    preflight = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "role": "exact_index_replay_fixed_compute_riceseg_replacement",
        "status": "preflight_passed" if args.audit_only else "training_pending",
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
        "matrix": str(matrix_path),
        "matrix_sha256": sha256(matrix_path),
        "resolved_config": str(resolved_path.resolve()),
        "resolved_config_sha256": sha256(resolved_path),
        "source_tree_sha256": engine.source_tree_sha256(),
        "evidence": evidence,
    }
    if args.audit_only:
        print(json.dumps(preflight, indent=2, sort_keys=True))
        return

    original_sampler = engine.DomainBalancedSampler

    def replay_sampler_factory(
        records: Sequence[SampleRecord],
        num_samples: int | None = None,
        seed: int = 17,
        dataset_weights: Mapping[str, float] | None = None,
    ) -> ExactIndexReplayReplacementSampler:
        if num_samples is None:
            raise ValueError("Exact replay requires explicit samples_per_epoch")
        return ExactIndexReplayReplacementSampler(
            records,
            num_samples=num_samples,
            seed=seed,
            dataset_weights=dataset_weights,
            replay=replay,
        )

    engine.DomainBalancedSampler = replay_sampler_factory  # type: ignore[assignment]
    try:
        completed_run = engine.train_from_config(resolved_path)
    finally:
        engine.DomainBalancedSampler = original_sampler
    if completed_run.resolve() != run_dir.resolve():
        raise RuntimeError("Training produced an unexpected run directory")

    receipt = {
        **preflight,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "complete",
        "run_dir": str(run_dir.resolve()),
        "checkpoint": str((run_dir / "last.pt").resolve()),
        "checkpoint_sha256": sha256(run_dir / "last.pt"),
        "summary_sha256": sha256(run_dir / "summary.json"),
        "history_sha256": sha256(run_dir / "history.jsonl"),
        "run_metadata_sha256": sha256(run_dir / "run_metadata.json"),
    }
    write_json(receipt_path, receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
