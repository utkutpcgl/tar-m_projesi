#!/usr/bin/env python3
"""Audit whether RiceSEG mixture runs replay the accepted sample stream."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import yaml

from agri_seg.data import DomainBalancedSampler
from agri_seg.engine import source_tree_sha256
from agri_seg.manifest import SampleRecord, read_manifest


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_mapping(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if source.suffix.lower() == ".json":
        value = json.loads(source.read_text(encoding="utf-8"))
    else:
        value = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a mapping: {source}")
    return value


def stream_sha256(records: Sequence[SampleRecord]) -> str:
    digest = hashlib.sha256()
    for record in records:
        digest.update(record.sample_id.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def sampled_epochs(
    config: dict[str, Any], epochs: int
) -> tuple[list[list[SampleRecord]], dict[str, Any]]:
    training = config["training"]
    records = [
        record
        for record in read_manifest(config["manifest"])
        if record.split == str(training.get("train_split", "train"))
        and (
            not bool(config.get("commercial_only", True))
            or record.commercial_allowed
        )
    ]
    limit = training.get("limit_train_samples")
    if limit is not None:
        records = records[: int(limit)]
    sampler = DomainBalancedSampler(
        records,
        num_samples=int(training["samples_per_epoch"]),
        seed=int(config["seed"]),
        dataset_weights=training.get("dataset_weights"),
    )
    sampled: list[list[SampleRecord]] = []
    for epoch in range(epochs):
        sampler.set_epoch(epoch)
        sampled.append([records[index] for index in sampler])
    flat = [record for epoch in sampled for record in epoch]
    return sampled, {
        "manifest": str(Path(config["manifest"]).resolve()),
        "manifest_sha256": sha256(config["manifest"]),
        "train_rows": len(records),
        "train_groups": len({record.group_id for record in records}),
        "samples_per_epoch": len(sampled[0]),
        "dataset_draws_all_epochs": dict(
            sorted(Counter(record.dataset_id for record in flat).items())
        ),
        "epoch_stream_sha256": [stream_sha256(epoch) for epoch in sampled],
    }


def compare_streams(
    baseline: Sequence[Sequence[SampleRecord]],
    candidate: Sequence[Sequence[SampleRecord]],
    target_dataset_id: str,
) -> dict[str, Any]:
    if len(baseline) != len(candidate):
        raise ValueError("Baseline and candidate epoch counts differ")
    per_epoch: list[dict[str, Any]] = []
    target_groups: Counter[str] = Counter()
    for epoch_index, (base_epoch, candidate_epoch) in enumerate(
        zip(baseline, candidate, strict=True)
    ):
        target = [
            record
            for record in candidate_epoch
            if record.dataset_id == target_dataset_id
        ]
        old = [
            record
            for record in candidate_epoch
            if record.dataset_id != target_dataset_id
        ]
        target_groups.update(record.group_id for record in target)
        compared = min(len(base_epoch), len(old))
        exact_position_matches = sum(
            base_epoch[index].sample_id == old[index].sample_id
            for index in range(compared)
        )
        multiset_overlap = sum(
            (
                Counter(record.sample_id for record in base_epoch)
                & Counter(record.sample_id for record in old)
            ).values()
        )
        per_epoch.append(
            {
                "epoch": epoch_index,
                "baseline_draws": len(base_epoch),
                "candidate_old_draws": len(old),
                "candidate_target_draws": len(target),
                "old_filtered_stream_sha256": stream_sha256(old),
                "exact_old_filtered_position_matches": exact_position_matches,
                "exact_old_filtered_position_match_fraction": (
                    exact_position_matches / max(1, compared)
                ),
                "old_sample_multiset_overlap": multiset_overlap,
                "old_sample_multiset_overlap_fraction": (
                    multiset_overlap / max(1, len(base_epoch))
                ),
            }
        )
    totals = {
        key: sum(int(item[key]) for item in per_epoch)
        for key in (
            "baseline_draws",
            "candidate_old_draws",
            "candidate_target_draws",
            "exact_old_filtered_position_matches",
            "old_sample_multiset_overlap",
        )
    }
    compared_total = min(totals["baseline_draws"], totals["candidate_old_draws"])
    totals["exact_old_filtered_position_match_fraction"] = (
        totals["exact_old_filtered_position_matches"] / max(1, compared_total)
    )
    totals["old_sample_multiset_overlap_fraction"] = (
        totals["old_sample_multiset_overlap"] / max(1, totals["baseline_draws"])
    )
    return {
        "per_epoch": per_epoch,
        "totals": totals,
        "target_group_draws_all_epochs": dict(sorted(target_groups.items())),
        "target_group_draw_min": min(target_groups.values()) if target_groups else 0,
        "target_group_draw_max": max(target_groups.values()) if target_groups else 0,
        "interpretation": (
            "exact_index_replay"
            if totals["candidate_old_draws"] == totals["baseline_draws"]
            and totals["exact_old_filtered_position_matches"]
            == totals["baseline_draws"]
            else "expected_volume_only_not_exact_index_replay"
        ),
    }


def parse_candidate(value: str) -> tuple[str, Path]:
    label, separator, raw_path = value.partition("=")
    if not separator or not label or not raw_path:
        raise argparse.ArgumentTypeError("Candidate must be LABEL=CONFIG_PATH")
    return label, Path(raw_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument(
        "--candidate", action="append", required=True, type=parse_candidate
    )
    parser.add_argument("--target-dataset-id", default="riceseg")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if args.epochs <= 0:
        raise ValueError("epochs must be positive")
    baseline_path = args.baseline.resolve()
    baseline_config = load_mapping(baseline_path)
    baseline_epochs, baseline_summary = sampled_epochs(
        baseline_config, args.epochs
    )
    candidates: dict[str, Any] = {}
    for label, candidate_path_value in args.candidate:
        if label in candidates:
            raise ValueError(f"Duplicate candidate label: {label}")
        candidate_path = candidate_path_value.resolve()
        candidate_config = load_mapping(candidate_path)
        candidate_epochs, candidate_summary = sampled_epochs(
            candidate_config, args.epochs
        )
        candidates[label] = {
            "config": str(candidate_path),
            "config_sha256": sha256(candidate_path),
            "stream": candidate_summary,
            "comparison_to_baseline": compare_streams(
                baseline_epochs,
                candidate_epochs,
                args.target_dataset_id,
            ),
        }

    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "role": "riceseg_sampler_stream_replay_audit",
        "source_tree_sha256": source_tree_sha256(),
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
        "epochs": args.epochs,
        "target_dataset_id": args.target_dataset_id,
        "baseline": {
            "config": str(baseline_path),
            "config_sha256": sha256(baseline_path),
            "stream": baseline_summary,
        },
        "candidates": candidates,
        "sampler_contract": (
            "dataset -> field/session group -> image; groups are uniform within "
            "each dataset and row count does not determine group probability"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
