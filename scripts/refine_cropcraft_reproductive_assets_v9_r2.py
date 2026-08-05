#!/usr/bin/env python3
"""Build reproductive-rice R2 after R1 failed the manual morphology gate.

R2 keeps the frozen R5 base surfaces and the same three traceable texture
sources.  It changes only reproductive rice morphology/material parameters:
shared distichous tiller axes, denser gravity-dropped panicles, and darker,
more visible grains.  The rejected R1 pack and review remain immutable.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Any

import numpy as np

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from build_cropcraft_agri_assets import Mesh, sha256  # noqa: E402
import build_cropcraft_reproductive_assets_v9 as r1  # noqa: E402


PACK_ID = "cropcraft_paddy_reproductive_v9_r2"
ORIGINAL_MATERIAL_PALETTE = r1.material_palette


def dense_drooping_panicle(
    mesh: Mesh,
    rng: random.Random,
    origin: tuple[float, float, float],
    azimuth: float,
    target_height: float,
    stage_index: int,
    rachis_material: str,
    grain_material: str,
) -> tuple[int, int]:
    """Add a full, gravity-bent panicle closer to reviewed RiceSEG examples."""

    maturity = (stage_index - 1) / 3.0
    lean = target_height * rng.uniform(0.085, 0.145) * (0.90 + 0.25 * maturity)
    panicle_height = target_height * rng.uniform(0.145, 0.195)
    direction = np.array([math.cos(azimuth), math.sin(azimuth), 0.0])
    side = np.array([-math.sin(azimuth), math.cos(azimuth), 0.0])
    p0 = np.asarray(origin, dtype=np.float64)
    p1 = p0 + direction * lean * 0.23 + np.array(
        [0.0, 0.0, panicle_height * 0.46]
    )
    p2 = p0 + direction * lean * 0.61 + side * rng.uniform(-0.012, 0.012) + np.array(
        [0.0, 0.0, panicle_height * (0.78 - 0.10 * maturity)]
    )
    p3 = p0 + direction * lean + np.array(
        [0.0, 0.0, panicle_height * (0.98 - 0.58 * maturity)]
    )
    r1._tube_chain(
        mesh,
        [tuple(p0), tuple(p1), tuple(p2), tuple(p3)],
        target_height * 0.0035,
        rachis_material,
        sides=7,
    )

    branches = rng.randint(7, 10)
    grains_total = 0
    for branch_index in range(branches):
        fraction = 0.12 + 0.76 * branch_index / max(1, branches - 1)
        if fraction < 0.46:
            start = p0 + (p1 - p0) * (fraction / 0.46)
        elif fraction < 0.72:
            start = p1 + (p2 - p1) * ((fraction - 0.46) / 0.26)
        else:
            start = p2 + (p3 - p2) * ((fraction - 0.72) / 0.28)
        branch_azimuth = (
            azimuth
            + math.pi * 0.5
            + branch_index * math.radians(137.5)
            + rng.uniform(-0.12, 0.12)
        )
        branch_dir = np.array(
            [math.cos(branch_azimuth), math.sin(branch_azimuth), 0.0],
            dtype=np.float64,
        )
        branch_length = target_height * rng.uniform(0.075, 0.125) * (
            1.10 - 0.28 * fraction
        )
        gravity = target_height * (0.025 + 0.055 * maturity)
        mid = start + branch_dir * branch_length * 0.50
        mid[2] -= gravity * 0.32
        end = start + branch_dir * branch_length
        end[2] -= gravity * rng.uniform(0.85, 1.18)
        r1._tube_chain(
            mesh,
            [tuple(start), tuple(mid), tuple(end)],
            target_height * 0.0017,
            rachis_material,
            sides=6,
        )

        grain_count = rng.randint(12, 17)
        grains_total += grain_count
        lateral = np.array([-branch_dir[1], branch_dir[0], 0.0], dtype=np.float64)
        for grain_index in range(grain_count):
            t = 0.10 + 0.86 * grain_index / max(1, grain_count - 1)
            if t <= 0.50:
                center = start + (mid - start) * (t / 0.50)
            else:
                center = mid + (end - mid) * ((t - 0.50) / 0.50)
            alternating = -1.0 if grain_index % 2 else 1.0
            center = center + lateral * alternating * target_height * rng.uniform(
                0.0028, 0.0058
            )
            center[2] -= target_height * rng.uniform(0.004, 0.011)
            grain_axis = tuple(
                branch_dir * rng.uniform(0.08, 0.22)
                + np.array([0.0, 0.0, -1.0], dtype=np.float64)
            )
            r1.add_oriented_ellipsoid(
                mesh,
                tuple(center),
                grain_axis,
                target_height * rng.uniform(0.0057, 0.0076),
                target_height * rng.uniform(0.0024, 0.0032),
                grain_material,
                rings=3,
                sides=6,
            )
    return branches, grains_total


def reproductive_rice_mesh_r2(
    seed: int, target_height: float, stage_index: int
) -> tuple[Mesh, dict[str, Any]]:
    if stage_index not in range(1, 5):
        raise ValueError(f"Unsupported reproductive stage: {stage_index}")
    rng = random.Random(seed)
    mesh = Mesh()
    prefix = f"rice_reproductive_v9_{seed}"
    stem_material = f"{prefix}_stem"
    leaf_material = f"{prefix}_leaf"
    midrib_material = f"{prefix}_midrib"
    rachis_material = f"{prefix}_rachis"
    grain_material = f"{prefix}_grain"

    tiller_min = (4, 5, 5, 5)[stage_index - 1]
    tiller_max = (5, 6, 7, 7)[stage_index - 1]
    panicle_min = (2, 3, 4, 5)[stage_index - 1]
    panicle_max = (3, 4, 5, 6)[stage_index - 1]
    tiller_count = rng.randint(tiller_min, tiller_max)
    panicle_count = min(tiller_count, rng.randint(panicle_min, panicle_max))
    dominant_axis = rng.uniform(0.0, math.tau)
    total_leaves = 0
    total_branches = 0
    total_grains = 0
    widths: list[float] = []
    elevations: list[float] = []
    fan_deviations: list[float] = []

    for tiller in range(tiller_count):
        fan_deviation = rng.gauss(0.0, math.radians(25.0))
        fan_axis = dominant_axis + fan_deviation
        fan_deviations.append(math.degrees(fan_deviation))
        axial = target_height * rng.gauss(0.0, 0.018)
        lateral = target_height * rng.gauss(0.0, 0.035)
        axis_direction = np.array(
            [math.cos(dominant_axis), math.sin(dominant_axis)], dtype=np.float64
        )
        cross_direction = np.array([-axis_direction[1], axis_direction[0]])
        offset = axis_direction * axial + cross_direction * lateral
        base = (float(offset[0]), float(offset[1]), 0.0)
        culm_height = target_height * rng.uniform(0.72, 0.82)
        lean = target_height * rng.uniform(0.015, 0.055)
        middle = (
            base[0] + 0.35 * lean * math.cos(fan_axis),
            base[1] + 0.35 * lean * math.sin(fan_axis),
            culm_height * 0.52,
        )
        top = (
            base[0] + lean * math.cos(fan_axis),
            base[1] + lean * math.sin(fan_axis),
            culm_height,
        )
        r1._tube_chain(
            mesh,
            [base, middle, top],
            target_height * rng.uniform(0.0062, 0.0084),
            stem_material,
            sides=10,
        )

        leaves = rng.randint(5, 8)
        total_leaves += leaves
        for leaf_index in range(leaves):
            rank = leaf_index / max(1, leaves - 1)
            side_angle = 0.0 if leaf_index % 2 == 0 else math.pi
            azimuth = fan_axis + side_angle + rng.gauss(0.0, math.radians(9.0))
            leaf_length = target_height * rng.uniform(0.31, 0.52) * (
                1.10 - 0.24 * rank
            )
            elevation_deg = rng.uniform(23.0 + 18.0 * rank, 45.0 + 19.0 * rank)
            width_ratio = rng.uniform(0.018, 0.030)
            widths.append(width_ratio)
            elevations.append(elevation_deg)
            maturity = (stage_index - 1) / 3.0
            mesh.add_blade(
                (
                    base[0] + lean * 0.4 * rank * math.cos(fan_axis),
                    base[1] + lean * 0.4 * rank * math.sin(fan_axis),
                    culm_height * (0.12 + 0.65 * rank),
                ),
                leaf_length,
                azimuth,
                math.radians(elevation_deg),
                leaf_length * width_ratio,
                rng.uniform(0.06, 0.15),
                rng.uniform(0.040, 0.100) + 0.075 * maturity,
                rng.uniform(-0.20, 0.20),
                rng.uniform(0.15, 0.26),
                leaf_material,
                midrib_material,
                segments=30,
                profile_power=0.80,
            )

        if tiller < panicle_count:
            branches, grains = dense_drooping_panicle(
                mesh,
                rng,
                top,
                fan_axis + rng.uniform(-0.32, 0.32),
                target_height,
                stage_index,
                rachis_material,
                grain_material,
            )
            total_branches += branches
            total_grains += grains

    mesh.scale_to_height(target_height)
    morphology = {
        "architecture": "shared_axis_distichous_dense_drooping_panicle",
        "target_height_m": target_height,
        "tiller_count": tiller_count,
        "leaf_count": total_leaves,
        "panicle_count": panicle_count,
        "panicle_branch_count": total_branches,
        "grain_count": total_grains,
        "leaf_half_width_to_length_min": min(widths),
        "leaf_half_width_to_length_max": max(widths),
        "leaf_elevation_deg_min": min(elevations),
        "leaf_elevation_deg_max": max(elevations),
        "tiller_fan_deviation_deg_min": min(fan_deviations),
        "tiller_fan_deviation_deg_max": max(fan_deviations),
    }
    return mesh, morphology


def material_palette_r2(
    seed: int, phenotype: str, stage_index: int
) -> dict[str, tuple[tuple[float, float, float], float]]:
    materials = ORIGINAL_MATERIAL_PALETTE(seed, phenotype, stage_index)
    prefix = f"rice_reproductive_v9_{seed}"
    grain = {
        "heading_green": (0.20, 0.43, 0.08),
        "grain_fill_transition": (0.43, 0.46, 0.10),
        "mature_senescent": (0.60, 0.43, 0.13),
    }[phenotype]
    rachis = {
        "heading_green": (0.24, 0.45, 0.10),
        "grain_fill_transition": (0.40, 0.45, 0.11),
        "mature_senescent": (0.54, 0.41, 0.14),
    }[phenotype]
    materials[f"{prefix}_grain"] = (grain, 0.68)
    materials[f"{prefix}_rachis"] = (rachis, 0.62)
    return materials


def main() -> None:
    r1.PACK_ID = PACK_ID
    r1.reproductive_rice_mesh = reproductive_rice_mesh_r2
    r1.material_palette = material_palette_r2
    r1.main()

    output_index = sys.argv.index("--output") + 1
    destination = Path(sys.argv[output_index]).expanduser().resolve()
    manifest_path = destination / "PACK.json"
    pack = json.loads(manifest_path.read_text(encoding="utf-8"))
    pack["purpose"] = "R2 isolated late-reproductive rice contribution gate"
    pack["builder_script"] = str(Path(__file__).resolve())
    pack["builder_script_sha256"] = sha256(__file__)
    reproductive = pack["generated_assets"]["reproductive_crop"]
    reproductive.update(
        {
            "refinement_revision": "v9_r2",
            "refinement_control": {
                "pack_id": "cropcraft_paddy_reproductive_v9_r1",
                "pack_manifest_sha256": "5da41a4863067cbe602d6ccbedf0fe84e906c4306ecd77b37d669f54a665ace7",
                "manual_review_sha256": "607bc82381355e2f05efa404bd1cf9646145faec66e691a4cb5492fd13c5cad8",
                "decision": "rejected_before_pilot",
            },
            "morphology_changes": [
                "shared distichous tiller axis with bounded angular variance",
                "seven-to-ten longer gravity-dropped branches per panicle",
                "twelve-to-seventeen larger grains per branch",
                "lower-poly grains preserve render cost while increasing density",
                "darker stage-conditioned rachis and grain materials",
            ],
        }
    )
    extension = pack["paddy_v4_assets"]["full_cycle_extension"]
    extension["revision"] = "v9_r2"
    extension["refinement_reason"] = (
        "R1 numerical smoke passed, but manual review rejected sparse upright "
        "bead-like panicles and radial starburst clumps before the 100-frame pilot"
    )
    manifest_path.write_text(
        json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(destination),
                "final_pack_id": pack["pack_id"],
                "final_pack_manifest_sha256": sha256(manifest_path),
                "builder_script_sha256": pack["builder_script_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
