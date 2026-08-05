#!/usr/bin/env python3
"""Select and verify Sbest from 12 completed fixed-update real-val runs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from pathlib import Path


CONDITIONS = ("R_ONLY", "R_S025", "R_S050", "R_S100")
CANDIDATES = ("R_S025", "R_S050", "R_S100")
SEEDS = (17, 29, 43)


def fail(message: str) -> None:
    raise SystemExit(f"Sbest selection contract failed: {message}")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_matrix_lock(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("status") != "PASS":
        fail("standard matrix lock schema/status is invalid")
    conditions = payload.get("conditions")
    if not isinstance(conditions, dict) or set(conditions) != set(CONDITIONS):
        fail("standard matrix lock condition set is invalid")
    return payload


def resolve_record_path(value: str, parent: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = parent / path
    return path.resolve()


def verify_run_contract(
    path: Path,
    condition: str,
    seed: int,
    expected_composition_sha: str,
    expected_runs_root: Path | None = None,
) -> dict[str, object]:
    if not path.is_file():
        fail(f"missing run contract: {path}")
    if path.parent.name != "contracts":
        fail(f"run contract must be under a RUNS_ROOT/contracts directory: {path}")
    runs_root = path.parent.parent.resolve()
    if expected_runs_root and runs_root != expected_runs_root.resolve():
        fail(f"run contract is outside the selected RUNS_ROOT: {path}")

    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("status") != "PASS":
        fail(f"run contract is not PASS: {path}")
    if contract.get("condition") != condition or contract.get("seed") != seed:
        fail(f"run contract condition/seed mismatch: {path}")

    composition_path = resolve_record_path(
        str(contract.get("composition_audit", "")), path.parent
    )
    if not composition_path.is_file():
        fail(f"missing run composition audit: {composition_path}")
    if sha256_file(composition_path) != contract.get("composition_audit_sha256"):
        fail(f"run composition audit SHA mismatch: {composition_path}")
    composition = json.loads(composition_path.read_text(encoding="utf-8"))
    if composition.get("composition_csv_sha256") != expected_composition_sha:
        fail(f"run composition is not the matrix-locked {condition} composition")

    checkpoint = resolve_record_path(
        str(contract.get("primary_checkpoint", "")), path.parent
    )
    if not checkpoint.is_file():
        fail(f"missing primary last.pt: {checkpoint}")
    if sha256_file(checkpoint) != contract.get("primary_checkpoint_sha256"):
        fail(f"primary checkpoint SHA mismatch: {checkpoint}")

    return {
        "contract": contract,
        "contract_sha256": sha256_file(path),
        "contract_path": str(path),
        "composition_audit_path": str(composition_path),
        "checkpoint_path": str(checkpoint),
        "checkpoint_sha256": contract["primary_checkpoint_sha256"],
        "runs_root": str(runs_root),
    }


def parse_metrics(
    path: Path, matrix_lock: dict[str, object]
) -> tuple[list[dict[str, object]], Path]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "condition",
            "seed",
            "rfid_ap50_95",
            "rfid_recall",
            "run_contract",
        }
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            fail(
                "metrics CSV needs condition,seed,rfid_ap50_95,"
                "rfid_recall,run_contract headers"
            )
        raw_rows = list(reader)

    expected_keys = {(condition, seed) for condition in CONDITIONS for seed in SEEDS}
    observed_keys: set[tuple[str, int]] = set()
    records: list[dict[str, object]] = []
    runs_root: Path | None = None
    matrix_conditions = matrix_lock["conditions"]
    assert isinstance(matrix_conditions, dict)

    for line_number, row in enumerate(raw_rows, start=2):
        condition = (row.get("condition") or "").strip()
        try:
            seed = int((row.get("seed") or "").strip())
            ap = float((row.get("rfid_ap50_95") or "").strip())
            recall = float((row.get("rfid_recall") or "").strip())
        except ValueError:
            fail(f"metrics CSV line {line_number} has invalid numeric data")
        key = (condition, seed)
        if key not in expected_keys:
            fail(f"metrics CSV line {line_number} has unexpected condition/seed: {key}")
        if key in observed_keys:
            fail(f"duplicate metrics row: {key}")
        observed_keys.add(key)
        if not (0.0 <= ap <= 1.0 and 0.0 <= recall <= 1.0):
            fail(f"metrics must use 0..1 scale: {key}")

        contract_path = Path((row.get("run_contract") or "").strip())
        if not contract_path.is_absolute():
            contract_path = path.parent / contract_path
        contract_path = contract_path.resolve()
        expected_composition_sha = matrix_conditions[condition][
            "composition_csv_sha256"
        ]
        verified = verify_run_contract(
            contract_path,
            condition,
            seed,
            expected_composition_sha,
            runs_root,
        )
        current_root = Path(str(verified["runs_root"]))
        if runs_root is None:
            runs_root = current_root
        record = {
            "condition": condition,
            "seed": seed,
            "rfid_ap50_95": ap,
            "rfid_recall": recall,
            "run_contract": str(contract_path),
            "run_contract_sha256": verified["contract_sha256"],
            "primary_checkpoint": verified["checkpoint_path"],
            "primary_checkpoint_sha256": verified["checkpoint_sha256"],
        }
        records.append(record)

    if observed_keys != expected_keys:
        missing = sorted(expected_keys - observed_keys)
        fail(f"metrics CSV does not contain exactly 12 standard runs; missing={missing}")
    assert runs_root is not None

    update_budgets = {
        json.loads(Path(str(record["run_contract"])).read_text(encoding="utf-8")).get(
            "target_optimizer_updates"
        )
        for record in records
    }
    if len(update_budgets) != 1 or None in update_budgets:
        fail("12 run contracts do not share one target_optimizer_updates value")
    return records, runs_root


def summarize_and_select(
    records: list[dict[str, object]]
) -> tuple[dict[str, dict[str, float]], str]:
    summary: dict[str, dict[str, float]] = {}
    for condition in CONDITIONS:
        rows = [row for row in records if row["condition"] == condition]
        summary[condition] = {
            "rfid_ap50_95_median": statistics.median(
                float(row["rfid_ap50_95"]) for row in rows
            ),
            "rfid_recall_median": statistics.median(
                float(row["rfid_recall"]) for row in rows
            ),
        }
    lower_dose_preference = {"R_S025": 2, "R_S050": 1, "R_S100": 0}
    selected = max(
        CANDIDATES,
        key=lambda condition: (
            summary[condition]["rfid_ap50_95_median"],
            summary[condition]["rfid_recall_median"],
            lower_dose_preference[condition],
        ),
    )
    return summary, selected


def create_ledger(
    metrics_path: Path, matrix_path: Path, output: Path
) -> dict[str, object]:
    if output.exists():
        fail(f"immutable output already exists: {output}")
    matrix = load_matrix_lock(matrix_path)
    records, runs_root = parse_metrics(metrics_path, matrix)
    summary, selected = summarize_and_select(records)
    payload: dict[str, object] = {
        "schema_version": 1,
        "status": "PASS",
        "selection_rule": (
            "highest three-seed median real-val RFID AP50-95; "
            "tie: higher median RFID recall; tie: lower synthetic dose"
        ),
        "selected_condition": selected,
        "standard_matrix_lock": str(matrix_path.resolve()),
        "standard_matrix_lock_sha256": sha256_file(matrix_path),
        "metrics_csv": str(metrics_path.resolve()),
        "metrics_csv_sha256": sha256_file(metrics_path),
        "runs_root": str(runs_root),
        "condition_summary": summary,
        "run_records": sorted(
            records, key=lambda row: (str(row["condition"]), int(row["seed"]))
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def verify_ledger(
    ledger_path: Path,
    matrix_path: Path,
    sbest_composition: Path,
    runs_root: Path,
) -> dict[str, object]:
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    if ledger.get("schema_version") != 1 or ledger.get("status") != "PASS":
        fail("selection ledger schema/status is invalid")
    if ledger.get("standard_matrix_lock_sha256") != sha256_file(matrix_path):
        fail("selection ledger does not match the current standard matrix lock")
    if Path(str(ledger.get("runs_root", ""))).resolve() != runs_root.resolve():
        fail("selection ledger RUNS_ROOT differs from the current RUNS_ROOT")

    metrics_path = Path(str(ledger.get("metrics_csv", "")))
    if not metrics_path.is_file() or sha256_file(metrics_path) != ledger.get(
        "metrics_csv_sha256"
    ):
        fail("selection metrics CSV is missing or changed")

    matrix = load_matrix_lock(matrix_path)
    records, parsed_root = parse_metrics(metrics_path, matrix)
    if parsed_root.resolve() != runs_root.resolve():
        fail("recomputed run-contract root differs from current RUNS_ROOT")
    summary, selected = summarize_and_select(records)
    if selected != ledger.get("selected_condition"):
        fail("recomputed Sbest differs from selection ledger")
    if summary != ledger.get("condition_summary"):
        fail("recomputed val summary differs from selection ledger")

    expected_records = sorted(
        records, key=lambda row: (str(row["condition"]), int(row["seed"]))
    )
    if expected_records != ledger.get("run_records"):
        fail("recomputed run/checkpoint records differ from selection ledger")

    conditions = matrix["conditions"]
    assert isinstance(conditions, dict)
    expected_composition_sha = conditions[selected]["composition_csv_sha256"]
    if not sbest_composition.is_file() or sha256_file(
        sbest_composition
    ) != expected_composition_sha:
        fail("provided Sbest composition is not the matrix-locked selected dose")

    return {
        "status": "PASS",
        "selected_condition": selected,
        "sbest_composition_csv_sha256": expected_composition_sha,
        "selection_ledger_sha256": sha256_file(ledger_path),
        "standard_matrix_lock_sha256": sha256_file(matrix_path),
        "runs_root": str(runs_root.resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics-csv", type=Path)
    parser.add_argument("--matrix-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-ledger", type=Path)
    parser.add_argument("--sbest-composition", type=Path)
    parser.add_argument("--runs-root", type=Path)
    args = parser.parse_args()

    if not args.matrix_lock.is_file():
        fail(f"missing matrix lock: {args.matrix_lock}")
    if args.verify_ledger:
        if not args.verify_ledger.is_file():
            fail(f"missing selection ledger: {args.verify_ledger}")
        if not args.sbest_composition or not args.runs_root:
            fail("--verify-ledger requires --sbest-composition and --runs-root")
        payload = verify_ledger(
            args.verify_ledger.resolve(),
            args.matrix_lock.resolve(),
            args.sbest_composition.resolve(),
            args.runs_root.resolve(),
        )
    else:
        if not args.metrics_csv or not args.output:
            fail("creation requires --metrics-csv and --output")
        if not args.metrics_csv.is_file():
            fail(f"missing metrics CSV: {args.metrics_csv}")
        payload = create_ledger(
            args.metrics_csv.resolve(),
            args.matrix_lock.resolve(),
            args.output.resolve(),
        )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
