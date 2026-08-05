#!/usr/bin/env python3
"""Compose compact best/worst contact sheets from an error-gallery index."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont


FONT_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FONT_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(
            str(FONT_BOLD if bold else FONT_REGULAR), size=size
        )
    except OSError:
        return ImageFont.load_default()


def legend_row(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    items: list[tuple[tuple[int, int, int], str]],
) -> None:
    label_font = font(25, bold=True)
    item_font = font(24)
    draw.text((x, y), label, fill=(20, 20, 20), font=label_font)
    cursor = x + int(draw.textlength(label, font=label_font)) + 22
    for colour, text in items:
        draw.rounded_rectangle(
            (cursor, y + 1, cursor + 30, y + 30),
            radius=5,
            fill=colour,
            outline=(45, 45, 45),
            width=1,
        )
        cursor += 40
        draw.text((cursor, y), text, fill=(35, 35, 35), font=item_font)
        cursor += int(draw.textlength(text, font=item_font)) + 34


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def render(
    rows: list[dict[str, Any]],
    root: Path,
    output: Path,
    title: str,
    context: Mapping[str, object] | None = None,
) -> None:
    """Compose a high-resolution, self-explanatory labeled contact sheet."""
    context = dict(context or {})
    columns, cell_width, cell_height, header = 2, 1700, 735, 270
    count_rows = (len(rows) + columns - 1) // columns
    canvas = Image.new(
        "RGB",
        (columns * cell_width, header + count_rows * cell_height),
        (246, 247, 244),
    )
    draw = ImageDraw.Draw(canvas)
    title_font = font(46, bold=True)
    role_font = font(29, bold=True)
    body_font = font(25)
    draw.text((28, 18), title, fill=(18, 18, 18), font=title_font)
    evidence = str(context.get("evidence_label", "ETİKETLİ DEĞERLENDİRME"))
    target = str(context.get("target", "Hedef mahsul bilgisi her tekil görselde yazılıdır"))
    metrics = str(context.get("metrics", ""))
    warning = str(
        context.get(
            "warning",
            "Kırmızı semantik sınıf = diğer bitki; doğrudan püskürtme izni değildir.",
        )
    )
    draw.rounded_rectangle((28, 79, canvas.width - 28, 120), radius=8, fill=(29, 72, 48))
    draw.text((44, 83), f"{evidence}  •  {target}", fill="white", font=role_font)
    legend_row(
        draw,
        30,
        133,
        "SEMANTİK:",
        [
            ((40, 220, 70), "hedef mahsul / crop"),
            ((230, 45, 45), "diğer bitki / weed"),
            ((180, 60, 210), "ignore"),
        ],
    )
    legend_row(
        draw,
        30,
        174,
        "SAFETY:",
        [
            ((40, 220, 70), "crop guard"),
            ((20, 190, 240), "izinli spray"),
            ((255, 180, 0), "crop hit / hata"),
            ((180, 60, 210), "kararsız / no-spray"),
        ],
    )
    draw.text(
        (30, 220),
        f"{metrics}  •  {warning}" if metrics else warning,
        fill=(92, 25, 25),
        font=body_font,
    )
    for index, row in enumerate(rows):
        x = (index % columns) * cell_width
        y = header + (index // columns) * cell_height
        path = root / str(row["artifact"])
        with Image.open(path) as handle:
            image = handle.convert("RGB")
            image.thumbnail((cell_width - 36, cell_height - 46), Image.Resampling.LANCZOS)
        background = Image.new("RGB", (cell_width - 16, cell_height - 16), (232, 234, 230))
        background.paste(image, ((cell_width - image.width) // 2, (cell_height - image.height) // 2))
        canvas.paste(background, (x + 8, y + 8))
        draw.rounded_rectangle(
            (x + 8, y + 8, x + cell_width - 9, y + cell_height - 9),
            radius=7,
            outline=(150, 154, 148),
            width=2,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=94, subsampling=0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--evidence-label", default="ETİKETLİ DEĞERLENDİRME")
    parser.add_argument("--target", default="Hedef mahsul bilgisi her tekil görselde yazılıdır")
    parser.add_argument("--metrics", default="")
    parser.add_argument(
        "--warning",
        default="Kırmızı semantik sınıf = diğer bitki; doğrudan püskürtme izni değildir.",
    )
    args = parser.parse_args()
    index_path = Path(args.index).resolve()
    root = index_path.parent
    receipt_path = root / "contact_sheet_receipt.json"
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    value = json.loads(index_path.read_text(encoding="utf-8"))
    artifacts = value["artifacts"]
    outputs: dict[str, Any] = {}
    for selection in ("best", "worst"):
        rows = sorted(
            (row for row in artifacts if row["selection"] == selection),
            key=lambda row: int(row["selection_rank"]),
        )
        if not rows:
            continue
        output = root / f"{selection}_contact_sheet.jpg"
        render(
            rows,
            root,
            output,
            f"{args.title} | {selection.upper()} {len(rows)}",
            {
                "evidence_label": args.evidence_label,
                "target": args.target,
                "metrics": args.metrics,
                "warning": args.warning,
            },
        )
        outputs[selection] = {
            "path": str(output),
            "sha256": sha256(output),
            "items": len(rows),
        }
    receipt = {
        "schema_version": 1,
        "gallery_index": str(index_path),
        "gallery_index_sha256": sha256(index_path),
        "title": args.title,
        "contact_sheets": outputs,
        "script": str(Path(__file__).resolve()),
        "script_sha256": sha256(__file__),
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
