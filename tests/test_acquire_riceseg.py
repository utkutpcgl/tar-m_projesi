from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.acquire_riceseg import archive_summary


def test_archive_summary_runs_full_crc_and_counts_files(tmp_path: Path) -> None:
    archive_path = tmp_path / "safe.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("country/site/image.png", b"image")
        archive.writestr("country/site/mask.png", b"mask")

    summary = archive_summary(archive_path, full_crc=True)

    assert summary["files"] == 2
    assert summary["unsafe_paths"] == 0
    assert summary["symlinks"] == 0
    assert summary["full_crc_passed"] is True


def test_archive_summary_rejects_parent_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.txt", b"unsafe")

    with pytest.raises(ValueError, match="Unsafe archive paths"):
        archive_summary(archive_path, full_crc=True)
