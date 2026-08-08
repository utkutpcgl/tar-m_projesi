#!/usr/bin/env python3
"""Build the readable point-intervention PoC report from frozen artifacts.

The report intentionally separates semantic-pixel diagnostics from the
one-to-one weed-stem action metric needed by a point actuator.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from PIL import Image, ImageDraw

try:
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
        font,
        metric_card,
        paste_contain,
        pct,
        save_pdf,
    )
except ModuleNotFoundError:
    from build_intervention_reports import (  # type: ignore[no-redef]
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
        font,
        metric_card,
        paste_contain,
        pct,
        save_pdf,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
SEMANTIC_PATH = (
    DATA_ROOT
    / "processed/audits/small_object_selected_intervention_v1/selected/"
    "sugarbeets_robot_holdout.json"
)
ROW_PATH = DATA_ROOT / "processed/audits/crop_row_prior_v1/sugarbeets_robot_holdout.json"
BASE_RUN = DATA_ROOT / "runs/wsd_pose_poc_v1/yolo26s_pose_1024_seed17"
HIGH_RUN = DATA_ROOT / "runs/wsd_pose_poc_v1/yolo26s_pose_1536_finetune_seed17"
BASE_ACTION_PATH = BASE_RUN / "action_metrics_v2_img1024/action_metrics.json"
HIGH_ACTION_PATH = HIGH_RUN / "action_metrics_v2_img1536/action_metrics.json"
CONTACT_SHEET = DATA_ROOT / "processed/audits/weed_stem_detection_v1_contact_sheet.jpg"
HIGH_GALLERY = HIGH_RUN / "action_metrics_v2_img1536/gallery"
OUTPUT_DIR = DATA_ROOT / "processed/audits/point_intervention_poc_v1"
PDF_PATH = PROJECT_ROOT / "docs/results/BASLA_BURADAN_NOKTASAL_MUDAHALE_POC.pdf"
MARKDOWN_PATH = PROJECT_ROOT / "docs/NOKTASAL_MUDAHALE_POC_V1.md"
RECEIPT_PATH = OUTPUT_DIR / "build_receipt.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def f1(precision: float, recall: float) -> float:
    return 2.0 * precision * recall / (precision + recall)


def tolerance_key(kind: str, value: int) -> str:
    if kind == "fraction":
        return f"box_diagonal_fraction_{value / 100:.2f}"
    return f"pixels_{value}"


def action_metric(
    report: dict[str, Any],
    mode: str,
    *,
    kind: str = "fraction",
    value: int = 10,
) -> dict[str, Any]:
    return report["test"]["stem_action_modes"][mode]["test_by_tolerance"][
        tolerance_key(kind, value)
    ]


def action_threshold(report: dict[str, Any], mode: str) -> float:
    return float(report["test"]["stem_action_modes"][mode]["selection"]["threshold"])


def percent(value: float, digits: int = 1) -> str:
    return f"%{100.0 * value:.{digits}f}".replace(".", ",")


def pp(value: float, digits: int = 1) -> str:
    return f"{100.0 * value:+.{digits}f} puan".replace(".", ",")


def read_data() -> dict[str, Any]:
    semantic_raw = load_json(SEMANTIC_PATH)
    semantic = semantic_raw["overall"]
    row = load_json(ROW_PATH)
    base = load_json(BASE_ACTION_PATH)
    high = load_json(HIGH_ACTION_PATH)
    resolution: list[dict[str, Any]] = []
    for size in (768, 1024, 1536, 2048):
        if size == 1024:
            result = base
        else:
            result = load_json(
                BASE_RUN / f"action_metrics_v1_img{size}/action_metrics.json"
            )
        metric = action_metric(result, "keypoint_deduplicated_balanced_max_f1")
        resolution.append({"name": f"1024 model / {size} inference", **metric})
    resolution.append(
        {
            "name": "1536 fine-tune / 1536 inference",
            **action_metric(high, "keypoint_deduplicated_balanced_max_f1"),
        }
    )
    return {
        "semantic": semantic,
        "semantic_policy": semantic_raw["frozen_safety_policy"],
        "row": row,
        "base": base,
        "high": high,
        "resolution": resolution,
    }


def cover_page(data: dict[str, Any]) -> Image.Image:
    best = action_metric(data["high"], "keypoint_deduplicated_balanced_max_f1")
    page = Image.new("RGB", (W, H), DARK_GREEN)
    draw = ImageDraw.Draw(page)
    card(draw, (70, 60, 1850, 1015), fill=BG, outline=BG, radius=38)
    add_text(draw, (125, 116), "Noktasal bitki müdahalesi PoC", 63, bold=True, fill=DARK_GREEN)
    add_text(draw, (128, 202), "Segmentasyon, keypoint, sıra bilgisi ve video kararı", 32, fill=GREEN)
    add_text(draw, (130, 262), "8 Ağustos 2026 • gerçek robot görüntüsü • tarih-ayrı test", 23, fill=MUTED)
    card(draw, (125, 340, 1795, 525), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (168, 373), "DÜZELTİLMİŞ ANA SONUÇ", 23, bold=True, fill=ORANGE)
    add_text(
        draw,
        (168, 418),
        "%9,7 gerçek bitki müdahale recall'ı değildi. Doğrudan sap noktası PoC'si %69,2 F1 verdi; %95 kapısı geçilmedi.",
        35,
        bold=True,
        width=84,
    )
    metric_card(page, (125, 594, 630, 840), percent(best["precision"]), "Precision", "Verilen aksiyonların doğru weed sapına isabeti.", accent=BLUE)
    metric_card(page, (660, 594, 1165, 840), percent(best["recall"]), "Recall", "Etiketli weed saplarının yakalanan oranı.", accent=GREEN)
    metric_card(page, (1195, 594, 1700, 840), percent(best["f1"]), "Müdahale F1", "10% bitki-kutusu köşegeni toleransı, tekil aksiyon.", accent=RED)
    add_text(
        draw,
        (130, 895),
        "Karar: segmentasyonu atma; fakat lazer/mekanik komutu detection + stem/root keypoint başından üret. Video tarafında world-coordinate track + tek-sefer ateşleme kullan.",
        26,
        bold=True,
        fill=DARK_GREEN,
        width=109,
    )
    return page


def semantic_page(data: dict[str, Any]) -> Image.Image:
    sem = data["semantic"]
    policy = data["semantic_policy"]
    weed_p = sem["semantic_segmentation"]["precision"]["other_vegetation"]
    weed_r = sem["semantic_segmentation"]["recall"]["other_vegetation"]
    weed_f1 = f1(weed_p, weed_r)
    safe = sem["frozen_safe_pixel_metrics"]
    page = base_page("%9,7 neydi?", "Bir bitkiyi bulma oranı değil; çok katı bir piksel politikasının weed-pixel recall'ıydı.")
    metric_card(page, (70, 205, 525, 440), f"{sem['semantic_segmentation']['mean_iou']:.3f}".replace(".", ","), "mIoU", "283 gerçek SugarBeets robot karesi.", accent=GREEN)
    metric_card(page, (555, 205, 1010, 440), percent(weed_f1), "Weed pixel F1", f"P {percent(weed_p)} • R {percent(weed_r)}", accent=BLUE)
    metric_card(page, (1040, 205, 1495, 440), percent(safe["safe_weed_pixel_recall"]), "Safe pixel recall", f"Weed eşiği {policy['weed_threshold']:.2f}; uncertainty + crop guard.", accent=RED)
    metric_card(page, (1525, 205, 1850, 440), percent(safe["crop_spray_risk_per_crop_pixel"]), "Crop-pixel risk", "Yalnız bu frozen policy için.", accent=ORANGE)
    card(draw := ImageDraw.Draw(page), (70, 495, 1850, 930), fill=WHITE)
    add_text(draw, (110, 535), "Neden müdahale metriği değil?", 32, bold=True, fill=DARK_GREEN)
    bullet_list(
        page,
        [
            "Pixel recall, her botanik weed'e bir kez isabet edildi mi sorusunu cevaplamaz; büyük bitkiler sonucu domine edebilir.",
            "Connected component gerçek bitki ID'si değildir; birbirine değen yapraklar birleşir, tek bitki parçalanabilir.",
            "0,99 weed eşiği hedef veri için optimize edilmemişti. Düşük recall burada ‘model hiçbir şey görmüyor’ değil, ‘policy çoğu noktada ateşlemiyor’ demekti.",
            "Bu nedenle gerçek PoC metriği: her GT weed sapına karşı tek aksiyon, tek-eşleşmeli precision/recall/F1.",
        ],
        (115, 600),
        width=112,
        size=25,
        line_gap=17,
    )
    return page


def protocol_page(data: dict[str, Any]) -> Image.Image:
    best = action_metric(data["high"], "keypoint_deduplicated_balanced_max_f1")
    page = base_page("Gerçek müdahale metriği", "Amaç: bir weed sapına bir doğru komut; tekrar atış ve boş atış FP sayılır.")
    draw = ImageDraw.Draw(page)
    boxes = [
        ((75, 225, 430, 440), "GT weed", "Kutusu + uzman tarafından işaretlenmiş sap/kök noktası", GREEN),
        ((505, 225, 860, 440), "Model", "weed/crop kutusu + weed keypoint + güven", BLUE),
        ((935, 225, 1290, 440), "Tek eşleşme", "Her tahmin ve her sap en fazla bir kez kullanılır", ORANGE),
        ((1365, 225, 1720, 440), "Doğru aksiyon", "Mesafe ≤10% GT weed kutusu köşegeni", RED),
    ]
    for box, title, note, accent in boxes:
        card(draw, box, fill=WHITE, outline=accent, width=4)
        add_text(draw, (box[0] + 24, box[1] + 28), title, 29, bold=True, fill=accent)
        add_text(draw, (box[0] + 24, box[1] + 86), note, 22, width=24)
    for x in (452, 882, 1312):
        draw.line((x, 332, x + 32, 332), fill=DARK_GREEN, width=7)
        draw.polygon(((x + 32, 322), (x + 52, 332), (x + 32, 342)), fill=DARK_GREEN)
    draw_table(
        page,
        (75, 515, 1720, 760),
        ["Split", "Tarih", "Görüntü", "Weed etiketi", "Kullanım"],
        [
            ["Train", "30 Kasım", "211", "1.437", "Ağırlık öğrenme"],
            ["Validation", "4 Aralık", "152", "1.576", "Eşik + dedupe yarıçapı"],
            ["Test", "6 Aralık", "148", "1.102 / 1.097 geçerli sap", "Dondurulmuş değerlendirme"],
        ],
        (0.18, 0.16, 0.14, 0.24, 0.28),
        font_size=21,
        row_height=58,
    )
    add_text(draw, (80, 810), f"Dondurulan seçim: conf ≥ {action_threshold(data['high'], 'keypoint_deduplicated_balanced_max_f1'):.2f} • aynı kare dedupe yarıçapı = 0,30 × küçük kutu köşegeni.", 27, bold=True, fill=DARK_GREEN)
    add_text(draw, (80, 870), "Not: yüksek-çözünürlük kararında bu test tarihi tekrar görüldü; artık development holdout'tur, untouched final test değildir.", 24, fill=RED, width=118)
    return page


def dataset_page() -> Image.Image:
    page = base_page("PoC verisi gerçek robot görüntüsü", "2048×2048 RGB; yaklaşık 1 m kamera yüksekliği; maize/soybean + weed sap noktaları.")
    paste_contain(page, CONTACT_SHEET, (70, 205, 1850, 845), background=WHITE)
    draw = ImageDraw.Draw(page)
    card(draw, (95, 860, 1825, 975), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (125, 888), "Veri uyarısı", 24, bold=True, fill=ORANGE)
    add_text(draw, (320, 888), "İndirilebilir arşivde 511 eşli kare var; makale 1.556 etiketli kare bildiriyor. Bu nedenle sonuç araştırma PoC'si, hedef tarla onayı değil.", 23, width=101)
    return page


def result_page(data: dict[str, Any]) -> Image.Image:
    best = action_metric(data["high"], "keypoint_deduplicated_balanced_max_f1")
    page = base_page("Mevcut en gerçekçi tek-kare sonucu", "1536 fine-tune • ayrı çekim tarihi • validation'da seçilmiş threshold ve dedupe.")
    metric_card(page, (75, 205, 565, 440), percent(best["precision"]), "Precision", f"TP {best['true_positive']} / aksiyon {best['actions']}", accent=BLUE)
    metric_card(page, (595, 205, 1085, 440), percent(best["recall"]), "Recall", f"{best['true_positive']} / {best['visible_ground_truth_stems']} weed sapı", accent=GREEN)
    metric_card(page, (1115, 205, 1605, 440), percent(best["f1"]), "F1", "10% kutu-köşegeni toleransı", accent=RED)
    metric_card(page, (1635, 205, 1850, 440), "0", "Crop→weed FP", "IoU≥0,50 crop kutusu eşleşmesi.", accent=GREEN)
    rows = []
    for kind, value, label in [
        ("fraction", 5, "≤%5 kutu köşegeni"),
        ("fraction", 10, "≤%10 kutu köşegeni"),
        ("fraction", 20, "≤%20 kutu köşegeni"),
        ("pixels", 5, "≤5 px"),
        ("pixels", 10, "≤10 px"),
        ("pixels", 20, "≤20 px"),
    ]:
        metric = action_metric(data["high"], "keypoint_deduplicated_balanced_max_f1", kind=kind, value=value)
        rows.append([label, percent(metric["precision"]), percent(metric["recall"]), percent(metric["f1"]), f"{metric['true_positive']}/{metric['false_positive']}/{metric['false_negative']}"])
    draw_table(page, (75, 500, 1850, 920), ["Doğru sayma toleransı", "P", "R", "F1", "TP / FP / FN"], rows, (0.34, 0.13, 0.13, 0.13, 0.27), font_size=22, row_height=58, align_right=(1, 2, 3, 4))
    overlap = best["crop_box_collision"]["0"]["rate_per_action"]
    add_text(draw := ImageDraw.Draw(page), (80, 945), f"Safety uyarısı: noktaların {percent(overlap)}'i bir GT crop bounding rectangle içinde. Dikdörtgen canopy/temas değil; yine de lazer için crop-mask + mm aktüatör testi açık kapıdır.", 22, bold=True, fill=RED, width=125)
    return page


def visual_page(filename: str, title: str, subtitle: str, finding: str) -> Image.Image:
    page = base_page(title, subtitle)
    paste_contain(page, HIGH_GALLERY / filename, (70, 195, 1850, 855), background=WHITE)
    draw = ImageDraw.Draw(page)
    card(draw, (85, 872, 1835, 975), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (115, 900), finding, 24, bold=True, width=112)
    return page


def dedupe_page(data: dict[str, Any]) -> Image.Image:
    raw = action_metric(data["high"], "keypoint_balanced_max_f1")
    dedup = action_metric(data["high"], "keypoint_deduplicated_balanced_max_f1")
    breakdown = raw["false_positive_breakdown"]
    page = base_page("Basit birleştirme gerçekten fayda sağladı", "Aynı karede aynı sapa yakın tahminlerden yalnızca en güvenlisini tutuyoruz.")
    metric_card(page, (85, 215, 580, 455), percent(raw["f1"]), "Ham keypoint F1", f"P {percent(raw['precision'])} • R {percent(raw['recall'])}", accent=ORANGE)
    metric_card(page, (615, 215, 1110, 455), percent(dedup["f1"]), "Dedupe F1", f"P {percent(dedup['precision'])} • R {percent(dedup['recall'])}", accent=GREEN)
    metric_card(page, (1145, 215, 1640, 455), pp(dedup["f1"] - raw["f1"]), "Net kazanç", "Validation'da yarıçap ve yeni threshold seçildi.", accent=BLUE)
    card(draw := ImageDraw.Draw(page), (85, 520, 1640, 890), fill=WHITE)
    add_text(draw, (125, 555), "Ham false-positive anatomisi", 30, bold=True, fill=DARK_GREEN)
    total = raw["false_positive"]
    rows = [
        ("Aynı sap için tekrar aksiyon", breakdown["duplicate_action_near_already_hit_stem"], BLUE),
        ("2× tolerans içinde yakın kaçırma", breakdown["stem_localization_near_miss_within_2x_tolerance"], ORANGE),
        ("Diğer / arka plan", breakdown["other_or_background"], RED),
        ("Crop'u weed sanma (IoU≥0,50)", breakdown["crop_as_weed_box_match"], GREEN),
    ]
    y = 625
    for label, value, color in rows:
        add_text(draw, (135, y), label, 23)
        draw.rounded_rectangle((650, y + 2, 1480, y + 32), radius=14, fill=(230, 234, 230))
        width = int(830 * value / max(1, total))
        if width:
            draw.rounded_rectangle((650, y + 2, 650 + width, y + 32), radius=14, fill=color)
        add_text(draw, (1510, y), f"{value} ({percent(value / total)})", 22, bold=True, fill=color)
        y += 62
    add_text(draw, (1680, 585), "Video tracking'in ilk işi", 25, bold=True, fill=DARK_GREEN, width=13)
    add_text(draw, (1680, 690), "Tekrar atışı engellemek ve tek-kare parazitini onay bekleterek bastırmak.", 22, fill=MUTED, width=13)
    return page


def resolution_page(data: dict[str, Any]) -> Image.Image:
    page = base_page("Çözünürlük sonucu", "Kör upscale yetmedi; train ve inference rasterı birlikte yükseltildiğinde sınırlı ama gerçek kazanç geldi.")
    rows = []
    for item in data["resolution"]:
        rows.append([item["name"], percent(item["precision"]), percent(item["recall"]), percent(item["f1"])])
    draw_table(page, (80, 215, 1370, 610), ["Model / inference raster", "P", "R", "F1"], rows, (0.55, 0.15, 0.15, 0.15), font_size=22, row_height=62, align_right=(1, 2, 3))
    draw = ImageDraw.Draw(page)
    x1, y1, x2, y2 = 1450, 245, 1815, 820
    draw.line((x1, y2, x2, y2), fill=INK, width=3)
    best_f1 = max(float(item["f1"]) for item in data["resolution"])
    for index, item in enumerate(data["resolution"]):
        value = float(item["f1"])
        bar_height = int((y2 - y1) * value)
        left = x1 + 12 + index * 67
        color = GREEN if value == best_f1 else BLUE
        draw.rounded_rectangle((left, y2 - bar_height, left + 43, y2), radius=8, fill=color)
        add_text(draw, (left - 5, y2 + 12), str(index + 1), 18, bold=True, fill=MUTED)
    draw.line((x1, y2 - int((y2 - y1) * 0.95), x2, y2 - int((y2 - y1) * 0.95)), fill=RED, width=4)
    add_text(draw, (1445, 180), "F1", 24, bold=True)
    add_text(draw, (1540, y1 - 30), "%95 hedef", 20, bold=True, fill=RED)
    card(draw, (80, 680, 1370, 925), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (115, 715), "Karar", 28, bold=True, fill=ORANGE)
    add_text(draw, (115, 770), "1536 fine-tune: %69,2 F1. 1024 tabanın en iyi 1024 inference sonucu: %66,2 F1. Kazanç yaklaşık +3,0 puan; hesap maliyeti artıyor ve deney equal-compute değil.", 27, bold=True, width=82)
    return page


def keypoint_page(data: dict[str, Any]) -> Image.Image:
    high = data["high"]
    key_5 = action_metric(high, "keypoint_balanced_max_f1", value=5)
    center_5 = action_metric(high, "box_center_balanced_max_f1", value=5)
    key_10 = action_metric(high, "keypoint_balanced_max_f1", value=10)
    center_10 = action_metric(high, "box_center_balanced_max_f1", value=10)
    page = base_page("Segmentasyon mu, detection + keypoint mi?", "Tek bir kazanan yerine görev ayrımı: algı bağlamı maskeden, fiziksel hedef keypoint'ten.")
    draw_table(
        page,
        (80, 220, 1110, 520),
        ["Tek-kare kontrol", "F1 @%5", "F1 @%10", "Ne söyler?"],
        [
            ["Weed box merkezi", percent(center_5["f1"]), percent(center_10["f1"]), "Ucuz; morfolojiye güveniyor"],
            ["Regrese sap keypoint", percent(key_5["f1"]), percent(key_10["f1"]), "Sıkı toleransta +%1,3 puan"],
        ],
        (0.27, 0.17, 0.17, 0.39),
        font_size=22,
        row_height=72,
    )
    cards = [
        ((80, 590, 610, 895), "Semantik maske", "Bitki/zemin sınırı, crop safety halo, OOD ve spray footprint için koru.", GREEN),
        ((695, 590, 1225, 895), "Detection + keypoint", "Bir weed = bir ID adayı; sap/kök/meristem doğrudan etiketlenir ve aktüatöre gider.", BLUE),
        ((1310, 590, 1840, 895), "Multi-task çıktı", "Aynı backbone: crop/weed instance + stem point + isteğe bağlı mask. En mantıklı hedef mimari.", ORANGE),
    ]
    draw = ImageDraw.Draw(page)
    for box, title, text, color in cards:
        card(draw, box, fill=WHITE, outline=color, width=4)
        add_text(draw, (box[0] + 25, box[1] + 28), title, 29, bold=True, fill=color)
        add_text(draw, (box[0] + 25, box[1] + 92), text, 24, width=32)
    add_text(draw, (1190, 260), "Dürüst sonuç", 28, bold=True, fill=RED)
    add_text(draw, (1190, 320), "Bu veri diliminde keypoint, genel F1'i tek başına sıçratmadı; ana darboğaz weed'i bulma/sınıflama. Keypoint lazer için yine de doğru hedef tanımı.", 26, width=43)
    add_text(draw, (85, 930), "Literatür kalibrasyonu: WSD makalesi de kendi simüle weeding testinde %80,42 accuracy raporlar; kamusal kanıt %95 saha başarısını hazır vermiyor.", 23, bold=True, fill=RED, width=118)
    return page


def row_page(data: dict[str, Any]) -> Image.Image:
    modes = data["row"]["modes"]
    baseline = modes["baseline"]["frozen_safe_pixel_metrics"]
    practical = modes["practical_guard"]["frozen_safe_pixel_metrics"]
    oracle = modes["oracle_guard"]["frozen_safe_pixel_metrics"]
    page = base_page("Ekim sırası prior: yararlı ama hard kural değil", "Sıra içinde weed bulunabildiği için ‘sıra içi = crop’ recall'ı da kesiyor.")
    draw_table(
        page,
        (80, 220, 1280, 520),
        ["SugarBeets tanısı", "Weed recall", "Crop-pixel risk", "Sonuç"],
        [
            ["Row guard yok", percent(baseline["safe_weed_pixel_recall"]), percent(baseline["crop_spray_risk_per_crop_pixel"]), "Referans"],
            ["Pratik row guard", percent(practical["safe_weed_pixel_recall"]), percent(practical["crop_spray_risk_per_crop_pixel"]), "Risk −0,5; recall −1,2 puan"],
            ["Oracle row guard", percent(oracle["safe_weed_pixel_recall"]), percent(oracle["crop_spray_risk_per_crop_pixel"]), "Üst sınır bile recall kesiyor"],
        ],
        (0.31, 0.18, 0.20, 0.31),
        font_size=22,
        row_height=68,
    )
    draw = ImageDraw.Draw(page)
    card(draw, (80, 600, 1280, 910), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (120, 635), "Nasıl kullanılmalı?", 31, bold=True, fill=DARK_GREEN)
    bullet_list(
        page,
        [
            "Planter/RTK veya çok-kareli fit ile daha stabil sıra geometrisi.",
            "Sıra dışında weed olasılığına yumuşak destek; sıra içinde otomatik veto yok.",
            "Crop keypoint/instance ile safety halo; belirsiz durumda ateş yok.",
        ],
        (125, 705),
        width=70,
        size=25,
    )
    card(draw, (1350, 220, 1835, 910), fill=LIGHT_RED, outline=RED)
    add_text(draw, (1390, 265), "Hard prior neden tehlikeli?", 28, bold=True, fill=RED, width=26)
    add_text(draw, (1390, 390), "Intra-row weed, mahsulle aynı sırada büyür. Hard veto onu sistematik olarak kaçırır. RoWeeder çalışması da bu failure mode'u açıkça raporluyor.", 26, width=28)
    add_text(draw, (1390, 680), "Karar: row prior bir safety/score özelliği; ana sınıflandırıcı değil.", 27, bold=True, fill=DARK_GREEN, width=27)
    return page


def video_page() -> Image.Image:
    page = base_page("Video PoC: ReID ile başlama", "Bitkiler sabit; esas ihtiyaç kamera hareketini toprağa projekte etmek ve aynı bitkiye bir kez ateşlemek.")
    draw = ImageDraw.Draw(page)
    steps = [
        ("1", "Her kare", "instance + weed skoru + sap noktası", BLUE),
        ("2", "Zemin koordinatı", "kalibre homografi/pose; piksel IoU tek başına yetmez", ORANGE),
        ("3", "Basit track", "nearest world point + boyut/güven gate", GREEN),
        ("4", "Temporal onay", "≥3 kare; ortalama nokta; crop veto", BLUE),
        ("5", "Tek atış", "fire-once ID + aktüatör latency telafisi", RED),
    ]
    x = 70
    for index, (number, title, note, color) in enumerate(steps):
        box = (x, 230, x + 300, 500)
        card(draw, box, fill=WHITE, outline=color, width=4)
        draw.ellipse((x + 20, 250, x + 74, 304), fill=color)
        add_text(draw, (x + 37, 258), number, 25, bold=True, fill=WHITE)
        add_text(draw, (x + 95, 255), title, 26, bold=True, fill=color)
        add_text(draw, (x + 24, 330), note, 22, width=20)
        if index < len(steps) - 1:
            draw.line((x + 305, 365, x + 335, 365), fill=DARK_GREEN, width=6)
            draw.polygon(((x + 335, 355), (x + 352, 365), (x + 335, 375)), fill=DARK_GREEN)
        x += 355
    card(draw, (75, 590, 880, 900), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (115, 625), "Ne kazandırması beklenir?", 30, bold=True, fill=DARK_GREEN)
    bullet_list(page, ["Tek-kare yalancı pozitiflerini onay bekleterek azaltır.", "Aynı weed'e tekrar atışı engeller.", "Sap noktasını birkaç gözlemle stabilize eder."], (120, 700), width=47, size=24)
    card(draw, (960, 590, 1840, 900), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (1000, 625), "Ne kazandırmaz?", 30, bold=True, fill=ORANGE)
    bullet_list(page, ["Sistematik crop/weed yanlışını düzeltmez.", "Görülmeyen küçük otu geri getirmez; confirmation recall'ı azaltabilir.", "mm kamera–lazer kalibrasyonunun yerini tutmaz."], (1005, 700), width=50, size=24, color=INK)
    add_text(draw, (70, 945), "ReID ancak uzun kayıp/occlusion, geri dönüş ve benzer tracklerin karışması ölçülürse eklenmeli. İlk PoC'de gereksiz karmaşıklık.", 24, bold=True, fill=RED, width=118)
    return page


def gate_page(data: dict[str, Any]) -> Image.Image:
    best = action_metric(data["high"], "keypoint_deduplicated_balanced_max_f1")
    train = data["high"]["train_diagnostic"]["stem_action_keypoint_deduplicated_10pct_box_diagonal"]
    page = base_page("%95'e giden en kısa yol", "Model karmaşıklığından önce hedef veri, fiziksel tolerans ve video karar protokolü.")
    draw = ImageDraw.Draw(page)
    metric_card(page, (75, 205, 500, 425), percent(best["f1"]), "Farklı tarih F1", "Mevcut development holdout.", accent=RED)
    metric_card(page, (535, 205, 960, 425), percent(train["f1"]), "Seen-date tanısı", "Aynı threshold; final kanıt değil.", accent=ORANGE)
    metric_card(page, (995, 205, 1420, 425), pp(0.95 - best["f1"]), "%95'e kalan", "Yalnız perception F1 farkı.", accent=RED)
    metric_card(page, (1455, 205, 1850, 425), "%0", "Crop→weed FP", "Bu testte; saha garantisi değil.", accent=GREEN)
    draw_table(
        page,
        (75, 500, 1850, 825),
        ["Sıra", "Deney", "Kabul metriği", "Neden"],
        [
            ["P0", "Hedef kamera + 3–4 tarla oturumu", "Sap/meristem point + crop instance ID", "En büyük domain açığı"],
            ["P0", "GSD/focus/blur/DOF bench", "Minimum weed mm → piksel; p95 nokta hatası", "Lazer toleransı piksel değil mm"],
            ["P1", "Video ID holdout", "Track-level P/R/F1; duplicate shot; latency", "Temporal kazanç ilk kez burada ölçülür"],
            ["P1", "Multi-task fine-tune", "Untouched farm/session macro-F1 ≥%95", "Detection + keypoint + safety mask"],
            ["P2", "Aktüatör bench", "Kill/removal ≥%95; crop injury ayrı gate", "Perception başarısı kill başarısı değil"],
        ],
        (0.08, 0.29, 0.31, 0.32),
        font_size=21,
        row_height=55,
    )
    add_text(draw, (80, 880), "Bugün go/no-go: araştırma PoC GO; gerçek ilaç/lazer ateşleme NO-GO. %95 hedef mantıklı, fakat hedef-tarla untouched test + mm kalibrasyon + crop injury kapısıyla birlikte tanımlanmalı.", 26, bold=True, fill=DARK_GREEN, width=112)
    return page


def source_page(data: dict[str, Any]) -> Image.Image:
    page = base_page("Kanıt sınırları ve kaynaklar", "Rakamların neyi kanıtlamadığı, en az neyi kanıtladığı kadar önemli.")
    draw = ImageDraw.Draw(page)
    card(draw, (75, 205, 915, 900), fill=WHITE)
    add_text(draw, (115, 245), "Bu PoC'nin sınırları", 31, bold=True, fill=DARK_GREEN)
    bullet_list(
        page,
        [
            "WSD test tarihi resolution/model kararında tekrar kullanıldı; final untouched kanıt değil.",
            "Crop-as-weed = crop GT kutusuyla IoU≥0,50 olan unmatched weed tahmini. Crop canopy/yaralanma testi değil.",
            "Kutuya göre %10 tolerans fiziksel mm değil. Kamera–alet kalibrasyonu ve robot latency yok.",
            "Tracking kodu calibrated world-coordinate gözlemleri için hazır; ID-etiketli videoda net F1 kazanç henüz ölçülmedi.",
            "Ultralytics tabanı AGPL araştırma PoC kapsamında; ürün lisansı ayrı karardır.",
        ],
        (120, 320),
        width=49,
        size=23,
        line_gap=18,
    )
    card(draw, (965, 205, 1845, 900), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (1005, 245), "Birincil kaynaklar", 31, bold=True, fill=BLUE)
    sources = [
        "Weed Stem Detection (AAAI 2025):\narxiv.org/abs/2502.06255",
        "RoWeeder / intra-row sınırı:\narxiv.org/abs/2410.04983",
        "ByteTrack / basit association:\narxiv.org/abs/2110.06864",
        "YOLO pose görev tanımı:\ndocs.ultralytics.com/tasks/pose",
    ]
    y = 330
    for text in sources:
        card(draw, (1010, y, 1800, y + 112), fill=WHITE, outline=LINE)
        add_text(draw, (1040, y + 22), text, 23, bold=True, width=49)
        y += 135
    add_text(draw, (90, 945), f"Best checkpoint SHA-256: {data['high']['checkpoint_sha256']}", 19, mono=True, fill=MUTED, width=140)
    return page


def build_markdown(data: dict[str, Any]) -> str:
    sem = data["semantic"]
    weed_p = sem["semantic_segmentation"]["precision"]["other_vegetation"]
    weed_r = sem["semantic_segmentation"]["recall"]["other_vegetation"]
    safe = sem["frozen_safe_pixel_metrics"]
    base = action_metric(data["base"], "keypoint_deduplicated_balanced_max_f1")
    high = action_metric(data["high"], "keypoint_deduplicated_balanced_max_f1")
    raw = action_metric(data["high"], "keypoint_balanced_max_f1")
    center = action_metric(data["high"], "box_center_balanced_max_f1")
    train = data["high"]["train_diagnostic"]["stem_action_keypoint_deduplicated_10pct_box_diagonal"]
    row = data["row"]["modes"]
    lines = [
        "# Noktasal bitki müdahalesi PoC v1",
        "",
        "## Kısa karar",
        "",
        f"`%9,72`, gerçek bitki-müdahale recall'ı değildi. 768 uzman modelin `weed_threshold=0.99` ve uncertainty/crop guard sonrasında kalan weed **piksellerini** yakalama oranıydı. Aynı 283 gerçek SugarBeets robot karesinde semantik sonuç mIoU `{sem['semantic_segmentation']['mean_iou']:.4f}`, weed-pixel P/R/F1 `{weed_p:.4f}/{weed_r:.4f}/{f1(weed_p, weed_r):.4f}` idi.",
        "",
        f"Gerçek sap etiketi olan WSD robot verisiyle kurulan detection+keypoint PoC'sinde mevcut en iyi 1536 fine-tune, ayrı test tarihinde 10% GT weed-box diagonal toleransında P/R/F1 `{high['precision']:.4f}/{high['recall']:.4f}/{high['f1']:.4f}` verdi. TP/FP/FN `{high['true_positive']}/{high['false_positive']}/{high['false_negative']}`; `{high['visible_ground_truth_stems']}` geçerli weed sapı vardı. %95 F1 kapısı **geçilmedi**.",
        "",
        "Bugün için doğru mimari: segmentasyon safety/context olarak kalır; noktasal aktüatör komutu crop/weed instance detection + weed stem/root keypoint'ten gelir. Video katmanı kalibre zemin koordinatında track, ≥3-kare onay ve fire-once mantığı kullanır. ReID ancak ölçülmüş uzun occlusion/geri dönüş sorunu varsa eklenir.",
        "",
        "Literatür de bu işi otomatik olarak %95'e çözmüş değil: WSD çalışması kendi simüle weeding deneyinde detection kontrolü için %75,37, detection+stem regression için %80,42 weeding accuracy raporlar. Bu metrik bizim one-to-one F1'imizle aynı değildir; yalnızca hedefin zorluğunu kalibre eder.",
        "",
        "## Sonuçlar",
        "",
        "| Model / karar | Precision | Recall | F1 | Not |",
        "|---|---:|---:|---:|---|",
        f"| 1024 pose + within-frame dedupe | {base['precision']:.4f} | {base['recall']:.4f} | {base['f1']:.4f} | tarih-ayrı WSD |",
        f"| 1536 fine-tune, ham keypoint | {raw['precision']:.4f} | {raw['recall']:.4f} | {raw['f1']:.4f} | eşik validation'dan |",
        f"| **1536 fine-tune + dedupe** | **{high['precision']:.4f}** | **{high['recall']:.4f}** | **{high['f1']:.4f}** | mevcut en iyi |",
        f"| 1536 box-center kontrol | {center['precision']:.4f} | {center['recall']:.4f} | {center['f1']:.4f} | keypoint'in 10% toleranstaki ham farkı küçük |",
        f"| 1536 seen-date tanısı + dedupe | {train['precision']:.4f} | {train['recall']:.4f} | {train['f1']:.4f} | final kanıt değil |",
        "",
        "### Tolerans duyarlılığı — mevcut en iyi model",
        "",
        "| Tolerans | P | R | F1 | TP/FP/FN |",
        "|---|---:|---:|---:|---:|",
    ]
    for kind, value, label in [
        ("fraction", 5, "5% box diagonal"),
        ("fraction", 10, "10% box diagonal"),
        ("fraction", 20, "20% box diagonal"),
        ("pixels", 5, "5 px"),
        ("pixels", 10, "10 px"),
        ("pixels", 20, "20 px"),
    ]:
        metric = action_metric(data["high"], "keypoint_deduplicated_balanced_max_f1", kind=kind, value=value)
        lines.append(f"| {label} | {metric['precision']:.4f} | {metric['recall']:.4f} | {metric['f1']:.4f} | {metric['true_positive']}/{metric['false_positive']}/{metric['false_negative']} |")
    lines.extend(
        [
            "",
            f"`crop_as_weed_false_fire=0`: unmatched predicted-weed kutularından GT crop kutusuyla IoU≥0.50 eşleşen yoktu. Bu, crop canopy/yaralanma garantisi değildir. Tahmin noktalarının `{high['crop_box_collision']['0']['rate_per_action']:.4f}` oranı bir GT crop bounding rectangle içinde kaldı; bu daha muhafazakâr bir mekânsal proxy'dir ve fiziksel temas olarak yorumlanmaz.",
            "",
            "## Dedupe ve tracking",
            "",
            f"1536 ham keypoint FP sayısı `{raw['false_positive']}` idi: `{raw['false_positive_breakdown']['duplicate_action_near_already_hit_stem']}` tekrar-aksiyon, `{raw['false_positive_breakdown']['stem_localization_near_miss_within_2x_tolerance']}` yakın kaçırma ve `{raw['false_positive_breakdown']['other_or_background']}` diğer/arka plan. Validation'da seçilen within-frame dedupe, yeni threshold ile F1'i `{raw['f1']:.4f}→{high['f1']:.4f}` yaptı.",
            "",
            "Gerçek video kazanımı henüz sayısal olarak raporlanmıyor; WSD'de frame-level GT var ama botanik track ID ve kamera–zemin hareket kalibrasyonu yok. Uydurma bir tracking F1 vermek yerine `src/agri_seg/temporal_action.py` calibrated world-coordinate gözlemleri için testli minimum uygulamayı sağlar: nearest-world association, ≥3 gözlem, crop veto, ortalama nokta ve fire-once.",
            "",
            "## Çözünürlük",
            "",
            "| Model / inference | P | R | F1 |",
            "|---|---:|---:|---:|",
        ]
    )
    for item in data["resolution"]:
        lines.append(f"| {item['name']} | {item['precision']:.4f} | {item['recall']:.4f} | {item['f1']:.4f} |")
    lines.extend(
        [
            "",
            "Kör inference upscale monotonik fayda vermedi. 1536'da train+inference uyumu yaklaşık 3 F1 puanı kazandırdı; deney equal-compute değil ve aynı development test tarihi model kararında tekrar kullanıldı.",
            "",
            "## Crop-row prior",
            "",
            "| Mod | Safe weed-pixel recall | Crop-pixel risk |",
            "|---|---:|---:|",
            f"| Baseline | {row['baseline']['frozen_safe_pixel_metrics']['safe_weed_pixel_recall']:.4f} | {row['baseline']['frozen_safe_pixel_metrics']['crop_spray_risk_per_crop_pixel']:.4f} |",
            f"| Practical guard | {row['practical_guard']['frozen_safe_pixel_metrics']['safe_weed_pixel_recall']:.4f} | {row['practical_guard']['frozen_safe_pixel_metrics']['crop_spray_risk_per_crop_pixel']:.4f} |",
            f"| Oracle guard | {row['oracle_guard']['frozen_safe_pixel_metrics']['safe_weed_pixel_recall']:.4f} | {row['oracle_guard']['frozen_safe_pixel_metrics']['crop_spray_risk_per_crop_pixel']:.4f} |",
            "",
            "Sıra guard risk ile birlikte recall'ı da azalttı. Sıra içi weed bulunduğu için `in-row=crop` hard kuralı kullanılmayacak. RTK/planter veya temporal row fit, skor özelliği ve soft safety prior olarak kullanılacak.",
            "",
            "## %95 kabul kapısı",
            "",
            "1. Hedef kamera/GSD ve fiziksel doğru-isabet toleransı mm olarak dondurulacak.",
            "2. 3–4 yeni tarla/kamera oturumunda weed instance + stem/root point + crop instance ve video track ID etiketlenecek.",
            "3. Farm/session ayrı untouched testte track-level precision/recall/F1 ≥0.95 aranacak; crop-as-weed ve duplicate-shot ayrı safety gate olacak.",
            "4. Sonra aktüatör testinde gerçek deposition/removal/kill ≥0.95 ve crop injury ayrı kapı olarak ölçülecek.",
            "",
            "Bugün: **research PoC GO; sahada ilaç/lazer ateşleme NO-GO**.",
            "",
            "## Veri ve protokol sınırları",
            "",
            "- WSD indirilebilir labelled arşivinde 511 eşli kare vardır; makale 1.556 etiketli kare bildirir.",
            "- Train/validation/test tarihleri ayrıdır; fakat resolution/fine-tune kararında test yeniden görüldüğü için artık development holdout'tur.",
            "- 10% weed-box diagonal toleransı fiziksel mm değildir; GSD, kamera–alet extrinsic ve latency yoktur.",
            "- Ultralytics baseline AGPL-3.0 araştırma PoC kapsamındadır; ürün lisansı ayrı çözülmelidir.",
            "",
            "## Birincil kaynaklar",
            "",
            "- [Weed Stem Detection — laser için detection + stem regression](https://arxiv.org/abs/2502.06255)",
            "- [RoWeeder — row prior ve intra-row weed sınırı](https://arxiv.org/abs/2410.04983)",
            "- [ByteTrack — basit detection association](https://arxiv.org/abs/2110.06864)",
            "- [Ultralytics pose görev dokümanı](https://docs.ultralytics.com/tasks/pose/)",
            "",
            "## Exact artefaktlar",
            "",
            f"- 1024 action JSON: `{BASE_ACTION_PATH}`",
            f"- 1536 action JSON: `{HIGH_ACTION_PATH}`",
            f"- 1536 best checkpoint SHA-256: `{data['high']['checkpoint_sha256']}`",
            f"- Dataset receipt: `{DATA_ROOT / 'processed/audits/weed_stem_detection_v1_receipt.json'}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    required = [SEMANTIC_PATH, ROW_PATH, BASE_ACTION_PATH, HIGH_ACTION_PATH, CONTACT_SHEET]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing required artifacts: {missing}")
    data = read_data()
    pages = [
        cover_page(data),
        semantic_page(data),
        protocol_page(data),
        dataset_page(),
        result_page(data),
        visual_page(
            "06_Image_20231206120903530.jpg",
            "Güçlü gerçek saha örneği",
            "Yeşil: GT crop kutusu • Kırmızı: GT weed kutusu • Camgöbeği: GT sap • Sarı: model weed/keypoint.",
            "Bu karede küçük weed saplarının çoğu doğru noktalanıyor; crop kutularına weed sınıfıyla ateş yok. Tek iyi kare, split metriğinin yerine geçmez.",
        ),
        visual_page(
            "05_Image_20231206120117538.jpg",
            "Zor gerçek saha örneği",
            "Magenta: eşleşmeyen/yanlış aksiyon • Sarı: tahmin • Camgöbeği: gerçek sap.",
            "Model sağdaki weed'leri yakalarken zeminde bir yalancı aksiyon üretiyor ve bazı bitkileri kaçırıyor. Ana açık detection/classification; yalnız keypoint hassasiyeti değil.",
        ),
        dedupe_page(data),
        resolution_page(data),
        keypoint_page(data),
        row_page(data),
        video_page(),
        gate_page(data),
        source_page(data),
    ]
    finalize_pages(pages, "Noktasal bitki müdahalesi PoC v1")
    save_pdf(pages, PDF_PATH, title="Noktasal bitki müdahalesi PoC v1")
    MARKDOWN_PATH.write_text(build_markdown(data), encoding="utf-8")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema_version": 1,
        "status": "research_poc_complete_not_field_or_laser_validated",
        "pdf": str(PDF_PATH.resolve()),
        "pdf_sha256": sha256(PDF_PATH),
        "markdown": str(MARKDOWN_PATH.resolve()),
        "markdown_sha256": sha256(MARKDOWN_PATH),
        "inputs": {str(path): sha256(path) for path in required},
        "pages": len(pages),
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
