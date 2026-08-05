"""Bounded project tools registered in Epic's official ToolsetRegistry."""

import json

import toolset_registry
import unreal
from toolset_registry.registration import Registration

import ebis_scene


@unreal.uclass()
class EBISTools(unreal.ToolsetDefinition):
    """Build, inspect and render only the EBIS synthetic-data scene."""

    @toolset_registry.tool_call
    @staticmethod
    def get_status() -> str:
        """Return engine, world, actor and physical-instance status as JSON."""
        return json.dumps(ebis_scene.status(), sort_keys=True)

    @toolset_registry.tool_call
    @staticmethod
    def build_scene(
        config_path: str,
        seed: int,
        camera_name: str = "",
        sample_shape: str = "",
    ) -> str:
        """Build and save one deterministic EBIS scene.

        Args:
            config_path: Absolute path to the versioned EBIS JSON config.
            seed: Scenario seed.
            camera_name: Empty for seed mapping, or camera_door/camera_angled.
            sample_shape: Empty for seed mapping, or cube/cylinder.
        """
        result = ebis_scene.build_scene(config_path, seed, camera_name, sample_shape, True)
        return json.dumps(result, sort_keys=True)

    @toolset_registry.tool_call
    @staticmethod
    def render_current(
        output_root: str,
        stem: str,
        width: int = 1920,
        height: int = 1080,
        include_depth: bool = True,
    ) -> str:
        """Render RGB, depth, visible and amodal instance masks for the active scene."""
        result = ebis_scene.render_current_scene(
            output_root, stem, width, height, include_depth
        )
        return json.dumps(result, sort_keys=True)

    @toolset_registry.tool_call
    @staticmethod
    def validate_scene() -> str:
        """Check the active scene contract without changing it."""
        status = ebis_scene.status()
        instances = status["instance_part_counts"]
        errors = []
        if status["managed_actor_count"] < 35:
            errors.append("managed_actor_count_below_35")
        if "concrete_00" not in instances:
            errors.append("missing_concrete_instance")
        if not any(key.startswith("rfid_") for key in instances):
            errors.append("missing_rfid_instance")
        result = {"ok": not errors, "errors": errors, "status": status}
        return json.dumps(result, sort_keys=True)


_REGISTRATION = Registration([EBISTools])
_REGISTERED = False


def register() -> bool:
    global _REGISTERED
    if _REGISTERED:
        return True
    _REGISTERED = bool(_REGISTRATION.register())
    return _REGISTERED
