#!/usr/bin/env python3
"""Make a saved EBIS .blend write to a portable relative preview directory.

Blender loads the target .blend before this script runs.  The script updates
the active render path and all compositor File Output nodes, saves in place,
then refreshes the corresponding metadata blend hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True, type=Path)
    parser.add_argument(
        "--relative-root",
        help="Blender // path; default is //../manual_preview/<blend-stem>",
    )
    return parser.parse_args(argv)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    args = parse_args()
    blend_path = Path(bpy.data.filepath).resolve()
    if not blend_path.is_file():
        raise ValueError("Blender must load an existing .blend before this script runs")
    metadata_path = args.metadata.resolve()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    expected_blend = metadata.get("outputs", {}).get("blend")
    if not expected_blend or Path(expected_blend).name != blend_path.name:
        raise ValueError(f"Metadata does not reference loaded blend: {expected_blend!r}")

    relative_root = args.relative_root or f"//../manual_preview/{blend_path.stem}"
    if not relative_root.startswith("//"):
        raise ValueError("relative-root must use Blender's // relative-path prefix")
    relative_root = relative_root.rstrip("/")
    scene = bpy.context.scene
    scene.render.filepath = f"{relative_root}/rgb.png"
    file_output_nodes = []
    if scene.use_nodes and scene.node_tree:
        for node in scene.node_tree.nodes:
            if node.bl_idname == "CompositorNodeOutputFile":
                node.base_path = f"{relative_root}/passes"
                file_output_nodes.append(node.name)
    scene["ebis_portable_output_root"] = relative_root
    scene["ebis_file_output_nodes_rebased"] = len(file_output_nodes)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), check_existing=False)

    metadata.setdefault("render", {})["saved_blend_output_root"] = relative_root
    metadata["render"]["saved_blend_file_output_nodes"] = file_output_nodes
    metadata.setdefault("sha256", {})["blend"] = sha256(blend_path)
    temporary = metadata_path.with_suffix(metadata_path.suffix + ".tmp")
    temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(metadata_path)
    print(
        "EBIS_BLEND_REBASE_OK",
        blend_path,
        relative_root,
        f"file_output_nodes={len(file_output_nodes)}",
        f"sha256={metadata['sha256']['blend']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
