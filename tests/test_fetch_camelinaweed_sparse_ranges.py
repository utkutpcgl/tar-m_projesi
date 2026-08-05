from __future__ import annotations

import importlib.util
from pathlib import Path
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fetch_camelinaweed_sparse_ranges.py"
SPEC = importlib.util.spec_from_file_location("fetch_camelinaweed_sparse_ranges", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_selects_only_annotated_metadata_or_rgb(tmp_path: Path) -> None:
    archive_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("root/Flight/Annotated/a.jpg", b"rgb")
        archive.writestr("root/Flight/Annotated/_annotations.coco.json", b"{}")
        archive.writestr("root/Flight/Unannotated/b.jpg", b"other")
        archive.writestr("root/Flight/Annotated/note.xml", b"skip")
    with zipfile.ZipFile(archive_path) as archive:
        metadata = MODULE.selected_members(archive, "metadata")
        annotated = MODULE.selected_members(archive, "annotated")
        assert [item.filename for item in metadata] == [
            "root/Flight/Annotated/_annotations.coco.json"
        ]
        assert {item.filename for item in annotated} == {
            "root/Flight/Annotated/a.jpg",
            "root/Flight/Annotated/_annotations.coco.json",
        }
        intervals = MODULE.member_record_intervals(archive, annotated)
        assert intervals
        assert all(end > start for start, end in intervals)


def test_splits_combined_ranges_at_part_boundaries() -> None:
    chunks = MODULE.split_intervals_by_parts([(8, 25)], [10, 10, 10])
    assert chunks == [
        {
            "part_index": 0,
            "global_start": 8,
            "global_end": 10,
            "part_start": 8,
            "part_end": 10,
        },
        {
            "part_index": 1,
            "global_start": 10,
            "global_end": 20,
            "part_start": 0,
            "part_end": 10,
        },
        {
            "part_index": 2,
            "global_start": 20,
            "global_end": 25,
            "part_start": 0,
            "part_end": 5,
        },
    ]
