"""Entry point used by UnrealEditor-Cmd -ExecutePythonScript."""

import json
import os
import traceback

import unreal

import ebis_scene


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


try:
    result = ebis_scene.generate_dataset(
        config_path=env("EBIS_CONFIG"),
        output_root=env("EBIS_OUTPUT"),
        start_seed=int(env("EBIS_START_SEED", "58200")),
        count=int(env("EBIS_COUNT", "1")),
        width=int(env("EBIS_WIDTH", "1280")),
        height=int(env("EBIS_HEIGHT", "720")),
        include_depth=env("EBIS_DEPTH", "1").lower() not in {"0", "false", "no"},
    )
    unreal.log("EBIS_BATCH_RESULT=" + json.dumps({
        "count": result["count"],
        "elapsed_seconds": result["elapsed_seconds"],
        "output": env("EBIS_OUTPUT"),
    }, sort_keys=True))
except Exception as exc:
    unreal.log_error(f"EBIS_BATCH_FAILED: {exc!r}\n{traceback.format_exc()}")
    raise
