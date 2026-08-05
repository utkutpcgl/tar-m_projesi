#!/usr/bin/env python3
"""Build the compact, presentation-first segmentation result PDF.

The PDF is intentionally rasterized with Pillow so Turkish glyphs, legends and
the already-rendered qualitative artifacts remain self-contained on every page.
It does not re-run inference or alter model selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


W, H = 1920, 1080
BG = (246, 247, 242)
INK = (27, 38, 35)
MUTED = (91, 104, 99)
GREEN = (35, 132, 86)
DARK_GREEN = (22, 76, 55)
LIGHT_GREEN = (224, 240, 230)
RED = (193, 54, 50)
LIGHT_RED = (251, 231, 228)
BLUE = (42, 138, 169)
PURPLE = (162, 55, 196)
YELLOW = (243, 174, 36)
WHITE = (255, 255, 255)
LINE = (211, 218, 212)

REGULAR_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(BOLD_FONT if bold else REGULAR_FONT), size=size)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wrap(text: str, width: int) -> str:
    return "\n".join(
        textwrap.wrap(
            text,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
    )


def add_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    size: int,
    *,
    bold: bool = False,
    fill: tuple[int, int, int] = INK,
    width: int | None = None,
    spacing: int = 10,
) -> None:
    if width:
        text = wrap(text, width)
    draw.multiline_text(xy, text, font=font(size, bold), fill=fill, spacing=spacing)


def page(title: str, number: int, subtitle: str | None = None) -> Image.Image:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 38, 1872, 48), radius=5, fill=GREEN)
    add_text(draw, (70, 73), title, 52, bold=True)
    if subtitle:
        add_text(draw, (72, 140), subtitle, 25, fill=MUTED, width=116)
    add_text(draw, (1730, 1023), f"{number}/9", 23, bold=True, fill=MUTED)
    add_text(draw, (70, 1023), "Crop Segmentation • Kısa Sonuç Raporu", 21, fill=MUTED)
    return image


def card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int] = WHITE,
    outline: tuple[int, int, int] = LINE,
    radius: int = 22,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def paste_contain(
    canvas: Image.Image,
    source: Image.Image,
    box: tuple[int, int, int, int],
    *,
    background: tuple[int, int, int] = WHITE,
) -> None:
    x1, y1, x2, y2 = box
    width, height = x2 - x1, y2 - y1
    fitted = ImageOps.contain(source, (width, height), Image.Resampling.LANCZOS)
    frame = Image.new("RGB", (width, height), background)
    frame.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
    canvas.paste(frame, (x1, y1))


def artifact_visual(path: Path, *, unlabeled: bool = False) -> Image.Image:
    """Crop verbose artifact header/footer while retaining local column labels."""
    with Image.open(path) as source:
        image = source.convert("RGB")
    top = int(image.height * (0.27 if unlabeled else 0.225))
    bottom = int(image.height * (0.885 if not unlabeled else 0.88))
    return image.crop((18, top, image.width - 18, bottom))


def unlabeled_rgb_prediction(path: Path) -> Image.Image:
    """Keep RGB and semantic-prediction columns; discard the verbose header."""
    visual = artifact_visual(path, unlabeled=True)
    # Unlabeled artifacts have three equal columns. Keep columns 1 and 2.
    right = int(visual.width * 2 / 3) - 2
    return visual.crop((0, 0, right, visual.height))


def find_rank(directory: Path, rank: int) -> Path:
    matches = sorted(directory.glob(f"{rank:02d}_*.jpg"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one rank-{rank} artifact under {directory}, found {len(matches)}")
    return matches[0]


def draw_artifact_row(
    canvas: Image.Image,
    path: Path,
    y: int,
    title: str,
    note: str,
    *,
    accent: tuple[int, int, int],
    unlabeled: bool = False,
) -> None:
    draw = ImageDraw.Draw(canvas)
    add_text(draw, (75, y), title, 29, bold=True, fill=accent)
    add_text(draw, (520, y + 2), note, 23, fill=MUTED, width=90)
    card(draw, (68, y + 45, 1852, y + 386))
    paste_contain(canvas, artifact_visual(path, unlabeled=unlabeled), (78, y + 55, 1842, y + 376))


def draw_metric_bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    width: int,
    value: float,
    color: tuple[int, int, int],
    label: str,
) -> None:
    draw.rounded_rectangle((x, y, x + width, y + 32), radius=16, fill=(225, 229, 225))
    draw.rounded_rectangle((x, y, x + max(3, int(width * value)), y + 32), radius=16, fill=color)
    add_text(draw, (x + width + 18, y - 3), f"{label} {value:.3f}", 25, bold=True, fill=color)


def build_pages(report_dir: Path) -> tuple[list[Image.Image], list[Path]]:
    index = json.loads((report_dir / "report_index.json").read_text(encoding="utf-8"))
    individual = report_dir / "INDIVIDUAL"
    selected: list[Path] = []

    rose_good = find_rank(individual / "01_SEEN_DATASET_VALIDATION/rose/best", 5)
    we3ds_hard = find_rank(individual / "01_SEEN_DATASET_VALIDATION/we3ds/worst", 2)
    rice_good = find_rank(individual / "01_SEEN_DATASET_VALIDATION/riceseg_specialist/best", 5)
    sugar_good = find_rank(individual / "03_LABELED_TRANSFER/sugarbeets_holdout/best", 5)
    weedmap_hard = find_rank(individual / "03_LABELED_TRANSFER/weedmap_uav/worst", 5)
    synthetic_good = find_rank(individual / "04_SYNTHETIC_STRESS/v11_test/best", 3)
    synthetic_hard = find_rank(individual / "04_SYNTHETIC_STRESS/v11_test/worst", 3)
    farmbot = individual / "02_UNLABELED_REAL/farmbot_soy/frame_020.jpg"
    bonirob = individual / "02_UNLABELED_REAL/bonirob_unseen/frame_003.jpg"
    naio = individual / "02_UNLABELED_REAL/naio_oz/frame_000.jpg"
    selected.extend(
        [
            rose_good,
            we3ds_hard,
            rice_good,
            sugar_good,
            weedmap_hard,
            farmbot,
            bonirob,
            naio,
            synthetic_good,
            synthetic_hard,
        ]
    )
    missing = [str(path) for path in selected if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing selected artifacts:\n" + "\n".join(missing))

    pages: list[Image.Image] = []

    # 1. Cover / decision summary
    p = Image.new("RGB", (W, H), DARK_GREEN)
    d = ImageDraw.Draw(p)
    d.rounded_rectangle((70, 70, 1850, 1010), radius=36, fill=(246, 247, 242))
    add_text(d, (130, 130), "Crop Segmentation", 76, bold=True, fill=DARK_GREEN)
    add_text(d, (130, 225), "Kısa ve görsel sonuç raporu", 45, bold=True, fill=GREEN)
    add_text(d, (130, 302), "4 Ağustos 2026 • kabul edilmiş modeller ve dondurulmuş sonuçlar", 27, fill=MUTED)
    card(d, (125, 390, 1795, 565), fill=LIGHT_GREEN, outline=GREEN)
    add_text(d, (175, 427), "SONUÇ", 25, bold=True, fill=GREEN)
    add_text(
        d,
        (175, 472),
        "Genel model güçlü bir base. Pirinçte ayrı uzman model gerekli. Sistem henüz püskürtmeye hazır değil.",
        37,
        bold=True,
        width=74,
    )
    summaries = [
        ("0.826", "En iyi validation mIoU", "Sorghum Weed"),
        ("3/3", "Pirinç uzmanı seed kazanımı", "Kabul edildi"),
        ("ANA RİSK", "Yeni domainde weed ayrımı", "WE3DS weed IoU: 0.282"),
    ]
    x_positions = [125, 685, 1245]
    for x, (big, label, detail) in zip(x_positions, summaries):
        card(d, (x, 620, x + 510, 885))
        add_text(d, (x + 35, 660), big, 45, bold=True, fill=RED if big == "ANA RİSK" else GREEN)
        add_text(d, (x + 35, 735), label, 27, bold=True, width=28)
        add_text(d, (x + 35, 825), detail, 23, fill=MUTED, width=32)
    add_text(d, (1460, 950), "1/9", 23, bold=True, fill=MUTED)
    pages.append(p)

    # 2. Legend
    p = page("Görseller nasıl okunur?", 2, "Renk anlamı semantic tahmin ve safety kararında aynı değildir.")
    d = ImageDraw.Draw(p)
    semantic = [
        (GREEN, "YEŞİL", "hedef mahsul / crop"),
        ((232, 49, 50), "KIRMIZI", "diğer bitki / weed"),
        (PURPLE, "MOR", "GT'de ignore; safety'de no-spray"),
    ]
    for idx, (color, name, meaning) in enumerate(semantic):
        x = 75 + idx * 585
        card(d, (x, 205, x + 540, 325))
        d.rounded_rectangle((x + 25, 230, x + 85, 290), radius=12, fill=color)
        add_text(d, (x + 105, 225), name, 25, bold=True, fill=color)
        add_text(d, (x + 105, 263), meaning, 22, fill=MUTED)
    add_text(
        d,
        (75, 350),
        "Kritik kural: Kırmızı semantic alan tek başına püskürtme emri değildir. Eylem için yalnız 4. SAFETY paneli ve kendi yerel legend'i okunur.",
        28,
        bold=True,
        fill=RED,
        width=105,
    )
    card(d, (68, 455, 1852, 980))
    paste_contain(p, artifact_visual(rose_good), (78, 465, 1842, 970))
    pages.append(p)

    # 3. Full validation table
    p = page(
        "Validation benchmark",
        3,
        "Model datasetin train kısmını gördü; aşağıdaki validation/holdout karelerini görmedi.",
    )
    d = ImageDraw.Draw(p)
    headers = [(80, "Dataset"), (780, "Kare"), (955, "mIoU"), (1225, "Crop IoU"), (1505, "Weed IoU")]
    for x, text in headers:
        add_text(d, (x, 205), text, 25, bold=True, fill=MUTED)
    rows = index["seen_dataset_validation"]
    row_y = 250
    for item in rows:
        metric = item["metric"]
        miou = float(metric["mean_iou"])
        crop_iou = float(metric["iou"]["target_crop"])
        weed_iou = float(metric["iou"]["other_vegetation"])
        card(d, (68, row_y, 1852, row_y + 112), fill=WHITE)
        add_text(d, (88, row_y + 27), item["title"].split("—")[0].strip(), 29, bold=True)
        add_text(d, (795, row_y + 29), str(item["evaluation_rows"]), 27)
        draw_metric_bar(d, 955, row_y + 38, 150, miou, GREEN, "")
        draw_metric_bar(d, 1225, row_y + 38, 150, crop_iou, BLUE, "")
        draw_metric_bar(d, 1505, row_y + 38, 150, weed_iou, RED, "")
        row_y += 122
    add_text(
        d,
        (75, 985),
        "mIoU = background + crop + weed ortalaması. Bu nedenle crop ve weed sütunları ayrıca okunmalıdır.",
        22,
        fill=MUTED,
    )
    pages.append(p)

    # 4. One strong and one hard validation example
    p = page(
        "Tek skor yetmez: iyi ve zor örnek",
        4,
        "Bunlar bilerek uçlardan seçildi; tipik kare veya ayrı bir benchmark değildir.",
    )
    draw_artifact_row(
        p,
        rose_good,
        205,
        "GÜÇLÜ — ROSE",
        "split mIoU 0.824 • crop 0.803 • weed 0.691",
        accent=GREEN,
    )
    draw_artifact_row(
        p,
        we3ds_hard,
        615,
        "ZOR — WE3DS",
        "split mIoU 0.691 • crop 0.792 • weed 0.282",
        accent=RED,
    )
    pages.append(p)

    # 5. Rice specialist decision
    selection_path = report_dir.parent / "riceseg_specialist_confirmation_selection_v1.json"
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    paired = next(item for item in selection["confirmation"]["paired"] if item["seed"] == 29)
    p = page(
        "Pirinç: uzman model belirgin biçimde daha iyi",
        5,
        "Karşılaştırma aynı seed=29 içindir; uzman model yalnız crop_id=12 biliniyorsa çalıştırılır.",
    )
    d = ImageDraw.Draw(p)
    domains = [
        ("Erken pirinç", "early_rice"),
        ("RiceSEG", "riceseg"),
        ("Üreme dönemi", "riceseg_reproductive"),
    ]
    add_text(d, (80, 215), "GLOBAL", 24, bold=True, fill=MUTED)
    add_text(d, (560, 215), "PİRİNÇ UZMANI", 24, bold=True, fill=GREEN)
    for idx, (label, key) in enumerate(domains):
        y = 270 + idx * 92
        add_text(d, (80, y), label, 25, bold=True)
        global_value = float(paired["fallback"]["domains"][key])
        specialist_value = float(paired["specialist"]["domains"][key])
        draw_metric_bar(d, 300, y + 3, 190, global_value, MUTED, "")
        draw_metric_bar(d, 780, y + 3, 270, specialist_value, GREEN, "")
    card(d, (1330, 205, 1815, 515), fill=LIGHT_GREEN, outline=GREEN)
    add_text(d, (1380, 250), "3 / 3 seed", 48, bold=True, fill=GREEN)
    add_text(d, (1380, 325), "uzman model kazandı", 29, bold=True)
    add_text(d, (1380, 390), "Robust skor\n0.019 → 0.418", 30, bold=True, fill=DARK_GREEN, spacing=14)
    add_text(d, (80, 545), "Görsel: uzman modelin iyi uçtan bir held-out RiceSEG örneği", 23, fill=MUTED)
    card(d, (68, 585, 1852, 985))
    paste_contain(p, artifact_visual(rice_good), (78, 595, 1842, 975))
    pages.append(p)

    # 6. New labeled distributions
    p = page(
        "Eğitimde olmayan etiketli dağılımlar",
        6,
        "Yeni session ve UAV ölçeği. Görseller biri iyi, biri zor uçtan; split metriği yerine geçmez.",
    )
    draw_artifact_row(
        p,
        sugar_good,
        205,
        "İYİ UÇ — SugarBeets",
        "BoniRob 10:37 session'ı eğitime girmedi",
        accent=GREEN,
    )
    draw_artifact_row(
        p,
        weedmap_hard,
        615,
        "ZOR UÇ — WeedMap",
        "Dataset ve UAV görüntü ölçeği eğitime girmedi",
        accent=RED,
    )
    pages.append(p)

    # 7. Unlabeled real-world sequences
    p = page("Unseen gerçek video ve sekanslar", 7)
    d = ImageDraw.Draw(p)
    d.rounded_rectangle((70, 145, 1850, 205), radius=14, fill=(143, 31, 31))
    add_text(
        d,
        (95, 156),
        "ETİKET YOK → mIoU/doğruluk yok. Yalnız RGB ile model tahmini yan yana incelenir.",
        27,
        bold=True,
        fill=WHITE,
    )
    unseen = [
        (farmbot, "FarmBot Soy", "Bilinen hedef: soya (crop_id=8)"),
        (bonirob, "BoniRob unseen", "Bilinen hedef: şeker pancarı (crop_id=0)"),
        (naio, "Naïo Oz online video", "Hedef bilinmiyor: yalnız vegetation/background okunabilir"),
    ]
    for idx, (path, title, note) in enumerate(unseen):
        y = 235 + idx * 248
        card(d, (68, y, 1852, y + 225))
        paste_contain(p, unlabeled_rgb_prediction(path), (82, y + 12, 1005, y + 213))
        add_text(d, (1050, y + 42), title, 31, bold=True, fill=DARK_GREEN)
        add_text(d, (1050, y + 97), note, 25, fill=MUTED, width=45)
        add_text(d, (1050, y + 164), "Solda RGB • sağda semantic tahmin", 22, bold=True)
    pages.append(p)

    # 8. Synthetic stress only
    p = page(
        "Sentetik veri: stres testi, saha kanıtı değil",
        8,
        "V11 asset/seed ayrık test. Model seçim ağırlığı = 0; iyi ve zor uç birlikte gösteriliyor.",
    )
    draw_artifact_row(
        p,
        synthetic_good,
        205,
        "İYİ UÇ — V11 test",
        "Sentetik dağılım içinde",
        accent=GREEN,
    )
    draw_artifact_row(
        p,
        synthetic_hard,
        615,
        "ZOR UÇ — V11 test",
        "Sentetik dağılım içinde",
        accent=RED,
    )
    pages.append(p)

    # 9. Decision and next action
    p = page("Net karar ve sıradaki adım", 9)
    d = ImageDraw.Draw(p)
    decisions = [
        (GREEN, LIGHT_GREEN, "KORU", "Global base", "Pirinç dışı bilinen ve bilinmeyen crop rotasında kabul edilen global model."),
        (BLUE, (228, 241, 246), "ROUTE ET", "Rice specialist", "Yalnız dış bilgiden crop_id=12 / Oryza sativa kesin ise kullan."),
        (RED, LIGHT_RED, "ANA RİSK", "Weed genellemesi", "WE3DS, UAV ölçeği, ince bitkiler ve yeni domainlerde hatalar sürüyor."),
        (YELLOW, (253, 245, 220), "SONRAKİ GATE", "Bağımsız gerçek saha", "Farklı tarla/zemin/ışık koşullarında etiketli video test ve safety kalibrasyonu."),
    ]
    positions = [(70, 190, 925, 500), (995, 190, 1850, 500), (70, 550, 925, 860), (995, 550, 1850, 860)]
    for (accent, fill, badge, title, body), box in zip(decisions, positions):
        card(d, box, fill=fill, outline=accent)
        x1, y1, _, _ = box
        add_text(d, (x1 + 38, y1 + 34), badge, 23, bold=True, fill=accent)
        add_text(d, (x1 + 38, y1 + 82), title, 36, bold=True)
        add_text(d, (x1 + 38, y1 + 145), body, 27, fill=INK, width=46, spacing=13)
    d.rounded_rectangle((70, 900, 1850, 995), radius=20, fill=DARK_GREEN)
    add_text(
        d,
        (105, 925),
        "Şimdi: baseline'ı dondur → bağımsız gerçek saha testi → sonra depth.",
        31,
        bold=True,
        fill=WHITE,
    )
    pages.append(p)

    return pages, selected


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    default_report = project_root / "data/processed/audits/segmentation_visual_report_v2"
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", type=Path, default=default_report)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report_dir = args.report_dir.resolve()
    output = (args.output or report_dir / "BASLA_BURADAN_SEGMENTASYON_SONUCLARI.pdf").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    pages, selected = build_pages(report_dir)
    pages[0].save(
        output,
        "PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=144.0,
        quality=90,
        optimize=True,
        title="Crop Segmentation - Kisa Sonuc Raporu",
        author="Tarim Projesi",
        subject="Accepted segmentation models and validation evidence",
    )

    receipt = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "compact_presentation_only_segmentation_report",
        "inference_rerun": False,
        "model_selection_changed": False,
        "source_report_index": str((report_dir / "report_index.json").resolve()),
        "source_report_index_sha256": sha256(report_dir / "report_index.json"),
        "pdf": str(output),
        "pdf_sha256": sha256(output),
        "page_count": len(pages),
        "selected_artifacts": [
            {"path": str(path.resolve()), "sha256": sha256(path)} for path in selected
        ],
    }
    receipt_path = report_dir / "PROVENANCE/simple_pdf_receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    print(receipt_path)


if __name__ == "__main__":
    main()
