"""Download, normalize, and audit public real-field datasets."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import numpy as np
import yaml
from PIL import Image, ImageDraw

from .constants import BACKGROUND, CROP, IGNORE, WEED
from .data import image_hw, load_rgb_image, to_display_pil
from .manifest import SampleRecord, read_manifest, write_manifest


def load_registry(path: str | Path) -> dict[str, object]:
    with Path(path).open("r", encoding="utf-8") as handle:
        registry = yaml.safe_load(handle)
    if not isinstance(registry, dict) or "data_root" not in registry:
        raise ValueError("Dataset registry must define data_root")
    return registry


def file_checksum(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_free_space(path: Path, required_bytes: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    available = shutil.disk_usage(path).free
    if available < required_bytes:
        raise OSError(
            f"Insufficient free space at {path}: need {required_bytes:,}, "
            f"available {available:,} bytes"
        )


def download_with_resume(
    url: str,
    destination: Path,
    expected_size: int | None = None,
    checksum: tuple[str, str] | None = None,
) -> Path:
    """Resume a download and only accept the final file after integrity checks."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        size_ok = expected_size is None or destination.stat().st_size == expected_size
        hash_ok = (
            checksum is None
            or file_checksum(destination, checksum[0]).lower()
            == checksum[1].lower()
        )
        if size_ok and hash_ok:
            return destination

    partial = destination.with_suffix(destination.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 agri-seg-dataset-audit/1.0",
            "Accept": "*/*",
        },
    )
    if offset:
        request.add_header("Range", f"bytes={offset}-")
    with urllib.request.urlopen(request) as response:
        status = getattr(response, "status", 200)
        if offset and status != 206:
            offset = 0
            partial.unlink(missing_ok=True)
        mode = "ab" if offset else "wb"
        with partial.open(mode) as output:
            shutil.copyfileobj(response, output, length=4 * 1024 * 1024)

    if expected_size is not None and partial.stat().st_size != expected_size:
        raise IOError(
            f"Unexpected size for {partial}: {partial.stat().st_size:,}, "
            f"expected {expected_size:,}"
        )
    if checksum is not None:
        actual = file_checksum(partial, checksum[0])
        if actual.lower() != checksum[1].lower():
            raise IOError(
                f"{checksum[0]} mismatch for {partial}: {actual} != {checksum[1]}"
            )
    partial.replace(destination)
    return destination


def safe_extract_zip(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise ValueError(f"Unsafe zip member: {member.filename}")
        bundle.extractall(destination)
    return destination


def safe_extract_tar(archive: Path, destination: Path) -> Path:
    """Extract a regular-file tar archive without links or path traversal."""
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        for member in members:
            target = (destination / member.name).resolve()
            if root not in target.parents and target != root:
                raise ValueError(f"Unsafe tar member: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"Tar links are not accepted: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"Unsupported tar member type: {member.name}")
        bundle.extractall(destination, members=members)
    return destination


def _archive_entry_flag(entry: object, name: str) -> bool:
    value = getattr(entry, name, False)
    return bool(value() if callable(value) else value)


def _safe_archive_target(destination: Path, member_name: str) -> Path:
    """Resolve an archive member after normalizing Windows separators."""
    normalized = member_name.replace("\\", "/")
    root = destination.resolve()
    target = (destination / normalized).resolve()
    if root not in target.parents and target != root:
        raise ValueError(f"Unsafe archive member: {member_name}")
    return target


def safe_extract_rar(
    archive: Path,
    destination: Path,
    max_members: int = 1_000_000,
    max_uncompressed_bytes: int = 100 * 1024**3,
) -> Path:
    """Extract regular RAR members through libarchive with fail-closed checks."""
    try:
        import libarchive
    except ImportError as error:  # pragma: no cover - dependency is declared.
        raise RuntimeError(
            "RAR extraction requires the declared libarchive-c dependency"
        ) from error

    destination.mkdir(parents=True, exist_ok=True)
    members = 0
    uncompressed_bytes = 0
    with libarchive.file_reader(str(archive)) as bundle:
        for entry in bundle:
            members += 1
            if members > max_members:
                raise ValueError(f"RAR member limit exceeded: {archive}")
            _safe_archive_target(destination, str(entry.pathname))
            if _archive_entry_flag(entry, "issym") or _archive_entry_flag(
                entry, "islnk"
            ):
                raise ValueError(f"RAR links are not accepted: {entry.pathname}")
            is_file = _archive_entry_flag(entry, "isfile")
            is_dir = _archive_entry_flag(entry, "isdir")
            if not (is_file or is_dir) or (is_file and is_dir):
                raise ValueError(
                    f"Unsupported RAR member type: {entry.pathname}"
                )
            if is_file:
                size = int(entry.size)
                if size < 0:
                    raise ValueError(f"Negative RAR member size: {entry.pathname}")
                uncompressed_bytes += size
                if uncompressed_bytes > max_uncompressed_bytes:
                    raise ValueError(f"RAR extraction size limit exceeded: {archive}")

    require_free_space(destination, uncompressed_bytes + 1024**3)
    with libarchive.file_reader(str(archive)) as bundle:
        for entry in bundle:
            target = _safe_archive_target(destination, str(entry.pathname))
            if _archive_entry_flag(entry, "isdir"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".part")
            written = 0
            with temporary.open("wb") as output:
                for block in entry.get_blocks():
                    output.write(block)
                    written += len(block)
            if written != int(entry.size):
                temporary.unlink(missing_ok=True)
                raise IOError(
                    f"RAR member size mismatch for {entry.pathname}: "
                    f"{written} != {entry.size}"
                )
            temporary.replace(target)
    return destination


def acquire_dataset(
    name: str, registry_path: str | Path = "configs/datasets.yaml", extract: bool = True
) -> Path:
    registry = load_registry(registry_path)
    datasets = registry["datasets"]
    if name not in datasets:
        raise KeyError(f"Unknown dataset: {name}")
    spec = datasets[name]
    data_root = Path(registry["data_root"]).expanduser()
    expected_size = int(spec.get("size_bytes", 0))
    # Keep at least 2x archive size plus 20 GiB for extraction/checkpoints.
    require_free_space(data_root, expected_size * 2 + 20 * 1024**3)
    source = str(spec["source"])
    extracted = data_root / str(spec["extracted"])

    if source.endswith(".git"):
        if not extracted.exists():
            subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--no-tags",
                    source,
                    str(extracted),
                ],
                check=True,
            )
        revision = spec.get("revision")
        if revision:
            expected_revision = str(revision)
            actual_revision = subprocess.run(
                ["git", "-C", str(extracted), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if actual_revision != expected_revision:
                raise RuntimeError(
                    f"Pinned revision mismatch for {name}: "
                    f"{actual_revision} != {expected_revision}"
                )
        return extracted

    archive = data_root / str(spec["archive"])
    checksum_spec = spec.get("checksum")
    checksum = None
    if checksum_spec:
        checksum = (
            str(checksum_spec["algorithm"]),
            str(checksum_spec["value"]),
        )
    download_with_resume(source, archive, expected_size, checksum)
    if extract:
        if zipfile.is_zipfile(archive):
            safe_extract_zip(archive, extracted)
        elif tarfile.is_tarfile(archive):
            safe_extract_tar(archive, extracted)
        elif archive.suffix.lower() == ".rar":
            safe_extract_rar(archive, extracted)
        else:
            raise ValueError(f"Unsupported dataset archive format: {archive}")
        return extracted
    return archive


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _save_common_mask(array: np.ndarray, destination: Path) -> None:
    allowed = {BACKGROUND, CROP, WEED, IGNORE}
    values = set(np.unique(array).tolist())
    if not values <= allowed:
        raise ValueError(f"Unexpected normalized labels {values} for {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.png")
    Image.fromarray(array.astype(np.uint8)).save(temporary, format="PNG")
    temporary.replace(destination)


def _find_dataset_layout(root: Path, marker: str) -> Path:
    if (root / marker).is_dir():
        return root
    matches: list[Path] = []
    for path in root.rglob(marker):
        if not path.is_dir():
            continue
        candidate = path
        for _ in Path(marker).parts:
            candidate = candidate.parent
        matches.append(candidate)
    matches = sorted(matches)
    if len(matches) != 1:
        raise FileNotFoundError(
            f"Could not uniquely locate {marker!r} under {root}; found {matches}"
        )
    return matches[0]


def convert_phenobench(data_root: str | Path) -> Path:
    root = Path(data_root).expanduser().resolve()
    source = _find_dataset_layout(
        root / "raw/phenobench/PhenoBench-v110", "train/images"
    )
    normalized_root = root / "processed/phenobench/common_masks"
    records: list[SampleRecord] = []
    for split in ("train", "val"):
        image_dir = source / split / "images"
        mask_dir = source / split / "semantics"
        if not image_dir.is_dir() or not mask_dir.is_dir():
            raise FileNotFoundError(f"Incomplete PhenoBench {split} layout at {source}")
        for mask_path in sorted(mask_dir.glob("*.png")):
            image_path = image_dir / mask_path.name
            if not image_path.is_file():
                raise FileNotFoundError(f"Missing image for {mask_path}")
            raw = np.asarray(Image.open(mask_path), dtype=np.uint16)
            common = np.full(raw.shape, IGNORE, dtype=np.uint8)
            common[raw == 0] = BACKGROUND
            common[raw == 1] = CROP
            common[raw == 2] = WEED
            # IDs 3/4 are partial plants at annotation/visibility boundaries.
            # They are not trustworthy full crop/weed supervision.
            common[(raw == 3) | (raw == 4)] = IGNORE
            common_path = normalized_root / split / mask_path.name
            _save_common_mask(common, common_path)
            date_token = mask_path.stem[:5]
            capture_date = (
                f"2020-{date_token}" if len(date_token) == 5 else "unknown"
            )
            records.append(
                SampleRecord(
                    sample_id=f"phenobench:{split}:{mask_path.stem}",
                    image_path=_relative(image_path, root),
                    mask_path=_relative(common_path, root),
                    split=split,
                    dataset_id="phenobench",
                    # The official split is spatial; retain that boundary explicitly.
                    field_id=f"cka_2020_{split}_region",
                    session_id=f"flight_{date_token}",
                    capture_date=capture_date,
                    platform="uav_dji_m600",
                    sensor="phaseone_ixm100_rgb",
                    target_crop_id=0,
                    crop_species="Beta vulgaris",
                    weed_species_optional="six regional species; see dataset card",
                    growth_stage=date_token,
                    annotation_exhaustive=True,
                    license_status="CC-BY-NC-SA-4.0",
                    commercial_allowed=False,
                )
            )
    destination = root / "processed/manifests/phenobench.csv"
    write_manifest(records, destination)
    return destination


def convert_cwfid(data_root: str | Path) -> Path:
    root = Path(data_root).expanduser().resolve()
    source = root / "raw/cwfid/repository"
    normalized_root = root / "processed/cwfid/common_masks"
    records: list[SampleRecord] = []
    for image_path in sorted((source / "images").glob("*_image.png")):
        frame = int(image_path.stem.split("_")[0])
        vegetation_path = source / "masks" / f"{frame:03d}_mask.png"
        annotation_path = (
            source / "annotations" / f"{frame:03d}_annotation.png"
        )
        vegetation = np.asarray(Image.open(vegetation_path).convert("L"))
        annotation = np.asarray(Image.open(annotation_path).convert("RGB"))
        common = np.zeros(vegetation.shape, dtype=np.uint8)
        red_weed = (
            (annotation[..., 0] > 200)
            & (annotation[..., 1] < 50)
            & (annotation[..., 2] < 50)
        )
        green_crop = (
            (annotation[..., 1] > 200)
            & (annotation[..., 0] < 50)
            & (annotation[..., 2] < 50)
        )
        common[green_crop] = CROP
        common[red_weed] = WEED
        untyped_vegetation = (
            (vegetation < 128) & ~green_crop & ~red_weed
        )
        common[untyped_vegetation] = IGNORE
        common_path = normalized_root / f"{frame:03d}.png"
        _save_common_mask(common, common_path)
        records.append(
            SampleRecord(
                sample_id=f"cwfid:{frame:03d}",
                image_path=_relative(image_path, root),
                mask_path=_relative(common_path, root),
                # One short capture sequence: never create a random/frame split.
                # CWFID is architecture-development data; Carrot/EWIS stay final.
                split="external_calibration",
                dataset_id="cwfid",
                field_id="carrot_field_2014",
                session_id="capture_session_unknown",
                capture_date="unknown",
                platform="ground_camera",
                sensor="jais_ad_130ge_rgb",
                target_crop_id=1,
                crop_species="Daucus carota",
                weed_species_optional="mixed",
                growth_stage="early",
                annotation_exhaustive=False,
                license_status="non-commercial-research-only",
                commercial_allowed=False,
            )
        )
    destination = root / "processed/manifests/cwfid.csv"
    write_manifest(records, destination)
    return destination


def _acre_session_split(session: str) -> str:
    """Fixed acquisition-folder split; the final two sessions are hard sunlight."""
    normalized = session.lower().replace("_", "-")
    groups = {
        "train": {
            "06-08-16-09",
            "06-08-17-24",
            "06-09-10-18",
            "06-08-16-44",
            "06-08-17-38",
            "06-09-10-26",
        },
        "val": {"06-09-11-06", "06-09-10-58"},
        "test": {"06-10-10-50", "06-10-10-39"},
    }
    matches = [
        split
        for split, tokens in groups.items()
        if any(token in normalized for token in tokens)
    ]
    if len(matches) != 1:
        raise ValueError(f"Unknown or ambiguous ACRE acquisition session: {session}")
    return matches[0]


def _xml_text(element: ET.Element, *paths: str) -> str:
    for path in paths:
        value = element.findtext(path)
        if value and value.strip():
            return value.strip()
    return ""


def _acre_polygon(
    clipping: ET.Element, width: int, height: int
) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for point in clipping.findall(".//points/point"):
        try:
            x = int(round(float(point.attrib["x"])))
            y = int(round(float(point.attrib["y"])))
        except (KeyError, TypeError, ValueError):
            continue
        points.append(
            (
                min(max(x, 0), width - 1),
                min(max(y, 0), height - 1),
            )
        )
    return points


def _read_acre_xml(xml_path: Path) -> ET.Element:
    payload = xml_path.read_bytes()
    try:
        return ET.fromstring(payload)
    except (ET.ParseError, ValueError):
        return ET.fromstring(payload.decode("iso-8859-5").encode("utf-8"))


def _rasterize_acre_xml(
    xml_path: Path, image_size: tuple[int, int]
) -> tuple[np.ndarray, set[str]]:
    """Rasterize ACRE XML; unsafe/unknown/conflicting plants become ignore."""
    width, height = image_size
    root = _read_acre_xml(xml_path)
    xml_width = _xml_text(root, ".//width")
    xml_height = _xml_text(root, ".//height")
    if xml_width and xml_height:
        declared = (int(float(xml_width)), int(float(xml_height)))
        if declared != image_size:
            raise ValueError(
                f"ACRE XML/image size mismatch for {xml_path}: "
                f"{declared} != {image_size}"
            )

    crop_layer = Image.new("1", image_size, 0)
    weed_layer = Image.new("1", image_size, 0)
    ignore_layer = Image.new("1", image_size, 0)
    crop_draw = ImageDraw.Draw(crop_layer)
    weed_draw = ImageDraw.Draw(weed_layer)
    ignore_draw = ImageDraw.Draw(ignore_layer)
    weed_species: set[str] = set()

    clippings = root.findall(".//clipping")
    if not clippings:
        declared_count = _xml_text(root, ".//clippings/number")
        if declared_count not in {"", "0"}:
            raise ValueError(
                f"Missing ACRE clipping polygons in {xml_path} "
                f"despite declared count {declared_count}"
            )
        return np.full((height, width), BACKGROUND, dtype=np.uint8), set()
    for clipping in clippings:
        points = _acre_polygon(clipping, width, height)
        if len(points) < 3:
            if points:
                ignore_draw.line(points, fill=1, width=3)
            continue
        class_name = _xml_text(clipping, "class", ".//class").lower()
        trusted_text = _xml_text(
            clipping, "trusted/isTrusted", ".//trusted/isTrusted"
        ).lower()
        is_trusted = trusted_text not in {"false", "0", "no"}
        plant_name = _xml_text(
            clipping, "plant_name", ".//plant_name", "name", ".//name"
        )

        if not is_trusted or class_name in {"unknown", "unknow", ""}:
            ignore_draw.polygon(points, fill=1)
        elif class_name == "crop":
            crop_draw.polygon(points, fill=1)
        elif class_name == "weed":
            weed_draw.polygon(points, fill=1)
            if plant_name:
                weed_species.add(plant_name)
        else:
            ignore_draw.polygon(points, fill=1)

    crop = np.asarray(crop_layer, dtype=bool)
    weed = np.asarray(weed_layer, dtype=bool)
    ignore = np.asarray(ignore_layer, dtype=bool) | (crop & weed)
    common = np.full((height, width), BACKGROUND, dtype=np.uint8)
    common[crop] = CROP
    common[weed] = WEED
    common[ignore] = IGNORE
    return common, weed_species


def convert_acre(data_root: str | Path) -> Path:
    """Convert ACRE XML polygons and create a session-disjoint train/val split."""
    root = Path(data_root).expanduser().resolve()
    archive_root = root / "raw/acre/The_ACRE_Crop-Weed_Dataset"
    data_candidates = [
        path
        for path in archive_root.rglob("data")
        if path.is_dir() and any(path.rglob("*.xml"))
    ]
    if archive_root.name == "data" and any(archive_root.rglob("*.xml")):
        data_candidates.append(archive_root)
    data_candidates = sorted(set(data_candidates))
    if len(data_candidates) != 1:
        raise FileNotFoundError(
            f"Could not uniquely locate ACRE data directory under "
            f"{archive_root}; found {data_candidates}"
        )
    source = data_candidates[0]

    pairs: list[tuple[Path, Path, str, str]] = []
    crop_aliases = {
        "bean": ("Phaseolus vulgaris", 2),
        "maize": ("Zea mays", 3),
    }
    for xml_path in sorted(source.rglob("*.xml")):
        image_path = xml_path.with_suffix(".jpg")
        if not image_path.is_file():
            image_path = xml_path.with_suffix(".JPG")
        if not image_path.is_file():
            continue
        relative = xml_path.relative_to(source)
        parts_lower = [part.lower() for part in relative.parts]
        crop_key = next(
            (name for name in crop_aliases if name in parts_lower), ""
        )
        if not crop_key:
            continue
        session_path = relative.parent.as_posix()
        pairs.append((image_path, xml_path, crop_key, session_path))
    if not pairs:
        raise FileNotFoundError(f"No paired ACRE JPG/XML files under {source}")

    normalized_root = root / "processed/acre/common_masks"
    records: list[SampleRecord] = []
    for image_path, xml_path, crop_key, session_path in pairs:
        xml_root = _read_acre_xml(xml_path)
        usable = _xml_text(
            xml_root, ".//usable/isUsable", ".//isUsable"
        ).lower()
        if usable in {"false", "0", "no"}:
            continue
        with Image.open(image_path) as image:
            image_size = image.size
        common, weeds = _rasterize_acre_xml(xml_path, image_size)
        relative_stem = xml_path.relative_to(source).with_suffix("")
        common_path = normalized_root / relative_stem.with_suffix(".png")
        _save_common_mask(common, common_path)
        crop_species, target_crop_id = crop_aliases[crop_key]
        sample_token = relative_stem.as_posix()
        records.append(
            SampleRecord(
                sample_id=f"acre:{sample_token}",
                image_path=_relative(image_path, root),
                mask_path=_relative(common_path, root),
                split=_acre_session_split(session_path),
                dataset_id="acre",
                field_id=f"acre_{crop_key}",
                session_id=session_path.replace("/", "__"),
                capture_date="unknown",
                platform="ground_robot",
                sensor="rgb_camera",
                target_crop_id=target_crop_id,
                crop_species=crop_species,
                weed_species_optional=";".join(sorted(weeds)) or "unknown",
                growth_stage="mixed",
                annotation_exhaustive=True,
                license_status="CC-BY-4.0",
                commercial_allowed=True,
            )
        )
    destination = root / "processed/manifests/acre.csv"
    write_manifest(records, destination)
    return destination


def convert_carrot_weed(data_root: str | Path) -> Path:
    """Convert the single-sequence Carrot-Weed set as a fully locked test."""
    root = Path(data_root).expanduser().resolve()
    source = _find_dataset_layout(
        root / "raw/carrot_weed/repository", "Images"
    )
    image_dir = source / "Images"
    mask_dir = source / "Weed_Plant_Masks"
    if not mask_dir.is_dir():
        raise FileNotFoundError(f"Missing Carrot-Weed masks at {mask_dir}")

    normalized_root = root / "processed/carrot_weed/common_masks"
    records: list[SampleRecord] = []
    for image_path in sorted(image_dir.glob("*.JPG")):
        mask_path = mask_dir / f"{image_path.stem}_mask.png"
        if not mask_path.is_file():
            raise FileNotFoundError(f"Missing mask for {image_path}")
        raw = np.asarray(Image.open(mask_path).convert("L"), dtype=np.uint8)
        values = set(np.unique(raw).tolist())
        if not values <= {0, 1, 2}:
            raise ValueError(
                f"Unexpected Carrot-Weed labels {values} in {mask_path}"
            )
        common = np.zeros(raw.shape, dtype=np.uint8)
        common[raw == 1] = WEED
        common[raw == 2] = CROP
        common_path = normalized_root / f"{image_path.stem}.png"
        _save_common_mask(common, common_path)
        records.append(
            SampleRecord(
                sample_id=f"carrot_weed:{image_path.stem}",
                image_path=_relative(image_path, root),
                mask_path=_relative(common_path, root),
                split="external_test",
                dataset_id="carrot_weed",
                field_id="carrot_field_single_sequence",
                session_id="IMG_3438_to_IMG_3476",
                capture_date="unknown",
                platform="ground_camera",
                sensor="rgb_camera",
                target_crop_id=1,
                crop_species="Daucus carota",
                weed_species_optional="mixed",
                growth_stage="early",
                annotation_exhaustive=True,
                license_status="non-commercial-research-only",
                commercial_allowed=False,
            )
        )
    if not records:
        raise FileNotFoundError(f"No Carrot-Weed JPG files under {image_dir}")
    destination = root / "processed/manifests/carrot_weed.csv"
    write_manifest(records, destination)
    return destination


def _save_uint16_rgb(array: np.ndarray, destination: Path) -> None:
    if array.dtype != np.uint16 or array.ndim != 3 or array.shape[2] != 3:
        raise ValueError(
            f"Expected uint16 HWC RGB array for {destination}, got "
            f"{array.dtype} {array.shape}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    with temporary.open("wb") as handle:
        np.save(handle, array, allow_pickle=False)
    temporary.replace(destination)


def convert_weedsgalore(data_root: str | Path) -> Path:
    """Preserve 16-bit RGB bands and normalize authoritative semantic masks."""
    root = Path(data_root).expanduser().resolve()
    source = _find_dataset_layout(
        root / "raw/weedsgalore/repository", "splits"
    )
    split_membership: dict[str, str] = {}
    for split in ("train", "val", "test"):
        split_path = source / "splits" / f"{split}.txt"
        members = [
            line.strip()
            for line in split_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        for stem in members:
            if stem in split_membership:
                raise ValueError(
                    f"WeedsGalore sample {stem} appears in multiple splits"
                )
            split_membership[stem] = split
    if not split_membership:
        raise ValueError(f"Empty WeedsGalore split lists under {source}")

    rgb_root = root / "processed/weedsgalore/rgb16"
    mask_root = root / "processed/weedsgalore/common_masks"
    records: list[SampleRecord] = []
    for stem, split in sorted(split_membership.items()):
        capture_date = stem[:10]
        session_root = source / capture_date
        band_paths = [
            session_root / "images" / f"{stem}_{band}.png"
            for band in ("R", "G", "B")
        ]
        if not all(path.is_file() for path in band_paths):
            raise FileNotFoundError(f"Missing RGB band for WeedsGalore {stem}")
        bands = [
            np.asarray(Image.open(path), dtype=np.uint16)
            for path in band_paths
        ]
        if any(band.shape != bands[0].shape for band in bands[1:]):
            raise ValueError(f"Band shape mismatch for WeedsGalore {stem}")
        rgb = np.stack(bands, axis=-1)
        rgb_path = rgb_root / f"{stem}.npy"
        _save_uint16_rgb(rgb, rgb_path)

        semantic_path = session_root / "semantics" / f"{stem}.png"
        if not semantic_path.is_file():
            raise FileNotFoundError(f"Missing semantic mask for {stem}")
        raw = np.asarray(Image.open(semantic_path).convert("L"), dtype=np.uint8)
        values = set(np.unique(raw).tolist())
        if not values <= {0, 1, 2, 3, 4, 5}:
            raise ValueError(
                f"Unexpected WeedsGalore labels {values} in {semantic_path}"
            )
        common = np.zeros(raw.shape, dtype=np.uint8)
        common[raw == 1] = CROP
        common[(raw >= 2) & (raw <= 5)] = WEED
        common_path = mask_root / f"{stem}.png"
        _save_common_mask(common, common_path)
        records.append(
            SampleRecord(
                sample_id=f"weedsgalore:{stem}",
                image_path=_relative(rgb_path, root),
                mask_path=_relative(common_path, root),
                split=split,
                dataset_id="weedsgalore",
                # The publisher split is spatially disjoint and keeps dates from
                # one location together. Treat each partition as a strict group.
                field_id=f"official_{split}_spatial_partition",
                session_id=f"official_{split}_spatial_partition",
                capture_date=capture_date,
                platform="field_multispectral_camera",
                sensor="five_band_R_G_B_NIR_RE",
                target_crop_id=3,
                crop_species="Zea mays",
                weed_species_optional=(
                    "Amaranthus;Echinochloa crus-galli;"
                    "Galinsoga parviflora;other"
                ),
                growth_stage=capture_date,
                annotation_exhaustive=True,
                license_status="CC-BY-4.0",
                commercial_allowed=True,
            )
        )
    destination = root / "processed/manifests/weedsgalore.csv"
    write_manifest(records, destination)
    return destination


_ROSE_CROPS: dict[str, tuple[str, int]] = {
    "haricot": ("Phaseolus vulgaris", 2),
    "mais": ("Zea mays", 3),
}
_ROSE_WEEDS = (
    "Lolium perenne",
    "Sinapis arvensis",
    "Chenopodium album",
    "Matricaria chamomilla",
)
_ROSE_COLORS: dict[tuple[int, int, int], int] = {
    (0, 0, 0): BACKGROUND,
    (254, 124, 18): WEED,
    (255, 255, 255): CROP,
    (216, 67, 82): WEED,
}
_ROSE_V2_BIPBIP_HARICOT_MISSING_MASKS = frozenset(
    {
        "Bipbip_haricot_im_00211",
        "Bipbip_haricot_im_00581",
        "Bipbip_haricot_im_00721",
        "Bipbip_haricot_im_00951",
        "Bipbip_haricot_im_01341",
        "Bipbip_haricot_im_02421",
        "Bipbip_haricot_im_02781",
        "Bipbip_haricot_im_02841",
        "Bipbip_haricot_im_02901",
        "Bipbip_haricot_im_03691",
        "Bipbip_haricot_im_06581",
        "Bipbip_haricot_im_06751",
        "Bipbip_haricot_im_07181",
        "Bipbip_haricot_im_07331",
        "Bipbip_haricot_im_07421",
    }
)
_ROSE_V2_BIPBIP_HARICOT_ORPHAN_MASKS = frozenset(
    {
        "Bipbip_mais_im_01931",
        "Bipbip_mais_im_02211",
        "Bipbip_mais_im_03621",
        "Bipbip_mais_im_04121",
        "Bipbip_mais_im_05521",
        "Bipbip_mais_im_06381",
        "Bipbip_mais_im_06831",
        "Bipbip_mais_im_07611",
        "Bipbip_mais_im_07681",
        "Bipbip_mais_im_09091",
        "Bipbip_mais_im_09571",
        "Bipbip_mais_im_09781",
        "Bipbip_mais_im_10441",
        "Bipbip_mais_im_10941",
        "Bipbip_mais_im_11021",
    }
)


def _rose_split(year: str, team: str) -> str:
    """Hold out an entire robot and an entire year, never individual frames."""
    if year == "2021":
        return "test"
    if team.lower() == "weedelec":
        return "val"
    return "train"


def convert_rose(data_root: str | Path) -> Path:
    """Normalize ROSE with robot/year-disjoint train, val, and test groups."""
    root = Path(data_root).expanduser().resolve()
    source = _find_dataset_layout(root / "raw/rose/repository", "2019")
    image_dirs = sorted(
        path for path in source.rglob("Images") if path.is_dir()
    )
    if not image_dirs:
        raise FileNotFoundError(f"No ROSE image directories under {source}")

    normalized_root = root / "processed/rose/common_masks"
    records: list[SampleRecord] = []
    source_images = 0
    source_masks = 0
    excluded_missing_masks: list[str] = []
    excluded_orphan_masks: list[str] = []
    group_counts: dict[str, dict[str, int]] = {}
    for image_dir in image_dirs:
        relative = image_dir.relative_to(source).parts
        if len(relative) != 4 or relative[-1] != "Images":
            raise ValueError(f"Unexpected ROSE directory layout: {image_dir}")
        year, team, crop_folder, _ = relative
        crop_key = crop_folder.lower().removesuffix("_2021")
        if crop_key not in _ROSE_CROPS:
            raise ValueError(f"Unexpected ROSE crop folder: {image_dir}")
        crop_species, target_crop_id = _ROSE_CROPS[crop_key]
        mask_dir = image_dir.parent / "Masks"
        images = {
            path.stem: path
            for path in sorted(image_dir.iterdir())
            if path.is_file()
            and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
        }
        masks = {
            path.stem: path for path in sorted(mask_dir.glob("*.png"))
        }
        if not images or not masks:
            raise ValueError(f"Empty ROSE image or mask group: {image_dir}")
        source_images += len(images)
        source_masks += len(masks)
        missing_masks = set(images) - set(masks)
        orphan_masks = set(masks) - set(images)
        if missing_masks or orphan_masks:
            known_v2_anomaly = (
                year == "2019"
                and team.lower() == "bipbip"
                and crop_key == "haricot"
                and missing_masks
                == _ROSE_V2_BIPBIP_HARICOT_MISSING_MASKS
                and orphan_masks
                == _ROSE_V2_BIPBIP_HARICOT_ORPHAN_MASKS
            )
            if not known_v2_anomaly:
                raise ValueError(
                    f"ROSE image/mask pairing mismatch in {image_dir}: "
                    f"missing_masks={sorted(missing_masks)}, "
                    f"orphan_masks={sorted(orphan_masks)}"
                )
            prefix = f"{year}/{team}/{crop_folder}"
            excluded_missing_masks.extend(
                f"{prefix}/{stem}" for stem in sorted(missing_masks)
            )
            excluded_orphan_masks.extend(
                f"{prefix}/{stem}" for stem in sorted(orphan_masks)
            )

        split = _rose_split(year, team)
        session = f"{year}_{team.lower()}_{crop_key}"
        paired_stems = sorted(set(images) & set(masks))
        if not paired_stems:
            raise ValueError(f"No paired ROSE samples in {image_dir}")
        group_counts[session] = {
            "source_images": len(images),
            "source_masks": len(masks),
            "included_samples": len(paired_stems),
            "excluded_missing_masks": len(missing_masks),
            "excluded_orphan_masks": len(orphan_masks),
        }
        for stem in paired_stems:
            image_path = images[stem]
            mask_path = masks[stem]
            raw = np.asarray(
                Image.open(mask_path).convert("RGB"), dtype=np.uint8
            )
            common = np.full(raw.shape[:2], IGNORE, dtype=np.uint8)
            known = np.zeros(raw.shape[:2], dtype=bool)
            for color, label in _ROSE_COLORS.items():
                selected = np.all(raw == color, axis=-1)
                common[selected] = label
                known |= selected
            if not np.all(known):
                unexpected = np.unique(raw[~known].reshape(-1, 3), axis=0)
                raise ValueError(
                    f"Unexpected ROSE mask colors in {mask_path}: "
                    f"{unexpected[:10].tolist()}"
                )
            common_path = (
                normalized_root
                / split
                / year
                / team.lower()
                / crop_key
                / f"{stem}.png"
            )
            _save_common_mask(common, common_path)
            records.append(
                SampleRecord(
                    sample_id=f"rose:{session}:{stem}",
                    image_path=_relative(image_path, root),
                    mask_path=_relative(common_path, root),
                    split=split,
                    dataset_id="rose",
                    field_id=f"inrae_montoldre_{year}",
                    session_id=f"rose_{session}",
                    capture_date=year,
                    platform=f"rose_robot_{team.lower()}",
                    sensor=f"{team.lower()}_rgb_camera",
                    target_crop_id=target_crop_id,
                    crop_species=crop_species,
                    weed_species_optional=";".join(_ROSE_WEEDS),
                    growth_stage="unknown",
                    annotation_exhaustive=True,
                    license_status=(
                        "CC-BY-4.0-record;"
                        "ODbL-1.0-embedded-content-review"
                    ),
                    commercial_allowed=False,
                )
            )
    destination = root / "processed/manifests/rose.csv"
    write_manifest(records, destination)
    report = {
        "dataset_id": "rose",
        "source_images": source_images,
        "source_masks": source_masks,
        "included_samples": len(records),
        "excluded_missing_masks": excluded_missing_masks,
        "excluded_orphan_masks": excluded_orphan_masks,
        "split_counts": {
            split: sum(record.split == split for record in records)
            for split in ("train", "val", "test")
        },
        "group_counts": group_counts,
        "policy": {
            "class_mapping": (
                "black=background; orange=other_vegetation/weed; "
                "white=crop; pink=weed"
            ),
            "pairing": "exact_filename_stem_intersection",
            "known_upstream_anomaly": (
                "official-v2-bipbip-haricot-mask-packaging-error"
            ),
            "unmatched": "excluded_not_inferred",
            "split": "2019_weedelec_val_2021_test_other_2019_train",
        },
    }
    report_path = root / "processed/manifests/rose_conversion.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


_WE3DS_CROPS: dict[int, tuple[str, int]] = {
    2: ("Vicia faba", 5),
    5: ("Fagopyrum esculentum", 6),
    6: ("Pisum sativum", 7),
    11: ("Zea mays", 3),
    14: ("Glycine max", 8),
    15: ("Helianthus annuus", 9),
    18: ("Beta vulgaris", 0),
}
_WE3DS_WEEDS: dict[int, str] = {
    3: "Spergula arvensis",
    4: "Amaranthus retroflexus",
    7: "Digitaria sanguinalis",
    8: "Avena fatua",
    9: "Centaurea cyanus",
    10: "Agrostemma githago",
    12: "Silybum marianum",
    13: "Bromus secalinus",
    16: "Plantago lanceolata",
    17: "Geranium pusillum",
}


def _we3ds_iso_date(value: str) -> str:
    for pattern in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized WE3DS date: {value!r}")


def _we3ds_split(capture_date: str) -> str:
    """Fixed date-disjoint split; no one-FPS capture session crosses splits."""
    validation_dates = {
        "2020-08-10",
        "2021-05-28",
        "2021-09-21",
    }
    test_dates = {
        "2020-08-06",
        "2021-06-01",
        "2021-06-29",
        "2021-09-16",
        "2021-10-13",
    }
    if capture_date in validation_dates:
        return "val"
    if capture_date in test_dates:
        return "test"
    return "train"


def _we3ds_metadata(info_path: Path) -> dict[str, dict[str, str]]:
    with info_path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = handle.readline()
        delimiter = ";" if ";" in header else ","
        handle.seek(0)
        rows = list(csv.DictReader(handle, delimiter=delimiter))
    if not rows:
        raise ValueError(f"Empty WE3DS metadata: {info_path}")
    metadata: dict[str, dict[str, str]] = {}
    for index, row in enumerate(rows):
        normalized = {
            str(key).strip().lower().replace(" ", "_").replace("-", "_"): str(
                value
            ).strip()
            for key, value in row.items()
            if key is not None
        }
        filename = next(
            (
                normalized[key]
                for key in ("dst_filename", "filename", "image", "image_name", "file", "name")
                if normalized.get(key, "").lower().endswith(".png")
            ),
            f"img_{index:05d}.png",
        )
        stem = Path(filename).stem
        if stem in metadata:
            raise ValueError(f"Duplicate WE3DS metadata row for {stem}")
        metadata[stem] = normalized
    return metadata


def _we3ds_growth_stage(metadata: dict[str, str], capture_date: str) -> str:
    seeding = next(
        (
            metadata[key]
            for key in ("seeding_date", "seed_date", "date_of_seeding")
            if metadata.get(key) and metadata[key].lower() != "nan"
        ),
        "",
    )
    if seeding:
        try:
            start = datetime.strptime(_we3ds_iso_date(seeding), "%Y-%m-%d").date()
            capture = datetime.strptime(capture_date, "%Y-%m-%d").date()
            days = (capture - start).days
            if days >= 0:
                return f"days_after_seeding_{days}"
        except ValueError:
            pass
    return capture_date


def convert_we3ds(data_root: str | Path) -> Path:
    """Normalize WE3DS while enforcing a capture-date-disjoint split."""
    root = Path(data_root).expanduser().resolve()
    source = _find_dataset_layout(
        root / "raw/we3ds/WE3DS",
        "annotations/segmentation/SegmentationLabel",
    )
    image_root = source / "images"
    semantic_root = source / "annotations/segmentation/SegmentationLabel"
    info_path = source / "info.csv"
    if not image_root.is_dir() or not info_path.is_file():
        raise FileNotFoundError(f"Incomplete WE3DS layout under {source}")
    images = {path.stem: path for path in sorted(image_root.glob("*.png"))}
    semantics = {
        path.stem: path for path in sorted(semantic_root.glob("*.png"))
    }
    if not images or set(images) != set(semantics):
        raise ValueError(
            "WE3DS image/mask pairing mismatch: "
            f"images={len(images)}, masks={len(semantics)}"
        )
    metadata = _we3ds_metadata(info_path)
    if set(metadata) != set(images):
        raise ValueError(
            "WE3DS metadata/image mismatch: "
            f"metadata={len(metadata)}, images={len(images)}"
        )

    normalized_root = root / "processed/we3ds/common_masks"
    records: list[SampleRecord] = []
    excluded_no_crop: list[str] = []
    excluded_multiple_crops: list[str] = []
    for stem, image_path in sorted(images.items()):
        semantic_path = semantics[stem]
        raw = np.asarray(Image.open(semantic_path).convert("L"), dtype=np.uint8)
        values = set(np.unique(raw).tolist())
        if not values <= set(range(19)):
            raise ValueError(f"Unexpected WE3DS labels {values} in {semantic_path}")
        present_crops = [label for label in _WE3DS_CROPS if label in values]
        if not present_crops:
            excluded_no_crop.append(stem)
            continue
        if len(present_crops) > 1:
            excluded_multiple_crops.append(stem)
            continue
        crop_label = present_crops[0]
        crop_species, target_crop_id = _WE3DS_CROPS[crop_label]
        common = np.full(raw.shape, IGNORE, dtype=np.uint8)
        common[raw == 1] = BACKGROUND
        common[raw == crop_label] = CROP
        common[np.isin(raw, list(_WE3DS_WEEDS))] = WEED

        row = metadata[stem]
        raw_date = next(
            (row[key] for key in ("date", "capture_date") if row.get(key)),
            "",
        )
        capture_date = _we3ds_iso_date(raw_date)
        split = _we3ds_split(capture_date)
        common_path = normalized_root / split / f"{stem}.png"
        _save_common_mask(common, common_path)
        records.append(
            SampleRecord(
                sample_id=f"we3ds:{stem}",
                image_path=_relative(image_path, root),
                mask_path=_relative(common_path, root),
                split=split,
                dataset_id="we3ds",
                field_id="boku_gross_enzersdorf_2020_2021",
                session_id=f"capture_date_{capture_date}",
                capture_date=capture_date,
                platform="manual_trolley_top_down",
                sensor="ximea_mc023cg_sy_stereo_rgb_left",
                target_crop_id=target_crop_id,
                crop_species=crop_species,
                weed_species_optional=";".join(_WE3DS_WEEDS.values()),
                growth_stage=_we3ds_growth_stage(row, capture_date),
                annotation_exhaustive=True,
                license_status="CC-BY-4.0",
                commercial_allowed=True,
            )
        )
    destination = root / "processed/manifests/we3ds.csv"
    write_manifest(records, destination)
    split_counts = {
        split: sum(record.split == split for record in records)
        for split in ("train", "val", "test")
    }
    report = {
        "dataset_id": "we3ds",
        "source_images": len(images),
        "included_samples": len(records),
        "excluded_no_target_crop": excluded_no_crop,
        "excluded_multiple_target_crops": excluded_multiple_crops,
        "split_counts": split_counts,
        "policy": {
            "target_identity": "exactly_one_crop_class_in_semantic_mask",
            "no_target_crop": "excluded",
            "multiple_target_crops": "excluded",
            "split": "capture_date_disjoint",
        },
    }
    report_path = root / "processed/manifests/we3ds_conversion.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination


_CROPANDWEED_CROPS: dict[str, tuple[set[int], int]] = {
    "Zea mays": (set(range(1, 7)), 3),
    "Beta vulgaris": (set(range(7, 13)), 0),
    "Pisum sativum": ({13}, 7),
    "Cucurbita spp.": ({15}, 11),
    "Solanum tuberosum": ({18}, 10),
    "Helianthus annuus": ({24}, 9),
    "Phaseolus vulgaris": ({26}, 2),
    "Vicia faba": ({27}, 5),
    "Glycine max": ({94}, 8),
}
_CROPANDWEED_WEED_LABELS = {
    22,
    29,
    30,
    31,
    32,
    33,
    34,
    35,
    36,
    37,
    38,
    39,
    41,
    42,
    44,
    45,
    47,
    48,
    49,
    50,
    51,
    52,
    54,
    56,
    57,
    58,
    59,
    60,
    61,
    62,
    63,
    64,
    65,
    66,
    67,
    68,
    69,
    70,
    71,
    72,
    74,
    75,
    76,
    77,
    78,
    79,
    80,
    81,
    83,
    84,
    85,
    86,
    87,
    88,
    89,
    91,
    96,
}
_CROPANDWEED_STAGE_LABELS = {
    1: "unspecified",
    2: "two_leaf",
    3: "four_leaf",
    4: "six_leaf",
    5: "eight_leaf",
    6: "maximum",
    7: "unspecified",
    8: "two_leaf",
    9: "four_leaf",
    10: "six_leaf",
    11: "eight_leaf",
    12: "maximum",
}


def _cropandweed_gate(path: str | Path) -> tuple[dict[str, object], set[str]]:
    gate_path = Path(path)
    with gate_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict) or payload.get("dataset_id") != "cropandweed":
        raise ValueError(f"Invalid CropAndWeed gate config: {gate_path}")
    raw_sessions = payload.get("external_calibration_sessions")
    if not isinstance(raw_sessions, list) or not raw_sessions:
        raise ValueError("CropAndWeed gate must freeze calibration sessions")
    sessions = {str(value) for value in raw_sessions}
    if len(sessions) != len(raw_sessions):
        raise ValueError("CropAndWeed calibration session list contains duplicates")
    return payload, sessions


def _cropandweed_growth_stage(crop_species: str, values: set[int]) -> str:
    crop_labels = _CROPANDWEED_CROPS[crop_species][0]
    stages = sorted(
        {
            _CROPANDWEED_STAGE_LABELS[label]
            for label in values & crop_labels
            if label in _CROPANDWEED_STAGE_LABELS
        }
    )
    return "+".join(stages) if stages else "unknown"


def convert_cropandweed(
    data_root: str | Path,
    gate_config: str | Path = "configs/data/cropandweed_real_gate_v1.yaml",
) -> Path:
    """Normalize CropAndWeed with fail-closed target identity and session holdout."""
    root = Path(data_root).expanduser().resolve()
    source = _find_dataset_layout(
        root / "raw/cropandweed/repository", "labelIds/CropAndWeed"
    )
    image_root = source / "images"
    semantic_root = source / "labelIds/CropAndWeed"
    bbox_root = source / "bboxes"
    params_root = source / "params"
    if not all(path.is_dir() for path in (image_root, semantic_root, bbox_root, params_root)):
        raise FileNotFoundError(f"Incomplete CropAndWeed layout under {source}")

    gate, calibration_sessions = _cropandweed_gate(gate_config)
    images = {
        path.stem: path
        for path in sorted(image_root.iterdir())
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    }
    semantics = {path.stem: path for path in sorted(semantic_root.glob("*.png"))}
    bboxes = {path.stem: path for path in sorted(bbox_root.glob("*.csv"))}
    params = {path.stem: path for path in sorted(params_root.glob("*.csv"))}
    stem_sets = {
        "images": set(images),
        "semantics": set(semantics),
        "bboxes": set(bboxes),
        "params": set(params),
    }
    if not images or any(stems != set(images) for stems in stem_sets.values()):
        raise ValueError(
            "CropAndWeed image/annotation pairing mismatch: "
            + ", ".join(f"{name}={len(stems)}" for name, stems in stem_sets.items())
        )

    expected = gate.get("expected_counts", {})
    if not isinstance(expected, dict):
        raise ValueError("CropAndWeed expected_counts must be a mapping")
    expected_source = int(expected.get("source_images", len(images)))
    if len(images) != expected_source:
        raise ValueError(
            f"Unexpected CropAndWeed source count: {len(images)} != {expected_source}"
        )

    annotation_archive = root / "raw/cropandweed/archives/cropandweed_annotations.tar"
    expected_annotation_sha = str(gate.get("annotation_archive_sha256", ""))
    annotation_sha = "unavailable"
    if annotation_archive.is_file():
        annotation_sha = file_checksum(annotation_archive, "sha256")
        if expected_annotation_sha and annotation_sha != expected_annotation_sha:
            raise ValueError(
                "CropAndWeed annotation archive SHA-256 mismatch: "
                f"{annotation_sha} != {expected_annotation_sha}"
            )

    crop_labels = set().union(*(entry[0] for entry in _CROPANDWEED_CROPS.values()))
    known_labels = {0, 255} | crop_labels | _CROPANDWEED_WEED_LABELS
    normalized_root = root / "processed/cropandweed/common_masks"
    records: list[SampleRecord] = []
    condition_rows: list[dict[str, object]] = []
    excluded_no_crop: list[str] = []
    excluded_multiple_crops: list[str] = []
    bbox_semantic_mismatches: list[str] = []
    class_pixels = {"background": 0, "target_crop": 0, "weed": 0, "ignore": 0}
    ignored_label_image_counts: dict[int, int] = {}

    for stem, image_path in sorted(images.items()):
        semantic_path = semantics[stem]
        with Image.open(semantic_path) as mask_image:
            raw = np.asarray(mask_image.convert("L"), dtype=np.uint8)
        with Image.open(image_path) as intensity_image:
            image_size = intensity_image.size
        if image_size != (raw.shape[1], raw.shape[0]):
            raise ValueError(
                f"CropAndWeed shape mismatch for {stem}: "
                f"image={image_size}, mask={(raw.shape[1], raw.shape[0])}"
            )
        values = set(np.unique(raw).tolist())
        if not values <= ({*range(100), 255}):
            raise ValueError(f"Unexpected CropAndWeed labels {values} in {semantic_path}")

        bbox_values: set[int] = set()
        with bboxes[stem].open("r", encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                if row:
                    if len(row) != 7:
                        raise ValueError(f"Malformed CropAndWeed bbox row in {bboxes[stem]}")
                    bbox_values.add(int(row[4]))
        if values - {0, 255} != bbox_values - {255}:
            bbox_semantic_mismatches.append(stem)

        present_crops = [
            species
            for species, (labels, _) in _CROPANDWEED_CROPS.items()
            if values & labels
        ]
        if not present_crops:
            excluded_no_crop.append(stem)
            continue
        if len(present_crops) > 1:
            excluded_multiple_crops.append(stem)
            continue
        crop_species = present_crops[0]
        target_labels, target_crop_id = _CROPANDWEED_CROPS[crop_species]

        with params[stem].open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if len(rows) != 1:
            raise ValueError(f"Expected one CropAndWeed parameter row in {params[stem]}")
        parameter_values = {
            key: int(rows[0][key])
            for key in ("moisture", "soil", "lighting", "separability")
        }
        allowed_parameters = {
            "moisture": {0, 1, 2},
            "soil": {0, 1, 2},
            "lighting": {0, 1},
            "separability": {0, 1, 2},
        }
        if any(
            parameter_values[key] not in allowed
            for key, allowed in allowed_parameters.items()
        ):
            raise ValueError(f"Unexpected CropAndWeed parameters in {params[stem]}")

        prefix, session_number, _ = stem.split("-")
        session_id = f"{prefix}-{session_number}"
        split = (
            "external_calibration"
            if session_id in calibration_sessions
            else "train"
        )
        common = np.full(raw.shape, IGNORE, dtype=np.uint8)
        common[raw == 0] = BACKGROUND
        common[np.isin(raw, sorted(target_labels))] = CROP
        common[np.isin(raw, sorted(_CROPANDWEED_WEED_LABELS))] = WEED
        common_path = normalized_root / split / f"{stem}.png"
        _save_common_mask(common, common_path)

        ignored_labels = sorted(values - known_labels)
        for label in ignored_labels:
            ignored_label_image_counts[label] = ignored_label_image_counts.get(label, 0) + 1
        weed_labels = sorted(values & _CROPANDWEED_WEED_LABELS)
        for name, label in (
            ("background", BACKGROUND),
            ("target_crop", CROP),
            ("weed", WEED),
            ("ignore", IGNORE),
        ):
            class_pixels[name] += int((common == label).sum())

        field_id = (
            "austria_commercial_sites_unresolved"
            if prefix == "ave"
            else "ait_gross_enzersdorf_experimental"
        )
        record = SampleRecord(
            sample_id=f"cropandweed:{stem}",
            image_path=_relative(image_path, root),
            mask_path=_relative(common_path, root),
            split=split,
            dataset_id="cropandweed",
            field_id=field_id,
            session_id=session_id,
            capture_date="unknown",
            platform="handheld_top_down_1.1m",
            sensor="full_frame_dslr_50mm_rgb_autoexposure",
            target_crop_id=target_crop_id,
            crop_species=crop_species,
            weed_species_optional=";".join(f"raw_id_{label}" for label in weed_labels),
            growth_stage=_cropandweed_growth_stage(crop_species, values),
            annotation_exhaustive=not bool(np.any(common == IGNORE)),
            license_status="non-commercial-research-only;no-redistribution",
            commercial_allowed=False,
        )
        records.append(record)
        condition_rows.append(
            {
                "sample_id": record.sample_id,
                "session_id": session_id,
                "split": split,
                "crop_species": crop_species,
                **parameter_values,
                "source_raw_labels": ";".join(map(str, sorted(values))),
                "ignored_raw_labels": ";".join(map(str, ignored_labels)),
                "has_ambiguous_vegetation_255": 255 in values,
            }
        )

    included_sessions = {record.session_id for record in records}
    unknown_calibration_sessions = calibration_sessions - included_sessions
    if unknown_calibration_sessions:
        raise ValueError(
            "Frozen CropAndWeed calibration sessions are not eligible: "
            f"{sorted(unknown_calibration_sessions)}"
        )
    actual_counts = {
        "included_samples": len(records),
        "excluded_no_target_crop": len(excluded_no_crop),
        "excluded_multiple_target_crops": len(excluded_multiple_crops),
        "bbox_semantic_labelset_mismatches": len(bbox_semantic_mismatches),
    }
    for key, actual in actual_counts.items():
        if key in expected and actual != int(expected[key]):
            raise ValueError(
                f"Unexpected CropAndWeed {key}: {actual} != {int(expected[key])}"
            )

    destination = root / "processed/manifests/cropandweed.csv"
    write_manifest(records, destination)
    condition_path = root / "processed/cropandweed/conditions.csv"
    condition_path.parent.mkdir(parents=True, exist_ok=True)
    condition_columns = [
        "sample_id",
        "session_id",
        "split",
        "crop_species",
        "moisture",
        "soil",
        "lighting",
        "separability",
        "source_raw_labels",
        "ignored_raw_labels",
        "has_ambiguous_vegetation_255",
    ]
    with condition_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=condition_columns)
        writer.writeheader()
        writer.writerows(condition_rows)

    split_counts = {
        split: sum(record.split == split for record in records)
        for split in ("train", "external_calibration")
    }
    crop_counts = {
        species: {
            split: sum(
                record.crop_species == species and record.split == split
                for record in records
            )
            for split in ("train", "external_calibration")
        }
        for species in _CROPANDWEED_CROPS
    }
    report = {
        "dataset_id": "cropandweed",
        "source_images": len(images),
        **actual_counts,
        "split_counts": split_counts,
        "session_counts": {
            split: len({record.session_id for record in records if record.split == split})
            for split in ("train", "external_calibration")
        },
        "crop_counts": crop_counts,
        "class_pixels": class_pixels,
        "ignored_label_image_counts": ignored_label_image_counts,
        "excluded_no_target_crop_samples": excluded_no_crop,
        "excluded_multiple_target_crop_samples": excluded_multiple_crops,
        "bbox_semantic_labelset_mismatch_samples": bbox_semantic_mismatches,
        "provenance": {
            "annotation_archive_sha256": annotation_sha,
            "gate_config": str(Path(gate_config).resolve()),
            "gate_config_sha256": file_checksum(Path(gate_config), "sha256"),
        },
        "policy": {
            "target_identity": "exactly_one_official_crop_group_in_semantic_mask",
            "no_target_crop": "excluded",
            "multiple_target_crops": "excluded",
            "raw_255": "ignore",
            "unsupported_raw_labels": "ignore",
            "split": "explicit_frozen_session_disjoint_80_20",
            "licence": "research_only_no_raw_or_modified_data_redistribution",
        },
    }
    report_path = root / "processed/manifests/cropandweed_conversion.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination


_RICE_SEEDLING_WEED_SOURCE_TILES = 224
_RICE_SEEDLING_WEED_IMAGE_SIZE = (912, 1024)
_RICE_SEEDLING_WEED_EXPECTED_RAW_PIXEL_COUNTS = {
    0: 13_752_258,
    1: 22_507_511,
    2: 163_104_287,
    3: 9_826_856,
}
_RICE_SEEDLING_WEED_ARCHIVE_SHA256 = (
    "dab8deb4d412cf26094279337b198cbaef4588cd4dd9f6327c67871124b47bf5"
)


def _normalize_rice_seedling_weed_mask(raw: np.ndarray) -> np.ndarray:
    """Map publisher labels while preserving unlabeled boundary pixels.

    The paper's three reported class frequencies exactly match raw labels
    1/2/3 after raw label 0 is excluded. Raw 0 also traces plant boundaries
    from both semantic classes, so treating it as crop or background would
    introduce false supervision.
    """
    values = set(np.unique(raw).tolist())
    if not values <= {0, 1, 2, 3}:
        raise ValueError(f"Unexpected Rice Seedling Weed labels: {values}")
    common = np.full(raw.shape, IGNORE, dtype=np.uint8)
    common[raw == 1] = CROP
    common[raw == 2] = BACKGROUND
    common[raw == 3] = WEED
    return common


def convert_rice_seedling_weed(data_root: str | Path) -> Path:
    """Normalize the single-session paddy dataset as train-only data.

    The 224 released tiles came from only 28 photographs (eight tiles per
    photograph). The release does not retain parent-photo IDs. Keeping every
    tile in one training split is therefore the only fail-closed use that
    cannot leak sibling tiles into an internal evaluation split.
    """
    root = Path(data_root).expanduser().resolve()
    source = root / "raw/rice_seedling_weed/repository"
    image_root = source / "image"
    mask_root = source / "PixelLabelData"
    if not image_root.is_dir() or not mask_root.is_dir():
        raise FileNotFoundError(f"Incomplete Rice Seedling Weed layout at {source}")

    image_pattern = re.compile(r"image_(\d+)\.(?:jpg|jpeg|png)", re.IGNORECASE)
    mask_pattern = re.compile(r"Label_(\d+)\.png", re.IGNORECASE)

    def indexed_files(directory: Path, pattern: re.Pattern[str]) -> dict[int, Path]:
        indexed: dict[int, Path] = {}
        unexpected: list[str] = []
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            match = pattern.fullmatch(path.name)
            if not match:
                unexpected.append(path.name)
                continue
            index = int(match.group(1))
            if index in indexed:
                raise ValueError(f"Duplicate Rice Seedling Weed tile ID {index}")
            indexed[index] = path
        if unexpected:
            raise ValueError(
                f"Unexpected files in Rice Seedling Weed layout: {unexpected[:10]}"
            )
        return indexed

    images = indexed_files(image_root, image_pattern)
    masks = indexed_files(mask_root, mask_pattern)
    expected_ids = set(range(1, _RICE_SEEDLING_WEED_SOURCE_TILES + 1))
    if set(images) != expected_ids or set(masks) != expected_ids:
        raise ValueError(
            "Rice Seedling Weed pairing/count mismatch: "
            f"images={len(images)}, masks={len(masks)}, "
            f"missing_images={sorted(expected_ids - set(images))[:10]}, "
            f"missing_masks={sorted(expected_ids - set(masks))[:10]}"
        )

    normalized_root = root / "processed/rice_seedling_weed/common_masks/train"
    raw_pixel_counts = {label: 0 for label in range(4)}
    common_pixel_counts = {
        "background": 0,
        "target_crop": 0,
        "weed": 0,
        "ignore": 0,
    }
    records: list[SampleRecord] = []
    for index in sorted(expected_ids):
        image_path = images[index]
        mask_path = masks[index]
        with Image.open(image_path) as image:
            image_size = image.size
        with Image.open(mask_path) as mask_image:
            raw = np.asarray(mask_image, dtype=np.uint8)
        if image_size != _RICE_SEEDLING_WEED_IMAGE_SIZE:
            raise ValueError(
                f"Unexpected Rice Seedling Weed image size for {image_path}: "
                f"{image_size} != {_RICE_SEEDLING_WEED_IMAGE_SIZE}"
            )
        if raw.shape != (image_size[1], image_size[0]):
            raise ValueError(
                f"Rice Seedling Weed shape mismatch for tile {index}: "
                f"image={image_size}, mask={(raw.shape[1], raw.shape[0])}"
            )
        common = _normalize_rice_seedling_weed_mask(raw)
        for label in raw_pixel_counts:
            raw_pixel_counts[label] += int((raw == label).sum())
        for name, label in (
            ("background", BACKGROUND),
            ("target_crop", CROP),
            ("weed", WEED),
            ("ignore", IGNORE),
        ):
            common_pixel_counts[name] += int((common == label).sum())

        common_path = normalized_root / f"{index:03d}.png"
        _save_common_mask(common, common_path)
        records.append(
            SampleRecord(
                sample_id=f"rice_seedling_weed:{index:03d}",
                image_path=_relative(image_path, root),
                mask_path=_relative(common_path, root),
                split="train",
                dataset_id="rice_seedling_weed",
                field_id="jiangmen_guangdong_paddy_2018",
                session_id="jiangmen_2018-04-13_single_session",
                capture_date="2018-04-13",
                platform="ground_camera_top_down_0.8_1.2m",
                sensor="canon_ixus_1000_hs_rgb",
                target_crop_id=12,
                crop_species="Oryza sativa",
                weed_species_optional="Sagittaria trifolia",
                growth_stage="rice_20_days_after_transplant;weed_early",
                annotation_exhaustive=False,
                license_status="CC-BY-4.0",
                commercial_allowed=True,
            )
        )

    if raw_pixel_counts != _RICE_SEEDLING_WEED_EXPECTED_RAW_PIXEL_COUNTS:
        raise ValueError(
            "Rice Seedling Weed aggregate label counts changed: "
            f"{raw_pixel_counts} != "
            f"{_RICE_SEEDLING_WEED_EXPECTED_RAW_PIXEL_COUNTS}"
        )

    destination = root / "processed/manifests/rice_seedling_weed.csv"
    write_manifest(records, destination)
    archive = (
        root
        / "raw/rice_seedling_weed/archives/rice_seedling_and_weed_dataset.rar"
    )
    archive_sha256 = (
        file_checksum(archive, "sha256") if archive.is_file() else "unavailable"
    )
    if (
        archive_sha256 != "unavailable"
        and archive_sha256 != _RICE_SEEDLING_WEED_ARCHIVE_SHA256
    ):
        raise ValueError(
            f"Rice Seedling Weed archive SHA-256 mismatch: {archive_sha256}"
        )
    labeled_pixels = sum(raw_pixel_counts[label] for label in (1, 2, 3))
    report = {
        "dataset_id": "rice_seedling_weed",
        "included_samples": len(records),
        "split_counts": {"train": len(records)},
        "source_parent_photos": 28,
        "released_tiles_per_parent": 8,
        "raw_pixel_counts": raw_pixel_counts,
        "common_pixel_counts": common_pixel_counts,
        "labeled_class_fractions": {
            "target_crop": raw_pixel_counts[1] / labeled_pixels,
            "background": raw_pixel_counts[2] / labeled_pixels,
            "weed": raw_pixel_counts[3] / labeled_pixels,
        },
        "provenance": {
            "archive_sha256": archive_sha256,
            "figshare_doi": "10.6084/m9.figshare.7488830.v5",
            "paper_doi": "10.1371/journal.pone.0215676",
        },
        "policy": {
            "raw_0": "ignore_unlabeled_boundary",
            "raw_1": "target_crop",
            "raw_2": "background",
            "raw_3": "weed",
            "split": "all_train_single_field_session_no_parent_ids",
            "evaluation": "never_use_any_released_tile_for_internal_evaluation",
        },
    }
    report_path = root / "processed/manifests/rice_seedling_weed_conversion.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination


def _ewis_metadata(stem: str) -> tuple[str, str, str, int]:
    """Return capture date, field, session, and deployment crop ID."""
    legacy = re.fullmatch(
        r"img_(\d{8})_([A-Za-z]\d+)_(\d+)_(\d+)", stem
    )
    if legacy:
        date, field, flight, _ = legacy.groups()
        return date, field, f"{date}_{field}_flight_{flight}", 31
    named = re.fullmatch(
        r"([^_]+)_(\d{8})_(Maize|Sorghum)_(\d+)", stem
    )
    if named:
        field, date, crop, _ = named.groups()
        crop_id = 3 if crop.lower() == "maize" else 4
        return date, field, f"{field}_{date}_{crop}", crop_id
    raise ValueError(f"Unrecognized EWIS1 filename: {stem}")


def convert_ewis1(data_root: str | Path) -> Path:
    """Convert the 88-image EWIS1 UAV set as a locked grouped external test."""
    root = Path(data_root).expanduser().resolve()
    images_root = root / "raw/ewis1/images"
    masks_root = root / "raw/ewis1/masks"
    image_paths = [
        path
        for path in images_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ]
    mask_paths = [
        path
        for path in masks_root.rglob("*")
        if path.is_file() and path.suffix.lower() == ".png"
    ]
    images_by_stem = {path.stem: path for path in image_paths}
    masks_by_stem = {path.stem: path for path in mask_paths}
    if len(images_by_stem) != len(image_paths):
        raise ValueError("Duplicate EWIS1 image stems")
    if len(masks_by_stem) != len(mask_paths):
        raise ValueError("Duplicate EWIS1 mask stems")
    if set(images_by_stem) != set(masks_by_stem):
        missing_images = sorted(set(masks_by_stem) - set(images_by_stem))
        missing_masks = sorted(set(images_by_stem) - set(masks_by_stem))
        raise ValueError(
            f"EWIS1 pairing mismatch; images missing {missing_images[:5]}, "
            f"masks missing {missing_masks[:5]}"
        )
    if not images_by_stem:
        raise FileNotFoundError(
            f"No paired EWIS1 files under {images_root} and {masks_root}"
        )

    background = np.array([0, 0, 0], dtype=np.uint8)
    crop_color = np.array([31, 119, 180], dtype=np.uint8)
    weed_color = np.array([255, 127, 14], dtype=np.uint8)
    normalized_root = root / "processed/ewis1/common_masks"
    records: list[SampleRecord] = []
    for stem in sorted(images_by_stem):
        image_path = images_by_stem[stem]
        mask_path = masks_by_stem[stem]
        raw = np.asarray(Image.open(mask_path).convert("RGB"), dtype=np.uint8)
        is_background = np.all(raw == background, axis=-1)
        is_crop = np.all(raw == crop_color, axis=-1)
        is_weed = np.all(raw == weed_color, axis=-1)
        if not np.all(is_background | is_crop | is_weed):
            invalid_colors = np.unique(
                raw[~(is_background | is_crop | is_weed)].reshape(-1, 3),
                axis=0,
            )
            raise ValueError(
                f"Unexpected EWIS1 mask colors in {mask_path}: "
                f"{invalid_colors[:10].tolist()}"
            )
        common = np.zeros(raw.shape[:2], dtype=np.uint8)
        common[is_crop] = CROP
        common[is_weed] = WEED
        common_path = normalized_root / f"{stem}.png"
        _save_common_mask(common, common_path)

        date, field, session, crop_id = _ewis_metadata(stem)
        crop_species = {
            3: "Zea mays",
            4: "Sorghum bicolor",
            31: "Zea mays or Sorghum bicolor",
        }[crop_id]
        records.append(
            SampleRecord(
                sample_id=f"ewis1:{stem}",
                image_path=_relative(image_path, root),
                mask_path=_relative(common_path, root),
                split="external_test",
                dataset_id="ewis1",
                field_id=field,
                session_id=session,
                capture_date=date,
                platform="uav_dji_mavic_2_pro_5m",
                sensor="hasselblad_l1d_20c_rgb",
                target_crop_id=crop_id,
                crop_species=crop_species,
                weed_species_optional="mixed",
                growth_stage="mixed",
                annotation_exhaustive=True,
                license_status="CC-BY-4.0",
                commercial_allowed=True,
            )
        )
    destination = root / "processed/manifests/ewis1.csv"
    write_manifest(records, destination)
    return destination


_SORGHUM_WEED_SPLITS = {
    "Train": "train",
    "Validate": "external_calibration",
    "Test": "external_test",
}
_SORGHUM_WEED_CLASSES = {
    "Sorghum": CROP,
    "Grass": WEED,
    "BLweed": WEED,
}


def _via_regions(entry: dict[str, object]) -> list[dict[str, object]]:
    value = entry.get("regions", [])
    if isinstance(value, list):
        regions = value
    elif isinstance(value, dict):
        regions = list(value.values())
    else:
        raise ValueError(f"Invalid VIA regions container: {type(value).__name__}")
    if not all(isinstance(region, dict) for region in regions):
        raise ValueError("Every VIA region must be an object")
    return regions  # type: ignore[return-value]


def _rasterize_sorghum_weed_entry(
    entry: dict[str, object], image_size: tuple[int, int]
) -> tuple[np.ndarray, dict[str, int], int, int]:
    width, height = image_size
    crop_layer = Image.new("1", image_size, 0)
    weed_layer = Image.new("1", image_size, 0)
    crop_draw = ImageDraw.Draw(crop_layer)
    weed_draw = ImageDraw.Draw(weed_layer)
    class_instances = {name: 0 for name in _SORGHUM_WEED_CLASSES}
    clipped_vertices = 0
    for region in _via_regions(entry):
        attributes = region.get("region_attributes")
        shape = region.get("shape_attributes")
        if not isinstance(attributes, dict) or not isinstance(shape, dict):
            raise ValueError("VIA region attributes and shape must be objects")
        class_name = str(attributes.get("classname", ""))
        if class_name not in _SORGHUM_WEED_CLASSES:
            raise ValueError(f"Unknown SorghumWeed class: {class_name!r}")
        if shape.get("name") != "polygon":
            raise ValueError(f"Unsupported VIA shape: {shape.get('name')!r}")
        xs = shape.get("all_points_x")
        ys = shape.get("all_points_y")
        if not isinstance(xs, list) or not isinstance(ys, list):
            raise ValueError("VIA polygon coordinates must be arrays")
        if len(xs) != len(ys) or len(xs) < 3:
            raise ValueError("VIA polygon must have at least three paired points")
        points = []
        for raw_x, raw_y in zip(xs, ys, strict=True):
            x, y = int(raw_x), int(raw_y)
            clipped_x = min(max(x, 0), width - 1)
            clipped_y = min(max(y, 0), height - 1)
            clipped_vertices += int((clipped_x, clipped_y) != (x, y))
            points.append((clipped_x, clipped_y))
        draw = crop_draw if _SORGHUM_WEED_CLASSES[class_name] == CROP else weed_draw
        draw.polygon(points, fill=1)
        class_instances[class_name] += 1

    crop = np.asarray(crop_layer, dtype=bool)
    weed = np.asarray(weed_layer, dtype=bool)
    conflict = crop & weed
    common = np.full((height, width), BACKGROUND, dtype=np.uint8)
    common[crop] = CROP
    common[weed] = WEED
    common[conflict] = IGNORE
    return common, class_instances, int(conflict.sum()), clipped_vertices


def convert_sorghum_weed(data_root: str | Path) -> Path:
    """Normalize the official SorghumWeed train/validate/test release.

    The COCO category names in the release are blank. The VIA JSON is used
    because it preserves the explicit Sorghum/Grass/BLweed class names.
    """
    root = Path(data_root).expanduser().resolve()
    source = _find_dataset_layout(
        root / "raw/sorghum_weed/repository",
        "SorghumWeedDataset_Segmentation",
    ) / "SorghumWeedDataset_Segmentation"
    normalized_root = root / "processed/sorghum_weed/common_masks"
    records: list[SampleRecord] = []
    split_counts: dict[str, int] = {}
    class_instances = {name: 0 for name in _SORGHUM_WEED_CLASSES}
    conflict_pixels = 0
    clipped_polygon_vertices = 0
    annotation_hashes: dict[str, str] = {}

    for source_split, split in _SORGHUM_WEED_SPLITS.items():
        split_root = source / source_split
        annotation_path = split_root / f"{source_split}SorghumWeed_json.json"
        if not annotation_path.is_file():
            raise FileNotFoundError(annotation_path)
        annotation_hashes[source_split] = file_checksum(annotation_path, "sha256")
        payload = json.loads(annotation_path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError(f"Expected VIA object in {annotation_path}")
        entries: list[dict[str, object]] = []
        for value in payload.values():
            if not isinstance(value, dict):
                raise ValueError(f"Invalid VIA image entry in {annotation_path}")
            entries.append(value)
        entries.sort(key=lambda entry: str(entry.get("filename", "")))
        seen_filenames: set[str] = set()
        for entry in entries:
            filename = str(entry.get("filename", ""))
            if not filename or filename in seen_filenames:
                raise ValueError(f"Missing or duplicate VIA filename: {filename!r}")
            seen_filenames.add(filename)
            image_path = split_root / filename
            if not image_path.is_file():
                raise FileNotFoundError(image_path)
            with Image.open(image_path) as image:
                image_size = image.size
            common, counts, conflicts, clipped_vertices = _rasterize_sorghum_weed_entry(
                entry, image_size
            )
            for class_name, count in counts.items():
                class_instances[class_name] += count
            conflict_pixels += conflicts
            clipped_polygon_vertices += clipped_vertices
            stem = Path(filename).stem
            common_path = normalized_root / split / f"{stem}.png"
            _save_common_mask(common, common_path)
            records.append(
                SampleRecord(
                    sample_id=f"sorghum_weed:{source_split.lower()}:{stem}",
                    image_path=_relative(image_path, root),
                    mask_path=_relative(common_path, root),
                    split=split,
                    dataset_id="sorghum_weed",
                    field_id="srm_care_farm_chengalpattu_2023",
                    session_id=f"official_{source_split.lower()}_partition",
                    capture_date="2023-04_to_2023-05",
                    platform="handheld_or_tripod_dslr",
                    sensor="canon_eos_80d_rgb",
                    target_crop_id=4,
                    crop_species="Sorghum bicolor",
                    weed_species_optional="grass and broad-leaf weeds",
                    growth_stage="early_critical_weed_competition",
                    annotation_exhaustive=True,
                    license_status="CC-BY-4.0",
                    commercial_allowed=True,
                )
            )
        split_counts[split] = len(entries)

    destination = root / "processed/manifests/sorghum_weed.csv"
    write_manifest(records, destination)
    report = {
        "dataset_id": "sorghum_weed",
        "source": str(source),
        "source_annotation_sha256": annotation_hashes,
        "split_counts": split_counts,
        "class_instance_counts": class_instances,
        "observed_polygon_instances": sum(class_instances.values()),
        "publisher_readme_claimed_segments": 5555,
        "publisher_claim_minus_observed_instances": (
            5555 - sum(class_instances.values())
        ),
        "out_of_bounds_polygon_vertices_clipped": clipped_polygon_vertices,
        "crop_weed_conflict_pixels_mapped_to_ignore": conflict_pixels,
        "mapping": {
            "Sorghum": CROP,
            "Grass": WEED,
            "BLweed": WEED,
            "unannotated": BACKGROUND,
            "crop_weed_overlap": IGNORE,
        },
        "split_caveat": (
            "The official partitions are image-disjoint but originate from one "
            "named farm; they are not evidence of unseen-field generalization."
        ),
    }
    report_path = root / "processed/manifests/sorghum_weed_conversion.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination


@dataclass(frozen=True)
class AuditResult:
    samples: int
    missing_files: int
    invalid_masks: int
    shape_mismatches: int
    split_counts: dict[str, int]
    dataset_counts: dict[str, int]
    class_pixel_counts: dict[str, int]


def audit_manifest(
    manifest_path: str | Path, data_root: str | Path
) -> AuditResult:
    root = Path(data_root).expanduser().resolve()
    records = read_manifest(manifest_path)
    missing = 0
    invalid = 0
    mismatched = 0
    split_counts: dict[str, int] = {}
    dataset_counts: dict[str, int] = {}
    class_pixels = {
        "background": 0,
        "target_crop": 0,
        "other_vegetation": 0,
        "ignore": 0,
    }
    allowed = {BACKGROUND, CROP, WEED, IGNORE}
    for record in records:
        split_counts[record.split] = split_counts.get(record.split, 0) + 1
        dataset_counts[record.dataset_id] = (
            dataset_counts.get(record.dataset_id, 0) + 1
        )
        image_path = Path(record.image_path)
        mask_path = Path(record.mask_path)
        image_path = image_path if image_path.is_absolute() else root / image_path
        mask_path = mask_path if mask_path.is_absolute() else root / mask_path
        if not image_path.is_file() or not mask_path.is_file():
            missing += 1
            continue
        image = load_rgb_image(image_path)
        image_height, image_width = image_hw(image)
        with Image.open(mask_path) as mask:
            if (image_width, image_height) != mask.size:
                mismatched += 1
            mask_array = np.asarray(mask)
            if not set(np.unique(mask_array).tolist()) <= allowed:
                invalid += 1
            class_pixels["background"] += int((mask_array == BACKGROUND).sum())
            class_pixels["target_crop"] += int((mask_array == CROP).sum())
            class_pixels["other_vegetation"] += int((mask_array == WEED).sum())
            class_pixels["ignore"] += int((mask_array == IGNORE).sum())
    return AuditResult(
        samples=len(records),
        missing_files=missing,
        invalid_masks=invalid,
        shape_mismatches=mismatched,
        split_counts=split_counts,
        dataset_counts=dataset_counts,
        class_pixel_counts=class_pixels,
    )


def _difference_hash(path: Path, hash_size: int = 16) -> int:
    image = to_display_pil(load_rgb_image(path))
    gray = image.convert("L").resize(
        (hash_size + 1, hash_size), Image.Resampling.LANCZOS
    )
    values = np.asarray(gray)
    bits = (values[:, 1:] > values[:, :-1]).reshape(-1)
    result = 0
    for bit in bits:
        result = (result << 1) | int(bit)
    return result


def cross_split_near_duplicates(
    manifest_path: str | Path,
    data_root: str | Path,
    max_hamming: int = 2,
) -> dict[str, object]:
    root = Path(data_root).expanduser().resolve()
    records = read_manifest(manifest_path)
    hashed: list[tuple[SampleRecord, int]] = []
    for record in records:
        image_path = Path(record.image_path)
        image_path = image_path if image_path.is_absolute() else root / image_path
        hashed.append((record, _difference_hash(image_path)))
    matches: list[dict[str, object]] = []
    for left_index, (left, left_hash) in enumerate(hashed):
        for right, right_hash in hashed[left_index + 1 :]:
            if left.split == right.split:
                continue
            distance = (left_hash ^ right_hash).bit_count()
            if distance <= max_hamming:
                matches.append(
                    {
                        "left": left.sample_id,
                        "left_split": left.split,
                        "right": right.sample_id,
                        "right_split": right.split,
                        "hamming": distance,
                    }
                )
    return {
        "hash": "dHash-256",
        "max_hamming": max_hamming,
        "samples": len(records),
        "cross_split_matches": matches,
        "match_count": len(matches),
        "note": (
            "This catches exact/very-near visual duplicates; it does not prove "
            "sequence independence."
        ),
    }


def write_audit(result: AuditResult, destination: str | Path) -> None:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
