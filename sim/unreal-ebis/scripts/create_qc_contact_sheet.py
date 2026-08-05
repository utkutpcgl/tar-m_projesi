#!/usr/bin/env python3
"""Draw the published YOLO boxes on every Unreal-EBIS partition image."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


COLORS = {0: (255, 74, 164), 1: (36, 211, 231)}
NAMES = {0: "rfid", 1: "concrete"}
PANEL = (384, 216)
CAPTION = 54
GAP = 10
MARGIN = 12
HEADER = 36


def font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path("/usr/share/fonts/truetype/dejavu") / name
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def load_boxes(path: Path) -> list[tuple[int, float, float, float, float]]:
    boxes = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        fields = raw.split()
        if not fields:
            continue
        if len(fields) != 5:
            raise ValueError(f"invalid YOLO row at {path}:{number}")
        class_id = int(fields[0])
        coordinates = tuple(map(float, fields[1:]))
        if any(not 0.0 <= value <= 1.0 for value in coordinates):
            raise ValueError(f"non-normalized YOLO row at {path}:{number}")
        boxes.append((class_id, *coordinates))
    return boxes


def discover(root: Path):
    samples = []
    for partition in ("standard", "hard_occlusion", "exclude"):
        for image in sorted((root / "partitions" / partition / "images").glob("*.png")):
            label = image.parent.parent / "labels" / f"{image.stem}.txt"
            metadata_path = root / "metadata" / f"{image.stem}.json"
            if not label.is_file() or not metadata_path.is_file():
                raise FileNotFoundError(f"missing label or metadata for {image.stem}")
            samples.append((partition, image, load_boxes(label), json.loads(metadata_path.read_text(encoding="utf-8"))))
    if not samples:
        raise FileNotFoundError(f"no partition images below {root}")
    return samples


def draw_box(draw, box, origin, rendered_size, label_font):
    class_id, cx, cy, width, height = box
    ox, oy = origin
    rw, rh = rendered_size
    xyxy = (
        round(ox + (cx - width / 2) * rw),
        round(oy + (cy - height / 2) * rh),
        round(ox + (cx + width / 2) * rw),
        round(oy + (cy + height / 2) * rh),
    )
    color = COLORS.get(class_id, (255, 190, 48))
    draw.rectangle(xyxy, outline=color, width=3)
    label = NAMES.get(class_id, str(class_id))
    bounds = draw.textbbox((0, 0), label, font=label_font)
    tw, th = bounds[2] - bounds[0], bounds[3] - bounds[1]
    tx, ty = xyxy[0], max(oy, xyxy[1] - th - 6)
    draw.rectangle((tx, ty, tx + tw + 8, ty + th + 6), fill=color)
    draw.text((tx + 4, ty + 2), label, fill=(10, 12, 16), font=label_font)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--columns", type=int, default=4)
    args = parser.parse_args()
    if args.columns < 1 or args.output.suffix.lower() != ".png":
        parser.error("columns must be positive and output must be PNG")

    samples = discover(args.dataset.resolve())
    rows = math.ceil(len(samples) / args.columns)
    width = MARGIN * 2 + args.columns * PANEL[0] + (args.columns - 1) * GAP
    height = MARGIN * 2 + HEADER + rows * (PANEL[1] + CAPTION) + (rows - 1) * GAP
    sheet = Image.new("RGB", (width, height), (14, 17, 21))
    draw = ImageDraw.Draw(sheet)
    header_font, caption_font, label_font = font(16, True), font(12), font(12, True)
    draw.text((MARGIN, MARGIN), f"Unreal-EBIS QC | {args.dataset.name} | {len(samples)} kare", fill=(242, 244, 248), font=header_font)

    for index, (partition, path, boxes, metadata) in enumerate(samples):
        row, column = divmod(index, args.columns)
        x = MARGIN + column * (PANEL[0] + GAP)
        y = MARGIN + HEADER + row * (PANEL[1] + CAPTION + GAP)
        with Image.open(path) as source:
            original = ImageOps.exif_transpose(source).convert("RGB")
        fitted = ImageOps.fit(original, PANEL, getattr(Image, "Resampling", Image).LANCZOS)
        sheet.paste(fitted, (x, y))
        for box in boxes:
            draw_box(draw, box, (x, y), PANEL, label_font)
        line1 = f"seed={metadata['seed']}  {metadata['camera']}  {metadata['sample']['shape']}"
        line2 = f"{metadata['lighting']['profile']}  partition={partition}"
        draw.text((x + 6, y + PANEL[1] + 6), line1, fill=(238, 240, 244), font=caption_font)
        draw.text((x + 6, y + PANEL[1] + 27), line2, fill=(177, 184, 194), font=caption_font)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output, format="PNG", optimize=True)
    print(f"QC_CONTACT_SHEET_OK images={len(samples)} size={width}x{height} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
