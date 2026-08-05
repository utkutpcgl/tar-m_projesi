#!/usr/bin/env python3
"""Build a provenance-locked CropCraft asset pack for early crop scenes.

The plant, weed, and residue meshes are generated procedurally without third-
party geometry.  Soil PBR maps and HDRIs are fetched from the official Poly
Haven API and verified against the advertised MD5 and byte count.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import shutil
import tempfile
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


USER_AGENT = "AgriSegSyntheticAssetCuration/1.0"
API_ROOT = "https://api.polyhaven.com"
LICENSE_URL = "https://polyhaven.com/license"
GROUND_IDS = ("dry_mud_field_001", "brown_mud", "cracked_red_ground")
ENVIRONMENT_IDS = (
    "farm_field_puresky",
    "overcast_soil_puresky",
    "citrus_orchard_puresky",
)
GROUND_CHANNELS = {
    "diff.jpg": ("Diffuse", "2k", "jpg"),
    "rough.jpg": ("Rough", "2k", "jpg"),
    "nor_gl.exr": ("nor_gl", "2k", "exr"),
    "disp.png": ("Displacement", "2k", "png"),
}

Vec3 = tuple[float, float, float]


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def subtract(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def multiply(a: Vec3, value: float) -> Vec3:
    return (a[0] * value, a[1] * value, a[2] * value)


def dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def normalized(a: Vec3) -> Vec3:
    magnitude = length(a)
    if magnitude <= 1e-12:
        raise ValueError("Cannot normalize a zero-length vector")
    return multiply(a, 1.0 / magnitude)


def triangle_area(a: Vec3, b: Vec3, c: Vec3) -> float:
    return 0.5 * length(cross(subtract(b, a), subtract(c, a)))


@dataclass
class Face:
    vertices: tuple[int, ...]
    material: str


@dataclass
class Mesh:
    vertices: list[Vec3] = field(default_factory=list)
    faces: list[Face] = field(default_factory=list)

    def vertex(self, value: Vec3) -> int:
        if not all(math.isfinite(component) for component in value):
            raise ValueError(f"Non-finite vertex: {value}")
        self.vertices.append(value)
        return len(self.vertices)

    def face(self, vertices: Iterable[int], material: str) -> None:
        indexes = tuple(vertices)
        if len(indexes) < 3 or len(set(indexes)) < 3:
            raise ValueError(f"Degenerate face indexes: {indexes}")
        self.faces.append(Face(indexes, material))

    def add_tube(
        self,
        start: Vec3,
        end: Vec3,
        radius_start: float,
        radius_end: float,
        sides: int,
        material: str,
    ) -> None:
        axis = normalized(subtract(end, start))
        reference = (0.0, 0.0, 1.0)
        if abs(dot(axis, reference)) > 0.92:
            reference = (1.0, 0.0, 0.0)
        basis_a = normalized(cross(axis, reference))
        basis_b = normalized(cross(axis, basis_a))
        rings: list[list[int]] = []
        for center, radius in ((start, radius_start), (end, radius_end)):
            ring = []
            for side in range(sides):
                angle = math.tau * side / sides
                offset = add(
                    multiply(basis_a, math.cos(angle) * radius),
                    multiply(basis_b, math.sin(angle) * radius),
                )
                ring.append(self.vertex(add(center, offset)))
            rings.append(ring)
        for side in range(sides):
            nxt = (side + 1) % sides
            self.face(
                (rings[0][side], rings[0][nxt], rings[1][nxt], rings[1][side]),
                material,
            )
        start_center = self.vertex(start)
        end_center = self.vertex(end)
        for side in range(sides):
            nxt = (side + 1) % sides
            self.face((start_center, rings[0][nxt], rings[0][side]), material)
            self.face((end_center, rings[1][side], rings[1][nxt]), material)

    def add_blade(
        self,
        base: Vec3,
        blade_length: float,
        azimuth: float,
        elevation: float,
        half_width: float,
        arch: float,
        droop: float,
        twist: float,
        fold: float,
        leaf_material: str,
        midrib_material: str,
        segments: int = 24,
        profile_power: float = 0.72,
        lobes: int = 0,
    ) -> None:
        across = (-1.0, -0.14, 0.0, 0.14, 1.0)
        rows: list[list[int]] = []
        for step in range(segments + 1):
            t = step / segments
            theta = azimuth + twist * (t - 0.5)
            planar = blade_length * math.cos(elevation) * t
            center = (
                base[0] + planar * math.cos(theta),
                base[1] + planar * math.sin(theta),
                base[2]
                + blade_length
                * (
                    math.sin(elevation) * t
                    + arch * math.sin(math.pi * t)
                    - droop * t * t
                ),
            )
            cross_axis = (-math.sin(theta), math.cos(theta), 0.0)
            profile = max(0.035, math.sin(math.pi * t)) ** profile_power
            if lobes > 0:
                profile *= 0.78 + 0.22 * abs(math.sin(lobes * math.pi * t))
            width = half_width * profile
            row: list[int] = []
            for across_position in across:
                lateral = multiply(cross_axis, across_position * width)
                crease = -fold * abs(across_position) * width
                row.append(
                    self.vertex(
                        (
                            center[0] + lateral[0],
                            center[1] + lateral[1],
                            center[2] + crease,
                        )
                    )
                )
            rows.append(row)
        for step in range(segments):
            for strip in range(len(across) - 1):
                material = (
                    midrib_material if strip in (1, 2) else leaf_material
                )
                self.face(
                    (
                        rows[step][strip],
                        rows[step + 1][strip],
                        rows[step + 1][strip + 1],
                        rows[step][strip + 1],
                    ),
                    material,
                )

    def add_box(
        self,
        center: Vec3,
        dimensions: Vec3,
        angle: float,
        material: str,
    ) -> None:
        half_x, half_y, half_z = (value / 2.0 for value in dimensions)
        points: list[int] = []
        for z in (-half_z, half_z):
            for y in (-half_y, half_y):
                for x in (-half_x, half_x):
                    rotated_x = x * math.cos(angle) - y * math.sin(angle)
                    rotated_y = x * math.sin(angle) + y * math.cos(angle)
                    points.append(
                        self.vertex(
                            (
                                center[0] + rotated_x,
                                center[1] + rotated_y,
                                center[2] + z,
                            )
                        )
                    )
        for face_indexes in (
            (0, 1, 3, 2),
            (4, 6, 7, 5),
            (0, 4, 5, 1),
            (2, 3, 7, 6),
            (0, 2, 6, 4),
            (1, 5, 7, 3),
        ):
            self.face((points[index] for index in face_indexes), material)

    def add_irregular_chip(
        self,
        chip_length: float,
        chip_width: float,
        thickness: float,
        angle: float,
        rng: random.Random,
        material: str,
    ) -> None:
        outline = (
            (-0.50, -0.12),
            (-0.34, -0.50),
            (0.22, -0.43),
            (0.50, -0.10),
            (0.37, 0.39),
            (-0.28, 0.50),
        )
        bottom: list[int] = []
        top: list[int] = []
        for x_ratio, y_ratio in outline:
            x = chip_length * x_ratio
            y = chip_width * y_ratio
            rotated_x = x * math.cos(angle) - y * math.sin(angle)
            rotated_y = x * math.sin(angle) + y * math.cos(angle)
            bottom.append(self.vertex((rotated_x, rotated_y, 0.0)))
            top.append(
                self.vertex(
                    (
                        rotated_x + rng.uniform(-0.08, 0.08) * chip_width,
                        rotated_y + rng.uniform(-0.08, 0.08) * chip_width,
                        thickness * rng.uniform(0.78, 1.18),
                    )
                )
            )
        self.face(tuple(reversed(bottom)), material)
        self.face(tuple(top), material)
        for index in range(len(outline)):
            nxt = (index + 1) % len(outline)
            self.face(
                (bottom[index], bottom[nxt], top[nxt], top[index]), material
            )

    def add_clod(
        self,
        radii: Vec3,
        rng: random.Random,
        material: str,
        rings_count: int = 5,
        sides: int = 9,
    ) -> None:
        rings: list[list[int]] = []
        bottom = self.vertex((0.0, 0.0, 0.0))
        for ring_index in range(1, rings_count):
            phi = (math.pi / 2.0) * ring_index / rings_count
            ring: list[int] = []
            for side in range(sides):
                theta = math.tau * side / sides
                jitter = rng.uniform(0.82, 1.18)
                ring.append(
                    self.vertex(
                        (
                            radii[0] * math.sin(phi) * math.cos(theta) * jitter,
                            radii[1] * math.sin(phi) * math.sin(theta) * jitter,
                            radii[2] * (1.0 - math.cos(phi)) * jitter,
                        )
                    )
                )
            rings.append(ring)
        top = self.vertex((0.0, 0.0, radii[2] * 1.05))
        for side in range(sides):
            nxt = (side + 1) % sides
            self.face((bottom, rings[0][side], rings[0][nxt]), material)
        for ring_index in range(len(rings) - 1):
            for side in range(sides):
                nxt = (side + 1) % sides
                self.face(
                    (
                        rings[ring_index][side],
                        rings[ring_index + 1][side],
                        rings[ring_index + 1][nxt],
                        rings[ring_index][nxt],
                    ),
                    material,
                )
        for side in range(sides):
            nxt = (side + 1) % sides
            self.face((rings[-1][side], top, rings[-1][nxt]), material)

    def scale_to_height(self, target_height: float) -> None:
        minimum, maximum = self.bounds()
        current = maximum[2] - minimum[2]
        if current <= 0.0:
            raise ValueError("Mesh has no positive height")
        scale = target_height / current
        self.vertices = [
            (
                vertex[0] * scale,
                vertex[1] * scale,
                (vertex[2] - minimum[2]) * scale,
            )
            for vertex in self.vertices
        ]

    def clamp_width(self, maximum_width: float) -> None:
        minimum, maximum = self.bounds()
        current_width = max(
            maximum[0] - minimum[0], maximum[1] - minimum[1]
        )
        if current_width <= maximum_width:
            return
        scale = maximum_width / current_width
        center_x = (minimum[0] + maximum[0]) / 2.0
        center_y = (minimum[1] + maximum[1]) / 2.0
        self.vertices = [
            (
                center_x + (vertex[0] - center_x) * scale,
                center_y + (vertex[1] - center_y) * scale,
                vertex[2],
            )
            for vertex in self.vertices
        ]

    def bounds(self) -> tuple[Vec3, Vec3]:
        if not self.vertices:
            raise ValueError("Empty mesh")
        return (
            tuple(min(value[index] for value in self.vertices) for index in range(3)),
            tuple(max(value[index] for value in self.vertices) for index in range(3)),
        )  # type: ignore[return-value]

    def surface_area(self, materials: set[str] | None = None) -> float:
        total = 0.0
        for face in self.faces:
            if materials is not None and face.material not in materials:
                continue
            origin = self.vertices[face.vertices[0] - 1]
            for index in range(1, len(face.vertices) - 1):
                total += triangle_area(
                    origin,
                    self.vertices[face.vertices[index] - 1],
                    self.vertices[face.vertices[index + 1] - 1],
                )
        return total


def material_text(name: str, color: tuple[float, float, float], roughness: float) -> str:
    return "\n".join(
        (
            f"newmtl {name}",
            "Ns 32.000000",
            "Ka 0.000000 0.000000 0.000000",
            f"Kd {color[0]:.6f} {color[1]:.6f} {color[2]:.6f}",
            "Ks 0.080000 0.080000 0.080000",
            "Ke 0.000000 0.000000 0.000000",
            "Ni 1.450000",
            "d 1.000000",
            "illum 2",
            f"Pr {roughness:.6f}",
            "",
        )
    )


def write_mesh(
    directory: Path,
    name: str,
    mesh: Mesh,
    materials: dict[str, tuple[tuple[float, float, float], float]],
) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=True)
    obj_path = directory / f"{name}.obj"
    mtl_path = directory / f"{name}.mtl"
    lines = [f"mtllib {mtl_path.name}", f"o {name}", "s 1"]
    lines.extend(
        f"v {vertex[0]:.9f} {vertex[1]:.9f} {vertex[2]:.9f}"
        for vertex in mesh.vertices
    )
    active_material = None
    for face_value in mesh.faces:
        if face_value.material != active_material:
            active_material = face_value.material
            lines.append(f"usemtl {active_material}")
        lines.append("f " + " ".join(str(index) for index in face_value.vertices))
    obj_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    mtl_path.write_text(
        "".join(
            material_text(material, color, roughness)
            for material, (color, roughness) in materials.items()
        ),
        encoding="utf-8",
    )
    minimum, maximum = mesh.bounds()
    face_areas = []
    for face_value in mesh.faces:
        origin = mesh.vertices[face_value.vertices[0] - 1]
        area = 0.0
        for index in range(1, len(face_value.vertices) - 1):
            area += triangle_area(
                origin,
                mesh.vertices[face_value.vertices[index] - 1],
                mesh.vertices[face_value.vertices[index + 1] - 1],
            )
        face_areas.append(area)
    return {
        "filename": obj_path.name,
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "degenerate_faces": sum(area <= 1e-12 for area in face_areas),
        "bounds_min_m": list(minimum),
        "bounds_max_m": list(maximum),
        "height_m": maximum[2] - minimum[2],
        "width_m": max(maximum[0] - minimum[0], maximum[1] - minimum[1]),
        "surface_area_m2": mesh.surface_area(),
        "obj_sha256": sha256(obj_path),
        "mtl_sha256": sha256(mtl_path),
    }


def crop_mesh(seed: int, target_height: float, leaf_count: int) -> tuple[Mesh, dict[str, Any]]:
    rng = random.Random(seed)
    mesh = Mesh()
    prefix = f"sorghum_{seed}"
    stem_material = f"{prefix}_stem"
    leaf_material = f"{prefix}_leaf"
    midrib_material = f"{prefix}_midrib"
    stem_height = target_height * rng.uniform(0.36, 0.52)
    mesh.add_tube(
        (0.0, 0.0, 0.0),
        (0.0, 0.0, stem_height),
        target_height * 0.018,
        target_height * 0.011,
        12,
        stem_material,
    )
    phase = rng.uniform(0.0, math.tau)
    for leaf_index in range(leaf_count):
        maturity = (leaf_index + 1) / leaf_count
        base_z = stem_height * (0.10 + 0.78 * maturity)
        blade_length = target_height * rng.uniform(0.62, 1.06) * (
            1.02 - 0.20 * maturity
        )
        elevation = math.radians(rng.uniform(24.0, 58.0) + 18.0 * maturity)
        mesh.add_blade(
            (0.0, 0.0, base_z),
            blade_length,
            phase + leaf_index * math.radians(137.5) + rng.uniform(-0.16, 0.16),
            elevation,
            blade_length * rng.uniform(0.035, 0.060),
            rng.uniform(0.06, 0.18),
            rng.uniform(0.0, 0.055),
            rng.uniform(-0.34, 0.34),
            rng.uniform(0.18, 0.34),
            leaf_material,
            midrib_material,
            segments=40,
        )
    mesh.scale_to_height(target_height)
    green = rng.uniform(0.34, 0.48)
    materials = {
        leaf_material: ((green * 0.38, green, green * 0.22), 0.72),
        midrib_material: ((green * 0.68, min(0.72, green * 1.28), green * 0.38), 0.66),
        stem_material: ((green * 0.58, min(0.68, green * 1.12), green * 0.30), 0.70),
    }
    return mesh, materials


def weed_mesh(
    family: str, seed: int, target_height: float
) -> tuple[Mesh, dict[str, Any]]:
    rng = random.Random(seed)
    mesh = Mesh()
    prefix = f"{family}_{seed}"
    stem_material = f"{prefix}_stem"
    leaf_material = f"{prefix}_leaf"
    midrib_material = f"{prefix}_midrib"
    phase = rng.uniform(0.0, math.tau)
    if family == "weed_grass_v2":
        blade_count = rng.randint(5, 8)
        for index in range(blade_count):
            blade_length = target_height * rng.uniform(0.80, 1.35)
            mesh.add_blade(
                (rng.uniform(-0.002, 0.002), rng.uniform(-0.002, 0.002), 0.0),
                blade_length,
                phase + index * math.tau / blade_count + rng.uniform(-0.24, 0.24),
                math.radians(rng.uniform(38.0, 76.0)),
                blade_length * rng.uniform(0.025, 0.050),
                rng.uniform(0.03, 0.13),
                rng.uniform(0.0, 0.08),
                rng.uniform(-0.25, 0.25),
                rng.uniform(0.16, 0.30),
                leaf_material,
                midrib_material,
                segments=18,
            )
    else:
        rosette = family == "weed_rosette_v2"
        cotyledon = family == "weed_cotyledon_v2"
        leaf_count = (
            rng.randint(7, 10)
            if rosette
            else (4 if cotyledon else rng.randint(5, 8))
        )
        stem_height = target_height * (0.20 if rosette else rng.uniform(0.45, 0.68))
        mesh.add_tube(
            (0.0, 0.0, 0.0),
            (0.0, 0.0, stem_height),
            max(0.0006, target_height * 0.025),
            max(0.0004, target_height * 0.015),
            9,
            stem_material,
        )
        for index in range(leaf_count):
            if rosette:
                base_z = target_height * rng.uniform(0.02, 0.07)
                elevation = math.radians(rng.uniform(8.0, 22.0))
                blade_length = target_height * rng.uniform(1.0, 1.8)
                width_ratio = rng.uniform(0.15, 0.27)
                lobes = rng.randint(4, 7)
                profile_power = 0.58
            elif cotyledon:
                base_z = stem_height * (0.58 if index < 2 else 0.82)
                elevation = math.radians(rng.uniform(14.0, 34.0))
                blade_length = target_height * (
                    rng.uniform(0.55, 0.76) if index < 2 else rng.uniform(0.32, 0.52)
                )
                width_ratio = rng.uniform(0.30, 0.44)
                lobes = 0
                profile_power = 0.42
            else:
                base_z = stem_height * rng.uniform(0.30, 0.92)
                elevation = math.radians(rng.uniform(18.0, 48.0))
                blade_length = target_height * rng.uniform(0.52, 0.95)
                width_ratio = rng.uniform(0.20, 0.34)
                lobes = rng.randint(3, 6)
                profile_power = 0.55
            mesh.add_blade(
                (0.0, 0.0, base_z),
                blade_length,
                phase + index * math.tau / leaf_count + rng.uniform(-0.18, 0.18),
                elevation,
                blade_length * width_ratio,
                rng.uniform(0.02, 0.10),
                rng.uniform(0.0, 0.035),
                rng.uniform(-0.22, 0.22),
                rng.uniform(0.08, 0.18),
                leaf_material,
                midrib_material,
                segments=16,
                profile_power=profile_power,
                lobes=lobes,
            )
    mesh.scale_to_height(target_height)
    maximum_width_ratio = {
        "weed_cotyledon_v2": 1.8,
        "weed_broadleaf_v2": 2.2,
        "weed_grass_v2": 1.4,
        "weed_rosette_v2": 2.0,
    }[family]
    mesh.clamp_width(target_height * maximum_width_ratio)
    green = rng.uniform(0.38, 0.60)
    red_stem = family in {"weed_broadleaf_v2", "weed_cotyledon_v2"} and seed % 2 == 0
    materials = {
        leaf_material: ((green * 0.34, green, green * 0.26), 0.76),
        midrib_material: ((green * 0.52, min(0.78, green * 1.12), green * 0.38), 0.69),
        stem_material: (
            (0.30, 0.08, 0.07) if red_stem else (green * 0.46, green * 0.88, green * 0.30),
            0.73,
        ),
    }
    return mesh, materials


def debris_mesh(kind: str, seed: int) -> tuple[Mesh, dict[str, Any]]:
    rng = random.Random(seed)
    mesh = Mesh()
    material = f"{kind}_{seed}_material"
    if kind == "residue_stick":
        stick_length = rng.uniform(0.05, 0.24)
        radius = rng.uniform(0.0018, 0.0070)
        angle = rng.uniform(0.0, math.tau)
        start = (-stick_length / 2.0 * math.cos(angle), -stick_length / 2.0 * math.sin(angle), radius)
        end = (stick_length / 2.0 * math.cos(angle), stick_length / 2.0 * math.sin(angle), radius * rng.uniform(0.8, 1.6))
        mesh.add_tube(start, end, radius, radius * rng.uniform(0.45, 0.90), 9, material)
        color = (rng.uniform(0.18, 0.32), rng.uniform(0.10, 0.20), rng.uniform(0.035, 0.09))
    elif kind == "residue_chip":
        chip_length = rng.uniform(0.025, 0.13)
        chip_width = rng.uniform(0.006, min(0.035, chip_length * 0.45))
        thickness = rng.uniform(0.002, 0.007)
        mesh.add_irregular_chip(
            chip_length,
            chip_width,
            thickness,
            rng.uniform(0.0, math.tau),
            rng,
            material,
        )
        color = (rng.uniform(0.27, 0.48), rng.uniform(0.17, 0.31), rng.uniform(0.07, 0.14))
    elif kind == "soil_clod":
        mesh.add_clod(
            (
                rng.uniform(0.012, 0.045),
                rng.uniform(0.010, 0.038),
                rng.uniform(0.008, 0.028),
            ),
            rng,
            material,
        )
        value = rng.uniform(0.10, 0.24)
        color = (value * 1.15, value * 0.82, value * 0.55)
    else:
        raise ValueError(f"Unknown debris type: {kind}")
    return mesh, {material: (color, 0.88)}


def write_description(directory: Path, rows: list[dict[str, Any]]) -> None:
    description = {
        "models": [
            {
                "filename": row["filename"],
                "height": round(float(row["height_m"]), 6),
                "width": round(float(row["width_m"]), 6),
                "leaf_area": round(float(row["leaf_area_m2"]), 8),
            }
            for row in rows
        ]
    }
    (directory / "description.yaml").write_text(
        yaml.safe_dump(description, sort_keys=False), encoding="utf-8"
    )


def build_generated_geometry(root: Path) -> dict[str, Any]:
    plants_root = root / "xdg/cropcraft/plants"
    crop_rows: list[dict[str, Any]] = []
    crop_directory = plants_root / "sorghum_seedling_v2"
    crop_heights = (0.06, 0.09, 0.13, 0.18, 0.24)
    for stage_index, target_height in enumerate(crop_heights):
        for variant in range(3):
            seed = 2100 + stage_index * 10 + variant
            name = f"sorghum_stage{stage_index + 1}_v{variant + 1}"
            mesh, materials = crop_mesh(
                seed, target_height, leaf_count=2 + stage_index + variant % 2
            )
            row = write_mesh(crop_directory, name, mesh, materials)
            row["leaf_area_m2"] = mesh.surface_area(
                {material for material in materials if "leaf" in material or "midrib" in material}
            )
            row["growth_stage"] = stage_index + 1
            crop_rows.append(row)
    write_description(crop_directory, crop_rows)

    weed_rows: dict[str, list[dict[str, Any]]] = {}
    weed_families = (
        "weed_cotyledon_v2",
        "weed_broadleaf_v2",
        "weed_grass_v2",
        "weed_rosette_v2",
    )
    for family_index, family in enumerate(weed_families):
        directory = plants_root / family
        family_rows: list[dict[str, Any]] = []
        for variant, target_height in enumerate((0.015, 0.022, 0.032, 0.045, 0.060, 0.080)):
            seed = 3100 + family_index * 100 + variant
            name = f"{family}_{variant + 1:02d}"
            mesh, materials = weed_mesh(family, seed, target_height)
            row = write_mesh(directory, name, mesh, materials)
            row["leaf_area_m2"] = mesh.surface_area(
                {material for material in materials if "leaf" in material or "midrib" in material}
            )
            family_rows.append(row)
        write_description(directory, family_rows)
        weed_rows[family] = family_rows

    stones_root = root / "overlay/stones"
    debris_rows: list[dict[str, Any]] = []
    for kind, count, base_seed in (
        ("residue_stick", 6, 4100),
        ("residue_chip", 5, 4200),
        ("soil_clod", 5, 4300),
    ):
        for index in range(count):
            seed = base_seed + index
            name = f"{kind}_{index + 1:02d}"
            mesh, materials = debris_mesh(kind, seed)
            row = write_mesh(stones_root, name, mesh, materials)
            row["kind"] = kind
            debris_rows.append(row)
    return {
        "crop": {"plant_type": "sorghum_seedling_v2", "models": crop_rows},
        "weeds": {
            family: {"plant_type": family, "models": rows}
            for family, rows in weed_rows.items()
        },
        "background_debris": debris_rows,
    }


def url_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object from {url}")
    return value


def nested(value: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    current: Any = value
    for key in path:
        current = current[key]
    if not isinstance(current, dict):
        raise ValueError(f"Expected file metadata at {'/'.join(path)}")
    for required in ("url", "size", "md5"):
        if required not in current:
            raise ValueError(f"Missing {required} at {'/'.join(path)}")
    return current


def download_file(metadata: dict[str, Any], output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        str(metadata["url"]), headers={"User-Agent": USER_AGENT}
    )
    md5 = hashlib.md5(usedforsecurity=False)
    digest = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(request, timeout=120) as response, output.open("wb") as handle:
        while True:
            block = response.read(4 * 1024 * 1024)
            if not block:
                break
            handle.write(block)
            md5.update(block)
            digest.update(block)
            size += len(block)
    if size != int(metadata["size"]):
        raise RuntimeError(f"Size mismatch for {output}: {size} != {metadata['size']}")
    if md5.hexdigest() != str(metadata["md5"]):
        raise RuntimeError(f"MD5 mismatch for {output}")
    return {
        "path": output.as_posix(),
        "source_url": metadata["url"],
        "size_bytes": size,
        "source_md5": metadata["md5"],
        "sha256": digest.hexdigest(),
    }


def selected_downloads(files_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for asset_id in GROUND_IDS:
        for output_name, path in GROUND_CHANNELS.items():
            metadata = nested(files_by_id[asset_id], path)
            selected.append(
                {
                    "asset_id": asset_id,
                    "kind": "ground",
                    "output_name": output_name,
                    "metadata": metadata,
                }
            )
    for asset_id in ENVIRONMENT_IDS:
        metadata = nested(files_by_id[asset_id], ("hdri", "2k", "hdr"))
        selected.append(
            {
                "asset_id": asset_id,
                "kind": "environment",
                "output_name": f"{asset_id}_2k.hdr",
                "metadata": metadata,
            }
        )
    return selected


def tree_inventory(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != "PACK.json":
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    destination = Path(args.output).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    asset_catalog = url_json(f"{API_ROOT}/assets")
    selected_ids = (*GROUND_IDS, *ENVIRONMENT_IDS)
    files_by_id = {
        asset_id: url_json(f"{API_ROOT}/files/{asset_id}")
        for asset_id in selected_ids
    }
    downloads = selected_downloads(files_by_id)
    advertised_bytes = sum(int(row["metadata"]["size"]) for row in downloads)
    free_bytes = shutil.disk_usage(destination.parent).free
    required_free = advertised_bytes * 2 + 1024**3
    if free_bytes < required_free:
        raise RuntimeError(
            f"Insufficient capacity: need {required_free} free bytes, have {free_bytes}"
        )

    with tempfile.TemporaryDirectory(
        prefix="cropcraft-agri-assets-", dir=destination.parent
    ) as temporary_directory:
        root = Path(temporary_directory) / destination.name
        root.mkdir()
        generated = build_generated_geometry(root)
        downloaded_rows: list[dict[str, Any]] = []
        for row in downloads:
            if row["kind"] == "ground":
                output = root / "grounds" / row["asset_id"] / row["output_name"]
            else:
                output = root / "environments" / row["output_name"]
            receipt = download_file(row["metadata"], output)
            receipt["path"] = output.relative_to(root).as_posix()
            receipt["asset_id"] = row["asset_id"]
            receipt["kind"] = row["kind"]
            downloaded_rows.append(receipt)

        license_text = (
            "Generated geometry\n"
            "==================\n"
            "The procedural OBJ/MTL geometry generated by this script is made "
            "available under CC0-1.0: https://creativecommons.org/publicdomain/zero/1.0/\n\n"
            "Poly Haven inputs\n"
            "=================\n"
            "The downloaded soil maps and HDRIs are original Poly Haven assets "
            f"distributed under CC0-1.0. License: {LICENSE_URL}\n"
        )
        (root / "LICENSES.txt").write_text(license_text, encoding="utf-8")
        sources = {
            asset_id: {
                "name": asset_catalog[asset_id]["name"],
                "type": asset_catalog[asset_id]["type"],
                "category": asset_catalog[asset_id].get("category"),
                "authors": asset_catalog[asset_id].get("authors", {}),
                "files_hash": asset_catalog[asset_id].get("files_hash"),
                "asset_url": f"https://polyhaven.com/a/{asset_id}",
                "api_files_url": f"{API_ROOT}/files/{asset_id}",
                "license": "CC0-1.0",
                "license_url": LICENSE_URL,
            }
            for asset_id in selected_ids
        }
        inventory = tree_inventory(root)
        pack = {
            "schema_version": 1,
            "pack_id": "cropcraft_agri_early_v2_r3",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "purpose": "early-stage robust crop segmentation synthetic ablation",
            "generator_script": str(Path(__file__).resolve()),
            "generator_script_sha256": sha256(__file__),
            "mesh_provenance": (
                "procedurally generated in-project; no third-party mesh or plant texture input"
            ),
            "generated_geometry_license": "CC0-1.0",
            "third_party_source": "Poly Haven official API",
            "third_party_license": "CC0-1.0",
            "third_party_license_url": LICENSE_URL,
            "api_user_agent": USER_AGENT,
            "capacity_check": {
                "advertised_download_bytes": advertised_bytes,
                "free_bytes_before_build": free_bytes,
                "required_free_bytes": required_free,
                "passed": True,
            },
            "sources": sources,
            "downloads": downloaded_rows,
            "generated_assets": generated,
            "grounds": list(GROUND_IDS),
            "environments": [f"{asset_id}_2k.hdr" for asset_id in ENVIRONMENT_IDS],
            "inventory": inventory,
            "inventory_sha256": canonical_sha256(inventory),
            "inventory_bytes": sum(row["size_bytes"] for row in inventory),
        }
        (root / "PACK.json").write_text(
            json.dumps(pack, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        root.replace(destination)

    print(
        json.dumps(
            {
                "output": str(destination),
                "pack_sha256": sha256(destination / "PACK.json"),
                "advertised_download_bytes": advertised_bytes,
                "free_bytes_before_build": free_bytes,
                "inventory_bytes": json.loads(
                    (destination / "PACK.json").read_text(encoding="utf-8")
                )["inventory_bytes"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
