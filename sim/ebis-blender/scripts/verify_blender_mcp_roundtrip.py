#!/usr/bin/env python3
"""Exercise BlenderMCP's real JSON/TCP path and write a reproducible evidence record.

Run this script on the same host as BlenderMCP.  The add-on must already be
listening on a loopback address; the script never starts or exposes the server.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import socket
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9876)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--render-width", type=int, default=1920)
    parser.add_argument("--render-height", type=int, default=1080)
    parser.add_argument("--render-samples", type=int, default=128)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    return parser.parse_args()


def request(host: str, port: int, payload: dict[str, Any], timeout: float) -> Any:
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    with socket.create_connection((host, port), timeout=timeout) as client:
        client.settimeout(timeout)
        client.sendall(encoded)
        buffer = bytearray()
        while True:
            chunk = client.recv(65536)
            if not chunk:
                raise RuntimeError("BlenderMCP closed the connection before a JSON response")
            buffer.extend(chunk)
            try:
                return json.loads(buffer.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue


def successful_result(response: Any, command: str) -> Any:
    if not isinstance(response, dict) or response.get("status") != "success":
        raise RuntimeError(f"BlenderMCP {command} failed: {response!r}")
    return response.get("result")


def png_facts(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"Not a valid PNG header: {path}")
    width, height = struct.unpack(">II", raw[16:24])
    return {
        "path": str(path),
        "bytes": len(raw),
        "width": width,
        "height": height,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def main() -> int:
    args = parse_args()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = args.run_id or f"{timestamp}-{secrets.token_hex(4)}"
    nonce = secrets.token_hex(16)
    run_dir = (args.evidence_root / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    viewport_path = run_dir / "viewport.png"
    render_path = run_dir / "render.png"

    scene_before = successful_result(
        request(args.host, args.port, {"type": "get_scene_info"}, args.timeout_seconds),
        "get_scene_info",
    )

    probe_code = (
        "import bpy\n"
        f"print('MCP_EXEC_OK:{nonce}')\n"
        "print('BLENDER_VERSION=' + bpy.app.version_string)\n"
        "print('SCENE=' + bpy.context.scene.name)\n"
        "print('ACTIVE_CAMERA=' + (bpy.context.scene.camera.name if bpy.context.scene.camera else 'NONE'))\n"
    )
    execute_probe = successful_result(
        request(
            args.host,
            args.port,
            {"type": "execute_code", "params": {"code": probe_code}},
            args.timeout_seconds,
        ),
        "execute_code probe",
    )
    if nonce not in str(execute_probe):
        raise RuntimeError("Nonce was not returned by BlenderMCP execute_code")

    viewport_response = successful_result(
        request(
            args.host,
            args.port,
            {
                "type": "get_viewport_screenshot",
                "params": {"max_size": 1200, "filepath": str(viewport_path), "format": "png"},
            },
            args.timeout_seconds,
        ),
        "get_viewport_screenshot",
    )

    render_code = (
        "import bpy\n"
        "scene = bpy.context.scene\n"
        "render_backend = 'CPU'\n"
        "render_devices = []\n"
        "try:\n"
        "    prefs = bpy.context.preferences.addons['cycles'].preferences\n"
        "    for candidate in ('OPTIX', 'CUDA'):\n"
        "        try:\n"
        "            prefs.compute_device_type = candidate\n"
        "            prefs.get_devices()\n"
        "            selected = [d for d in prefs.devices if d.type == candidate]\n"
        "            if selected:\n"
        "                for d in prefs.devices: d.use = d.type == candidate\n"
        "                scene.cycles.device = 'GPU'\n"
        "                render_backend = candidate\n"
        "                render_devices = [d.name for d in selected]\n"
        "                break\n"
        "        except Exception:\n"
        "            pass\n"
        "except Exception:\n"
        "    pass\n"
        f"scene.render.resolution_x = {args.render_width}\n"
        f"scene.render.resolution_y = {args.render_height}\n"
        "scene.render.resolution_percentage = 100\n"
        f"scene.cycles.samples = {args.render_samples}\n"
        f"scene.render.filepath = {str(render_path)!r}\n"
        "scene.render.image_settings.file_format = 'PNG'\n"
        "bpy.ops.render.render(write_still=True)\n"
        f"print('MCP_RENDER_OK:{nonce}')\n"
        "print('RENDER_BACKEND=' + render_backend)\n"
        "print('RENDER_DEVICES=' + repr(render_devices))\n"
        "print('RENDER_PATH=' + scene.render.filepath)\n"
    )
    execute_render = successful_result(
        request(
            args.host,
            args.port,
            {"type": "execute_code", "params": {"code": render_code}},
            args.timeout_seconds,
        ),
        "execute_code render",
    )
    if nonce not in str(execute_render):
        raise RuntimeError("Nonce was not returned by BlenderMCP render command")

    scene_after = successful_result(
        request(args.host, args.port, {"type": "get_scene_info"}, args.timeout_seconds),
        "get_scene_info after",
    )
    if scene_before.get("object_count") != scene_after.get("object_count"):
        raise RuntimeError("Scene object count changed during the read/render round-trip")

    evidence = {
        "schema_version": 1,
        "verified_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": run_id,
        "nonce": nonce,
        "endpoint": f"{args.host}:{args.port}",
        "scene_before": scene_before,
        "execute_probe": execute_probe,
        "viewport_response": viewport_response,
        "execute_render": execute_render,
        "scene_after": scene_after,
        "viewport_png": png_facts(viewport_path),
        "render_png": png_facts(render_path),
    }
    output_path = run_dir / "roundtrip.json"
    output_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "roundtrip": str(output_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
