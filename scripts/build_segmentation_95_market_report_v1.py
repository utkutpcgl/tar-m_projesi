#!/usr/bin/env python3
"""Build a readable evidence and competitor-ceiling PDF for the 95% plan."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

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
    font,
    metric_card,
    paste_contain,
    save_pdf,
    sha256,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = PROJECT_ROOT / "docs/results/phenobench_95_evidence_summary_v1.json"
DETAIL_PATH = PROJECT_ROOT / "docs/SEGMENTASYON_95_SAHA_KANIT_PLANI_V1.md"
PDF_PATH = PROJECT_ROOT / "docs/results/SEGMENTASYON_95_VE_RAKIP_CEILING_RAPORU_V1.pdf"
GALLERY = PROJECT_ROOT / "docs/results/fair_detection_segmentation_gallery_v1"


def load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def pct(value: float, digits: int = 1) -> str:
    return f"%{100.0 * float(value):.{digits}f}".replace(".", ",")


def cover(summary: Mapping[str, Any]) -> Image.Image:
    heldout = summary["action_point_ablation_on_common_test"][
        "crop_safe_excess_green"
    ]
    capacity = summary["intentional_same_set_capacity"]["target_like126"]
    page = Image.new("RGB", (W, H), DARK_GREEN)
    draw = ImageDraw.Draw(page)
    card(draw, (65, 52, 1855, 1010), fill=BG, outline=BG, radius=40)
    add_text(draw, (120, 95), "Segmentasyonda %95 saha başarısı", 60, bold=True, fill=DARK_GREEN)
    add_text(draw, (124, 178), "Kapasite kanıtlandı; genelleme henüz kanıtlanmadı", 35, bold=True, fill=GREEN)
    add_text(draw, (125, 240), "PhenoBench eylem metriği • kamera kontratı • rakip ceiling'i • sonraki kanıt", 23, fill=MUTED)
    metric_card(page, (120, 350, 620, 610), pct(capacity["f1"], 2), "Aynı hedef karelerde F1", "Bilinçli kapasite/overfit testi; saha genellemesi değil.", accent=GREEN)
    metric_card(page, (710, 350, 1210, 610), pct(heldout["f1"], 2), "Farklı parsel action F1", "403 kare, 625 uygun weed; post-hoc development.", accent=ORANGE)
    metric_card(page, (1300, 350, 1800, 610), pct(heldout["crop_collision_rate_per_attempt"], 2), "Crop hit / atış", "Ana GO sınırı ≤%0,5; bugün geçmedi.", accent=RED)
    card(draw, (120, 710, 1800, 900), fill=LIGHT_RED, outline=RED)
    add_text(draw, (165, 748), "BUGÜNKÜ KARAR: ARAŞTIRMA DEVAM • SAHA ATEŞLEMESİ NO-GO", 33, bold=True, fill=RED, width=92)
    add_text(draw, (165, 826), "Instance segmentation doğru temel. Sıradaki büyük kaldıraç model zoo değil; optik/GSD + kontrollü ışık + session-ayrı hedef veri + tracking.", 24, bold=True, width=112)
    return page


def score_contract_page() -> Image.Image:
    page = base_page("Gerçek hedef mIoU değil, güvenli bitki müdahalesi", "Bir weed track'ine bir komut; crop teması ve fiziksel sonuç ayrı ölçülür.")
    rows = [
        ["Track action precision", "≥%97", "Yanlış atışı ve kimyasal israfını sınırlar"],
        ["Track action recall", "≥%95", "Müdahale edilebilir weed'lerin çoğunu bulur"],
        ["Track action F1", "≥%96", "Precision ve recall birlikte yüksek"],
        ["Crop'a yanlış aksiyon", "≤%0,5", "İlk GO; güçlü hedef %0,1–0,25"],
        ["Nozul footprint safe hit", "≥%95", "Nokta doğru olsa da damla alanı crop'a taşmamalı"],
        ["Fiziksel weed knockdown", "≥%90", "7/14 gün agronomik outcome; perception'dan ayrı"],
    ]
    draw_table(page, (55, 220, 1865, 760), ("Metrik", "GO", "Ne anlatır?"), rows, (0.30, 0.14, 0.56), font_size=22, row_height=76)
    draw = ImageDraw.Draw(page)
    card(draw, (95, 825, 1825, 950), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (140, 856), "Ana iddia, tamamen ayrı tarla/session testindeki alt %95 güven sınırıyla verilir. Boyut, gölge, ıslak toprak, crop yakınlığı ve hız ayrı strata'dır.", 25, bold=True, fill=BLUE, width=110)
    return page


def current_result_page(summary: Mapping[str, Any]) -> Image.Image:
    base = summary["action_point_ablation_on_common_test"]
    deepest = base["deepest_interior"]
    green = base["crop_safe_excess_green"]
    safe = base["confidence_only_crop_safe_policy"]
    rows = [
        ["Maske en derin iç nokta", pct(deepest["precision"]), pct(deepest["recall"]), pct(deepest["f1"]), pct(deepest["crop_collision_rate_per_attempt"], 2)],
        ["Crop-safe excess-green", pct(green["precision"]), pct(green["recall"]), pct(green["f1"]), pct(green["crop_collision_rate_per_attempt"], 2)],
        ["Confidence-only güvenli", pct(safe["precision"]), pct(safe["recall"]), pct(safe["f1"]), pct(safe["crop_collision_rate_per_attempt"], 2)],
    ]
    page = base_page("Bugün gerçekçi eylem başarımız", "403 farklı-parsel karesi, 625 adet ≥42 px weed; validation policy'si testte sabit.")
    draw_table(page, (45, 235, 1875, 545), ("Aksiyon", "Precision", "Recall", "F1", "Crop hit"), rows, (0.39, 0.15, 0.15, 0.14, 0.17), font_size=23, row_height=78, align_right=(1, 2, 3, 4))
    draw = ImageDraw.Draw(page)
    metric_card(page, (80, 640, 570, 900), "+3,86 puan", "Basit nokta kazanımı", "RGB excess-green + predicted crop halo; yeni model yok.", accent=GREEN)
    metric_card(page, (715, 640, 1205, 900), "141 FN", "%95 recall açığı", "625 uygun weed'in 484'ünde doğru ilk aksiyon.", accent=ORANGE)
    metric_card(page, (1350, 640, 1840, 900), "15 crop hit", "Safety açığı", "526 denemede %2,85; GO sınırı ≤%0,5.", accent=RED)
    add_text(draw, (110, 935), "Confidence'i yükseltmek crop hit'i sıfırlıyor, fakat recall %27,2'ye iniyor. Threshold ana çözüm değil.", 23, bold=True, fill=RED, width=120)
    return page


def visual_page(path: Path, title: str, subtitle: str, note: str, colour: tuple[int, int, int]) -> Image.Image:
    page = base_page(title, subtitle)
    paste_contain(page, path, (70, 205, 1850, 840))
    draw = ImageDraw.Draw(page)
    card(draw, (105, 875, 1815, 965), fill=WHITE, outline=colour)
    add_text(draw, (145, 897), note, 23, bold=True, fill=colour, width=120)
    return page


def camera_contract_page() -> Image.Image:
    page = base_page("Minimum weed'i kamera kontratına çevir", "42 px, fiziksel milimetre değil; model girdisindeki görünür kısa kenar hedefidir.")
    draw = ImageDraw.Draw(page)
    card(draw, (70, 220, 905, 520), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (115, 255), "ANA PoC: ≥20 mm", 36, bold=True, fill=GREEN)
    add_text(draw, (115, 335), "42 px için GSD ≤0,476 mm/px\n4096 px FOV ≤1,95 m\n1 m/s, <1 px blur: ≤0,476 ms", 29, bold=True, width=42)
    card(draw, (1015, 220, 1850, 520), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (1060, 255), "STRETCH: 10–20 mm", 36, bold=True, fill=ORANGE)
    add_text(draw, (1060, 335), "10 mm / 42 px: 0,238 mm/px\n4096 px FOV ≤0,975 m\n1 m/s, <1 px blur: ≤0,238 ms", 29, bold=True, width=42)
    card(draw, (120, 610, 1800, 910), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (165, 645), "KRİTİK RASTER KURALI", 28, bold=True, fill=BLUE)
    bullet_list(page, [
        "4K kareyi tek parça 1024'e küçültürsek 42 px hedef yaklaşık 10,5 px'e düşer; optik avantajı kaybederiz.",
        "Native 1024/1536 tile, kontrollü overlap ve aynı rasterda eğitim gerekir; dijital upscale yeni bilgi eklemez.",
        "Global shutter + senkron LED/strobe + focus/DOF, teorik GSD'yi gerçek yaprak ayrıntısına dönüştürür.",
    ], (165, 710), width=108, size=23, line_gap=11)
    return page


def camera_evidence_page() -> Image.Image:
    page = base_page("Kamera ve raster etkisi zaten görünür; kör upscale çözüm değil", "Sentetik paired tanı yön gösterir; gerçek holdout donanım kararını sınırlar.")
    rows = [
        ["Native sentetik 256", "%55,5", "%19,4", "Aynı unseen geometri"],
        ["Native sentetik 512", "%69,5", "%33,3", "Model/eşik sabit"],
        ["Native sentetik 1024", "%82,5", "%48,8", "Yeni optik/render ayrıntısı"],
    ]
    draw_table(page, (75, 220, 1845, 500), ("Koşul", "mIoU", "Safe recall", "Not"), rows, (0.31, 0.15, 0.18, 0.36), font_size=23, row_height=68, align_right=(1, 2))
    metric_card(page, (75, 590, 570, 860), "−8,26 puan", "Defocus σ=3", "Aynı sentetik sahnede mIoU kaybı; focus kritik.", accent=ORANGE)
    metric_card(page, (710, 590, 1205, 860), "0,577→0,362", "Gerçek kör 1,5× upscale", "Yeni bilgi yok; crop riski %4,10→%65,20. Reddedildi.", accent=RED)
    metric_card(page, (1345, 590, 1840, 860), "+13,01 puan", "768 target specialist", "SugarBeets iki-seed mIoU; CWFID −4,42 puan, routing şart.", accent=GREEN)
    draw = ImageDraw.Draw(page)
    add_text(draw, (115, 920), "Dürüst sonuç: native sensör detayi + focus/short shutter + aynı rasterda eğitim birlikte test edilmeli. Sentetik ışık enerjisi lux değildi; fiziksel LED kazancı henüz ölçülmedi.", 23, bold=True, fill=BLUE, width=120)
    return page


def capacity_page(summary: Mapping[str, Any]) -> Image.Image:
    capacity = summary["intentional_same_set_capacity"]
    common = summary["common_plot_domain_adaptation"]
    rows = [
        ["126 source; aynı kare", pct(capacity["source126"]["precision"], 2), pct(capacity["source126"]["recall"], 2), pct(capacity["source126"]["f1"], 2), "Kaldı"],
        ["126 target-like; aynı kare", pct(capacity["target_like126"]["precision"], 2), pct(capacity["target_like126"]["recall"], 2), pct(capacity["target_like126"]["f1"], 2), "GEÇTİ"],
        ["Target model; farklı parsel", pct(common["target126_aggressive"]["precision"], 2), pct(common["target126_aggressive"]["recall"], 2), pct(common["target126_aggressive"]["f1"], 2), "Genellemedi"],
    ]
    page = base_page("Model %95'i yapabiliyor mu? Evet — ama yalnız öğrendiği dağılımda", "Kapasite testi ile yeni-parsel genellemesini aynı sayı gibi okumuyoruz.")
    draw_table(page, (55, 235, 1865, 560), ("Test", "Precision", "Recall", "F1", "%98 kapısı"), rows, (0.39, 0.15, 0.15, 0.15, 0.16), font_size=23, row_height=82, align_right=(1, 2, 3))
    draw = ImageDraw.Draw(page)
    card(draw, (90, 650, 900, 915), fill=LIGHT_GREEN, outline=GREEN)
    add_text(draw, (135, 685), "NE KANITLANDI?", 29, bold=True, fill=GREEN)
    bullet_list(page, ["Model/etiket/action pipeline kapasitesi yeterli.", "Maskeden crop-safe nokta çıkarmak çalışıyor.", "Daha büyük model ilk zorunlu adım değil."], (135, 755), width=46, size=24)
    card(draw, (1020, 650, 1830, 915), fill=LIGHT_RED, outline=RED)
    add_text(draw, (1065, 685), "NE KANITLANMADI?", 29, bold=True, fill=RED)
    bullet_list(page, ["Yeni tarla/session'da %95 genelleme.", "Gerçek robot kamera ve hareket dayanıklılığı.", "Nozul deposition, kill veya crop injury."], (1065, 755), width=46, size=24)
    return page


def adaptation_page(summary: Mapping[str, Any]) -> Image.Image:
    common = summary["common_plot_domain_adaptation"]
    rows = []
    for key, label in (
        ("base", "Dondurulmuş base"),
        ("source126_aggressive", "126 source agresif"),
        ("target126_aggressive", "126 target agresif"),
        ("target126_source126_replay", "126+126 replay"),
    ):
        item = common[key]
        rows.append([label, pct(item["precision"]), pct(item["recall"]), pct(item["f1"]), pct(item["crop_collision_rate_per_attempt"], 2)])
    page = base_page("Basit domain adaptation recall'ı artırdı, güvenliği bozdu", "Ortak 172-kare calibration; aynı 403-kare test ve aynı ≥42 px eligibility.")
    draw_table(page, (45, 230, 1875, 600), ("Model", "Precision", "Recall", "F1", "Crop hit"), rows, (0.37, 0.15, 0.15, 0.15, 0.18), font_size=23, row_height=74, align_right=(1, 2, 3, 4))
    draw = ImageDraw.Draw(page)
    card(draw, (90, 690, 1830, 930), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (135, 724), "REPLAY KARARI: RED", 30, bold=True, fill=ORANGE)
    bullet_list(page, [
        "Recall %77,44 → %85,44: hedef veri doğru yönde sinyal veriyor.",
        "Precision %92,02 → %81,40 ve crop hit %2,85 → %5,64: yüksek güvenli crop/soil false-positive oluşuyor.",
        "Sıradaki tarif: crop-yakın hard-negative + session-dengeli replay + erken validation; daha uzun ezber değil.",
    ], (135, 785), width=110, size=23, line_gap=11)
    return page


def prior_page(summary: Mapping[str, Any]) -> Image.Image:
    rows_data = summary["predicted_crop_row_safety_ablation"]
    rows = []
    for key, label in (
        ("row_half_width_21", "21 px"),
        ("row_half_width_42", "42 px"),
        ("row_half_width_63", "63 px"),
        ("row_half_width_84", "84 px"),
    ):
        item = rows_data[key]
        rows.append([label, pct(item["precision"]), pct(item["recall"]), pct(item["f1"]), pct(item["crop_collision_rate_per_attempt"], 2)])
    page = base_page("Ekim sırası güçlü prior; ana sınıflandırıcı değil", "Predicted crop merkezlerinden kamera-dikey bant; label oracle kullanılmadı.")
    draw_table(page, (80, 230, 1840, 590), ("Yarı bant", "Precision", "Recall", "F1", "Crop hit"), rows, (0.29, 0.16, 0.16, 0.16, 0.23), font_size=23, row_height=72, align_right=(1, 2, 3, 4))
    draw = ImageDraw.Draw(page)
    card(draw, (120, 680, 1800, 920), fill=LIGHT_BLUE, outline=BLUE)
    add_text(draw, (165, 715), "Doğru kullanım: soft veto + RTK/temporal sıra", 31, bold=True, fill=BLUE)
    bullet_list(page, [
        "Bant genişledikçe crop hit azalıyor; 84 px'de sıfır.",
        "Aynı anda recall %69,9 → %51,4 düşüyor; gerçek in-row weed'ler de siliniyor.",
        "Ekim haritası, crop maskesi ve track kanıtı birlikte puanı değiştirsin; 'sıra içi = crop' hard kuralı olmasın.",
    ], (165, 785), width=108, size=23, line_gap=10)
    return page


def competitor_sprayer_page() -> Image.Image:
    rows = [
        ["Greeneye", "%95,7 recall", "Min weed yok", "24 kamera + 12 GPU + 72 ışık; vendor/Volcani"],
        ["Ecorobotix ARA", "≥2 mm recognition", "6×6 cm spray", "6 RGB+3D modül; P/R/F1 yok"],
        ["Bilberry", ">%90 hit", "≥5 cm weed", "25 km/h; ikinci geçiş teorik %99"],
        ["WEED-IT", "%95–98 hit", "4×25 cm zone", "Fluoresans; klasik vision/tür ayrımı değil"],
        ["ONE SMART", ">%95 application", "Min weed yok", "Kamera + LED; metrik tanımı belirsiz"],
        ["John Deere", "Broadcast-benzeri", "Min weed yok", "36 kamera; 5M acre; ~%50 ilaç azalması"],
    ]
    page = base_page("Ticari ilaçlama ceiling'i: yaklaşık %90–98", "Metrikler aynı değil. Kamera megapikseli çoğunlukla yayımlanmıyor; recognition, spray footprint ve saha outcome ayrı.")
    draw_table(page, (30, 220, 1890, 790), ("Sistem", "Başarı iddiası", "Boyut / footprint", "Kanıtı nasıl okumak gerekir?"), rows, (0.18, 0.20, 0.20, 0.42), font_size=19, row_height=78)
    draw = ImageDraw.Draw(page)
    card(draw, (105, 845, 1815, 960), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (150, 875), "ARA'nın 2 mm tanıma eşiği, 2 mm spray alanı veya o boyutta %95 F1 değildir. Bilberry'nin ≥5 cm kontratı daha kaba ama daha yorumlanabilirdir.", 24, bold=True, fill=ORANGE, width=114)
    return page


def competitor_precision_page() -> Image.Image:
    page = base_page("En ileri noktasal sistemler neyi kanıtlıyor?", "Aktüatör yerleştirme, recognition ve sezon-sonu weed kontrolü birbirinin yerine geçmez.")
    draw = ImageDraw.Draw(page)
    metric_card(page, (80, 230, 580, 505), "%99 / 2 mm", "Verdant placement", "Atışların %99'u seçilmiş hedefin 2 mm içinde. Recognition P/R değil.", accent=BLUE)
    metric_card(page, (710, 230, 1210, 505), "sub-mm", "Carbon hedefleme", "3 kamera + 20 LED + 2 GPU / modül; min-weed P/R yayımlanmıyor.", accent=ORANGE)
    metric_card(page, (1340, 230, 1840, 505), "≥%97", "Weed biomass sonucu", "Hakemli eski nesil çoklu-geçiş; crop stunting ≤%1.", accent=GREEN)
    card(draw, (100, 610, 1820, 915), fill=LIGHT_RED, outline=RED)
    add_text(draw, (145, 645), "PİYASADA EVRENSEL 'MÜKEMMEL VISION' KANITI YOK", 31, bold=True, fill=RED)
    bullet_list(page, [
        "Hiçbir sistem aynı testte minimum weed + recognition precision/recall + crop hit + fiziksel kill-rate sözleşmesini yayımlamıyor.",
        "Yaklaşık %95–98 ticari ceiling, bilinen crop/domain ve kontrollü görüntüleme hacminde gerçekçi görünüyor.",
        "Bizim iddiamız daha denetlenebilir olmalı: her metrik boyut, crop mesafesi, hız ve fiziksel footprint ile birlikte verilecek.",
    ], (145, 720), width=112, size=23, line_gap=11)
    return page


def architecture_page() -> Image.Image:
    page = base_page("Rakiplerin ortak mimarisi bizim tasarım cevabımız", "Ceiling tek bir model checkpoint'i değil; kontrollü sense–decide–act zinciridir.")
    draw = ImageDraw.Draw(page)
    boxes: Sequence[tuple[int, int, int, int, str, tuple[int, int, int]]] = (
        (55, 300, 370, 575, "YAKIN KAMERA\n\nYeterli GSD\nGlobal shutter\nNative tile", BLUE),
        (435, 300, 750, 575, "KONTROLLÜ IŞIK\n\nLED/strobe\nKısa pozlama\nGölgelik", ORANGE),
        (815, 300, 1130, 575, "SEGMENTASYON\n\nCrop + weed\nUnknown/abstain\nSafety halo", GREEN),
        (1195, 300, 1510, 575, "TRACKING\n\n3–5 gözlem\nGround plane\nFire once", BLUE),
        (1575, 300, 1890, 575, "AKTÜATÖR\n\nLatency calib.\nFootprint\nKill/injury", RED),
    )
    for x1, y1, x2, y2, label, colour in boxes:
        fill = LIGHT_BLUE if colour == BLUE else LIGHT_ORANGE if colour == ORANGE else LIGHT_GREEN if colour == GREEN else LIGHT_RED
        card(draw, (x1, y1, x2, y2), fill=fill, outline=colour)
        add_text(draw, (x1 + 25, y1 + 35), label, 24, bold=True, fill=colour, width=18)
    for x in (388, 768, 1148, 1528):
        draw.line((x, 438, x + 30, 438), fill=DARK_GREEN, width=7)
        draw.polygon(((x + 30, 425), (x + 52, 438), (x + 30, 451)), fill=DARK_GREEN)
    card(draw, (155, 700, 1765, 915), fill=WHITE, outline=LINE)
    add_text(draw, (205, 735), "En önemli iki eksen doğru anlaşıldı", 31, bold=True, fill=DARK_GREEN)
    bullet_list(page, ["1) Kamera + GSD + focus + kısa pozlama + kontrollü ışık.", "2) Hedef saha/session verisini gören, eski sahaları unutmayan domain adaptation.", "Tracking precision/recall'ı artırabilecek üçüncü sistem kaldıracıdır; ID-GT olmadan kazanç iddia edilmez."], (205, 800), width=105, size=23, line_gap=9)
    return page


def proof_plan_page() -> Image.Image:
    page = base_page("%95'i nasıl gerçekten ispatlarız?", "Sıra, ucuz ve nedensel deneyden pahalı fiziksel denemeye gider.")
    draw = ImageDraw.Draw(page)
    steps = (
        ("1", "Fiziksel kontrat", "20 mm ana / 10–20 mm stretch; nozzle footprint, hız, crop mesafesi", BLUE),
        ("2", "Paired kamera bench", "Aynı 300–500 bitki: mevcut rig vs global-shutter + 4K + LED/strobe", ORANGE),
        ("3", "Session-ayrı veri + video", "Crop-yakın hard-negative, instance mask, track ID; native tile training", GREEN),
        ("4", "Tek sefer final test", "≥2.000 weed track; P≥97/R≥95/F1≥96; crop hit≤0,5%", BLUE),
        ("5", "Fiziksel outcome", "Su/UV deposition → sınırlı herbisit; knockdown, crop injury, ilaç tasarrufu", RED),
    )
    y = 220
    for number, title, detail, colour in steps:
        fill = LIGHT_BLUE if colour == BLUE else LIGHT_ORANGE if colour == ORANGE else LIGHT_GREEN if colour == GREEN else LIGHT_RED
        card(draw, (85, y, 1835, y + 135), fill=fill, outline=colour)
        card(draw, (115, y + 25, 205, y + 110), fill=colour, outline=colour, radius=42)
        add_text(draw, (145, y + 44), number, 33, bold=True, fill=WHITE)
        add_text(draw, (250, y + 24), title, 28, bold=True, fill=colour)
        add_text(draw, (250, y + 69), detail, 22, bold=True, width=112)
        y += 150
    add_text(draw, (125, 955), "Depth/NIR yalnız RGB hata analizi gerekçelendirirse; ilk satın alma değil.", 23, bold=True, fill=MUTED, width=118)
    return page


def source_page() -> Image.Image:
    page = base_page("Kaynaklar ve yeniden üretilebilir kanıt", "Vendor iddiaları vendor olarak; hakemli/bağımsız outcome ayrı etiketlendi.")
    draw = ImageDraw.Draw(page)
    left = [
        "Deere: deere.com/.../see-spray-technology-across-5-million-acres",
        "Greeneye: greeneye.ag/trials + UNL field-trial release",
        "Ecorobotix: ARA 620 brochure (2025-12-11)",
        "ONE SMART SPRAY: onesmartspray.com",
        "Bilberry: bilberry.io/faq",
        "WEED-IT: weed-it.com/.../spot-spraying",
    ]
    right = [
        "Verdant: verdantrobotics.com/faqs",
        "Carbon: carbonrobotics.com/laserweeder-g2-600",
        "Carbon field study: Pest Management Science, DOI 10.1002/ps.8912",
        "Exact yerel rapor: docs/SEGMENTASYON_95_SAHA_KANIT_PLANI_V1.md",
        "Exact özet: docs/results/phenobench_95_evidence_summary_v1.json",
        "Tüm raw run'lar SHA-256 ile kilitli; model/dataset GitHub'a eklenmedi.",
    ]
    card(draw, (65, 225, 925, 860), fill=WHITE, outline=LINE)
    add_text(draw, (110, 260), "Piyasa kaynakları", 30, bold=True, fill=BLUE)
    bullet_list(page, left, (110, 330), width=48, size=22, line_gap=17)
    card(draw, (995, 225, 1855, 860), fill=WHITE, outline=LINE)
    add_text(draw, (1040, 260), "Bizim kanıt", 30, bold=True, fill=GREEN)
    bullet_list(page, right, (1040, 330), width=48, size=22, line_gap=17)
    card(draw, (170, 900, 1750, 975), fill=LIGHT_RED, outline=RED)
    add_text(draw, (215, 920), "Sonuç: %95 kapasite var; %95 yeni-saha genellemesi ve fiziksel ilaçlama başarısı henüz yok.", 26, bold=True, fill=RED, width=102)
    return page


def repair_two_digit_page_labels(pages: Sequence[Image.Image]) -> None:
    """Keep the first digit visible in PIL's PDF rendering for pages 10+."""
    for index, page in enumerate(pages, start=1):
        if index < 10:
            continue
        draw = ImageDraw.Draw(page)
        background = page.getpixel((1800, 1050))
        draw.rectangle((1740, 1024, 1870, 1075), fill=background)
        draw.text(
            (1848, 1031),
            f"{index}/{len(pages)}",
            font=font(19, bold=True),
            fill=MUTED,
            anchor="ra",
        )


def main() -> None:
    summary = load(SUMMARY_PATH)
    if summary.get("status") != "posthoc_development_evidence_only_not_field_go":
        raise ValueError("Unexpected evidence status")
    if not DETAIL_PATH.is_file():
        raise FileNotFoundError(DETAIL_PATH)
    visuals = sorted(path for path in GALLERY.glob("*.jpg") if path.is_file())
    if len(visuals) < 2:
        raise ValueError("At least two explanatory gallery images are required")
    pages = [
        cover(summary),
        score_contract_page(),
        current_result_page(summary),
        visual_page(visuals[0], "Başarılı saha örneği", "Aynı PhenoBench test karesi; sol GT, orta detection, sağ segmentation.", "Renk legend'i görselin içindedir. Bu sayfa maskenin düzensiz weed dokusunda neden kutu merkezinden daha iyi aksiyon verebildiğini gösterir.", GREEN),
        visual_page(visuals[1], "Zor saha örneği", "Küçük/karışık bitkilerde tek kare hatası görünür hale gelir.", "Kırmızı nokta crop/toprak hatasını, kaçırılan GT weed recall açığını gösterir. Kamera ve temporal kanıt bu strata için ölçülmelidir.", RED),
        camera_evidence_page(),
        camera_contract_page(),
        capacity_page(summary),
        adaptation_page(summary),
        prior_page(summary),
        competitor_sprayer_page(),
        competitor_precision_page(),
        architecture_page(),
        proof_plan_page(),
        source_page(),
    ]
    finalize_pages(pages, "Segmentasyon %95 ve rakip ceiling raporu v1")
    repair_two_digit_page_labels(pages)
    save_pdf(pages, PDF_PATH, title="Segmentasyon %95 ve rakip ceiling raporu v1")
    print(
        json.dumps(
            {
                "pdf": str(PDF_PATH),
                "pages": len(pages),
                "bytes": PDF_PATH.stat().st_size,
                "sha256": sha256(PDF_PATH),
                "summary_sha256": sha256(SUMMARY_PATH),
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
