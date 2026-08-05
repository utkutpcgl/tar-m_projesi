"""Deterministic EBIS press scene and ground-truth renderer for Unreal 5.8.

The batch path and the MCP toolset both call this module.  All dimensions are
centimetres (Unreal native units).  RGB and masks are captured by the same
SceneCapture2D actor.  Visible masks keep every occluder in the scene; amodal
masks hide every non-instance mesh.  Annotation policy is applied later by the
host-side validator so visible-but-unlabelled objects cannot silently enter the
standard training partition.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import time
from pathlib import Path
from typing import Any, Iterable

import unreal


MANAGED_TAG = unreal.Name("EBIS_MANAGED")
MAP_PATH = "/Game/EBIS/Maps/EBIS_Press"
MATERIAL_PATH = "/Game/EBIS/Materials"
EXTERNAL_TEXTURE_PATH = "/Game/EBIS/External/AmbientCG/Concrete003"
STATE: dict[str, Any] = {}


def _json_load(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    total = sum(max(0.0, float(value)) for value in weights.values())
    if total <= 0.0:
        raise ValueError(f"Weighted choice requires a positive total: {weights}")
    target = rng.random() * total
    running = 0.0
    for key, value in weights.items():
        running += max(0.0, float(value))
        if target <= running:
            return str(key)
    return str(next(reversed(weights)))


def _vector(values: Iterable[float]) -> unreal.Vector:
    x, y, z = values
    return unreal.Vector(float(x), float(y), float(z))


def _rotator(*, pitch: float = 0.0, yaw: float = 0.0, roll: float = 0.0) -> unreal.Rotator:
    return unreal.Rotator(pitch=float(pitch), yaw=float(yaw), roll=float(roll))


def _world() -> unreal.World:
    subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = subsystem.get_editor_world()
    if not world:
        raise RuntimeError("Unreal editor world is unavailable")
    return world


def _actor_subsystem() -> unreal.EditorActorSubsystem:
    subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    if not subsystem:
        raise RuntimeError("EditorActorSubsystem is unavailable")
    return subsystem


def _asset_tools() -> unreal.AssetTools:
    return unreal.AssetToolsHelpers.get_asset_tools()


def _safe_set(obj: Any, property_name: str, value: Any) -> bool:
    try:
        obj.set_editor_property(property_name, value)
        return True
    except Exception as exc:
        unreal.log_warning(f"EBIS: could not set {obj}.{property_name}: {exc}")
        return False


def _ensure_level() -> None:
    level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    current = str(_world().get_path_name()).split(":", 1)[0]
    if current.startswith(MAP_PATH):
        return
    if unreal.EditorAssetLibrary.does_asset_exist(MAP_PATH):
        level_subsystem.load_level(MAP_PATH)
    else:
        if not level_subsystem.new_level(MAP_PATH):
            raise RuntimeError(f"Failed to create {MAP_PATH}")


def _clear_managed_actors() -> int:
    actors = _actor_subsystem().get_all_level_actors()
    managed = [actor for actor in actors if actor.actor_has_tag(MANAGED_TAG)]
    if managed:
        _actor_subsystem().destroy_actors(managed)
    return len(managed)


def _constant_vector(material: unreal.Material, value: tuple[float, float, float], x: int, y: int):
    node = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant3Vector, x, y
    )
    node.set_editor_property("constant", unreal.LinearColor(value[0], value[1], value[2], 1.0))
    return node


def _constant_scalar(material: unreal.Material, value: float, x: int, y: int):
    node = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant, x, y
    )
    node.set_editor_property("r", float(value))
    return node


def _material(
    name: str,
    base: tuple[float, float, float],
    roughness: float,
    metallic: float = 0.0,
    emissive: tuple[float, float, float] | None = None,
    two_sided: bool = False,
    specular: float | None = None,
    opacity: float | None = None,
) -> unreal.Material:
    asset_path = f"{MATERIAL_PATH}/{name}"
    existing = unreal.load_asset(asset_path)
    if existing:
        return existing
    material = _asset_tools().create_asset(
        name, MATERIAL_PATH, unreal.Material, unreal.MaterialFactoryNew()
    )
    if not material:
        raise RuntimeError(f"Could not create material {asset_path}")
    material.set_editor_property(
        "two_sided", bool(two_sided or opacity is not None)
    )
    if opacity is not None:
        material.set_editor_property(
            "blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT
        )
    base_node = _constant_vector(material, base, -520, -100)
    rough_node = _constant_scalar(material, roughness, -520, 80)
    metal_node = _constant_scalar(material, metallic, -520, 210)
    unreal.MaterialEditingLibrary.connect_material_property(
        base_node, "", unreal.MaterialProperty.MP_BASE_COLOR
    )
    unreal.MaterialEditingLibrary.connect_material_property(
        rough_node, "", unreal.MaterialProperty.MP_ROUGHNESS
    )
    unreal.MaterialEditingLibrary.connect_material_property(
        metal_node, "", unreal.MaterialProperty.MP_METALLIC
    )
    if specular is not None:
        specular_node = _constant_scalar(material, specular, -520, 280)
        unreal.MaterialEditingLibrary.connect_material_property(
            specular_node, "", unreal.MaterialProperty.MP_SPECULAR
        )
    if emissive is not None:
        emissive_node = _constant_vector(material, emissive, -520, 340)
        unreal.MaterialEditingLibrary.connect_material_property(
            emissive_node, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
        )
    if opacity is not None:
        opacity_node = _constant_scalar(material, opacity, -520, 420)
        unreal.MaterialEditingLibrary.connect_material_property(
            opacity_node, "", unreal.MaterialProperty.MP_OPACITY
        )
    errors = unreal.MaterialEditingLibrary.recompile_material(material)
    if errors:
        raise RuntimeError(f"Material compile failed for {name}: {list(errors)}")
    unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)
    return material


def _procedural_pbr_material(
    name: str,
    dark: tuple[float, float, float],
    light: tuple[float, float, float],
    roughness_low: float,
    roughness_high: float,
    metallic: float,
    noise_scale: float,
    noise_levels: int = 3,
    specular: float = 0.5,
) -> unreal.Material:
    """Create deterministic world-space albedo/roughness variation.

    This is intentionally texture-free so a fresh 3090 checkout is complete.
    It adds the low-amplitude coating/oxidation variation missing from flat
    constant materials; measured PBR scans should eventually replace it.
    """
    asset_path = f"{MATERIAL_PATH}/{name}"
    existing = unreal.load_asset(asset_path)
    if existing:
        # Linux editor sessions can load a saved procedural material before
        # its shader map is ready and render the engine checker fallback in
        # the first off-screen capture.  RGB QC caught this on the used-paper
        # form; synchronously compiling an existing graph makes the material
        # contract explicit rather than trusting editor timing.
        errors = unreal.MaterialEditingLibrary.recompile_material(existing)
        if errors:
            raise RuntimeError(
                f"Existing procedural material compile failed for {name}: {list(errors)}"
            )
        return existing
    material = _asset_tools().create_asset(
        name, MATERIAL_PATH, unreal.Material, unreal.MaterialFactoryNew()
    )
    if not material:
        raise RuntimeError(f"Could not create material {asset_path}")
    world_position = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionWorldPosition, -920, -80
    )
    noise = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionNoise, -650, -70
    )
    noise.set_editor_property("scale", float(noise_scale))
    noise.set_editor_property("quality", 2)
    noise.set_editor_property("levels", int(noise_levels))
    noise.set_editor_property("output_min", 0.0)
    noise.set_editor_property("output_max", 1.0)
    noise.set_editor_property("level_scale", 2.0)
    dark_node = _constant_vector(material, dark, -620, -300)
    light_node = _constant_vector(material, light, -620, -220)
    color_lerp = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionLinearInterpolate, -330, -220
    )
    rough_low = _constant_scalar(material, roughness_low, -620, 120)
    rough_high = _constant_scalar(material, roughness_high, -620, 200)
    rough_lerp = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionLinearInterpolate, -330, 130
    )
    metal_node = _constant_scalar(material, metallic, -330, 280)
    specular_node = _constant_scalar(material, specular, -330, 350)
    connections = [
        (world_position, "XYZ", noise, "World Position"),
        (dark_node, "", color_lerp, "A"),
        (light_node, "", color_lerp, "B"),
        (noise, "", color_lerp, "Alpha"),
        (rough_low, "", rough_lerp, "A"),
        (rough_high, "", rough_lerp, "B"),
        (noise, "", rough_lerp, "Alpha"),
    ]
    failed = []
    for source, output_name, destination, input_name in connections:
        if not unreal.MaterialEditingLibrary.connect_material_expressions(
            source, output_name, destination, input_name
        ):
            failed.append(input_name)
    if failed:
        raise RuntimeError(f"Could not connect {name} graph inputs: {failed}")
    unreal.MaterialEditingLibrary.connect_material_property(
        color_lerp, "", unreal.MaterialProperty.MP_BASE_COLOR
    )
    unreal.MaterialEditingLibrary.connect_material_property(
        rough_lerp, "", unreal.MaterialProperty.MP_ROUGHNESS
    )
    unreal.MaterialEditingLibrary.connect_material_property(
        metal_node, "", unreal.MaterialProperty.MP_METALLIC
    )
    unreal.MaterialEditingLibrary.connect_material_property(
        specular_node, "", unreal.MaterialProperty.MP_SPECULAR
    )
    errors = unreal.MaterialEditingLibrary.recompile_material(material)
    if errors:
        raise RuntimeError(f"Material compile failed for {name}: {list(errors)}")
    unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)
    return material


def _glass_material() -> unreal.Material:
    """Create the blue-grey safety-glass insert used by the open door."""
    name = "M_DoorSafetyGlassV1"
    asset_path = f"{MATERIAL_PATH}/{name}"
    existing = unreal.load_asset(asset_path)
    if existing:
        return existing
    material = _asset_tools().create_asset(
        name, MATERIAL_PATH, unreal.Material, unreal.MaterialFactoryNew()
    )
    if not material:
        raise RuntimeError(f"Could not create material {asset_path}")
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property("two_sided", True)
    base_node = _constant_vector(material, (0.055, 0.075, 0.085), -520, -120)
    rough_node = _constant_scalar(material, 0.16, -520, 40)
    metal_node = _constant_scalar(material, 0.0, -520, 120)
    specular_node = _constant_scalar(material, 0.62, -520, 200)
    opacity_node = _constant_scalar(material, 0.24, -520, 280)
    refraction_node = _constant_scalar(material, 1.48, -520, 360)
    for node, prop in (
        (base_node, unreal.MaterialProperty.MP_BASE_COLOR),
        (rough_node, unreal.MaterialProperty.MP_ROUGHNESS),
        (metal_node, unreal.MaterialProperty.MP_METALLIC),
        (specular_node, unreal.MaterialProperty.MP_SPECULAR),
        (opacity_node, unreal.MaterialProperty.MP_OPACITY),
        (refraction_node, unreal.MaterialProperty.MP_REFRACTION),
    ):
        unreal.MaterialEditingLibrary.connect_material_property(node, "", prop)
    errors = unreal.MaterialEditingLibrary.recompile_material(material)
    if errors:
        raise RuntimeError(f"Material compile failed for {name}: {list(errors)}")
    unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)
    return material


def _import_texture(
    source: Path,
    *,
    srgb: bool,
    normal_map: bool = False,
) -> unreal.Texture:
    """Import one pinned external texture and normalize its colour contract."""

    if not source.is_file():
        raise FileNotFoundError(f"Required EBIS PBR map is missing: {source}")
    asset_path = f"{EXTERNAL_TEXTURE_PATH}/{source.stem}"
    texture = unreal.load_asset(asset_path)
    if not texture:
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(source))
        task.set_editor_property("destination_path", EXTERNAL_TEXTURE_PATH)
        task.set_editor_property("destination_name", source.stem)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", False)
        task.set_editor_property("save", True)
        task.set_editor_property("async_", False)
        _asset_tools().import_asset_tasks([task])
        imported = list(task.get_editor_property("imported_object_paths"))
        texture = unreal.load_asset(imported[0]) if imported else unreal.load_asset(asset_path)
    if not texture:
        raise RuntimeError(f"Could not import EBIS PBR map: {source}")
    _safe_set(texture, "srgb", bool(srgb))
    if normal_map:
        _safe_set(
            texture,
            "compression_settings",
            unreal.TextureCompressionSettings.TC_NORMALMAP,
        )
    unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False)
    return texture


def _ambientcg_concrete_material() -> unreal.Material:
    """Build the rights-cleared Concrete003 hybrid used by both EBIS engines."""

    name = "M_ConcreteAmbientCG003HybridV4"
    asset_path = f"{MATERIAL_PATH}/{name}"
    existing = unreal.load_asset(asset_path)
    if existing:
        errors = unreal.MaterialEditingLibrary.recompile_material(existing)
        if errors:
            raise RuntimeError(
                f"Existing concrete PBR material compile failed: {list(errors)}"
            )
        return existing

    project_root = Path(__file__).resolve().parents[2]
    source_root = (
        project_root
        / "assets"
        / "external"
        / "ambientcg"
        / "Concrete003_2K_JPG"
    )
    colour_texture = _import_texture(
        source_root / "Concrete003_2K-JPG_Color.jpg", srgb=True
    )
    roughness_texture = _import_texture(
        source_root / "Concrete003_2K-JPG_Roughness.jpg", srgb=False
    )
    normal_texture = _import_texture(
        source_root / "Concrete003_2K-JPG_NormalDX.jpg",
        srgb=False,
        normal_map=True,
    )

    material = _asset_tools().create_asset(
        name, MATERIAL_PATH, unreal.Material, unreal.MaterialFactoryNew()
    )
    if not material:
        raise RuntimeError(f"Could not create material {asset_path}")
    uv = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureCoordinate, -900, -40
    )
    uv.set_editor_property("u_tiling", 2.0)
    uv.set_editor_property("v_tiling", 2.0)
    colour = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureSample, -650, -220
    )
    colour.set_editor_property("texture", colour_texture)
    roughness = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureSample, -650, 40
    )
    roughness.set_editor_property("texture", roughness_texture)
    normal = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureSample, -650, 250
    )
    normal.set_editor_property("texture", normal_texture)
    tint = _constant_vector(material, (0.115, 0.108, 0.098), -650, -390)
    colour_multiply = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionMultiply, -340, -190
    )
    rough_low = _constant_scalar(material, 0.72, -370, 20)
    rough_high = _constant_scalar(material, 0.94, -370, 100)
    rough_lerp = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionLinearInterpolate, -120, 60
    )
    specular = _constant_scalar(material, 0.22, -120, 180)
    connections = [
        (uv, "", colour, "UVs"),
        (uv, "", roughness, "UVs"),
        (uv, "", normal, "UVs"),
        (colour, "RGB", colour_multiply, "A"),
        (tint, "", colour_multiply, "B"),
        (rough_low, "", rough_lerp, "A"),
        (rough_high, "", rough_lerp, "B"),
        (roughness, "R", rough_lerp, "Alpha"),
    ]
    failed = []
    for source, output_name, destination, input_name in connections:
        if not unreal.MaterialEditingLibrary.connect_material_expressions(
            source, output_name, destination, input_name
        ):
            failed.append(input_name)
    if failed:
        raise RuntimeError(
            "Could not connect concrete PBR graph inputs: "
            f"{failed}; uv_outputs="
            f"{list(unreal.MaterialEditingLibrary.get_material_expression_output_names(uv))}; "
            f"texture_inputs="
            f"{list(unreal.MaterialEditingLibrary.get_material_expression_input_names(colour))}"
        )
    unreal.MaterialEditingLibrary.connect_material_property(
        colour_multiply, "", unreal.MaterialProperty.MP_BASE_COLOR
    )
    unreal.MaterialEditingLibrary.connect_material_property(
        rough_lerp, "", unreal.MaterialProperty.MP_ROUGHNESS
    )
    unreal.MaterialEditingLibrary.connect_material_property(
        normal, "RGB", unreal.MaterialProperty.MP_NORMAL
    )
    unreal.MaterialEditingLibrary.connect_material_property(
        specular, "", unreal.MaterialProperty.MP_SPECULAR
    )
    errors = unreal.MaterialEditingLibrary.recompile_material(material)
    if errors:
        raise RuntimeError(f"Concrete PBR material compile failed: {list(errors)}")
    unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)
    return material


def _concrete_material(profile: str) -> unreal.Material:
    """Create a world-space multi-tone concrete shader without external assets."""
    if profile == "ambientcg_concrete003_hybrid_v1":
        return _ambientcg_concrete_material()
    if profile != "procedural_cast_concrete_v2":
        raise ValueError(f"Unsupported sample.material_profile={profile}")
    # V20 separates broad low-contrast cast variation from sub-centimetre
    # aggregate grain. MaterialExpressionNoise scale is frequency-like in
    # this UE build (the inverse of Blender's intuitive feature-size reading):
    # the V9 pilot proved that a small paint scale creates metre-like clouds.
    # Pass-6b actual-pixel comparison found V18's 0.9-scale field too broad,
    # while the rejected V19 diagnostic (7/80) averaged the body almost flat.
    # This bounded midpoint retains readable cast variation without restoring
    # metre-like clouds. True cavities remain geometry, not painted black dots.
    # V27 removed procedural noise from both albedo and roughness. V24/r57
    # produced an all-over cellular skin; V25 produced marble-like 5--15 cm
    # albedo clouds; V26 retained the same broad cells through roughness. The
    # V28 restores only a narrow, fine-scale cast variation.  It deliberately
    # leaves the broad noise disconnected: matched Blender/real crops showed
    # that more homogeneous shader contrast did not close the gap, whereas
    # localized pores, exposed aggregate and fracture geometry did.
    name = "M_ConcreteProceduralV29"
    asset_path = f"{MATERIAL_PATH}/{name}"
    existing = unreal.load_asset(asset_path)
    if existing:
        errors = unreal.MaterialEditingLibrary.recompile_material(existing)
        if errors:
            raise RuntimeError(
                f"Existing concrete material compile failed: {list(errors)}"
            )
        return existing
    material = _asset_tools().create_asset(
        name, MATERIAL_PATH, unreal.Material, unreal.MaterialFactoryNew()
    )
    if not material:
        raise RuntimeError(f"Could not create material {asset_path}")
    world_position = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionWorldPosition, -900, -100
    )
    noise = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionNoise, -470, -70
    )
    noise.set_editor_property("scale", 0.18)
    noise.set_editor_property("quality", 2)
    noise.set_editor_property("levels", 3)
    noise.set_editor_property("output_min", 0.22)
    noise.set_editor_property("output_max", 0.78)
    noise.set_editor_property("level_scale", 2.0)
    fine_noise = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionNoise, -470, 20
    )
    fine_noise.set_editor_property("scale", 28.0)
    fine_noise.set_editor_property("quality", 2)
    fine_noise.set_editor_property("levels", 3)
    fine_noise.set_editor_property("output_min", 0.16)
    fine_noise.set_editor_property("output_max", 0.84)
    fine_noise.set_editor_property("level_scale", 2.0)
    # Values are linear.  The narrow band remains matte and mid-light under
    # the U-diffuser, with enough headroom for real contact highlights.
    dark = _constant_vector(material, (0.039, 0.041, 0.039), -480, -290)
    light = _constant_vector(material, (0.053, 0.055, 0.052), -480, -210)
    color_lerp = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionLinearInterpolate, -230, -190
    )
    cast_body = _constant_vector(material, (0.045, 0.047, 0.045), 10, -360)
    aggregate_tone = _constant_vector(material, (0.066, 0.065, 0.061), -250, -310)
    aggregate_lerp = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionLinearInterpolate, 10, -190
    )
    rough_low = _constant_scalar(material, 0.78, -470, 120)
    rough_high = _constant_scalar(material, 0.92, -470, 200)
    rough_lerp = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionLinearInterpolate, -220, 130
    )
    cast_roughness = _constant_scalar(material, 0.86, 10, 130)
    # V28's 0.27 value turned nearby rectangular diffuser cards into
    # metre-scale polygonal highlights on an otherwise nominal cube face.
    # Dry cast concrete in the references is overwhelmingly diffuse; the
    # sensor still retains local wet/contaminated highlights through separate
    # residue materials and lighting profiles.
    specular = _constant_scalar(material, 0.10, -220, 300)
    connection_specs = [
        ("world_to_noise", world_position, "XYZ", noise, "World Position"),
        ("world_to_fine_noise", world_position, "XYZ", fine_noise, "World Position"),
        ("dark_to_a", dark, "", color_lerp, "A"),
        ("light_to_b", light, "", color_lerp, "B"),
        ("fine_noise_to_color_alpha", fine_noise, "", color_lerp, "Alpha"),
        ("coarse_color_to_aggregate_a", color_lerp, "", aggregate_lerp, "A"),
        ("aggregate_tone_to_b", aggregate_tone, "", aggregate_lerp, "B"),
        ("fine_noise_to_aggregate_alpha", fine_noise, "", aggregate_lerp, "Alpha"),
        ("rough_low_to_a", rough_low, "", rough_lerp, "A"),
        ("rough_high_to_b", rough_high, "", rough_lerp, "B"),
        ("fine_noise_to_rough_alpha", fine_noise, "", rough_lerp, "Alpha"),
    ]
    failed_connections = []
    for label, source, output_name, destination, input_name in connection_specs:
        if not unreal.MaterialEditingLibrary.connect_material_expressions(
            source, output_name, destination, input_name
        ):
            failed_connections.append(
                {
                    "label": label,
                    "source_outputs": list(unreal.MaterialEditingLibrary.get_material_expression_output_names(source)),
                    "destination_inputs": list(unreal.MaterialEditingLibrary.get_material_expression_input_names(destination)),
                }
            )
    if failed_connections:
        raise RuntimeError(f"Could not connect procedural concrete material graph: {failed_connections}")
    unreal.MaterialEditingLibrary.connect_material_property(
        color_lerp, "", unreal.MaterialProperty.MP_BASE_COLOR
    )
    unreal.MaterialEditingLibrary.connect_material_property(
        rough_lerp, "", unreal.MaterialProperty.MP_ROUGHNESS
    )
    unreal.MaterialEditingLibrary.connect_material_property(
        specular, "", unreal.MaterialProperty.MP_SPECULAR
    )
    errors = unreal.MaterialEditingLibrary.recompile_material(material)
    if errors:
        raise RuntimeError(f"Concrete material compile failed: {list(errors)}")
    unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)
    return material


def _mask_material(name: str, value: float) -> unreal.Material:
    asset_path = f"{MATERIAL_PATH}/{name}"
    existing = unreal.load_asset(asset_path)
    if existing:
        # Precompiled Linux builds can load an editor material before its
        # shadermap is ready and temporarily draw the white default material.
        # A synchronous recompile is cheap for these one-node masks and avoids
        # silently exporting an all-white ground-truth pass.
        errors = unreal.MaterialEditingLibrary.recompile_material(existing)
        if errors:
            raise RuntimeError(
                f"Existing mask material compile failed for {name}: {list(errors)}"
            )
        return existing
    material = _asset_tools().create_asset(
        name, MATERIAL_PATH, unreal.Material, unreal.MaterialFactoryNew()
    )
    if not material:
        raise RuntimeError(f"Could not create mask material {asset_path}")
    if hasattr(unreal, "MaterialShadingModel"):
        material.set_editor_property(
            "shading_model", unreal.MaterialShadingModel.MSM_UNLIT
        )
    emissive = _constant_vector(material, (value, value, value), -320, 0)
    unreal.MaterialEditingLibrary.connect_material_property(
        emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    )
    errors = unreal.MaterialEditingLibrary.recompile_material(material)
    if errors:
        raise RuntimeError(f"Mask material compile failed for {name}: {list(errors)}")
    unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)
    return material


def ensure_materials(cfg: dict[str, Any]) -> dict[str, unreal.Material]:
    materials = {
        # Versioned names are intentional: an already-saved .uasset must not
        # silently retain the older constants when the generator changes.
        "machine_blue": _procedural_pbr_material(
            "M_MachineBluePowderCoatV9", (0.020, 0.052, 0.18), (0.052, 0.14, 0.42),
            0.58, 0.75, 0.0, 7.5, 3, 0.42
        ),
        "machine_grey": _procedural_pbr_material(
            "M_InteriorGreyStippleV8", (0.045, 0.070, 0.125), (0.105, 0.15, 0.265),
            0.60, 0.78, 0.0, 9.0, 3, 0.48
        ),
        "ceiling_dark": _material(
            "M_OverheadShellDarkUsedV2", (0.012, 0.015, 0.021), 0.86, 0.10
        ),
        "interior_dimple": _material("M_InteriorDimpleV6", (0.035, 0.048, 0.080), 0.74, 0.03),
        "blue_dimple": _material("M_BlueInteriorDimpleV2", (0.014, 0.070, 0.19), 0.72, 0.02),
        "dark_steel": _procedural_pbr_material(
            "M_DarkSteelProceduralV5", (0.025, 0.030, 0.034), (0.060, 0.066, 0.072),
            0.40, 0.58, 0.90, 4.5, 3, 0.55
        ),
        "worn_steel": _procedural_pbr_material(
            "M_WornSteelProceduralV7", (0.20, 0.215, 0.23), (0.34, 0.355, 0.37),
            0.50, 0.72, 0.48, 3.4, 3, 0.52
        ),
        "lower_contact_dry_used": _material(
            "M_LowerContactDryUsedV5", (0.10, 0.105, 0.11),
            0.56, 0.90, specular=0.40
        ),
        "lower_contact_dusty_used": _material(
            "M_LowerContactDustyUsedV6", (0.067, 0.070, 0.074),
            0.68, 0.70, specular=0.30
        ),
        "lower_contact_damp_residue": _material(
            "M_LowerContactDampResidueV5", (0.078, 0.084, 0.090),
            0.48, 0.80, specular=0.40
        ),
        "polished_steel": _procedural_pbr_material(
            "M_PolishedSteelProceduralV5", (0.20, 0.215, 0.225), (0.34, 0.355, 0.365),
            0.22, 0.38, 0.94, 6.0, 3, 0.62
        ),
        "upper_contact_steel": _material(
            "M_UpperPlatenBodyUsedSteelV17",
            (0.145, 0.155, 0.165),
            0.55,
            0.92,
            specular=0.43,
        ),
        "upper_contact_face": _material(
            "M_UpperContactFaceUsedV16",
            (0.115, 0.125, 0.135),
            0.54,
            0.92,
            specular=0.44,
        ),
        "platen_scratch": _material(
            "M_PlatenScratchV2", (0.045, 0.048, 0.052), 0.70, 0.55,
            specular=0.30
        ),
        "platen_dust_streak": _material(
            "M_PlatenDustStreakV2", (0.13, 0.125, 0.115), 0.94, 0.02,
            specular=0.12
        ),
        "rubber": _material("M_Rubber", (0.008, 0.009, 0.011), 0.9, 0.0),
        "camera_white": _procedural_pbr_material(
            "M_ServiceCoverCoolGreyV4", (0.13, 0.15, 0.18), (0.24, 0.27, 0.31),
            0.42, 0.58, 0.04, 8.0, 2, 0.44
        ),
        "safety_glass": _glass_material(),
        "concrete": _concrete_material(
            str(cfg["sample"].get("material_profile", "procedural_cast_concrete_v2"))
        ),
        "concrete_dark": _material(
            "M_ConcretePoreV5", (0.021, 0.020, 0.018), 0.99, 0.0,
            specular=0.10
        ),
        "pore_shadow": _material(
            "M_ConcreteRecessedPoreV1", (0.008, 0.007, 0.006), 0.99, 0.0,
            specular=0.08
        ),
        "aggregate": _material("M_Aggregate", (0.16, 0.15, 0.14), 0.87, 0.0),
        "dust": _material("M_ConcreteDust", (0.31, 0.29, 0.26), 0.98, 0.0),
        "concrete_load_stain_ochre": _material(
            "M_ConcreteLoadZoneOchreV4",
            (0.078, 0.071, 0.052),
            0.97,
            0.0,
            specular=0.12,
        ),
        "concrete_load_stain_dark": _material(
            "M_ConcreteLoadZoneDarkV4",
            (0.060, 0.058, 0.050),
            0.99,
            0.0,
            specular=0.10,
        ),
        "rfid_film": _material("M_RFIDFilm", (0.62, 0.115, 0.012), 0.42, 0.05, two_sided=True),
        "rfid_back": _material("M_RFIDBack", (0.21, 0.032, 0.005), 0.78, 0.0, two_sided=True),
        "copper": _material("M_RFIDCopper", (0.72, 0.22, 0.025), 0.24, 0.91, two_sided=True),
        "chip": _material("M_RFIDChip", (0.004, 0.005, 0.006), 0.28, 0.16),
        "paper": _procedural_pbr_material(
            "M_UsedPaperFormV2", (0.145, 0.126, 0.094), (0.225, 0.207, 0.165),
            0.82, 0.96, 0.0, 1.8, 3, 0.24
        ),
        "paper_white": _procedural_pbr_material(
            "M_WhitePaperFormV1", (0.48, 0.46, 0.41), (0.70, 0.67, 0.60),
            0.78, 0.94, 0.0, 2.1, 3, 0.18
        ),
        "paper_orange": _procedural_pbr_material(
            "M_OrangeNonTargetPaperV1", (0.42, 0.085, 0.012), (0.78, 0.20, 0.025),
            0.72, 0.91, 0.0, 2.0, 3, 0.20
        ),
        "paper_ink": _material("M_PaperInkV1", (0.012, 0.010, 0.008), 0.90, 0.0),
        "paper_tape": _material("M_DirtyPaperTapeV1", (0.32, 0.16, 0.022), 0.52, 0.02),
        "warning_red": _material("M_WarningRed", (0.47, 0.008, 0.004), 0.43, 0.15),
        "warning_yellow": _material("M_WarningYellow", (0.78, 0.42, 0.015), 0.48, 0.03),
        "led_channel": _material("M_LEDChannelV3", (0.075, 0.08, 0.085), 0.32, 0.94),
        "led": _material("M_LEDDiffuserOpalV5", (0.58, 0.60, 0.62), 0.52, 0.0, (0.44, 0.48, 0.52)),
        "mask_black": _mask_material("M_MaskBlackUnlitV2", 0.0),
        "mask_white": _mask_material("M_MaskWhiteUnlitV2", 1.0),
    }
    return materials


def _load_mesh(shape: str) -> unreal.StaticMesh:
    paths = {
        "cube": "/Engine/BasicShapes/Cube.Cube",
        "cylinder": "/Engine/BasicShapes/Cylinder.Cylinder",
        "sphere": "/Engine/BasicShapes/Sphere.Sphere",
        "cone": "/Engine/BasicShapes/Cone.Cone",
    }
    mesh = unreal.load_asset(paths[shape])
    if not mesh:
        raise RuntimeError(f"Missing engine basic shape: {paths[shape]}")
    return mesh


def _spawn_mesh(
    label: str,
    shape: str,
    location: tuple[float, float, float],
    dimensions: tuple[float, float, float],
    material: unreal.Material,
    rotation: unreal.Rotator | None = None,
    instance_key: str | None = None,
    semantic_class: str | None = None,
    role: str | None = None,
) -> unreal.StaticMeshActor:
    actor = _actor_subsystem().spawn_actor_from_object(
        _load_mesh(shape), _vector(location), rotation or _rotator()
    )
    if not actor:
        raise RuntimeError(f"Failed to spawn {label}")
    actor.set_actor_label(label)
    actor.set_actor_scale3d(_vector((dimensions[0] / 100.0, dimensions[1] / 100.0, dimensions[2] / 100.0)))
    component = actor.static_mesh_component
    component.set_material(0, material)
    component.set_editor_property("cast_shadow", True)
    tags = [MANAGED_TAG]
    if instance_key:
        tags.append(unreal.Name(f"EBIS_INSTANCE={instance_key}"))
    if semantic_class:
        tags.append(unreal.Name(f"EBIS_CLASS={semantic_class}"))
    if role:
        tags.append(unreal.Name(f"EBIS_ROLE={role}"))
    actor.tags = tags
    return actor


def _spawn_light(
    cls: type,
    label: str,
    location: tuple[float, float, float],
    target: tuple[float, float, float] | None,
    intensity: float,
    temperature: float,
    width: float | None = None,
    height: float | None = None,
    attenuation: float = 220.0,
    cast_shadows: bool = True,
) -> unreal.Actor:
    rotation = (
        unreal.MathLibrary.find_look_at_rotation(_vector(location), _vector(target))
        if target
        else _rotator()
    )
    actor = _actor_subsystem().spawn_actor_from_class(cls, _vector(location), rotation)
    actor.set_actor_label(label)
    actor.tags = [MANAGED_TAG, unreal.Name("EBIS_ROLE=light")]
    component = actor.get_component_by_class(unreal.LightComponent)
    if not component:
        component = actor.get_components_by_class(unreal.LightComponentBase)[0]
    _safe_set(component, "intensity", float(intensity))
    _safe_set(component, "intensity_units", unreal.LightUnits.LUMENS)
    _safe_set(component, "use_temperature", True)
    _safe_set(component, "temperature", float(temperature))
    _safe_set(component, "attenuation_radius", float(attenuation))
    _safe_set(component, "cast_shadows", bool(cast_shadows))
    _safe_set(component, "indirect_lighting_intensity", 1.0)
    _safe_set(component, "volumetric_scattering_intensity", 0.18)
    if width is not None:
        _safe_set(component, "source_width", float(width))
    if height is not None:
        _safe_set(component, "source_height", float(height))
    return actor


def _spawn_wall_dimples(
    machine: dict[str, Any],
    materials: dict[str, unreal.Material],
    width: float,
    depth: float,
    height: float,
) -> int:
    """Add shallow geometric dots to the fixed blue chamber panels.

    These meshes have no semantic instance. Visible passes retain them as
    occluders and amodal passes hide them, preserving the annotation contract.
    """
    spacing = float(machine["wall_dimple_spacing_cm"])
    diameter = float(machine["wall_dimple_diameter_cm"])
    dimple_depth = float(machine["wall_dimple_depth_cm"])
    wall_t = float(machine["inner_wall_thickness_cm"])
    panel_materials = machine["interior_panel_materials"]
    half_w = width / 2.0
    back_y = depth / 2.0
    z_values = [8.0 + row * spacing for row in range(int((height - 14.0) // spacing) + 1)]
    back_x_values = [
        -half_w + 6.0 + column * spacing
        for column in range(int((width - 12.0) // spacing) + 1)
    ]
    side_y_values = [
        -depth / 2.0 + 8.0 + column * spacing
        for column in range(int((depth - 12.0) // spacing) + 1)
    ]
    count = 0
    back_surface_y = back_y - wall_t / 2.0 - dimple_depth / 2.0
    for row, z in enumerate(z_values):
        offset = spacing * 0.5 if row % 2 else 0.0
        for column, x in enumerate(back_x_values):
            phase = row * 12.9898 + column * 78.233
            shifted_x = x + offset + math.sin(phase) * spacing * 0.16
            if shifted_x > half_w - 5.0:
                continue
            local_diameter = diameter * (0.72 + 0.42 * (0.5 + 0.5 * math.sin(phase * 1.71)))
            _spawn_mesh(
                f"Rear wall dimple r{row:02d}c{column:02d}",
                "cylinder",
                (shifted_x, back_surface_y, z),
                (local_diameter, local_diameter, dimple_depth),
                materials[
                    "blue_dimple"
                    if panel_materials["back"] == "machine_blue"
                    else "interior_dimple"
                ],
                rotation=_rotator(roll=90.0),
                role="wall_dimple",
            )
            count += 1
    for side_name, side, surface_x in (
        ("left", -1.0, -half_w + wall_t / 2.0 + dimple_depth / 2.0),
        ("right", 1.0, half_w - wall_t / 2.0 - dimple_depth / 2.0),
    ):
        for row, z in enumerate(z_values):
            offset = spacing * 0.5 if row % 2 else 0.0
            for column, y in enumerate(side_y_values):
                phase = row * 19.191 + column * 41.733 + (17.0 if side_name == "right" else 3.0)
                shifted_y = y + offset + math.sin(phase) * spacing * 0.16
                if shifted_y > back_y - 4.0:
                    continue
                local_diameter = diameter * (0.72 + 0.42 * (0.5 + 0.5 * math.sin(phase * 1.71)))
                _spawn_mesh(
                    f"{side_name.title()} wall dimple r{row:02d}c{column:02d}",
                    "cylinder",
                    (surface_x, shifted_y, z),
                    (local_diameter, local_diameter, dimple_depth),
                    materials[
                        "blue_dimple"
                        if panel_materials[side_name] == "machine_blue"
                        else "interior_dimple"
                    ],
                    rotation=_rotator(pitch=side * 90.0),
                    role="wall_dimple",
                )
                count += 1
    return count


def _spawn_machine(
    cfg: dict[str, Any],
    materials: dict[str, unreal.Material],
    rng: random.Random,
    sample_height: float,
    seed: int,
) -> dict[str, Any]:
    machine = cfg["machine"]
    width = float(machine["chamber_width_cm"])
    depth = float(machine["chamber_depth_cm"])
    height = float(machine["chamber_height_cm"])
    half_w = width / 2.0
    back_y = depth / 2.0
    center_y = float(machine["platen_center_y_cm"])
    lower_top = float(machine["lower_platen_top_z_cm"])
    # A sub-millimetre clearance admits the physical RFID film at the contact
    # boundary. The visible platen side, rather than this gap, caused the dark
    # fisheye band in the p1 diagnostic.
    upper_bottom = lower_top + sample_height + 0.05
    wall_t = float(machine["inner_wall_thickness_cm"])
    panel_materials = machine.get("interior_panel_materials", {})
    required_panel_zones = {"back", "left", "right", "ceiling", "tray"}
    allowed_panel_materials = {"machine_grey", "machine_blue", "ceiling_dark"}
    if (
        set(panel_materials) != required_panel_zones
        or any(value not in allowed_panel_materials for value in panel_materials.values())
        or not str(machine.get("interior_finish", "")).strip()
    ):
        raise ValueError("Fixed chamber panel material contract is invalid")
    door_profiles = machine.get("door_open_angle_profiles")
    door_rng = random.Random(f"{seed}:door-v1")
    if door_profiles:
        if (
            not isinstance(door_profiles, dict)
            or not door_profiles
            or any(float(values.get("weight", 0.0)) < 0.0 for values in door_profiles.values())
            or sum(float(values.get("weight", 0.0)) for values in door_profiles.values()) <= 0.0
        ):
            raise ValueError("Door angle profile weights are invalid")
        door_profile = _weighted_choice(
            door_rng,
            {name: float(values["weight"]) for name, values in door_profiles.items()},
        )
        door_range = list(map(float, door_profiles[door_profile]["range_deg"]))
    else:
        door_profile = "legacy_fixed"
        fixed_angle = float(machine.get("open_door_angle_deg", 90.0))
        door_range = [fixed_angle, fixed_angle]
    if (
        len(door_range) != 2
        or not 0.0 <= door_range[0] <= door_range[1] <= 115.0
        or not str(machine.get("door_angle_status", "")).strip()
    ):
        raise ValueError("Door angle range/status is outside the bounded physical contract")
    door_angle = door_rng.uniform(door_range[0], door_range[1])
    door_side = str(machine.get("door_side", "left"))
    if door_side != "right":
        raise ValueError("The calibrated EBIS front-door contract requires a right hinge")
    door_width = float(machine["door_leaf_width_cm"])
    door_height = float(machine["door_leaf_height_cm"])
    door_thickness = float(machine["door_leaf_thickness_cm"])
    cover_size = list(map(float, machine["door_service_cover_size_cm"]))
    if (
        not width * 0.9 <= door_width <= width * 1.02
        or not 64.0 <= door_height <= height * 1.02
        or not 1.2 <= door_thickness <= 4.5
        or len(cover_size) != 2
        or any(not 14.0 <= value <= 25.0 for value in cover_size)
        or machine.get("blue_wall_material_profile")
        not in {"procedural_hammertone_v2", "polyhaven_blue_metal_plate_2k_trial"}
    ):
        raise ValueError("Front-door or blue-wall material contract is invalid")

    boxes = [
        ("Chamber back panel", (0.0, back_y, height / 2), (width, wall_t, height), panel_materials["back"]),
        ("Chamber left inner wall", (-half_w, 0.0, height / 2), (wall_t, depth, height), panel_materials["left"]),
        ("Chamber right inner wall", (half_w, 0.0, height / 2), (wall_t, depth, height), panel_materials["right"]),
        ("Chamber ceiling", (0.0, 0.0, height), (width, depth, 3.0), panel_materials["ceiling"]),
        ("Debris tray", (0.0, 1.5, 3.5), (55.0, 49.0, 6.5), panel_materials["tray"]),
        ("Rear lower rubber seam", (0.0, back_y - 1.8, 20.5), (width - 3.5, 0.9, 3.5), "rubber"),
        ("Blue left front aperture jamb", (-half_w - 1.4, -depth / 2 - 0.6, height / 2), (5.5, 6.0, height + 7.0), "machine_blue"),
        ("Blue right front aperture jamb", (half_w + 1.4, -depth / 2 - 0.6, height / 2), (5.5, 6.0, height + 7.0), "machine_blue"),
        ("Blue front aperture header", (0.0, -depth / 2 - 0.6, height + 2.2), (width + 10.0, 6.0, 5.8), "machine_blue"),
        ("Blue front aperture sill", (0.0, -depth / 2 - 0.6, -0.4), (width + 10.0, 6.0, 6.6), "machine_blue"),
        ("Workshop floor proxy", (0.0, -92.0, 0.5), (145.0, 115.0, 2.5), "machine_grey"),
        ("Workshop back wall proxy", (0.0, -145.0, 42.0), (145.0, 2.5, 84.0), "machine_grey"),
    ]
    for label, location, dimensions, material_name in boxes:
        _spawn_mesh(label, "cube", location, dimensions, materials[material_name], role="machine")

    dimple_count = _spawn_wall_dimples(machine, materials, width, depth, height)

    fixed_camera_stack_count = int(machine["fixed_camera_stack_count"])
    if (
        fixed_camera_stack_count != 0
        or not str(machine.get("fixed_camera_stack_status", "")).strip()
    ):
        raise ValueError("Fixed camera-stack contract is invalid")

    # Broad solid sheet spanning the front opening. "Right" is defined from
    # the operator/exterior view facing +Y, hence world -X for the rear
    # cameras. Positive opening sends the left latch edge into the workshop.
    hinge_x = -half_w - 1.0
    hinge_y = -depth / 2.0 - 0.4
    door_base_z = 1.5
    door_z = door_base_z + door_height / 2.0
    theta = math.radians(door_angle)
    door_u = (math.cos(theta), -math.sin(theta))
    door_v = (math.sin(theta), math.cos(theta))
    door_rotation = _rotator(yaw=-door_angle)

    def door_point(along: float, inward: float, z: float) -> tuple[float, float, float]:
        return (
            hinge_x + door_u[0] * along + door_v[0] * inward,
            hinge_y + door_u[1] * along + door_v[1] * inward,
            z,
        )

    inner_y = door_thickness / 2.0
    gasket_inset = 2.2
    gasket_width = 1.2
    door_parts = [
        ("Solid grey front door sheet", door_point(door_width / 2.0, 0.0, door_z), (door_width, door_thickness, door_height), "machine_grey"),
        ("Door inner gasket hinge", door_point(gasket_inset, inner_y + 0.15, door_z), (gasket_width, 0.6, door_height - 2.0 * gasket_inset), "rubber"),
        ("Door inner gasket latch", door_point(door_width - gasket_inset, inner_y + 0.15, door_z), (gasket_width, 0.6, door_height - 2.0 * gasket_inset), "rubber"),
        ("Door inner gasket top", door_point(door_width / 2.0, inner_y + 0.15, door_base_z + door_height - gasket_inset), (door_width - 2.0 * gasket_inset, 0.6, gasket_width), "rubber"),
        ("Door inner gasket bottom", door_point(door_width / 2.0, inner_y + 0.15, door_base_z + gasket_inset), (door_width - 2.0 * gasket_inset, 0.6, gasket_width), "rubber"),
    ]
    for label, location, dimensions, material_name in door_parts:
        _spawn_mesh(
            label,
            "cube",
            location,
            dimensions,
            materials[material_name],
            rotation=door_rotation,
            role="front_door",
        )

    cover_distance = float(machine["door_service_cover_center_from_hinge_cm"])
    cover_z = float(machine["door_service_cover_center_z_cm"])
    cover_w, cover_h = cover_size
    cover_center = door_point(cover_distance, inner_y + 0.8, cover_z)
    _spawn_mesh(
        "Door service cover gasket",
        "cube",
        door_point(cover_distance, inner_y + 0.4, cover_z),
        (cover_w + 1.7, 0.6, cover_h + 1.7),
        materials["rubber"],
        rotation=door_rotation,
        role="door_service_cover",
    )
    cover_corner_rotation = _rotator(pitch=90.0, yaw=90.0 + door_angle)
    cover_parts = [
        ("Door service cover vertical core", cover_center, (cover_w - 4.5, 0.9, cover_h), "cube", door_rotation),
        ("Door service cover horizontal core", cover_center, (cover_w, 0.9, cover_h - 4.5), "cube", door_rotation),
    ]
    for horizontal_sign in (-1.0, 1.0):
        for vertical_sign in (-1.0, 1.0):
            along = cover_distance + horizontal_sign * (cover_w / 2.0 - 2.25)
            z = cover_z + vertical_sign * (cover_h / 2.0 - 2.25)
            cover_parts.append(
                (
                    f"Door service cover corner {horizontal_sign:+.0f} {vertical_sign:+.0f}",
                    door_point(along, inner_y + 0.8, z),
                    (4.5, 4.5, 0.9),
                    "cylinder",
                    cover_corner_rotation,
                )
            )
    for label, location, dimensions, shape, rotation in cover_parts:
        _spawn_mesh(
            label,
            shape,
            location,
            dimensions,
            materials["camera_white"],
            rotation=rotation,
            role="door_service_cover",
        )
    screw_dx = cover_w / 2.0 - 2.85
    screw_dz = cover_h / 2.0 - 2.85
    for index, (along_offset, z_offset) in enumerate(
        ((-screw_dx, -screw_dz), (-screw_dx, screw_dz), (screw_dx, -screw_dz), (screw_dx, screw_dz))
    ):
        _spawn_mesh(
            f"Door service cover screw {index}",
            "cylinder",
            door_point(cover_distance + along_offset, inner_y + 1.32, cover_z + z_offset),
            (1.15, 1.15, 0.38),
            materials["polished_steel"],
            rotation=cover_corner_rotation,
            role="door_service_cover_fastener",
        )

    for index, z in enumerate(
        (
            door_base_z + door_height * 0.22,
            door_base_z + door_height * 0.50,
            door_base_z + door_height * 0.78,
        )
    ):
        _spawn_mesh(
            f"Door hinge {index}",
            "cylinder",
            (hinge_x, hinge_y, z),
            (2.5, 2.5, 7.0),
            materials["dark_steel"],
            role="door_hinge",
        )

    # Workshop cabinet silhouettes through the front opening. Time-diverse real
    # frames support only a muted depth cue; earlier red badge proxies created
    # a high-saturation synthetic shortcut and are intentionally omitted.
    for idx, x in enumerate((-21.0, 5.0, 31.0)):
        _spawn_mesh(f"Workshop muted cabinet {idx}", "cube", (x, -89.0, 28.0), (20.0, 9.0, 54.0), materials["dark_steel"], role="backdrop")
        _spawn_mesh(f"Workshop cabinet door {idx}", "cube", (x, -83.7, 31.0), (15.0, 1.2, 34.0), materials["machine_grey"], role="backdrop")

    # Compression stack. Both 40 cm discs are 2.22x the 18 cm cube edge,
    # matching the canonical approximately-2x ratio and Blender control scene.
    lower_radius = float(machine["lower_platen_radius_cm"])
    upper_radius = float(machine["upper_platen_radius_cm"])
    lower_thickness = float(machine["lower_platen_thickness_cm"])
    upper_thickness = float(machine["upper_platen_thickness_cm"])
    contact_face_thickness = float(machine["upper_contact_face_thickness_cm"])
    contact_face_scale = float(machine["upper_contact_face_diameter_scale"])
    contact_face_extension = float(machine["upper_contact_face_bottom_extension_cm"])
    lower_contact_face_thickness = float(machine["lower_contact_face_thickness_cm"])
    lower_contact_face_scale = float(machine["lower_contact_face_diameter_scale"])
    lower_contact_profile_weights = machine[
        "lower_contact_face_surface_profile_weights"
    ]
    allowed_lower_contact_profiles = {"dry_used", "dusty_used", "damp_residue"}
    if (
        not 0.02 <= contact_face_thickness <= 0.15
        or not 0.94 <= contact_face_scale <= 1.0
        or not 0.0 <= contact_face_extension < contact_face_thickness
        or not str(machine.get("upper_contact_face_material_profile", "")).strip()
    ):
        raise ValueError("Upper platen contact face must remain a thin inset disc")
    if (
        not 0.02 <= lower_contact_face_thickness <= 0.15
        or not 0.94 <= lower_contact_face_scale <= 1.0
        or set(lower_contact_profile_weights) != allowed_lower_contact_profiles
        or any(float(value) < 0.0 for value in lower_contact_profile_weights.values())
        or sum(map(float, lower_contact_profile_weights.values())) <= 0.0
        or not str(machine.get("lower_contact_face_surface_status", "")).strip()
    ):
        raise ValueError("Lower platen contact face geometry/profile contract is invalid")
    lower_contact_profile = _weighted_choice(
        random.Random(f"{seed}:lower-contact-v1"),
        lower_contact_profile_weights,
    )
    lower_diameter = lower_radius * 2.0
    upper_diameter = upper_radius * 2.0
    _spawn_mesh("Lower hydraulic piston", "cylinder", (0.0, center_y, 13.0), (20.4, 20.4, 15.0), materials["worn_steel"], role="machine")
    _spawn_mesh(
        "Lower press platen",
        "cylinder",
        (
            0.0,
            center_y,
            lower_top - lower_contact_face_thickness - lower_thickness / 2.0,
        ),
        (lower_diameter, lower_diameter, lower_thickness),
        materials["worn_steel"],
        role="platen",
    )
    # Pass-5 LED/IR pixels consistently show a dark used-steel contact surface
    # with circular wear, concrete residue and localized reflections. Keep the
    # appearance regime on an independent RNG so controlled sample/tag seeds
    # remain stable across the material correction.
    _spawn_mesh(
        "Lower platen used contact face",
        "cylinder",
        (
            0.0,
            center_y,
            lower_top - lower_contact_face_thickness / 2.0,
        ),
        (
            lower_diameter * lower_contact_face_scale,
            lower_diameter * lower_contact_face_scale,
            lower_contact_face_thickness,
        ),
        materials[f"lower_contact_{lower_contact_profile}"],
        role="platen_contact_face",
    )
    _spawn_mesh(
        "Upper press platen",
        "cylinder",
        (0.0, center_y, upper_bottom + upper_thickness / 2.0),
        (upper_diameter, upper_diameter, upper_thickness),
        materials["upper_contact_steel"],
        role="platen",
    )
    contact_face_bottom = upper_bottom - contact_face_extension
    _spawn_mesh(
        "Upper platen dark contact face",
        "cylinder",
        (
            0.0,
            center_y,
            contact_face_bottom + contact_face_thickness / 2.0,
        ),
        (
            upper_diameter * contact_face_scale,
            upper_diameter * contact_face_scale,
            contact_face_thickness,
        ),
        materials["upper_contact_face"],
        role="platen_contact_face",
    )
    platen_wear_rng = random.Random(f"{seed}:platen-wear-v1")
    lower_wear_count = 8
    upper_wear_count = 6
    for surface_name, count, surface_z, radius_limit in (
        ("lower", lower_wear_count, lower_top + 0.012, lower_radius * 0.86),
        (
            "upper",
            upper_wear_count,
            contact_face_bottom - 0.012,
            upper_radius * 0.84,
        ),
    ):
        for index in range(count):
            angle = platen_wear_rng.uniform(0.0, math.tau)
            radial = platen_wear_rng.uniform(2.0, radius_limit)
            length = platen_wear_rng.uniform(0.8, 4.0)
            width = platen_wear_rng.uniform(0.018, 0.050)
            material_key = (
                "platen_dust_streak"
                if index % 5 == 0
                else "platen_scratch"
            )
            actor = _spawn_mesh(
                f"{surface_name.title()} platen wear line {index:02d}",
                "cube",
                (
                    math.cos(angle) * radial,
                    center_y + math.sin(angle) * radial,
                    surface_z,
                ),
                (length, width, 0.018),
                materials[material_key],
                rotation=_rotator(
                    yaw=math.degrees(angle)
                    + platen_wear_rng.uniform(-24.0, 24.0)
                ),
                role="platen_wear",
            )
            actor.static_mesh_component.set_editor_property(
                "cast_shadow", False
            )
    _spawn_mesh("Upper ram", "cylinder", (0.0, center_y, upper_bottom + 15.9), (25.0, 25.0, 24.5), materials["dark_steel"], role="machine")
    _spawn_mesh("Upper ram collar", "cylinder", (0.0, center_y, upper_bottom + upper_thickness + 1.65), (32.0, 32.0, 3.2), materials["dark_steel"], role="machine")

    # Narrow U-shaped opal LED channel: back + left + right inner walls at the
    # upper platen level. It is deliberately not a large luminous panel.
    led_z = upper_bottom + float(machine["led_center_offset_from_upper_platen_bottom_cm"])
    channel_h = float(machine["led_channel_height_cm"])
    channel_d = float(machine["led_channel_depth_cm"])
    diffuser_h = float(machine["led_diffuser_height_cm"])
    diffuser_d = float(machine["led_diffuser_depth_cm"])
    if not 0.5 <= diffuser_h <= 2.0 or not 1.0 <= channel_h <= 4.0:
        raise ValueError("U-LED diffuser/channel height is outside the bounded thin-strip profile")
    back_length = float(machine["led_back_length_cm"])
    left_length = float(machine["led_left_length_cm"])
    right_length = float(machine["led_right_length_cm"])
    inner_back_y = back_y - wall_t / 2.0
    back_channel_y = inner_back_y - channel_d / 2.0
    back_diffuser_y = inner_back_y - channel_d - diffuser_d / 2.0
    left_center_y = back_y - left_length / 2.0
    right_center_y = back_y - right_length / 2.0
    left_inner_x = -half_w + wall_t / 2.0
    right_inner_x = half_w - wall_t / 2.0
    left_channel_x = left_inner_x + channel_d / 2.0
    right_channel_x = right_inner_x - channel_d / 2.0
    left_diffuser_x = left_inner_x + channel_d + diffuser_d / 2.0
    right_diffuser_x = right_inner_x - channel_d - diffuser_d / 2.0
    led_meshes = [
        ("Back LED metal channel", (0.0, back_channel_y, led_z), (back_length + 2.0, channel_d, channel_h), "led_channel"),
        ("Back LED opal diffuser", (0.0, back_diffuser_y, led_z), (back_length, diffuser_d, diffuser_h), "led"),
        ("Left LED metal channel", (left_channel_x, left_center_y, led_z), (channel_d, left_length + 1.0, channel_h), "led_channel"),
        ("Left LED opal diffuser", (left_diffuser_x, left_center_y, led_z), (diffuser_d, left_length, diffuser_h), "led"),
        ("Right LED metal channel", (right_channel_x, right_center_y, led_z), (channel_d, right_length + 1.0, channel_h), "led_channel"),
        ("Right LED opal diffuser", (right_diffuser_x, right_center_y, led_z), (diffuser_d, right_length, diffuser_h), "led"),
    ]
    for label, location, dimensions, material_name in led_meshes:
        _spawn_mesh(
            label, "cube", location, dimensions, materials[material_name],
            role="led_diffuser" if material_name == "led" else "led_channel"
        )

    # Concrete chips/dust are background, never class 1.  The previous all-
    # sphere field read as smooth pebbles; real press trays contain mostly
    # angular fracture chips with only a small rounded tail.
    debris_profile = str(
        machine.get("debris_morphology_profile", "rounded_sphere_v1")
    )
    if debris_profile not in {
        "rounded_sphere_v1",
        "angular_fracture_mix_v2",
    }:
        raise ValueError(f"Unsupported debris morphology: {debris_profile}")
    debris_count_range = list(
        map(int, machine.get("debris_count_range", [32, 32]))
    )
    if (
        len(debris_count_range) != 2
        or not 0 <= debris_count_range[0] <= debris_count_range[1] <= 48
    ):
        raise ValueError("Invalid machine.debris_count_range")
    debris_rng = random.Random(f"{seed}:platen-debris-v2")
    debris_count = debris_rng.randint(*debris_count_range)
    debris_shape_counts = {"angular_cube": 0, "rounded_sphere": 0}
    for index in range(debris_count):
        angle = debris_rng.uniform(0.0, math.tau)
        radius = debris_rng.uniform(lower_radius * 0.48, lower_radius * 0.91)
        large = index < 2
        dims = (
            debris_rng.uniform(0.6, 1.6) if large else debris_rng.uniform(0.2, 0.8),
            debris_rng.uniform(0.4, 1.2) if large else debris_rng.uniform(0.18, 0.65),
            debris_rng.uniform(0.15, 0.4) if large else debris_rng.uniform(0.07, 0.26),
        )
        height_phase = debris_rng.random()
        chip_z = lower_top + dims[2] * (0.28 + 0.24 * height_phase)
        angular = (
            debris_profile == "angular_fracture_mix_v2"
            and debris_rng.random() < 0.82
        )
        shape_name = "cube" if angular else "sphere"
        debris_shape_counts[
            "angular_cube" if angular else "rounded_sphere"
        ] += 1
        actor = _spawn_mesh(
            f"Background concrete chip {index:02d}",
            shape_name,
            (math.cos(angle) * radius, center_y + math.sin(angle) * radius * 0.72, chip_z),
            dims,
            materials["aggregate" if index % 4 == 0 else "dust"],
            rotation=_rotator(
                pitch=debris_rng.uniform(0, 180),
                yaw=debris_rng.uniform(0, 180),
                roll=debris_rng.uniform(0, 180),
            ),
            role="debris",
        )
        actor.static_mesh_component.set_editor_property("cast_shadow", True)

    return {
        "lower_platen_top_z_cm": lower_top,
        "upper_platen_bottom_z_cm": upper_bottom,
        "platen_center_y_cm": center_y,
        "led_z_cm": led_z,
        "back_y_cm": back_y,
        "open_door_angle_deg": door_angle,
        "door": {
            "angle_deg": door_angle,
            "profile": door_profile,
            "angle_range_deg": door_range,
            "side": door_side,
            "angle_convention": "0=closed across front aperture, positive=left latch edge rotates outward",
            "distribution_status": machine["door_angle_status"],
            "leaf_width_cm": door_width,
            "leaf_height_cm": door_height,
            "leaf_thickness_cm": door_thickness,
            "service_cover": {
                "center_from_hinge_cm": cover_distance,
                "center_z_cm": cover_z,
                "size_cm": [cover_w, cover_h],
            },
        },
        "interior_finish": machine["interior_finish"],
        "interior_panel_materials": panel_materials,
        "blue_wall_material_profile": machine["blue_wall_material_profile"],
        "fixed_camera_stack_count": fixed_camera_stack_count,
        "fixed_camera_stack_status": machine["fixed_camera_stack_status"],
        "workshop_backdrop_status": machine["workshop_backdrop_status"],
        "platen_diameters_cm": {"lower": lower_diameter, "upper": upper_diameter},
        "lower_contact_face": {
            "diameter_cm": lower_diameter * lower_contact_face_scale,
            "diameter_scale": lower_contact_face_scale,
            "thickness_cm": lower_contact_face_thickness,
            "top_z_cm": lower_top,
            "specimen_contact_gap_cm": 0.0,
            "surface_profile": lower_contact_profile,
            "surface_status": machine["lower_contact_face_surface_status"],
        },
        "upper_contact_face": {
            "diameter_cm": upper_diameter * contact_face_scale,
            "diameter_scale": contact_face_scale,
            "thickness_cm": contact_face_thickness,
            "bottom_z_cm": contact_face_bottom,
            "contact_gap_cm": contact_face_bottom - (lower_top + sample_height),
            "material_profile": machine["upper_contact_face_material_profile"],
        },
        "debris_count": debris_count,
        "debris_shape_counts": debris_shape_counts,
        "debris_morphology": debris_profile,
        "debris_annotation_policy": "background only, never concrete target class",
        "platen_wear_line_counts": {
            "lower": lower_wear_count,
            "upper": upper_wear_count,
        },
        "platen_wear_profile": "bounded_sparse_scratches_and_dust_streaks_v1",
        "led_diffuser_height_cm": diffuser_h,
        "wall_dimple_count": dimple_count,
        "led_segments": {
            "back": {
                "location_cm": [0.0, back_diffuser_y - 0.1, led_z],
                "source_width_cm": back_length,
            },
            "left": {
                "location_cm": [left_diffuser_x + 0.1, left_center_y, led_z],
                "source_width_cm": left_length,
            },
            "right": {
                "location_cm": [right_diffuser_x - 0.1, right_center_y, led_z],
                "source_width_cm": right_length,
            },
        },
    }


def _sample_shape(seed: int, forced: str | None) -> str:
    if forced in {"cube", "cylinder"}:
        return forced
    return "cube" if ((seed // 2) % 2 == 0) else "cylinder"


def _spawn_sample(
    cfg: dict[str, Any], materials: dict[str, unreal.Material], rng: random.Random, machine_state: dict[str, float], shape: str
) -> dict[str, Any]:
    sample_cfg = cfg["sample"]
    if shape == "cube":
        dims = tuple(map(float, sample_cfg["cube_size_cm"]))
    else:
        diameter = float(sample_cfg["cylinder_diameter_cm"])
        dims = (diameter, diameter, float(sample_cfg["cylinder_height_cm"]))
    px = rng.uniform(-float(sample_cfg["position_jitter_cm"][0]), float(sample_cfg["position_jitter_cm"][0]))
    py = machine_state["platen_center_y_cm"] + rng.uniform(
        -float(sample_cfg["position_jitter_cm"][1]), float(sample_cfg["position_jitter_cm"][1])
    )
    pz = machine_state["lower_platen_top_z_cm"] + dims[2] / 2.0
    yaw = rng.uniform(-float(sample_cfg["yaw_jitter_deg"]), float(sample_cfg["yaw_jitter_deg"]))
    damage = rng.uniform(*map(float, sample_cfg["damage_range"]))
    allowed_surface_regimes = {"clean_cast", "pitted", "edge_worn", "spalled"}
    regime_weights = sample_cfg.get("surface_regime_weights_by_shape", {})
    relief_ranges = sample_cfg.get("edge_relief_count_range_by_regime", {})
    relief_size_range = list(map(float, sample_cfg.get("edge_relief_size_cm", [])))
    aggregate_ranges = sample_cfg.get(
        "exposed_aggregate_count_range_by_regime", {}
    )
    aggregate_radius_range = list(
        map(float, sample_cfg.get("exposed_aggregate_radius_cm", []))
    )
    cylinder_spall_size_range = list(
        map(float, sample_cfg.get("spalled_cylinder_patch_size_cm", []))
    )
    weathering_count_ranges = sample_cfg.get(
        "top_load_weathering_patch_count_range_by_regime", {}
    )
    weathering_width_range = list(
        map(float, sample_cfg.get("top_load_weathering_width_fraction_range", []))
    )
    weathering_height_range = list(
        map(float, sample_cfg.get("top_load_weathering_height_fraction_range", []))
    )
    weathering_depth_range = list(
        map(
            float,
            sample_cfg.get(
                "top_load_weathering_depth_below_top_fraction_range", []
            ),
        )
    )
    weathering_thickness_range = list(
        map(
            float,
            sample_cfg.get("top_load_weathering_half_thickness_cm", []),
        )
    )
    if (
        set(regime_weights) != {"cube", "cylinder"}
        or set(regime_weights.get(shape, {})) != allowed_surface_regimes
        or set(relief_ranges) != allowed_surface_regimes
        or len(relief_size_range) != 2
        or not 0.03 <= relief_size_range[0] <= relief_size_range[1] <= 0.6
        or set(aggregate_ranges) != allowed_surface_regimes
        or len(aggregate_radius_range) != 2
        or not 0.035
        <= aggregate_radius_range[0]
        <= aggregate_radius_range[1]
        <= 0.40
        or len(cylinder_spall_size_range) != 2
        or not 0.8
        <= cylinder_spall_size_range[0]
        <= cylinder_spall_size_range[1]
        <= 4.0
    ):
        raise ValueError("Invalid concrete surface-regime augmentation contract")
    for regime, count_range in relief_ranges.items():
        values = list(map(int, count_range))
        if len(values) != 2 or not 0 <= values[0] <= values[1] <= 32:
            raise ValueError(f"Invalid edge-relief count range: {regime}={count_range}")
    for regime, count_range in aggregate_ranges.items():
        values = list(map(int, count_range))
        if len(values) != 2 or not 0 <= values[0] <= values[1] <= 40:
            raise ValueError(
                f"Invalid exposed-aggregate count range: {regime}={count_range}"
            )
    if (
        set(weathering_count_ranges) != allowed_surface_regimes
        or any(
            len(list(map(int, count_range))) != 2
            or not 0
            <= int(count_range[0])
            <= int(count_range[1])
            <= 16
            for count_range in weathering_count_ranges.values()
        )
        or len(weathering_width_range) != 2
        or not 0.01
        <= weathering_width_range[0]
        <= weathering_width_range[1]
        <= 0.24
        or len(weathering_height_range) != 2
        or not 0.01
        <= weathering_height_range[0]
        <= weathering_height_range[1]
        <= 0.16
        or len(weathering_depth_range) != 2
        or not 0.01
        <= weathering_depth_range[0]
        <= weathering_depth_range[1]
        <= 0.24
        or len(weathering_thickness_range) != 2
        or not 0.005
        <= weathering_thickness_range[0]
        <= weathering_thickness_range[1]
        <= 0.06
        or not str(sample_cfg.get("top_load_weathering_status", "")).strip()
    ):
        raise ValueError("Invalid concrete top-load weathering contract")
    surface_rng = random.Random(
        f"{px:.9f}:{py:.9f}:{shape}:{damage:.9f}:surface-regime-v1"
    )
    surface_regime = _weighted_choice(surface_rng, regime_weights[shape])
    instance_key = "concrete_00"
    yaw_rad = math.radians(yaw)

    def world_from_sample_local(
        local_x: float, local_y: float, local_z: float
    ) -> tuple[float, float, float]:
        return (
            px + math.cos(yaw_rad) * local_x - math.sin(yaw_rad) * local_y,
            py + math.sin(yaw_rad) * local_x + math.cos(yaw_rad) * local_y,
            pz + local_z,
        )

    body_profile = "solid_nominal_v1"
    spall_notch_cm: list[float] | None = None
    spall_notch_side: str | None = None
    spall_fracture_tooth_count = 0
    cylinder_spall_patch_size_cm: list[float] | None = None
    cylinder_spall_patch_angle_deg: float | None = None
    cylinder_spall_aggregate_count = 0
    if shape == "cube" and surface_regime == "spalled":
        notch_ranges = sample_cfg.get("spalled_cube_notch_fraction_range", {})
        if set(notch_ranges) != {"x", "y", "z"}:
            raise ValueError("Invalid spalled-cube notch axis contract")
        for axis, bounds in notch_ranges.items():
            values = list(map(float, bounds))
            if (
                len(values) != 2
                or not 0.05 <= values[0] <= values[1] <= 0.30
            ):
                raise ValueError(
                    f"Invalid spalled-cube notch fraction range: {axis}={bounds}"
                )
        spall_rng = random.Random(
            f"{px:.9f}:{py:.9f}:{yaw:.9f}:{damage:.9f}:spall-notch-v1"
        )
        notch_x = dims[0] * spall_rng.uniform(*map(float, notch_ranges["x"]))
        notch_y = dims[1] * spall_rng.uniform(*map(float, notch_ranges["y"]))
        notch_z = dims[2] * spall_rng.uniform(*map(float, notch_ranges["z"]))
        notch_side_sign = -1.0 if spall_rng.random() < 0.5 else 1.0
        # Three non-overlapping pieces form one semantic/instance union while
        # removing a real upper camera-facing (+Y) corner volume. This produces the missing
        # silhouette seen in damaged cam-11 specimens without relying on
        # version-sensitive runtime mesh booleans.
        body_pieces = [
            (
                "SEM_CONCRETE_SAMPLE",
                (dims[0], dims[1], dims[2] - notch_z),
                (0.0, 0.0, -notch_z / 2.0),
            ),
            (
                "SEM_CONCRETE_SAMPLE upper rear",
                (dims[0], dims[1] - notch_y, notch_z),
                (0.0, -notch_y / 2.0, dims[2] / 2.0 - notch_z / 2.0),
            ),
            (
                "SEM_CONCRETE_SAMPLE upper front remainder",
                (dims[0] - notch_x, notch_y, notch_z),
                (
                    -notch_side_sign * notch_x / 2.0,
                    dims[1] / 2.0 - notch_y / 2.0,
                    dims[2] / 2.0 - notch_z / 2.0,
                ),
            ),
        ]
        for label, piece_dims, local_center in body_pieces:
            _spawn_mesh(
                label,
                "cube",
                world_from_sample_local(*local_center),
                piece_dims,
                materials["concrete"],
                rotation=_rotator(yaw=yaw),
                instance_key=instance_key,
                semantic_class="concrete_sample",
                role="sample_body",
            )
        tooth_count_range = list(
            map(int, sample_cfg["spalled_cube_fracture_tooth_count_range"])
        )
        if (
            len(tooth_count_range) != 2
            or not 2 <= tooth_count_range[0] <= tooth_count_range[1] <= 24
        ):
            raise ValueError(
                "Invalid spalled-cube fracture-tooth count contract"
            )
        spall_fracture_tooth_count = spall_rng.randint(*tooth_count_range)
        for index in range(spall_fracture_tooth_count):
            # Pass-10's 8--20 mm blocks read as loose cubes instead of
            # aggregate exposed in a fracture. Use more, smaller anisotropic
            # pieces and keep their centres farther inside the cut planes.
            tooth_dims = (
                spall_rng.uniform(0.32, 0.92),
                spall_rng.uniform(0.24, 0.74),
                spall_rng.uniform(0.30, 0.88),
            )
            if index % 2 == 0:
                # Embed aggregate into the vertical inner fracture wall. The
                # centre sits on the retained-body side; no loose-looking
                # block is allowed to float in the removed corner volume.
                local_center = (
                    notch_side_sign
                    * (dims[0] / 2.0 - notch_x - tooth_dims[0] * 0.30),
                    dims[1] / 2.0
                    - notch_y * spall_rng.uniform(0.12, 0.88),
                    dims[2] / 2.0
                    - notch_z * spall_rng.uniform(0.16, 0.84),
                )
            else:
                # Embed the remaining aggregate into the fracture floor.
                local_center = (
                    notch_side_sign
                    * (
                        dims[0] / 2.0
                        - notch_x * spall_rng.uniform(0.18, 0.86)
                    ),
                    dims[1] / 2.0
                    - notch_y * spall_rng.uniform(0.10, 0.86),
                    dims[2] / 2.0
                    - notch_z
                    - tooth_dims[2] * 0.30,
                )
            _spawn_mesh(
                f"SEM_CONCRETE spall fracture tooth {index:02d}",
                "cube",
                world_from_sample_local(*local_center),
                tooth_dims,
                materials["aggregate" if index % 3 else "concrete_dark"],
                rotation=_rotator(
                    pitch=spall_rng.uniform(-28.0, 28.0),
                    yaw=yaw + spall_rng.uniform(-34.0, 34.0),
                    roll=spall_rng.uniform(-28.0, 28.0),
                ),
                instance_key=instance_key,
                semantic_class="concrete_sample",
                role="sample_spall_fracture",
            )
        body_profile = "notched_upper_front_corner_with_inset_aggregate_v5"
        spall_notch_cm = [notch_x, notch_y, notch_z]
        spall_notch_side = "left" if notch_side_sign < 0.0 else "right"
    else:
        _spawn_mesh(
            "SEM_CONCRETE_SAMPLE",
            shape,
            (px, py, pz),
            dims,
            materials["concrete"],
            rotation=_rotator(yaw=yaw),
            instance_key=instance_key,
            semantic_class="concrete_sample",
            role="sample_body",
        )

    if shape == "cylinder" and surface_regime == "spalled":
        # Runtime subtraction on the engine cylinder is not stable enough for
        # annotation production.  Use a bounded, mostly embedded faceted
        # cluster at one upper loaded side; metadata labels this honestly as an
        # additive proxy so it cannot be mistaken for a mechanics simulation.
        spall_rng = random.Random(
            f"{px:.9f}:{py:.9f}:{yaw:.9f}:{damage:.9f}:"
            "cylinder-spall-cluster-v1"
        )
        patch_width = spall_rng.uniform(*cylinder_spall_size_range)
        patch_height = spall_rng.uniform(
            cylinder_spall_size_range[0] * 0.72,
            patch_width * 1.08,
        )
        theta = spall_rng.uniform(-1.02, 1.02)
        cluster_z = spall_rng.uniform(dims[2] * 0.31, dims[2] * 0.45)
        cylinder_spall_aggregate_count = spall_rng.randint(18, 26)
        for index in range(cylinder_spall_aggregate_count):
            grain_radius = spall_rng.uniform(0.10, 0.32)
            local_theta = theta + spall_rng.uniform(-0.16, 0.16)
            radial = (
                dims[0] / 2.0
                - grain_radius * spall_rng.uniform(0.10, 0.30)
            )
            local_center = (
                math.sin(local_theta) * radial,
                math.cos(local_theta) * radial,
                cluster_z
                + spall_rng.uniform(-patch_height * 0.42, patch_height * 0.42),
            )
            material_key = (
                "aggregate"
                if index % 3 == 0
                else "concrete_load_stain_ochre"
                if index % 5 == 0
                else "concrete"
            )
            _spawn_mesh(
                f"SEM_CONCRETE cylinder spall aggregate {index:02d}",
                "cube",
                world_from_sample_local(*local_center),
                (
                    grain_radius * spall_rng.uniform(0.78, 1.55),
                    grain_radius * spall_rng.uniform(0.28, 0.62),
                    grain_radius * spall_rng.uniform(0.70, 1.48),
                ),
                materials[material_key],
                rotation=_rotator(
                    pitch=spall_rng.uniform(-38.0, 38.0),
                    yaw=yaw
                    - math.degrees(local_theta)
                    + spall_rng.uniform(-32.0, 32.0),
                    roll=spall_rng.uniform(-38.0, 38.0),
                ),
                instance_key=instance_key,
                semantic_class="concrete_sample",
                role="sample_cylinder_spall_proxy",
            )
        body_profile = "solid_nominal_with_additive_faceted_spall_proxy_v1"
        cylinder_spall_patch_size_cm = [patch_width, patch_height]
        cylinder_spall_patch_angle_deg = math.degrees(theta)

    # Nearly flush, very thin dark shells read as shallow casting voids without
    # the unstable runtime booleans or bead-like protrusions of the first proxy.
    pore_min, pore_max = map(int, sample_cfg["pore_count_range"])
    pore_count = int(pore_min + damage * (pore_max - pore_min))
    pore_radius_min, pore_radius_max = map(
        float, sample_cfg.get("pore_radius_cm", [0.045, 0.385])
    )
    pore_radius_power = float(
        sample_cfg.get("pore_radius_distribution_power", 2.5)
    )
    pore_rng = random.Random(
        f"{px:.9f}:{py:.9f}:{shape}:{damage:.9f}:{surface_regime}:"
        "primary-pores-v3"
    )
    for index in range(pore_count):
        radius = (
            pore_radius_min
            + (pore_radius_max - pore_radius_min)
            * (pore_rng.random() ** pore_radius_power)
        ) * (0.88 + damage * 0.20)
        face_roll = pore_rng.random()
        if shape == "cylinder":
            theta = pore_rng.uniform(-1.46, 1.46)
            pore_normal = (math.sin(theta), math.cos(theta), 0.0)
            x = px + math.sin(theta) * (dims[0] / 2.0 + radius * 0.01)
            y = py + math.cos(theta) * (dims[1] / 2.0 + radius * 0.01)
            z = pz + pore_rng.uniform(-dims[2] * 0.44, dims[2] * 0.44)
            pore_rotation = _rotator(roll=-90.0, yaw=-math.degrees(theta))
        elif face_roll < 0.78:
            pore_normal = (0.0, 1.0, 0.0)
            x = px + pore_rng.uniform(-dims[0] * 0.43, dims[0] * 0.43)
            y = py + dims[1] / 2.0 + radius * 0.01
            z = pz + pore_rng.uniform(-dims[2] * 0.43, dims[2] * 0.43)
            pore_rotation = _rotator(roll=-90.0)
        else:
            side = -1.0 if pore_rng.random() < 0.5 else 1.0
            pore_normal = (side, 0.0, 0.0)
            x = px + side * (dims[0] / 2.0 + radius * 0.01)
            y = py + pore_rng.uniform(-dims[1] * 0.4, dims[1] * 0.4)
            z = pz + pore_rng.uniform(-dims[2] * 0.4, dims[2] * 0.4)
            pore_rotation = _rotator(roll=90.0, yaw=side * 90.0)
        pore_aspect_x = pore_rng.uniform(1.02, 1.64)
        pore_aspect_y = pore_rng.uniform(0.72, 1.26)
        _spawn_mesh(
            f"SEM_CONCRETE pore interior {index:02d}",
            "cylinder",
            (x, y, z),
            (radius * pore_aspect_x, radius * pore_aspect_y, radius * 0.035),
            materials["concrete_dark"],
            rotation=pore_rotation,
            instance_key=instance_key,
            semantic_class="concrete_sample",
            role="sample_surface_detail",
        )

    # V20 deliberately removes the large procedural colour clouds. Preserve
    # the real pitted/spalled regimes with additional scale-correct cavities,
    # driven by an independent RNG so their refinement cannot reshuffle RFID,
    # paper, lighting or camera choices for the same scenario seed.
    additional_pore_count = int(
        sample_cfg["additional_regime_pore_count"][surface_regime]
    )
    regime_pore_rng = random.Random(
        f"{px:.9f}:{py:.9f}:{shape}:{damage:.9f}:{surface_regime}:extra-pores-v2"
    )
    for index in range(additional_pore_count):
        radius = 0.04 + 0.18 * (regime_pore_rng.random() ** 2.4)
        if shape == "cylinder":
            theta = regime_pore_rng.uniform(-1.46, 1.46)
            pore_normal = (math.sin(theta), math.cos(theta), 0.0)
            x = px + math.sin(theta) * (dims[0] / 2.0 + radius * 0.01)
            y = py + math.cos(theta) * (dims[1] / 2.0 + radius * 0.01)
            z = pz + regime_pore_rng.uniform(-dims[2] * 0.43, dims[2] * 0.43)
            pore_rotation = _rotator(roll=-90.0, yaw=-math.degrees(theta))
        elif regime_pore_rng.random() < 0.82:
            pore_normal = (0.0, 1.0, 0.0)
            x = px + regime_pore_rng.uniform(-dims[0] * 0.42, dims[0] * 0.42)
            y = py + dims[1] / 2.0 + radius * 0.01
            z = pz + regime_pore_rng.uniform(-dims[2] * 0.42, dims[2] * 0.42)
            pore_rotation = _rotator(roll=-90.0)
        else:
            side = -1.0 if regime_pore_rng.random() < 0.5 else 1.0
            pore_normal = (side, 0.0, 0.0)
            x = px + side * (dims[0] / 2.0 + radius * 0.01)
            y = py + regime_pore_rng.uniform(-dims[1] * 0.38, dims[1] * 0.38)
            z = pz + regime_pore_rng.uniform(-dims[2] * 0.38, dims[2] * 0.38)
            pore_rotation = _rotator(roll=90.0, yaw=side * 90.0)
        _spawn_mesh(
            f"SEM_CONCRETE regime pore interior {index:02d}",
            "cylinder",
            (x, y, z),
            (
                radius * regime_pore_rng.uniform(1.15, 1.65),
                radius * regime_pore_rng.uniform(0.90, 1.35),
                radius * 0.05,
            ),
            materials["concrete_dark"],
            rotation=pore_rotation,
            instance_key=instance_key,
            semantic_class="concrete_sample",
            role="sample_surface_detail",
        )

    aggregate_rng = random.Random(
        f"{px:.9f}:{py:.9f}:{yaw:.9f}:{shape}:{damage:.9f}:"
        f"{surface_regime}:exposed-aggregate-v1"
    )
    aggregate_count_range = list(
        map(int, aggregate_ranges[surface_regime])
    )
    exposed_aggregate_count = aggregate_rng.randint(*aggregate_count_range)
    exposed_aggregate_material_counts = {
        "light_aggregate": 0,
        "dark_mortar": 0,
        "body_tone": 0,
    }
    aggregate_radius_min, aggregate_radius_max = aggregate_radius_range
    for index in range(exposed_aggregate_count):
        radius = aggregate_radius_min + (
            aggregate_radius_max - aggregate_radius_min
        ) * (aggregate_rng.random() ** 1.75)
        if shape == "cylinder":
            theta = aggregate_rng.uniform(-1.42, 1.42)
            radial = dims[0] / 2.0 - radius * aggregate_rng.uniform(0.10, 0.28)
            local_center = (
                math.sin(theta) * radial,
                math.cos(theta) * radial,
                aggregate_rng.uniform(-dims[2] * 0.41, dims[2] * 0.41),
            )
            detail_dims = (
                radius * aggregate_rng.uniform(0.96, 1.84),
                radius * aggregate_rng.uniform(0.32, 0.58),
                radius * aggregate_rng.uniform(0.88, 1.76),
            )
            detail_rotation = _rotator(
                pitch=aggregate_rng.uniform(-24.0, 24.0),
                yaw=yaw
                - math.degrees(theta)
                + aggregate_rng.uniform(-18.0, 18.0),
                roll=aggregate_rng.uniform(-24.0, 24.0),
            )
        else:
            on_front = aggregate_rng.random() < 0.82
            if on_front:
                local_center = (
                    aggregate_rng.uniform(-dims[0] * 0.42, dims[0] * 0.42),
                    dims[1] / 2.0
                    - radius * aggregate_rng.uniform(0.10, 0.28),
                    aggregate_rng.uniform(-dims[2] * 0.41, dims[2] * 0.41),
                )
                detail_dims = (
                    radius * aggregate_rng.uniform(0.96, 1.84),
                    radius * aggregate_rng.uniform(0.32, 0.58),
                    radius * aggregate_rng.uniform(0.88, 1.76),
                )
                detail_rotation = _rotator(
                    pitch=aggregate_rng.uniform(-24.0, 24.0),
                    yaw=yaw + aggregate_rng.uniform(-18.0, 18.0),
                    roll=aggregate_rng.uniform(-24.0, 24.0),
                )
            else:
                side = -1.0 if aggregate_rng.random() < 0.5 else 1.0
                local_center = (
                    side
                    * (
                        dims[0] / 2.0
                        - radius * aggregate_rng.uniform(0.10, 0.28)
                    ),
                    aggregate_rng.uniform(-dims[1] * 0.20, dims[1] * 0.42),
                    aggregate_rng.uniform(-dims[2] * 0.40, dims[2] * 0.40),
                )
                detail_dims = (
                    radius * aggregate_rng.uniform(0.32, 0.58),
                    radius * aggregate_rng.uniform(0.96, 1.84),
                    radius * aggregate_rng.uniform(0.88, 1.76),
                )
                detail_rotation = _rotator(
                    pitch=aggregate_rng.uniform(-24.0, 24.0),
                    yaw=yaw + aggregate_rng.uniform(-18.0, 18.0),
                    roll=aggregate_rng.uniform(-24.0, 24.0),
                )
        material_roll = aggregate_rng.random()
        if material_roll < 0.34:
            material_key = "aggregate"
            exposed_aggregate_material_counts["light_aggregate"] += 1
        elif material_roll < 0.54:
            material_key = "concrete_dark"
            exposed_aggregate_material_counts["dark_mortar"] += 1
        else:
            material_key = "concrete"
            exposed_aggregate_material_counts["body_tone"] += 1
        _spawn_mesh(
            f"SEM_CONCRETE exposed aggregate {index:02d}",
            "cube",
            world_from_sample_local(*local_center),
            detail_dims,
            materials[material_key],
            rotation=detail_rotation,
            instance_key=instance_key,
            semantic_class="concrete_sample",
            role="sample_exposed_aggregate",
        )

    # Actual task-9..14 LED pixels and every REF machine/camera group show a
    # localized dirty load zone just below the upper platen.  Keep it as part
    # of the concrete instance and mostly embed several sub-millimetre
    # ellipsoids so the nominal detector silhouette and amodal bbox stay
    # unchanged.  An independent RNG prevents this material correction from
    # reshuffling RFID, paper, camera or light choices for the same seed.
    weathering_rng = random.Random(
        f"{px:.9f}:{py:.9f}:{shape}:{damage:.9f}:{surface_regime}:"
        "top-load-weathering-v1"
    )
    weathering_count_range = list(
        map(int, weathering_count_ranges[surface_regime])
    )
    top_load_weathering_patch_count = weathering_rng.randint(
        *weathering_count_range
    )
    weathering_cluster_theta = weathering_rng.uniform(-0.72, 0.72)
    weathering_cluster_x = weathering_rng.uniform(-0.24, 0.24) * dims[0]
    weathering_side_sign = -1.0 if weathering_rng.random() < 0.5 else 1.0
    weathering_cluster_depth = weathering_rng.uniform(*weathering_depth_range)
    weathering_material_counts = {"ochre": 0, "dark": 0}
    for index in range(top_load_weathering_patch_count):
        patch_width = dims[0] * weathering_rng.uniform(
            *weathering_width_range
        )
        patch_height = dims[2] * weathering_rng.uniform(
            *weathering_height_range
        )
        half_thickness = weathering_rng.uniform(*weathering_thickness_range)
        patch_depth_fraction = max(
            weathering_depth_range[0],
            min(
                weathering_depth_range[1],
                weathering_cluster_depth
                + weathering_rng.uniform(-0.025, 0.025),
            ),
        )
        local_z = min(
            dims[2] / 2.0 - patch_height * 0.52,
            dims[2] / 2.0 - dims[2] * patch_depth_fraction,
        )
        if shape == "cylinder":
            theta = max(
                -1.40,
                min(
                    1.40,
                    weathering_cluster_theta
                    + weathering_rng.uniform(-0.16, 0.16),
                ),
            )
            radial = dims[0] / 2.0 - half_thickness * 0.86
            local_center = (
                math.sin(theta) * radial,
                math.cos(theta) * radial,
                local_z,
            )
            patch_dims = (
                patch_width,
                patch_height,
                half_thickness * 2.0,
            )
            patch_rotation = _rotator(
                roll=-90.0, yaw=yaw - math.degrees(theta)
            )
        else:
            on_front = index % 4 != 3
            if on_front:
                local_center = (
                    max(
                        -dims[0] * 0.42,
                        min(
                            dims[0] * 0.42,
                            weathering_cluster_x
                            + weathering_rng.uniform(-0.07, 0.07) * dims[0],
                        ),
                    ),
                    dims[1] / 2.0 - half_thickness * 0.86,
                    local_z,
                )
                patch_dims = (
                    patch_width,
                    patch_height,
                    half_thickness * 2.0,
                )
                patch_rotation = _rotator(roll=-90.0, yaw=yaw)
            else:
                local_center = (
                    weathering_side_sign
                    * (dims[0] / 2.0 - half_thickness * 0.86),
                    max(
                        -dims[1] * 0.18,
                        min(
                            dims[1] * 0.42,
                            dims[1] * 0.26
                            + weathering_rng.uniform(-0.06, 0.06) * dims[1],
                        ),
                    ),
                    local_z,
                )
                patch_dims = (
                    patch_width,
                    patch_height,
                    half_thickness * 2.0,
                )
                patch_rotation = _rotator(
                    roll=90.0,
                    yaw=yaw + weathering_side_sign * 90.0,
                )
        material_key = (
            "concrete_load_stain_ochre"
            if weathering_rng.random() < 0.68
            else "concrete_load_stain_dark"
        )
        weathering_material_counts[
            "ochre" if material_key.endswith("ochre") else "dark"
        ] += 1
        patch = _spawn_mesh(
            f"SEM_CONCRETE upper load-zone residue {index:02d}",
            "cylinder",
            world_from_sample_local(*local_center),
            patch_dims,
            materials[material_key],
            rotation=patch_rotation,
            instance_key=instance_key,
            semantic_class="concrete_sample",
            role="sample_top_load_weathering",
        )
        patch.static_mesh_component.set_editor_property("cast_shadow", False)

    # Exposed aggregate and a chipped upper edge are part of the same target instance.
    fragment_count = 5 + int(damage * 8)
    for index in range(fragment_count):
        if shape == "cylinder":
            theta = rng.uniform(-1.5, 1.5)
            radial = dims[0] / 2.0 - rng.uniform(0.0, 0.9)
            x = px + math.sin(theta) * radial
            y = py + math.cos(theta) * radial
        else:
            x = px + rng.uniform(-dims[0] * 0.46, dims[0] * 0.46)
            y = py + dims[1] / 2.0 + rng.uniform(-0.28, 0.1)
        z = pz + dims[2] / 2.0 + rng.uniform(-0.32, 0.04)
        fragment_rng = random.Random(
            f"{px:.9f}:{py:.9f}:{damage:.9f}:{shape}:{index}:fragment-rotation-v1"
        )
        _spawn_mesh(
            f"SEM_CONCRETE chipped aggregate {index:02d}",
            "cube",
            (x, y, z),
            (rng.uniform(0.16, 0.42), rng.uniform(0.14, 0.38), rng.uniform(0.10, 0.28)),
            materials["aggregate" if index % 3 == 0 else "concrete"],
            rotation=_rotator(
                pitch=fragment_rng.uniform(-38.0, 38.0),
                yaw=fragment_rng.uniform(-38.0, 38.0),
                roll=fragment_rng.uniform(-38.0, 38.0),
            ),
            instance_key=instance_key,
            semantic_class="concrete_sample",
            role="sample_surface_detail",
        )

    # Real certified specimens remain nominally regular but their loaded edges
    # range from clean to locally spalled.  These small, mostly embedded actors
    # create bounded parallax/silhouette wear without unstable runtime booleans.
    relief_count_range = list(
        map(int, relief_ranges[surface_regime])
    )
    edge_relief_count = surface_rng.randint(*relief_count_range)
    relief_min, relief_max = relief_size_range
    for index in range(edge_relief_count):
        radius = relief_min + (relief_max - relief_min) * (surface_rng.random() ** 2.1)
        if shape == "cylinder":
            theta = surface_rng.uniform(-1.52, 1.52)
            radial = dims[0] / 2.0 - radius * surface_rng.uniform(0.38, 0.55)
            x = px + math.sin(theta) * radial
            y = py + math.cos(theta) * radial
            z = pz + dims[2] / 2.0 - radius * surface_rng.uniform(0.38, 0.58)
            detail_dims = (
                radius * surface_rng.uniform(0.78, 1.18),
                radius * surface_rng.uniform(0.70, 1.08),
                radius * surface_rng.uniform(0.62, 1.00),
            )
        else:
            edge_mode = surface_rng.randrange(3)
            side = -1.0 if surface_rng.random() < 0.5 else 1.0
            if edge_mode == 0:
                x = px + surface_rng.uniform(-dims[0] * 0.44, dims[0] * 0.44)
                y = py + dims[1] / 2.0 - radius * surface_rng.uniform(0.38, 0.55)
                z = pz + dims[2] / 2.0 - radius * surface_rng.uniform(0.38, 0.56)
            elif edge_mode == 1:
                x = px + side * (
                    dims[0] / 2.0 - radius * surface_rng.uniform(0.38, 0.55)
                )
                y = py + surface_rng.uniform(-dims[1] * 0.43, dims[1] * 0.20)
                z = pz + dims[2] / 2.0 - radius * surface_rng.uniform(0.38, 0.58)
            else:
                x = px + side * (
                    dims[0] / 2.0 - radius * surface_rng.uniform(0.38, 0.56)
                )
                y = py + dims[1] / 2.0 - radius * surface_rng.uniform(0.38, 0.56)
                z = pz + surface_rng.uniform(-dims[2] * 0.35, dims[2] * 0.35)
            detail_dims = (
                radius * surface_rng.uniform(0.76, 1.14),
                radius * surface_rng.uniform(0.66, 1.04),
                radius * surface_rng.uniform(0.70, 1.08),
            )
        _spawn_mesh(
            f"SEM_CONCRETE bounded edge relief {index:02d}",
            "cube",
            (x, y, z),
            detail_dims,
            materials[
                "aggregate"
                if surface_regime == "spalled" and index % 3 == 0
                else "concrete_dark"
                if index % 5 == 0
                else "concrete"
            ],
            rotation=_rotator(
                pitch=surface_rng.uniform(-32.0, 32.0),
                yaw=surface_rng.uniform(-32.0, 32.0),
                roll=surface_rng.uniform(-32.0, 32.0),
            ),
            instance_key=instance_key,
            semantic_class="concrete_sample",
            role="sample_edge_relief",
        )

    return {
        "instance_key": instance_key,
        "shape": shape,
        "location_cm": [px, py, pz],
        "dimensions_cm": list(dims),
        "yaw_deg": yaw,
        "damage": damage,
        "pore_count": pore_count,
        "pore_radius_range_cm": [pore_radius_min, pore_radius_max],
        "pore_radius_distribution_power": pore_radius_power,
        "surface_regime": surface_regime,
        "surface_profile": "fine_cast_tone_with_irregular_flush_pores_exposed_aggregate_spall_and_load_zone_v7",
        "pore_proxy_profile": "single_layer_low_contrast_variable_aspect_flush_void_v3",
        "body_profile": body_profile,
        "spall_notch_cm": spall_notch_cm,
        "spall_notch_side": spall_notch_side,
        "spall_fracture_tooth_count": spall_fracture_tooth_count,
        "spall_notch_status": sample_cfg["spalled_cube_notch_status"],
        "cylinder_spall_patch_size_cm": cylinder_spall_patch_size_cm,
        "cylinder_spall_patch_angle_deg": cylinder_spall_patch_angle_deg,
        "cylinder_spall_aggregate_count": cylinder_spall_aggregate_count,
        "cylinder_spall_status": sample_cfg["spalled_cylinder_patch_status"],
        "additional_regime_pore_count": additional_pore_count,
        "exposed_aggregate_count": exposed_aggregate_count,
        "exposed_aggregate_radius_range_cm": [
            aggregate_radius_min,
            aggregate_radius_max,
        ],
        "exposed_aggregate_material_counts": (
            exposed_aggregate_material_counts
        ),
        "edge_relief_count": edge_relief_count,
        "edge_relief_size_range_cm": [relief_min, relief_max],
        "top_load_weathering_patch_count": top_load_weathering_patch_count,
        "top_load_weathering_material_counts": weathering_material_counts,
        "top_load_weathering_profile": "clustered_submillimetre_embedded_ochre_dark_residue_v1",
        "top_load_weathering_status": sample_cfg[
            "top_load_weathering_status"
        ],
        "surface_regime_distribution_status": sample_cfg["surface_regime_status"],
    }


def _tag_transform(
    state: str,
    sample: dict[str, Any],
    machine: dict[str, float],
    tag_cfg: dict[str, Any],
    rng: random.Random,
    index: int,
    tag_length: float,
    seed: int,
):
    px, py, pz = map(float, sample["location_cm"])
    sx, sy, sz = map(float, sample["dimensions_cm"])
    angle = rng.uniform(*map(float, tag_cfg["in_plane_rotation_deg"]))
    angle_rad = math.radians(angle)
    standoff = float(tag_cfg.get("surface_standoff_cm", 0.055))
    visible_tip: float | None = None
    tip_regime: str | None = None
    if state == "sample_front":
        x = px + rng.uniform(-sx * 0.31, sx * 0.31)
        z = pz + rng.uniform(-sz * 0.29, sz * 0.31)
        if sample["shape"] == "cylinder":
            radius = sx / 2.0
            local_x = max(-radius * 0.92, min(radius * 0.92, x - px))
            tangent_yaw = math.asin(local_x / radius)
            normal = (math.sin(tangent_yaw), math.cos(tangent_yaw), 0.0)
            surface_y = py + math.sqrt(max(0.0, radius * radius - local_x * local_x))
            location = (
                x + normal[0] * standoff,
                surface_y + normal[1] * standoff,
                z,
            )
            rotation = _rotator(pitch=angle, yaw=-math.degrees(tangent_yaw))
            length_axis = (
                math.cos(tangent_yaw) * math.cos(angle_rad),
                -math.sin(tangent_yaw) * math.cos(angle_rad),
                math.sin(angle_rad),
            )
            contact_model = "cylinder_conformed_arc"
        else:
            location = (x, py + sy / 2.0 + standoff, z)
            rotation = _rotator(pitch=angle)
            normal = (0.0, 1.0, 0.0)
            length_axis = (math.cos(angle_rad), 0.0, math.sin(angle_rad))
            contact_model = "planar_sample_face"
    elif state == "sample_side":
        side = -1.0 if index % 2 == 0 else 1.0
        z = pz + rng.uniform(-sz * 0.22, sz * 0.25)
        if sample["shape"] == "cylinder":
            radius = sx / 2.0
            tangent_yaw = side * math.acos(0.26)
            normal = (math.sin(tangent_yaw), math.cos(tangent_yaw), 0.0)
            location = (
                px + normal[0] * (radius + standoff),
                py + normal[1] * (radius + standoff),
                z,
            )
            rotation = _rotator(pitch=angle, yaw=-math.degrees(tangent_yaw))
            length_axis = (
                math.cos(tangent_yaw) * math.cos(angle_rad),
                -math.sin(tangent_yaw) * math.cos(angle_rad),
                math.sin(angle_rad),
            )
            contact_model = "cylinder_conformed_arc"
        else:
            location = (
                px + side * (sx / 2.0 + standoff),
                py + sy * 0.13,
                z,
            )
            rotation = _rotator(pitch=angle, yaw=-side * 90.0)
            normal = (side, 0.0, 0.0)
            length_axis = (
                0.0,
                -side * math.cos(angle_rad),
                math.sin(angle_rad),
            )
            contact_model = "planar_sample_face"
    elif state == "plate_gap_top":
        modulo = int(tag_cfg["plate_gap_tip_regime_seed_modulo"])
        tip_regime = tag_cfg["plate_gap_tip_regime_by_remainder"][
            str(int(seed) % modulo)
        ]
        visible_tip = rng.uniform(
            *map(
                float,
                tag_cfg["plate_gap_tip_regimes"][tip_regime][
                    "plate_gap_top_cm"
                ],
            )
        )
        x = px + rng.uniform(-sx * 0.22, sx * 0.22)
        if sample["shape"] == "cylinder":
            radius = sx / 2.0
            local_x = max(-radius * 0.92, min(radius * 0.92, x - px))
            front_y = py + math.sqrt(max(0.0, radius * radius - local_x * local_x))
        else:
            front_y = py + sy / 2.0
        length_axis = (-math.sin(angle_rad), -math.cos(angle_rad), 0.0)
        half_y_extent = abs(length_axis[1]) * tag_length / 2.0
        location = (
            x,
            front_y - half_y_extent + visible_tip,
            pz + sz / 2.0 + 0.025,
        )
        rotation = _rotator(roll=90.0, yaw=-90.0 - angle)
        normal = (0.0, 0.0, 1.0)
        contact_model = "plate_gap_visible_tip"
    elif state == "plate_gap_bottom":
        modulo = int(tag_cfg["plate_gap_tip_regime_seed_modulo"])
        tip_regime = tag_cfg["plate_gap_tip_regime_by_remainder"][
            str(int(seed) % modulo)
        ]
        visible_tip = rng.uniform(
            *map(
                float,
                tag_cfg["plate_gap_tip_regimes"][tip_regime][
                    "plate_gap_bottom_cm"
                ],
            )
        )
        x = px + rng.uniform(-sx * 0.24, sx * 0.24)
        if sample["shape"] == "cylinder":
            radius = sx / 2.0
            local_x = max(-radius * 0.92, min(radius * 0.92, x - px))
            front_y = py + math.sqrt(max(0.0, radius * radius - local_x * local_x))
        else:
            front_y = py + sy / 2.0
        length_axis = (-math.sin(angle_rad), -math.cos(angle_rad), 0.0)
        half_y_extent = abs(length_axis[1]) * tag_length / 2.0
        location = (
            x,
            front_y - half_y_extent + visible_tip,
            machine["lower_platen_top_z_cm"] + 0.02,
        )
        rotation = _rotator(roll=90.0, yaw=-90.0 - angle)
        normal = (0.0, 0.0, 1.0)
        contact_model = "plate_gap_visible_tip"
    else:  # loose_front
        theta = rng.uniform(-1.15, 1.15)
        radius = rng.uniform(17.0, 25.0)
        location = (math.sin(theta) * radius, machine["platen_center_y_cm"] + math.cos(theta) * radius * 0.64, machine["lower_platen_top_z_cm"] + rng.uniform(0.12, 0.6))
        roll = math.radians(rng.uniform(64.0, 88.0))
        rotation = _rotator(roll=math.degrees(roll), yaw=angle)
        normal = (
            -math.sin(angle_rad) * math.cos(roll),
            math.cos(angle_rad) * math.cos(roll),
            math.sin(roll),
        )
        length_axis = (math.cos(angle_rad), math.sin(angle_rad), 0.0)
        contact_model = "loose_platen"
    return (
        location,
        rotation,
        normal,
        angle,
        length_axis,
        contact_model,
        visible_tip,
        tip_regime,
    )


def _spawn_rfid_instance(
    cfg: dict[str, Any], materials: dict[str, unreal.Material], sample: dict[str, Any], machine: dict[str, float], rng: random.Random, index: int, state: str, seed: int
) -> dict[str, Any]:
    tag_cfg = cfg["rfid_tag"]
    length, thickness, width = map(float, tag_cfg["size_cm"])
    instance_key = f"rfid_{index:02d}"
    (
        location,
        rotation,
        normal,
        angle,
        length_axis,
        contact_model,
        visible_tip,
        tip_regime,
    ) = _tag_transform(
        state,
        sample,
        machine,
        tag_cfg,
        rng,
        index,
        length,
        seed,
    )
    # A simplified but physically dimensional copper antenna and epoxy package.
    # Offsets are intentionally tiny; same-instance mask includes every part.
    if state in {"sample_front", "sample_side"}:
        facing_offset = 0.04
    else:
        facing_offset = 0.025
    nx, ny, nz = normal
    conformed = contact_model == "cylinder_conformed_arc"
    conform_segment_count = 1
    if conformed:
        conform_segment_count = int(tag_cfg.get("cylinder_conform_segments", 10))
        if not 6 <= conform_segment_count <= 24:
            raise ValueError("rfid_tag.cylinder_conform_segments must be within 6..24")
        px, py, _pz = map(float, sample["location_cm"])
        radius = float(sample["dimensions_cm"][0]) / 2.0
        standoff = float(tag_cfg.get("surface_standoff_cm", 0.055))
        angle_rad = math.radians(angle)
        center_theta = math.atan2(float(normal[0]), float(normal[1]))

        def arc_pose(
            distance_along_tag: float,
            radial_offset: float,
        ) -> tuple[tuple[float, float, float], unreal.Rotator]:
            theta = center_theta + (
                distance_along_tag * math.cos(angle_rad) / radius
            )
            radial_distance = radius + standoff + radial_offset
            pose_location = (
                px + math.sin(theta) * radial_distance,
                py + math.cos(theta) * radial_distance,
                float(location[2]) + distance_along_tag * math.sin(angle_rad),
            )
            pose_rotation = _rotator(
                pitch=angle,
                yaw=-math.degrees(theta),
            )
            return pose_location, pose_rotation

        film_segment_length = length / conform_segment_count
        for segment in range(conform_segment_count):
            distance = -length / 2.0 + (segment + 0.5) * film_segment_length
            segment_location, segment_rotation = arc_pose(distance, 0.0)
            _spawn_mesh(
                f"SEM_RFID_{index:02d} conformed film {segment:02d}",
                "cube",
                segment_location,
                (film_segment_length + 0.025, max(thickness, 0.018), width),
                materials["rfid_film"],
                rotation=segment_rotation,
                instance_key=instance_key,
                semantic_class="rfid_tag",
                role=state,
            )

        antenna_segments_per_wing = 4
        antenna_segment_length = 2.45 / antenna_segments_per_wing
        for side, sign in (("left", -1.0), ("right", 1.0)):
            for segment in range(antenna_segments_per_wing):
                distance = (
                    sign * 1.48
                    - 2.45 / 2.0
                    + (segment + 0.5) * antenna_segment_length
                )
                segment_location, segment_rotation = arc_pose(
                    distance, facing_offset
                )
                _spawn_mesh(
                    f"SEM_RFID_{index:02d} conformed copper {side} {segment:02d}",
                    "cube",
                    segment_location,
                    (antenna_segment_length + 0.025, 0.022, 0.56),
                    materials["copper"],
                    rotation=segment_rotation,
                    instance_key=instance_key,
                    semantic_class="rfid_tag",
                    role="antenna",
                )
        front, chip_rotation = arc_pose(0.0, facing_offset)
    else:
        # Flat cube faces, platen gaps and loose tags retain one film body.
        _spawn_mesh(
            f"SEM_RFID_{index:02d} film",
            "cube",
            location,
            (length, max(thickness, 0.018), width),
            materials["rfid_film"],
            rotation=rotation,
            instance_key=instance_key,
            semantic_class="rfid_tag",
            role=state,
        )
        front = (
            location[0] + nx * facing_offset,
            location[1] + ny * facing_offset,
            location[2] + nz * facing_offset,
        )
        for side, sign in (("left", -1.0), ("right", 1.0)):
            wing_location = tuple(
                front[axis] + sign * 1.48 * length_axis[axis]
                for axis in range(3)
            )
            _spawn_mesh(
                f"SEM_RFID_{index:02d} copper {side}",
                "cube",
                wing_location,
                (2.45, 0.022, 0.56),
                materials["copper"],
                rotation=rotation,
                instance_key=instance_key,
                semantic_class="rfid_tag",
                role="antenna",
            )
        chip_rotation = rotation
    _spawn_mesh(
        f"SEM_RFID_{index:02d} chip",
        "sphere",
        front,
        (float(tag_cfg["center_dome_diameter_cm"]), 0.14, float(tag_cfg["center_dome_diameter_cm"])),
        materials["chip"],
        rotation=chip_rotation,
        instance_key=instance_key,
        semantic_class="rfid_tag",
        role="chip",
    )
    return {
        "instance_key": instance_key,
        "state": state,
        "location_cm": list(location),
        "rotation_deg": {"in_plane": angle},
        "physical_size_cm": [length, thickness, width],
        "surface_normal_world": list(normal),
        "length_axis_world": list(length_axis),
        "contact_model": contact_model,
        "contact_profile": tag_cfg["contact_profile"],
        "visible_tip_target_cm": visible_tip,
        "visible_tip_regime": tip_regime,
        "conform_segment_count": conform_segment_count,
    }


def _spawn_paper_labels(
    cfg: dict[str, Any],
    materials: dict[str, unreal.Material],
    sample: dict[str, Any],
    tags: list[dict[str, Any]],
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Spawn used non-target paper forms with physical RFID occlusion.

    The current primitive stays on planar cube faces.  A floating flat card on
    a cylinder would be a stronger synthetic shortcut than omitting it until a
    conformed mesh is measured and implemented.
    """

    paper_cfg = cfg.get("paper_label", {})
    if (
        not paper_cfg.get("enabled", False)
        or sample.get("shape") != "cube"
        or rng.random() > float(paper_cfg.get("cube_occurrence_probability", 0.0))
    ):
        return []

    paper_length, paper_thickness, paper_height = map(
        float, paper_cfg.get("size_cm", [9.5, 0.025, 7.0])
    )
    px, py, pz = map(float, sample["location_cm"])
    sx, sy, sz = map(float, sample["dimensions_cm"])
    candidates = [
        index for index, tag in enumerate(tags) if tag.get("state") == "sample_front"
    ]
    linked_index: int | None = None
    mode = "independent"
    visible_fraction: float | None = None
    angle = rng.uniform(*map(float, paper_cfg.get("rotation_deg", [-9.0, 9.0])))
    paper_center = (
        px + rng.uniform(-sx * 0.16, sx * 0.16),
        py + sy / 2.0 + 0.085,
        pz + rng.uniform(-sz * 0.18, sz * 0.18),
    )

    if candidates and rng.random() < float(paper_cfg.get("rfid_link_probability", 0.72)):
        linked_index = candidates[rng.randrange(len(candidates))]
        linked = tags[linked_index]
        mode = _weighted_choice(
            rng,
            paper_cfg.get(
                "rfid_occlusion_weights",
                {"partial_tip_visible": 0.78, "fully_hidden": 0.22},
            ),
        )
        angle = float(linked["rotation_deg"]["in_plane"])
        tx, ty, tz = map(float, linked["location_cm"])
        local_x = rng.uniform(-0.2, 0.2)
        if mode == "partial_tip_visible":
            low, high = map(
                float,
                paper_cfg.get("visible_tag_tip_fraction_range", [0.15, 0.50]),
            )
            visible_fraction = rng.uniform(low, high)
            tag_length = float(linked["physical_size_cm"][0])
            direction = -1.0 if rng.random() < 0.5 else 1.0
            visible_length = tag_length * visible_fraction
            cover_edge = direction * (tag_length / 2.0 - visible_length)
            local_x = cover_edge - direction * paper_length / 2.0
        radians = math.radians(angle)
        paper_center = (
            tx + local_x * math.cos(radians),
            ty + 0.095,
            tz - local_x * math.sin(radians),
        )

    paper_rotation = _rotator(pitch=angle)
    paper_style_rng = random.Random(
        f"{px:.9f}:{py:.9f}:{pz:.9f}:{angle:.9f}:paper-style-v1"
    )
    paper_colour_profile = _weighted_choice(
        paper_style_rng,
        paper_cfg.get(
            "colour_profile_weights",
            {"white_form": 0.52, "aged_form": 0.32, "orange_decoy": 0.16},
        ),
    )
    paper_material_by_profile = {
        "white_form": "paper_white",
        "aged_form": "paper",
        "orange_decoy": "paper_orange",
    }
    if paper_colour_profile not in paper_material_by_profile:
        raise ValueError(
            f"Unsupported paper colour profile: {paper_colour_profile}"
        )
    paper_actor = _spawn_mesh(
        "Specimen paper form 00",
        "cube",
        paper_center,
        (paper_length, paper_thickness, paper_height),
        materials[paper_material_by_profile[paper_colour_profile]],
        rotation=paper_rotation,
        role="paper_occluder",
    )
    paper_actor.static_mesh_component.set_editor_property("cast_shadow", True)

    def place(local_x: float, local_z: float, front_offset: float = 0.0):
        radians = math.radians(angle)
        return (
            paper_center[0] + local_x * math.cos(radians) + local_z * math.sin(radians),
            paper_center[1] + paper_thickness / 2.0 + front_offset,
            paper_center[2] - local_x * math.sin(radians) + local_z * math.cos(radians),
        )

    row_count = int(paper_cfg.get("print_row_count", 7))
    for row_index in range(row_count):
        line_length = paper_length * rng.uniform(0.36, 0.76)
        line_x = rng.uniform(-paper_length * 0.10, paper_length * 0.08)
        line_z = paper_height * (0.29 - row_index * 0.085)
        _spawn_mesh(
            f"Specimen paper print row {row_index:02d}",
            "cube",
            place(line_x, line_z, 0.018),
            (line_length, 0.018, 0.075 if row_index else 0.13),
            materials["paper_ink"],
            rotation=paper_rotation,
            role="paper_print",
        )

    handwriting_low, handwriting_high = map(
        int, paper_cfg.get("handwriting_stroke_range", [3, 6])
    )
    handwriting_count = rng.randint(handwriting_low, handwriting_high)
    for stroke_index in range(handwriting_count):
        stroke_angle = angle + rng.uniform(-22.0, 22.0)
        _spawn_mesh(
            f"Specimen paper handwriting {stroke_index:02d}",
            "cube",
            place(
                rng.uniform(-paper_length * 0.22, paper_length * 0.22),
                rng.uniform(-paper_height * 0.24, paper_height * 0.18),
                0.021,
            ),
            (rng.uniform(0.75, 2.2), 0.019, rng.uniform(0.045, 0.085)),
            materials["paper_ink"],
            rotation=_rotator(pitch=stroke_angle),
            role="paper_handwriting",
        )

    tape_low, tape_high = map(int, paper_cfg.get("tape_count_range", [2, 4]))
    tape_count = rng.randint(tape_low, tape_high)
    for tape_index in range(tape_count):
        edge_z = (
            paper_height * 0.48 * (-1.0 if tape_index % 2 == 0 else 1.0)
            + rng.uniform(-0.25, 0.25)
        )
        tape_angle = angle + rng.uniform(-7.0, 7.0)
        _spawn_mesh(
            f"Specimen paper tape {tape_index:02d}",
            "cube",
            place(rng.uniform(-paper_length * 0.36, paper_length * 0.36), edge_z, 0.026),
            (rng.uniform(2.0, 3.6), 0.022, rng.uniform(0.55, 0.82)),
            materials["paper_tape"],
            rotation=_rotator(pitch=tape_angle),
            role="paper_tape",
        )

    linked_key = tags[linked_index]["instance_key"] if linked_index is not None else None
    record = {
        "paper_index": 0,
        "occlusion_mode": mode,
        "linked_rfid_instance_key": linked_key,
        "visible_tag_tip_fraction_target": visible_fraction,
        "location_cm": list(paper_center),
        "rotation_deg": {"in_plane": angle},
        "size_cm": [paper_length, paper_thickness, paper_height],
        "surface_profile": "used_stained_procedural_paper",
        "colour_profile": paper_colour_profile,
        "target_class": None,
        "orange_decoy_is_rfid": False,
        "print_row_count": row_count,
        "handwriting_stroke_count": handwriting_count,
        "tape_count": tape_count,
    }
    if linked_index is not None:
        tags[linked_index]["paper_occlusion"] = {
            "mode": mode,
            "paper_index": 0,
            "visible_tag_tip_fraction_target": visible_fraction,
        }
    return [record]


def _spawn_lighting(cfg: dict[str, Any], materials: dict[str, unreal.Material], machine: dict[str, Any], sample: dict[str, Any], profile_name: str) -> dict[str, Any]:
    profile = cfg["lighting_profiles"][profile_name]
    sample_target = tuple(map(float, sample["location_cm"]))
    door_angle = math.radians(float(machine["door"]["angle_deg"]))
    door_open_factor = max(0.12, min(1.0, math.sin(door_angle)))
    temperature = float(profile["temperature_k"])
    total_led_lumens = float(profile["led_lumens"])
    weights = cfg["machine"]["led_lumen_weights"]
    segment_lumens: dict[str, float] = {}
    for segment_name in ("back", "left", "right"):
        segment = machine["led_segments"][segment_name]
        lumens = total_led_lumens * float(weights[segment_name])
        segment_lumens[segment_name] = round(lumens, 3)
        _spawn_light(
            unreal.RectLight,
            f"LED {segment_name} diffuser area light",
            tuple(map(float, segment["location_cm"])),
            sample_target,
            lumens,
            temperature,
            width=float(segment["source_width_cm"]),
            height=max(
                3.2,
                3.5 * float(machine["led_diffuser_height_cm"]),
            ),
            attenuation=145.0,
            cast_shadows=False,
        )
    # Lumen's multi-bounce response is intentionally not trusted as the sole
    # front-face exposure source in off-screen SceneCapture.  This broad,
    # low-energy card represents diffuse return from the open door/workshop;
    # its energy is explicit in the profile and remains far below the U-LED.
    _spawn_light(
        unreal.RectLight,
        "Chamber diffuse return",
        (0.0, 22.0, 48.0),
        sample_target,
        float(profile["camera_fill_lumens"]),
        temperature,
        width=72.0,
        height=64.0,
        attenuation=190.0,
        cast_shadows=False,
    )
    _spawn_light(
        unreal.RectLight,
        "Lower chamber bounce",
        (0.0, 18.0, 14.0),
        (sample_target[0], sample_target[1], machine["upper_platen_bottom_z_cm"]),
        0.35 * float(profile["camera_fill_lumens"]),
        temperature,
        width=56.0,
        height=30.0,
        attenuation=155.0,
        cast_shadows=False,
    )
    # The real U-diffuser keeps the concrete/upper-platen contact readable,
    # even though the platen hides most of the strip from either camera.
    _spawn_light(
        unreal.RectLight,
        "Upper platen contact spill",
        (0.0, 16.0, machine["upper_platen_bottom_z_cm"] - 4.5),
        (sample_target[0], sample_target[1], machine["upper_platen_bottom_z_cm"]),
        float(profile["contact_spill_lumens"]),
        temperature,
        width=44.0,
        height=5.0,
        attenuation=105.0,
        cast_shadows=False,
    )
    _spawn_light(
        unreal.RectLight,
        "Open door fill",
        (-18.0, -58.0, 48.0),
        sample_target,
        float(profile["door_fill_lumens"]) * door_open_factor,
        5700.0,
        width=65.0,
        height=85.0,
        attenuation=240.0,
        cast_shadows=False,
    )
    _spawn_light(
        unreal.RectLight,
        "Front door LED return",
        (0.0, 18.0, 50.0),
        (0.0, -30.0, 43.0),
        260.0 + 0.10 * total_led_lumens,
        temperature,
        width=44.0,
        height=34.0,
        attenuation=125.0,
        cast_shadows=False,
    )
    # Camera 02 sees the real workshop through the open front door.  This
    # low-energy source lights only the proxy cabinets/wall enough to retain
    # that depth cue; it is deliberately weaker than the measured-domain LED
    # and does not replace the three physical diffuser lights.
    _spawn_light(
        unreal.RectLight,
        "Workshop background fill",
        (0.0, -105.0, 68.0),
        (0.0, -89.0, 30.0),
        (520.0 + 0.70 * float(profile["door_fill_lumens"]))
        * door_open_factor,
        4800.0,
        width=48.0,
        height=36.0,
        attenuation=240.0,
        cast_shadows=False,
    )
    return {
        "profile": profile_name,
        **profile,
        "led_segment_lumens": segment_lumens,
        "door_open_factor": door_open_factor,
    }


def _camera_name(seed: int, forced: str | None) -> str:
    if forced in {"camera_door", "camera_angled"}:
        return forced
    return "camera_door" if seed % 2 == 0 else "camera_angled"


def _spawn_camera(
    cfg: dict[str, Any],
    camera_name: str,
    sample: dict[str, Any],
    seed: int,
):
    camera_cfg = cfg["cameras"][camera_name]
    camera_post = cfg["camera_post"]
    location = list(map(float, camera_cfg["location_cm"]))
    target = list(map(float, camera_cfg["target_cm"]))
    # Shape-bounded visual fit from real concrete bbox medians.
    if sample["shape"] == "cube":
        # The shared 104-degree overscan + radial camera model preserves the
        # cylinder cells but makes the cube slightly too small/low if the
        # pre-warp perspective offsets are retained.  These two bounded
        # scales restore the observed cam-10/cam-11 bbox medians.
        distance_scale = 0.95
        if camera_name == "camera_angled":
            target[2] += 0.4
        else:
            # Pass-10/11 batches placed the cam-11 cube centre at x=0.575
            # versus the time-diverse real median x=0.511. Aim 20 mm farther
            # toward the door side; the post-warp object should move left
            # without changing its physical sample position or dimensions.
            target[0] += 2.0
        location = [
            target[index] + (location[index] - target[index]) * distance_scale
            for index in range(3)
        ]
    else:
        target[2] += 0.8
        distance_scale = 0.91 if camera_name == "camera_door" else 0.94
        location = [
            target[index] + (location[index] - target[index]) * distance_scale
            for index in range(3)
        ]
    randomization = cfg.get("camera_randomization", {})
    location_jitter = list(
        map(float, randomization.get("location_jitter_cm", [0.0, 0.0, 0.0]))
    )
    target_jitter = list(
        map(float, randomization.get("target_jitter_cm", [0.0, 0.0, 0.0]))
    )
    roll_range = list(
        map(float, randomization.get("roll_jitter_deg", [0.0, 0.0]))
    )
    fov_range = list(
        map(float, randomization.get("fov_jitter_deg", [0.0, 0.0]))
    )
    if (
        len(location_jitter) != 3
        or len(target_jitter) != 3
        or len(roll_range) != 2
        or len(fov_range) != 2
        or any(not 0.0 <= value <= 0.8 for value in location_jitter)
        or any(not 0.0 <= value <= 1.0 for value in target_jitter)
        or not -1.5 <= roll_range[0] <= roll_range[1] <= 1.5
        or not -2.0 <= fov_range[0] <= fov_range[1] <= 2.0
    ):
        raise ValueError("camera_randomization is outside the bounded contract")
    camera_rng = random.Random(f"{seed}:{camera_name}:camera-jitter-v1")
    location_delta = [
        camera_rng.uniform(-bound, bound) for bound in location_jitter
    ]
    target_delta = [
        camera_rng.uniform(-bound, bound) for bound in target_jitter
    ]
    location = [
        location[index] + location_delta[index] for index in range(3)
    ]
    target = [target[index] + target_delta[index] for index in range(3)]
    roll_delta = camera_rng.uniform(*roll_range)
    fov_delta = camera_rng.uniform(*fov_range)
    actual_fov = float(camera_cfg["horizontal_fov_deg"]) + fov_delta
    look_at_rotation = unreal.MathLibrary.find_look_at_rotation(
        _vector(location), _vector(target)
    )
    rotation = _rotator(
        pitch=float(look_at_rotation.pitch),
        yaw=float(look_at_rotation.yaw),
        roll=float(look_at_rotation.roll) + roll_delta,
    )
    camera = _actor_subsystem().spawn_actor_from_class(unreal.CameraActor, _vector(location), rotation)
    camera.set_actor_label(camera_name)
    camera.tags = [MANAGED_TAG, unreal.Name("EBIS_ROLE=camera"), unreal.Name(f"EBIS_CAMERA={camera_name}")]
    camera.camera_component.set_editor_property("field_of_view", actual_fov)
    _safe_set(camera.camera_component, "constrain_aspect_ratio", True)
    _safe_set(camera.camera_component, "aspect_ratio", 16.0 / 9.0)
    capture = _actor_subsystem().spawn_actor_from_class(unreal.SceneCapture2D, _vector(location), rotation)
    capture.set_actor_label(f"{camera_name}_capture")
    capture.tags = [MANAGED_TAG, unreal.Name("EBIS_ROLE=capture")]
    component = capture.capture_component2d
    component.set_editor_property("capture_every_frame", False)
    component.set_editor_property("capture_on_movement", False)
    component.set_editor_property("fov_angle", actual_fov)
    _safe_set(component, "always_persist_rendering_state", True)
    # UE project default exposure is deliberately disabled for deterministic
    # CV frames.  Manual exposure retains the surveillance-camera highlight
    # without letting the close diffuser turn the entire steel stack white.
    post = unreal.PostProcessSettings()
    post.set_editor_property("override_auto_exposure_method", True)
    post.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
    post.set_editor_property("override_auto_exposure_apply_physical_camera_exposure", True)
    post.set_editor_property("auto_exposure_apply_physical_camera_exposure", False)
    post.set_editor_property("override_auto_exposure_bias", True)
    post.set_editor_property("auto_exposure_bias", float(camera_post["manual_exposure_bias"]))
    post.set_editor_property("override_bloom_intensity", True)
    post.set_editor_property("bloom_intensity", float(camera_post["bloom_intensity"]))
    _safe_set(post, "override_ambient_occlusion_intensity", True)
    _safe_set(post, "ambient_occlusion_intensity", float(camera_post["ambient_occlusion_intensity"]))
    _safe_set(post, "override_ambient_occlusion_radius", True)
    _safe_set(post, "ambient_occlusion_radius", float(camera_post["ambient_occlusion_radius_cm"]))
    _safe_set(post, "override_vignette_intensity", True)
    _safe_set(post, "vignette_intensity", float(camera_post["vignette_intensity"]))
    component.set_editor_property("post_process_settings", post)
    component.set_editor_property("post_process_blend_weight", 1.0)
    realization = {
        "base_location_cm": list(map(float, camera_cfg["location_cm"])),
        "base_target_cm": list(map(float, camera_cfg["target_cm"])),
        "resolved_location_cm": location,
        "resolved_target_cm": target,
        "location_jitter_cm": location_delta,
        "target_jitter_cm": target_delta,
        "roll_jitter_deg": roll_delta,
        "base_horizontal_fov_deg": float(camera_cfg["horizontal_fov_deg"]),
        "horizontal_fov_deg": actual_fov,
        "fov_jitter_deg": fov_delta,
        "randomization_profile": "bounded_camera_jitter_v1",
    }
    return camera, capture, realization


def _set_render_quality(world: unreal.World) -> None:
    commands = [
        "r.ScreenPercentage 100",
        "r.AntiAliasingMethod 4",
        "r.TemporalAA.Upsampling 1",
        "r.Lumen.HardwareRayTracing 1",
        "r.Lumen.Reflections.HardwareRayTracing 1",
        "r.Lumen.ScreenProbeGather.RadianceCache.ProbeResolution 32",
        "r.Shadow.Virtual.Enable 1",
        "r.MotionBlurQuality 0",
        "r.DepthOfFieldQuality 0",
        "r.LensFlareQuality 0",
        "r.BloomQuality 4",
        "r.ViewDistanceScale 1.0",
    ]
    for command in commands:
        unreal.SystemLibrary.execute_console_command(world, command)


def build_scene(
    config_path: str,
    seed: int,
    camera_name: str = "",
    sample_shape: str = "",
    save_level: bool = True,
) -> dict[str, Any]:
    started = time.time()
    cfg = _json_load(config_path)
    rng = random.Random(int(seed))
    _ensure_level()
    removed = _clear_managed_actors()
    materials = ensure_materials(cfg)
    shape = _sample_shape(int(seed), sample_shape or None)
    height = (
        float(cfg["sample"]["cube_size_cm"][2])
        if shape == "cube"
        else float(cfg["sample"]["cylinder_height_cm"])
    )
    machine = _spawn_machine(cfg, materials, rng, height, int(seed))
    sample = _spawn_sample(cfg, materials, rng, machine, shape)
    states = list(cfg["rfid_tag"]["states"])
    # Deliberate deterministic coverage: 0..6 tags, with real dataset median near 5.
    tag_count = 0 if int(seed) % 17 == 0 else 1 + (int(seed) % int(cfg["rfid_tag"]["instance_count_max"]))
    tags = []
    for index in range(tag_count):
        state = states[(int(seed) + index * 3) % len(states)]
        tags.append(
            _spawn_rfid_instance(
                cfg, materials, sample, machine, rng, index, state, int(seed)
            )
        )
    paper_labels = _spawn_paper_labels(cfg, materials, sample, tags, rng)
    profile_names = list(cfg["lighting_profiles"].keys())
    lighting = _spawn_lighting(cfg, materials, machine, sample, profile_names[int(seed) % len(profile_names)])
    selected_camera = _camera_name(int(seed), camera_name or None)
    camera_actor, capture_actor, camera_realization = _spawn_camera(
        cfg, selected_camera, sample, int(seed)
    )
    world = _world()
    _set_render_quality(world)
    if save_level:
        level_subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if not level_subsystem.save_current_level():
            raise RuntimeError("Failed to save EBIS level")
    actors = _actor_subsystem().get_all_level_actors()
    scenario = {
        "schema_version": 1,
        "generator": "ebis_scene.py",
        "physical_revision": cfg.get("physical_revision", "unspecified"),
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "config_path": os.path.abspath(config_path),
        "config_sha256": _sha256(config_path),
        "seed": int(seed),
        "camera": selected_camera,
        "camera_realization": camera_realization,
        "sample": sample,
        "sample_material_profile": cfg["sample"].get(
            "material_profile", "procedural_cast_concrete_v2"
        ),
        "rfid_instances": tags,
        "paper_labels": paper_labels,
        "lighting": lighting,
        "machine": machine,
        "managed_actor_count": sum(actor.actor_has_tag(MANAGED_TAG) for actor in actors),
        "removed_previous_managed_actor_count": removed,
        "build_seconds": round(time.time() - started, 3),
    }
    STATE.clear()
    STATE.update(
        {
            "config": cfg,
            "config_path": os.path.abspath(config_path),
            "materials": materials,
            "camera_actor": camera_actor,
            "capture_actor": capture_actor,
            "scenario": scenario,
        }
    )
    unreal.log(f"EBIS_SCENE_BUILT seed={seed} camera={selected_camera} shape={shape} actors={scenario['managed_actor_count']}")
    return scenario


def _actor_instance_key(actor: unreal.Actor) -> str | None:
    for tag in actor.tags:
        value = str(tag)
        if value.startswith("EBIS_INSTANCE="):
            return value.split("=", 1)[1]
    return None


def _mesh_records():
    records = []
    for actor in _actor_subsystem().get_all_level_actors():
        if not actor.actor_has_tag(MANAGED_TAG):
            continue
        component = getattr(actor, "static_mesh_component", None)
        if not component:
            continue
        material_count = component.get_num_materials()
        records.append(
            {
                "actor": actor,
                "component": component,
                "instance_key": _actor_instance_key(actor),
                "materials": [component.get_material(index) for index in range(material_count)],
                "visible": component.is_visible(),
            }
        )
    return records


def _restore_mesh_records(records) -> None:
    for record in records:
        component = record["component"]
        component.set_visibility(bool(record["visible"]), True)
        for index, material in enumerate(record["materials"]):
            component.set_material(index, material)


def _export_capture(
    capture: unreal.SceneCapture2D,
    width: int,
    height: int,
    source,
    output_path: Path,
    fmt,
    warmup_frames: int = 0,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    world = _world()
    render_target = unreal.RenderingLibrary.create_render_target2d(
        world,
        int(width),
        int(height),
        fmt,
        unreal.LinearColor(0.0, 0.0, 0.0, 1.0),
        False,
        False,
    )
    component = capture.capture_component2d
    component.set_editor_property("texture_target", render_target)
    component.set_editor_property("capture_source", source)
    # Lumen and TSR need deterministic temporal history after a procedural
    # scene rebuild.  Warm-up is RGB-only; masks and depth stay single-frame.
    for _ in range(max(0, int(warmup_frames))):
        component.capture_scene()
        unreal.RenderingLibrary.read_render_target_pixel(world, render_target, 0, 0)
    component.capture_scene()
    # SceneCapture work is queued on the render thread.  A one-pixel readback
    # is an intentional GPU fence: without it rapid per-instance material/
    # visibility changes can export the previous target, duplicating masks.
    unreal.RenderingLibrary.read_render_target_pixel(world, render_target, 0, 0)
    unreal.RenderingLibrary.export_render_target(world, render_target, str(output_path.parent), output_path.name)
    unreal.RenderingLibrary.release_render_target2d(render_target)
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"SceneCapture export failed: {output_path}")


def render_current_scene(output_root: str, stem: str, width: int, height: int, include_depth: bool = True) -> dict[str, Any]:
    if not STATE:
        raise RuntimeError("No EBIS scene is active; call build_scene first")
    root = Path(output_root).resolve()
    capture = STATE["capture_actor"]
    materials = STATE["materials"]
    scenario = STATE["scenario"]
    records = _mesh_records()
    capture_component = capture.capture_component2d
    original_post = capture_component.get_editor_property("post_process_settings")
    original_post_weight = capture_component.get_editor_property("post_process_blend_weight")
    outputs: dict[str, Any] = {"rgb": "", "depth": "", "instances": {}}
    try:
        rgb_path = root / "raw" / "images" / f"{stem}.png"
        _export_capture(
            capture,
            width,
            height,
            unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,
            rgb_path,
            unreal.TextureRenderTargetFormat.RTF_RGBA8_SRGB,
            warmup_frames=int(STATE["config"]["camera_post"].get("rgb_warmup_frames", 0)),
        )
        outputs["rgb"] = str(rgb_path)

        # Mask capture is unlit and uses neutral exposure; RGB's manual exposure
        # and bloom would otherwise erode a thin visible strip or grow its bbox.
        mask_post = unreal.PostProcessSettings()
        mask_post.set_editor_property("override_auto_exposure_method", True)
        mask_post.set_editor_property("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL)
        mask_post.set_editor_property("override_auto_exposure_apply_physical_camera_exposure", True)
        mask_post.set_editor_property("auto_exposure_apply_physical_camera_exposure", False)
        mask_post.set_editor_property("override_auto_exposure_bias", True)
        mask_post.set_editor_property("auto_exposure_bias", 0.0)
        mask_post.set_editor_property("override_bloom_intensity", True)
        mask_post.set_editor_property("bloom_intensity", 0.0)
        capture_component.set_editor_property("post_process_settings", mask_post)
        capture_component.set_editor_property("post_process_blend_weight", 1.0)

        instance_keys = [scenario["sample"]["instance_key"]] + [item["instance_key"] for item in scenario["rfid_instances"]]
        for instance_key in instance_keys:
            # Visible pass: all occluders remain present and black; only this physical instance is white.
            for record in records:
                component = record["component"]
                component.set_visibility(True, True)
                replacement = materials["mask_white"] if record["instance_key"] == instance_key else materials["mask_black"]
                for material_index in range(max(1, component.get_num_materials())):
                    component.set_material(material_index, replacement)
            visible_path = root / "raw" / "masks_visible" / f"{stem}__{instance_key}.png"
            _export_capture(
                capture,
                width,
                height,
                unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,
                visible_path,
                unreal.TextureRenderTargetFormat.RTF_RGBA8,
            )

            # Amodal in-frame pass: only target parts remain; frame clipping is retained.
            for record in records:
                is_target = record["instance_key"] == instance_key
                record["component"].set_visibility(is_target, True)
                if is_target:
                    for material_index in range(max(1, record["component"].get_num_materials())):
                        record["component"].set_material(material_index, materials["mask_white"])
            amodal_path = root / "raw" / "masks_amodal" / f"{stem}__{instance_key}.png"
            _export_capture(
                capture,
                width,
                height,
                unreal.SceneCaptureSource.SCS_FINAL_COLOR_LDR,
                amodal_path,
                unreal.TextureRenderTargetFormat.RTF_RGBA8,
            )
            outputs["instances"][instance_key] = {"visible_mask": str(visible_path), "amodal_mask": str(amodal_path)}
            _restore_mesh_records(records)
        # Scene-depth capture is deliberately last. UE may defer capture-source
        # proxy updates until the next editor tick; no RGB/mask pass is allowed
        # after depth in this synchronous batch function.
        if include_depth:
            depth_path = root / "raw" / "depth" / f"{stem}.exr"
            _export_capture(
                capture,
                width,
                height,
                unreal.SceneCaptureSource.SCS_SCENE_DEPTH,
                depth_path,
                unreal.TextureRenderTargetFormat.RTF_RGBA32F,
            )
            outputs["depth"] = str(depth_path)
    finally:
        _restore_mesh_records(records)
        capture_component.set_editor_property("post_process_settings", original_post)
        capture_component.set_editor_property("post_process_blend_weight", original_post_weight)

    manifest = {
        **scenario,
        "stem": stem,
        "resolution_px": [int(width), int(height)],
        "render_outputs": outputs,
        "rendered_at_unix": time.time(),
    }
    metadata_path = root / "raw" / "metadata" / f"{stem}.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
    outputs["metadata"] = str(metadata_path)
    unreal.log(f"EBIS_SCENE_RENDERED stem={stem} instances={len(outputs['instances'])} resolution={width}x{height}")
    return outputs


def generate_dataset(
    config_path: str,
    output_root: str,
    start_seed: int,
    count: int,
    width: int,
    height: int,
    include_depth: bool = True,
) -> dict[str, Any]:
    started = time.time()
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    frames = []
    for offset in range(int(count)):
        seed = int(start_seed) + offset
        scenario = build_scene(config_path, seed, save_level=(offset == int(count) - 1))
        stem = f"ebis_{scenario['camera']}_{seed:06d}"
        outputs = render_current_scene(str(root), stem, int(width), int(height), include_depth)
        frames.append({"seed": seed, "stem": stem, "camera": scenario["camera"], "shape": scenario["sample"]["shape"], "outputs": outputs})
    run_manifest = {
        "schema_version": 1,
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "config_path": os.path.abspath(config_path),
        "config_sha256": _sha256(config_path),
        "start_seed": int(start_seed),
        "count": int(count),
        "resolution_px": [int(width), int(height)],
        "include_depth": bool(include_depth),
        "elapsed_seconds": round(time.time() - started, 3),
        "frames": frames,
    }
    manifest_path = root / "raw" / "run_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(run_manifest, handle, indent=2, sort_keys=True)
    unreal.log(f"EBIS_DATASET_COMPLETE frames={count} output={root}")
    return run_manifest


def status() -> dict[str, Any]:
    actors = _actor_subsystem().get_all_level_actors()
    managed = [actor for actor in actors if actor.actor_has_tag(MANAGED_TAG)]
    instance_counts: dict[str, int] = {}
    for actor in managed:
        key = _actor_instance_key(actor)
        if key:
            instance_counts[key] = instance_counts.get(key, 0) + 1
    return {
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "world": _world().get_path_name(),
        "managed_actor_count": len(managed),
        "instance_part_counts": instance_counts,
        "active_scenario": STATE.get("scenario"),
    }
