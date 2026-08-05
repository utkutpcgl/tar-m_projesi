from pathlib import Path

import numpy as np

from agri_seg.manifest import SampleRecord
from scripts.build_riceseg_contact_sheet import (
    COMMON_COLORS,
    SOURCE_COLORS,
    SampleStats,
    colorize,
    select_subdataset,
)


def _record(index: int) -> SampleRecord:
    return SampleRecord(
        sample_id=f"riceseg:JS_1:{index:03d}",
        image_path=f"image_{index}.jpg",
        mask_path=f"mask_{index}.png",
        split="train",
        dataset_id="riceseg",
        field_id="china_jiangsu_njau",
        session_id="jiangsu_njau_2020",
        capture_date="2020",
        platform="handheld_rod",
        sensor="SONY_RX0_RGB",
        target_crop_id=12,
        crop_species="Oryza sativa",
        weed_species_optional="weed;duckweed",
        growth_stage="vegetative",
        annotation_exhaustive=True,
        license_status="research-only",
        commercial_allowed=False,
    )


def test_class_aware_selection_is_distinct_and_deterministic(tmp_path: Path) -> None:
    values = [
        SampleStats(
            record=_record(index),
            source_mask=tmp_path / f"source_{index}.png",
            common_mask=tmp_path / f"common_{index}.png",
            vegetation_fraction=index / 100.0,
            weed_fraction=(99 - index) / 200.0,
            rice_organ_fraction=abs(50 - index) / 100.0,
        )
        for index in range(100)
    ]

    selected = select_subdataset(values)

    assert list(selected) == [
        "low_vegetation_q10",
        "median_vegetation_q50",
        "high_vegetation_q90",
        "weed_rich",
        "rice_organ_rich",
    ]
    assert len({item.record.sample_id for item in selected.values()}) == 5
    assert selected["low_vegetation_q10"].vegetation_fraction == 0.10
    assert selected["median_vegetation_q50"].vegetation_fraction == 0.50
    assert selected["high_vegetation_q90"].vegetation_fraction == 0.89
    assert selected["weed_rich"].weed_fraction == 0.495


def test_source_and_common_color_tables_cover_all_labels() -> None:
    source = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.uint8)
    common = np.array([[0, 1, 2]], dtype=np.uint8)

    source_image = colorize(source, SOURCE_COLORS)
    common_image = colorize(common, COMMON_COLORS)

    assert source_image.size == (3, 2)
    assert common_image.size == (3, 1)
