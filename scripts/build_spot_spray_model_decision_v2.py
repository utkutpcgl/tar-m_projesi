#!/usr/bin/env python3
"""Build the concise segmentation/detection/keypoint spray decision report."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from scripts.build_detection_spot_spray_report_v1 import (
    _bar,
    _panel,
    _paste_image,
    pct,
    spot,
    strict,
)
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
DETECTION_ROOT = (
    DATA_ROOT
    / "runs/wsd_detection_poc_v1/yolo26s_detect_1024_seed17"
    / "spot_spray_ab_1024_final_v1"
)
DETECTION_METRICS = DETECTION_ROOT / "spot_spray_ab_metrics.json"
SEGMENTATION_ROOT = (
    DATA_ROOT / "processed/audits/wsd_segmentation_spot_spray_v1"
)
SEGMENTATION_METRICS = SEGMENTATION_ROOT / "segmentation_vs_detection_metrics.json"
SIZE_METRICS = (
    DATA_ROOT
    / "processed/audits/wsd_spot_success_conditions_v1/detection_gt_size_conditioned.json"
)
KEYPOINT_RECEIPT = (
    DATA_ROOT / "processed/audits/weed_stem_detection_v1_receipt.json"
)
DETECTION_VISUAL = DETECTION_ROOT / "comparison_gallery/01_Image_20231206115739783.jpg"
SEGMENTATION_VISUAL_1024 = (
    SEGMENTATION_ROOT
    / "equal_raster_1024/gallery/01_Image_20231206115739783.jpg"
)
SEGMENTATION_VISUAL_2048 = (
    SEGMENTATION_ROOT
    / "native_tiled_2048/gallery/06_Image_20231206115757781.jpg"
)
PDF_PATH = PROJECT_ROOT / "docs/results/SPOT_SPRAY_MODEL_KARARI_V2.pdf"
MARKDOWN_PATH = PROJECT_ROOT / "docs/SPOT_SPRAY_MODEL_KARARI_V2.md"
PACKAGE = DATA_ROOT / "processed/audits/spot_spray_model_decision_v2"


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


def seg_metric(segmentation: dict[str, Any], mode: str, key: str) -> dict[str, Any]:
    return segmentation["segmentation_modes"][mode]["calibration_and_test"][
        "test"
    ][key]


def cover(detection: dict[str, Any], segmentation: dict[str, Any]) -> Image.Image:
    detector = spot(detection, "detection_only_box_center")
    segmenter = seg_metric(segmentation, "equal_raster_1024", "weed_box_proxy")
    page = Image.new("RGB", (W, H), DARK_GREEN)
    draw = ImageDraw.Draw(page)
    card(draw, (70, 60, 1850, 1015), fill=BG, outline=BG, radius=38)
    add_text(draw, (125, 115), "Sprey için hangi model?", 64, bold=True, fill=DARK_GREEN)
    add_text(draw, (128, 198), "Segmentasyon • kutu merkezi • keypoint", 38, bold=True, fill=GREEN)
    add_text(draw, (130, 260), "10 Ağustos 2026 • aynı WSD robot test kareleri", 23, fill=MUTED)
    card(draw, (125, 330, 1795, 505), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (166, 362), "KISA KARAR", 23, bold=True, fill=GREEN)
    add_text(
        draw,
        (166, 408),
        "İlk kimyasal spot-spray PoC'si: hedef-domain kutularıyla eğitilmiş detection + kutu merkezi. Segmentasyon safety maskesi olarak kalsın; keypoint'i lazer aşamasına ertele.",
        31,
        bold=True,
        width=91,
    )
    metric_card(page, (125, 565, 630, 805), pct(detector["f1"]), "Detection spot F1", "WSD train kutularını gördü; test tarihi ayrı.", accent=GREEN)
    metric_card(page, (660, 565, 1165, 805), pct(segmenter["f1"]), "Segmentasyon F1", "WSD'yi hiç görmemiş global model, 1024.", accent=RED)
    metric_card(page, (1195, 565, 1700, 805), "%95", "Hedef kapı", "Henüz hiçbir kol geçmedi.", accent=ORANGE)
    add_text(draw, (130, 875), "Bu sonuç saha püskürtme onayı değil; kutu isabeti iyimser bir offline proxy'dir.", 28, bold=True, fill=RED, width=104)
    return page


def fairness_page() -> Image.Image:
    page = base_page("Bu kıyas ne kadar adil?", "Aynı test var; eğitim etiketi aynı değil. Sonucu doğru adlandırıyoruz.")
    draw = ImageDraw.Draw(page)
    card(draw, (70, 220, 900, 825), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (110, 255), "Ortak koşullar", 34, bold=True, fill=DARK_GREEN)
    bullet_list(
        page,
        [
            "Aynı 152 validation ve 148 test WSD karesi; tarihler ayrı.",
            "Ana kıyasta aynı tam-kare 1024 raster.",
            "Aksiyon eşiği ve maske→nokta kuralı yalnız validation'dan seçildi.",
            "Aynı one-to-one GT weed-kutusu sprey proxy'si.",
        ],
        (110, 330),
        width=48,
        size=25,
    )
    card(draw, (1020, 220, 1850, 825), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (1060, 255), "Kritik asimetri", 34, bold=True, fill=ORANGE)
    bullet_list(
        page,
        [
            "Detector: 211 WSD train karesi ve 1.437 weed kutusu gördü.",
            "Pose: ayrıca 1.435 yayıncı stem noktası gördü.",
            "Global segmenter: 0 WSD karesi gördü; WSD'de semantik maske yok.",
            "Fark, mimari + hedef-domain anotasyonu etkisidir; saf mimari A/B değildir.",
        ],
        (1060, 330),
        width=48,
        size=25,
    )
    card(draw, (220, 865, 1700, 965), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (265, 892), "Pratik soru için geçerli: hedef sahadan etiket toplamak işe yarıyor mu? Evet. Saf model kıyası için WSD maskesi gerekir.", 26, bold=True, fill=BLUE, width=99)
    return page


def result_page(detection: dict[str, Any], segmentation: dict[str, Any]) -> Image.Image:
    rows: list[list[str]] = []
    for mode, label in (
        ("equal_raster_1024", "Segmentasyon, zero-shot 1024"),
        ("native_tiled_2048", "Segmentasyon, zero-shot 2048 tile"),
    ):
        spray = seg_metric(segmentation, mode, "weed_box_proxy")
        stem = seg_metric(segmentation, mode, "stem_strict")
        rows.append([label, pct(spray["precision"]), pct(spray["recall"]), pct(spray["f1"]), pct(stem["f1"])])
    for strategy, label in (
        ("detection_only_box_center", "Detection-only → kutu merkezi"),
        ("pose_box_center", "Pose → kutu merkezi"),
        ("pose_keypoint", "Pose → keypoint"),
    ):
        spray = spot(detection, strategy)
        stem = strict(detection, strategy)
        rows.append([label, pct(spray["precision"]), pct(spray["recall"]), pct(spray["f1"]), pct(stem["f1"])])
    page = base_page("Aynı testte toplu sonuç", "Spot = GT weed kutusuna nokta; stem = yayıncı noktasına ≤%10 kutu diyagonali.")
    draw_table(
        page,
        (55, 220, 1865, 735),
        ("Yaklaşım", "Spot P", "Spot R", "Spot F1", "Stem F1"),
        rows,
        (0.42, 0.14, 0.14, 0.15, 0.15),
        font_size=23,
        row_height=84,
        align_right=(1, 2, 3, 4),
    )
    draw = ImageDraw.Draw(page)
    card(draw, (70, 790, 900, 950), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (110, 825), "Detection kazanımı", 29, bold=True, fill=DARK_GREEN)
    add_text(draw, (110, 875), "1024 spot F1: %19,3 → %76,6", 35, bold=True, width=44)
    card(draw, (1020, 790, 1850, 950), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (1060, 825), "Keypoint kazanımı", 29, bold=True, fill=ORANGE)
    add_text(draw, (1060, 875), "Pose merkez→point stem F1: +0,3 puan", 30, bold=True, width=48)
    return page


def segmentation_failure_page() -> Image.Image:
    page = base_page("Neden zero-shot segmentasyon zorlandı?", "Bu test karesinde GT weed yok; yeşil kutular crop, kırmızı boyama modelin weed tahmini.")
    with Image.open(SEGMENTATION_VISUAL_1024) as handle:
        _paste_image(page, handle, (190, 210, 1730, 830))
    draw = ImageDraw.Draw(page)
    card(draw, (170, 860, 1750, 970), fill=LIGHT_RED, outline=RED)
    add_text(draw, (215, 890), "Model tekerlek/parlak donanım parçalarını weed sandı. Bu, piksel azlığından çok WSD kamera-toprak-donanım domainini görmemiş olmasını gösteriyor.", 25, bold=True, width=105)
    return page


def detection_visual_page() -> Image.Image:
    page = base_page("Aynı karede hedef-domain detector", "Yeşil=GT crop. Weed olmadığı için doğru davranış: hiç sarı/magenta aksiyon üretmemek.")
    panel = _panel(DETECTION_VISUAL, 1)
    _paste_image(page, panel, (190, 210, 1730, 830))
    draw = ImageDraw.Draw(page)
    card(draw, (170, 860, 1750, 970), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (215, 890), "211 hedef-domain train karesi bile bu kamera ve crop görünümüne önemli uyum sağladı. Bu tek kare kanıt değil; toplu test farkıyla birlikte açıklayıcı örnek.", 25, bold=True, width=105)
    return page


def keypoint_page() -> Image.Image:
    page = base_page("Keypoint etiketini nasıl ekledik?", "Ek nokta uydurulmadı; WSD yayıncısının aynı satır sırasındaki points_labels dosyaları kullanıldı.")
    draw = ImageDraw.Draw(page)
    rows = [
        ["Train", "1.435", "Pose eğitimi"],
        ["Validation", "1.549", "Threshold seçimi"],
        ["Test", "1.097", "Sıkı stem metriği"],
    ]
    draw_table(page, (180, 235, 1740, 525), ("Split", "Görünür stem noktası", "Rol"), rows, (0.27, 0.34, 0.39), font_size=26, row_height=70)
    card(draw, (70, 610, 900, 920), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (110, 645), "Sprey için bulgu", 31, bold=True, fill=DARK_GREEN)
    add_text(draw, (110, 705), "Pose kutu merkezi spot F1 %75,0; keypoint %74,9. Stem F1 farkı yalnız +0,3 puan.", 30, bold=True, width=47)
    card(draw, (1020, 610, 1850, 920), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (1060, 645), "Etiket kararı", 31, bold=True, fill=ORANGE)
    add_text(draw, (1060, 705), "Kimyasal PoC'de önce kutu/instance topla. Stem-root-meristem keypoint'i dar lazer veya mekanik sökme aşamasında topla.", 29, bold=True, width=47)
    return page


def size_page(detection: dict[str, Any], size_metrics: dict[str, Any]) -> Image.Image:
    bins = detection["strategies"]["detection_only_box_center"]["test"]["weed_box_proxy"]["balanced_max_f1"]["test_radius_0_recall_by_apparent_weed_box_size"]["bins"]
    conditioned = size_metrics["regimes"]["28"]["test"]["spot_balanced"]
    page = base_page("28 px gerekli mi? Evet; yeterli mi? Hayır.", "28 px = 1024 model girişinde sqrt(GT weed kutu alanı); maske çapı veya fiziksel mm değil.")
    _bar(page, 250, "<14 px", bins["lt14"]["recall"], note=f"n={bins['lt14']['ground_truth']} weed", colour=RED)
    _bar(page, 390, "14–28 px", bins["14_to_lt28"]["recall"], note=f"n={bins['14_to_lt28']['ground_truth']} weed", colour=ORANGE)
    _bar(page, 530, "28–56 px", bins["28_to_lt56"]["recall"], note=f"n={bins['28_to_lt56']['ground_truth']} weed", colour=GREEN)
    draw = ImageDraw.Draw(page)
    card(draw, (70, 705, 900, 945), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (110, 740), "Boyut neyi düzeltti?", 29, bold=True, fill=DARK_GREEN)
    add_text(draw, (110, 795), "28–56 px recall %88,3: küçük weed'e göre belirgin daha iyi.", 30, bold=True, width=47)
    card(draw, (1020, 705, 1850, 945), fill=LIGHT_RED, outline=RED)
    add_text(draw, (1060, 740), "Neyi düzeltmedi?", 29, bold=True, fill=RED)
    add_text(draw, (1060, 795), f"≥28 px hedeflere koşullu n=163: recall {pct(conditioned['recall'])}, precision {pct(conditioned['precision'])}, F1 {pct(conditioned['f1'])}. Yanlış aksiyonlar sürüyor.", 27, bold=True, width=48)
    return page


def resolution_domain_page(detection: dict[str, Any], segmentation: dict[str, Any]) -> Image.Image:
    seg_1024 = seg_metric(segmentation, "equal_raster_1024", "weed_box_proxy")
    seg_2048 = seg_metric(segmentation, "native_tiled_2048", "weed_box_proxy")
    page = base_page("Piksel artırmak domain açığını kapatmadı", "Native 2048 fayda verdi; fakat hedef-domain örneği görmemiş model hâlâ çok geride.")
    draw = ImageDraw.Draw(page)
    metric_card(page, (90, 240, 605, 520), pct(seg_1024["f1"]), "Segmentasyon 1024", "Zero-shot, tam kare.", accent=RED)
    metric_card(page, (700, 240, 1215, 520), pct(seg_2048["f1"]), "Segmentasyon 2048", "Native tile; +5,3 F1 puan.", accent=ORANGE)
    metric_card(page, (1310, 240, 1825, 520), pct(spot(detection, "detection_only_box_center")["f1"]), "Detection 1024", "Hedef-domain kutularıyla eğitildi.", accent=GREEN)
    card(draw, (70, 610, 900, 925), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (110, 645), "Kamera ekseni", 31, bold=True, fill=BLUE)
    bullet_list(page, ["Native sensör detayı / daha dar FOV", "Doğru focus, DOF, shutter ve aydınlatma", "Train ve inference rasterını eşleştirme"], (110, 710), width=46, size=25)
    card(draw, (1020, 610, 1850, 925), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (1060, 645), "Veri ekseni", 31, bold=True, fill=DARK_GREEN)
    bullet_list(page, ["Aynı kamera/toprak/crop evresinden gerçek örnek", "Tarla/session ayrı train–val–test", "Kutu/instance ile weed proposal öğrenme"], (1060, 710), width=46, size=25)
    return page


def collection_page() -> Image.Image:
    page = base_page("Gerçek veri toplamaya ne zaman değer?", "Aşamalı topla; en pahalı etiketi baştan isteme.")
    draw = ImageDraw.Draw(page)
    rows = [
        ["1", "Weed + crop kutusu / instance", "Yüksek", "Detection, sayım, bir-bitki/bir-atış"],
        ["2", "Video zamanı + kamera metadata", "Yüksek", "Basit tracking, fire-once, hata analizi"],
        ["3", "50–100 stratified maske audit", "Orta/yüksek", "Crop safety + adil target-trained seg kıyası"],
        ["4", "Stem/root/meristem keypoint", "Spray için düşük", "Lazer/mekanik fazında gerekli"],
    ]
    draw_table(page, (50, 225, 1870, 625), ("Sıra", "Etiket", "Bugün ROI", "Ne açar?"), rows, (0.08, 0.31, 0.18, 0.43), font_size=23, row_height=82)
    card(draw, (70, 690, 1850, 945), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (115, 725), "Minimum ikna edici pilot", 31, bold=True, fill=ORANGE)
    add_text(draw, (115, 785), "En az 3–4 deploy-benzeri tarla/session: train, validation ve tamamen untouched test session'ları ayrı. Önce kutuları etiketle; segmentasyonun gerçek marjını görmek için küçük ama stratified maske alt-kümesi ekle. %95'e yaklaşmadan tam keypoint kampanyasına girme.", 27, bold=True, width=110)
    return page


def final_page() -> Image.Image:
    page = base_page("Nihai PoC kararı", "Basit ama genişletilebilir bir sprey hattı.")
    draw = ImageDraw.Draw(page)
    rows = [
        ("1", "Detection / instance", "Weed'i bul; bugün kutu merkezi aksiyon adayı."),
        ("2", "Segmentasyon safety", "Crop maskesi, weed dokusu/footprint ve no-fire veto."),
        ("3", "Basit video onayı", "Kalibre zeminde ≥3 kare, fire-once; kazanç ID-GT videoda ölçülür."),
        ("4", "Fiziksel bench", "Deposition/kill ve crop injury ayrı kapı; perception F1 kill-rate değildir."),
    ]
    y = 215
    for number, title, text in rows:
        card(draw, (70, y, 1850, y + 135), fill=WHITE, outline=LINE)
        draw.ellipse((95, y + 35, 165, y + 105), fill=GREEN)
        add_text(draw, (119, y + 50), number, 27, bold=True, fill=WHITE)
        add_text(draw, (200, y + 23), title, 29, bold=True, fill=DARK_GREEN)
        add_text(draw, (200, y + 69), text, 24, width=112)
        y += 153
    card(draw, (120, 850, 1800, 975), fill=LIGHT_RED, outline=RED)
    add_text(draw, (165, 879), "Bugün: detection-only spray araştırma baseline'ı GO • saha ateşlemesi NO-GO • 28 px tek başına yeterli değil • bir sonraki P0 hedef-domain kutusu + native high-res train/inference.", 27, bold=True, fill=RED, width=108)
    return page


def build_package() -> dict[str, Any]:
    PACKAGE.mkdir(parents=True, exist_ok=True)
    examples = PACKAGE / "examples"
    examples.mkdir(exist_ok=True)
    copies = [
        (PDF_PATH, PDF_PATH.name),
        (MARKDOWN_PATH, "README.md"),
        (DETECTION_METRICS, "detection_metrics_1024.json"),
        (SEGMENTATION_METRICS, "segmentation_vs_detection_metrics.json"),
        (SIZE_METRICS, "detection_gt_size_conditioned_metrics.json"),
        (KEYPOINT_RECEIPT, "keypoint_dataset_receipt.json"),
        (DETECTION_VISUAL, "examples/same_frame_detection_pose.jpg"),
        (SEGMENTATION_VISUAL_1024, "examples/same_frame_segmentation_1024.jpg"),
        (SEGMENTATION_VISUAL_2048, "examples/segmentation_2048_example.jpg"),
    ]
    copied: list[Path] = []
    for source, relative in copies:
        destination = PACKAGE / relative
        shutil.copy2(source, destination)
        copied.append(destination)
    receipt = {
        "schema_version": 1,
        "status": "offline_research_decision_not_field_validated",
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
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    detection = load(DETECTION_METRICS)
    segmentation = load(SEGMENTATION_METRICS)
    size_metrics = load(SIZE_METRICS)
    for path in (DETECTION_VISUAL, SEGMENTATION_VISUAL_1024, SEGMENTATION_VISUAL_2048, MARKDOWN_PATH):
        if not path.is_file():
            raise FileNotFoundError(path)
    pages = [
        cover(detection, segmentation),
        fairness_page(),
        result_page(detection, segmentation),
        segmentation_failure_page(),
        detection_visual_page(),
        keypoint_page(),
        size_page(detection, size_metrics),
        resolution_domain_page(detection, segmentation),
        collection_page(),
        final_page(),
    ]
    finalize_pages(pages, "Spot spray model kararı v2")
    save_pdf(pages, PDF_PATH, title="Spot spray model kararı v2")
    receipt = build_package()
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
