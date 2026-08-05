from pathlib import Path

import yaml
from PIL import Image

from scripts.audit_cropcraft_reproductive_assets_v9 import (
    edge_max_abs_difference,
    sha256,
)
from scripts.build_cropcraft_agri_assets import Mesh
from scripts.build_cropcraft_reproductive_assets_v9 import (
    SOURCE_TEXTURES,
    add_oriented_ellipsoid,
    prepare_imagegen_texture,
    reproductive_rice_mesh,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_oriented_grain_is_closed_and_nontrivial() -> None:
    mesh = Mesh()
    add_oriented_ellipsoid(
        mesh,
        center=(0.0, 0.0, 0.1),
        axis=(0.2, 0.1, -1.0),
        long_radius=0.006,
        cross_radius=0.0025,
        material="grain",
    )

    assert len(mesh.vertices) == 42
    assert len(mesh.faces) == 48
    assert mesh.surface_area() > 0.0


def test_reproductive_mesh_is_deterministic_and_has_explicit_panicles() -> None:
    first, first_meta = reproductive_rice_mesh(9401, 1.02, 4)
    second, second_meta = reproductive_rice_mesh(9401, 1.02, 4)

    assert first.vertices == second.vertices
    assert first.faces == second.faces
    assert first_meta == second_meta
    assert first.bounds()[1][2] == 1.02
    assert first_meta["panicle_count"] >= 5
    assert first_meta["panicle_branch_count"] >= 10
    assert first_meta["grain_count"] >= 80
    assert first_meta["leaf_count"] >= 20


def test_imagegen_texture_processing_is_repeatable_and_seam_exact(
    tmp_path: Path,
) -> None:
    source_root = PROJECT_ROOT / "assets/source_textures/rice_reproductive_v9"
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    for phenotype, filename in SOURCE_TEXTURES.items():
        first = prepare_imagegen_texture(
            source_root / filename, first_root, phenotype
        )
        second = prepare_imagegen_texture(
            source_root / filename, second_root, phenotype
        )
        for key in ("albedo", "normal_gl"):
            first_path = first_root / first[key]
            second_path = second_root / second[key]
            with Image.open(first_path) as image:
                assert image.size == (1024, 1024)
            assert sha256(first_path) == sha256(second_path)
            assert edge_max_abs_difference(first_path) == 0


def test_frozen_gate_locks_current_builder_and_only_one_missing_factor() -> None:
    gate_path = (
        PROJECT_ROOT
        / "configs/simulation/cropcraft_reproductive_asset_gate_v9.yaml"
    )
    gate = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    builder_path = PROJECT_ROOT / gate["builder_lock"]["path"]

    assert sha256(builder_path) == gate["builder_lock"]["sha256"]
    assert gate["selection_evidence_lock"]["selected_factor"] == (
        "late_reproductive_rice"
    )
    assert gate["asset_pack_gate"]["require_duckweed_added"] is False
    assert gate["bounded_render_gate"]["prohibit_large_batch_before_all_pass"]
