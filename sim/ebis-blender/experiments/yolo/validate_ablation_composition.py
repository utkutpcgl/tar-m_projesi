#!/usr/bin/env python3
"""Fail-fast audit for the EBIS YOLO train-manifest composition contract."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


STANDARD_CONDITIONS = {
    "R_ONLY": (0, 1),
    "R_S025": (1, 4),
    "R_S050": (1, 2),
    "R_S100": (1, 1),
}
HARD_CONDITION = "R_Sbest_HARD"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_paths(paths: set[str]) -> str:
    payload = "".join(f"{path}\n" for path in sorted(paths)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def fail(message: str) -> None:
    raise SystemExit(f"composition contract failed: {message}")


def load_manifest(path: Path) -> list[str]:
    rows = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    rows = [line for line in rows if line]
    if not rows:
        fail(f"empty train manifest: {path}")
    if len(rows) != len(set(rows)):
        fail(f"duplicate path in train manifest: {path}")
    for item in rows:
        image = Path(item)
        if not image.is_absolute() or not image.is_file():
            fail(f"manifest entry must be an existing absolute file: {item}")
    return rows


def load_composition(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"image_path", "source", "partition"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            fail(f"{path} needs CSV headers image_path,source,partition")
        rows = []
        seen: set[str] = set()
        for line_number, raw in enumerate(reader, start=2):
            row = {key: (raw.get(key) or "").strip() for key in required}
            image_path = row["image_path"]
            image = Path(image_path)
            if not image_path or not image.is_absolute() or not image.is_file():
                fail(f"{path}:{line_number} image_path must be an existing absolute file")
            if image_path in seen:
                fail(f"{path}:{line_number} duplicate image_path: {image_path}")
            seen.add(image_path)
            if row["source"] == "real":
                if row["partition"] != "real":
                    fail(f"{path}:{line_number} real source must use partition=real")
            elif row["source"] == "synthetic":
                if row["partition"] not in {"standard", "hard_occlusion"}:
                    fail(
                        f"{path}:{line_number} synthetic partition must be "
                        "standard or hard_occlusion"
                    )
            else:
                fail(f"{path}:{line_number} source must be real or synthetic")
            rows.append(row)
    if not rows:
        fail(f"empty composition CSV: {path}")
    return rows


def split_sets(rows: list[dict[str, str]]) -> dict[str, set[str]]:
    return {
        "real": {
            row["image_path"] for row in rows if row["source"] == "real"
        },
        "standard": {
            row["image_path"]
            for row in rows
            if row["source"] == "synthetic" and row["partition"] == "standard"
        },
        "hard_occlusion": {
            row["image_path"]
            for row in rows
            if row["source"] == "synthetic"
            and row["partition"] == "hard_occlusion"
        },
    }


def expected_synthetic(real_count: int, numerator: int, denominator: int) -> int:
    # Nearest integer, with an exact .5 rounded upward.
    return (2 * real_count * numerator + denominator) // (2 * denominator)


def validate_standard(
    condition: str, rows: list[dict[str, str]], label: str
) -> dict[str, set[str]]:
    if condition not in STANDARD_CONDITIONS:
        fail(f"invalid standard condition for {label}: {condition}")
    sets = split_sets(rows)
    real_count = len(sets["real"])
    if real_count == 0:
        fail(f"{label} contains no real training images")
    if real_count % 20:
        fail(
            f"{label} real image count N={real_count} must be divisible by 20 "
            "so 0.25/0.50/1.00 doses and exact 20% hard replacement are integral"
        )
    if sets["hard_occlusion"]:
        fail(f"{label} standard condition contains hard_occlusion images")
    numerator, denominator = STANDARD_CONDITIONS[condition]
    expected = expected_synthetic(real_count, numerator, denominator)
    actual = len(sets["standard"])
    if actual != expected:
        fail(
            f"{label} {condition} expects {expected} standard synthetic "
            f"images for N={real_count}, found {actual}"
        )
    return sets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--condition", required=True)
    parser.add_argument("--train-manifest", type=Path, required=True)
    parser.add_argument("--composition-csv", type=Path, required=True)
    parser.add_argument("--sbest-condition")
    parser.add_argument("--sbest-composition-csv", type=Path)
    args = parser.parse_args()

    if not args.train_manifest.is_file():
        fail(f"missing train manifest: {args.train_manifest}")
    if not args.composition_csv.is_file():
        fail(f"missing composition CSV: {args.composition_csv}")

    manifest_rows = load_manifest(args.train_manifest)
    composition_rows = load_composition(args.composition_csv)
    composition_paths = [row["image_path"] for row in composition_rows]
    if manifest_rows != composition_paths:
        fail("train manifest rows must exactly equal composition CSV image_path order")

    result: dict[str, object] = {
        "schema_version": 1,
        "condition": args.condition,
        "train_manifest_sha256": sha256_file(args.train_manifest),
        "composition_csv_sha256": sha256_file(args.composition_csv),
    }

    if args.condition in STANDARD_CONDITIONS:
        if args.sbest_condition or args.sbest_composition_csv:
            fail("Sbest arguments are forbidden for a standard condition")
        sets = validate_standard(args.condition, composition_rows, "candidate")
        result.update(
            {
                "real_count": len(sets["real"]),
                "synthetic_count": len(sets["standard"]),
                "standard_count": len(sets["standard"]),
                "hard_count": 0,
                "real_set_sha256": sha256_paths(sets["real"]),
                "synthetic_set_sha256": sha256_paths(sets["standard"]),
                "hard_replacement_fraction": 0.0,
            }
        )
    elif args.condition == HARD_CONDITION:
        if args.sbest_condition not in {"R_S025", "R_S050", "R_S100"}:
            fail("hard condition requires --sbest-condition R_S025/R_S050/R_S100")
        if not args.sbest_composition_csv or not args.sbest_composition_csv.is_file():
            fail("hard condition requires an existing --sbest-composition-csv")

        hard_sets = split_sets(composition_rows)
        sbest_rows = load_composition(args.sbest_composition_csv)
        sbest_sets = validate_standard(
            args.sbest_condition, sbest_rows, "selected standard dose"
        )

        if hard_sets["real"] != sbest_sets["real"]:
            fail("hard and selected-standard real image sets are not identical")
        sbest_synthetic = sbest_sets["standard"]
        hard_standard = hard_sets["standard"]
        hard_images = hard_sets["hard_occlusion"]
        synthetic_total = len(hard_standard) + len(hard_images)
        if synthetic_total != len(sbest_synthetic):
            fail(
                "hard condition must keep the selected standard condition's "
                "total synthetic count"
            )
        if synthetic_total == 0 or synthetic_total % 5:
            fail("selected synthetic count must be positive and divisible by 5")
        if len(hard_images) * 5 != synthetic_total:
            fail("hard_occlusion images must be exactly 20% of synthetic images")
        if not hard_standard.issubset(sbest_synthetic):
            fail("hard condition standard images must be retained from Sbest")
        removed = sbest_synthetic - hard_standard
        if len(removed) != len(hard_images):
            fail("hard image count must equal the number of replaced standard images")
        if hard_images & sbest_synthetic:
            fail("replacement hard images must not duplicate Sbest standard images")

        result.update(
            {
                "sbest_condition": args.sbest_condition,
                "sbest_composition_csv_sha256": sha256_file(
                    args.sbest_composition_csv
                ),
                "real_count": len(hard_sets["real"]),
                "synthetic_count": synthetic_total,
                "standard_count": len(hard_standard),
                "hard_count": len(hard_images),
                "real_set_sha256": sha256_paths(hard_sets["real"]),
                "synthetic_set_sha256": sha256_paths(
                    hard_standard | hard_images
                ),
                "sbest_synthetic_set_sha256": sha256_paths(sbest_synthetic),
                "hard_replacement_fraction": 0.2,
            }
        )
    else:
        fail(f"unknown condition: {args.condition}")

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
