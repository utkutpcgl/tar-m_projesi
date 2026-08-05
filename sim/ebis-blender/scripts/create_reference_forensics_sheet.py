#!/usr/bin/env python3
"""Create a labelled contact sheet from explicit EBIS reference images."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def load_font(size: int, *, bold: bool = False):
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path("/usr/share/fonts/truetype/dejavu") / filename
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--columns", type=int, default=4)
    parser.add_argument("--cell-width", type=int, default=480)
    parser.add_argument("--cell-height", type=int, default=270)
    parser.add_argument("--title", default="EBIS reference forensics")
    args = parser.parse_args()

    if args.columns < 1 or args.cell_width < 160 or args.cell_height < 90:
        parser.error("invalid grid dimensions")
    missing = [path for path in args.input if not path.is_file()]
    if missing:
        parser.error(f"missing input(s): {missing}")
    if args.output.suffix.lower() != ".png":
        parser.error("--output must end in .png")

    title_height = 54
    caption_height = 46
    margin = 12
    gap = 10
    rows = math.ceil(len(args.input) / args.columns)
    width = margin * 2 + args.columns * args.cell_width + (args.columns - 1) * gap
    height = (
        margin * 2
        + title_height
        + rows * (args.cell_height + caption_height)
        + (rows - 1) * gap
    )
    canvas = Image.new("RGB", (width, height), (14, 17, 21))
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, margin + 8), args.title, font=load_font(24, bold=True), fill=(240, 243, 247))
    caption_font = load_font(13)

    resampling = getattr(Image, "Resampling", Image)
    for index, path in enumerate(args.input):
        row, column = divmod(index, args.columns)
        x = margin + column * (args.cell_width + gap)
        y = margin + title_height + row * (args.cell_height + caption_height + gap)
        with Image.open(path) as opened:
            panel = ImageOps.fit(
                opened.convert("RGB"),
                (args.cell_width, args.cell_height),
                method=resampling.LANCZOS,
            )
        canvas.paste(panel, (x, y))
        label = f"{index + 1:02d}  {path.parent.parent.parent.name}/{path.name}"
        draw.text(
            (x + 4, y + args.cell_height + 5),
            label[:76],
            font=caption_font,
            fill=(200, 208, 219),
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output, format="PNG", optimize=True)
    print(f"REFERENCE_FORENSICS_SHEET_OK images={len(args.input)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
