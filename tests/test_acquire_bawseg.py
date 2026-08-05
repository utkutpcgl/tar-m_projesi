import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from scripts.acquire_bawseg import (
    discover_archive_url,
    inspect_archive,
    load_gate,
    parse_checksums,
    safe_member_name,
)


def test_safe_member_name_rejects_parent_traversal() -> None:
    with pytest.raises(ValueError, match="Unsafe ZIP member"):
        safe_member_name("../escape.txt")


def test_parse_checksums_requires_sha256_and_safe_paths() -> None:
    digest = "a" * 64
    assert parse_checksums(f"{digest}  data/file.tif\n".encode()) == {
        "data/file.tif": digest
    }
    with pytest.raises(ValueError, match="Malformed"):
        parse_checksums(b"not-a-checksum  file\n")


def test_discover_archive_url_ignores_subscription_placeholder() -> None:
    gate = {
        "source": {"archive_display_name": "Multispectral Image Benchmark Dataset.zip"}
    }
    placeholder = (
        '<a href="#">Multispectral Image Benchmark Dataset.zip</a>'
    )
    assert discover_archive_url(placeholder, gate) is None
    direct = (
        '<a href="/secure/archive.zip">Multispectral Image Benchmark Dataset.zip</a>'
    )
    assert discover_archive_url(direct, gate) == "/secure/archive.zip"


def test_public_page_contract_snippets_are_strings() -> None:
    gate = load_gate(Path("configs/data/bawseg_acquisition_v1.yaml"))
    snippets = gate["public_page_gate"]["required_snippets"]
    assert snippets
    assert all(isinstance(snippet, str) for snippet in snippets)


def _archive_gate(tmp_path: Path) -> tuple[dict, Path, Path]:
    data_root = tmp_path / "data"
    archive_path = data_root / "raw" / "bawseg" / "archives" / "dataset.zip"
    archive_path.parent.mkdir(parents=True)
    config_path = tmp_path / "gate.yaml"
    config_path.write_text("schema_version: 1\n", encoding="utf-8")
    gate = {
        "data_root": str(data_root),
        "outputs": {
            "archive": "raw/bawseg/archives/dataset.zip",
            "archive_inspection_receipt": "processed/audits/inspect.json",
            "acquisition_receipt": "processed/audits/verify.json",
        },
        "archive_gate": {
            "maximum_download_bytes": 1024 * 1024,
            "minimum_free_space_after_extraction_bytes": 0,
            "required_control_files": [
                "README_DATASET.txt",
                "LICENSE.txt",
                "manifest.csv",
                "checksums_sha256.txt",
            ],
            "manifest_required_columns": [
                "relative_path",
                "bytes",
                "sha256",
                "year",
                "field",
                "product_type",
            ],
            "max_control_file_bytes": 1024 * 1024,
        },
    }
    return gate, config_path, archive_path


def _write_fixture_archive(path: Path, *, declared_bytes: int = 7) -> None:
    payload = b"pixels!"
    digest = hashlib.sha256(payload).hexdigest()
    manifest = (
        "relative_path,bytes,sha256,year,field,product_type\n"
        f"patches_256/sample.tif,{declared_bytes},{digest},2023,E8,rgb\n"
    )
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("BAWSeg/README_DATASET.txt", "fixture\n")
        archive.writestr("BAWSeg/LICENSE.txt", "review me\n")
        archive.writestr("BAWSeg/manifest.csv", manifest)
        archive.writestr(
            "BAWSeg/checksums_sha256.txt",
            f"{digest}  patches_256/sample.tif\n",
        )
        archive.writestr("BAWSeg/patches_256/sample.tif", payload)


def test_inspect_archive_verifies_crc_internal_sha_and_manifest(tmp_path: Path) -> None:
    gate, config_path, archive_path = _archive_gate(tmp_path)
    _write_fixture_archive(archive_path)
    receipt_path = inspect_archive(gate, config_path, full_verify=True)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "verified"
    assert receipt["full_crc_passed"] is True
    assert receipt["internal_sha256_passed"] is True
    assert receipt["extraction_authorized"] is True
    assert receipt["training_authorized"] is False


def test_inspect_archive_rejects_manifest_byte_mismatch(tmp_path: Path) -> None:
    gate, config_path, archive_path = _archive_gate(tmp_path)
    _write_fixture_archive(archive_path, declared_bytes=8)
    with pytest.raises(ValueError, match="Manifest byte mismatch"):
        inspect_archive(gate, config_path, full_verify=False)
