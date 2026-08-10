#!/usr/bin/env python3
"""Build the concise detection-only vs keypoint spot-spray report."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw, ImageOps

from scripts.build_intervention_reports import (
    BG,
    BLUE,
    DARK_GREEN,
    GREEN,
    H,
    INK,
    LIGHT_BLUE,
    LIGHT_GREEN,
    LIGHT_ORANGE,
    LIGHT_RED,
    LINE,
    MUTED,
    ORANGE,
    RED,
    W,
    WHITE,
    add_text,
    base_page,
    bullet_list,
    card,
    draw_table,
    finalize_pages,
    metric_card,
    save_pdf,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
RUN = DATA_ROOT / "runs/wsd_detection_poc_v1/yolo26s_detect_1024_seed17"
METRICS_1024 = RUN / "spot_spray_ab_1024_final_v1/spot_spray_ab_metrics.json"
METRICS_1536 = RUN / "spot_spray_ab_1536_inference_v1/spot_spray_ab_metrics.json"
TRAINING_RECEIPT = RUN / "run_receipt.json"
DATASET_RECEIPT = (
    DATA_ROOT
    / "processed/audits/weed_stem_detection_detect_v1_receipt.json"
)
GALLERY = RUN / "spot_spray_ab_1024_final_v1/comparison_gallery"
PDF_PATH = PROJECT_ROOT / "docs/results/DETECTION_SPOT_SPRAY_BENCHMARK_V1.pdf"
MARKDOWN_PATH = PROJECT_ROOT / "docs/DETECTION_SPOT_SPRAY_BENCHMARK_V1.md"
PACKAGE = (
    DATA_ROOT
    / "processed/audits/wsd_detection_spot_spray_benchmark_v1"
)


def load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"%{100.0 * value:.{digits}f}".replace(".", ",")


def spot(
    report: dict[str, Any],
    strategy: str,
    *,
    policy: str = "balanced_max_f1",
    radius: str = "0",
) -> dict[str, Any]:
    return report["strategies"][strategy]["test"]["weed_box_proxy"][policy][
        "test_by_footprint_radius"
    ][radius]


def strict(report: dict[str, Any], strategy: str) -> dict[str, Any]:
    return report["strategies"][strategy]["test"]["stem_strict"][
        "balanced_max_f1"
    ]["test_by_tolerance"]["box_diagonal_fraction_0.10"]


def _bar(
    page: Image.Image,
    y: int,
    label: str,
    value: float,
    *,
    note: str,
    colour: tuple[int, int, int],
    left: int = 400,
    width: int = 1250,
) -> None:
    draw = ImageDraw.Draw(page)
    add_text(draw, (75, y - 3), label, 24, bold=True, width=18)
    draw.rounded_rectangle((left, y, left + width, y + 44), radius=15, fill=LINE)
    draw.rounded_rectangle(
        (left, y, left + round(width * value), y + 44), radius=15, fill=colour
    )
    add_text(draw, (left + width + 25, y - 5), pct(value), 28, bold=True, fill=colour)
    add_text(draw, (left, y + 53), note, 18, fill=MUTED, width=105)


def _paste_image(
    page: Image.Image,
    source: Image.Image,
    box: tuple[int, int, int, int],
) -> None:
    x1, y1, x2, y2 = box
    fitted = ImageOps.contain(
        source.convert("RGB"), (x2 - x1, y2 - y1), Image.Resampling.LANCZOS
    )
    frame = Image.new("RGB", (x2 - x1, y2 - y1), WHITE)
    frame.paste(
        fitted,
        ((frame.width - fitted.width) // 2, (frame.height - fitted.height) // 2),
    )
    page.paste(frame, (x1, y1))


def _panel(path: Path, index: int) -> Image.Image:
    with Image.open(path) as handle:
        image = handle.convert("RGB")
    half_width = image.width // 2
    half_height = image.height // 2
    x = (index % 2) * half_width
    y = (index // 2) * half_height
    return image.crop((x, y, x + half_width, y + half_height))


def cover(report: dict[str, Any]) -> Image.Image:
    metric = spot(report, "detection_only_box_center")
    stem = strict(report, "detection_only_box_center")
    page = Image.new("RGB", (W, H), DARK_GREEN)
    draw = ImageDraw.Draw(page)
    card(draw, (70, 60, 1850, 1015), fill=BG, outline=BG, radius=38)
    add_text(draw, (125, 115), "Detection-only spot spray", 66, bold=True, fill=DARK_GREEN)
    add_text(draw, (128, 200), "Kutu merkezi mi, keypoint mi?", 42, bold=True, fill=GREEN)
    add_text(draw, (130, 266), "10 Ağustos 2026 • gerçek WSD robot verisi • tarih-ayrı test", 23, fill=MUTED)
    card(draw, (125, 340, 1795, 510), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (166, 372), "KISA CEVAP", 23, bold=True, fill=ORANGE)
    add_text(
        draw,
        (166, 415),
        "Detection-only, ilk kimyasal spot-spray PoC'si için yeterli aday; saha ateşlemesi için yeterli değil. Lazer için keypoint hâlâ gerekir.",
        34,
        bold=True,
        width=84,
    )
    metric_card(page, (125, 575, 630, 820), pct(metric["precision"]), "Spot precision", "GT weed kutusuna merkez-isabet; iyimser proxy.", accent=BLUE)
    metric_card(page, (660, 575, 1165, 820), pct(metric["recall"]), "Spot recall", "1.102 weed kutusunun yakalanan oranı.", accent=GREEN)
    metric_card(page, (1195, 575, 1700, 820), pct(metric["f1"]), "Spot F1", f"Gövdeye yakın F1 yalnız {pct(stem['f1'])}.", accent=RED)
    add_text(
        draw,
        (130, 885),
        "Hedef %95 F1 kapısı geçilmedi. Mevcut sonuç yalnız offline araştırma benchmark'ıdır.",
        29,
        bold=True,
        fill=RED,
        width=103,
    )
    return page


def architecture_page() -> Image.Image:
    page = base_page("Hangi müdahalede hangi başlık?", "En basit yeterli modeli müdahale yöntemine göre seçiyoruz.")
    draw = ImageDraw.Draw(page)
    card(draw, (70, 220, 900, 815), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (110, 255), "Kimyasal spot spray", 36, bold=True, fill=DARK_GREEN)
    add_text(draw, (110, 315), "DETECTION-ONLY ADAY", 25, bold=True, fill=GREEN)
    bullet_list(
        page,
        [
            "Weed kutusunu bul; merkezine veya güvenli iç bölgesine püskürt.",
            "Nozul ayak izi hedefleme hatasından genişse ayrı sap noktası zorunlu olmayabilir.",
            "Segmentasyon crop-maskesi, safety veto ve gerçek püskürtme footprint'i için korunur.",
            "Gerçek deposition/kill ve crop injury ölçülmeden ateşleme onayı verilmez.",
        ],
        (110, 380),
        width=48,
        size=24,
    )
    card(draw, (1020, 220, 1850, 815), fill=LIGHT_RED, outline=RED)
    add_text(draw, (1060, 255), "Lazer / mekanik sökme", 36, bold=True, fill=RED)
    add_text(draw, (1060, 315), "KEYPOINT GEREKİR", 25, bold=True, fill=RED)
    bullet_list(
        page,
        [
            "Kutu merkezi sap, kök, crown veya meristem değildir.",
            "Dar etki alanında stem/root/meristem keypoint veya eşdeğer instance-geometri gerekir.",
            "Kamera–alet extrinsic, GSD, latency ve mm hata dağılımı ayrıca kalibre edilir.",
            "Keypoint başlığı kötü weed detection/classification'ı tek başına düzeltemez.",
        ],
        (1060, 380),
        width=48,
        size=24,
    )
    card(draw, (250, 860, 1670, 965), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (295, 890), "Karar: spray baseline = detection-only + segmentation safety; lazer kolu = detection + stem keypoint.", 28, bold=True, fill=BLUE, width=90)
    return page


def definition_page() -> Image.Image:
    page = base_page("İki farklı ‘isabet’ ölçtük", "Aynı rakam gibi gösterilmeleri yanıltıcı olur.")
    draw = ImageDraw.Draw(page)
    card(draw, (70, 225, 900, 775), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (110, 260), "1 • Weed kutusu proxy'si", 35, bold=True, fill=BLUE)
    add_text(draw, (110, 330), "Tahmin noktası GT weed bounding box'ın içine girerse isabet sayılır.", 28, bold=True, width=47)
    add_text(draw, (110, 470), "Ne söyler?", 23, bold=True, fill=DARK_GREEN)
    add_text(draw, (110, 510), "Geniş ayak izli spot spray için erişilebilir üst sınır.", 25, width=48)
    add_text(draw, (110, 610), "Ne söylemez?", 23, bold=True, fill=RED)
    add_text(draw, (110, 650), "Kutu toprak içerir; weed dokusuna damla veya öldürme garantisi değildir.", 25, width=48)
    card(draw, (1020, 225, 1850, 775), fill=LIGHT_RED, outline=RED)
    add_text(draw, (1060, 260), "2 • Sıkı gövde proxy'si", 35, bold=True, fill=RED)
    add_text(draw, (1060, 330), "Nokta, etiketli weed sapına kutu diyagonalinin en fazla %10'u kadar uzaksa isabet.", 28, bold=True, width=47)
    add_text(draw, (1060, 470), "Ne söyler?", 23, bold=True, fill=DARK_GREEN)
    add_text(draw, (1060, 510), "Dar noktasal müdahale için daha gerçekçi localisation testi.", 25, width=48)
    add_text(draw, (1060, 610), "Ne söylemez?", 23, bold=True, fill=RED)
    add_text(draw, (1060, 650), "%10 diyagonal mm değildir; WSD'de GSD ve aktüatör kalibrasyonu yoktur.", 25, width=48)
    card(draw, (215, 830, 1705, 960), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (260, 862), "Her iki ölçüm one-to-one eşleşir: bir tahmin iki weed'i, iki tahmin bir weed'i doğru sayamaz. Threshold ve dedupe yalnız validation'dan seçilir.", 26, bold=True, width=98)
    return page


def ab_page(report: dict[str, Any]) -> Image.Image:
    page = base_page("Eşit koşullu A/B sonucu", "Aynı 211/152/148 tarih-ayrı kare, 1024 train/inference, seed 17 ve 100 epoch isteği.")
    rows: list[list[str]] = []
    for strategy, label in (
        ("detection_only_box_center", "Detection-only → merkez"),
        ("pose_box_center", "Pose model → merkez"),
        ("pose_keypoint", "Pose model → keypoint"),
    ):
        box_metric = spot(report, strategy)
        stem_metric = strict(report, strategy)
        rows.append(
            [
                label,
                pct(box_metric["precision"]),
                pct(box_metric["recall"]),
                pct(box_metric["f1"]),
                pct(stem_metric["f1"]),
            ]
        )
    draw_table(
        page,
        (70, 235, 1850, 570),
        ("Model / aksiyon", "Spot P", "Spot R", "Spot F1", "Gövde F1"),
        rows,
        (0.38, 0.14, 0.14, 0.16, 0.18),
        font_size=25,
        row_height=80,
        align_right=(1, 2, 3, 4),
    )
    draw = ImageDraw.Draw(page)
    card(draw, (70, 640, 900, 930), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (110, 675), "Ne kazandık?", 31, bold=True, fill=DARK_GREEN)
    add_text(draw, (110, 735), "Detection-only spot F1, pose keypoint'ten +1,6 puan yüksek. Daha basit başlık gerilemedi.", 29, bold=True, width=47)
    card(draw, (1020, 640, 1850, 930), fill=LIGHT_RED, outline=RED)
    add_text(draw, (1060, 675), "Ne çözülmedi?", 31, bold=True, fill=RED)
    add_text(draw, (1060, 735), "Üç yaklaşımın sıkı gövde F1'ı yaklaşık %66. Ana sınır weed proposal/classification; keypoint hassasiyeti değil.", 29, bold=True, width=47)
    return page


def recall_tradeoff_page(report: dict[str, Any]) -> Image.Image:
    balanced = spot(report, "detection_only_box_center")
    high = spot(
        report,
        "detection_only_box_center",
        policy="validation_recall_95",
    )
    page = base_page("%95 recall zorlanınca ne oluyor?", "Eşiği düşürmek kaçırmayı azaltıyor; yanlış püskürtmeyi patlatıyor.")
    draw = ImageDraw.Draw(page)
    add_text(draw, (70, 215), "Dengeli validation seçimi", 29, bold=True, fill=DARK_GREEN)
    _bar(page, 280, "Precision", balanced["precision"], note=f"{balanced['false_positive']} yanlış aksiyon", colour=BLUE)
    _bar(page, 400, "Recall", balanced["recall"], note=f"{balanced['false_negative']} weed kaçırıldı", colour=GREEN)
    _bar(page, 520, "F1", balanced["f1"], note=f"{balanced['actions']} toplam aksiyon", colour=ORANGE)
    add_text(draw, (70, 655), "Recall-95 validation politikası", 29, bold=True, fill=RED)
    _bar(page, 710, "Precision", high["precision"], note=f"{high['false_positive']} yanlış aksiyon", colour=BLUE)
    _bar(page, 830, "Recall", high["recall"], note=f"{high['false_negative']} weed kaçırıldı", colour=GREEN)
    card(draw, (1180, 630, 1835, 950), fill=LIGHT_RED, outline=RED)
    add_text(draw, (1220, 665), "Sonuç", 30, bold=True, fill=RED)
    add_text(draw, (1220, 725), f"Recall {pct(high['recall'])}; fakat precision {pct(high['precision'])} ve F1 {pct(high['f1'])}.", 29, bold=True, width=34)
    add_text(draw, (1220, 865), "Tracking/prior ölçülmeden bu yanlışların düzeleceği varsayılmaz.", 22, fill=MUTED, width=39)
    return page


def size_page(report: dict[str, Any]) -> Image.Image:
    size = report["strategies"]["detection_only_box_center"]["test"][
        "weed_box_proxy"
    ]["balanced_max_f1"]["test_radius_0_recall_by_apparent_weed_box_size"]["bins"]
    page = base_page("Küçük nesne ana darboğazlardan biri", "Boyut = model girişinde sqrt(GT weed kutu alanı); gerçek mask çapı değildir.")
    _bar(page, 260, "<14 px", size["lt14"]["recall"], note=f"n={size['lt14']['ground_truth']} weed", colour=RED)
    _bar(page, 410, "14–28 px", size["14_to_lt28"]["recall"], note=f"n={size['14_to_lt28']['ground_truth']} weed", colour=ORANGE)
    _bar(page, 560, "28–56 px", size["28_to_lt56"]["recall"], note=f"n={size['28_to_lt56']['ground_truth']} weed", colour=GREEN)
    draw = ImageDraw.Draw(page)
    card(draw, (70, 735, 1850, 940), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (115, 770), "28 px üstü güçlü ama kusursuz değil", 31, bold=True, fill=ORANGE)
    add_text(draw, (115, 825), f"28–56 px grubunda recall {pct(size['28_to_lt56']['recall'])}. ≥56 px grubunda yalnız bir örnek vardı ve kaçtı; oradan genelleme yapılamaz. 28 px bir mühendislik başlangıç hipotezidir, güvenlik garantisi değildir.", 26, width=106)
    return page


def resolution_page(report_1024: dict[str, Any], report_1536: dict[str, Any]) -> Image.Image:
    base = spot(report_1024, "detection_only_box_center")
    large = spot(report_1536, "detection_only_box_center")
    counter = report_1024["data"]["test_size_counterfactuals_without_model_inference"]
    rows = []
    for size in ("1024", "1536", "2048"):
        metrics = counter[size]
        bins = metrics["bins"]
        above = bins["28_to_lt56"]["fraction"] + bins["ge56"]["fraction"]
        rows.append([size, pct(above), f"{metrics['distribution_px']['p50']:.1f} px".replace(".", ",")])
    page = base_page("28 px’i korumak kamera problemidir", "Dijital upscale ile sensörde yeni detay oluşmaz.")
    draw_table(
        page,
        (70, 235, 900, 570),
        ("Model girişi", "≥28 px", "Medyan"),
        rows,
        (0.38, 0.31, 0.31),
        font_size=24,
        row_height=78,
        align_right=(1, 2),
    )
    draw = ImageDraw.Draw(page)
    card(draw, (1020, 235, 1850, 570), fill=LIGHT_RED, outline=RED)
    add_text(draw, (1060, 270), "Gerçek 1536 inference testi", 30, bold=True, fill=RED)
    add_text(draw, (1060, 330), f"1024 F1 {pct(base['f1'])}\n1536 F1 {pct(large['f1'])}", 39, bold=True, fill=INK)
    add_text(draw, (1060, 450), "Aynı 1024-trained checkpoint büyütülünce precision düştü. Kör resize reddedildi.", 24, width=48)
    card(draw, (70, 650, 1850, 935), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (115, 685), "Kamera tasarım eşitliği", 30, bold=True, fill=BLUE)
    add_text(draw, (115, 745), "GSD_max (mm/px) = minimum müdahale edilecek weed çapı (mm) / hedef piksel", 33, bold=True, width=98)
    add_text(draw, (115, 825), "Örnek: 20 mm weed’i 28 px görmek için GSD ≤0,71 mm/px. 2048 px yatay sensörde yer genişliği ≤1,46 m; 4096 px sensörde ≤2,93 m. Blur/focus marjı için 42–56 px hedeflemek daha güvenli başlangıçtır.", 25, width=112)
    return page


def visual_detection_page(path: Path) -> Image.Image:
    page = base_page("Gerçek saha örneği: detection-only", "Kırmızı=GT weed • yeşil=GT crop • cyan +=GT sap • sarı=doğru sıkı isabet • magenta=kaçırma/yanlış.")
    panel = _panel(path, 1)
    _paste_image(page, panel, (160, 215, 1760, 850))
    draw = ImageDraw.Draw(page)
    card(draw, (200, 875, 1720, 970), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (240, 899), "Küçük/ince weed'lerde hem kaçırma hem fazla aday görülüyor. Kutu merkezi doğru olduğunda spot spray mümkün; crop güvenliği bu kutu verisiyle kanıtlanamaz.", 24, bold=True, width=105)
    return page


def visual_pose_page(path: Path) -> Image.Image:
    page = base_page("Aynı kare: merkez ve keypoint", "Sol: pose modelinin kutu merkezi • sağ: pose modelinin tahmin edilen sap noktası.")
    left = _panel(path, 2)
    right = _panel(path, 3)
    _paste_image(page, left, (70, 220, 935, 855))
    _paste_image(page, right, (985, 220, 1850, 855))
    draw = ImageDraw.Draw(page)
    card(draw, (150, 885, 1770, 970), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (195, 906), "Görsel fark var; fakat toplu 10% gövde F1 farkı yalnız +0,3 puan. Bu veri diliminde önce weed proposal/classification iyileştirilmeli.", 24, bold=True, width=108)
    return page


def next_steps_page() -> Image.Image:
    page = base_page("Şimdi ne yapmalıyız?", "Kompleksliği ancak ölçülmüş darboğaza ekliyoruz.")
    draw = ImageDraw.Draw(page)
    rows = [
        ("1", "Kamera bench", "Minimum müdahale weed mm, FOV/GSD, focus/DOF, shutter, blur ve gerçek nozzle footprint."),
        ("2", "Deploy verisi", "3–4 tarla/session; weed/crop instance, stem noktası ve video track ID. Test tamamen untouched."),
        ("3", "Spray baseline", "Detection-only + native tile/high-res training + segmentation crop veto. Threshold validation'da."),
        ("4", "Video", "Kalibre zemin koordinatında basit association, ≥3 kare onay, tek-sefer ateş. Kazancı ölçmeden ReID yok."),
        ("5", "Gerçek kapı", "Track-level P/R/F1 ≥%95 + deposition/kill ≥%95 + ayrı crop-injury limiti."),
        ("6", "Lazer kolu", "Detection sağlamlaştıktan sonra stem/meristem keypoint, mm P50/P95 ve fiziksel kill testi."),
    ]
    y = 215
    for number, title, text in rows:
        card(draw, (70, y, 1850, y + 112), fill=WHITE, outline=LINE)
        draw.ellipse((95, y + 24, 155, y + 84), fill=GREEN)
        add_text(draw, (115, y + 34), number, 25, bold=True, fill=WHITE)
        add_text(draw, (185, y + 18), title, 27, bold=True, fill=DARK_GREEN)
        add_text(draw, (185, y + 58), text, 22, width=118)
        y += 127
    card(draw, (250, 970, 1670, 1005), fill=LIGHT_RED, outline=RED)
    add_text(draw, (500, 974), "Bugün: research PoC GO • saha püskürtmesi NO-GO", 23, bold=True, fill=RED)
    return page


def build_package(
    report_1024: dict[str, Any],
    report_1536: dict[str, Any],
    selected_gallery: Sequence[Path],
) -> dict[str, Any]:
    PACKAGE.mkdir(parents=True, exist_ok=True)
    copied: list[Path] = []
    for source, name in (
        (METRICS_1024, "spot_spray_ab_1024.json"),
        (METRICS_1536, "spot_spray_ab_1536_inference.json"),
        (TRAINING_RECEIPT, "detection_training_receipt.json"),
        (DATASET_RECEIPT, "detection_dataset_receipt.json"),
        (MARKDOWN_PATH, "README.md"),
    ):
        destination = PACKAGE / name
        shutil.copy2(source, destination)
        copied.append(destination)
    gallery_output = PACKAGE / "examples"
    gallery_output.mkdir(exist_ok=True)
    for source in selected_gallery:
        destination = gallery_output / source.name
        shutil.copy2(source, destination)
        copied.append(destination)
    local_pdf = PACKAGE / PDF_PATH.name
    shutil.copy2(PDF_PATH, local_pdf)
    copied.append(local_pdf)
    receipt = {
        "schema_version": 1,
        "status": "offline_research_benchmark_complete_not_field_validated",
        "metrics_1024_gate": report_1024["decision_gate"],
        "metrics_1536_gate": report_1536["decision_gate"],
        "files": [
            {
                "path": str(path.relative_to(PACKAGE)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in copied
        ],
    }
    receipt_path = PACKAGE / "package_receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> None:
    report_1024 = load(METRICS_1024)
    report_1536 = load(METRICS_1536)
    examples = [
        GALLERY / "04_Image_20231206120126538.jpg",
        GALLERY / "01_Image_20231206115739783.jpg",
    ]
    for path in examples:
        if not path.is_file():
            raise FileNotFoundError(path)
    pages = [
        cover(report_1024),
        architecture_page(),
        definition_page(),
        ab_page(report_1024),
        recall_tradeoff_page(report_1024),
        size_page(report_1024),
        resolution_page(report_1024, report_1536),
        visual_detection_page(examples[0]),
        visual_pose_page(examples[0]),
        next_steps_page(),
    ]
    finalize_pages(pages, "Detection-only spot-spray benchmark v1")
    save_pdf(pages, PDF_PATH, title="Detection-only spot-spray benchmark v1")
    receipt = build_package(report_1024, report_1536, examples)
    print(
        json.dumps(
            {
                "pdf": str(PDF_PATH),
                "pdf_sha256": sha256(PDF_PATH),
                "pages": len(pages),
                "package": str(PACKAGE),
                "package_files": len(receipt["files"]),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
