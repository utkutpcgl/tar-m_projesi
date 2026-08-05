import io
import json
import tarfile
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import pytest
from PIL import Image

import agri_seg.prepare as prepare_module
from agri_seg.constants import CROP, IGNORE, WEED
from agri_seg.prepare import (
    _ROSE_V2_BIPBIP_HARICOT_MISSING_MASKS,
    _ROSE_V2_BIPBIP_HARICOT_ORPHAN_MASKS,
    _rasterize_acre_xml,
    convert_cropandweed,
    convert_cwfid,
    convert_rice_seedling_weed,
    convert_rose,
    convert_sorghum_weed,
    convert_we3ds,
    safe_extract_tar,
    safe_extract_rar,
    safe_extract_zip,
)
from agri_seg.manifest import read_manifest


def test_safe_extract_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.txt", "no")
    with pytest.raises(ValueError, match="Unsafe"):
        safe_extract_zip(archive, tmp_path / "output")


def test_safe_tar_extract_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, "w") as bundle:
        payload = b"no"
        member = tarfile.TarInfo("../escape.txt")
        member.size = len(payload)
        bundle.addfile(member, io.BytesIO(payload))
    with pytest.raises(ValueError, match="Unsafe"):
        safe_extract_tar(archive, tmp_path / "output")


def test_safe_rar_extracts_regular_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import libarchive

    class FakeEntry:
        pathname = "nested/example.txt"
        size = 2
        isfile = True
        isdir = False
        issym = False
        islnk = False

        @staticmethod
        def get_blocks() -> list[bytes]:
            return [b"ok"]

    class FakeReader:
        def __enter__(self) -> list[FakeEntry]:
            return [FakeEntry()]

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(libarchive, "file_reader", lambda _: FakeReader())
    archive = tmp_path / "safe.rar"
    archive.write_bytes(b"placeholder")
    destination = tmp_path / "output"
    safe_extract_rar(archive, destination, max_uncompressed_bytes=1024)
    assert (destination / "nested/example.txt").read_bytes() == b"ok"


def test_rice_seedling_weed_conversion_ignores_raw_zero_and_is_train_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "raw/rice_seedling_weed/repository"
    image_root = source / "image"
    mask_root = source / "PixelLabelData"
    image_root.mkdir(parents=True)
    mask_root.mkdir(parents=True)
    masks = {
        1: np.array([[0, 1, 2, 3]], dtype=np.uint8),
        2: np.array([[2, 2, 1, 3]], dtype=np.uint8),
    }
    for index, mask in masks.items():
        Image.new("RGB", (4, 1)).save(image_root / f"image_{index}.jpg")
        Image.fromarray(mask).save(mask_root / f"Label_{index}.png")

    monkeypatch.setattr(prepare_module, "_RICE_SEEDLING_WEED_SOURCE_TILES", 2)
    monkeypatch.setattr(
        prepare_module, "_RICE_SEEDLING_WEED_IMAGE_SIZE", (4, 1)
    )
    monkeypatch.setattr(
        prepare_module,
        "_RICE_SEEDLING_WEED_EXPECTED_RAW_PIXEL_COUNTS",
        {0: 1, 1: 2, 2: 3, 3: 2},
    )

    manifest = convert_rice_seedling_weed(tmp_path)
    records = read_manifest(manifest)

    assert len(records) == 2
    assert all(record.split == "train" for record in records)
    assert all(record.target_crop_id == 12 for record in records)
    assert all(not record.annotation_exhaustive for record in records)
    assert all(record.commercial_allowed for record in records)
    common = np.asarray(
        Image.open(
            tmp_path
            / "processed/rice_seedling_weed/common_masks/train/001.png"
        )
    )
    assert common.tolist() == [[IGNORE, CROP, 0, WEED]]
    report = json.loads(
        (tmp_path / "processed/manifests/rice_seedling_weed_conversion.json")
        .read_text(encoding="utf-8")
    )
    assert report["policy"]["raw_0"] == "ignore_unlabeled_boundary"
    assert report["policy"]["evaluation"].startswith("never_use")


def test_cwfid_conversion_preserves_untyped_vegetation_as_ignore(
    tmp_path: Path,
) -> None:
    source = tmp_path / "raw/cwfid/repository"
    for folder in ("images", "masks", "annotations"):
        (source / folder).mkdir(parents=True, exist_ok=True)
    (source / "train_test_split.yaml").write_text(
        "train: [1]\ntest: []\n", encoding="utf-8"
    )
    Image.new("RGB", (3, 1)).save(source / "images/001_image.png")
    Image.fromarray(np.array([[255, 0, 0]], dtype=np.uint8)).save(
        source / "masks/001_mask.png"
    )
    annotation = np.array([[[0, 0, 0], [0, 255, 0], [0, 0, 0]]], dtype=np.uint8)
    Image.fromarray(annotation).save(
        source / "annotations/001_annotation.png"
    )
    manifest = convert_cwfid(tmp_path)
    assert manifest.is_file()
    common = np.asarray(
        Image.open(tmp_path / "processed/cwfid/common_masks/001.png")
    )
    assert common.tolist() == [[0, 1, IGNORE]]


def test_acre_unknown_and_untrusted_polygons_are_ignored(
    tmp_path: Path,
) -> None:
    xml = tmp_path / "sample.xml"
    xml.write_text(
        """
        <annotation>
          <size><width>10</width><height>10</height></size>
          <data><clippings>
            <clipping>
              <class>crop</class>
              <trusted><isTrusted>true</isTrusted></trusted>
              <points>
                <point x="1" y="1"/><point x="3" y="1"/><point x="3" y="3"/>
              </points>
            </clipping>
            <clipping>
              <class>weed</class><plant_name>Chenopodium</plant_name>
              <trusted><isTrusted>true</isTrusted></trusted>
              <points>
                <point x="5" y="1"/><point x="7" y="1"/><point x="7" y="3"/>
              </points>
            </clipping>
            <clipping>
              <class>unknow</class>
              <points>
                <point x="1" y="6"/><point x="3" y="6"/><point x="3" y="8"/>
              </points>
            </clipping>
            <clipping>
              <class>weed</class>
              <trusted><isTrusted>false</isTrusted></trusted>
              <points>
                <point x="6" y="6"/><point x="8" y="6"/><point x="8" y="8"/>
              </points>
            </clipping>
          </clippings></data>
        </annotation>
        """,
        encoding="utf-8",
    )
    mask, species = _rasterize_acre_xml(xml, (10, 10))
    assert mask[2, 2] == CROP
    assert mask[2, 6] == WEED
    assert mask[7, 2] == IGNORE
    assert mask[7, 7] == IGNORE
    assert species == {"Chenopodium"}


def test_rose_conversion_maps_colors_and_holds_out_robot(tmp_path: Path) -> None:
    source = (
        tmp_path
        / "raw/rose/repository/Dataset/2019/Weedelec/Haricot"
    )
    image_root = source / "Images"
    mask_root = source / "Masks"
    image_root.mkdir(parents=True)
    mask_root.mkdir(parents=True)
    Image.new("RGB", (4, 1)).save(image_root / "frame.jpg")
    raw = np.array(
        [
            [
                [0, 0, 0],
                [254, 124, 18],
                [255, 255, 255],
                [216, 67, 82],
            ]
        ],
        dtype=np.uint8,
    )
    Image.fromarray(raw).save(mask_root / "frame.png")

    manifest = convert_rose(tmp_path)
    records = read_manifest(manifest)

    assert len(records) == 1
    assert records[0].split == "val"
    assert records[0].target_crop_id == 2
    assert records[0].crop_species == "Phaseolus vulgaris"
    assert not records[0].commercial_allowed
    common = np.asarray(
        Image.open(
            tmp_path
            / "processed/rose/common_masks/val/2019/weedelec/haricot/frame.png"
        )
    )
    assert common.tolist() == [[0, WEED, CROP, WEED]]


def test_rose_conversion_reports_only_known_v2_pairing_anomaly(
    tmp_path: Path,
) -> None:
    source = (
        tmp_path
        / "raw/rose/repository/Dataset/2019/Bipbip/Haricot"
    )
    image_root = source / "Images"
    mask_root = source / "Masks"
    image_root.mkdir(parents=True)
    mask_root.mkdir(parents=True)
    for stem in sorted(
        _ROSE_V2_BIPBIP_HARICOT_MISSING_MASKS | {"paired"}
    ):
        Image.new("RGB", (1, 1)).save(image_root / f"{stem}.jpg")
    for stem in sorted(
        _ROSE_V2_BIPBIP_HARICOT_ORPHAN_MASKS | {"paired"}
    ):
        Image.new("RGB", (1, 1)).save(mask_root / f"{stem}.png")

    manifest = convert_rose(tmp_path)
    records = read_manifest(manifest)
    report = json.loads(
        (tmp_path / "processed/manifests/rose_conversion.json").read_text()
    )

    assert [record.sample_id for record in records] == [
        "rose:2019_bipbip_haricot:paired"
    ]
    assert report["source_images"] == 16
    assert report["source_masks"] == 16
    assert report["included_samples"] == 1
    assert set(report["excluded_missing_masks"]) == {
        f"2019/Bipbip/Haricot/{stem}"
        for stem in _ROSE_V2_BIPBIP_HARICOT_MISSING_MASKS
    }
    assert set(report["excluded_orphan_masks"]) == {
        f"2019/Bipbip/Haricot/{stem}"
        for stem in _ROSE_V2_BIPBIP_HARICOT_ORPHAN_MASKS
    }
    assert report["split_counts"] == {"train": 1, "val": 0, "test": 0}


def test_rose_conversion_rejects_unknown_pairing_mismatch(
    tmp_path: Path,
) -> None:
    source = (
        tmp_path
        / "raw/rose/repository/Dataset/2019/Pead/Mais"
    )
    image_root = source / "Images"
    mask_root = source / "Masks"
    image_root.mkdir(parents=True)
    mask_root.mkdir(parents=True)
    Image.new("RGB", (1, 1)).save(image_root / "missing.jpg")
    Image.new("RGB", (1, 1)).save(mask_root / "orphan.png")

    with pytest.raises(ValueError, match="pairing mismatch"):
        convert_rose(tmp_path)


def test_we3ds_conversion_maps_species_and_uses_date_disjoint_split(
    tmp_path: Path,
) -> None:
    source = tmp_path / "raw/we3ds/WE3DS"
    image_root = source / "images"
    mask_root = source / "annotations/segmentation/SegmentationLabel"
    image_root.mkdir(parents=True)
    mask_root.mkdir(parents=True)
    Image.new("RGB", (4, 1)).save(image_root / "img_00000.png")
    raw = np.array([[1, 2, 3, 0]], dtype=np.uint8)
    Image.fromarray(raw).save(mask_root / "img_00000.png")
    (source / "info.csv").write_text(
        "dst_filename;date;seeding_date;height_mm\n"
        "img_00000.png;10.08.2020;01.08.2020;900\n",
        encoding="utf-8",
    )

    manifest = convert_we3ds(tmp_path)
    records = read_manifest(manifest)
    assert len(records) == 1
    assert records[0].split == "val"
    assert records[0].target_crop_id == 5
    assert records[0].crop_species == "Vicia faba"
    assert records[0].growth_stage == "days_after_seeding_9"
    common = np.asarray(
        Image.open(
            tmp_path
            / "processed/we3ds/common_masks/val/img_00000.png"
        )
    )
    assert common.tolist() == [[0, CROP, WEED, IGNORE]]


def test_we3ds_conversion_reports_ambiguous_target_exclusions(
    tmp_path: Path,
) -> None:
    source = tmp_path / "raw/we3ds/WE3DS"
    image_root = source / "images"
    mask_root = source / "annotations/segmentation/SegmentationLabel"
    image_root.mkdir(parents=True)
    mask_root.mkdir(parents=True)
    masks = {
        "img_00000.png": np.array([[1, 2, 3]], dtype=np.uint8),
        "img_00001.png": np.array([[1, 3, 4]], dtype=np.uint8),
        "img_00002.png": np.array([[2, 5, 3]], dtype=np.uint8),
    }
    for filename, mask in masks.items():
        Image.new("RGB", (3, 1)).save(image_root / filename)
        Image.fromarray(mask).save(mask_root / filename)
    (source / "info.csv").write_text(
        "dst_filename;date;seeding_date\n"
        "img_00000.png;10.08.2020;01.08.2020\n"
        "img_00001.png;10.08.2020;01.08.2020\n"
        "img_00002.png;10.08.2020;01.08.2020\n",
        encoding="utf-8",
    )

    manifest = convert_we3ds(tmp_path)

    assert [record.sample_id for record in read_manifest(manifest)] == [
        "we3ds:img_00000"
    ]
    report = json.loads(
        (tmp_path / "processed/manifests/we3ds_conversion.json").read_text(
            encoding="utf-8"
        )
    )
    assert report["source_images"] == 3
    assert report["included_samples"] == 1
    assert report["excluded_no_target_crop"] == ["img_00001"]
    assert report["excluded_multiple_target_crops"] == ["img_00002"]


def test_cropandweed_conversion_is_target_and_session_fail_closed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "raw/cropandweed/repository"
    image_root = source / "images"
    mask_root = source / "labelIds/CropAndWeed"
    bbox_root = source / "bboxes"
    params_root = source / "params"
    for directory in (image_root, mask_root, bbox_root, params_root):
        directory.mkdir(parents=True)
    masks = {
        "ave-0001-0001": np.array([[0, 1, 31, 255]], dtype=np.uint8),
        "ave-0002-0001": np.array([[0, 7, 14, 31]], dtype=np.uint8),
        "vwg-0003-0001": np.array([[0, 1, 7, 31]], dtype=np.uint8),
        "vwg-0004-0001": np.array([[0, 31, 255, 0]], dtype=np.uint8),
    }
    for stem, mask in masks.items():
        Image.new("RGB", (4, 1)).save(image_root / f"{stem}.jpg")
        Image.fromarray(mask).save(mask_root / f"{stem}.png")
        labels = sorted(set(mask.reshape(-1).tolist()) - {0})
        (bbox_root / f"{stem}.csv").write_text(
            "".join(f"0,0,1,1,{label},0,0\n" for label in labels),
            encoding="utf-8",
        )
        (params_root / f"{stem}.csv").write_text(
            "moisture,soil,lighting,separability\n0,0,1,0\n",
            encoding="utf-8",
        )
    gate = tmp_path / "cropandweed_gate.yaml"
    gate.write_text(
        "dataset_id: cropandweed\n"
        "external_calibration_sessions: [ave-0002]\n"
        "expected_counts:\n"
        "  source_images: 4\n"
        "  included_samples: 2\n"
        "  excluded_no_target_crop: 1\n"
        "  excluded_multiple_target_crops: 1\n"
        "  bbox_semantic_labelset_mismatches: 0\n",
        encoding="utf-8",
    )

    manifest = convert_cropandweed(tmp_path, gate)
    records = read_manifest(manifest)
    assert [(record.sample_id, record.split) for record in records] == [
        ("cropandweed:ave-0001-0001", "train"),
        ("cropandweed:ave-0002-0001", "external_calibration"),
    ]
    assert [record.target_crop_id for record in records] == [3, 0]
    assert all(not record.commercial_allowed for record in records)
    train_mask = np.asarray(
        Image.open(
            tmp_path
            / "processed/cropandweed/common_masks/train/ave-0001-0001.png"
        )
    )
    calibration_mask = np.asarray(
        Image.open(
            tmp_path
            / "processed/cropandweed/common_masks/external_calibration/ave-0002-0001.png"
        )
    )
    assert train_mask.tolist() == [[0, CROP, WEED, IGNORE]]
    assert calibration_mask.tolist() == [[0, CROP, IGNORE, WEED]]
    report = json.loads(
        (tmp_path / "processed/manifests/cropandweed_conversion.json").read_text()
    )
    assert report["included_samples"] == 2
    assert report["split_counts"] == {"external_calibration": 1, "train": 1}
    assert report["ignored_label_image_counts"] == {"14": 1}


def test_sorghum_weed_conversion_uses_via_classes_and_official_roles(
    tmp_path: Path,
) -> None:
    source = (
        tmp_path
        / "raw/sorghum_weed/repository/SorghumWeedDataset_Segmentation"
    )
    classes = ("Sorghum", "Grass", "BLweed")
    for source_split in ("Train", "Validate", "Test"):
        split_root = source / source_split
        split_root.mkdir(parents=True)
        filename = f"{source_split}SorghumWeed (1).JPG"
        Image.new("RGB", (7, 3)).save(split_root / filename)
        regions = []
        for index, class_name in enumerate(classes):
            regions.append(
                {
                    "shape_attributes": {
                        "name": "polygon",
                        "all_points_x": [index * 2, index * 2 + 1, index * 2],
                        "all_points_y": [0, 0, 1],
                    },
                    "region_attributes": {"classname": class_name},
                }
            )
        payload = {
            f"{filename}123": {
                "filename": filename,
                "size": 123,
                "regions": regions,
                "file_attributes": {},
            }
        }
        (split_root / f"{source_split}SorghumWeed_json.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    manifest = convert_sorghum_weed(tmp_path)
    records = read_manifest(manifest)
    assert [record.split for record in records] == [
        "train",
        "external_calibration",
        "external_test",
    ]
    assert all(record.target_crop_id == 4 for record in records)
    mask = np.asarray(
        Image.open(
            tmp_path
            / "processed/sorghum_weed/common_masks/train/TrainSorghumWeed (1).png"
        )
    )
    assert mask[0, 0] == CROP
    assert mask[0, 2] == WEED
    assert mask[0, 4] == WEED
