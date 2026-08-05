#!/usr/bin/env python3
"""Create a neutral real/Blender/Unreal EBIS visual-comparison sheet."""

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
    for camera in ("angled", "door"):
        for domain in ("real", "blender", "unreal"):
            parser.add_argument(f"--{camera}-{domain}", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.suffix.lower() != ".png":
        parser.error("output must be PNG")

    panel = (640, 360)
    gap, margin, label_h, header_h, footer_h = 12, 14, 40, 54, 48
    width = margin * 2 + panel[0] * 3 + gap * 2
    height = margin * 2 + header_h + (panel[1] + label_h) * 2 + gap + footer_h
    canvas = Image.new("RGB", (width, height), (14, 17, 21))
    draw = ImageDraw.Draw(canvas)
    title_font, label_font, note_font = font(22, True), font(17, True), font(15)
    draw.text((margin, margin + 8), "EBIS görsel engine karşılaştırması — ölçüm değil, eşlenik QC", fill=(242, 244, 248), font=title_font)

    columns = (("Gerçek LED", "real"), ("Blender", "blender"), ("Unreal 5.8.1", "unreal"))
    rows = (("camera_angled / Kamera 01", "angled"), ("camera_door / Kamera 02", "door"))
    resampling = getattr(Image, "Resampling", Image)
    for row_index, (camera_label, camera_key) in enumerate(rows):
        y = margin + header_h + row_index * (panel[1] + label_h + gap)
        for column_index, (domain_label, domain_key) in enumerate(columns):
            source = getattr(args, f"{camera_key}_{domain_key}")
            if not source.is_file():
                parser.error(f"missing input: {source}")
            with Image.open(source) as opened:
                image = ImageOps.fit(opened.convert("RGB"), panel, resampling.LANCZOS)
            x = margin + column_index * (panel[0] + gap)
            canvas.paste(image, (x, y))
            draw.rectangle((x, y, x + panel[0] - 1, y + panel[1] - 1), outline=(68, 74, 84))
            draw.text((x + 5, y + panel[1] + 8), f"{camera_label} · {domain_label}", fill=(231, 234, 240), font=label_font)

    draw.text(
        (margin, height - footer_h + 12),
        "Farklı an/seed ve insan örtüşmesi içerir; yalnız domain-gap ve sonraki iyileştirme kararları için kullanılır.",
        fill=(174, 182, 193),
        font=note_font,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output, format="PNG", optimize=True)
    print(f"ENGINE_COMPARISON_OK output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
