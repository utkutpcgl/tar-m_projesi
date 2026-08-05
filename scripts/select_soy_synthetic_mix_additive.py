#!/usr/bin/env python3
"""Apply the soybean additive gate to an explicitly balanced synthetic mix."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import select_soy_synthetic_additive as implementation


base_validate_recipe = implementation.validate_recipe


def validate_mix_recipe(
    protocol: dict[str, Any], candidate: str, run_dir: Path
) -> dict[str, Any]:
    soy_ids = [str(value) for value in protocol["soy_synthetic_dataset_ids"]]
    if len(soy_ids) < 2 or len(set(soy_ids)) != len(soy_ids):
        raise ValueError("The balanced mix requires at least two unique soy datasets")

    # Reuse every frozen check in the single-domain selector, with the first
    # component acting only as its backward-compatible presence sentinel.
    adapted = dict(protocol)
    adapted["soy_synthetic_dataset_id"] = soy_ids[0]
    recipe = base_validate_recipe(adapted, candidate, run_dir)
    weights = {
        str(name): float(value) for name, value in recipe["dataset_weights"].items()
    }
    draws = {
        str(name): float(value)
        for name, value in recipe["expected_draws_per_epoch"].items()
    }
    expected_component_draws = float(protocol["soy_component_draws_per_epoch"])
    is_additive = candidate == str(protocol["additive_candidate"])
    if is_additive:
        for dataset_id in soy_ids:
            if dataset_id not in weights or weights[dataset_id] <= 0.0:
                raise ValueError(f"Missing positive soybean-mix exposure: {dataset_id}")
            if not math.isclose(
                draws[dataset_id], expected_component_draws, abs_tol=1e-9
            ):
                raise ValueError(f"Unbalanced soybean-mix draws: {dataset_id}")
    else:
        for dataset_id in soy_ids:
            if weights.get(dataset_id, 0.0) != 0.0:
                raise ValueError(f"Control has soybean-mix exposure: {dataset_id}")

    exposure_by_dataset = {
        dataset_id: weights.get(dataset_id, 0.0) for dataset_id in soy_ids
    }
    draws_by_dataset = {
        dataset_id: draws.get(dataset_id, 0.0) for dataset_id in soy_ids
    }
    recipe.update(
        {
            "soy_synthetic_dataset_ids": soy_ids,
            "soy_synthetic_exposure_by_dataset": exposure_by_dataset,
            "soy_synthetic_draws_per_epoch_by_dataset": draws_by_dataset,
            "soy_synthetic_exposure": sum(exposure_by_dataset.values()),
            "soy_synthetic_draws_per_epoch": sum(draws_by_dataset.values()),
        }
    )
    return recipe


if __name__ == "__main__":
    implementation.validate_recipe = validate_mix_recipe
    # Ensure the generated receipt locks this wrapper, not the imported base.
    implementation.__file__ = __file__
    implementation.main()
