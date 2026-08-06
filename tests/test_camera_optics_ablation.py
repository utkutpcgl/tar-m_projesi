from __future__ import annotations

import math

import numpy as np
from PIL import Image

from scripts.build_camera_optics_ablation_v1 import (
    _derive_image,
    _derive_rgb_mask,
    _variant_config,
    zoomed_fov_deg,
)


def _base() -> dict[str, object]:
    return {
        "render": {
            "resolution_x": 512,
            "resolution_y": 512,
            "camera": {"fov_deg": 60.0},
        },
        "field": {"random_seed": 7, "beds": {"x": 1}},
        "agri_asset_profile": {
            "surface_parameters": {
                "environment_strength": 0.8,
                "sun_energy": 1.0,
                "artificial_light_energy": 0.0,
            }
        },
    }


def test_zoom_preserves_geometry_and_increases_image_scale() -> None:
    base = _base()
    result = _variant_config(base, {"optical_zoom": 2.0, "resolution": 512})
    assert result["field"] == base["field"]
    assert result["render"]["camera"]["fov_deg"] < 60.0
    original_span = math.tan(math.radians(60.0) / 2.0)
    zoomed_span = math.tan(
        math.radians(result["render"]["camera"]["fov_deg"]) / 2.0
    )
    assert math.isclose(original_span / zoomed_span, 2.0, rel_tol=1e-5)


def test_resolution_and_light_patch_do_not_mutate_input() -> None:
    base = _base()
    result = _variant_config(
        base,
        {
            "resolution": 1024,
            "environment_strength": 0.3,
            "sun_energy": 0.08,
            "artificial_light_energy": 120.0,
        },
    )
    assert base["render"]["resolution_x"] == 512
    assert result["render"]["resolution_x"] == 1024
    assert result["field"] == base["field"]
    assert (
        result["agri_asset_profile"]["surface_parameters"][
            "artificial_light_energy"
        ]
        == 120.0
    )


def test_zoomed_fov_rejects_invalid_values() -> None:
    for fov, zoom in ((0.0, 1.0), (180.0, 1.0), (60.0, 0.9)):
        try:
            zoomed_fov_deg(fov, zoom)
        except ValueError:
            pass
        else:
            raise AssertionError((fov, zoom))


def test_digital_raster_variants_have_expected_sizes(tmp_path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (512, 512), (20, 80, 140)).save(source)
    direct = tmp_path / "direct.jpg"
    restored = tmp_path / "restored.jpg"
    upscale = tmp_path / "upscale.jpg"
    _derive_image(source, direct, {"resize_to": 256})
    _derive_image(
        source,
        restored,
        {"downsample_to": 256, "resize_to": 512},
    )
    _derive_image(source, upscale, {"resize_to": 1024})
    assert Image.open(direct).size == (256, 256)
    assert Image.open(restored).size == (512, 512)
    assert Image.open(upscale).size == (1024, 1024)


def test_rgb_mask_resize_preserves_palette(tmp_path) -> None:
    source = tmp_path / "mask.png"
    mask = np.zeros((4, 4, 3), dtype=np.uint8)
    mask[:2] = (0, 255, 0)
    mask[2:] = (255, 0, 0)
    Image.fromarray(mask).save(source)
    destination = tmp_path / "resized.png"
    _derive_rgb_mask(source, destination, 7)
    colors = set(map(tuple, np.asarray(Image.open(destination)).reshape(-1, 3)))
    assert colors == {(0, 255, 0), (255, 0, 0)}
