#!/usr/bin/env python3
"""Verify the accepted/rejected synthetic asset portfolio and next-gate lock."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from agri_seg.engine import source_tree_sha256


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_equal(name: str, actual: object, expected: object) -> None:
    if actual != expected:
        raise ValueError(f"{name}: expected {expected!r}, got {actual!r}")


def resolve(project_root: Path, recorded: str) -> Path:
    path = Path(recorded).expanduser()
    return (path if path.is_absolute() else project_root / path).resolve()


def nested_value(payload: dict[str, Any], dotted_path: str) -> object:
    value: object = payload
    for component in dotted_path.split("."):
        if not isinstance(value, dict) or component not in value:
            raise KeyError(f"Missing JSON path {dotted_path!r} at {component!r}")
        value = value[component]
    return value


def verify_artifact(
    project_root: Path, specification: dict[str, Any], label: str
) -> dict[str, Any]:
    path = resolve(project_root, str(specification["path"]))
    if not path.is_file():
        raise FileNotFoundError(path)
    actual_hash = sha256(path)
    require_equal(f"{label} SHA", actual_hash, str(specification["sha256"]))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    observed: dict[str, object] = {}
    for dotted_path, expected in specification.get("checks", {}).items():
        actual = nested_value(payload, str(dotted_path))
        require_equal(f"{label} {dotted_path}", actual, expected)
        observed[str(dotted_path)] = actual
    return {"path": str(path), "sha256": actual_hash, "checks": observed}


def audit(config_path: Path) -> Path:
    config_path = config_path.expanduser().resolve()
    project_root = config_path.parents[2]
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"Expected YAML mapping: {config_path}")
    require_equal("schema version", config.get("schema_version"), 1)
    accepted = config["accepted_control"]
    require_equal("source tree", source_tree_sha256(), str(accepted["source_tree_sha256"]))
    checkpoint = resolve(project_root, str(accepted["checkpoint"]))
    if not checkpoint.is_file():
        raise FileNotFoundError(checkpoint)
    require_equal("accepted checkpoint SHA", sha256(checkpoint), str(accepted["checkpoint_sha256"]))

    entries: list[dict[str, Any]] = []
    asset_quality_passes = 0
    global_acceptances = 0
    global_rejections = 0
    for item in config["portfolio"]:
        entry = {
            "id": item["id"],
            "asset_domain": item["asset_domain"],
            "portfolio_status": item["portfolio_status"],
            "asset_quality": verify_artifact(project_root, item["asset_quality"], f"{item['id']} asset quality"),
            "model_gate": verify_artifact(project_root, item["model_gate"], f"{item['id']} model gate"),
        }
        for extra_name in ("supplemental_quality", "manual_quality"):
            if extra_name in item:
                entry[extra_name] = verify_artifact(
                    project_root, item[extra_name], f"{item['id']} {extra_name.replace('_', ' ')}"
                )
        asset_quality_passes += 1
        status = str(item["portfolio_status"])
        if status in {"accepted_component_superseded_by_paddy_mix", "accepted_global_control"}:
            global_acceptances += 1
        else:
            global_rejections += 1
        entries.append(entry)
    require_equal("portfolio entries", len(entries), 5)
    require_equal("asset-quality pass entries", asset_quality_passes, 5)
    require_equal("globally useful accepted stages", global_acceptances, 2)
    require_equal("global model-gate rejections", global_rejections, 3)
    require_equal("new generation lock", config["next_asset_gate"]["generation_authorized_now"], False)

    report = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "verified",
        "config": str(config_path),
        "config_sha256": sha256(config_path),
        "accepted_control": {
            "candidate": accepted["candidate"],
            "checkpoint": str(checkpoint),
            "checkpoint_sha256": sha256(checkpoint),
            "source_tree_sha256": source_tree_sha256(),
        },
        "portfolio_counts": {
            "asset_quality_passes": asset_quality_passes,
            "globally_useful_accepted_stages": global_acceptances,
            "global_model_gate_rejections": global_rejections,
        },
        "portfolio": entries,
        "next_asset_gate": config["next_asset_gate"],
        "new_asset_generated": False,
        "large_synthetic_batch_generated": False,
        "external_test_used": False,
        "model_retrained": False,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(Path(__file__).resolve()),
    }
    output = resolve(project_root, str(config["outputs"]["audit"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/simulation/synthetic_asset_portfolio_v8.yaml"))
    arguments = parser.parse_args()
    output = audit(arguments.config)
    print(json.dumps({"audit": str(output), "sha256": sha256(output)}, indent=2))


if __name__ == "__main__":
    main()
