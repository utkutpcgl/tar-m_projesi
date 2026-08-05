#!/usr/bin/env python3
"""Build a labelled real-versus-synthetic EBIS framing comparison."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def font(size: int, bold: bool = False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = Path("/usr/share/fonts/truetype/dejavu") / name
    return ImageFont.truetype(str(path), size) if path.is_file() else ImageFont.load_default()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", required=True, type=Path)
    parser.add_argument("--synthetic", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--real-label", default="Gerçek EBİS referansı")
    parser.add_argument("--synthetic-label", default="Blender sentetik")
    args = parser.parse_args()

    for source in (args.real, args.synthetic):
        if not source.is_file():
            parser.error(f"input does not exist: {source}")
    if args.output.suffix.lower() != ".png":
        parser.error("--output must be a PNG")

    panel_size = (800, 450)
    header = 54
    footer = 42
    margin = 14
    gap = 14
    canvas = Image.new(
        "RGB",
        (margin * 2 + panel_size[0] * 2 + gap, margin * 2 + header + panel_size[1] + footer),
        (16, 19, 24),
    )
    draw = ImageDraw.Draw(canvas)
    title_font = font(24, bold=True)
    note_font = font(17)

    for index, (path, label) in enumerate(
        ((args.real, args.real_label), (args.synthetic, args.synthetic_label))
    ):
        with Image.open(path) as opened:
            resampling = getattr(Image, "Resampling", Image)
            panel = ImageOps.fit(opened.convert("RGB"), panel_size, resampling.LANCZOS)
        x = margin + index * (panel_size[0] + gap)
        canvas.paste(panel, (x, margin + header))
        draw.text((x, margin + 10), label, fill=(238, 241, 246), font=title_font)

    draw.text(
        (margin, margin + header + panel_size[1] + 11),
        "Görsel kadraj kontrolü; CAD ve kamera intrinsics kalibrasyonu yerine geçmez.",
        fill=(174, 183, 196),
        font=note_font,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output, format="PNG", optimize=True)
    print(f"REFERENCE_COMPARISON_OK {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
