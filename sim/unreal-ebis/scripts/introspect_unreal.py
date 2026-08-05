"""Emit a small, machine-readable UE Python API inventory, then exit."""

import json
import os
import unreal


names = [
    "SceneCapture2D",
    "SceneCaptureComponent2D",
    "TextureRenderTarget2D",
    "RenderingLibrary",
    "AutomationLibrary",
    "EditorActorSubsystem",
    "EditorAssetLibrary",
    "MaterialEditingLibrary",
    "CameraActor",
    "RectLight",
    "PostProcessVolume",
    "PostProcessSettings",
    "MaterialExpressionNoise",
    "MaterialExpressionLinearInterpolate",
    "MaterialExpressionWorldPosition",
    "MaterialExpressionMultiply",
    "StaticMeshComponent",
]

inventory = {
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "project_dir": unreal.Paths.project_dir(),
    "classes": {},
}
for name in names:
    value = getattr(unreal, name, None)
    inventory["classes"][name] = {
        "exists": value is not None,
        "doc": getattr(value, "__doc__", None),
        "members": sorted(item for item in dir(value) if not item.startswith("__")) if value else [],
    }

for owner_name, member_names in {
    "RenderingLibrary": ["create_render_target2d", "export_render_target", "read_render_target"],
    "SceneCapture2D": ["capture_component2d", "get_capture_component2d"],
    "SceneCaptureComponent2D": ["capture_scene", "texture_target", "capture_source", "fov_angle"],
    "AutomationLibrary": ["take_high_res_screenshot", "finish_loading_before_screenshot"],
    "MaterialEditingLibrary": [
        "create_material_expression",
        "connect_material_property",
        "connect_material_expressions",
        "recompile_material",
    ],
}.items():
    owner = getattr(unreal, owner_name, None)
    if not owner:
        continue
    inventory.setdefault("member_docs", {})[owner_name] = {}
    for member_name in member_names:
        member = getattr(owner, member_name, None)
        inventory["member_docs"][owner_name][member_name] = getattr(member, "__doc__", None)

for enum_name in [
    "SceneCaptureSource",
    "TextureRenderTargetFormat",
    "MaterialProperty",
    "MaterialDomain",
    "BlendMode",
    "AutoExposureMethod",
    "LightUnits",
]:
    enum_value = getattr(unreal, enum_name, None)
    inventory.setdefault("enums", {})[enum_name] = {
        "exists": enum_value is not None,
        "members": [item for item in dir(enum_value) if item.isupper()] if enum_value else [],
        "doc": getattr(enum_value, "__doc__", None),
    }

out_path = os.environ.get("EBIS_INTROSPECTION_OUT")
if not out_path:
    out_path = os.path.join(unreal.Paths.project_saved_dir(), "ebis_unreal_api.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(inventory, handle, indent=2, sort_keys=True)
unreal.log(f"EBIS_INTROSPECTION: {out_path}")
