"""Manifest I/O, validation, and leakage checks."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

from .constants import MANIFEST_COLUMNS


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y"}:
        return True
    if normalized in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Not a boolean value: {value!r}")


@dataclass(frozen=True)
class SampleRecord:
    sample_id: str
    image_path: str
    mask_path: str
    split: str
    dataset_id: str
    field_id: str
    session_id: str
    capture_date: str
    platform: str
    sensor: str
    target_crop_id: int
    crop_species: str
    weed_species_optional: str
    growth_stage: str
    annotation_exhaustive: bool
    license_status: str
    commercial_allowed: bool

    @classmethod
    def from_mapping(cls, row: Mapping[str, object]) -> "SampleRecord":
        missing = [column for column in MANIFEST_COLUMNS if column not in row]
        if missing:
            raise ValueError(f"Manifest row is missing columns: {missing}")
        values = {column: row[column] for column in MANIFEST_COLUMNS}
        values["target_crop_id"] = int(values["target_crop_id"])
        values["annotation_exhaustive"] = _as_bool(values["annotation_exhaustive"])
        values["commercial_allowed"] = _as_bool(values["commercial_allowed"])
        record = cls(**values)  # type: ignore[arg-type]
        record.validate()
        return record

    def validate(self) -> None:
        if not self.sample_id:
            raise ValueError("sample_id cannot be empty")
        if self.split not in {
            "train",
            "val",
            "test",
            "external_calibration",
            "external_test",
        }:
            raise ValueError(f"Unsupported split: {self.split!r}")
        if self.target_crop_id < 0:
            raise ValueError("target_crop_id must be non-negative")
        if not self.image_path or not self.mask_path:
            raise ValueError("image_path and mask_path are required")

    @property
    def group_id(self) -> str:
        """Capture group that must never cross train/evaluation boundaries."""
        return "::".join((self.dataset_id, self.field_id, self.session_id))


def write_manifest(records: Iterable[SampleRecord], path: str | Path) -> int:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    rows = list(records)
    validate_records(rows)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for record in rows:
            writer.writerow(asdict(record))
    return len(rows)


def read_manifest(path: str | Path) -> list[SampleRecord]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        records = [
            SampleRecord.from_mapping(row) for row in csv.DictReader(handle)
        ]
    validate_records(records)
    return records


def combine_manifests(
    sources: Sequence[str | Path], destination: str | Path
) -> int:
    """Combine canonical manifests while re-running ID and leakage checks."""
    if not sources:
        raise ValueError("At least one source manifest is required")
    records: list[SampleRecord] = []
    for source in sources:
        records.extend(read_manifest(source))
    return write_manifest(records, destination)


def iter_resolved(
    records: Sequence[SampleRecord], data_root: str | Path
) -> Iterator[tuple[SampleRecord, Path, Path]]:
    root = Path(data_root).expanduser().resolve()
    for record in records:
        image = Path(record.image_path)
        mask = Path(record.mask_path)
        yield (
            record,
            image if image.is_absolute() else root / image,
            mask if mask.is_absolute() else root / mask,
        )


def validate_records(records: Sequence[SampleRecord]) -> None:
    seen_ids: set[str] = set()
    for record in records:
        record.validate()
        if record.sample_id in seen_ids:
            raise ValueError(f"Duplicate sample_id: {record.sample_id}")
        seen_ids.add(record.sample_id)
    assert_no_group_leakage(records)


def assert_no_group_leakage(records: Sequence[SampleRecord]) -> None:
    """Reject any capture/session group assigned to more than one split."""
    group_splits: dict[str, set[str]] = {}
    for record in records:
        group_splits.setdefault(record.group_id, set()).add(record.split)
    overlap = sorted(
        (group, sorted(splits))
        for group, splits in group_splits.items()
        if len(splits) > 1
    )
    if overlap:
        examples = ", ".join(
            f"{group}={splits}" for group, splits in overlap[:10]
        )
        raise ValueError(
            "Capture/session leakage across manifest splits: " + examples
        )


def manifest_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mask_tree_sha256(
    records: Sequence[SampleRecord], data_root: str | Path
) -> str:
    """Hash the exact normalized labels referenced by a manifest.

    The manifest hash alone cannot detect a converter change that rewrites a
    mask at the same path.  Images remain tied to their immutable archive or
    repository receipts; this digest explicitly locks the derived supervision.
    """
    root = Path(data_root).expanduser().resolve()
    paths = sorted({record.mask_path for record in records})
    digest = hashlib.sha256()
    for recorded_path in paths:
        path = Path(recorded_path)
        resolved = path if path.is_absolute() else root / path
        if not resolved.is_file():
            raise FileNotFoundError(f"Missing mask while hashing dataset: {resolved}")
        digest.update(recorded_path.encode("utf-8"))
        digest.update(b"\0")
        with resolved.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()
