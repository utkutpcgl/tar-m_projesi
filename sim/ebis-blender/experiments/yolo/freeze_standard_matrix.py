#!/usr/bin/env python3
"""Freeze and verify the nested four-condition EBIS standard-dose matrix."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from validate_ablation_composition import (
    load_composition,
    sha256_file,
    sha256_paths,
    validate_standard,
)


CONDITIONS = ("R_ONLY", "R_S025", "R_S050", "R_S100")


def fail(message: str) -> None:
    raise SystemExit(f"standard matrix contract failed: {message}")


def create_lock(paths: dict[str, Path], output: Path) -> dict[str, object]:
    if output.exists():
        fail(f"immutable output already exists: {output}")

    condition_payload: dict[str, dict[str, object]] = {}
    sets_by_condition: dict[str, dict[str, set[str]]] = {}
    for condition in CONDITIONS:
        path = paths[condition].resolve()
        if not path.is_file():
            fail(f"missing {condition} composition CSV: {path}")
        rows = load_composition(path)
        sets = validate_standard(condition, rows, condition)
        sets_by_condition[condition] = sets
        condition_payload[condition] = {
            "composition_csv": str(path),
            "composition_csv_sha256": sha256_file(path),
            "real_count": len(sets["real"]),
            "standard_synthetic_count": len(sets["standard"]),
            "standard_synthetic_set_sha256": sha256_paths(sets["standard"]),
        }

    real_sets = [sets_by_condition[name]["real"] for name in CONDITIONS]
    if any(candidate != real_sets[0] for candidate in real_sets[1:]):
        fail("all four conditions must use the exact same real image set")
    if sets_by_condition["R_ONLY"]["standard"]:
        fail("R_ONLY must not contain synthetic images")

    s025 = sets_by_condition["R_S025"]["standard"]
    s050 = sets_by_condition["R_S050"]["standard"]
    s100 = sets_by_condition["R_S100"]["standard"]
    if not s025.issubset(s050):
        fail("R_S025 synthetic set is not a subset of R_S050")
    if not s050.issubset(s100):
        fail("R_S050 synthetic set is not a subset of R_S100")

    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "PASS",
        "real_count": len(real_sets[0]),
        "real_set_sha256": sha256_paths(real_sets[0]),
        "dose_rounding": "exact; frozen real N is divisible by 20",
        "nesting": "R_S025 subset R_S050 subset R_S100",
        "conditions": condition_payload,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def verify_condition(
    lock_path: Path, condition: str, composition_path: Path
) -> dict[str, object]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1 or lock.get("status") != "PASS":
        fail("matrix lock schema/status is invalid")
    conditions = lock.get("conditions")
    if not isinstance(conditions, dict) or condition not in conditions:
        fail(f"condition is absent from matrix lock: {condition}")
    composition_path = composition_path.resolve()
    if not composition_path.is_file():
        fail(f"missing composition CSV: {composition_path}")
    expected = conditions[condition].get("composition_csv_sha256")
    actual = sha256_file(composition_path)
    if actual != expected:
        fail(f"{condition} composition SHA does not match matrix lock")
    return {
        "status": "PASS",
        "condition": condition,
        "matrix_lock": str(lock_path.resolve()),
        "matrix_lock_sha256": sha256_file(lock_path),
        "composition_csv_sha256": actual,
        "real_set_sha256": lock.get("real_set_sha256"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--r-only", type=Path)
    parser.add_argument("--r-s025", type=Path)
    parser.add_argument("--r-s050", type=Path)
    parser.add_argument("--r-s100", type=Path)
    parser.add_argument("--verify-lock", type=Path)
    parser.add_argument("--condition", choices=CONDITIONS)
    parser.add_argument("--composition-csv", type=Path)
    args = parser.parse_args()

    if args.verify_lock:
        if not args.condition or not args.composition_csv:
            fail("--verify-lock requires --condition and --composition-csv")
        if not args.verify_lock.is_file():
            fail(f"missing matrix lock: {args.verify_lock}")
        payload = verify_condition(
            args.verify_lock.resolve(), args.condition, args.composition_csv
        )
    else:
        required = {
            "R_ONLY": args.r_only,
            "R_S025": args.r_s025,
            "R_S050": args.r_s050,
            "R_S100": args.r_s100,
        }
        if not args.output or any(path is None for path in required.values()):
            fail("creation requires --output and all four composition CSV options")
        payload = create_lock(
            {name: path for name, path in required.items() if path is not None},
            args.output.resolve(),
        )

    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
