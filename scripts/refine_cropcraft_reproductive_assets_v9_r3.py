#!/usr/bin/env python3
"""Build R3 with clustered herringbone panicles after R2 visual rejection.

The R2 leaf/tiller geometry, textures, scene recipe and random sequence are
preserved.  Only each panicle's internal branch/grain construction changes:
branches alternate in a gravity-bent plane and grain cross-sections are made
slightly more visible at the frozen 512 px camera distance.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import numpy as np

SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from build_cropcraft_agri_assets import Mesh, sha256  # noqa: E402
import build_cropcraft_reproductive_assets_v9 as r1  # noqa: E402
import refine_cropcraft_reproductive_assets_v9_r2 as r2  # noqa: E402


PACK_ID = "cropcraft_paddy_reproductive_v9_r3"
ORIGINAL_R2_PANICLE = r2.dense_drooping_panicle


def clustered_herringbone_panicle(
    mesh: Mesh,
    rng: random.Random,
    origin: tuple[float, float, float],
    azimuth: float,
    target_height: float,
    stage_index: int,
    rachis_material: str,
    grain_material: str,
) -> tuple[int, int]:
    """Replace the R2 radial plume with an alternating weighted rice panicle."""

    # Advance the parent RNG exactly as R2 did.  Later tillers/leaves therefore
    # remain byte-identical in their random parameters; only this panicle uses
    # the cloned pre-call state and a revised construction.
    cloned_state = rng.getstate()
    ORIGINAL_R2_PANICLE(
        Mesh(),
        rng,
        origin,
        azimuth,
        target_height,
        stage_index,
        rachis_material,
        grain_material,
    )
    local = random.Random()
    local.setstate(cloned_state)

    maturity = (stage_index - 1) / 3.0
    lean = target_height * local.uniform(0.095, 0.155) * (0.90 + 0.28 * maturity)
    panicle_height = target_height * local.uniform(0.145, 0.195)
    direction = np.array([math.cos(azimuth), math.sin(azimuth), 0.0])
    side = np.array([-math.sin(azimuth), math.cos(azimuth), 0.0])
    p0 = np.asarray(origin, dtype=np.float64)
    p1 = p0 + direction * lean * 0.24 + np.array(
        [0.0, 0.0, panicle_height * 0.48]
    )
    p2 = p0 + direction * lean * 0.62 + side * local.uniform(-0.008, 0.008) + np.array(
        [0.0, 0.0, panicle_height * (0.78 - 0.14 * maturity)]
    )
    p3 = p0 + direction * lean + np.array(
        [0.0, 0.0, panicle_height * (0.96 - 0.72 * maturity)]
    )
    r1._tube_chain(
        mesh,
        [tuple(p0), tuple(p1), tuple(p2), tuple(p3)],
        target_height * 0.0036,
        rachis_material,
        sides=7,
    )

    branches = local.randint(8, 11)
    grains_total = 0
    for branch_index in range(branches):
        fraction = 0.10 + 0.78 * branch_index / max(1, branches - 1)
        if fraction < 0.48:
            start = p0 + (p1 - p0) * (fraction / 0.48)
        elif fraction < 0.74:
            start = p1 + (p2 - p1) * ((fraction - 0.48) / 0.26)
        else:
            start = p2 + (p3 - p2) * ((fraction - 0.74) / 0.26)

        sign = -1.0 if branch_index % 2 else 1.0
        # A small forward component plus alternating sides creates the compact
        # herringbone outline visible in weighted rice panicles.
        branch_dir = direction * local.uniform(0.15, 0.34) + side * sign
        branch_dir /= np.linalg.norm(branch_dir)
        branch_length = target_height * local.uniform(0.082, 0.132) * (
            1.12 - 0.30 * fraction
        )
        gravity = target_height * (0.030 + 0.070 * maturity)
        mid = start + branch_dir * branch_length * 0.48 + direction * branch_length * 0.08
        mid[2] -= gravity * 0.34
        end = start + branch_dir * branch_length + direction * branch_length * 0.13
        end[2] -= gravity * local.uniform(0.92, 1.20)
        r1._tube_chain(
            mesh,
            [tuple(start), tuple(mid), tuple(end)],
            target_height * 0.0018,
            rachis_material,
            sides=6,
        )

        grain_count = local.randint(14, 19)
        grains_total += grain_count
        normal_to_branch = np.array(
            [-branch_dir[1], branch_dir[0], 0.0], dtype=np.float64
        )
        for grain_index in range(grain_count):
            t = 0.08 + 0.89 * grain_index / max(1, grain_count - 1)
            if t <= 0.48:
                center = start + (mid - start) * (t / 0.48)
            else:
                center = mid + (end - mid) * ((t - 0.48) / 0.52)
            alternating = -1.0 if grain_index % 2 else 1.0
            center = center + normal_to_branch * alternating * target_height * local.uniform(
                0.0025, 0.0050
            )
            center[2] -= target_height * local.uniform(0.004, 0.012)
            grain_axis = tuple(
                branch_dir * local.uniform(0.24, 0.42)
                + np.array([0.0, 0.0, -1.0], dtype=np.float64)
            )
            r1.add_oriented_ellipsoid(
                mesh,
                tuple(center),
                grain_axis,
                target_height * local.uniform(0.0060, 0.0080),
                target_height * local.uniform(0.0028, 0.0036),
                grain_material,
                rings=3,
                sides=6,
            )
    return branches, grains_total


def main() -> None:
    r2.PACK_ID = PACK_ID
    r2.dense_drooping_panicle = clustered_herringbone_panicle
    r2.main()

    output_index = sys.argv.index("--output") + 1
    destination = Path(sys.argv[output_index]).expanduser().resolve()
    manifest_path = destination / "PACK.json"
    pack = json.loads(manifest_path.read_text(encoding="utf-8"))
    pack["purpose"] = "R3 clustered-panicle late-reproductive rice contribution gate"
    pack["builder_script"] = str(Path(__file__).resolve())
    pack["builder_script_sha256"] = sha256(__file__)
    reproductive = pack["generated_assets"]["reproductive_crop"]
    reproductive.update(
        {
            "refinement_revision": "v9_r3",
            "refinement_control": {
                "pack_id": "cropcraft_paddy_reproductive_v9_r2",
                "pack_manifest_sha256": "3ed0ecae66a1dc47af41883e823e4da11f94ec3d38d71b2de360e74bc79106c5",
                "manual_review_sha256": "36a488d943b0232f48a662940d813d0c6be9fc452c019548cfdf17161ab415ce",
                "decision": "rejected_before_pilot",
            },
            "r3_isolated_morphology_changes": [
                "alternate branches in a shared herringbone panicle plane",
                "increase mature gravity bend of main rachis and side branches",
                "increase per-branch grains from 12-17 to 14-19",
                "increase grain cross radius to 2.8-3.6 mm per meter of plant height",
                "advance parent RNG exactly as R2 to preserve later tiller parameters",
            ],
        }
    )
    extension = pack["paddy_v4_assets"]["full_cycle_extension"]
    extension["revision"] = "v9_r3"
    extension["refinement_reason"] = (
        "R2 matched frozen RiceSEG low-order statistics and fixed leaf habit, "
        "but manual review rejected its open radial panicle skeleton"
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
