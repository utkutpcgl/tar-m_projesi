#!/usr/bin/env python3
"""Remove obsolete EBIS run/QC artifacts with an explicit allowlist.

The default is a dry run. ``--apply`` uses the desktop trash so the cleanup is
recoverable. Candidates are limited to immediate run directories/generated
logs under each engine's ``output``, generated QC PNGs, and superseded
image-bearing MCP evidence directories. Source, configs, real references,
docs, stable ``output/current_samples`` and current MCP evidence are never
inferred as targets.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Iterable


ENGINE_ROOTS = ("ebis-blender", "unreal-ebis")
CURRENT_MCP_EVIDENCE = {
    "ebis-blender": {
        "20260730-cast-pores-v8",
        "current_cast_pores_v8_scene",
    },
    "unreal-ebis": {
        "20260730-neutral-cast-r59-artifacts",
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--keep-blender", action="append", default=[])
    parser.add_argument("--keep-unreal", action="append", default=[])
    parser.add_argument(
        "--keep-qc",
        action="append",
        default=[],
        help="Repository-relative generated QC PNG to retain; repeatable",
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--delete-permanently",
        action="store_true",
        help="Use irreversible deletion instead of the default recoverable trash",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("reports/cleanup/CLEANUP_MANIFEST_2026-07-30.json"),
    )
    return parser.parse_args()


def tree_stats(path: Path) -> tuple[int, int]:
    if path.is_file():
        return path.stat().st_size, 1
    size = 0
    count = 0
    for item in path.rglob("*"):
        if item.is_file() and not item.is_symlink():
            try:
                size += item.stat().st_size
                count += 1
            except FileNotFoundError:
                pass
    return size, count


def normalized_names(values: Iterable[str]) -> set[str]:
    names = set(values)
    invalid = [
        value
        for value in names
        if not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
    ]
    if invalid:
        raise ValueError(f"Run keep names must be single path components: {invalid}")
    return names


def collect_candidates(
    repo: Path,
    keeps: dict[str, set[str]],
    keep_qc: set[Path],
) -> list[Path]:
    candidates: list[Path] = []
    for engine in ENGINE_ROOTS:
        output = repo / engine / "output"
        if not output.is_dir():
            continue
        keep = {"current_samples", *keeps[engine]}
        for path in sorted(output.iterdir()):
            if path.is_dir() and path.name not in keep:
                candidates.append(path)
            elif path.is_file() and path.suffix == ".log":
                candidates.append(path)

        mcp_root = repo / engine / "evidence" / "mcp"
        if mcp_root.is_dir():
            for path in sorted(mcp_root.iterdir()):
                if (
                    path.is_dir()
                    and path.name not in CURRENT_MCP_EVIDENCE[engine]
                ):
                    candidates.append(path)

    qc_roots = (
        repo / "ebis-blender" / "reports" / "qc",
        repo / "unreal-ebis" / "reports" / "qc" / "assets",
    )
    for qc_root in qc_roots:
        if not qc_root.is_dir():
            continue
        for path in sorted(qc_root.glob("*.png")):
            if path.resolve() not in keep_qc:
                candidates.append(path)
    return candidates


def remove(path: Path, permanent: bool) -> str:
    if permanent:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        return "permanent"
    subprocess.run(["gio", "trash", str(path)], check=True)
    return "gio-trash"


def main() -> int:
    args = parse_args()
    repo = args.repo.resolve()
    keeps = {
        "ebis-blender": normalized_names(args.keep_blender),
        "unreal-ebis": normalized_names(args.keep_unreal),
    }
    keep_qc = {(repo / value).resolve() for value in map(Path, args.keep_qc)}
    for path in keep_qc:
        if not path.is_relative_to(repo):
            raise ValueError(f"QC keep path escapes repository: {path}")

    candidates = collect_candidates(repo, keeps, keep_qc)
    records = []
    for path in candidates:
        resolved = path.resolve()
        if not resolved.is_relative_to(repo):
            raise RuntimeError(f"Refusing target outside repository: {resolved}")
        size, files = tree_stats(path)
        records.append(
            {
                "path": str(path.relative_to(repo)),
                "bytes": size,
                "file_count": files,
                "exists_before": path.exists(),
            }
        )

    manifest_path = (
        args.manifest
        if args.manifest.is_absolute()
        else repo / args.manifest
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo": str(repo),
        "mode": (
            "dry-run"
            if not args.apply
            else "permanent"
            if args.delete_permanently
            else "gio-trash"
        ),
        "recoverable": bool(args.apply and not args.delete_permanently),
        "allowlist": {
            engine: sorted({"current_samples", *names})
            for engine, names in keeps.items()
        },
        "kept_mcp_evidence_directories": {
            engine: sorted(CURRENT_MCP_EVIDENCE[engine])
            for engine in ENGINE_ROOTS
        },
        "kept_qc_png": sorted(
            str(path.relative_to(repo)) for path in keep_qc if path.exists()
        ),
        "candidate_count": len(records),
        "candidate_bytes": sum(record["bytes"] for record in records),
        "candidate_files": sum(record["file_count"] for record in records),
        "targets": records,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if args.apply:
        for record in records:
            target = repo / record["path"]
            record["removal_method"] = remove(
                target,
                permanent=args.delete_permanently,
            )
            record["exists_after"] = target.exists()
        manifest["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["all_targets_absent"] = all(
            not record["exists_after"] for record in records
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    gib = manifest["candidate_bytes"] / (1024**3)
    print(
        "CLEANUP_"
        + ("APPLY" if args.apply else "DRY_RUN")
        + f"_OK targets={len(records)} files={manifest['candidate_files']} "
        + f"gib={gib:.3f} manifest={manifest_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
