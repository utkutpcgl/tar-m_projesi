#!/usr/bin/env python3
"""Promote one validated EBIS run into a stable four-cell review folder.

The immutable run folders remain provenance.  Reviewers only need to watch
``<engine>/output/current_samples``; this script replaces that directory
atomically after validating the source run and selecting one cube/cylinder
frame for each physical camera.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

from PIL import Image, ImageDraw, ImageFont


CAMERA_ROLES = {
    "camera_angled": "cam10",
    "camera_door": "cam11",
}
PARTITION_RANK = {
    "standard": 0,
    "hard_occlusion": 1,
    "exclude": 2,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def partition_for(source: Path, stem: str, metadata: dict[str, Any]) -> str:
    annotated = metadata.get("annotation_partition")
    if isinstance(annotated, str) and annotated in PARTITION_RANK:
        return annotated
    for partition in PARTITION_RANK:
        if (source / "partitions" / partition / "images" / f"{stem}.png").is_file():
            return partition
    raise FileNotFoundError(f"No partition image for {stem} under {source}")


def select_cells(source: Path) -> dict[str, dict[str, Any]]:
    candidates: dict[str, list[dict[str, Any]]] = {
        f"{camera}_{shape}": []
        for camera in CAMERA_ROLES
        for shape in ("cube", "cylinder")
    }
    for metadata_path in sorted((source / "metadata").glob("*.json")):
        metadata = load_json(metadata_path)
        camera_value = metadata.get("camera")
        if isinstance(camera_value, dict):
            camera = camera_value.get("name")
        else:
            camera = camera_value
        sample = metadata.get("sample")
        shape = sample.get("shape") if isinstance(sample, dict) else None
        if camera not in CAMERA_ROLES or shape not in {"cube", "cylinder"}:
            continue
        partition = partition_for(source, metadata_path.stem, metadata)
        candidates[f"{camera}_{shape}"].append(
            {
                "stem": metadata_path.stem,
                "camera": camera,
                "shape": shape,
                "partition": partition,
                "metadata_path": metadata_path,
            }
        )

    selected: dict[str, dict[str, Any]] = {}
    for key, values in candidates.items():
        if not values:
            raise RuntimeError(f"Validated run has no candidate for required cell {key}")
        values.sort(key=lambda item: (PARTITION_RANK[item["partition"]], item["stem"]))
        selected[key] = values[0]
    return selected


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def source_image(source: Path, stem: str, partition: str) -> Path:
    path = source / "partitions" / partition / "images" / f"{stem}.png"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def source_label(source: Path, stem: str, partition: str) -> Path:
    path = source / "partitions" / partition / "labels" / f"{stem}.txt"
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def copy_masks(source: Path, stem: str, target: Path) -> list[str]:
    copied: list[str] = []
    blender_concrete = source / "masks" / "concrete_sample" / f"{stem}.png"
    if blender_concrete.is_file():
        destination = target / "masks_visible" / f"{stem}__concrete_00.png"
        copy_file(blender_concrete, destination)
        copied.append(destination.relative_to(target).as_posix())
        for mask in sorted((source / "masks" / "rfid_instances").glob(f"{stem}__*.png")):
            destination = target / "masks_visible" / mask.name
            copy_file(mask, destination)
            copied.append(destination.relative_to(target).as_posix())
        return copied

    for kind in ("masks_visible", "masks_amodal"):
        for mask in sorted((source / "raw" / kind).glob(f"{stem}__*.png")):
            destination = target / kind / mask.name
            copy_file(mask, destination)
            copied.append(destination.relative_to(target).as_posix())
    return copied


def make_contact_sheet(target: Path, records: list[dict[str, Any]]) -> None:
    opened = [Image.open(target / record["image"]).convert("RGB") for record in records]
    try:
        resampling = getattr(Image, "Resampling", Image)
        cell_width = 640
        cell_height = 360
        label_height = 44
        sheet = Image.new("RGB", (cell_width * 2, (cell_height + label_height) * 2), (14, 17, 21))
        draw = ImageDraw.Draw(sheet)
        font = ImageFont.load_default()
        for index, (record, image) in enumerate(zip(records, opened)):
            column = index % 2
            row = index // 2
            x = column * cell_width
            y = row * (cell_height + label_height)
            image.thumbnail((cell_width, cell_height), resampling.LANCZOS)
            paste_x = x + (cell_width - image.width) // 2
            paste_y = y + (cell_height - image.height) // 2
            sheet.paste(image, (paste_x, paste_y))
            label = (
                f"{record['role']}  source={record['source_stem']}  "
                f"partition={record['partition']}"
            )
            draw.text((x + 8, y + cell_height + 12), label, fill=(230, 235, 240), font=font)
        sheet.save(target / "contact_sheet.png", optimize=True)
    finally:
        for image in opened:
            image.close()


def validate_source(source: Path) -> dict[str, Any]:
    validation_path = source / "validation.json"
    if not validation_path.is_file():
        raise FileNotFoundError(validation_path)
    validation = load_json(validation_path)
    passed = validation.get("status") == "PASS" or validation.get("ok") is True
    if not passed or validation.get("errors"):
        raise RuntimeError(f"Source run is not a clean PASS: {validation_path}")
    return validation


def promote(engine_root: Path, source: Path) -> Path:
    engine_root = engine_root.resolve()
    output_root = (engine_root / "output").resolve()
    source = source.resolve()
    if source.parent != output_root or source.name == "current_samples":
        raise ValueError("Source must be one immutable immediate child of <engine>/output")
    validation = validate_source(source)
    selected = select_cells(source)

    target = output_root / "current_samples"
    staging = output_root / ".current_samples.next"
    previous = output_root / ".current_samples.previous"
    for transient in (staging, previous):
        if transient.exists():
            shutil.rmtree(transient)
    staging.mkdir(parents=True)

    records: list[dict[str, Any]] = []
    order = (
        ("camera_angled", "cube"),
        ("camera_angled", "cylinder"),
        ("camera_door", "cube"),
        ("camera_door", "cylinder"),
    )
    for camera, shape in order:
        selected_cell = selected[f"{camera}_{shape}"]
        stem = selected_cell["stem"]
        partition = selected_cell["partition"]
        role = f"{CAMERA_ROLES[camera]}_{shape}"
        image_destination = staging / "images" / f"{role}.png"
        label_destination = staging / "labels" / f"{role}.txt"
        metadata_destination = staging / "metadata" / f"{role}.json"
        copy_file(source_image(source, stem, partition), image_destination)
        copy_file(source_label(source, stem, partition), label_destination)
        copy_file(selected_cell["metadata_path"], metadata_destination)
        masks = copy_masks(source, stem, staging)
        records.append(
            {
                "role": role,
                "camera": camera,
                "shape": shape,
                "source_stem": stem,
                "partition": partition,
                "image": image_destination.relative_to(staging).as_posix(),
                "label": label_destination.relative_to(staging).as_posix(),
                "metadata": metadata_destination.relative_to(staging).as_posix(),
                "masks": masks,
            }
        )

    make_contact_sheet(staging, records)
    manifest = {
        "schema_version": 1,
        "convention": "EBIS_CURRENT_SAMPLES_V1",
        # Keep the manifest byte-identical when the validated release is
        # mirrored from the workstation to the RTX 3090 workspace.
        "engine_root": engine_root.name,
        "source_run": source.name,
        "source_validation_sha256": sha256(source / "validation.json"),
        "source_validation": {
            "status": validation.get("status"),
            "ok": validation.get("ok"),
            "errors": validation.get("errors", []),
        },
        "selection_policy": "standard > hard_occlusion > exclude, then lexical stem",
        "records": records,
    }
    (staging / "CURRENT.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (staging / "README.md").write_text(
        "# EBIS current samples\n\n"
        "`contact_sheet.png` ve `images/` her zaman son doğrulanmış dört "
        "kamera×şekil örneğini gösterir. Kaynak run ve partition seçimi "
        "`CURRENT.json` içindedir. Bu klasör elle düzenlenmez; "
        "`scripts/promote_ebis_current_samples.py` ile atomik yenilenir.\n",
        encoding="utf-8",
    )

    if target.exists():
        os.replace(target, previous)
    try:
        os.replace(staging, target)
    except Exception:
        if previous.exists() and not target.exists():
            os.replace(previous, target)
        raise
    if previous.exists():
        shutil.rmtree(previous)

    tracked = [
        path
        for path in target.rglob("*")
        if path.is_file() and path.name != "CURRENT.json"
    ]
    manifest["files_sha256"] = {
        path.relative_to(target).as_posix(): sha256(path)
        for path in sorted(tracked)
    }
    (target / "CURRENT.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-root", required=True, type=Path)
    parser.add_argument("--source-run", required=True, type=Path)
    args = parser.parse_args()
    target = promote(args.engine_root, args.source_run)
    print(f"PROMOTE_OK target={target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
