#!/usr/bin/env python3
"""Audit a candidate manifest against existing data, independent of split names."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path

from agri_seg.manifest import SampleRecord, manifest_sha256, read_manifest
from agri_seg.prepare import _difference_hash


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_image(record: SampleRecord, data_root: Path) -> Path:
    path = Path(record.image_path)
    resolved = path if path.is_absolute() else data_root / path
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved.resolve()


def fingerprints(
    records: list[SampleRecord], data_root: Path
) -> list[tuple[SampleRecord, str, int]]:
    cache: dict[Path, tuple[str, int]] = {}
    result: list[tuple[SampleRecord, str, int]] = []
    for record in records:
        path = resolve_image(record, data_root)
        if path not in cache:
            cache[path] = (sha256(path), _difference_hash(path))
        exact, difference = cache[path]
        result.append((record, exact, difference))
    return result


def match_payload(
    left: SampleRecord,
    right: SampleRecord,
    exact: bool,
    hamming: int,
) -> dict[str, object]:
    return {
        "candidate": left.sample_id,
        "candidate_split": left.split,
        "reference": right.sample_id,
        "reference_dataset": right.dataset_id,
        "reference_split": right.split,
        "sha256_exact": exact,
        "dhash_hamming": hamming,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_manifest")
    parser.add_argument("reference_manifests", nargs="+")
    parser.add_argument("--data-root", required=True)
    parser.add_argument("--max-hamming", type=int, default=2)
    parser.add_argument("--output", required=True)
    arguments = parser.parse_args()

    data_root = Path(arguments.data_root).expanduser().resolve()
    candidate_path = Path(arguments.candidate_manifest).expanduser().resolve()
    reference_paths = [
        Path(path).expanduser().resolve() for path in arguments.reference_manifests
    ]
    candidate_records = read_manifest(candidate_path)
    reference_records: list[SampleRecord] = []
    for path in reference_paths:
        reference_records.extend(read_manifest(path))
    candidate_ids = {record.sample_id for record in candidate_records}
    reference_ids = {record.sample_id for record in reference_records}
    overlap_ids = candidate_ids & reference_ids
    if overlap_ids:
        raise ValueError(
            f"Candidate is already present in reference manifests: {sorted(overlap_ids)[:5]}"
        )

    candidate = fingerprints(candidate_records, data_root)
    reference = fingerprints(reference_records, data_root)
    candidate_to_reference: list[dict[str, object]] = []
    nearest: list[int] = []
    for candidate_record, candidate_exact, candidate_hash in candidate:
        nearest_distance = 256
        for reference_record, reference_exact, reference_hash in reference:
            distance = (candidate_hash ^ reference_hash).bit_count()
            nearest_distance = min(nearest_distance, distance)
            exact_match = candidate_exact == reference_exact
            if exact_match or distance <= arguments.max_hamming:
                candidate_to_reference.append(
                    match_payload(
                        candidate_record,
                        reference_record,
                        exact_match,
                        distance,
                    )
                )
        nearest.append(nearest_distance)

    within_candidate: list[dict[str, object]] = []
    for index, (left, left_exact, left_hash) in enumerate(candidate):
        for right, right_exact, right_hash in candidate[index + 1 :]:
            distance = (left_hash ^ right_hash).bit_count()
            exact_match = left_exact == right_exact
            if exact_match or distance <= arguments.max_hamming:
                within_candidate.append(
                    match_payload(left, right, exact_match, distance)
                )

    within_candidate_cross_split = [
        match
        for match in within_candidate
        if match["candidate_split"] != match["reference_split"]
    ]
    within_candidate_same_split = [
        match
        for match in within_candidate
        if match["candidate_split"] == match["reference_split"]
    ]

    report = {
        "schema_version": 2,
        "hash": "SHA-256 exact plus dHash-256 near",
        "max_hamming": arguments.max_hamming,
        "scope": {
            "candidate_manifest": str(candidate_path),
            "candidate_manifest_sha256": manifest_sha256(candidate_path),
            "candidate_samples": len(candidate_records),
            "candidate_dataset_counts": dict(
                Counter(record.dataset_id for record in candidate_records)
            ),
            "reference_manifests": [
                {"path": str(path), "sha256": manifest_sha256(path)}
                for path in reference_paths
            ],
            "reference_samples": len(reference_records),
            "reference_dataset_counts": dict(
                Counter(record.dataset_id for record in reference_records)
            ),
        },
        "candidate_to_reference_match_count": len(candidate_to_reference),
        "candidate_to_reference_matches": candidate_to_reference,
        "candidate_to_reference_nearest_hamming": {
            "min": min(nearest),
            "median": statistics.median(nearest),
            "max": max(nearest),
        },
        "within_candidate_match_count": len(within_candidate),
        "within_candidate_matches": within_candidate,
        "within_candidate_cross_split_match_count": len(
            within_candidate_cross_split
        ),
        "within_candidate_cross_split_matches": within_candidate_cross_split,
        "within_candidate_same_split_match_count": len(within_candidate_same_split),
        "script_sha256": sha256(Path(__file__).resolve()),
        "passed": not candidate_to_reference and not within_candidate_cross_split,
        "note": (
            "The pass gate rejects cross-dataset and cross-split exact/near copies. "
            "Same-split near frames remain reported as a correlation warning; "
            "trajectory, field, and temporal independence require metadata gates."
        ),
    }
    output = Path(arguments.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
