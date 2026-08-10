#!/usr/bin/env python3
"""Build the readable fair target-trained detection/segmentation decision PDF."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw

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
    paste_contain,
    save_pdf,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
EVALUATION_ROOT = DATA_ROOT / "runs/phenobench_detect_segment_fair_v1/fair_evaluation_v1"
METRICS_PATH = EVALUATION_ROOT / "fair_ab_metrics.json"
PDF_PATH = PROJECT_ROOT / "docs/results/FAIR_DETECTION_SEGMENTATION_KARARI_V1.pdf"
MARKDOWN_PATH = PROJECT_ROOT / "docs/FAIR_DETECTION_SEGMENTATION_KARARI_V1.md"
METRICS_COPY = PROJECT_ROOT / "docs/results/fair_detection_segmentation_metrics_v1.json"
GALLERY_COPY = PROJECT_ROOT / "docs/results/fair_detection_segmentation_gallery_v1"
PACKAGE = DATA_ROOT / "processed/audits/fair_detection_segmentation_decision_v1"


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
    return f"%{100.0 * float(value):.{digits}f}".replace(".", ",")


def ms(value: float) -> str:
    return f"{float(value):.1f} ms".replace(".", ",")


def portable_filename(name: str) -> str:
    """Keep copied report assets checkout-safe on Windows as well as Linux."""
    return name.replace(":", "__")


def action_metric(metrics: Mapping[str, Any], method: str) -> Mapping[str, Any]:
    return metrics["test"][method]


def verdict(metrics: Mapping[str, Any]) -> tuple[str, tuple[int, int, int]]:
    if metrics["segmentation_preference_gate"]["passed"]:
        return "SEGMENTATION TABANI TERCIH EDILEBILIR", GREEN
    return "SPREY POC ICIN DETECTION ONDE", ORANGE


def cover(metrics: Mapping[str, Any]) -> Image.Image:
    detector = action_metric(metrics, "detect_box_center")
    segmenter = action_metric(metrics, "segment_deepest_interior")
    decision, accent = verdict(metrics)
    page = Image.new("RGB", (W, H), DARK_GREEN)
    draw = ImageDraw.Draw(page)
    card(draw, (70, 60, 1850, 1015), fill=BG, outline=BG, radius=38)
    add_text(draw, (125, 105), "Adil detection vs segmentation", 62, bold=True, fill=DARK_GREEN)
    add_text(draw, (128, 188), "Iki model de ayni gercek bitkileri gordu", 37, bold=True, fill=GREEN)
    add_text(draw, (130, 247), "PhenoBench • YOLO26s • 1024 px • 50 epoch • parsel-ayri test", 23, fill=MUTED)
    card(draw, (125, 320, 1795, 492), fill=LIGHT_ORANGE if accent == ORANGE else LIGHT_GREEN, outline=accent)
    add_text(draw, (165, 348), "KISA KARAR", 22, bold=True, fill=accent)
    add_text(draw, (165, 397), decision, 39, bold=True, fill=accent, width=73)
    metric_card(page, (125, 555, 630, 805), pct(detector["f1"]), "Detection action F1", "Weed kutu merkezi exact GT ot dokusuna temas.", accent=BLUE)
    metric_card(page, (660, 555, 1165, 805), pct(segmenter["f1"]), "Segment action F1", "Tahmin maskesinin en guvenli ic noktasi.", accent=GREEN)
    difference = 100.0 * (float(segmenter["f1"]) - float(detector["f1"]))
    metric_card(page, (1195, 555, 1700, 805), f"{difference:+.1f} puan".replace(".", ","), "Segment − detect", "Ayni test, val'de ayri optimize edilmis esikler.", accent=accent)
    add_text(draw, (130, 865), "Bu temiz mimari/gorev kontroludur; UAV seker pancari verisi nihai robot-kamera saha onayi degildir.", 27, bold=True, fill=RED, width=106)
    return page


def fairness_page(metrics: Mapping[str, Any]) -> Image.Image:
    page = base_page("Bu kez karsilastirma gercekten eslenmis", "Zero-shot segmenter ile target-trained detector farki mimari sonucu olarak kullanilmadi.")
    draw = ImageDraw.Draw(page)
    rows = [
        ["Goruntu", "Ayni", "1.407 train / 369 val / 403 test"],
        ["Bitki ornegi", "Ayni", "Ayni publisher instance maskesi"],
        ["Etiket turetme", "Eslenmis", "Maske → exact kutu veya poligon"],
        ["Model / raster", "Ayni aile", "YOLO26s; 9,95M vs 11,44M; native 1024"],
        ["Egitim", "Ayni", "50 epoch, batch 8, seed 17, augmentation"],
        ["Secim", "Ayni kural", "last.pt; confidence yalniz val'de"],
    ]
    draw_table(page, (70, 220, 1850, 745), ("Kontrol", "Durum", "Sozlesme"), rows, (0.23, 0.18, 0.59), font_size=24, row_height=74)
    card(draw, (110, 810, 1810, 955), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (155, 842), "Test, val esikleri locked_validation_calibration.json dosyasina yazildiktan sonra ilk kez calistirildi. Segmentasyonun kutu-merkezi kontrolu de ayni segmenter tahminlerinden gelir; maske noktasinin ek degerini ayirir.", 25, bold=True, fill=BLUE, width=110)
    return page


def results_page(metrics: Mapping[str, Any]) -> Image.Image:
    rows = []
    labels = (
        ("detect_box_center", "Detection → kutu merkezi"),
        ("segment_deepest_interior", "Segment → guvenli maske ici"),
        ("segment_box_center", "Segment → kutu merkezi kontrol"),
    )
    for method, label in labels:
        item = action_metric(metrics, method)
        rows.append(
            [
                label,
                pct(item["precision"]),
                pct(item["recall"]),
                pct(item["f1"]),
                pct(item["crop_collision_rate_per_attempt"]),
                str(item["attempted_actions"]),
            ]
        )
    page = base_page("Ana sonuc: exact dokuya bir-bitki/bir-atis", "TP = ilk noktanin uygun GT weed dokusuna temasi; duplicate, toprak veya crop temasi FP.")
    draw_table(
        page,
        (45, 225, 1875, 545),
        ("Yontem", "Precision", "Recall", "F1", "Crop riski", "Atis"),
        rows,
        (0.36, 0.13, 0.13, 0.13, 0.14, 0.11),
        font_size=24,
        row_height=78,
        align_right=(1, 2, 3, 4, 5),
    )
    draw = ImageDraw.Draw(page)
    standard = metrics["standard_test_metrics"]
    detect_map = standard["detect"]["results"]["metrics/mAP50-95(B)"]
    segment_box_map = standard["segment"]["results"]["metrics/mAP50-95(B)"]
    segment_mask_map = standard["segment"]["results"]["metrics/mAP50-95(M)"]
    metric_card(page, (75, 650, 590, 910), pct(detect_map), "Detection box mAP50–95", "Standart instance kutu metrigi.", accent=BLUE)
    metric_card(page, (700, 650, 1215, 910), pct(segment_box_map), "Segment box mAP50–95", "Ayni segment head'in kutulari.", accent=GREEN)
    metric_card(page, (1325, 650, 1840, 910), pct(segment_mask_map), "Segment mask mAP50–95", "Gelecek doku/lazer ihtiyaci icin.", accent=ORANGE)
    return page


def recall_gate_page(metrics: Mapping[str, Any]) -> Image.Image:
    page = base_page("%95 recall politikasi gercekte neye mal oluyor?", "Esik validation'da secildi; tablo untouched test sonucudur. Ana karar balanced-F1 politikasindandir.")
    rows = []
    labels = (
        ("detect_box_center", "Detection → kutu merkezi"),
        ("segment_deepest_interior", "Segment → guvenli maske ici"),
    )
    for method, label in labels:
        item = metrics["test_recall_95_policy"][method]
        metric = item["metrics"]
        rows.append(
            [
                label,
                "Evet" if item["validation_target_attainable"] else "Hayir",
                pct(metric["precision"]),
                pct(metric["recall"]),
                pct(metric["f1"]),
                pct(metric["crop_collision_rate_per_attempt"]),
            ]
        )
    draw_table(
        page,
        (55, 250, 1865, 515),
        ("Yontem", "Val %95?", "Test P", "Test R", "Test F1", "Crop riski"),
        rows,
        (0.34, 0.13, 0.13, 0.13, 0.13, 0.14),
        font_size=24,
        row_height=82,
        align_right=(2, 3, 4, 5),
    )
    draw = ImageDraw.Draw(page)
    card(draw, (100, 625, 1820, 915), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (145, 665), "Nasil okunmali?", 31, bold=True, fill=ORANGE)
    bullet_list(
        page,
        [
            "%95 recall tek basina yeterli degil: cok false action precision'i ve crop guvenligini dusurebilir.",
            "Hedefimiz deploy testinde precision ve recall'in birlikte yaklasik %95 olmasi; F1 bunu ozetler.",
            "Bu tablo %95 recall'in val'de bile ulasilamaz olup olmadigini da acikca gosterir.",
        ],
        (145, 735),
        width=105,
        size=25,
    )
    return page


def size_page(metrics: Mapping[str, Any]) -> Image.Image:
    detector = action_metric(metrics, "detect_box_center")["recall_by_sqrt_gt_box_area_px"]
    segmenter = action_metric(metrics, "segment_deepest_interior")["recall_by_sqrt_gt_box_area_px"]
    page = base_page("Kucuk weed darboğazi iki modelde nasil?", "Boyut = native/model 1024 rasterda sqrt(exact GT kutu alani). Her bar ayni GT bitkilerini kullanir.")
    draw = ImageDraw.Draw(page)
    labels = (("lt14", "<14 px"), ("14_to_lt28", "14–28 px"), ("28_to_lt56", "28–56 px"), ("ge56", "≥56 px"))
    y = 245
    for key, label in labels:
        d_value = float(detector[key]["recall"] or 0.0)
        s_value = float(segmenter[key]["recall"] or 0.0)
        total = int(detector[key]["total"])
        add_text(draw, (65, y), f"{label} (n={total})", 23, bold=True, width=17)
        left, width = 390, 1220
        draw.rounded_rectangle((left, y, left + width, y + 30), radius=12, fill=LINE)
        draw.rounded_rectangle((left, y, left + round(width * d_value), y + 30), radius=12, fill=BLUE)
        add_text(draw, (1635, y - 3), pct(d_value), 24, bold=True, fill=BLUE)
        draw.rounded_rectangle((left, y + 45, left + width, y + 75), radius=12, fill=LINE)
        draw.rounded_rectangle((left, y + 45, left + round(width * s_value), y + 75), radius=12, fill=GREEN)
        add_text(draw, (1635, y + 42), pct(s_value), 24, bold=True, fill=GREEN)
        y += 170
    card(draw, (480, 900, 1440, 972), fill=WHITE, outline=LINE)
    add_text(draw, (530, 920), "Mavi = detection kutu merkezi   •   Yesil = segmentation guvenli maske ici", 22, bold=True, width=73)
    return page


def visual_page(path: Path, title: str, subtitle: str, note: str, colour: tuple[int, int, int]) -> Image.Image:
    page = base_page(title, subtitle)
    paste_contain(page, path, (70, 205, 1850, 850))
    draw = ImageDraw.Draw(page)
    card(draw, (120, 875, 1800, 980), fill=WHITE, outline=colour)
    add_text(draw, (160, 902), note, 24, bold=True, fill=colour, width=112)
    return page


def segmentation_value_page(metrics: Mapping[str, Any]) -> Image.Image:
    tissue = metrics["segment_test_tissue_metrics"]
    timing = metrics["timing"]["test"]
    detector_ms = sum(
        float(timing["detect"][key])
        for key in (
            "model_preprocess_ms_per_image_mean",
            "model_inference_ms_per_image_mean",
            "framework_postprocess_ms_per_image_mean",
            "action_postprocess_ms_per_image_mean",
        )
    )
    segment_ms = sum(
        float(timing["segment"][key])
        for key in (
            "model_preprocess_ms_per_image_mean",
            "model_inference_ms_per_image_mean",
            "framework_postprocess_ms_per_image_mean",
            "action_postprocess_ms_per_image_mean",
        )
    )
    page = base_page("Segmentasyon neyi ekliyor?", "Sprey noktasi benzer olsa bile maske, daha dar ve farkli mudahaleler icin bilgi tasir.")
    metric_card(page, (80, 235, 570, 500), pct(tissue["weed"]["iou"]), "Weed tissue IoU", "Secilmis action esiginde pixel IoU.", accent=GREEN)
    metric_card(page, (715, 235, 1205, 500), pct(tissue["crop"]["iou"]), "Crop tissue IoU", "No-fire/safety maskesi icin.", accent=BLUE)
    metric_card(page, (1350, 235, 1840, 500), pct(tissue["macro_iou"]), "Macro tissue IoU", "Weed + crop ortalamasi.", accent=ORANGE)
    draw = ImageDraw.Draw(page)
    card(draw, (80, 590, 880, 915), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (120, 625), "Gelecek mudahale", 30, bold=True, fill=DARK_GREEN)
    bullet_list(page, ["Nozul footprint'ini weed maskesi icinde tutma", "Lazer icin meristem/keypoint'e gecis", "Mekanik temas ve crop no-go bolgesi"], (120, 690), width=46, size=24)
    card(draw, (1040, 590, 1840, 915), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (1080, 625), "Hesap maliyeti", 30, bold=True, fill=BLUE)
    add_text(draw, (1080, 700), f"Detection: {ms(detector_ms)} / kare\nSegmentasyon: {ms(segment_ms)} / kare\nOran: {metrics['segmentation_preference_gate']['latency_ratio_segment_over_detect']:.2f}x".replace(".", ","), 31, bold=True, width=42)
    add_text(draw, (1080, 835), "Offline batch olcumu; kamera aktarimi ve tracking dahil degil.", 21, fill=MUTED, width=53)
    add_text(draw, (120, 940), "Model: 9,95M vs 11,44M parametre; train: 23,9 vs 59,3 dk. Maske etiketi kutudan daha pahalidir; bu esit annotation-dakikasi deneyi degildir.", 19, bold=True, fill=MUTED, width=125)
    return page


def old_comparison_page() -> Image.Image:
    page = base_page("Onceki dusuk segmentasyon skoru ne anlatiyordu?", "WSD detector target train, global segmenter zero-shot idi; o test saf mimari A/B degildi.")
    draw = ImageDraw.Draw(page)
    card(draw, (75, 230, 875, 815), fill=LIGHT_RED, outline=RED)
    add_text(draw, (115, 270), "ESKI KIYAS", 26, bold=True, fill=RED)
    bullet_list(page, ["Detector WSD kutularini gordu", "Segmenter 0 WSD goruntusu gordu", "Sonuc mimari + domain adaptasyonu karisimiydi", "Mimari secimde kullanilmadi"], (115, 350), width=44, size=27)
    card(draw, (1045, 230, 1845, 815), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (1085, 270), "YENI KIYAS", 26, bold=True, fill=GREEN)
    bullet_list(page, ["Ikisi de ayni real train'i gordu", "Kutu ve maske ayni instance'tan", "Test parselleri untouched", "Fark task head + aksiyon temsili"], (1085, 350), width=44, size=27)
    card(draw, (220, 860, 1700, 965), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (265, 890), "Eski deney yine de degerli: hedef-domain gercek veri gormenin kritik oldugunu gosterdi. Yalniz 'detection segmentasyondan ustun' demiyordu.", 26, bold=True, fill=BLUE, width=96)
    return page


def final_page(metrics: Mapping[str, Any]) -> Image.Image:
    gate = metrics["segmentation_preference_gate"]
    decision, accent = verdict(metrics)
    page = base_page("Karar ve gercek saha anlami", "Bu benchmark hangi temeli sececegimizi soyler; saha atesleme izni vermez.")
    draw = ImageDraw.Draw(page)
    card(draw, (70, 220, 900, 760), fill=LIGHT_GREEN if gate["passed"] else LIGHT_ORANGE, outline=accent)
    add_text(draw, (110, 255), decision, 32, bold=True, fill=accent, width=38)
    checks = gate["checks"]
    labels = {
        "f1_within_allowed_drop": "F1 marji",
        "recall_within_allowed_drop": "Recall marji",
        "crop_collision_within_allowed_increase": "Crop guvenligi",
        "latency_ratio_allowed": "Gecikme ≤2x",
    }
    y = 390
    for key, label in labels.items():
        value = "GECTI" if checks[key] else "KALDI"
        colour = GREEN if checks[key] else RED
        add_text(draw, (120, y), f"{label}: {value}", 26, bold=True, fill=colour)
        y += 72
    card(draw, (1020, 220, 1850, 760), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (1060, 255), "Saha icin siradaki kapilar", 31, bold=True, fill=BLUE)
    bullet_list(page, ["Robot kamera/FOV/focus ile deploy-benzeri real veri", "Session/tarla-ayri untouched test", "Video tracking + bir-bitki/bir-atis", "Nozul footprint, kill ve crop injury bench testi", "Ticari kullanim icin veri/model lisansini degistir"], (1060, 335), width=46, size=23)
    bootstrap = metrics["paired_bootstrap"]
    low, high = (100.0 * float(value) for value in bootstrap["ci95"])
    card(draw, (120, 825, 1800, 965), fill=WHITE, outline=LINE)
    add_text(draw, (165, 852), f"Paired test-image bootstrap: segment − detect F1 %95 GA [{low:+.2f}, {high:+.2f}] puan. Tek seed ve UAV domaini nedeniyle bu aralik final saha garantisi degildir.".replace(".", ","), 25, bold=True, width=108)
    return page


def write_markdown(metrics: Mapping[str, Any]) -> None:
    detector = action_metric(metrics, "detect_box_center")
    segmenter = action_metric(metrics, "segment_deepest_interior")
    control = action_metric(metrics, "segment_box_center")
    tissue = metrics["segment_test_tissue_metrics"]
    standard = metrics["standard_test_metrics"]
    detect_timing = metrics["timing"]["test"]["detect"]
    segment_timing = metrics["timing"]["test"]["segment"]
    detect_threshold = metrics["calibration"]["detect_box_center"]["selection"]["balanced_max_f1"]["threshold"]
    segment_threshold = metrics["calibration"]["segment_deepest_interior"]["selection"]["balanced_max_f1"]["threshold"]
    size_rows = []
    size_labels = (("lt14", "<14 px"), ("14_to_lt28", "14–28 px"), ("28_to_lt56", "28–56 px"), ("ge56", "≥56 px"))
    for key, label in size_labels:
        detect_bin = detector["recall_by_sqrt_gt_box_area_px"][key]
        segment_bin = segmenter["recall_by_sqrt_gt_box_area_px"][key]
        size_rows.append(
            f"| {label} | {detect_bin['total']} | {pct(detect_bin['recall'])} | {pct(segment_bin['recall'])} |"
        )
    decision, _ = verdict(metrics)
    text = f"""# Adil detection vs segmentation karari v1

## Kisa karar

**{decision}.** Bu sonuc, iki modelin de ayni 1.407 gercek PhenoBench train goruntusunu ve ayni publisher bitki instance'larini gordugu eslenmis A/B'den gelir.

| Yontem | Precision | Recall | F1 | Crop temas riski |
|---|---:|---:|---:|---:|
| Detection → kutu merkezi | {pct(detector['precision'])} | {pct(detector['recall'])} | {pct(detector['f1'])} | {pct(detector['crop_collision_rate_per_attempt'])} |
| Segmentasyon → guvenli maske ici | {pct(segmenter['precision'])} | {pct(segmenter['recall'])} | {pct(segmenter['f1'])} | {pct(segmenter['crop_collision_rate_per_attempt'])} |
| Segmentasyon → kutu merkezi kontrol | {pct(control['precision'])} | {pct(control['recall'])} | {pct(control['f1'])} | {pct(control['crop_collision_rate_per_attempt'])} |

TP, bir weed'e yapilan ilk aksiyon noktasinin exact publisher weed dokusuna temasidir. Ayni weed'e ikinci aksiyon, toprak veya crop temasi FP'dir. Kismi bitkiler ignore edilir. Confidence esikleri yalniz validation'da secilip testten once dosyaya kilitlenmistir.

Validation'da secilen balanced-F1 confidence esikleri detection icin `{detect_threshold:.2f}`, segmentation icin `{segment_threshold:.2f}`'dir. Testte tekrar secim veya sweep yapilmadi.

## Kucuk weed sonucu

Boyut, native/model 1024 rasterda `sqrt(exact GT instance kutu alani)` olarak tanimlidir.

| Boyut | GT weed | Detection recall | Segmentation recall |
|---|---:|---:|---:|
{chr(10).join(size_rows)}

## Standart ve maske metrikleri

- Detection box mAP50–95: {pct(standard['detect']['results']['metrics/mAP50-95(B)'])}
- Segmenter box mAP50–95: {pct(standard['segment']['results']['metrics/mAP50-95(B)'])}
- Segmenter mask mAP50–95: {pct(standard['segment']['results']['metrics/mAP50-95(M)'])}
- Segmenter weed/crop tissue IoU: {pct(tissue['weed']['iou'])} / {pct(tissue['crop']['iou'])}; macro {pct(tissue['macro_iou'])}

Bu standart metrikler yardimci teshistir. Mimari kararin ana metrigi, iki model icin de ayni exact-doku one-to-one aksiyon F1/recall/crop temasidir.

## Neden adil?

- Ayni RGB kareleri, splitler ve uygun bitki instance'lari.
- Kutu ve poligon ayni publisher instance maskesinden turetildi.
- Ayni YOLO26s ailesi, native 1024 raster, 50 epoch, batch 8, seed 17 ve augmentation.
- Ikisi de hedef gercek train verisini gordu; zero-shot kol yok.
- Checkpoint iki kolda da sabit son epoch (`last.pt`).

PhenoBench resmi train bolgesinin 1.407 goruntusu train olarak kaldi. Resmi validation bolgesindeki P-parsel gruplari, her uc cekim tarihi iki tarafta da temsil edilecek bicimde 369 calibration ve 403 untouched test goruntusune ayrildi. Testte 1.754 uygun tam weed ve 2.654 uygun tam crop instance'i vardir. Train/val/test arasinda goruntu yolu cakismasi, val/test arasinda P-parsel cakismasi yoktur.

Task-eslesmis resmi COCO pretrained `yolo26s.pt` ve `yolo26s-seg.pt` baslangiclari kullanildi. Backbone olcegi aynidir; task head ve buna bagli parametre/FLOP farki gercek sistem maliyeti olarak tutulup latency ile raporlandi. Test batch-{detect_timing['batch']} offline olcumunde framework + action toplamlarinin ham parcasi JSON'da bulunur: detection inference {detect_timing['model_inference_ms_per_image_mean']:.2f} ms, segmentation inference {segment_timing['model_inference_ms_per_image_mean']:.2f} ms; maske transferi ve deepest-interior islemi ayrica `action_postprocess_ms_per_image_mean` alanindadir.

Egitilmis modeller detection icin {metrics['locked_arms']['detect']['trained_parameter_count'] / 1_000_000:.2f}M, segmentasyon icin {metrics['locked_arms']['segment']['trained_parameter_count'] / 1_000_000:.2f}M parametredir. Duvar-saat egitim sureleri sirasiyla {metrics['locked_arms']['detect']['training_elapsed_seconds'] / 60:.1f} ve {metrics['locked_arms']['segment']['training_elapsed_seconds'] / 60:.1f} dakikadir. Ayni epoch/goruntu butcesi kullanildi; segmentasyonun daha buyuk head'i ve ek mask loss'u gercek pipeline maliyeti olarak saklandi.

Supervision ayni source instance'lara dayanir ama maskeler kutulardan daha zengin ve gercekte daha pahali etikettir. Bu nedenle deney adil bir target-trained task-pipeline A/B'sidir; esit annotation-dakikasi maliyet analizi degildir.

Paired 403 test-kare bootstrap'inda segment−detect F1 farkinin %95 araligi `[{100*metrics['paired_bootstrap']['ci95'][0]:+.2f}, {100*metrics['paired_bootstrap']['ci95'][1]:+.2f}]` puandir. Bu, test kareleri uzerindeki ornekleme belirsizligidir; tek-seed egitim varyansini kapsamaz.

## Sinir

Bu, PhenoBench UAV seker pancari domaininde temiz bir mimari/gorev kontroludur. Nihai robot kamerasi, video tracking, nozul footprint, deposition, kill rate ve crop injury olculmedi. Dolayisiyla saha atesleme onayi degildir.

Lisans siniri da vardir: PhenoBench `CC BY-NC-SA 4.0`, Ultralytics baseline ise `AGPL-3.0` veya enterprise lisanslidir. Bu agirliklar ticari deployment adayi degil, arastirma mimari kanitidir; urun modeli uygun lisansli kendi verimizle yeniden egitilmelidir.

Onceki WSD sonucu hedef kutularini gormus detector ile WSD'yi hic gormemis global segmenteri karsilastiriyordu. O sonuc, hedef-domain gercek veri gormenin etkisini kanitlar; saf detection-vs-segmentation karari degildir ve burada mimari gate'e dahil edilmedi.

## Dosyalar

- [Okunabilir PDF](results/FAIR_DETECTION_SEGMENTATION_KARARI_V1.pdf)
- [Dondurulmus metrik JSON](results/fair_detection_segmentation_metrics_v1.json)
- [Aciklamali ornekler](results/fair_detection_segmentation_gallery_v1/README.md)
"""
    MARKDOWN_PATH.write_text(text, encoding="utf-8")


def copy_artifacts(metrics: Mapping[str, Any]) -> None:
    METRICS_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(METRICS_PATH, METRICS_COPY)
    GALLERY_COPY.mkdir(parents=True, exist_ok=False)
    for source_text in metrics["gallery"]:
        source = Path(source_text)
        shutil.copy2(source, GALLERY_COPY / portable_filename(source.name))
    shutil.copy2(EVALUATION_ROOT / "gallery/README.md", GALLERY_COPY / "README.md")


def build_package(metrics: Mapping[str, Any]) -> dict[str, Any]:
    PACKAGE.mkdir(parents=True, exist_ok=False)
    files = [PDF_PATH, MARKDOWN_PATH, METRICS_COPY]
    for source in files:
        shutil.copy2(source, PACKAGE / source.name)
    shutil.copytree(GALLERY_COPY, PACKAGE / GALLERY_COPY.name)
    packaged = sorted(path for path in PACKAGE.rglob("*") if path.is_file())
    receipt = {
        "schema_version": 1,
        "status": "fair_target_trained_research_ab_not_field_validated",
        "source_metrics_sha256": sha256(METRICS_PATH),
        "decision": verdict(metrics)[0],
        "files": [
            {
                "path": str(path.relative_to(PACKAGE)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in packaged
        ],
    }
    (PACKAGE / "package_receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main() -> None:
    metrics = load(METRICS_PATH)
    gallery = [Path(path) for path in metrics["gallery"]]
    if len(gallery) < 4 or not all(path.is_file() for path in gallery):
        raise ValueError("Expected at least four fair-evaluation gallery images")
    pages = [
        cover(metrics),
        fairness_page(metrics),
        results_page(metrics),
        recall_gate_page(metrics),
        size_page(metrics),
        visual_page(gallery[0], "Basarili test ornegi", "Uc panel de ayni untouched test goruntusunu gosterir.", "Yesil nokta exact GT weed dokusuna temas eder. Sol panel publisher GT; orta target-trained detector; sag target-trained segmenter.", GREEN),
        visual_page(gallery[1], "Zor test ornegi", "En dusuk ortak aksiyon basarili orneklerden biri.", "Kirmizi noktalar crop/toprak hatasini, kacirilan mor alanlar recall kaybini gorunur yapar. Tek kare yerine toplu metrik karar verir.", RED),
        visual_page(gallery[2], "Modellerin ayrildigi ornek", "Bu kare segmentasyon lehine en belirgin paired farklardan biri.", "Maske-ici nokta, kutu merkezinin kacirdigi duzensiz weed dokusuna temas edebilir; tersi ornekler de galeride bulunur.", BLUE),
        segmentation_value_page(metrics),
        old_comparison_page(),
        final_page(metrics),
    ]
    finalize_pages(pages, "Adil detection vs segmentation karari v1")
    save_pdf(pages, PDF_PATH, title="Adil detection vs segmentation karari v1")
    write_markdown(metrics)
    copy_artifacts(metrics)
    receipt = build_package(metrics)
    print(
        json.dumps(
            {
                "pdf": str(PDF_PATH),
                "pdf_sha256": sha256(PDF_PATH),
                "pages": len(pages),
                "metrics_copy": str(METRICS_COPY),
                "gallery": str(GALLERY_COPY),
                "package": str(PACKAGE),
                "package_files": len(receipt["files"]),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
