#!/usr/bin/env python3
"""Build a deterministic, blinded EBIS realism verification pack.

The input specification contains matched reference/baseline/candidate images.
The tool never calls a scalar image metric "realism".  It publishes descriptive
pixel statistics, fixed crops, edge views and an aligned baseline/candidate
difference heatmap so a reviewer can score one physical factor at a time.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shutil
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat


AXES = (
    "geometry_silhouette",
    "material_brdf",
    "lighting_shadow",
    "surface_microstructure",
    "camera_sensor",
    "rfid_contact_occlusion",
    "overall_plausibility",
)
RESAMPLING = getattr(Image, "Resampling", Image)

CROPS = {
    "upper_platen": (0.05, 0.00, 0.95, 0.34),
    "concrete": (0.18, 0.10, 0.82, 0.92),
    "lower_platen": (0.04, 0.64, 0.96, 1.00),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=260730)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def fit(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, size, method=RESAMPLING.LANCZOS)


def font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def descriptive_metrics(image: Image.Image) -> dict:
    rgb = image.convert("RGB")
    grey = ImageOps.grayscale(rgb)
    stat = ImageStat.Stat(rgb)
    grey_stat = ImageStat.Stat(grey)
    edges = grey.filter(ImageFilter.FIND_EDGES)
    edge_histogram = edges.histogram()
    edge_pixels = sum(edge_histogram)
    edge_density = (
        sum(edge_histogram[32:]) / edge_pixels if edge_pixels else 0.0
    )
    clipped_dark = sum(grey.histogram()[:5]) / max(1, grey.width * grey.height)
    clipped_bright = sum(grey.histogram()[251:]) / max(1, grey.width * grey.height)
    return {
        "mean_rgb_8bit": [round(value, 4) for value in stat.mean],
        "stddev_rgb_8bit": [round(value, 4) for value in stat.stddev],
        "mean_luma_8bit": round(grey_stat.mean[0], 4),
        "stddev_luma_8bit": round(grey_stat.stddev[0], 4),
        "edge_density_threshold_32": round(edge_density, 6),
        "clipped_dark_fraction": round(clipped_dark, 6),
        "clipped_bright_fraction": round(clipped_bright, 6),
        "interpretation": (
            "descriptive pixels only; these values are not a realism score and "
            "are meaningful only beside blinded visual review"
        ),
    }


def normalized_crop(
    image: Image.Image, bounds: tuple[float, float, float, float]
) -> Image.Image:
    left, top, right, bottom = bounds
    return image.crop(
        (
            round(left * image.width),
            round(top * image.height),
            round(right * image.width),
            round(bottom * image.height),
        )
    )


def difference_heatmap(baseline: Image.Image, candidate: Image.Image) -> Image.Image:
    candidate = fit(candidate, baseline.size)
    difference = ImageChops.difference(baseline, candidate)
    magnitude = ImageOps.grayscale(difference)
    magnitude = ImageOps.autocontrast(magnitude, cutoff=(1.0, 1.0))
    return ImageOps.colorize(magnitude, black="#050816", mid="#e76f00", white="#fff3a3")


def edge_view(image: Image.Image) -> Image.Image:
    grey = ImageOps.grayscale(image)
    return ImageOps.autocontrast(grey.filter(ImageFilter.FIND_EDGES))


def labelled_panel(image: Image.Image, label: str, width: int, height: int) -> Image.Image:
    panel = Image.new("RGB", (width, height + 46), "#11151c")
    panel.paste(fit(image, (width, height)), (0, 46))
    draw = ImageDraw.Draw(panel)
    draw.text((14, 12), label, fill="#f3f5f7", font=font(22))
    return panel


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    args = parse_args()
    spec_path = args.spec.resolve()
    output = args.output.resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    cases = spec.get("cases", [])
    if not cases:
        raise ValueError("spec.cases must contain at least one matched case")

    if output.exists() and not args.overwrite:
        raise FileExistsError(f"Output exists; pass --overwrite explicitly: {output}")
    temporary = output.with_name(f".{output.name}.tmp")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)

    rng = random.Random(args.seed)
    private_mapping = {
        "schema_version": 1,
        "seed": args.seed,
        "warning": "Keep private until the blinded rubric has been completed.",
        "cases": {},
    }
    public_cases = []
    sheet_rows: list[Image.Image] = []

    for case_index, case in enumerate(cases):
        name = str(case["name"])
        paths = {
            role: Path(case[role]).expanduser().resolve()
            for role in ("reference", "baseline", "candidate")
        }
        missing = [str(path) for path in paths.values() if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"{name}: missing images: {missing}")
        images = {role: load_rgb(path) for role, path in paths.items()}
        display_roles = list(images)
        rng.shuffle(display_roles)
        letters = ("A", "B", "C")
        mapping = dict(zip(letters, display_roles))
        private_mapping["cases"][name] = mapping

        case_root = temporary / "cases" / name
        (case_root / "crops").mkdir(parents=True)
        (case_root / "diagnostics").mkdir(parents=True)
        panels = []
        for letter in letters:
            role = mapping[letter]
            source = images[role]
            panels.append(labelled_panel(source, f"{name} — {letter}", 640, 360))
            edge_path = case_root / "diagnostics" / f"{letter}_edges.png"
            edge_view(source).save(edge_path, compress_level=6)
            for crop_name, crop_bounds in CROPS.items():
                crop = normalized_crop(source, crop_bounds)
                crop.save(
                    case_root / "crops" / f"{crop_name}_{letter}.png",
                    compress_level=6,
                )

        row = Image.new("RGB", (640 * 3, 406), "#0c0f14")
        for panel_index, panel in enumerate(panels):
            row.paste(panel, (panel_index * 640, 0))
        sheet_rows.append(row)

        heatmap = difference_heatmap(images["baseline"], images["candidate"])
        heatmap_path = case_root / "diagnostics" / "baseline_candidate_diff_heatmap.png"
        heatmap.save(heatmap_path, compress_level=6)
        metrics = {
            role: descriptive_metrics(image) for role, image in images.items()
        }
        write_json(case_root / "pixel_metrics.json", metrics)
        public_cases.append(
            {
                "name": name,
                "anonymous_options": list(letters),
                "matched_control": case.get("matched_control", {}),
                "changed_factor": case.get("changed_factor", "unspecified"),
                "crop_regions_normalized": CROPS,
                "source_hashes_private_mapping_required": True,
            }
        )

    sheet = Image.new("RGB", (640 * 3, 406 * len(sheet_rows)), "#0c0f14")
    for row_index, row in enumerate(sheet_rows):
        sheet.paste(row, (0, row_index * 406))
    sheet.save(temporary / "BLINDED_CONTACT_SHEET.png", compress_level=6)

    rubric = {
        "schema_version": 1,
        "instructions": (
            "Score A/B/C independently from 1 (implausible) to 5 (closest to a "
            "real EBIS capture). Do not open PRIVATE_MAPPING.json first. Add one "
            "short pixel-grounded reason for every winner."
        ),
        "axes": list(AXES),
        "cases": [
            {
                "name": case["name"],
                "scores": {
                    letter: {axis: None for axis in AXES}
                    for letter in ("A", "B", "C")
                },
                "winner": None,
                "confidence": None,
                "pixel_grounded_reason": None,
            }
            for case in cases
        ],
    }
    write_json(temporary / "RUBRIC.json", rubric)
    write_json(temporary / "PRIVATE_MAPPING.json", private_mapping)
    public_manifest = {
        "schema_version": 1,
        "status": "PASS",
        "spec": spec_path.name,
        "spec_sha256": sha256(spec_path),
        "script_sha256": sha256(Path(__file__).resolve()),
        "seed": args.seed,
        "case_count": len(cases),
        "cases": public_cases,
        "method": {
            "blind_order": "deterministic A/B/C shuffle; mapping held separately",
            "single_factor_requirement": (
                "baseline and candidate must share engine, seed, camera, shape, "
                "geometry and lighting except the declared changed_factor"
            ),
            "diagnostics": [
                "fixed upper-platen/concrete/lower-platen crops",
                "edge views",
                "aligned baseline/candidate difference heatmap",
                "descriptive pixel statistics",
            ],
            "claim_boundary": (
                "visual ranking can select a renderer revision; only a frozen "
                "real holdout can support a YOLO-benefit claim"
            ),
        },
    }
    write_json(temporary / "MANIFEST.json", public_manifest)

    if output.exists():
        shutil.rmtree(output)
    os.replace(temporary, output)
    print(f"EBIS_REALISM_PACK_OK cases={len(cases)} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
