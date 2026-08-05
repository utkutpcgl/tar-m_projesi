import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
import yaml

from scripts.audit_weedy_rice_uav_archive import audit, sha256


def test_nested_archive_audit_extracts_and_receipts(tmp_path: Path) -> None:
    nested_buffer = io.BytesIO()
    with ZipFile(nested_buffer, "w", compression=ZIP_DEFLATED) as nested:
        nested.writestr("RGB/sample.png", b"rgb")
        nested.writestr("Masks/sample.png", b"mask")
    nested_payload = nested_buffer.getvalue()

    outer_path = tmp_path / "raw/source/outer.zip"
    outer_path.parent.mkdir(parents=True)
    member_name = "release/inner.zip"
    with ZipFile(outer_path, "w", compression=ZIP_DEFLATED) as outer:
        outer.writestr(member_name, nested_payload)
    with ZipFile(outer_path) as outer:
        info = outer.getinfo(member_name)
        outer_summary = {
            "members": len(outer.infolist()),
            "files": sum(not item.is_dir() for item in outer.infolist()),
            "compressed_bytes": sum(item.compress_size for item in outer.infolist()),
            "uncompressed_bytes": sum(item.file_size for item in outer.infolist()),
        }

    gate = {
        "schema_version": 1,
        "data_root": str(tmp_path),
        "source": {"dataset_id": "test", "license": "CC0"},
        "outer_archive": {
            "path": "raw/source/outer.zip",
            "size_bytes": outer_path.stat().st_size,
            "etag": "test",
            "exact_member": member_name,
            "exact_member_size_bytes": info.file_size,
            **outer_summary,
        },
        "quality_gate": {
            "require_full_nested_crc": True,
            "minimum_free_space_after_archive_and_nested_bytes": 0,
            "external_test_used": False,
            "model_selection_used": False,
        },
        "outputs": {
            "nested_archive": "raw/source/inner.zip",
            "acquisition_receipt": "processed/audits/receipt.json",
        },
    }
    config_path = tmp_path / "gate.yaml"
    config_path.write_text(yaml.safe_dump(gate), encoding="utf-8")

    receipt_path = audit(config_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))

    nested_path = tmp_path / "raw/source/inner.zip"
    assert receipt["status"] == "verified"
    assert receipt["outer_archive"]["full_crc_passed"] is True
    assert receipt["nested_archive"]["full_crc_passed"] is True
    assert receipt["nested_archive"]["sha256"] == sha256(nested_path)
    assert receipt["nested_archive"]["summary"]["files"] == 2


def test_existing_same_size_nested_archive_must_match_outer_member(
    tmp_path: Path,
) -> None:
    expected_buffer = io.BytesIO()
    with ZipFile(expected_buffer, "w", compression=ZIP_STORED) as nested:
        nested.writestr("RGB/sample.bin", b"expected")
    expected_payload = expected_buffer.getvalue()

    outer_path = tmp_path / "raw/source/outer.zip"
    outer_path.parent.mkdir(parents=True)
    member_name = "release/inner.zip"
    with ZipFile(outer_path, "w", compression=ZIP_STORED) as outer:
        outer.writestr(member_name, expected_payload)
    with ZipFile(outer_path) as outer:
        info = outer.getinfo(member_name)
        outer_summary = {
            "members": len(outer.infolist()),
            "files": sum(not item.is_dir() for item in outer.infolist()),
            "compressed_bytes": sum(item.compress_size for item in outer.infolist()),
            "uncompressed_bytes": sum(item.file_size for item in outer.infolist()),
        }

    replacement_buffer = io.BytesIO()
    with ZipFile(replacement_buffer, "w", compression=ZIP_STORED) as nested:
        nested.writestr("RGB/sample.bin", b"tampered")
    replacement_payload = replacement_buffer.getvalue()
    assert len(replacement_payload) == len(expected_payload)
    nested_path = tmp_path / "raw/source/inner.zip"
    nested_path.write_bytes(replacement_payload)

    gate = {
        "schema_version": 1,
        "data_root": str(tmp_path),
        "source": {"dataset_id": "test", "license": "CC0"},
        "outer_archive": {
            "path": "raw/source/outer.zip",
            "size_bytes": outer_path.stat().st_size,
            "etag": "test",
            "exact_member": member_name,
            "exact_member_size_bytes": info.file_size,
            **outer_summary,
        },
        "quality_gate": {
            "require_full_nested_crc": True,
            "minimum_free_space_after_archive_and_nested_bytes": 0,
            "external_test_used": False,
            "model_selection_used": False,
        },
        "outputs": {
            "nested_archive": "raw/source/inner.zip",
            "acquisition_receipt": "processed/audits/receipt.json",
        },
    }
    config_path = tmp_path / "gate.yaml"
    config_path.write_text(yaml.safe_dump(gate), encoding="utf-8")

    with pytest.raises(ValueError, match="existing nested archive SHA-256"):
        audit(config_path)
