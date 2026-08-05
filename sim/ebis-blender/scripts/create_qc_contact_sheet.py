#!/usr/bin/env python3
"""Create a deterministic visual-QC contact sheet for an EBIS dataset.

Expected dataset layout::

    ROOT/images/<sample>.(png|jpg|jpeg|...)                  # legacy
    ROOT/partitions/<policy>/images/<sample>.(png|jpg|...) # v2
    ROOT/metadata/<sample>.json       # optional
    ROOT/labels/<sample>.txt          # optional YOLO boxes

When a YOLO label file is absent, boxes in ``metadata.visible_annotations``
are used when available.  An existing but empty label file is respected: it
means the sample has no visible labelled objects.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError as exc:  # pragma: no cover - depends on host environment
    raise SystemExit(
        "Pillow is required. Install it with: python3 -m pip install Pillow"
    ) from exc


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
OUTPUT_SUFFIXES = {".png", ".jpg", ".jpeg"}
CLASS_NAMES = {0: "rfid", 1: "concrete"}
CLASS_COLORS = (
    (255, 78, 168),
    (42, 210, 236),
    (255, 190, 54),
    (104, 224, 122),
    (165, 120, 255),
    (255, 112, 84),
)
ANNOTATION_CLASS_IDS = {"rfid_tag": 0, "concrete_sample": 1}

PANEL_WIDTH = 384
PANEL_HEIGHT = 216
CAPTION_HEIGHT = 48
GAP = 10
MARGIN = 12
HEADER_HEIGHT = 34


class QCError(RuntimeError):
    """Raised for actionable dataset or annotation errors."""


@dataclass(frozen=True)
class YoloBox:
    class_id: int
    center_x: float
    center_y: float
    width: float
    height: float


@dataclass(frozen=True)
class Sample:
    image_path: Path
    metadata: dict[str, Any] | None
    boxes: tuple[YoloBox, ...]
    box_source: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an EBIS QC contact sheet with YOLO boxes and scenario captions."
    )
    parser.add_argument("--dataset", required=True, type=Path, help="Dataset root containing images/")
    parser.add_argument("--output", required=True, type=Path, help="Output .png, .jpg or .jpeg path")
    parser.add_argument("--columns", type=int, default=4, help="Tile columns (default: 4)")
    parser.add_argument(
        "--limit",
        type=int,
        default=24,
        help="Maximum lexicographically sorted images; 0 means all (default: 24)",
    )
    args = parser.parse_args(argv)
    if args.columns < 1:
        parser.error("--columns must be at least 1")
    if args.limit < 0:
        parser.error("--limit must be 0 or greater")
    if args.output.suffix.lower() not in OUTPUT_SUFFIXES:
        parser.error("--output must end in .png, .jpg or .jpeg")
    return args


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QCError(f"Could not read metadata {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise QCError(f"Metadata must contain a JSON object: {path}")
    return value


def validate_box(values: Iterable[Any], class_id: int, source: str) -> YoloBox:
    try:
        values_list = list(values)
    except TypeError as exc:
        raise QCError(f"YOLO coordinates must be a four-item sequence in {source}") from exc
    if len(values_list) != 4:
        raise QCError(f"Expected four YOLO coordinates in {source}; got {len(values_list)}")
    try:
        center_x, center_y, width, height = (float(value) for value in values_list)
    except (TypeError, ValueError) as exc:
        raise QCError(f"Non-numeric YOLO coordinate in {source}") from exc
    numbers = (center_x, center_y, width, height)
    if not all(math.isfinite(value) for value in numbers):
        raise QCError(f"Non-finite YOLO coordinate in {source}")
    if width <= 0.0 or height <= 0.0:
        raise QCError(f"YOLO width and height must be positive in {source}")
    if not (0.0 <= center_x <= 1.0 and 0.0 <= center_y <= 1.0):
        raise QCError(f"YOLO box centre must be normalized to [0, 1] in {source}")
    if center_x + width / 2.0 <= 0.0 or center_x - width / 2.0 >= 1.0:
        raise QCError(f"YOLO box lies outside the image horizontally in {source}")
    if center_y + height / 2.0 <= 0.0 or center_y - height / 2.0 >= 1.0:
        raise QCError(f"YOLO box lies outside the image vertically in {source}")
    return YoloBox(class_id, center_x, center_y, width, height)


def load_yolo_boxes(path: Path) -> tuple[YoloBox, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise QCError(f"Could not read YOLO labels {path}: {exc}") from exc

    boxes: list[YoloBox] = []
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        source = f"{path}:{line_number}"
        if len(fields) != 5:
            raise QCError(f"Expected 'class cx cy width height' in {source}; got {len(fields)} fields")
        try:
            parsed_class = float(fields[0])
        except ValueError as exc:
            raise QCError(f"Invalid class id in {source}: {fields[0]!r}") from exc
        if not parsed_class.is_integer() or parsed_class < 0:
            raise QCError(f"Class id must be a non-negative integer in {source}")
        boxes.append(validate_box(fields[1:], int(parsed_class), source))
    return tuple(boxes)


def metadata_boxes(metadata: dict[str, Any], path: Path) -> tuple[YoloBox, ...]:
    annotations = metadata.get("visible_annotations")
    if annotations is None:
        return ()
    if not isinstance(annotations, dict):
        raise QCError(f"visible_annotations must be an object in {path}")

    boxes: list[YoloBox] = []
    for name in sorted(annotations):
        annotation = annotations[name]
        if name not in ANNOTATION_CLASS_IDS or not isinstance(annotation, dict):
            continue
        yolo = annotation.get("yolo")
        if yolo is None:
            continue
        boxes.append(
            validate_box(yolo, ANNOTATION_CLASS_IDS[name], f"{path}:visible_annotations.{name}.yolo")
        )
    return tuple(boxes)


def discover_samples(dataset: Path, output: Path, limit: int) -> list[Sample]:
    if not dataset.is_dir():
        raise QCError(f"Dataset root is not a directory: {dataset}")
    try:
        output_resolved = output.resolve()
    except OSError:
        output_resolved = output.absolute()
    image_paths = []
    candidates = list((dataset / "images").glob("*"))
    candidates.extend(dataset.glob("partitions/*/images/*"))
    for path in candidates:
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            continue
        try:
            if path.resolve() == output_resolved:
                continue
        except OSError:
            pass
        image_paths.append(path)
    image_paths.sort(key=lambda path: (path.name.casefold(), path.name))
    if limit:
        image_paths = image_paths[:limit]
    if not image_paths:
        raise QCError(f"No supported legacy or partitioned images found below {dataset}")

    samples: list[Sample] = []
    for image_path in image_paths:
        stem = image_path.stem
        metadata_path = dataset / "metadata" / f"{stem}.json"
        metadata = load_json_object(metadata_path) if metadata_path.is_file() else None
        declared_label = nested_value(metadata, "outputs", "label")
        label_path = (
            dataset / str(declared_label)
            if declared_label
            else image_path.parent.parent / "labels" / f"{stem}.txt"
        )
        if label_path.is_file():
            boxes = load_yolo_boxes(label_path)
            box_source = "YOLO"
        elif metadata is not None:
            boxes = metadata_boxes(metadata, metadata_path)
            box_source = "metadata" if boxes else "none"
        else:
            boxes = ()
            box_source = "none"
        samples.append(Sample(image_path, metadata, boxes, box_source))
    return samples


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu") / filename,
        Path("/usr/share/fonts/dejavu") / filename,
    )
    for path in candidates:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def nested_value(data: dict[str, Any] | None, *keys: str) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def caption_lines(sample: Sample) -> tuple[str, str]:
    if sample.metadata is None:
        return sample.image_path.stem, "metadata unavailable"
    seed = nested_value(sample.metadata, "seed")
    camera = nested_value(sample.metadata, "camera")
    state = nested_value(sample.metadata, "rfid_tag", "state")
    light = nested_value(sample.metadata, "lighting", "profile")
    first = "  ".join(
        part for part in (f"seed={seed}" if seed is not None else "", f"cam={camera}" if camera else "") if part
    )
    second = "  ".join(
        part for part in (f"tag={state}" if state else "", f"light={light}" if light else "") if part
    )
    return first or sample.image_path.stem, second or "scenario fields unavailable"


def fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    suffix = "..."
    candidate = text
    while candidate and draw.textlength(candidate + suffix, font=font) > max_width:
        candidate = candidate[:-1]
    return candidate.rstrip() + suffix


def class_color(class_id: int) -> tuple[int, int, int]:
    return CLASS_COLORS[class_id % len(CLASS_COLORS)]


def draw_boxes(
    draw: ImageDraw.ImageDraw,
    boxes: tuple[YoloBox, ...],
    original_size: tuple[int, int],
    rendered_size: tuple[int, int],
    origin: tuple[int, int],
    font: ImageFont.ImageFont,
) -> None:
    original_width, original_height = original_size
    rendered_width, rendered_height = rendered_size
    origin_x, origin_y = origin
    scale_x = rendered_width / original_width
    scale_y = rendered_height / original_height
    for box in boxes:
        left = max(0.0, (box.center_x - box.width / 2.0) * original_width)
        right = min(float(original_width), (box.center_x + box.width / 2.0) * original_width)
        top = max(0.0, (box.center_y - box.height / 2.0) * original_height)
        bottom = min(float(original_height), (box.center_y + box.height / 2.0) * original_height)
        coordinates = (
            round(origin_x + left * scale_x),
            round(origin_y + top * scale_y),
            round(origin_x + right * scale_x),
            round(origin_y + bottom * scale_y),
        )
        color = class_color(box.class_id)
        draw.rectangle(coordinates, outline=color, width=3)
        label = CLASS_NAMES.get(box.class_id, f"class {box.class_id}")
        text_box = draw.textbbox((0, 0), label, font=font, stroke_width=0)
        text_width = text_box[2] - text_box[0]
        text_height = text_box[3] - text_box[1]
        label_left = coordinates[0]
        label_top = max(origin_y, coordinates[1] - text_height - 6)
        draw.rectangle(
            (label_left, label_top, label_left + text_width + 8, label_top + text_height + 6),
            fill=color,
        )
        draw.text((label_left + 4, label_top + 2), label, fill=(12, 14, 18), font=font)


def render_sample(
    sheet: Image.Image,
    sample: Sample,
    cell_x: int,
    cell_y: int,
    caption_font: ImageFont.ImageFont,
    label_font: ImageFont.ImageFont,
) -> None:
    draw = ImageDraw.Draw(sheet)
    draw.rectangle(
        (cell_x, cell_y, cell_x + PANEL_WIDTH - 1, cell_y + PANEL_HEIGHT + CAPTION_HEIGHT - 1),
        fill=(25, 28, 34),
        outline=(65, 70, 80),
    )
    try:
        with Image.open(sample.image_path) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except (OSError, ValueError) as exc:
        raise QCError(f"Could not decode image {sample.image_path}: {exc}") from exc
    original_size = image.size
    if original_size[0] < 1 or original_size[1] < 1:
        raise QCError(f"Image has invalid dimensions {original_size}: {sample.image_path}")

    scale = min(PANEL_WIDTH / original_size[0], PANEL_HEIGHT / original_size[1])
    rendered_size = (
        max(1, round(original_size[0] * scale)),
        max(1, round(original_size[1] * scale)),
    )
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    image = image.resize(rendered_size, resample=resampling)
    image_x = cell_x + (PANEL_WIDTH - rendered_size[0]) // 2
    image_y = cell_y + (PANEL_HEIGHT - rendered_size[1]) // 2
    sheet.paste(image, (image_x, image_y))
    draw_boxes(draw, sample.boxes, original_size, rendered_size, (image_x, image_y), label_font)

    first, second = caption_lines(sample)
    max_text_width = PANEL_WIDTH - 14
    first = fit_text(draw, first, caption_font, max_text_width)
    second = fit_text(draw, second, caption_font, max_text_width)
    draw.text((cell_x + 7, cell_y + PANEL_HEIGHT + 5), first, fill=(238, 240, 244), font=caption_font)
    draw.text((cell_x + 7, cell_y + PANEL_HEIGHT + 25), second, fill=(178, 184, 194), font=caption_font)


def create_sheet(dataset: Path, output: Path, columns: int, limit: int) -> tuple[int, tuple[int, int]]:
    samples = discover_samples(dataset, output, limit)
    rows = math.ceil(len(samples) / columns)
    cell_height = PANEL_HEIGHT + CAPTION_HEIGHT
    width = MARGIN * 2 + columns * PANEL_WIDTH + (columns - 1) * GAP
    height = MARGIN * 2 + HEADER_HEIGHT + rows * cell_height + (rows - 1) * GAP
    sheet = Image.new("RGB", (width, height), (15, 17, 21))
    draw = ImageDraw.Draw(sheet)
    header_font = load_font(16, bold=True)
    caption_font = load_font(13)
    label_font = load_font(12, bold=True)
    sources = ", ".join(sorted({sample.box_source for sample in samples}))
    header = f"EBIS QC | {dataset.name} | {len(samples)} image(s) | boxes: {sources}"
    draw.text((MARGIN, MARGIN), fit_text(draw, header, header_font, width - 2 * MARGIN), fill=(240, 242, 246), font=header_font)

    start_y = MARGIN + HEADER_HEIGHT
    for index, sample in enumerate(samples):
        row, column = divmod(index, columns)
        cell_x = MARGIN + column * (PANEL_WIDTH + GAP)
        cell_y = start_y + row * (cell_height + GAP)
        render_sample(sheet, sample, cell_x, cell_y, caption_font, label_font)

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.suffix.lower() in {".jpg", ".jpeg"}:
            sheet.save(output, quality=92, subsampling=0, optimize=True)
        else:
            sheet.save(output, optimize=True)
    except OSError as exc:
        raise QCError(f"Could not write contact sheet {output}: {exc}") from exc
    return len(samples), sheet.size


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        count, size = create_sheet(args.dataset, args.output, args.columns, args.limit)
    except QCError as exc:
        print(f"QC contact sheet failed: {exc}", file=sys.stderr)
        return 1
    print(f"QC_CONTACT_SHEET_OK images={count} size={size[0]}x{size[1]} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
