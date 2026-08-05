#!/usr/bin/env python3
"""Small standard-library client for Epic UE 5.8 Streamable HTTP MCP."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class Client:
    def __init__(self, url: str):
        self.url = url
        self.session_id: str | None = None
        self.protocol_version = "2025-11-25"
        self.request_id = 0
        self.transcript: list[dict[str, Any]] = []

    @staticmethod
    def _parse(body: bytes, content_type: str) -> Any:
        text = body.decode("utf-8", errors="replace")
        if "text/event-stream" not in content_type.lower():
            return json.loads(text) if text.strip() else None
        events = []
        for block in text.replace("\r\n", "\n").split("\n\n"):
            data_lines = [line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")]
            if data_lines:
                events.append(json.loads("\n".join(data_lines)))
        return events[-1] if len(events) == 1 else events

    def request(self, method: str, params: dict[str, Any] | None = None, notification: bool = False):
        self.request_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notification:
            payload["id"] = self.request_id
        if params is not None:
            payload["params"] = params
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
            headers["Mcp-Protocol-Version"] = self.protocol_version
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        started = time.time()
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                body = response.read()
                response_headers = dict(response.headers.items())
                parsed = self._parse(body, response_headers.get("Content-Type", ""))
                if not self.session_id:
                    self.session_id = response_headers.get("Mcp-Session-Id") or response_headers.get("mcp-session-id")
                record = {
                    "method": method,
                    "request": payload,
                    "http_status": response.status,
                    "response_headers": response_headers,
                    "response": parsed,
                    "elapsed_seconds": round(time.time() - started, 4),
                }
                self.transcript.append(record)
                return parsed
        except urllib.error.HTTPError as exc:
            body = exc.read()
            record = {
                "method": method,
                "request": payload,
                "http_status": exc.code,
                "response_headers": dict(exc.headers.items()),
                "response_body": body.decode("utf-8", errors="replace"),
                "elapsed_seconds": round(time.time() - started, 4),
            }
            self.transcript.append(record)
            raise RuntimeError(json.dumps(record, sort_keys=True)) from exc

    def initialize(self):
        result = self.request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": "ebis-verifier", "version": "1.0"},
            },
        )
        if not self.session_id:
            raise RuntimeError("UE MCP initialize did not return Mcp-Session-Id")
        self.request("notifications/initialized", {}, notification=True)
        return result

    def call(self, name: str, arguments: dict[str, Any]):
        return self.request("tools/call", {"name": name, "arguments": arguments})


def content_text(response: Any) -> str:
    if isinstance(response, dict):
        result = response.get("result", response)
        if isinstance(result, dict):
            blocks = result.get("content", [])
            return "\n".join(block.get("text", "") for block in blocks if block.get("type") == "text")
    return ""


def tool_return_value(response: Any) -> Any:
    """Decode ToolsetRegistry's JSON envelope and optional JSON return string."""
    if not isinstance(response, dict) or "error" in response:
        raise RuntimeError(f"MCP tool returned an error: {response!r}")
    text = content_text(response)
    if not text:
        raise RuntimeError(f"MCP tool returned no text content: {response!r}")
    envelope = json.loads(text)
    value = envelope.get("returnValue", envelope)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--seed", type=int, default=58203)
    parser.add_argument("--camera", default="camera_angled")
    parser.add_argument("--shape", default="cylinder")
    parser.add_argument("--render", action="store_true")
    args = parser.parse_args()

    client = Client(args.url)
    summary: dict[str, Any] = {"url": args.url, "nonce": f"ebis-mcp-{time.time_ns()}"}
    summary["initialize"] = client.initialize()
    summary["tools_list"] = client.request("tools/list", {})
    catalog_response = client.call("list_toolsets", {})
    catalog = content_text(catalog_response)
    summary["toolset_catalog"] = catalog
    candidates = [line.strip().split(":", 1)[0].strip(" -*`") for line in catalog.splitlines() if "EBISTools" in line]
    if not candidates:
        # Catalog text format can change; known stable Python-qualified name is tried explicitly.
        candidates = ["ebis_toolset.EBISTools"]
    toolset_name = candidates[0]
    summary["toolset_name"] = toolset_name
    summary["describe"] = client.call("describe_toolset", {"toolset_name": toolset_name})
    summary["build"] = client.call(
        "call_tool",
        {
            "toolset_name": toolset_name,
            "tool_name": "build_scene",
            "arguments": {
                "config_path": str(Path(args.config).resolve()),
                "seed": args.seed,
                "camera_name": args.camera,
                "sample_shape": args.shape,
            },
        },
    )
    summary["build_parsed"] = tool_return_value(summary["build"])
    summary["validate"] = client.call(
        "call_tool",
        {"toolset_name": toolset_name, "tool_name": "validate_scene", "arguments": {}},
    )
    summary["validate_parsed"] = tool_return_value(summary["validate"])
    if not summary["validate_parsed"].get("ok"):
        raise RuntimeError(f"EBIS MCP scene validation failed: {summary['validate_parsed']}")
    summary["status"] = client.call(
        "call_tool",
        {"toolset_name": toolset_name, "tool_name": "get_status", "arguments": {}},
    )
    summary["status_parsed"] = tool_return_value(summary["status"])
    if args.render:
        summary["render"] = client.call(
            "call_tool",
            {
                "toolset_name": toolset_name,
                "tool_name": "render_current",
                "arguments": {
                    "output_root": str(Path(args.output).resolve()),
                    "stem": f"ebis_mcp_{args.camera}_{args.seed:06d}",
                    "width": 1920,
                    "height": 1080,
                    "include_depth": True,
                },
            },
        )
        summary["render_parsed"] = tool_return_value(summary["render"])
        required_paths = [
            summary["render_parsed"].get("rgb"),
            summary["render_parsed"].get("depth"),
            summary["render_parsed"].get("metadata"),
        ]
        missing = [path for path in required_paths if not path or not Path(path).is_file()]
        if missing:
            raise RuntimeError(f"MCP render outputs are missing: {missing}")
    evidence = {
        "schema_version": 1,
        "verified_at_unix": time.time(),
        "summary": summary,
        "transcript": client.transcript,
    }
    evidence_path = Path(args.evidence)
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "ok": True,
        "session_id": client.session_id,
        "toolset_name": toolset_name,
        "evidence": str(evidence_path),
        "calls": len(client.transcript),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
