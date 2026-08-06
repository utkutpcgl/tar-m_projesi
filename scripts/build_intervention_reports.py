#!/usr/bin/env python3
"""Build concise and detailed intervention-oriented reports from frozen metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont, ImageOps


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_METRICS_ROOT = Path(
    "/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/"
    "intervention_metrics_v1"
)
DEFAULT_VISUAL_ROOT = Path(
    "/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/"
    "segmentation_visual_report_v2"
)
DEFAULT_INTERVENTION_VISUAL_ROOT = Path(
    "/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/"
    "intervention_visuals_v1"
)
DEFAULT_RESOLUTION_ROOT = Path(
    "/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/"
    "intervention_resolution_ablation_v1"
)
DEFAULT_OUTPUT = Path(
    "/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/"
    "crop_intervention_report_v1"
)

W, H = 1920, 1080
BG = (246, 247, 242)
WHITE = (255, 255, 255)
INK = (26, 38, 34)
MUTED = (90, 103, 98)
LINE = (210, 218, 211)
GREEN = (31, 132, 84)
DARK_GREEN = (19, 73, 51)
LIGHT_GREEN = (224, 241, 230)
RED = (194, 55, 51)
LIGHT_RED = (251, 230, 228)
ORANGE = (224, 139, 32)
LIGHT_ORANGE = (252, 240, 219)
BLUE = (40, 135, 170)
LIGHT_BLUE = (224, 241, 248)
PURPLE = (154, 63, 180)
GRAY = (225, 230, 226)

REGULAR_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
BOLD_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
MONO_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")


def font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont:
    source = MONO_FONT if mono else (BOLD_FONT if bold else REGULAR_FONT)
    return ImageFont.truetype(str(source), size=size)


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
    spacing: int = 9,
    mono: bool = False,
) -> None:
    if width:
        text = wrap(text, width)
    draw.multiline_text(
        xy,
        text,
        font=font(size, bold=bold, mono=mono),
        fill=fill,
        spacing=spacing,
    )


def card(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    fill: tuple[int, int, int] = WHITE,
    outline: tuple[int, int, int] = LINE,
    radius: int = 22,
    width: int = 2,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def base_page(title: str, subtitle: str = "") -> Image.Image:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 35, 1872, 46), radius=5, fill=GREEN)
    add_text(draw, (68, 68), title, 48, bold=True)
    if subtitle:
        add_text(draw, (70, 128), subtitle, 23, fill=MUTED, width=125)
    return image


def finalize_pages(pages: list[Image.Image], report_name: str) -> None:
    for index, page in enumerate(pages, start=1):
        draw = ImageDraw.Draw(page)
        draw.line((68, 1020, 1852, 1020), fill=LINE, width=2)
        add_text(draw, (70, 1033), report_name, 18, fill=MUTED)
        label = f"{index}/{len(pages)}"
        bbox = draw.textbbox((0, 0), label, font=font(19, bold=True))
        add_text(draw, (1848 - (bbox[2] - bbox[0]), 1031), label, 19, bold=True, fill=MUTED)


def save_pdf(
    pages: Sequence[Image.Image],
    destination: Path,
    *,
    title: str | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp.pdf")
    pages[0].save(
        temporary,
        "PDF",
        save_all=True,
        append_images=list(pages[1:]),
        resolution=150.0,
        quality=88,
        optimize=True,
        title=title or destination.stem.replace("_", " "),
    )
    temporary.replace(destination)


def paste_contain(
    canvas: Image.Image,
    source_path: Path,
    box: tuple[int, int, int, int],
    *,
    background: tuple[int, int, int] = WHITE,
) -> None:
    with Image.open(source_path) as handle:
        source = handle.convert("RGB")
    x1, y1, x2, y2 = box
    fitted = ImageOps.contain(
        source, (x2 - x1, y2 - y1), Image.Resampling.LANCZOS
    )
    frame = Image.new("RGB", (x2 - x1, y2 - y1), background)
    frame.paste(
        fitted,
        ((frame.width - fitted.width) // 2, (frame.height - fitted.height) // 2),
    )
    canvas.paste(frame, (x1, y1))


def draw_table(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    fractions: Sequence[float],
    *,
    font_size: int = 20,
    row_height: int | None = None,
    align_right: Iterable[int] = (),
) -> None:
    draw = ImageDraw.Draw(canvas)
    x1, y1, x2, y2 = box
    widths = [int((x2 - x1) * value) for value in fractions]
    widths[-1] += x2 - x1 - sum(widths)
    row_height = row_height or max(54, int((y2 - y1) / (len(rows) + 1)))
    right = set(align_right)
    cursor_y = y1
    cursor_x = x1
    for column, (header, width) in enumerate(zip(headers, widths)):
        draw.rectangle(
            (cursor_x, cursor_y, cursor_x + width, cursor_y + row_height),
            fill=DARK_GREEN,
        )
        text = wrap(header, max(8, int(width / (font_size * 0.60))))
        draw.multiline_text(
            (cursor_x + 12, cursor_y + 10),
            text,
            font=font(font_size, bold=True),
            fill=WHITE,
            spacing=4,
        )
        cursor_x += width
    cursor_y += row_height
    for row_index, row in enumerate(rows):
        fill = WHITE if row_index % 2 == 0 else (238, 242, 238)
        cursor_x = x1
        for column, (value, width) in enumerate(zip(row, widths)):
            draw.rectangle(
                (cursor_x, cursor_y, cursor_x + width, cursor_y + row_height),
                fill=fill,
                outline=LINE,
                width=1,
            )
            text = wrap(str(value), max(7, int(width / (font_size * 0.58))))
            text_font = font(font_size, bold=column == 0)
            if column in right and "\n" not in text:
                bbox_text = draw.textbbox((0, 0), text, font=text_font)
                text_x = cursor_x + width - 12 - (bbox_text[2] - bbox_text[0])
            else:
                text_x = cursor_x + 12
            draw.multiline_text(
                (text_x, cursor_y + 10),
                text,
                font=text_font,
                fill=INK,
                spacing=4,
            )
            cursor_x += width
        cursor_y += row_height


def bullet_list(
    canvas: Image.Image,
    items: Sequence[str],
    xy: tuple[int, int],
    *,
    width: int = 95,
    size: int = 25,
    line_gap: int = 16,
    color: tuple[int, int, int] = INK,
) -> int:
    draw = ImageDraw.Draw(canvas)
    x, y = xy
    for item in items:
        wrapped = wrap(item, width)
        lines = wrapped.count("\n") + 1
        draw.ellipse((x, y + 10, x + 10, y + 20), fill=GREEN)
        add_text(draw, (x + 24, y), wrapped, size, fill=color, spacing=7)
        y += lines * (size + 8) + line_gap
    return y


def pct(value: float | None, digits: int = 1) -> str:
    return "ölçülemez" if value is None else f"%{100.0 * value:.{digits}f}"


def dec(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def integer(value: int | float | None) -> str:
    return "—" if value is None else f"{int(value):,}".replace(",", ".")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def result_path(metrics_root: Path, model: str, evaluation: str) -> Path:
    path = metrics_root / model / f"{evaluation}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing completed intervention result: {path}")
    return path


def load_results(metrics_root: Path) -> dict[str, dict[str, Any]]:
    keys = {
        "source": ("global", "source_validation"),
        "sorghum": ("global", "sorghum_external_test"),
        "sugar": ("global", "sugarbeets_robot_holdout"),
        "weedmap": ("global", "weedmap_uav_holdout"),
        "rice": ("rice_specialist", "riceseg_heldout"),
        "early_rice": ("rice_specialist", "early_rice_transfer"),
    }
    return {
        name: load_json(result_path(metrics_root, model, evaluation))
        for name, (model, evaluation) in keys.items()
    }


def view(payload: Mapping[str, Any], dataset: str | None = None) -> Mapping[str, Any]:
    if dataset is None:
        return payload["overall"]
    return payload["by_dataset"][dataset]


def extract_metrics(data: Mapping[str, Any]) -> dict[str, float | int | None]:
    segmentation = data["semantic_segmentation"]
    semantic = data["modes"]["semantic_argmax"]
    safe = data["modes"]["frozen_safe_action"]
    sem_components = semantic["component_metrics"]["all"]
    safe_components = safe["component_metrics"]["all"]
    semantic_subpatch = semantic["component_metrics"]["sub_patch_lt14px"]
    safe_subpatch = safe["component_metrics"]["sub_patch_lt14px"]
    safe_actions = safe["action_point_metrics"]
    semantic_actions = semantic["action_point_metrics"]
    return {
        "images": data["images"],
        "miou": segmentation["mean_iou"],
        "crop_iou": segmentation["iou"]["target_crop"],
        "weed_iou": segmentation["iou"]["other_vegetation"],
        "weed_recall": segmentation["recall"]["other_vegetation"],
        "subpatch_fraction": data["gt_weed_semantic_component_diameter_px"][
            "sub_patch_fraction"
        ],
        "components": sem_components["semantic_component_proxies"],
        "sem_hit": sem_components["component_hit_recall_any_overlap"],
        "sem_subpatch_hit": semantic_subpatch[
            "component_hit_recall_any_overlap"
        ],
        "sem_cov50": sem_components["component_coverage_recall"][
            "at_least_50pct"
        ],
        "sem_cov90": sem_components["component_coverage_recall"][
            "at_least_90pct"
        ],
        "sem_center_r1": sem_components["center_proxy"][
            "recall_within_equivalent_radius"
        ]["1.0"],
        "sem_center_px10": sem_components["center_proxy"][
            "recall_within_pixels"
        ]["10"],
        "safe_hit": safe_components["component_hit_recall_any_overlap"],
        "safe_cov50": safe_components["component_coverage_recall"][
            "at_least_50pct"
        ],
        "safe_subpatch_hit": safe_subpatch[
            "component_hit_recall_any_overlap"
        ],
        "safe_point_precision": safe_actions["point_precision_on_weed"],
        "safe_point_crop": safe_actions["point_crop_hit_rate"],
        "safe_crop_collision_r10": safe_actions[
            "crop_collision_rate_by_circular_footprint_radius_px"
        ]["10"],
        "safe_action_points": safe_actions["action_points"],
        "semantic_point_precision": semantic_actions["point_precision_on_weed"],
        "semantic_point_crop": semantic_actions["point_crop_hit_rate"],
        "safe_pixel_recall": data["frozen_safe_pixel_metrics"][
            "safe_weed_pixel_recall"
        ],
        "safe_pixel_precision": data["frozen_safe_pixel_metrics"][
            "safe_weed_pixel_precision"
        ],
    }


def policy_lines(payload: Mapping[str, Any]) -> tuple[str, str]:
    policy = payload["frozen_safety_policy"]
    crop_specific = ", ".join(
        f"crop_id {crop_id}: {threshold:.3f}"
        for crop_id, threshold in sorted(
            policy["weed_threshold_by_crop_id"].items(),
            key=lambda item: int(item[0]),
        )
    )
    common = (
        f"default weed {policy['weed_threshold']:.3f}; unknown-crop weed "
        f"{policy['unknown_crop_weed_threshold']:.3f}; crop guard "
        f"{policy['crop_threshold']:.3f}; min confidence "
        f"{policy['min_confidence']:.3f}; min margin "
        f"{policy['min_margin']:.3f}; max entropy "
        f"{policy['max_entropy']:.3f}; crop dilation "
        f"{policy['crop_dilation_px']} px"
    )
    return common, crop_specific or "crop-specific override yok"


def dataset_rows(results: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    source = results["source"]
    rows = {
        "PhenoBench": extract_metrics(view(source, "phenobench")),
        "ACRE": extract_metrics(view(source, "acre")),
        "ROSE": extract_metrics(view(source, "rose")),
        "WE3DS": extract_metrics(view(source, "we3ds")),
        "WeedsGalore": extract_metrics(view(source, "weedsgalore")),
        "Sorghum test": extract_metrics(view(results["sorghum"])),
        "SugarBeets robot": extract_metrics(view(results["sugar"])),
        "WeedMap UAV": extract_metrics(view(results["weedmap"])),
        "RiceSEG calibration": extract_metrics(view(results["rice"])),
        "Early-rice transfer": extract_metrics(view(results["early_rice"])),
    }
    return rows


def load_resolution_rows(resolution_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, evaluation, scale in (
        ("1.0× native", "early_rice_scale100", 1.0),
        ("1.5× interp.", "early_rice_scale150", 1.5),
        ("2.0× interp.", "early_rice_scale200", 2.0),
    ):
        payload = load_json(
            result_path(resolution_root, "rice_specialist", evaluation)
        )
        metrics = extract_metrics(view(payload))
        subpatch_semantic = payload["overall"]["modes"]["semantic_argmax"][
            "component_metrics"
        ]["sub_patch_lt14px"]["component_hit_recall_any_overlap"]
        rows.append(
            {
                "label": label,
                "scale": scale,
                **metrics,
                "semantic_subpatch_hit": subpatch_semantic,
                "perception_ms": payload["runtime"].get(
                    "perception_ms_per_image"
                ),
                "perception_fps": payload["runtime"].get(
                    "perception_images_per_second"
                ),
            }
        )
    return rows


def markdown_report(
    results: Mapping[str, Mapping[str, Any]],
    rows: Mapping[str, Mapping[str, Any]],
    resolution_rows: Sequence[Mapping[str, Any]],
    synthetic_summary: Mapping[str, float | int],
) -> str:
    source = extract_metrics(view(results["source"]))
    rice = rows["RiceSEG calibration"]
    seen_names = ("PhenoBench", "ACRE", "ROSE", "WE3DS", "WeedsGalore")
    worst_crop_name, worst_crop = max(
        (
            (name, rows[name]["safe_point_crop"])
            for name in seen_names
            if rows[name]["safe_point_crop"] is not None
        ),
        key=lambda item: float(item[1]),
    )
    global_policy, global_overrides = policy_lines(results["source"])
    rice_policy, rice_overrides = policy_lines(results["rice"])
    baseline_scale, scale_150, scale_200 = resolution_rows
    lines: list[str] = []
    lines.extend(
        [
            "# Crop segmentasyonu ve bitki müdahalesi — ayrıntılı karar raporu",
            "",
            "Tarih: 5 Ağustos 2026  ",
            "Durum: kabul edilmiş global model + kabul edilmiş RiceSEG uzmanı; eşikler hedef setlerde yeniden ayarlanmadı.",
            "",
            "## Yönetici sonucu",
            "",
            f"Global modelin seen-validation mIoU'su `{source['miou']:.3f}`; semantic weed-component hit proxy'si `{pct(source['sem_hit'])}`. Ancak dondurulmuş güvenli aksiyon politikasının component hit recall'ı yalnız `{pct(source['safe_hit'])}` ve weed-pixel recall'ı `{pct(source['safe_pixel_recall'])}`. Bu nedenle model iyi bir algı tabanı olsa da mevcut policy ile saha püskürtme onayı yoktur.",
            "",
            f"Küçük-weed bulgusu sayısaldır: `<14 px` semantic-component hit `{pct(source['sem_subpatch_hit'])}`, tüm boyutlarda `{pct(source['sem_hit'])}`; safe-action küçük hit yalnız `{pct(source['safe_subpatch_hit'])}`. Pooled crop-point hit `{pct(source['safe_point_crop'])}` olsa da worst seen dataset `{worst_crop_name}` içinde `{pct(worst_crop)}`; safety ortalamayla geçirilmez.",
            "",
            f"RiceSEG uzmanı eğitime girmeyen 604-kare calibration split'inde crop IoU `{rice['crop_iou']:.3f}`, weed IoU `{rice['weed_iou']:.3f}` üretir. Bu panel önceki specialist seçiminde kullanıldığı için untouched final test değildir. Güvenli aksiyon eşiği pirinç üzerinde kalibre edilmediği için safe-action recall çok düşüktür; bu sonuç 'güvenli ama etkisiz/no-spray' davranışıdır.",
            "",
            "En kısa MVP yolu noktasal/mikro ilaçlamadır; çünkü mevcut semantic maske ile gerekli proxy'lerin çoğu ölçülebilir. Mekanik sökme ve lazer için kök/crown veya meristem keypoint etiketi, kamera–alet kalibrasyonu ve mm cinsinden hata zorunludur. Bugünkü rapor bu iki yöntemi başarısız saymaz; ölçülemez sayar.",
            "",
            "## Önceki raporda neden yoktu?",
            "",
            "Önceki pipeline mIoU/IoU ve çok temkinli piksel-level spray riskine odaklandı. Mevcut bağlı-komponent ölçümü bir weed proxy'sini ancak maskenin en az %50'si bulunursa 'tespit' sayıyordu. Bu spot spray için gereğinden katı, kök/meristem hedefi için ise yetersizdi. Ayrıca veri true instance, root, stem veya meristem etiketi taşımıyor ve removal aktüatörü/GSD henüz sabitlenmemişti. Yeni evaluator bu eksikleri gizlemeden ayrı proxy'ler üretir.",
            "",
            "## Sınıflar ve iki çıktı modu",
            "",
            "- `target_crop`: korunacak hedef mahsul.",
            "- `other_vegetation`: bu hedef ürün tanımına göre istenmeyen/diğer bitki; botanik tür instance'ı değildir.",
            "- `background`: toprak, su, residue ve bitki olmayan alan.",
            "- `ignore`: etiketi güvenilir olmayan piksel; metrik paydasına girmez.",
            "- `semantic_argmax`: modelin en olası sınıfı; algı kapasitesi, doğrudan spray izni değil.",
            "- `frozen_safe_action`: kaynak validation'da seçilmiş weed threshold + belirsizlik filtresi + predicted-crop guard. External sette retune edilmez.",
            "",
            "### Dondurulmuş policy'nin exact değerleri",
            "",
            f"- Global checkpoint: `{global_policy}`.",
            f"- Global crop override'ları: `{global_overrides}`.",
            f"- Rice specialist checkpoint: `{rice_policy}`.",
            f"- Rice checkpoint crop override'ları: `{rice_overrides}`.",
            "- Bu eşikler deployment crop injury/actuator outcome'u ile kalibre edilmiş safety sertifikası değildir; yalnız checkpoint'te saklı source-validation policy'sidir.",
            "",
            "## Müdahale yöntemine göre minimal başarı ölçüsü",
            "",
            "| Yöntem | Birincil gerçek saha ölçüsü | Bugün ölçülen proxy | Eksik zorunlu kanıt |",
            "|---|---|---|---|",
            "| Mikro/spot ilaçlama | weed'e ulaşan doz; crop deposition/injury; missed-weed rate | safe component any-hit, action-point precision, 0/5/10/20 px footprint crop collision | nozzle footprint/deposition, GSD, hız/gecikme, rüzgâr |",
            "| Mekanik sökme/gripper | root/crown içinde tool localization; crop clearance; successful removal | semantic component centroid error (px ve eşdeğer yarıçap) | root/crown keypoint, depth, mm calibration, tool geometry/pose |",
            "| Lazer | meristem/stem hit rate; mm error; crop collateral; enerji/weed | canopy-center proxy; raster işlem varsa %90 mask coverage | meristem/stem etiketi, beam çapı, dwell/energy, geometry |",
            "| Termal/elektrik temas | doğru temas noktası, süre/enerji ve crop clearance | action-point/center proxy | temas noktası etiketi, 3B yüzey, alet footprint'i |",
            "| İntra-row hoe | crop konumu/sırası ve crop injury; lateral mm error | crop segmentation yalnız dolaylı | crop-center/row etiketi, encoder zamanlama, mm calibration |",
            "",
            "Lazer için tüm bitkinin eksiksiz segmentasyonu evrensel birincil hedef değildir: tek-shot sistemde kritik olan çoğu zaman apikal meristem veya stem'dir. Tam mask coverage ancak konturu tarayarak enerji uygulayan tasarımda birincil olur.",
            "",
            "## Metrik tanımları",
            "",
            "- `component hit (any)`: GT semantic weed connected component üzerinde en az bir tahmin pikseli. Spot müdahalenin en iyimser alt sınırı.",
            "- `coverage@10/50/90`: component alanının en az belirtilen oranının bulunması. %90 yalnız alanı tarayan/kaplayan müdahaleye yakındır.",
            "- `action point`: her predicted component içindeki distance-transform maksimumu; şeklin içindeki en derin piksel.",
            "- `point precision`: valid action point'lerin gerçekten GT weed üzerinde olan oranı.",
            "- `crop collision r`: action merkezli r-piksel dairesel footprint'in GT crop'a değme oranı. Fiziksel deposition modeli değildir.",
            "- `center proxy`: en fazla overlap eden prediction centroid'i ile GT semantic-component centroid'i arasındaki hata. Root/crown/meristem değildir.",
            "- Boyut binleri: `<14 px`, `14–28`, `28–56`, `>=56 px` eşdeğer çap. 14 px DINOv2 patch ölçeğidir; bu botanik boyut değil görüntüdeki apparent size'dır.",
            "",
            "## Sonuç tabloları",
            "",
            "| Set | N | mIoU | Crop IoU | Weed IoU | Semantic hit | <14px semantic hit | Safe hit | <14px safe hit | Safe point precision | Crop point hit | <14px payı |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name, metric in rows.items():
        lines.append(
            f"| {name} | {metric['images']} | {dec(metric['miou'])} | {dec(metric['crop_iou'])} | {dec(metric['weed_iou'])} | {pct(metric['sem_hit'])} | {pct(metric['sem_subpatch_hit'])} | {pct(metric['safe_hit'])} | {pct(metric['safe_subpatch_hit'])} | {pct(metric['safe_point_precision'])} | {pct(metric['safe_point_crop'])} | {pct(metric['subpatch_fraction'])} |"
        )
    lines.extend(
        [
            "",
            "`point precision=ölçülemez`, model/policy hiç aksiyon noktası üretmediyse paydanın sıfır olduğu anlamına gelir; başarı değildir.",
            "",
            "`RiceSEG calibration` training-path-disjoint demektir: 604 kare eğitime girmedi, fakat geçmiş specialist model/doz/seed seçiminde kullanıldı. Bu nedenle final untouched test diye yorumlanamaz. Early-rice de training-unseen fakat aynı geçmiş selector'ın development panelidir.",
            "",
            "## Aggregation ve hedef ağırlığı",
            "",
            "Crop'a zarar gibi safety ihlalleri ortalama skorla telafi edilmez; worst-field/hard gate olarak kalır. Safety geçtikten sonra semantic model seçimindeki mevcut `%60 target-like + %25 breadth + %15 lower-tail` mantığı method-specific metriklere uygulanabilir. Ancak deployment crop'u, platformu ve aktüatörü sabitlenmeden hangi datasetin target-like sayılacağı yeniden tahmin edilmez. Bu nedenle bugün tek bir karışık 'removal skoru' yerine dataset/method tablosu raporlanır; büyük datasetler piksel sayısıyla diğer alanları bastırmaz.",
            "",
            "## İyi/kötü olunan veriler: en olası ilk neden",
            "",
            "| Veri | En olası ilk neden | İkincil etken / sınır |",
            "|---|---|---|",
            "| ROSE | Yakın robot görünümü ve büyük/ayrışmış bitki footprint'i eğitim–validation arasında iyi eşleşiyor. | Aynı saha coğrafyası paylaşıldığı için skor tam yeni-tarla genellemesi değildir. |",
            "| Sorghum | Aynı kaynak dağılımı, büyük ve net bitkiler; hedef ürün eğitime doğrudan girdi. | Test yalnız 25 kare; belirsizlik geniştir. |",
            "| PhenoBench | Crop sıraları ve bol crop training verisi crop'u kolaylaştırıyor. | Weed'ler az ve apparent-size küçük; asıl hata küçük weed recall. |",
            "| ACRE | Robot, ışık ve ürün/domain çeşitliliği ayrımı zorlaştırıyor. | Bean/maize ve farklı sessionlar arasında morphology kayması. |",
            "| WE3DS | Birçok ürün/tarih ve crop–weed benzerliği; weed footprint'leri küçük. | Site/date çeşitliliği ve semantik birleşmeler connected-component proxy'yi de zorlar. |",
            "| WeedsGalore | Yalnız 104 training kare ve multispektral-kamera dağılımı; crop görünümü az öğrenildi. | Weed IoU crop IoU'dan iyi olabilir; bu hedef mahsulü korumaya yetmez. |",
            "| WeedMap UAV | 10 m UAV GSD/apparent-size ve sensör/viewpoint domain shift'i. | RGB model, kaynağın multispektral bilgisini kullanmıyor. |",
            "| RiceSEG | Weed/duckweed azlığı ve su/evre/organ çeşitliliği; weed sınıfı zor. | Uzman crop'u iyi ayırsa da weed IoU ve güvenli-action kalibrasyonu zayıf. |",
            "| Early rice | Farklı dataset, kamera yüksekliği ve fide/su domain'i. | Rice specialist bu kaynağı eğitimde görmedi. |",
            "",
            "## Küçük weed darboğazı ve çözünürlük",
            "",
            "Kullanıcı gözlemi metrikle test edilir: `<14 px` component payı ve bu bindeki hit recall ayrı raporlanır. En önemli teknik sebep küçük bitkinin model input'unda az piksele/patch'e düşmesidir; yalnız sınıf sayısı değildir. Mevcut evaluator görüntüyü tek 512'ye küçültmez: native resolution kullanır ve 4 MP üzerini 1024 px, 128 px overlap tile'larla işler. Dolayısıyla SAHI-benzeri tiling zaten aktiftir.",
            "",
            "Yazılımsal 2× interpolasyon yeni optik detay üretmez; patch ölçeğini değiştirerek yardımcı olabilir ve ayrı A/B ile ölçülmelidir. İlk optik tasarım hedefi minimum weed çapını sensörde en az 28 px (tercihen 56 px) yapmak; doğru fokus ve düşük motion blur sağlamaktır. Bu 2/4-patch başlangıç heuristiği saha A/B'siyle dondurulmalıdır.",
            "",
            "- `GSD <= minimum weed diameter (mm) / desired pixels`.",
            "- Nadir kamera yaklaşımı: `GSD ≈ sensor_width_mm × height_mm / (focal_length_mm × image_width_px)`.",
            "- Motion blur: `blur_px ≈ ground_speed_mm_s × exposure_s / GSD_mm_px` (titreşim eklenir).",
            "- Öncelik: sabit yükseklik + kısa poz/global shutter veya strobe + focus lock + kontrollü diffuse ışık; sonra sensör/focal/height çözünürlüğü.",
            "",
            "### Early-rice software inference-scale A/B",
            "",
            "Bu deney aynı 224 kare, aynı specialist ve aynı native evaluation grid'ini kullanır. 1,5×/2,0× bilinear interpolation optik bilgi eklemez; yalnız model patch ölçeğini değiştirir.",
            "",
            "| Scale | mIoU | Weed IoU | <14px semantic hit | Safe hit | Crop point hit | Perception ms/image |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for metric in resolution_rows:
        lines.append(
            f"| {metric['label']} | {dec(metric['miou'])} | {dec(metric['weed_iou'])} | {pct(metric['semantic_subpatch_hit'])} | {pct(metric['safe_hit'])} | {pct(metric['safe_point_crop'])} | {dec(metric['perception_ms'], 1)} |"
        )
    lines.extend(
        [
            "",
            f"Karar: software upscale kabul edilmedi. 2,0× `<14 px` semantic hit'i `{pct(baseline_scale['semantic_subpatch_hit'])}` → `{pct(scale_200['semantic_subpatch_hit'])}`, weed IoU'yu `{pct(baseline_scale['weed_iou'])}` → `{pct(scale_200['weed_iou'])}` artırdı; fakat crop-point hit `{pct(baseline_scale['safe_point_crop'])}` → `{pct(scale_200['safe_point_crop'])}` ve perception süresi `{dec(baseline_scale['perception_ms'], 1)}` → `{dec(scale_200['perception_ms'], 1)} ms` oldu. 1,5× de crop-point hit'i `{pct(scale_150['safe_point_crop'])}` seviyesine çıkardı. Bu tek-dataset development A/B'si ölçek darboğazını doğrular, ancak safety/latency guard'larını geçmez. Öncelik optik GSD/fokus/exposure ve eş-hesap multi-scale training'dir.",
            "",
            "## Provisional proje gate'leri (aktüatör seçilince dondurulacak)",
            "",
            "| Faz | Safety | Etkinlik | Not |",
            "|---|---|---|---|",
            "| Offline aday | action-level crop hit <=%0,5; 10px footprint sensitivity raporlu | spot: safe component hit >=%90 ve point precision >=%95 | Evrensel standart değil, proje başlangıç gate'i |",
            "| Kontrollü saksı/şerit | gerçek deposition/crop injury; fail-safe stop | effective treatment >=%90 | Rüzgâr, hız ve gecikme dahil |",
            "| Tarla pilotu | crop injury üst güven sınırı ürün eşiği altında | residual weed / kill rate ve throughput | agronomist + yasal kimyasal protokol |",
            "| Mekanik/lazer | tool/beam crop collision üst sınırı | p95 mm error aktüatör toleransından küçük; successful kill/removal | Piksel proxy ile geçilemez |",
            "",
            "Bu gate'ler literatür rakamlarını kopyalayan evrensel eşikler değildir. Örneğin bir field smart-sprayer çalışması %90,6 effective spray; ayrı bir kontrollü micro-jet çalışma kendi düzeneğinde weed'lerin %98'inin doğru püskürtüldüğünü raporlamıştır. Bir intra-row positioning çalışması da kendi düzeneğinde >%95 tanıma ve ±15 mm hata göstermiştir. Bunlar doğrudan bizim kabul eşiğimiz değildir; aktüatör footprint'i, ürün hassasiyeti ve ekonomik missed-weed/crop-injury maliyetiyle gate yeniden dondurulmalıdır.",
            "",
            "## Öncelikli deney planı",
            "",
            "1. Kamera rig'i üzerinde checkerboard/intrinsics + çalışma düzleminde homography/GSD; nozzle/tool/beam footprint ve perception-to-actuation latency ölç.",
            "2. 3–4 temsilî saha, farklı saat/nem/toprak ve küçük weed strata içeren untouched field test topla; minimum weed fiziksel çapını kaydet.",
            "3. Spot spray MVP için weed üstü action-point ve crop-footprint metriklerini gerçek deposition kâğıdı/fluorescent dye ile doğrula.",
            "4. Tamamlandı: native 1.0× ile 1.5×/2.0× inference-scale A/B safety/latency guard'ını geçmedi; software upscale'ı bırak.",
            "5. Small-object oversampling + daha büyük train crop/multi-scale training deneyi; aynı hesap ve seed guard'larıyla compare et.",
            "6. Mekanik/lazer seçilirse 500–1000 plant için root/crown veya meristem keypoint + visibility/occlusion etiketi topla; mm P50/P95 ve kill/removal outcome'u primary yap.",
            "7. Safety threshold'u testte değil, aktüatör ve hedef ürüne ayrılmış calibration split'inde seç; untouched test'i bir kez aç.",
            "",
            "## Sentetik ve unseen değerlendirme",
            "",
            "Dryland V3 ve paddy R5 sentetik aşamaları gerçek-domain model gate'ini geçti. Soy, motion ve field-robustness asset'leri görsel/asset kalite gate'lerini geçse de ortak robust modelde domain regresyonu yarattı; bu nedenle global modele eklenmedi. Bu doğru fail-closed davranıştır: daha fazla kaliteli sentetik otomatik olarak daha iyi model değildir.",
            "",
            f"V11 asset/seed ayrık sentetik test 16 kareden oluşur; 14 karede GT weed vardır. Pixel-level visual-audit aggregate: macro crop IoU `{pct(float(synthetic_summary['crop_iou_macro']))}`, weed bulunan karelerde macro weed IoU `{pct(float(synthetic_summary['weed_iou_macro_present']))}`, micro safe-weed recall `{pct(float(synthetic_summary['safe_weed_recall_micro']))}`, micro safe precision `{pct(float(synthetic_summary['safe_weed_precision_micro']))}` ve crop-spray pixel risk `{pct(float(synthetic_summary['crop_spray_risk_micro']))}`. Bunlar sentetik-domain performansıdır; gerçek saha kanıtı değildir.",
            "",
            "Gerçek unlabeled online videolar (FarmBot soy, Naïo Oz, BoniRob) ve sentetik V11 val/test görselleri mevcut görsel pakete eklendi. Etiket olmayan videolara accuracy yazılmaz. Labeled development/transfer kanıtı SugarBeets robot, WeedMap UAV, Sorghum test, RiceSEG training-held-out calibration ve early-rice setlerinden gelir; bunların tamamı untouched final deployment testi değildir.",
            "",
            "## RiceSEG split erratum",
            "",
            "Önceki specialist `country-transfer` galerisi bağımsız performans kanıtı değildir. Alternatif country manifestindeki 1.254/1.254 RGB ve mask yolu specialist training coverage manifestinde bulunur; yalnız dataset/sample prefix'i farklıdır. Yeni ana RiceSEG sonucu `riceseg_v1.csv / external_calibration` kullanır: 604 kare, Guangdong + Tokyo, training image overlap 0/604. Bu training-held-out panel geçmiş specialist seçiminde kullanıldığı için development/calibration kanıtıdır, untouched final test değildir. Eski galeri train-seen diagnostic olarak yeniden sınıflandırılmalıdır.",
            "",
            "## Sınırlamalar",
            "",
            "- Semantic connected component true instance değildir: temas eden bitkiler birleşir, ayrık yapraklar bölünebilir.",
            "- Canopy centroid root/crown/meristem değildir.",
            "- px radius gerçek nozzle/tool/beam footprint'i değildir; GSD ve lens distortion gerekir.",
            "- Offline mask metriği actuation latency, wind, deposition, terrain ve kill outcome'u içermez.",
            "- Seen-validation field independence her kaynakta aynı güçte değildir; ROSE/WE3DS coğrafi sınırları raporlanmıştır.",
            "- Current safety policy yüksek threshold nedeniyle etkisiz no-spray'e kayabilir; düşük crop risk tek başına başarı değildir.",
            "- Dataset nedenleri scale/metadata/görsel hata ile desteklenen öncelikli hipotezlerdir; tek-faktörlü nedensel A/B olmayan yerde kesin neden diye sunulmaz.",
            "",
            "## Kaynaklar",
            "",
            "- Zhang et al., apical meristem localization for laser weeding: https://doi.org/10.3390/agronomy14092121",
            "- Li et al., crop positioning for intra-row mechanical weeding (>95%, ±15 mm in that setup): https://doi.org/10.3965/j.ijabe.20150806.1932",
            "- Sa et al., WeedMap and GSD/downsampling/tiled inference: https://arxiv.org/abs/1808.00100",
            "- Real-time high-resolution micro-jet sprayer (98% weeds sprayed in its setup): https://www.sciencedirect.com/science/article/pii/S1537511023000375",
            "- Field smart-sprayer evaluation (effective spray, precision, recall): https://www.sciencedirect.com/science/article/pii/S2666154324003685",
            "- Remote sensing segmentation and sprayed-area analysis: https://arxiv.org/abs/2410.22554",
            "",
            "## Reproducibility",
            "",
            "All intervention JSONs use the accepted checkpoint, frozen source-selected policy, native-resolution inference and no external threshold tuning. Exact checkpoint/manifest/mask hashes are stored in each JSON under `provenance`. The evaluator protocol is `intervention_semantic_component_proxy_v1`.",
        ]
    )
    return "\n".join(lines) + "\n"


def metric_card(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    value: str,
    label: str,
    note: str,
    *,
    accent: tuple[int, int, int] = GREEN,
) -> None:
    draw = ImageDraw.Draw(canvas)
    card(draw, box)
    x1, y1, x2, _ = box
    add_text(draw, (x1 + 24, y1 + 20), value, 46, bold=True, fill=accent)
    add_text(draw, (x1 + 24, y1 + 78), label, 23, bold=True)
    add_text(draw, (x1 + 24, y1 + 116), note, 18, fill=MUTED, width=max(18, int((x2 - x1) / 11)))


def summary_cover(source: Mapping[str, Any]) -> Image.Image:
    page = Image.new("RGB", (W, H), DARK_GREEN)
    draw = ImageDraw.Draw(page)
    card(draw, (70, 65, 1850, 1015), fill=BG, outline=BG, radius=38)
    add_text(draw, (130, 125), "Crop Segmentation", 72, bold=True, fill=DARK_GREEN)
    add_text(draw, (130, 214), "ve Bitki Müdahale Kararı", 55, bold=True, fill=GREEN)
    add_text(draw, (132, 294), "Kısa rapor • 5 Ağustos 2026", 27, fill=MUTED)
    card(draw, (125, 380, 1795, 565), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (172, 416), "ANA SONUÇ", 24, bold=True, fill=ORANGE)
    add_text(
        draw,
        (172, 460),
        "Semantik model iyi bir base; mevcut güvenli-aksiyon policy'si ise fazla temkinli. Henüz saha removal onayı yok.",
        36,
        bold=True,
        width=80,
    )
    metric_card(
        page,
        (125, 620, 630, 865),
        dec(source["miou"]),
        "Seen validation mIoU",
        "Genel segmentasyon; tek başına müdahale başarısı değil.",
    )
    metric_card(
        page,
        (660, 620, 1165, 865),
        pct(source["sem_hit"]),
        "Semantic weed hit",
        "GT semantic component üzerinde en az bir prediction pikseli.",
        accent=BLUE,
    )
    metric_card(
        page,
        (1195, 620, 1700, 865),
        pct(source["safe_hit"]),
        "Frozen safe-action hit",
        "Deploy-benzeri temkinli policy; hedef-set retune yok.",
        accent=RED,
    )
    add_text(
        draw,
        (130, 922),
        "Önerilen MVP: mikro/spot spray doğrulaması. Mekanik ve lazer için yeni keypoint + mm kalibrasyon gerekir.",
        26,
        bold=True,
        fill=DARK_GREEN,
        width=105,
    )
    return page


def build_short_pages(
    results: Mapping[str, Mapping[str, Any]],
    rows: Mapping[str, Mapping[str, Any]],
    resolution_rows: Sequence[Mapping[str, Any]],
    visual_root: Path,
) -> list[Image.Image]:
    source = extract_metrics(view(results["source"]))
    pages = [summary_cover(source)]

    page = base_page("Müdahale yöntemine göre doğru metrik", "mIoU yardımcıdır; robot kararını tek başına vermez.")
    draw_table(
        page,
        (70, 205, 1850, 890),
        ("Yöntem", "Birincil saha başarısı", "Bugün ölçülen", "Durum"),
        (
            ("Mikro / spot spray", "weed'e gerçek doz + crop injury", "safe hit, point precision, footprint collision", "En kısa MVP; gate geçmedi"),
            ("Mekanik sökme", "root/crown mm hata + tool clearance", "canopy-center px proxy", "Keypoint + depth eksik"),
            ("Lazer", "meristem/stem hit + beam/energy", "center ve coverage proxy", "Meristem etiketi eksik"),
            ("Termal / elektrik", "temas noktası + süre + crop clearance", "action-point proxy", "3B/temas etiketi eksik"),
            ("İntra-row hoe", "crop row/center + crop injury", "crop mask dolaylı", "Row + encoder ölçümü eksik"),
        ),
        (0.18, 0.30, 0.32, 0.20),
        font_size=21,
        row_height=108,
    )
    add_text(draw := ImageDraw.Draw(page), (75, 922), "Lazer için 'tam bitki maskesi' her zaman ana hedef değildir; çoğu tasarımda meristem/stem noktası kritiktir.", 24, bold=True, fill=RED, width=112)
    pages.append(page)

    baseline_scale = resolution_rows[0]
    scale_200 = resolution_rows[2]
    page = base_page(
        "Yazılımsal çözünürlük A/B sonucu",
        "Early-rice 224 development karesi; interpolation optik bilgi eklemez.",
    )
    draw_table(
        page,
        (90, 205, 1830, 600),
        ("Scale", "Weed IoU", "<14px sem. hit", "Crop point hit", "Perception ms/img"),
        [
            (
                str(metric["label"]),
                dec(metric["weed_iou"]),
                pct(metric["semantic_subpatch_hit"]),
                pct(metric["safe_point_crop"]),
                dec(metric["perception_ms"], 1),
            )
            for metric in resolution_rows
        ],
        (0.20, 0.19, 0.23, 0.20, 0.18),
        font_size=22,
        row_height=105,
        align_right=(1, 2, 3, 4),
    )
    card(ImageDraw.Draw(page), (90, 665, 1830, 940), fill=LIGHT_RED, outline=RED)
    add_text(ImageDraw.Draw(page), (130, 705), "KARAR • UPSCALE KABUL EDİLMEDİ", 29, bold=True, fill=RED)
    add_text(
        ImageDraw.Draw(page),
        (130, 765),
        (
            f"2× küçük-hit'i {pct(baseline_scale['semantic_subpatch_hit'])} → "
            f"{pct(scale_200['semantic_subpatch_hit'])} artırdı; fakat crop-point "
            f"{pct(baseline_scale['safe_point_crop'])} → {pct(scale_200['safe_point_crop'])} "
            f"ve latency {dec(baseline_scale['perception_ms'], 1)} → "
            f"{dec(scale_200['perception_ms'], 1)} ms oldu. 1,5× de crop guard'ını "
            "bozdu. Öncelik optik/GSD ve multi-scale training."
        ),
        27,
        bold=True,
        width=100,
    )
    pages.append(page)

    page = base_page("Ne ölçtük?", "True instance etiketi olmadığı için connected-component sonuçları açıkça proxy'dir.")
    cards = [
        ((75, 210, 885, 405), "ANY HIT", "Ot üzerinde ≥1 piksel", "Spot müdahalenin iyimser alt sınırı", BLUE),
        ((925, 210, 1735, 405), "COVERAGE 10/50/90", "Ot alanının ne kadarı?", "Alan tarayan müdahale için", GREEN),
        ((75, 445, 885, 640), "ACTION POINT", "Prediction içindeki en derin nokta", "Weed / crop / background ayrımı", ORANGE),
        ((925, 445, 1735, 640), "CENTER PROXY", "Semantic centroid sapması", "Root/crown/meristem değildir", PURPLE),
        ((75, 680, 885, 875), "FOOTPRINT", "0/5/10/20 px crop teması", "Nozzle/alet çapı hassasiyeti", RED),
        ((925, 680, 1735, 875), "APPARENT SIZE", "<14 / 14–28 / 28–56 / ≥56 px", "14 px backbone patch ölçeği", DARK_GREEN),
    ]
    for box, title, label, note, accent in cards:
        metric_card(page, box, title, label, note, accent=accent)
    pages.append(page)

    source_names = ["PhenoBench", "ACRE", "ROSE", "WE3DS", "WeedsGalore"]
    page = base_page("Global model • gerçek seen validation", "Aynı kabul edilmiş checkpoint; her datasetin group/session-ayrık validation satırları.")
    table_rows = []
    for name in source_names:
        metric = rows[name]
        table_rows.append(
            (
                name,
                str(metric["images"]),
                dec(metric["miou"]),
                dec(metric["crop_iou"]),
                dec(metric["weed_iou"]),
                pct(metric["sem_hit"]),
                pct(metric["safe_hit"]),
            )
        )
    draw_table(
        page,
        (70, 210, 1850, 790),
        ("Dataset", "N", "mIoU", "Crop IoU", "Weed IoU", "Semantic hit", "Safe hit"),
        table_rows,
        (0.20, 0.08, 0.12, 0.14, 0.14, 0.16, 0.16),
        font_size=21,
        row_height=90,
        align_right=(1, 2, 3, 4, 5, 6),
    )
    card(ImageDraw.Draw(page), (70, 825, 1850, 962), fill=LIGHT_RED, outline=RED)
    add_text(ImageDraw.Draw(page), (105, 852), "Okuma kuralı", 24, bold=True, fill=RED)
    add_text(ImageDraw.Draw(page), (300, 850), "Semantic hit modelin bir otu en azından gördüğünü; safe hit ise mevcut dondurulmuş policy'nin gerçekten aksiyona izin verdiğini gösterir. Aradaki fark kritik.", 25, width=95)
    pages.append(page)

    page = base_page("Gerçek holdout ve transfer", "Training-unseen ile untouched-final-test aynı kanıt seviyesi değildir.")
    transfer_names = ["Sorghum test", "SugarBeets robot", "WeedMap UAV", "RiceSEG calibration", "Early-rice transfer"]
    table_rows = []
    for name in transfer_names:
        metric = rows[name]
        table_rows.append(
            (
                name,
                str(metric["images"]),
                dec(metric["crop_iou"]),
                dec(metric["weed_iou"]),
                pct(metric["sem_hit"]),
                pct(metric["safe_hit"]),
                pct(metric["subpatch_fraction"]),
            )
        )
    draw_table(
        page,
        (70, 205, 1850, 790),
        ("Set", "N", "Crop IoU", "Weed IoU", "Semantic hit", "Safe hit", "<14px weed"),
        table_rows,
        (0.22, 0.07, 0.13, 0.13, 0.16, 0.14, 0.15),
        font_size=21,
        row_height=92,
        align_right=(1, 2, 3, 4, 5, 6),
    )
    card(ImageDraw.Draw(page), (70, 825, 1850, 960), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(ImageDraw.Draw(page), (100, 850), "RiceSEG düzeltmesi", 24, bold=True, fill=ORANGE)
    add_text(ImageDraw.Draw(page), (405, 848), "604 RiceSEG karesi eğitime girmedi (path overlap 0/604), fakat geçmiş specialist seçiminde kullanıldı: calibration'dır, final test değildir. Eski 1.254-kare country galerisi training ile 1.254/1.254 çakışır.", 24, width=82)
    pages.append(page)

    page = base_page("Küçük weed: asıl darboğaz", "Apparent-size, donanım ve model ölçeğini aynı tabloda okumak gerekir.")
    small_rows = []
    for name in source_names + ["WeedMap UAV", "RiceSEG calibration", "Early-rice transfer"]:
        metric = rows[name]
        small_rows.append(
            (
                name,
                pct(metric["subpatch_fraction"]),
                pct(metric["sem_hit"]),
                pct(metric["sem_subpatch_hit"]),
                pct(metric["safe_subpatch_hit"]),
            )
        )
    draw_table(
        page,
        (70, 205, 1120, 900),
        ("Set", "<14px payı", "Tüm sem. hit", "<14px sem. hit", "<14px safe hit"),
        small_rows,
        (0.27, 0.17, 0.18, 0.20, 0.18),
        font_size=17,
        row_height=72,
        align_right=(1, 2, 3),
    )
    card(ImageDraw.Draw(page), (1160, 205, 1850, 900), fill=LIGHT_BLUE, outline=BLUE)
    add_text(ImageDraw.Draw(page), (1200, 245), "En olası ilk neden", 29, bold=True, fill=BLUE)
    add_text(ImageDraw.Draw(page), (1200, 300), "Küçük bitki sensörde az piksel ve backbone'da az patch kaplıyor.", 29, bold=True, width=35)
    bullet_list(
        page,
        (
            "Native-resolution inference zaten açık.",
            ">4 MP görüntüler 1024 px / 128 px overlap tile ile işleniyor: SAHI-benzeri ölçek koruma mevcut.",
            "2× yazılım upscale yeni optik detay üretmez; yalnız A/B ile tutulmalı.",
            "Kalıcı çözüm: GSD, fokus, kısa poz, kontrollü ışık ve yeterli depth-of-field.",
        ),
        (1200, 430),
        width=38,
        size=22,
    )
    pages.append(page)

    page = base_page("Neden bazı veriler iyi, bazıları kötü?", "Odaklanmak için kanıtla en uyumlu ilk hipotez öne çıkarıldı.")
    draw_table(
        page,
        (70, 205, 1850, 905),
        ("Veri", "En olası ilk neden", "Sonuç / dikkat"),
        (
            ("ROSE", "Yakın robot + büyük/ayrışmış bitki", "Güçlü; fakat aynı saha coğrafyası"),
            ("Sorghum", "Aynı kaynak dağılımı + net bitki", "Güçlü; yalnız 25 test kare"),
            ("PhenoBench", "Crop düzenli; weed küçük/az", "Crop iyi, küçük weed zor"),
            ("WE3DS", "Çok ürün/tarih + benzer vegetation", "Weed ayrımı zayıf"),
            ("WeedsGalore", "104 train + multispektral sensör dağılımı", "Crop sınıfı zayıf"),
            ("WeedMap", "10 m UAV GSD + sensor/viewpoint shift", "Apparent-size darboğazı"),
            ("RiceSEG", "Seyrek weed/duckweed + su/evre çeşitliliği", "Crop iyi; weed ve safe action zayıf"),
        ),
        (0.16, 0.48, 0.36),
        font_size=20,
        row_height=87,
    )
    pages.append(page)

    page = base_page("Donanım + yazılım için en etkili plan", "Önce ölçülebilir fizik, sonra küçük kontrollü model A/B.")
    card(ImageDraw.Draw(page), (70, 200, 920, 915), fill=LIGHT_GREEN, outline=GREEN)
    add_text(ImageDraw.Draw(page), (110, 235), "1 • Kamera / optik", 31, bold=True, fill=GREEN)
    bullet_list(
        page,
        (
            "Minimum öldürülecek weed çapını mm olarak tanımla; sensörde ≥28 px, hedefte ≥56 px tasarla.",
            "Çalışma yüksekliği + intrinsics + düzlem homography ile GSD ölç.",
            "Global shutter/strobe veya kısa exposure; blur_px hedefini hızla birlikte kilitle.",
            "Focus lock, depth-of-field ve diffuse kontrollü aydınlatma; glare için gerekirse polarizasyon.",
            "Lens kirlenmesi, gölge ve exposure telemetry'sini kaydet.",
        ),
        (110, 310),
        width=54,
        size=24,
    )
    card(ImageDraw.Draw(page), (960, 200, 1850, 915), fill=LIGHT_BLUE, outline=BLUE)
    add_text(ImageDraw.Draw(page), (1000, 235), "2 • Model / inference", 31, bold=True, fill=BLUE)
    bullet_list(
        page,
        (
            "1.0× / 1.5× / 2.0× scale A/B: küçük-hit, crop false action ve latency birlikte.",
            "Small-object oversampling ve daha büyük training crop; eşit hesap kontrolü.",
            "Method-specific safety calibration; testte threshold seçme yok.",
            "Spot spray için footprint-aware loss/postprocess ancak nozzle ölçüldükten sonra.",
            "Mekanik/lazer seçilirse root/crown/meristem keypoint head + depth.",
        ),
        (1000, 310),
        width=54,
        size=24,
    )
    pages.append(page)

    page = base_page("Saha gate'i", "Bugünkü sonuç: offline base var; hiçbir removal yöntemi henüz production gate'i geçmedi.")
    draw_table(
        page,
        (70, 205, 1850, 710),
        ("Aşama", "Safety", "Etkinlik", "Karar"),
        (
            ("Offline aday", "crop action ≤%0,5 + footprint sensitivity", "spot safe-hit ≥%90; point precision ≥%95", "Mevcut policy geçmiyor"),
            ("Kontrollü şerit", "gerçek crop deposition/injury", "effective treatment ≥%90", "Henüz yapılmadı"),
            ("Tarla pilotu", "crop injury üst güven sınırı", "kill/removal + residual weed + throughput", "Henüz yapılmadı"),
            ("Mekanik/lazer", "tool/beam crop collision", "p95 mm hata < tolerans", "Etiket/kalibrasyon eksik"),
        ),
        (0.17, 0.30, 0.33, 0.20),
        font_size=21,
        row_height=100,
    )
    card(ImageDraw.Draw(page), (70, 755, 1850, 940), fill=LIGHT_RED, outline=RED)
    add_text(ImageDraw.Draw(page), (110, 790), "Fail-safe yorum", 27, bold=True, fill=RED)
    add_text(ImageDraw.Draw(page), (385, 788), "Düşük crop risk ama sıfıra yakın weed recall 'başarılı güvenlik' değildir; etkisiz no-spray davranışıdır. Safety ve etkinlik birlikte geçmelidir.", 28, bold=True, width=74)
    pages.append(page)

    visual = visual_root / "CONTACT_SHEETS/03_03_WEEDMAP_UAV_WORST.jpg"
    if visual.is_file():
        page = base_page("Görsel kanıt • zor UAV transferi", "Legend görselin içinde: yeşil=crop, kırmızı=other vegetation/weed, camgöbeği=izinli aksiyon.")
        card(ImageDraw.Draw(page), (60, 185, 1860, 985))
        paste_contain(page, visual, (75, 200, 1845, 970))
        pages.append(page)

    page = base_page("Net karar ve sonraki üç iş", "En etkili basit yaklaşım önce; karmaşıklık yalnız ölçülmüş darboğaza eklenir.")
    card(ImageDraw.Draw(page), (80, 205, 1840, 430), fill=LIGHT_GREEN, outline=GREEN)
    add_text(ImageDraw.Draw(page), (125, 245), "1", 58, bold=True, fill=GREEN)
    add_text(ImageDraw.Draw(page), (215, 244), "Spot-spray MVP için rig + footprint + latency kalibrasyonu ve küçük gerçek saha seti.", 34, bold=True, width=77)
    card(ImageDraw.Draw(page), (80, 465, 1840, 690), fill=LIGHT_BLUE, outline=BLUE)
    add_text(ImageDraw.Draw(page), (125, 505), "2", 58, bold=True, fill=BLUE)
    add_text(ImageDraw.Draw(page), (215, 504), "Software upscale reddedildi: optik GSD/focus/exposure ve eş-hesap multi-scale training A/B.", 34, bold=True, width=77)
    card(ImageDraw.Draw(page), (80, 725, 1840, 950), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(ImageDraw.Draw(page), (125, 765), "3", 58, bold=True, fill=ORANGE)
    add_text(ImageDraw.Draw(page), (215, 764), "Removal seçimi mekanik/lazer olursa semantic maskeyi zorlamayı bırak; doğrudan root/crown/meristem + mm outcome datası topla.", 34, bold=True, width=77)
    pages.append(page)
    finalize_pages(pages, "Crop Müdahale • Kısa Karar Raporu")
    return pages


def text_page(title: str, subtitle: str, sections: Sequence[tuple[str, Sequence[str]]]) -> Image.Image:
    page = base_page(title, subtitle)
    draw = ImageDraw.Draw(page)
    y = 200
    for heading, bullets in sections:
        add_text(draw, (80, y), heading, 29, bold=True, fill=DARK_GREEN)
        y += 48
        y = bullet_list(page, bullets, (90, y), width=112, size=23, line_gap=10)
        y += 12
    return page


def build_detailed_pages(
    results: Mapping[str, Mapping[str, Any]],
    rows: Mapping[str, Mapping[str, Any]],
    resolution_rows: Sequence[Mapping[str, Any]],
    visual_root: Path,
    intervention_visual_root: Path,
) -> list[Image.Image]:
    source = extract_metrics(view(results["source"]))
    pages: list[Image.Image] = [summary_cover(source)]

    pages.append(
        text_page(
            "Yönetici kararı",
            "Sonuç önce: iyi semantic base, production removal onayı değil.",
            (
                ("Bugünkü hüküm", (
                    f"Global seen mIoU {dec(source['miou'])}; semantic component hit {pct(source['sem_hit'])}, frozen safe-action hit {pct(source['safe_hit'])}.",
                    "Dondurulmuş policy crop'u korumaya çalışırken weed müdahalesini fazla bastırıyor; düşük risk tek başına başarı sayılmıyor.",
                    "Mikro/spot spray en kısa doğrulanabilir MVP. Mekanik/lazer için bugün ölçemediğimiz biyolojik hedef ve mm geometri gerekiyor.",
                )),
                ("Karar ilkesi", (
                    "Safety ve etkinlik aynı anda geçmeden saha onayı yok.",
                    "Bu koşuda dış panellerde threshold/model yeniden seçilmedi; geçmiş development kullanımı ayrıca açıklanır.",
                    "Ölçülemeyen değer sıfır veya başarı gibi gösterilmez.",
                )),
            ),
        )
    )

    pages.append(
        text_page(
            "Kanıt hiyerarşisi",
            "Hangi veri hangi iddiayı taşıyabilir?",
            (
                ("Nicel kanıt", (
                    "Seen source validation: PhenoBench, ACRE, ROSE, WE3DS, WeedsGalore; 1.637 gerçek görüntü.",
                    "Labeled holdout/development/transfer: Sorghum 25, SugarBeets 283, WeedMap 95, RiceSEG calibration 604, early-rice development 224.",
                    "Toplam bu koşuda 2.868 görüntü: global source 1.637 + global dış panel 403 + rice specialist 828.",
                )),
                ("Yalnız görsel kanıt", (
                    "FarmBot soy, Naïo Oz ve BoniRob online videoları unlabeled; accuracy/mIoU yazılamaz.",
                    "Sentetik V11 val/test domain stress görselleridir; gerçek saha başarısının yerine geçmez.",
                    "Best/worst galeriler örnek uçlarıdır; full-split metrik yerine okunmaz.",
                )),
            ),
        )
    )

    pages.append(
        text_page(
            "Model ve inference protokolü",
            "Kabul edilmiş checkpoint'ler değiştirilmedi.",
            (
                ("Global model", (
                    "DINOv2-small FPN; crop-conditioned; train crop 512; stage-4 fine-tuning; accepted seed 43 / epoch 8.",
                    "Dryland V3 + paddy R5 sentetik dozları kabul edilmiş training mix'tedir.",
                    "Checkpoint SHA-256 her sonuç JSON'unda tekrar doğrulanır.",
                )),
                ("Rice specialist", (
                    "Aynı base üzerinde gerçek RiceSEG additive specialist; accepted seed 29 / epoch 8.",
                    "604 kare training-path-disjoint'tir; geçmiş specialist selector'ında kullanıldığı için calibration'dır, final test değildir.",
                )),
                ("Inference", (
                    "Eval resize yok: native H×W. >4 MP kareler 1024 tile, 128 overlap ve Hann blend ile işlenir.",
                    "Dondurulmuş crop-ID/unknown threshold; external retune yok.",
                )),
            ),
        )
    )

    global_policy, global_overrides = policy_lines(results["source"])
    rice_policy, rice_overrides = policy_lines(results["rice"])
    pages.append(
        text_page(
            "Dondurulmuş safety policy",
            "Exact checkpoint değerleri; deployment safety sertifikası değildir.",
            (
                ("Global", (global_policy, f"Override: {global_overrides}.")),
                ("Rice specialist", (rice_policy, f"Override: {rice_overrides}.")),
                ("Yorum", (
                    "External panellerde eşik sweep/retune yapılmadı.",
                    "Rice crop_id=12 override listesinde yoksa unknown-crop eşiğine düşer.",
                    "Aktüatör, crop injury ve deposition outcome'u olmadan bu policy saha güvenlik onayı değildir.",
                )),
            ),
        )
    )

    pages.append(
        text_page(
            "Skor nasıl birleştirilmeli?",
            "Target-like başarı ağırlıklı; safety ise hard gate.",
            (
                ("Sıra", (
                    "1) Method safety: worst-field crop action/collision/injury gate. Ortalama ile telafi yok.",
                    "2) Target-like dataset/field macro: deployment crop + kamera + yükseklik + aktüatör koşuluna en yakın panel.",
                    "3) Breadth macro ve lower-tail: tek dataset/domain overfit'ini engeller.",
                )),
                ("Mevcut ağırlık", (
                    "Semantic seçimdeki %60 target-like + %25 breadth + %15 lower-tail yapısı korunabilir.",
                    "Removal yöntemi ve hedef crop sabitlenmeden dataset rolleri post-hoc değiştirilmez.",
                    "Bu rapor bu nedenle tek karma removal puanı değil, method × dataset dashboard'u verir.",
                )),
            ),
        )
    )

    pages.append(
        text_page(
            "Ontoloji ve görsel legend",
            "Bir renk, botanik tür değil hedefe göre rol ifade eder.",
            (
                ("Semantic", (
                    "Yeşil: target crop — korunacak hedef mahsul.",
                    "Kırmızı/turuncu: other vegetation / weed — hedef dışı bitki.",
                    "Mor: ignore — gerçek etiketi güvenilir değil, metrik dışı.",
                )),
                ("Safety overlay", (
                    "Yeşil: predicted crop guard; camgöbeği: izinli safe weed action.",
                    "Sarı/turuncu: crop-hit / tehlikeli hata; mor: kararsız/no-spray.",
                    "Kırmızı semantic prediction doğrudan spray komutu değildir.",
                )),
            ),
        )
    )

    metric_page = base_page("Müdahale proxy metrikleri", "Aynı maskeden farklı removal sorularına farklı ölçü çıkarılır.")
    draw_table(
        metric_page,
        (60, 195, 1860, 925),
        ("Metrik", "Sorduğu soru", "Doğru kullanım", "Sınır"),
        (
            ("Any hit", "Ot üzerinde ≥1 piksel var mı?", "Spot spray alt sınırı", "Footprint/kill yok"),
            ("Coverage@10/50/90", "Ot alanının ne kadarı bulundu?", "Area/raster treatment", "True instance değil"),
            ("Action-point precision", "Komut gerçekten weed üstünde mi?", "Noktasal müdahale", "Latency/GSD yok"),
            ("Crop collision r", "r-px footprint crop'a değer mi?", "Boyut hassasiyeti", "Deposition modeli değil"),
            ("Center error", "Canopy merkezi yakalandı mı?", "Mechanical/laser proxy", "Root/meristem değil"),
            ("Size bins", "Küçük apparent weed ne oluyor?", "Donanım/model teşhisi", "Fiziksel mm değil"),
        ),
        (0.20, 0.29, 0.24, 0.27),
        font_size=20,
        row_height=104,
    )
    pages.append(metric_page)

    method_page = base_page("Removal yöntemi karşılaştırması", "Birincil metric aktüatör fiziğinden gelir.")
    draw_table(
        method_page,
        (50, 190, 1870, 930),
        ("Yöntem", "Minimal hedef", "Primary metric", "Mevcut kanıt", "Readiness"),
        (
            ("Spot spray", "weed'e yeterli doz", "effective spray + crop injury", "action/footprint proxy", "MVP adayı; fail"),
            ("Pull/grip", "root/crown kavrama", "p95 mm error + removal", "canopy center px", "Ölçülemez"),
            ("Laser", "meristem/stem vurma", "beam-hit + kill + collateral", "center/coverage px", "Ölçülemez"),
            ("Thermal/electric", "doğru temas ve enerji", "contact-hit + kill", "action point px", "Ölçülemez"),
            ("Intra-row hoe", "crop etrafından geçme", "crop injury + lateral mm", "crop mask", "Ölçülemez"),
        ),
        (0.13, 0.20, 0.28, 0.22, 0.17),
        font_size=19,
        row_height=118,
    )
    pages.append(method_page)

    gate_page = base_page("Provisional engineering gates", "Aktüatör/GSD sabitlenince sayıların yeniden freeze edilmesi zorunlu.")
    draw_table(
        gate_page,
        (55, 195, 1865, 800),
        ("Faz", "Safety", "Etkinlik", "Şimdi"),
        (
            ("Offline spot", "action crop-hit ≤%0,5; r10 raporlu", "safe hit ≥%90; point precision ≥%95", "Geçmedi"),
            ("Controlled", "deposition + crop injury", "effective spray ≥%90", "Ölçülmedi"),
            ("Field", "crop injury confidence bound", "kill/residual weed/throughput", "Ölçülmedi"),
            ("Mechanical/laser", "tool/beam collision", "p95 mm < actuator tolerance", "Kalibrasyon yok"),
        ),
        (0.15, 0.31, 0.35, 0.19),
        font_size=21,
        row_height=116,
    )
    card(ImageDraw.Draw(gate_page), (70, 840, 1850, 950), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(ImageDraw.Draw(gate_page), (100, 870), "Not:", 24, bold=True, fill=ORANGE)
    add_text(ImageDraw.Draw(gate_page), (180, 868), "Bunlar evrensel standart değil; ilk saha pilotu için maliyet-temelli proje gate'leridir. Kimyasal kullanım mevzuatı/agronomi ayrıca doğrulanır.", 24, width=104)
    pages.append(gate_page)

    source_names = ["PhenoBench", "ACRE", "ROSE", "WE3DS", "WeedsGalore"]
    page = base_page("Global model • semantic validation", "İyi segmentasyon ile iyi müdahale aynı şey değildir.")
    draw_table(
        page,
        (65, 195, 1855, 820),
        ("Dataset", "N", "mIoU", "Crop IoU", "Weed IoU", "Weed recall", "<14px"),
        [
            (
                name,
                str(rows[name]["images"]),
                dec(rows[name]["miou"]),
                dec(rows[name]["crop_iou"]),
                dec(rows[name]["weed_iou"]),
                pct(rows[name]["weed_recall"]),
                pct(rows[name]["subpatch_fraction"]),
            )
            for name in source_names
        ],
        (0.19, 0.08, 0.13, 0.15, 0.15, 0.15, 0.15),
        font_size=21,
        row_height=98,
        align_right=(1, 2, 3, 4, 5, 6),
    )
    bullet_list(page, ("ROSE yüksek; yakın robot ve büyük bitki footprint'i ana avantaj.", "WE3DS/PhenoBench weed hatasında apparent-size ve class imbalance öne çıkıyor.", "Dataset macro/target-weighted skor kullanılmalı; tek büyük dataset mikro ortalamayı domine etmemeli."), (90, 850), width=112, size=22, line_gap=6)
    pages.append(page)

    page = base_page("Global model • müdahale görünümü", "Semantic kapasite ile frozen safe-action arasındaki recall kaybı.")
    draw_table(
        page,
        (55, 195, 1865, 830),
        ("Dataset", "Semantic hit", "Semantic cov50", "Center ≤1R", "Safe hit", "Safe point precision", "Crop point hit"),
        [
            (
                name,
                pct(rows[name]["sem_hit"]),
                pct(rows[name]["sem_cov50"]),
                pct(rows[name]["sem_center_r1"]),
                pct(rows[name]["safe_hit"]),
                pct(rows[name]["safe_point_precision"]),
                pct(rows[name]["safe_point_crop"]),
            )
            for name in source_names
        ],
        (0.18, 0.14, 0.15, 0.14, 0.13, 0.15, 0.11),
        font_size=18,
        row_height=100,
        align_right=(1, 2, 3, 4, 5, 6),
    )
    card(ImageDraw.Draw(page), (70, 865, 1850, 955), fill=LIGHT_RED, outline=RED)
    add_text(ImageDraw.Draw(page), (100, 889), "Ana teşhis: model bazı weed'leri görse de source-calibrated threshold/crop guard büyük bölümünde aksiyona izin vermiyor.", 26, bold=True, fill=RED, width=108)
    pages.append(page)

    page = base_page("Spot-spray proxy'leri • seen validation", "Aksiyon recall, doğruluk ve crop footprint riski birlikte okunur.")
    draw_table(
        page,
        (45, 190, 1875, 840),
        ("Dataset", "Safe hit", "Point precision", "Crop point", "Crop collision r10", "Safe pixel recall", "Action points"),
        [
            (
                name,
                pct(rows[name]["safe_hit"]),
                pct(rows[name]["safe_point_precision"]),
                pct(rows[name]["safe_point_crop"]),
                pct(rows[name]["safe_crop_collision_r10"]),
                pct(rows[name]["safe_pixel_recall"]),
                integer(rows[name]["safe_action_points"]),
            )
            for name in source_names
        ],
        (0.18, 0.12, 0.16, 0.12, 0.17, 0.14, 0.11),
        font_size=18,
        row_height=102,
        align_right=(1, 2, 3, 4, 5, 6),
    )
    card(ImageDraw.Draw(page), (70, 875, 1850, 955), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(ImageDraw.Draw(page), (100, 895), "r10 yalnız 10-piksel image-plane sensitivity'dir; nozzle çapı/GSD bilinmeden fiziksel crop deposition yüzdesi değildir.", 24, bold=True, fill=ORANGE, width=110)
    pages.append(page)

    page = base_page("Apparent-size analizi", "<14 px bir backbone patch'inden küçüktür; fiziksel plant instance anlamına gelmez.")
    draw_table(
        page,
        (70, 195, 1200, 915),
        (
            "Dataset",
            "<14px pay",
            "Tüm sem. hit",
            "<14px sem. hit",
            "<14px safe hit",
        ),
        [
            (
                name,
                pct(rows[name]["subpatch_fraction"]),
                pct(rows[name]["sem_hit"]),
                pct(rows[name]["sem_subpatch_hit"]),
                pct(rows[name]["safe_subpatch_hit"]),
            )
            for name in source_names + ["WeedMap UAV", "RiceSEG calibration"]
        ],
        (0.27, 0.18, 0.18, 0.19, 0.18),
        font_size=18,
        row_height=88,
        align_right=(1, 2, 3),
    )
    card(ImageDraw.Draw(page), (1240, 195, 1850, 915), fill=LIGHT_BLUE, outline=BLUE)
    add_text(ImageDraw.Draw(page), (1280, 235), "Nasıl okunur?", 29, bold=True, fill=BLUE)
    bullet_list(page, ("Pay yüksek + hit düşük: optik/GSD/model-scale önceliği.", "Pay düşük + weed IoU düşük: sınıf/domain/etiket sorunu daha olası.", "Safe hit semantic hit'ten çok düşük: safety calibration/policy darboğazı.", "True instance olmadığı için yaprak parçalanması küçük bin'i şişirebilir."), (1280, 310), width=34, size=23)
    pages.append(page)

    transfer_names = ["Sorghum test", "SugarBeets robot", "WeedMap UAV"]
    page = base_page("Global model • labeled external panel", "Aynı-dataset held-out ile unseen dataset transferi ayrı roller.")
    draw_table(
        page,
        (60, 195, 1860, 680),
        ("Set", "Rol", "N", "mIoU", "Crop IoU", "Weed IoU", "Semantic hit", "Safe hit"),
        [
            (
                name,
                "same-source test" if name == "Sorghum test" else "unseen dataset",
                str(rows[name]["images"]),
                dec(rows[name]["miou"]),
                dec(rows[name]["crop_iou"]),
                dec(rows[name]["weed_iou"]),
                pct(rows[name]["sem_hit"]),
                pct(rows[name]["safe_hit"]),
            )
            for name in transfer_names
        ],
        (0.16, 0.16, 0.07, 0.11, 0.12, 0.12, 0.14, 0.12),
        font_size=19,
        row_height=112,
        align_right=(2, 3, 4, 5, 6, 7),
    )
    bullet_list(page, ("Sorghum yüksek skor, yeni-dataset genellemesi değildir; aynı kaynağın ayrık testidir.", "SugarBeets robot yakın hedef kullanımına daha benzer bir external transferdir.", "WeedMap 10 m UAV; GSD ve viewpoint shift küçük weed teşhisini sertleştirir."), (90, 740), width=110, size=24)
    pages.append(page)

    rice_names = ["RiceSEG calibration", "Early-rice transfer"]
    page = base_page("Rice specialist", "Held-out crop başarısı weed/action başarısıyla birlikte okunur.")
    draw_table(
        page,
        (60, 195, 1860, 560),
        ("Set", "N", "mIoU", "Crop IoU", "Weed IoU", "Semantic hit", "Safe hit", "Safe point precision"),
        [
            (
                name,
                str(rows[name]["images"]),
                dec(rows[name]["miou"]),
                dec(rows[name]["crop_iou"]),
                dec(rows[name]["weed_iou"]),
                pct(rows[name]["sem_hit"]),
                pct(rows[name]["safe_hit"]),
                pct(rows[name]["safe_point_precision"]),
            )
            for name in rice_names
        ],
        (0.20, 0.07, 0.10, 0.13, 0.13, 0.14, 0.11, 0.12),
        font_size=19,
        row_height=115,
        align_right=(1, 2, 3, 4, 5, 6, 7),
    )
    card(ImageDraw.Draw(page), (70, 620, 1850, 930), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(ImageDraw.Draw(page), (110, 655), "Neden safe-action çok düşük?", 29, bold=True, fill=ORANGE)
    bullet_list(page, ("Rice crop ID için source validation safety calibration paneli yok; unknown fallback threshold çok yüksek.", "Bu, crop'u yanlış öldürmeyi azaltırken çoğu weed'i kaçıran no-spray davranışıdır.", "Doğru çözüm testte threshold düşürmek değil; ayrı rice safety-calibration field split'i toplamaktır."), (115, 720), width=104, size=24, line_gap=8)
    pages.append(page)

    page = base_page("Spot-spray proxy'leri • external ve rice", "No-action paydası precision'ı ölçülemez yapar; bu başarı değildir.")
    external_names = ["Sorghum test", "SugarBeets robot", "WeedMap UAV", "RiceSEG calibration", "Early-rice transfer"]
    draw_table(
        page,
        (45, 190, 1875, 840),
        ("Set", "Safe hit", "Point precision", "Crop point", "Crop collision r10", "Safe pixel recall", "Action points"),
        [
            (
                name,
                pct(rows[name]["safe_hit"]),
                pct(rows[name]["safe_point_precision"]),
                pct(rows[name]["safe_point_crop"]),
                pct(rows[name]["safe_crop_collision_r10"]),
                pct(rows[name]["safe_pixel_recall"]),
                integer(rows[name]["safe_action_points"]),
            )
            for name in external_names
        ],
        (0.20, 0.12, 0.16, 0.11, 0.17, 0.13, 0.11),
        font_size=18,
        row_height=102,
        align_right=(1, 2, 3, 4, 5, 6),
    )
    card(ImageDraw.Draw(page), (70, 875, 1850, 955), fill=LIGHT_RED, outline=RED)
    add_text(ImageDraw.Draw(page), (100, 895), "External sette threshold düşürülmedi. Recall düşükse doğru next step test retune değil, ayrı method/crop calibration split'idir.", 24, bold=True, fill=RED, width=110)
    pages.append(page)

    pages.append(
        text_page(
            "Spot spray yorumu",
            "Mevcut etiketlerle en iyi ölçülebilen removal yolu.",
            (
                ("Primary saha metric", (
                    "Weed üstüne ulaşan gerçek deposition/effective spray rate; yalnız prediction değil.",
                    "Crop deposition/injury, missed weed, sprayed area/chemical saving ve throughput birlikte.",
                    "Nozzle footprint, vehicle speed, perception→actuation latency, wind ve pressure dahil.",
                )),
                ("Offline proxy", (
                    "Safe component any-hit: en az bir izinli nokta var mı?",
                    "Safe action-point precision + crop-hit ve 0/5/10/20px footprint collision.",
                    "Coverage@90 yalnız weed konturunu rasterlayan sistem için önemli.",
                )),
            ),
        )
    )

    pages.append(
        text_page(
            "Mekanik sökme / gripper yorumu",
            "Canopy center, root/crown merkezi değildir.",
            (
                ("Gereken", (
                    "Root/crown point veya plant emergence point; occlusion/visibility etiketi.",
                    "Camera→tool extrinsic, ground plane/depth, mm cinsinden P50/P95 hata ve tool footprint.",
                    "Crop clearance/collision, successful grasp/removal, soil resistance ve cycle time.",
                )),
                ("Bugünkü proxy'nin anlamı", (
                    "Semantic component centroid hatası yalnız modelin canopy bölgesini kabaca merkezleyip merkezlemediğini gösterir.",
                    "Temas eden bitkiler tek component, ayrık yapraklar birkaç component olabilir.",
                    "Bu nedenle center≤1R iyi görünse bile mekanik-ready sonucu çıkarılamaz.",
                )),
            ),
        )
    )

    page = base_page("Center ve yüksek-coverage proxy'leri", "Mekanik/lazer için yalnız tanısal; root/meristem veya mm gate'i değil.")
    center_names = source_names + ["Sorghum test", "SugarBeets robot", "WeedMap UAV", "RiceSEG calibration", "Early-rice transfer"]
    draw_table(
        page,
        (55, 185, 1865, 955),
        ("Set", "Semantic hit", "Center ≤10px", "Center ≤1 eq-radius", "Coverage≥50", "Coverage≥90"),
        [
            (
                name,
                pct(rows[name]["sem_hit"]),
                pct(rows[name]["sem_center_px10"]),
                pct(rows[name]["sem_center_r1"]),
                pct(rows[name]["sem_cov50"]),
                pct(rows[name]["sem_cov90"]),
            )
            for name in center_names
        ],
        (0.24, 0.15, 0.16, 0.18, 0.14, 0.13),
        font_size=18,
        row_height=68,
        align_right=(1, 2, 3, 4, 5),
    )
    pages.append(page)

    pages.append(
        text_page(
            "Lazer, termal ve elektrik yorumu",
            "Tüm maskeyi tamamlamak yerine biyolojik hedefi doğru seçmek gerekir.",
            (
                ("Lazer", (
                    "Çoğu tek-shot yaklaşımda apical meristem veya stem keypoint, beam çapı içinde vurulmalıdır.",
                    "Kill probability enerji/dwell ve büyüme evresine bağlıdır; mask IoU bunu ölçmez.",
                    "Yalnız kontur-raster tedavide coverage@90 doğrudan önem kazanır.",
                )),
                ("Termal / elektrik", (
                    "Temas noktası, yüzey normal/depth, tool clearance ve enerji/süre primary'dir.",
                    "Action-point precision yalnız ilk 2B filtre olabilir.",
                )),
                ("Intra-row hoe", (
                    "Weed center'dan önce crop row/center ve crop exclusion geometry gerekir.",
                )),
            ),
        )
    )

    causes_page = base_page("Dataset root-cause özeti", "Her satırda en olası ilk hipotez; nedensel A/B olmayan yerde kesinlik iddiası yok.")
    draw_table(
        causes_page,
        (45, 185, 1875, 955),
        ("Dataset", "En olası ilk neden", "İkincil sınır"),
        (
            ("ROSE", "yakın robot + büyük plant footprint", "aynı saha coğrafyası"),
            ("Sorghum", "same-source ve net büyük bitki", "n=25 test"),
            ("PhenoBench", "weed küçük/az; crop row kolay", "UAV/class imbalance"),
            ("ACRE", "ışık/ürün/session çeşitliliği", "mixed morphology"),
            ("WE3DS", "çok crop/date + vegetation benzerliği", "küçük/temas eden weed"),
            ("WeedsGalore", "104 train + sensor distribution", "crop az öğrenildi"),
            ("WeedMap", "10 m GSD + UAV/sensor shift", "RGB-only input"),
            ("Rice", "sparse weed/duckweed + water/stage", "safety calibration yok"),
        ),
        (0.15, 0.49, 0.36),
        font_size=19,
        row_height=85,
    )
    pages.append(causes_page)

    pages.append(
        text_page(
            "Küçük weed: donanım hesabı",
            "Minimum öldürülebilir plant boyutundan sensör gereksinimine.",
            (
                ("Boyut hedefi", (
                    "Hedef minimum weed çapını D_min mm tanımla.",
                    "İlk tasarım: D_min sensörde ≥28 px (2 patch); tercihen ≥56 px (4 patch).",
                    "GSD üst sınırı: D_min_mm / desired_pixels.",
                )),
                ("Optik yaklaşım", (
                    "GSD ≈ sensor_width_mm × camera_height_mm / (focal_length_mm × image_width_px).",
                    "Daha alçak kamera/uzun focal/yüksek gerçek sensör çözünürlüğü footprint ve depth-of-field trade-off'u yaratır.",
                )),
                ("Hareket", (
                    "blur_px ≈ speed_mm_s × exposure_s / GSD_mm_px; titreşim ayrıca ölçülür.",
                    "Kısa exposure için kontrollü ışık/strobe ve global shutter tercih edilir.",
                )),
            ),
        )
    )

    pages.append(
        text_page(
            "SAHI / çözünürlük gerçeği",
            "Yazılım ve donanım çözünürlüğü aynı şey değildir.",
            (
                ("Zaten açık", (
                    "Eval görüntüyü 512'ye downsample etmez; native resolution kullanır.",
                    ">4MP için 1024×1024 overlap tile + Hann blending uygulanır; SAHI-benzeri ölçek koruma vardır.",
                )),
                ("Test edildi", (
                    "1.0× / 1.5× / 2.0× inference-scale A/B; output aynı native grid'e geri örneklenir.",
                    "Primary: <14px semantic/safe hit; guard: crop point hit, mIoU, VRAM ve latency.",
                    "Interpolasyon detay yaratmadığı için yalnız ölçülmüş kazanç varsa tutulur.",
                )),
                ("Daha olası kalıcı kazanım", (
                    "Optik GSD/fokus/exposure + small-object oversampling + larger/multi-scale train crop.",
                )),
            ),
        )
    )

    page = base_page("Inference-scale A/B sonucu", "Early-rice 224 kare; aynı specialist, aynı native output grid'i, optik bilgi eklenmez.")
    baseline_scale, scale_150, scale_200 = resolution_rows
    draw_table(
        page,
        (55, 195, 1865, 650),
        ("Scale", "mIoU", "Weed IoU", "<14px semantic hit", "Safe hit", "Crop point hit", "Perception ms/img"),
        [
            (
                str(metric["label"]),
                dec(metric["miou"]),
                dec(metric["weed_iou"]),
                pct(metric["semantic_subpatch_hit"]),
                pct(metric["safe_hit"]),
                pct(metric["safe_point_crop"]),
                dec(metric["perception_ms"], 1),
            )
            for metric in resolution_rows
        ],
        (0.18, 0.12, 0.13, 0.19, 0.13, 0.13, 0.12),
        font_size=20,
        row_height=105,
        align_right=(1, 2, 3, 4, 5, 6),
    )
    card(ImageDraw.Draw(page), (70, 710, 1850, 940), fill=LIGHT_RED, outline=RED)
    add_text(ImageDraw.Draw(page), (110, 745), "KARAR • SOFTWARE UPSCALE KABUL EDİLMEDİ", 27, bold=True, fill=RED)
    bullet_list(
        page,
        (
            f"2× küçük-hit: {pct(baseline_scale['semantic_subpatch_hit'])} → {pct(scale_200['semantic_subpatch_hit'])}; weed IoU: {pct(baseline_scale['weed_iou'])} → {pct(scale_200['weed_iou'])}.",
            f"Ancak crop-point: {pct(baseline_scale['safe_point_crop'])} → {pct(scale_200['safe_point_crop'])}; perception: {dec(baseline_scale['perception_ms'], 1)} → {dec(scale_200['perception_ms'], 1)} ms.",
            "Ölçek darboğazı gerçek; güvenli kalıcı yön optik/GSD + multi-scale training. Tek development dataset sonucu field-ready model seçmez.",
        ),
        (115, 800),
        width=108,
        size=21,
        line_gap=2,
    )
    pages.append(page)

    pages.append(
        text_page(
            "Saha veri toplama tasarımı",
            "Validation gerçek robotun beklediği çeşitliliği taşımalı.",
            (
                ("Strata", (
                    "3–4 bağımsız tarla; ürün/weed evresi; minimum weed mm; dry/medium/wet soil; tillage/clod/residue.",
                    "Sabah/öğle/akşam, güneş/diffuse/lokal gölge; robot ışığı açık/kapalı; rüzgâr/hız/exposure.",
                    "Lens/focus/height/GSD metadata ve kamera calibration ID.",
                )),
                ("Split", (
                    "Train daha geniş; validation target-weighted ve çeşitli; untouched test field/session-disjoint.",
                    "Val/test gerçekçi ve benzer olabilir, ama aynı frame/session/tarla train'e sızmaz.",
                    "Removal outcome için aynı plant'e treatment + post-treatment kill/removal etiketi bağlanır.",
                )),
            ),
        )
    )

    pages.append(
        text_page(
            "Sentetik veri kararı",
            "Asset kalitesi ile model katkısı ayrı gate'lerdir.",
            (
                ("Kabul edilen", (
                    "Dryland V3 ve paddy R5: asset ve gerçek-domain model gate'i geçti; current global control içinde.",
                )),
                ("Kaliteli ama reddedilen", (
                    "Soy morphology/stress, sensor-motion ve field-robustness paketleri asset gate'lerini geçti.",
                    "Hedef domain kazanımı olsa da CWFID/Rice/WeedMap veya macro non-inferiority kaybedildi; global mix'e eklenmedi.",
                )),
                ("Sonuç", (
                    "Yeni yüksek-quality asset üretmek tek başına doğru next step değil.",
                    "Yeni üretim yalnız gerçek field audit'in gösterdiği tek under-covered faktör ve önceden dondurulmuş A/B gate ile açılır.",
                )),
            ),
        )
    )

    seen_good = visual_root / "CONTACT_SHEETS/01_03_SEEN_ROSE_BEST.jpg"
    seen_bad = visual_root / "CONTACT_SHEETS/01_04_SEEN_WE3DS_WORST.jpg"
    for title, subtitle, path in (
        ("Görsel • güçlü seen örnekleri", "ROSE: yakın robot ölçeği; full-sheet legend ve full-split metric görselin içinde.", seen_good),
        ("Görsel • zor seen örnekleri", "WE3DS: best/worst görseller teşhistir; full-split skor yerine okunmaz.", seen_bad),
    ):
        if path.is_file():
            page = base_page(title, subtitle)
            card(ImageDraw.Draw(page), (55, 180, 1865, 985))
            paste_contain(page, path, (70, 195, 1850, 970))
            pages.append(page)

    for title, subtitle, filename in (
        ("Görsel • SugarBeets robot transferi", "Yeni dataset/session; hedef kullanım perspektifine yakın labeled transfer.", "03_01_SUGARBEETS_HOLDOUT_WORST.jpg"),
        ("Görsel • WeedMap UAV transferi", "10 m UAV apparent-size ve sensor/viewpoint shift.", "03_03_WEEDMAP_UAV_WORST.jpg"),
        ("Görsel • sentetik held-out stress", "Sentetik test, render-domain tutarlılığıdır; gerçek saha accuracy'si değildir.", "04_02_V11_TEST_WORST.jpg"),
    ):
        path = visual_root / "CONTACT_SHEETS" / filename
        if path.is_file():
            page = base_page(title, subtitle)
            card(ImageDraw.Draw(page), (55, 180, 1865, 985))
            paste_contain(page, path, (70, 195, 1850, 970))
            pages.append(page)

    for title, subtitle, filename in (
        (
            "Görsel • RiceSEG training-held-out calibration • güçlü",
            "Guangdong + Tokyo; training overlap 0/604; prior selector kullandı, final test değil.",
            "best_contact_sheet.jpg",
        ),
        (
            "Görsel • RiceSEG training-held-out calibration • zor",
            "Bu koşuda retune yok; panel geçmiş specialist seçiminde kullanıldı.",
            "worst_contact_sheet.jpg",
        ),
    ):
        path = intervention_visual_root / "riceseg_heldout" / filename
        if path.is_file():
            page = base_page(title, subtitle)
            card(ImageDraw.Draw(page), (55, 180, 1865, 985))
            paste_contain(page, path, (70, 195, 1850, 970))
            pages.append(page)

    pages.append(
        text_page(
            "RiceSEG split erratum",
            "Yeni rapor eski rol etiketini performans kanıtı olarak kullanmaz.",
            (
                ("Bulgu", (
                    "Country-transfer external satırları: 1.254 görüntü; specialist training image-path overlap 1.254/1.254.",
                    "Dataset/sample prefix farklı olduğu için önceki ID-based kontrol bunu kaçırdı; image_path/mask_path karşılaştırması gerçeği gösterdi.",
                )),
                ("Düzeltme", (
                    "Yeni RiceSEG ana paneli: Guangdong + Tokyo 604 training-held-out görüntü; path overlap 0/604.",
                    "Panel geçmiş specialist seçiminde kullanıldı; development/calibration kanıtıdır, untouched final test değildir.",
                    "Eski 1.254-kare specialist gallery yalnız train-seen diagnostic diye okunmalıdır.",
                )),
                ("Ders", (
                    "Alternatif split manifestleri karşılaştırılırken sample_id değil canonical content path/hash kullanılmalı.",
                )),
            ),
        )
    )

    pages.append(
        text_page(
            "Sınırlamalar ve dürüst yorum",
            "Bu rapor neyi kanıtlamaz?",
            (
                ("Etiket", (
                    "Connected component true plant instance değildir; touching/split leaf sorunu vardır.",
                    "Canopy centroid root/crown/meristem değildir.",
                )),
                ("Fizik", (
                    "px footprint gerçek nozzle deposition/tool/beam geometry değildir.",
                    "Offline görüntü latency, wind, terrain, depth, kill/removal outcome'u içermez.",
                )),
                ("İstatistik", (
                    "Bazı dış paneller küçük veya development-calibration rolündedir; final untouched field test değildir.",
                    "Dataset macro ve hedef-ağırlıklı ölçü, mikro piksel toplamıyla birlikte raporlanmalıdır.",
                )),
            ),
        )
    )

    pages.append(
        text_page(
            "Öncelikli uygulama planı",
            "Occam: en küçük deney, en kritik belirsizliği çözsün.",
            (
                ("P0 • fizik ve veri", (
                    "Actuator adayı + footprint + target minimum weed mm + speed tanımla.",
                    "Rig intrinsics/extrinsics/GSD/latency; 3–4 bağımsız field mini-test.",
                )),
                ("P1 • basit model deneyi", (
                    "Inference-scale A/B tamamlandı ve reddedildi; sırada small-object oversampling/larger crop/multi-scale train A/B.",
                    "Aynı compute ve seed guard; crop false-action kötüleşirse fail-closed.",
                    "Safety threshold'u ayrılmış method/crop calibration split'inde seç.",
                )),
                ("P2 • yalnız yöntem gerektirirse", (
                    "Mechanical: root/crown + depth. Laser: meristem/stem + beam outcome.",
                    "Sonra end-to-end treatment/kill/removal field metric'i primary yap.",
                )),
            ),
        )
    )

    sources_page = base_page("Kaynaklar ve provenance", "Literatür değerleri bağlamdır; bizim saha gate'imiz değildir.")
    bullet_list(
        sources_page,
        (
            "Laser apical meristem localization — DOI 10.3390/agronomy14092121",
            "Mechanical crop positioning — DOI 10.3965/j.ijabe.20150806.1932",
            "WeedMap, GSD ve tiled processing — arXiv:1808.00100",
            "High-resolution micro-jet sprayer — ScienceDirect PII S1537511023000375",
            "Field smart sprayer evaluation — ScienceDirect PII S2666154324003685",
            "Remote sensing sprayed-area analysis — arXiv:2410.22554",
        ),
        (90, 220),
        width=110,
        size=24,
    )
    card(ImageDraw.Draw(sources_page), (70, 715, 1850, 940), fill=LIGHT_GREEN, outline=GREEN)
    add_text(ImageDraw.Draw(sources_page), (105, 750), "Reproducibility", 27, bold=True, fill=GREEN)
    add_text(ImageDraw.Draw(sources_page), (105, 805), "Protocol: intervention_semantic_component_proxy_v1 • native inference • source-frozen safety • external retune yok. Her JSON checkpoint, manifest ve seçili mask-tree SHA-256 değerlerini içerir.", 24, width=110)
    pages.append(sources_page)

    finalize_pages(pages, "Crop Müdahale • Ayrıntılı Teknik Rapor")
    return pages


def readable_cover(source: Mapping[str, Any]) -> Image.Image:
    """Cover for the reader-first report.

    The old detailed PDF opened with the same dense summary used by the short
    deck.  This cover states the decision and the reading rule before exposing
    any implementation detail.
    """

    page = Image.new("RGB", (W, H), DARK_GREEN)
    draw = ImageDraw.Draw(page)
    card(draw, (70, 60, 1850, 1018), fill=BG, outline=BG, radius=38)
    add_text(draw, (130, 118), "Crop segmentasyonu", 66, bold=True, fill=DARK_GREEN)
    add_text(draw, (130, 202), "Anlaşılır detaylı sonuç raporu", 49, bold=True, fill=GREEN)
    add_text(draw, (132, 274), "5 Ağustos 2026 • bir sayfa = bir ana fikir", 25, fill=MUTED)
    card(draw, (125, 350, 1795, 555), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (170, 386), "SONUÇ", 24, bold=True, fill=ORANGE)
    add_text(
        draw,
        (170, 432),
        "Model bitkileri anlamlı ölçüde görüyor; fakat mevcut güvenli aksiyon politikası sahada weed öldürmek için henüz yeterli değil.",
        35,
        bold=True,
        width=79,
    )
    metric_card(
        page,
        (125, 620, 625, 850),
        pct(source["sem_hit"]),
        "Weed'i en az bir kez görme",
        "Semantic component proxy; gerçek instance değildir.",
        accent=BLUE,
    )
    metric_card(
        page,
        (655, 620, 1155, 850),
        pct(source["safe_hit"]),
        "Aksiyona izin verilen weed",
        "Mevcut dondurulmuş policy ile.",
        accent=RED,
    )
    metric_card(
        page,
        (1185, 620, 1685, 850),
        pct(source["safe_subpatch_hit"]),
        "Küçük weed safe hit",
        "Görüntüde eşdeğer çapı 14 px'ten küçük.",
        accent=PURPLE,
    )
    add_text(
        draw,
        (130, 915),
        "En kısa yol: optiği düzelt + küçük weed eğitim A/B'si + gerçek spot-spray deposition testi.",
        27,
        bold=True,
        fill=DARK_GREEN,
        width=105,
    )
    return page


def readable_text_page(
    title: str,
    subtitle: str,
    items: Sequence[tuple[str, str, tuple[int, int, int]]],
    *,
    conclusion: str | None = None,
    conclusion_color: tuple[int, int, int] = GREEN,
) -> Image.Image:
    """A spacious page with at most four result cards."""

    page = base_page(title, subtitle)
    draw = ImageDraw.Draw(page)
    count = len(items)
    if count <= 2:
        positions = [(85, 225, 1835, 500), (85, 550, 1835, 825)][:count]
    elif count == 3:
        positions = [
            (85, 215, 1835, 425),
            (85, 455, 1835, 665),
            (85, 695, 1835, 905),
        ]
    else:
        positions = [
            (85, 210, 925, 520),
            (995, 210, 1835, 520),
            (85, 565, 925, 875),
            (995, 565, 1835, 875),
        ][:count]
    for box, (heading, body, accent) in zip(positions, items):
        card(draw, box, fill=WHITE, outline=accent, width=3)
        x1, y1, x2, _ = box
        add_text(draw, (x1 + 30, y1 + 25), heading, 29, bold=True, fill=accent)
        body_width = max(34, int((x2 - x1 - 60) / 14.5))
        add_text(draw, (x1 + 30, y1 + 82), body, 25, width=body_width, spacing=10)
    if conclusion:
        card(draw, (85, 910, 1835, 985), fill=WHITE, outline=conclusion_color, width=3)
        add_text(draw, (115, 929), conclusion, 24, bold=True, fill=conclusion_color, width=112)
    return page


def draw_percent_bar(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    value: float | None,
    *,
    color: tuple[int, int, int],
    background: tuple[int, int, int] = GRAY,
) -> None:
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, radius=max(5, (y2 - y1) // 2), fill=background)
    bounded = 0.0 if value is None else max(0.0, min(1.0, float(value)))
    if bounded > 0:
        fill_x = x1 + max(y2 - y1, int((x2 - x1) * bounded))
        draw.rounded_rectangle(
            (x1, y1, min(x2, fill_x), y2),
            radius=max(5, (y2 - y1) // 2),
            fill=color,
        )


def paired_bar_page(
    title: str,
    subtitle: str,
    rows: Sequence[tuple[str, float | None, float | None]],
    *,
    left_label: str,
    right_label: str,
    left_color: tuple[int, int, int] = BLUE,
    right_color: tuple[int, int, int] = RED,
    note: str,
) -> Image.Image:
    """One chart, two directly comparable quantities per dataset."""

    page = base_page(title, subtitle)
    draw = ImageDraw.Draw(page)
    draw.rounded_rectangle((620, 195, 650, 225), radius=7, fill=left_color)
    add_text(draw, (665, 195), left_label, 22, bold=True)
    draw.rounded_rectangle((1110, 195, 1140, 225), radius=7, fill=right_color)
    add_text(draw, (1155, 195), right_label, 22, bold=True)
    y = 260
    row_gap = 136 if len(rows) <= 5 else 110
    for label, left_value, right_value in rows:
        add_text(draw, (85, y + 8), label, 25, bold=True, width=22)
        draw_percent_bar(draw, (400, y, 1640, y + 34), left_value, color=left_color)
        add_text(draw, (1665, y - 2), pct(left_value), 23, bold=True, fill=left_color)
        draw_percent_bar(draw, (400, y + 52, 1640, y + 86), right_value, color=right_color)
        add_text(draw, (1665, y + 50), pct(right_value), 23, bold=True, fill=right_color)
        y += row_gap
    card(draw, (80, 910, 1840, 982), fill=LIGHT_ORANGE, outline=ORANGE)
    add_text(draw, (110, 929), note, 23, bold=True, fill=DARK_GREEN, width=114)
    return page


def _artifact_panel(
    source_path: Path,
    index: int,
    *,
    profile: str,
) -> Image.Image:
    """Extract one large panel from an existing self-sufficient artifact."""

    with Image.open(source_path) as handle:
        source = handle.convert("RGB")
    if profile == "labeled":
        count, margin, top, bottom = 4, 0.010, 0.368, 0.868
    elif profile == "rice":
        count, margin, top, bottom = 4, 0.000, 0.126, 0.914
    elif profile == "unlabeled":
        count, margin, top, bottom = 3, 0.010, 0.372, 0.878
    else:
        raise ValueError(f"Unknown artifact profile: {profile}")
    if not 0 <= index < count:
        raise IndexError(index)
    usable = 1.0 - 2.0 * margin
    x1 = int(source.width * (margin + usable * index / count))
    x2 = int(source.width * (margin + usable * (index + 1) / count))
    y1 = int(source.height * top)
    y2 = int(source.height * bottom)
    return source.crop((x1, y1, x2, y2))


def _paste_image(
    canvas: Image.Image,
    source: Image.Image,
    box: tuple[int, int, int, int],
    *,
    background: tuple[int, int, int] = WHITE,
) -> None:
    x1, y1, x2, y2 = box
    fitted = ImageOps.contain(
        source.convert("RGB"),
        (x2 - x1, y2 - y1),
        Image.Resampling.LANCZOS,
    )
    frame = Image.new("RGB", (x2 - x1, y2 - y1), background)
    frame.paste(
        fitted,
        ((frame.width - fitted.width) // 2, (frame.height - fitted.height) // 2),
    )
    canvas.paste(frame, (x1, y1))


def example_comparison_page(
    title: str,
    subtitle: str,
    source_path: Path,
    *,
    profile: str,
    left_index: int,
    right_index: int,
    left_label: str,
    right_label: str,
    finding: str,
    metric_line: str,
    accent: tuple[int, int, int],
) -> Image.Image:
    """Show one example only, with two large panels and a plain-language readout."""

    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    page = base_page(title, subtitle)
    draw = ImageDraw.Draw(page)
    left_box = (75, 260, 925, 775)
    right_box = (995, 260, 1845, 775)
    for box, label in ((left_box, left_label), (right_box, right_label)):
        x1, _, x2, _ = box
        card(draw, (x1, 205, x2, 765), fill=WHITE, outline=LINE, radius=18)
        add_text(draw, (x1 + 24, 218), label, 25, bold=True, fill=DARK_GREEN)
    _paste_image(page, _artifact_panel(source_path, left_index, profile=profile), left_box)
    _paste_image(page, _artifact_panel(source_path, right_index, profile=profile), right_box)
    card(draw, (75, 805, 1845, 985), fill=WHITE, outline=accent, width=3)
    add_text(draw, (110, 832), "BU ÖRNEK NE ANLATIYOR?", 23, bold=True, fill=accent)
    add_text(draw, (110, 875), finding, 25, bold=True, width=108)
    add_text(draw, (110, 944), metric_line, 19, fill=MUTED, width=125)
    return page


def simple_metric_cards_page(
    title: str,
    subtitle: str,
    cards: Sequence[tuple[str, str, str, tuple[int, int, int]]],
    *,
    decision: str,
    decision_color: tuple[int, int, int] = RED,
) -> Image.Image:
    page = base_page(title, subtitle)
    draw = ImageDraw.Draw(page)
    count = len(cards)
    card_width = 520 if count == 3 else 390
    gap = 55 if count == 3 else 42
    total_width = count * card_width + (count - 1) * gap
    start_x = (W - total_width) // 2
    for idx, (value, label, note, accent) in enumerate(cards):
        x1 = start_x + idx * (card_width + gap)
        metric_card(page, (x1, 260, x1 + card_width, 650), value, label, note, accent=accent)
    card(draw, (100, 745, 1820, 950), fill=WHITE, outline=decision_color, width=4)
    add_text(draw, (145, 782), "KARAR", 25, bold=True, fill=decision_color)
    add_text(draw, (145, 832), decision, 31, bold=True, fill=decision_color, width=86)
    return page


def metric_flow_page() -> Image.Image:
    page = base_page(
        "Model çıktısı nasıl müdahaleye dönüşüyor?",
        "Dört ayrı adım var; birindeki başarı diğerlerini garanti etmez.",
    )
    draw = ImageDraw.Draw(page)
    steps = (
        ("1", "RGB görüntü", "Kamera ne kadar detay görüyorsa model de en fazla onu görür.", BLUE),
        ("2", "Semantic maske", "Crop, diğer bitki ve arka plan pikselleri ayrılır.", GREEN),
        ("3", "Safety policy", "Belirsiz ve crop'a yakın bölgelerde aksiyon kapatılır.", ORANGE),
        ("4", "Fiziksel işlem", "Nozzle / alet / lazer doğru noktaya ve doğru dozda ulaşır.", RED),
    )
    x_positions = (75, 520, 965, 1410)
    for x, (number, heading, body, accent) in zip(x_positions, steps):
        card(draw, (x, 270, x + 375, 790), fill=WHITE, outline=accent, width=4)
        draw.ellipse((x + 130, 310, x + 245, 425), fill=accent)
        bbox = draw.textbbox((0, 0), number, font=font(52, bold=True))
        add_text(
            draw,
            (x + 187 - (bbox[2] - bbox[0]) // 2, 332),
            number,
            52,
            bold=True,
            fill=WHITE,
        )
        add_text(draw, (x + 28, 470), heading, 29, bold=True, fill=accent, width=20)
        add_text(draw, (x + 28, 545), body, 24, width=25, spacing=10)
        if x != x_positions[-1]:
            draw.polygon(
                [(x + 390, 500), (x + 430, 530), (x + 390, 560)],
                fill=MUTED,
            )
    card(draw, (100, 855, 1820, 955), fill=LIGHT_RED, outline=RED)
    add_text(
        draw,
        (140, 882),
        "Bu rapor 1–3. adımı ölçüyor. Gerçek kill/removal başarısı için 4. adım ayrıca test edilmelidir.",
        27,
        bold=True,
        fill=RED,
        width=100,
    )
    return page


def legend_page() -> Image.Image:
    page = base_page("Renkleri böyle oku", "Renk, sınıfı veya policy kararını gösterir; botanik tür değildir.")
    draw = ImageDraw.Draw(page)
    entries = (
        (GREEN, "YEŞİL", "Hedef mahsul / crop", "Korunacak ürün."),
        (RED, "KIRMIZI", "Diğer bitki / weed", "Hedef mahsul dışındaki bitki."),
        (BLUE, "CAMGÖBEĞİ", "İzinli aksiyon", "Safety policy'nin müdahaleye izin verdiği alan."),
        (ORANGE, "SARI", "Crop teması", "Müdahale crop'a değebilir: tehlikeli hata."),
        (PURPLE, "MOR", "Ignore / no-spray", "Etiket dışı veya policy'nin durdurduğu alan."),
    )
    y = 220
    for color, name, meaning, note in entries:
        draw.rounded_rectangle((100, y, 220, y + 95), radius=18, fill=color)
        add_text(draw, (265, y), name, 27, bold=True, fill=color)
        add_text(draw, (510, y), meaning, 29, bold=True)
        add_text(draw, (510, y + 48), note, 23, fill=MUTED)
        y += 135
    card(draw, (95, 900, 1825, 982), fill=LIGHT_RED, outline=RED, width=3)
    add_text(
        draw,
        (130, 923),
        "Kritik: Kırmızı semantic tahmin, tek başına püskürtme emri değildir. Yalnız camgöbeği alan aksiyon adayıdır.",
        25,
        bold=True,
        fill=RED,
        width=105,
    )
    return page


def intervention_metric_diagram(method: str) -> Image.Image:
    if method == "spray":
        page = base_page("Spot spray için doğru başarı metriği", "Soru: weed'e doz ulaştı mı, crop zarar gördü mü?")
        draw = ImageDraw.Draw(page)
        card(draw, (75, 210, 980, 890), fill=WHITE, outline=BLUE, width=3)
        add_text(draw, (115, 245), "Örnek müdahale geometrisi", 28, bold=True, fill=BLUE)
        draw.ellipse((255, 430, 565, 740), fill=LIGHT_RED, outline=RED, width=6)
        draw.ellipse((585, 345, 825, 585), fill=LIGHT_GREEN, outline=GREEN, width=6)
        draw.ellipse((380, 540, 440, 600), fill=BLUE, outline=DARK_GREEN, width=4)
        draw.ellipse((325, 485, 495, 655), outline=BLUE, width=7)
        add_text(draw, (245, 760), "weed", 27, bold=True, fill=RED)
        add_text(draw, (650, 610), "crop", 27, bold=True, fill=GREEN)
        add_text(draw, (250, 355), "aksiyon noktası + nozzle footprint", 22, bold=True, fill=BLUE)
        cards = (
            ("1 • Etkinlik", "Weed component hit ve gerçek deposition / kill oranı.", BLUE),
            ("2 • Doğruluk", "Action point'in gerçekten weed üzerinde olma oranı.", GREEN),
            ("3 • Güvenlik", "Nozzle footprint'in crop'a değme ve crop injury oranı.", RED),
        )
        y = 240
        for heading, body, accent in cards:
            card(draw, (1050, y, 1840, y + 190), fill=WHITE, outline=accent, width=3)
            add_text(draw, (1085, y + 25), heading, 27, bold=True, fill=accent)
            add_text(draw, (1085, y + 75), body, 25, width=46)
            y += 225
        add_text(draw, (1080, 930), "Bugün ölçülenler proxy; deposition ve kill henüz ölçülmedi.", 23, bold=True, fill=RED, width=48)
        return page
    if method == "mechanical":
        page = base_page("Mekanik sökme için doğru başarı metriği", "Canopy merkezi yetmez; kök/crown ve alet geometrisi gerekir.")
        draw = ImageDraw.Draw(page)
        card(draw, (85, 220, 925, 890), fill=WHITE, outline=GREEN, width=3)
        draw.line((505, 570, 505, 790), fill=(111, 74, 42), width=18)
        draw.ellipse((320, 350, 505, 615), fill=LIGHT_GREEN, outline=GREEN, width=7)
        draw.ellipse((505, 350, 690, 615), fill=LIGHT_GREEN, outline=GREEN, width=7)
        draw.ellipse((470, 545, 540, 615), fill=RED)
        draw.line((610, 305, 610, 580), fill=BLUE, width=7)
        draw.polygon([(590, 565), (630, 565), (610, 610)], fill=BLUE)
        add_text(draw, (285, 275), "canopy merkezi", 25, bold=True, fill=BLUE)
        add_text(draw, (430, 625), "gerçek hedef: crown/root", 25, bold=True, fill=RED)
        card(draw, (1000, 235, 1830, 500), fill=LIGHT_GREEN, outline=GREEN)
        add_text(draw, (1040, 270), "Birincil saha metriği", 28, bold=True, fill=GREEN)
        add_text(draw, (1040, 330), "Crown'a göre mm P50/P95 hata + crop clearance + başarılı sökme oranı", 30, bold=True, width=44)
        card(draw, (1000, 545, 1830, 810), fill=LIGHT_RED, outline=RED)
        add_text(draw, (1040, 580), "Bugünkü durum", 28, bold=True, fill=RED)
        add_text(draw, (1040, 640), "Yalnız semantic canopy-center proxy var. Root/crown etiketi, depth ve kamera–alet kalibrasyonu yok.", 29, bold=True, width=44)
        add_text(draw, (1010, 875), "SONUÇ • Mekanik saha başarısı şu anda ölçülemez.", 27, bold=True, fill=RED)
        return page
    if method == "laser":
        page = base_page("Lazer için doğru başarı metriği", "Çoğu tasarımda asıl hedef tüm maske değil, meristem/stem noktasıdır.")
        draw = ImageDraw.Draw(page)
        card(draw, (85, 220, 925, 890), fill=WHITE, outline=PURPLE, width=3)
        draw.ellipse((290, 405, 520, 675), fill=LIGHT_GREEN, outline=GREEN, width=7)
        draw.ellipse((500, 405, 730, 675), fill=LIGHT_GREEN, outline=GREEN, width=7)
        draw.ellipse((470, 515, 550, 595), fill=RED)
        draw.line((510, 275, 510, 515), fill=PURPLE, width=10)
        draw.polygon([(490, 495), (530, 495), (510, 535)], fill=PURPLE)
        add_text(draw, (315, 300), "beam", 27, bold=True, fill=PURPLE)
        add_text(draw, (385, 700), "meristem / stem hedefi", 26, bold=True, fill=RED)
        card(draw, (1000, 235, 1830, 500), fill=LIGHT_BLUE, outline=BLUE)
        add_text(draw, (1040, 270), "Birincil saha metriği", 28, bold=True, fill=BLUE)
        add_text(draw, (1040, 330), "Meristem hit + mm hata + beam/dwell/energy + crop collateral + kill oranı", 30, bold=True, width=43)
        card(draw, (1000, 545, 1830, 810), fill=LIGHT_RED, outline=RED)
        add_text(draw, (1040, 580), "Bugünkü durum", 28, bold=True, fill=RED)
        add_text(draw, (1040, 640), "Maske ve canopy-center proxy var; meristem/stem etiketi ve lazer sonucu yok.", 29, bold=True, width=43)
        add_text(draw, (1010, 875), "SONUÇ • Lazer saha başarısı şu anda ölçülemez.", 27, bold=True, fill=RED)
        return page
    raise ValueError(method)


def readable_exact_table_page(
    title: str,
    subtitle: str,
    names: Sequence[str],
    rows: Mapping[str, Mapping[str, Any]],
    *,
    mode: str,
) -> Image.Image:
    page = base_page(title, subtitle)
    if mode == "mask":
        headers = ("Dataset", "N", "mIoU", "Crop IoU", "Weed IoU", "Semantic hit", "<14px payı")
        body = [
            (
                name,
                str(rows[name]["images"]),
                dec(rows[name]["miou"]),
                dec(rows[name]["crop_iou"]),
                dec(rows[name]["weed_iou"]),
                pct(rows[name]["sem_hit"]),
                pct(rows[name]["subpatch_fraction"]),
            )
            for name in names
        ]
        fractions = (0.24, 0.08, 0.12, 0.14, 0.14, 0.15, 0.13)
    elif mode == "action":
        headers = ("Dataset", "Safe hit", "<14px safe hit", "Point precision", "Crop point hit", "r=10 crop collision")
        body = [
            (
                name,
                pct(rows[name]["safe_hit"]),
                pct(rows[name]["safe_subpatch_hit"]),
                pct(rows[name]["safe_point_precision"]),
                pct(rows[name]["safe_point_crop"]),
                pct(rows[name]["safe_crop_collision_r10"]),
            )
            for name in names
        ]
        fractions = (0.25, 0.14, 0.17, 0.16, 0.14, 0.14)
    else:
        raise ValueError(mode)
    draw_table(
        page,
        (70, 245, 1850, 800),
        headers,
        body,
        fractions,
        font_size=21,
        row_height=92,
        align_right=tuple(range(1, len(headers))),
    )
    draw = ImageDraw.Draw(page)
    card(draw, (70, 850, 1850, 965), fill=LIGHT_ORANGE, outline=ORANGE)
    note = (
        "Semantic connected component = gerçek plant instance değildir. Boyut, görüntüdeki eşdeğer çaptır."
        if mode == "mask"
        else "Safe-action policy source validation'da donduruldu; external setlerde yeniden ayarlanmadı."
    )
    add_text(draw, (105, 882), note, 25, bold=True, fill=DARK_GREEN, width=108)
    return page


def load_synthetic_visual_summary(visual_root: Path) -> dict[str, float | int]:
    """Aggregate the complete 16-frame V11 held-out visual-audit panel.

    These are pixel-level gallery metrics, intentionally kept separate from
    the intervention connected-component benchmark.
    """

    index_path = (
        visual_root
        / "INDIVIDUAL/04_SYNTHETIC_STRESS/v11_test/index.json"
    )
    artifacts = load_json(index_path)["artifacts"]
    if not artifacts:
        raise ValueError(f"Synthetic visual index is empty: {index_path}")
    metrics = [item["metrics"] for item in artifacts]
    crop_ious = [float(item["crop_iou"]) for item in metrics if item["crop_iou"] is not None]
    weed_present = [item for item in metrics if int(item["weed_pixels"]) > 0]
    weed_ious = [float(item["weed_iou"]) for item in weed_present if item["weed_iou"] is not None]
    weed_pixels = sum(int(item["weed_pixels"]) for item in metrics)
    safe_weed_pixels = sum(int(item["weed_as_safe_weed_pixels"]) for item in metrics)
    predicted_safe_pixels = sum(int(item["safe_weed_pixels"]) for item in metrics)
    crop_pixels = sum(int(item["crop_pixels"]) for item in metrics)
    crop_spray_pixels = sum(int(item["crop_spray_pixels"]) for item in metrics)
    return {
        "images": len(metrics),
        "weed_present_images": len(weed_present),
        "crop_iou_macro": sum(crop_ious) / len(crop_ious),
        "weed_iou_macro_present": sum(weed_ious) / len(weed_ious),
        "safe_weed_recall_micro": safe_weed_pixels / weed_pixels,
        "safe_weed_precision_micro": safe_weed_pixels / predicted_safe_pixels,
        "crop_spray_risk_micro": crop_spray_pixels / crop_pixels,
    }


def build_readable_detailed_pages(
    results: Mapping[str, Mapping[str, Any]],
    rows: Mapping[str, Mapping[str, Any]],
    resolution_rows: Sequence[Mapping[str, Any]],
    visual_root: Path,
    intervention_visual_root: Path,
) -> list[Image.Image]:
    """Build the reader-first detailed PDF requested after visual review.

    Design constraints are deliberate: one main idea per page, at most one
    field example per page, large type, and exact tables only in the appendix.
    """

    source = extract_metrics(view(results["source"]))
    synthetic_summary = load_synthetic_visual_summary(visual_root)
    pages: list[Image.Image] = [readable_cover(source)]
    seen_names = ("PhenoBench", "ACRE", "ROSE", "WE3DS", "WeedsGalore")
    external_names = (
        "Sorghum test",
        "SugarBeets robot",
        "WeedMap UAV",
        "RiceSEG calibration",
        "Early-rice transfer",
    )
    baseline_scale, scale_150, scale_200 = resolution_rows
    worst_crop_name, worst_crop = max(
        ((name, rows[name]["safe_point_crop"]) for name in seen_names),
        key=lambda item: float(item[1] or 0.0),
    )

    pages.append(
        readable_text_page(
            "Bu raporu nasıl oku?",
            "Ana hikâye önde; exact tablolar ve eşikler en sonda.",
            (
                ("1 • Önce sonuç", "Modelin bugün neyi yapabildiğini ve neden saha onayı olmadığını gör.", GREEN),
                ("2 • Sonra örnek", "Her görsel sayfasında yalnız bir saha karesi ve sade bir yorum var.", BLUE),
                ("3 • Doğru metrik", "mIoU yerine müdahalenin gerektirdiği hit, point ve crop-collision ölçülerini izle.", ORANGE),
                ("4 • En sonda kanıt", "Exact dataset tabloları, policy ve sınırlamalar teknik ekte duruyor.", PURPLE),
            ),
            conclusion="Kırmızı uyarı = ölçülmüş risk veya eksik kanıt. Yeşil = yalnız belirtilen kapsamda olumlu sonuç.",
            conclusion_color=RED,
        )
    )
    pages.append(metric_flow_page())
    pages.append(legend_page())

    pages.append(
        simple_metric_cards_page(
            "Ana sonuç: algı var, saha aksiyonu hazır değil",
            "Aynı 1.637 gerçek seen-validation görüntüsü; kabul edilmiş global checkpoint.",
            (
                (pct(source["sem_hit"]), "Weed'i gördü", "GT semantic weed component üzerinde en az bir tahmin pikseli.", BLUE),
                (pct(source["safe_hit"]), "Aksiyona izin verdi", "Dondurulmuş temkinli policy sonrası component hit.", ORANGE),
                (pct(source["safe_subpatch_hit"]), "Küçük weed aksiyonu", "Eşdeğer çap <14 px için safe hit.", RED),
            ),
            decision="Model araştırma için güçlü bir base. Mevcut policy ile production removal kararı verilemez.",
        )
    )
    pages.append(
        readable_text_page(
            "Neden mIoU tek başına yetmiyor?",
            "Aynı maske skoru, robot için çok farklı sonuçlara yol açabilir.",
            (
                ("mIoU ne sorar?", "Tahmin edilen sınıf alanları ground truth ile ne kadar örtüşüyor? Genel segmentasyon kalitesidir.", GREEN),
                ("Robot ne sorar?", "Her weed için kullanılabilir bir hedef var mı? Aksiyon noktası weed üzerinde mi? Footprint crop'a değiyor mu?", BLUE),
                ("Saha ne sorar?", "Gerçek doz/alet/beam hedefe ulaştı mı ve bitki gerçekten öldü ya da söküldü mü?", RED),
            ),
            conclusion=f"Seen mIoU {pct(source['miou'])}; fakat safe component hit yalnız {pct(source['safe_hit'])}. Bu fark kararın özüdür.",
            conclusion_color=RED,
        )
    )
    pages.append(
        simple_metric_cards_page(
            "Bugünkü efektif aksiyon metrikleri",
            "Spot-spray'e en yakın offline proxy'ler; fiziksel deposition testi değildir.",
            (
                (pct(source["safe_hit"]), "Safe component hit", "Weed component üzerinde en az bir izinli aksiyon alanı.", BLUE),
                (pct(source["safe_point_precision"]), "Point precision", "Üretilen aksiyon noktalarının GT weed üzerinde olma oranı.", GREEN),
                (pct(worst_crop), "Worst-field crop point", f"En kötü seen alan: {worst_crop_name}. Ortalama ile gizlenmez.", RED),
            ),
            decision="Etkinlik düşük; safety de her field'da geçmiyor. Eşiklerin temkinli olması tek başına güvenli ürün demek değildir.",
        )
    )
    pages.append(
        simple_metric_cards_page(
            "Küçük weed: ölçülmüş ana darboğaz",
            "<14 px = DINOv2'nin bir patch'inden küçük apparent diameter; fiziksel mm değildir.",
            (
                (pct(source["sem_hit"]), "Tüm weed • semantic hit", "Modelin en azından gördüğü component oranı.", BLUE),
                (pct(source["sem_subpatch_hit"]), "<14 px • semantic hit", "Küçük görünümde belirgin düşüş.", ORANGE),
                (pct(source["safe_subpatch_hit"]), "<14 px • safe hit", "Mevcut policy küçük weed'i neredeyse tamamen susturuyor.", RED),
            ),
            decision="Önce sensörde daha fazla piksel ve küçük-object training; yalnız threshold düşürmek crop riskini artırabilir.",
        )
    )

    pages.append(
        readable_text_page(
            "Hangi bitki öldürme yöntemi bugün en mantıklı?",
            "Mevcut etiketlerin gerçekten desteklediği en basit yol seçildi.",
            (
                ("1 • Mikro / spot spray", "Action point ve footprint proxy'leri mevcut. Gerçek deposition/kill deneyi eklenince en kısa doğrulanabilir MVP.", GREEN),
                ("2 • Mekanik sökme", "Root/crown noktası, depth, mm kalibrasyon ve alet clearance etiketi olmadan saha başarısı ölçülemez.", ORANGE),
                ("3 • Lazer", "Meristem/stem hedefi, beam çapı, dwell/energy ve kill etiketi olmadan maske skoru yeterli değildir.", RED),
            ),
            conclusion="Karar: önce spot-spray test yatağı. Removal yöntemi değişirse primary metriği de değiştir.",
        )
    )
    pages.append(intervention_metric_diagram("spray"))
    pages.append(intervention_metric_diagram("mechanical"))
    pages.append(intervention_metric_diagram("laser"))

    pages.append(
        readable_text_page(
            "Kanıtın gücü aynı değil",
            "Training-unseen, calibration ve untouched final test ayrı şeylerdir.",
            (
                ("1.637 • seen validation", "Beş gerçek dataset. Aynı dataset ailesi train'de var; ayrık kare/session/group kullanıldı.", GREEN),
                ("403 • global dış panel", "Sorghum test + SugarBeets robot + WeedMap UAV. Yeni koşulları ölçer; hepsi final deployment testi değildir.", BLUE),
                ("828 • rice panel", "604 RiceSEG training-held-out calibration + 224 early-rice development/transfer.", ORANGE),
                ("Unlabeled video", "FarmBot, Naïo ve BoniRob yalnız görsel davranış gösterir; doğruluk metriği üretemez.", PURPLE),
            ),
            conclusion="Toplam 2.868 labeled görüntü ölçüldü; fakat henüz kullanıcı sahasından untouched final test yok.",
            conclusion_color=RED,
        )
    )
    pages.append(
        paired_bar_page(
            "Seen validation: model neyi görüyor, policy neye izin veriyor?",
            "Her satır full-split sonuçtur; seçilmiş örnek skoru değildir.",
            [(name, rows[name]["sem_hit"], rows[name]["safe_hit"]) for name in seen_names],
            left_label="Semantic hit • model gördü",
            right_label="Safe hit • aksiyona izin verdi",
            note="ROSE en güçlü aksiyon paneli; her dataset'te semantic → safe düşüşü policy'nin etkinliği bastırdığını gösteriyor.",
        )
    )
    pages.append(
        readable_text_page(
            "Seen veride neden iyi olduğumuz yerler iyi?",
            "En olası ilk neden; nedensel A/B olmayan yerde kesinlik iddiası yok.",
            (
                ("ROSE", "Yakın robot görünümü ve büyük, ayrışmış bitki footprint'i eğitim dağılımıyla iyi eşleşiyor. Semantic hit %70,6; safe hit %54,5.", GREEN),
                ("Sorghum", "Aynı kaynak dağılımı ve büyük/net bitkiler. Semantic hit %96,7; fakat test yalnız 25 kare.", BLUE),
                ("PhenoBench", "Düzenli crop sıraları ve bol crop verisi crop ayrımını kolaylaştırıyor; küçük weed yine zor.", ORANGE),
            ),
            conclusion="İyi skorun ana ortak noktası: hedef görünüme yakın kamera ölçeği ve yeterince büyük bitki footprint'i.",
        )
    )

    individual_root = visual_root / "INDIVIDUAL"
    rose_example = individual_root / "01_SEEN_DATASET_VALIDATION/rose/best/01_rose_2019_weedelec_mais_Weedelec_mais_2019-09-25T121622-252.jpg"
    pages.append(
        example_comparison_page(
            "Gerçek örnek • ROSE'ta semantic ayrım güçlü",
            "Tek kare; solda doğru etiket, sağda model tahmini.",
            rose_example,
            profile="labeled",
            left_index=1,
            right_index=2,
            left_label="GROUND TRUTH",
            right_label="MODEL TAHMİNİ",
            finding="Üstteki mısır crop olarak, ortadaki geniş yapraklı bitki weed olarak doğru ayrılıyor. Büyük ve net footprint model için elverişli.",
            metric_line="Full ROSE: mIoU %82,4 • weed IoU %69,1 • semantic hit %70,6.",
            accent=GREEN,
        )
    )
    pages.append(
        example_comparison_page(
            "Aynı ROSE örneği • iyi maske, az izinli aksiyon",
            "Semantic tahmin ile safety kararı aynı şey değildir.",
            rose_example,
            profile="labeled",
            left_index=2,
            right_index=3,
            left_label="MODEL TAHMİNİ",
            right_label="SAFETY POLICY",
            finding="Model weed alanını genişçe kırmızı görüyor; policy yalnız küçük camgöbeği bölgelerde aksiyona izin veriyor. Bu nedenle maske iyi olsa da müdahale recall'ı düşük kalıyor.",
            metric_line="Full ROSE: semantic hit %70,6 → safe hit %54,5 • safe point precision %78,2. Ana aksiyon ölçüsü full-split component hit'tir.",
            accent=ORANGE,
        )
    )

    pages.append(
        readable_text_page(
            "Seen veride neden zorlandığımız yerler zor?",
            "İlk odak: ölçek ve crop–weed görünüm benzerliği.",
            (
                ("WE3DS", "Çok ürün/tarih, küçük vegetation ve crop–weed morfoloji benzerliği. Weed IoU %28,2; worst seen crop-point hit %4,6.", RED),
                ("WeedsGalore", "Yalnız 104 training karesi ve farklı multispektral-kamera dağılımı. Küçük weed payı %72,1.", ORANGE),
                ("ACRE", "Robot/session ve bean–maize morfoloji değişimi ayrımı zorlaştırıyor; küçük weed payı az olsa da domain çeşitliliği yüksek.", BLUE),
            ),
            conclusion="Önce küçük görünüm + domain mismatch çözülmeli; kompleks post-process ikinci sırada.",
            conclusion_color=RED,
        )
    )
    we3ds_example = individual_root / "01_SEEN_DATASET_VALIDATION/we3ds/worst/01_we3ds_img_00307.jpg"
    pages.append(
        example_comparison_page(
            "Gerçek örnek • WE3DS'te küçük bitki ve crop karışması",
            "Tek kare; koyu/topaklı toprak üzerinde apparent size küçük.",
            we3ds_example,
            profile="labeled",
            left_index=1,
            right_index=2,
            left_label="GROUND TRUTH",
            right_label="MODEL TAHMİNİ",
            finding="Model birçok küçük weed parçasını görüyor; fakat çok küçük hedef crop'u doğru koruyamıyor. Görüntüde birkaç piksellik organlar sınıf ayrımını kırılganlaştırıyor.",
            metric_line="Full WE3DS: crop IoU %79,2 • weed IoU %28,2 • semantic hit %50,8 • safe hit %18,7.",
            accent=RED,
        )
    )

    pages.append(
        paired_bar_page(
            "Dış paneller: dağılım değişince ne oluyor?",
            "Sorghum aynı kaynağa yakın; diğerleri farklı kamera, saha veya rice development paneli.",
            [(name, rows[name]["sem_hit"], rows[name]["safe_hit"]) for name in external_names],
            left_label="Semantic hit",
            right_label="Safe hit",
            note="WeedMap ve early-rice, farklı ölçek/domain altında kırılmayı açıkça gösteriyor. Rice safe hit'in düşüklüğü ayrıca eşik kalibrasyon sorunu taşıyor.",
        )
    )

    sugar_best = individual_root / "03_LABELED_TRANSFER/sugarbeets_holdout/best/01_sugarbeets2016_multiclass_bonirob_2016-05-23-10-37-10_0_frame00187.jpg"
    pages.append(
        example_comparison_page(
            "Unseen robot örneği • SugarBeets iyi kare",
            "Bu session eğitime girmedi; hedef robot perspektifine yakın labeled transfer.",
            sugar_best,
            profile="labeled",
            left_index=1,
            right_index=2,
            left_label="GROUND TRUTH",
            right_label="MODEL TAHMİNİ",
            finding="Bu karede crop merkezde yeşil korunuyor, çevredeki weed alanları kırmızı ayrılıyor. Model doğru koşulda transfer edebiliyor.",
            metric_line="Bu yalnız iyi uç örnektir. Full SugarBeets sonucu: mIoU %57,7 • semantic hit %44,0 • safe hit %8,0.",
            accent=GREEN,
        )
    )
    sugar_worst = individual_root / "03_LABELED_TRANSFER/sugarbeets_holdout/worst/02_sugarbeets2016_multiclass_bonirob_2016-05-23-10-37-10_0_frame00128.jpg"
    pages.append(
        example_comparison_page(
            "Aynı unseen robot seti • tehlikeli kötü kare",
            "Tek bir iyi örnek full-split güvenliği temsil etmez.",
            sugar_worst,
            profile="labeled",
            left_index=1,
            right_index=3,
            left_label="GROUND TRUTH",
            right_label="SAFETY POLICY",
            finding="Ground truth'ta alttaki büyük bitki crop; safety panelindeki sarı alan crop'a yanlış müdahale riskini gösteriyor. Karanlık/exposure ve morfoloji kayması belirgin.",
            metric_line="Full SugarBeets: safe point precision %67,0 • crop point hit %18,2 • r=10 crop collision %18,8.",
            accent=RED,
        )
    )
    weedmap_example = individual_root / "03_LABELED_TRANSFER/weedmap_uav/worst/01_weedmap_003_frame0053.jpg"
    pages.append(
        example_comparison_page(
            "OOD örnek • WeedMap UAV",
            "10 m UAV görünümü; robot kamerasından çok farklı apparent scale.",
            weedmap_example,
            profile="labeled",
            left_index=1,
            right_index=2,
            left_label="GROUND TRUTH",
            right_label="MODEL TAHMİNİ",
            finding="Ground truth'ta düzenli yeşil crop sıraları var; model bunların önemli bölümünü kırmızı weed olarak yorumluyor. Bu net bir viewpoint/GSD domain failure örneği.",
            metric_line="Full WeedMap: crop IoU %0,01 • weed IoU %12,5 • semantic hit %7,0 • small-weed payı %92,8.",
            accent=RED,
        )
    )
    pages.append(
        readable_text_page(
            "Dış panellerde ilk kök neden",
            "Görseller ve metadata ile en uyumlu, öncelikli hipotezler.",
            (
                ("SugarBeets robot", "Karanlık/exposure farkı ve yeni session morfolojisi crop'u weed'e çeviriyor. İlk çözüm gerçek rig verisi + ışık kontrolü.", RED),
                ("WeedMap UAV", "10 m GSD ve üstten uzak bakış apparent size'ı aşırı küçültüyor. Robot hedefiyle aynı distribution değil; breadth stress testidir.", ORANGE),
                ("Early rice", "Farklı kamera yüksekliği, su yansıması ve fide evresi. Küçük component payı %87,0; specialist bu dataset'i train'de görmedi.", BLUE),
            ),
            conclusion="Genel base gerekiyor; fakat model seçimi hedef robot verisine daha yüksek ağırlık vermeli ve OOD alt sınırı ayrıca korunmalı.",
        )
    )

    pages.append(
        readable_text_page(
            "Rice sonucu hangi kanıt seviyesinde?",
            "Doğru yorum: training-held-out calibration; untouched final test değil.",
            (
                ("604 kare", "Guangdong + Tokyo görüntüleri specialist training yollarıyla 0/604 çakışıyor.", GREEN),
                ("Ama final test değil", "Bu panel geçmiş specialist model/seed seçiminde kullanıldı; dolayısıyla development/calibration rolünde.", ORANGE),
                ("Eski 1.254 galeri", "Alternatif country manifesti training path'leriyle 1.254/1.254 çakışıyor; yalnız train-seen diagnostic.", RED),
            ),
            conclusion="Rice için yeni, bağımsız saha/session untouched test hâlâ gerekli.",
            conclusion_color=RED,
        )
    )
    rice_example = intervention_visual_root / "riceseg_heldout/best/01_riceseg_TKO_2_2014_0805_080221_subset_overlap_1_1.jpg"
    pages.append(
        example_comparison_page(
            "Rice calibration örneği • crop maskesi güçlü",
            "Tek training-held-out kare; bu örnekte GT weed yok.",
            rice_example,
            profile="rice",
            left_index=1,
            right_index=2,
            left_label="GROUND TRUTH",
            right_label="MODEL TAHMİNİ",
            finding="Yoğun ve üst üste binen rice yaprakları büyük ölçüde crop olarak yakalanıyor. Bu örnek yalnız crop segmentasyonunu gösterir; weed başarısı hakkında kanıt taşımaz.",
            metric_line="Full Rice calibration: crop IoU %80,2 • weed IoU %22,2 • semantic weed hit %39,9.",
            accent=GREEN,
        )
    )
    rice = rows["RiceSEG calibration"]
    pages.append(
        simple_metric_cards_page(
            "Rice uzmanı: crop iyi, weed aksiyonu zayıf",
            "604 kare calibration paneli; bu koşuda threshold retune edilmedi.",
            (
                (pct(rice["crop_iou"]), "Crop IoU", "Rice canopy ayrımı güçlü.", GREEN),
                (pct(rice["weed_iou"]), "Weed IoU", "Seyrek weed/duckweed ve su domain'i zor.", ORANGE),
                (pct(rice["safe_hit"]), "Safe component hit", "Rice'e özel aksiyon eşiği pratikte no-spray davranıyor.", RED),
            ),
            decision="Rice specialist crop tabanı olarak değerli; weed-removal modeli olarak kalibre edilmiş değil.",
        )
    )

    pages.append(
        simple_metric_cards_page(
            "Yazılımsal upscale A/B",
            "Aynı 224 early-rice karesi; interpolation yeni optik bilgi üretmez.",
            tuple(
                (
                    str(metric["label"]),
                    f"<14 px hit {pct(metric['semantic_subpatch_hit'])}",
                    f"crop point {pct(metric['safe_point_crop'])} • {dec(metric['perception_ms'], 1)} ms/img",
                    BLUE if metric["scale"] == 1.0 else (ORANGE if metric["scale"] == 1.5 else RED),
                )
                for metric in resolution_rows
            ),
            decision="2× küçük weed hit'ini artırdı; fakat crop-point hatası ve latency ciddi arttığı için kabul edilmedi.",
        )
    )
    pages.append(
        readable_text_page(
            "Upscale neden reddedildi?",
            "Bir metriği yükseltmek yetmez; guard metrikleri aynı anda geçmelidir.",
            (
                ("Kazanç", f"<14 px semantic hit {pct(baseline_scale['semantic_subpatch_hit'])} → {pct(scale_200['semantic_subpatch_hit'])}; ölçek darboğazı gerçek.", GREEN),
                ("Safety kaybı", f"Crop-point hit {pct(baseline_scale['safe_point_crop'])} → {pct(scale_200['safe_point_crop'])}; yanlış müdahale riski arttı.", RED),
                ("Hız kaybı", f"Perception {dec(baseline_scale['perception_ms'], 1)} → {dec(scale_200['perception_ms'], 1)} ms/görüntü; yaklaşık 5,9× daha yavaş.", ORANGE),
            ),
            conclusion=f"1,5× de crop-point hit'i {pct(scale_150['safe_point_crop'])} yaptı. Karar: software upscale yok; optik + training A/B.",
            conclusion_color=RED,
        )
    )
    pages.append(
        readable_text_page(
            "Küçük weed için önce donanım",
            "Modelin görmediği optik detayı yazılım geri üretemez.",
            (
                ("1 • GSD / yükseklik", "Minimum öldürülecek weed'i sensörde en az 28 px, tercihen 56 px gösterecek kamera–yükseklik tasarla.", GREEN),
                ("2 • Fokus / blur", "Focus lock, yeterli depth-of-field, kısa exposure; hareket bulanıklığını robot hızıyla birlikte ölç.", BLUE),
                ("3 • Işık", "Diffuse kontrollü ışık veya strobe; güneş açısı, lokal gölge, ıslak toprak parlaması ve lens kirini telemetry'ye yaz.", ORANGE),
                ("4 • Sonra model", "Small-object oversampling + larger crop + multi-scale training; aynı compute ve seed guard ile A/B.", PURPLE),
            ),
            conclusion="En etkili basit yaklaşım: optik kaliteyi sabitle, sonra yalnız ölçülmüş small-object darboğazına eğitim değişikliği yap.",
        )
    )

    bonirob_example = individual_root / "02_UNLABELED_REAL/bonirob_unseen/frame_010.jpg"
    pages.append(
        example_comparison_page(
            "Online unseen video • BoniRob",
            "Etiket yok: solda görüntü, sağda yalnız model tahmini.",
            bonirob_example,
            profile="unlabeled",
            left_index=0,
            right_index=1,
            left_label="RGB / ORİJİNAL",
            right_label="MODEL TAHMİNİ",
            finding="Yeni videoda model bazı bitki parçalarını crop/weed olarak işaretliyor. Ground truth olmadığı için bunun doğru olup olmadığını sayısal olarak söyleyemeyiz.",
            metric_line="Bu sayfa yalnız görsel domain davranışıdır; accuracy, IoU veya removal başarı kanıtı değildir.",
            accent=PURPLE,
        )
    )
    pages.append(
        readable_text_page(
            "Unlabeled video ne işe yarar?",
            "Doğruluk ölçmez; yeni saha sorunlarını hızlıca bulur.",
            (
                ("Görebildiğimiz", "Kamera açısı, exposure, blur, soil/plant görünümü ve modelin aşırı/eksik tahmin eğilimi.", GREEN),
                ("Göremediğimiz", "Gerçek crop/weed doğruluğu, kaç weed kaçtı, crop'a yanlış aksiyon ve kill oranı.", RED),
                ("Doğru sonraki adım", "Videodan field/session-ayrık kare örnekle; bağımsız kişiyle mask/keypoint etiketle; bir kez untouched test olarak aç.", BLUE),
            ),
            conclusion="Video galerisi model seçme metriği değil, data toplama ve failure keşif aracıdır.",
        )
    )

    synthetic_best = individual_root / "04_SYNTHETIC_STRESS/v11_test/best/02_cropcraft_field_robustness_pilot_v11_r2q_test_scene_0001_frame_0001.jpg"
    pages.append(
        example_comparison_page(
            "Sentetik unseen holdout • güçlü örnek",
            "V11 asset/seed ayrık test; bu sahne ve seed eğitim rolünde yok.",
            synthetic_best,
            profile="labeled",
            left_index=1,
            right_index=2,
            left_label="SENTETİK GROUND TRUTH",
            right_label="MODEL TAHMİNİ",
            finding="Bu karede sorgum crop'ları yeşil, geniş yapraklı weed'ler kırmızı olarak büyük ölçüde doğru ayrılıyor. Farklı toprak parçaları ve residue tahmini bozmuyor.",
            metric_line="Bu kare: crop IoU %44,8 • weed IoU %84,6 • safe-weed recall %51,3 • crop spray pixel risk %0,0.",
            accent=GREEN,
        )
    )
    synthetic_worst = individual_root / "04_SYNTHETIC_STRESS/v11_test/worst/03_cropcraft_field_robustness_pilot_v11_r2q_test_scene_0002_frame_0002.jpg"
    pages.append(
        example_comparison_page(
            "Sentetik unseen holdout • zor örnek",
            "Aynı V11 test; küçük bitkiler ve farklı kırmızı toprak.",
            synthetic_worst,
            profile="labeled",
            left_index=1,
            right_index=2,
            left_label="SENTETİK GROUND TRUTH",
            right_label="MODEL TAHMİNİ",
            finding="Büyük iki sorgum yakalanıyor; küçük weed'lerin çoğu kayboluyor veya parçalanıyor. Gerçek veride gördüğümüz small-object darboğazı sentetik holdout'ta da tekrarlanıyor.",
            metric_line="Bu kare: crop IoU %36,5 • weed IoU %18,7 • safe-weed recall %0,66 • crop spray pixel risk %0,0.",
            accent=RED,
        )
    )
    pages.append(
        simple_metric_cards_page(
            "Sentetik unseen holdout • 16 karenin özeti",
            "V11 asset/seed ayrık test; pixel-level visual-audit aggregate.",
            (
                (pct(float(synthetic_summary["crop_iou_macro"])), "Macro crop IoU", "16 karenin per-image ortalaması.", GREEN),
                (pct(float(synthetic_summary["weed_iou_macro_present"])), "Macro weed IoU", f"Weed bulunan {int(synthetic_summary['weed_present_images'])}/{int(synthetic_summary['images'])} kare.", BLUE),
                (pct(float(synthetic_summary["safe_weed_recall_micro"])), "Safe weed recall", "Tüm GT weed pikselleri üzerinde mikro aggregate.", ORANGE),
            ),
            decision=(
                f"Safe pixel precision {pct(float(synthetic_summary['safe_weed_precision_micro']))}; "
                f"crop spray pixel risk {pct(float(synthetic_summary['crop_spray_risk_micro']))}. "
                "Sentetik domain içinde temkinli ama küçük weed recall'ı sınırlı."
            ),
            decision_color=ORANGE,
        )
    )
    pages.append(
        readable_text_page(
            "Sentetik veri için net karar",
            "Görsel kalite ve gerçek model katkısı iki ayrı gate'tir.",
            (
                ("Kabul edildi", "Dryland V3 + paddy R5 sentetik dozları gerçek-domain model gate'ini geçti ve global checkpoint'te kaldı.", GREEN),
                ("Kaliteli ama reddedildi", "Soy, motion ve field-robustness asset'leri görsel gate'i geçti; bazı gerçek datasetlerde regresyon yarattığı için mix'e eklenmedi.", RED),
                ("Yeni üretim ne zaman?", "Yalnız gerçek field audit tek bir eksik faktörü gösterirse ve önceden dondurulmuş A/B gate varsa.", BLUE),
            ),
            conclusion="Daha fazla sentetik veri otomatik olarak daha robust model demek değildir.",
        )
    )

    pages.append(
        simple_metric_cards_page(
            "Provisional offline spot-spray gate",
            "Evrensel standart değil; aktüatör seçilene kadar proje başlangıç gate'i.",
            (
                (f"{pct(source['safe_hit'])} / ≥%90", "Safe component hit", "Etkinlik gate'i: BAŞARISIZ.", RED),
                (f"{pct(source['safe_point_precision'])} / ≥%95", "Point precision", "Doğru hedef gate'i: BAŞARISIZ.", RED),
                (f"{pct(worst_crop)} / ≤%0,5", "Worst-field crop point", "Safety gate'i: BAŞARISIZ.", RED),
            ),
            decision="Hiçbir removal yöntemi production gate'i geçmedi. Sonraki onay, gerçek deposition/injury ve kill outcome ile verilecek.",
        )
    )
    pages.append(
        readable_text_page(
            "Untouched saha testi nasıl kurulmalı?",
            "Validation geniş olmalı; test kullanıcı sahasını dürüstçe temsil etmeli.",
            (
                ("Tarla bağımsızlığı", "3–4 bağımsız tarla/session; hiçbir komşu frame veya aynı sıra train'e sızmamalı.", GREEN),
                ("Gerçek çeşitlilik", "Dry/wet soil, tillage/clod/residue; sabah/öğle/akşam; gölge, robot ışığı, exposure, lens kiri.", BLUE),
                ("Küçük weed strata", "Minimum fiziksel çap mm + sensörde çap px; evre ve occlusion ayrı strata olarak raporlanmalı.", ORANGE),
                ("Removal outcome", "Her plant için action + deposition/tool hit + 24/48 saat kill veya successful removal etiketi bağlanmalı.", RED),
            ),
            conclusion="Val hedef koşullara ağırlıklı ve çeşitli; untouched test field/session-ayrık ve yalnız bir kez açılmalı.",
        )
    )
    pages.append(
        readable_text_page(
            "Şimdi yapılacak üç deney",
            "En küçük deney, en kritik belirsizliği çözsün.",
            (
                ("P0 • Kamera rig", "GSD, intrinsics/extrinsics, focus, exposure, blur, çalışma yüksekliği, footprint ve perception-to-actuation latency ölç.", GREEN),
                ("P1 • Basit model A/B", "Small-object oversampling + larger/multi-scale crop; aynı compute/seed. Crop false-action kötüleşirse fail-closed.", BLUE),
                ("P2 • Gerçek spot-spray", "Fluorescent dye / deposition paper ile weed deposition, crop deposition/injury, miss ve throughput ölç.", ORANGE),
            ),
            conclusion="Mekanik/lazer seçilirse P2 değişir: root/crown veya meristem keypoint + mm P50/P95 + gerçek removal/kill.",
        )
    )
    pages.append(
        readable_text_page(
            "Bu rapor neyi kanıtlıyor, neyi kanıtlamıyor?",
            "Dürüst sınır, doğru mühendislik kararının parçasıdır.",
            (
                ("Kanıtlıyor", "Kabul edilmiş modelin 2.868 labeled görüntüde mask, component, action-point ve footprint proxy davranışını.", GREEN),
                ("Kanıtlamıyor", "True plant instance, root/crown, meristem, mm doğruluğu, nozzle deposition, crop injury veya kill/removal oranını.", RED),
                ("En büyük risk", "Pooled ortalama iyi görünürken tek bir field'da crop yanlış aksiyonu yüksek olabilir; safety worst-field okunmalı.", ORANGE),
            ),
            conclusion="Bu nedenle bugünkü doğru ürün tanımı: robust segmentasyon araştırma base'i; production weed-removal sistemi değil.",
            conclusion_color=RED,
        )
    )
    pages.append(
        readable_text_page(
            "Net karar",
            "Bundan sonra odak dağılmadan ilerlemek için.",
            (
                ("Model", "Global checkpoint genel base; Rice checkpoint uzman base olarak korunur. Mevcut kanıtta model değiştirme gerekçesi yok.", GREEN),
                ("Veri", "Yeni kullanıcı-sahası untouched seti ve küçük weed strata kritik. Rastgele daha fazla dataset eklemek öncelik değil.", BLUE),
                ("Donanım", "GSD/focus/exposure/blur kontrolü, küçük weed için software upscale'tan daha yüksek öncelikte.", ORANGE),
                ("Müdahale", "Önce spot-spray deposition pilotu. Mekanik/lazer ancak gerekli keypoint ve mm geometri toplanınca.", RED),
            ),
            conclusion="Başarı tanımı: weed'i görmek değil; doğru bitkiye, crop'a zarar vermeden, yeterli fiziksel etkiyi uygulamak.",
        )
    )

    # Technical appendix: exact values remain available without interrupting
    # the main narrative.
    pages.append(
        readable_exact_table_page(
            "TEKNİK EK • Seen mask ve detection",
            "Exact full-split değerler.",
            seen_names,
            rows,
            mode="mask",
        )
    )
    pages.append(
        readable_exact_table_page(
            "TEKNİK EK • Seen aksiyon ve safety",
            "External retune yok; source-frozen policy.",
            seen_names,
            rows,
            mode="action",
        )
    )
    pages.append(
        readable_exact_table_page(
            "TEKNİK EK • Dış panel mask ve detection",
            "Kanıt rolleri birbirinden farklıdır; ana bölümde açıklanmıştır.",
            external_names,
            rows,
            mode="mask",
        )
    )
    pages.append(
        readable_exact_table_page(
            "TEKNİK EK • Dış panel aksiyon ve safety",
            "Düşük action sayısında point precision tek başına başarı değildir.",
            external_names,
            rows,
            mode="action",
        )
    )

    global_policy, global_overrides = policy_lines(results["source"])
    rice_policy, rice_overrides = policy_lines(results["rice"])
    pages.append(
        readable_text_page(
            "TEKNİK EK • Dondurulmuş policy",
            "Exact checkpoint değerleri; deployment safety sertifikası değildir.",
            (
                ("Global common", global_policy, GREEN),
                ("Global crop overrides", global_overrides, BLUE),
                ("Rice common", rice_policy, ORANGE),
                ("Rice overrides", rice_overrides, PURPLE),
            ),
            conclusion="External panellerde threshold sweep/retune yapılmadı. Test üzerinde eşik seçilmedi.",
        )
    )
    pages.append(
        readable_text_page(
            "TEKNİK EK • Metrik sözlüğü",
            "Kısa ve operasyonel tanım.",
            (
                ("Component hit", "GT semantic weed connected component üzerinde en az bir tahmin pikseli. True instance değildir.", BLUE),
                ("Action point", "Her predicted component içindeki en derin piksel; point precision bu noktanın GT weed üzerinde olup olmadığını ölçer.", GREEN),
                ("Footprint collision", "Action merkezli 0/5/10/20 px dairenin GT crop'a değmesi. Fiziksel nozzle modeli değildir.", RED),
                ("Small weed", "Eşdeğer component çapı <14 px. 14 px backbone patch ölçeğidir; botanik boyut değildir.", ORANGE),
            ),
            conclusion="Mekanik/lazer için canopy centroid yalnız proxy'dir; root/crown/meristem değildir.",
        )
    )
    pages.append(
        readable_text_page(
            "TEKNİK EK • Reproducibility ve kaynaklar",
            "Ham JSON ve exact hash'ler self-contained rapor klasöründe.",
            (
                ("Protokol", "intervention_semantic_component_proxy_v1 • native inference • source-frozen safety • external retune yok.", GREEN),
                ("Literatür", "Laser meristem DOI 10.3390/agronomy14092121 • Mechanical DOI 10.3965/j.ijabe.20150806.1932.", BLUE),
                ("Ölçek", "WeedMap/GSD: arXiv:1808.00100 • micro-jet PII S1537511023000375 • field sprayer PII S2666154324003685.", ORANGE),
            ),
            conclusion="Checkpoint, manifest ve mask-tree SHA-256 değerleri her metric JSON'unda provenance altında saklıdır.",
        )
    )

    finalize_pages(pages, "Crop Müdahale • Anlaşılır Detaylı Rapor")
    return pages


def write_readme(output: Path, files: Mapping[str, Path]) -> None:
    lines = [
        "# Crop intervention report v1",
        "",
        "Önce sonuç için `KISA_KARAR_RAPORU.pdf`; tek-fikir/tek-örnek düzenindeki açıklamalı ana rapor için `DETAYLI_TEKNIK_RAPOR.pdf` dosyasını açın.",
        "",
        "## Dosyalar",
        "",
    ]
    for label, path in files.items():
        lines.append(f"- `{path.name}` — {label}; SHA-256 `{sha256(path)}`")
    lines.extend(
        [
            "",
            "Metriklerin ham JSON'ları `METRICS/`, inference-scale A/B makbuzları `RESOLUTION_ABLATION/`, raporda kullanılan tekil açıklamalı örnekler `QUALITATIVE/` altında kopyalanmıştır. External threshold tuning yapılmadı.",
            "",
            "Önemli: connected-component ve center değerleri semantic-mask proxy'sidir; true plant instance/root/meristem veya mm doğruluğu değildir.",
        ]
    )
    (output / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build(
    metrics_root: Path,
    resolution_root: Path,
    visual_root: Path,
    intervention_visual_root: Path,
    output: Path,
) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    results = load_results(metrics_root)
    rows = dataset_rows(results)
    resolution_rows = load_resolution_rows(resolution_root)
    synthetic_summary = load_synthetic_visual_summary(visual_root)
    metrics_bundle = output / "METRICS"
    if metrics_bundle.exists():
        shutil.rmtree(metrics_bundle)
    shutil.copytree(metrics_root, metrics_bundle)
    resolution_bundle = output / "RESOLUTION_ABLATION"
    if resolution_bundle.exists():
        shutil.rmtree(resolution_bundle)
    shutil.copytree(resolution_root, resolution_bundle)
    qualitative_bundle = output / "QUALITATIVE"
    if qualitative_bundle.exists():
        shutil.rmtree(qualitative_bundle)
    qualitative_bundle.mkdir(parents=True)
    individual_root = visual_root / "INDIVIDUAL"
    qualitative_sources = {
        "01_seen_rose_good_example.jpg": individual_root / "01_SEEN_DATASET_VALIDATION/rose/best/01_rose_2019_weedelec_mais_Weedelec_mais_2019-09-25T121622-252.jpg",
        "02_seen_we3ds_hard_example.jpg": individual_root / "01_SEEN_DATASET_VALIDATION/we3ds/worst/01_we3ds_img_00307.jpg",
        "03_sugarbeets_holdout_good_example.jpg": individual_root / "03_LABELED_TRANSFER/sugarbeets_holdout/best/01_sugarbeets2016_multiclass_bonirob_2016-05-23-10-37-10_0_frame00187.jpg",
        "04_sugarbeets_holdout_danger_example.jpg": individual_root / "03_LABELED_TRANSFER/sugarbeets_holdout/worst/02_sugarbeets2016_multiclass_bonirob_2016-05-23-10-37-10_0_frame00128.jpg",
        "05_weedmap_uav_ood_example.jpg": individual_root / "03_LABELED_TRANSFER/weedmap_uav/worst/01_weedmap_003_frame0053.jpg",
        "06_riceseg_training_heldout_crop_example.jpg": intervention_visual_root / "riceseg_heldout/best/01_riceseg_TKO_2_2014_0805_080221_subset_overlap_1_1.jpg",
        "07_online_bonirob_unlabeled_example.jpg": individual_root / "02_UNLABELED_REAL/bonirob_unseen/frame_010.jpg",
        "08_synthetic_v11_holdout_good_example.jpg": individual_root / "04_SYNTHETIC_STRESS/v11_test/best/02_cropcraft_field_robustness_pilot_v11_r2q_test_scene_0001_frame_0001.jpg",
        "09_synthetic_v11_holdout_hard_example.jpg": individual_root / "04_SYNTHETIC_STRESS/v11_test/worst/03_cropcraft_field_robustness_pilot_v11_r2q_test_scene_0002_frame_0002.jpg",
    }
    missing_qualitative = [
        str(source_path)
        for source_path in qualitative_sources.values()
        if not source_path.is_file()
    ]
    if missing_qualitative:
        raise FileNotFoundError(
            "Missing required qualitative report evidence: "
            + "; ".join(missing_qualitative)
        )
    for destination, source_path in qualitative_sources.items():
        shutil.copy2(source_path, qualitative_bundle / destination)
    markdown_path = output / "DETAYLI_TEKNIK_RAPOR.md"
    markdown_path.write_text(
        markdown_report(results, rows, resolution_rows, synthetic_summary),
        encoding="utf-8",
    )

    short_path = output / "KISA_KARAR_RAPORU.pdf"
    detailed_path = output / "DETAYLI_TEKNIK_RAPOR.pdf"
    short_pages = build_short_pages(
        results, rows, resolution_rows, visual_root
    )
    detailed_pages = build_readable_detailed_pages(
        results,
        rows,
        resolution_rows,
        visual_root,
        intervention_visual_root,
    )
    short_page_count = len(short_pages)
    detailed_page_count = len(detailed_pages)
    save_pdf(
        short_pages,
        short_path,
        title="Crop Müdahale — Kısa Karar Raporu",
    )
    save_pdf(
        detailed_pages,
        detailed_path,
        title="Crop Müdahale — Anlaşılır Detaylı Rapor",
    )
    del short_pages, detailed_pages
    files = {
        "Kısa, karar-odaklı PDF": short_path,
        "Anlaşılır, örnekli ayrıntılı PDF": detailed_path,
        "Aranabilir teknik metin eki": markdown_path,
    }
    write_readme(output, files)

    repo_short = PROJECT_ROOT / "docs/results/BASLA_BURADAN_MUDAHALE_RAPORU.pdf"
    repo_detailed = PROJECT_ROOT / "docs/results/DETAYLI_BITKI_MUDAHALE_RAPORU.pdf"
    repo_markdown = PROJECT_ROOT / "docs/INTERVENTION_EVALUATION_V1.md"
    root_short = PROJECT_ROOT / "BASLA_BURADAN_MUDAHALE_RAPORU.pdf"
    root_detailed = PROJECT_ROOT / "ANLASILIR_DETAYLI_MUDAHALE_RAPORU.pdf"
    repo_short.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(short_path, repo_short)
    shutil.copy2(detailed_path, repo_detailed)
    shutil.copy2(markdown_path, repo_markdown)
    shutil.copy2(short_path, root_short)
    shutil.copy2(detailed_path, root_detailed)

    receipt = {
        "schema_version": 2,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "metrics_root": str(metrics_root.resolve()),
        "resolution_root": str(resolution_root.resolve()),
        "self_contained_metrics_bundle": str(metrics_bundle.resolve()),
        "self_contained_resolution_bundle": str(resolution_bundle.resolve()),
        "self_contained_qualitative_bundle": str(qualitative_bundle.resolve()),
        "visual_root": str(visual_root.resolve()),
        "intervention_visual_root": str(intervention_visual_root.resolve()),
        "output": str(output.resolve()),
        "files": {
            label: {
                "path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for label, path in files.items()
        },
        "repo_copies": {
            "short": str(repo_short.resolve()),
            "detailed": str(repo_detailed.resolve()),
            "markdown": str(repo_markdown.resolve()),
            "root_short": str(root_short.resolve()),
            "root_readable_detailed": str(root_detailed.resolve()),
        },
        "current_reproducer_sources": {
            str(path.relative_to(PROJECT_ROOT)): {
                "path": str(path.resolve()),
                "sha256": sha256(path),
            }
            for path in (
                PROJECT_ROOT / "scripts/evaluate_intervention_metrics.py",
                PROJECT_ROOT / "scripts/build_intervention_reports.py",
                PROJECT_ROOT / "scripts/audit_riceseg_split_overlap.py",
                PROJECT_ROOT / "configs/benchmark/intervention_metrics_v1.yaml",
                PROJECT_ROOT
                / "configs/benchmark/intervention_resolution_ablation_v1.yaml",
                PROJECT_ROOT / "tests/test_intervention_metrics.py",
            )
        },
        "quality_gates": {
            "all_metric_payloads_present": True,
            "external_threshold_tuning": False,
            "rice_training_heldout_calibration_used": True,
            "rice_untouched_final_test_claimed": False,
            "country_transfer_overlap_disclosed": True,
            "semantic_component_proxy_disclosed": True,
            "required_individual_qualitative_examples": len(qualitative_sources),
            "one_field_example_per_visual_page": True,
            "exact_tables_moved_to_appendix": True,
            "pdf_page_count_short": short_page_count,
            "pdf_page_count_detailed": detailed_page_count,
        },
    }
    receipt_path = output / "report_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics-root", type=Path, default=DEFAULT_METRICS_ROOT)
    parser.add_argument(
        "--resolution-root", type=Path, default=DEFAULT_RESOLUTION_ROOT
    )
    parser.add_argument("--visual-root", type=Path, default=DEFAULT_VISUAL_ROOT)
    parser.add_argument(
        "--intervention-visual-root",
        type=Path,
        default=DEFAULT_INTERVENTION_VISUAL_ROOT,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    receipt = build(
        args.metrics_root.expanduser().resolve(),
        args.resolution_root.expanduser().resolve(),
        args.visual_root.expanduser().resolve(),
        args.intervention_visual_root.expanduser().resolve(),
        args.output.expanduser().resolve(),
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
