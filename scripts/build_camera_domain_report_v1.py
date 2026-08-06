#!/usr/bin/env python3
"""Build a readable, result-first PDF/Markdown for the new ablations."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw
import yaml

try:
    from scripts.build_intervention_reports import (
        BG,
        BLUE,
        DARK_GREEN,
        GREEN,
        INK,
        LIGHT_BLUE,
        LIGHT_GREEN,
        LIGHT_ORANGE,
        LIGHT_RED,
        LINE,
        MUTED,
        ORANGE,
        RED,
        WHITE,
        add_text,
        base_page,
        bullet_list,
        card,
        draw_table,
        finalize_pages,
        font,
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
        INK,
        LIGHT_BLUE,
        LIGHT_GREEN,
        LIGHT_ORANGE,
        LIGHT_RED,
        LINE,
        MUTED,
        ORANGE,
        RED,
        WHITE,
        add_text,
        base_page,
        bullet_list,
        card,
        draw_table,
        finalize_pages,
        font,
        paste_contain,
        pct,
        save_pdf,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = Path("/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data")
CAMERA_ROOT = DATA_ROOT / "processed/audits/camera_optics_intervention_v1"
ROW_ROOT = DATA_ROOT / "processed/audits/crop_row_prior_v1"
INTERVENTION_ROOT = DATA_ROOT / "processed/audits/intervention_metrics_v1/global"
DOMAIN_RESULT = DATA_ROOT / "processed/audits/domain_adaptation_curve_v1/results.json"
DOMAIN_CONFIRM_RESULT = (
    DATA_ROOT / "processed/audits/domain_adaptation_confirm_v1/results.json"
)
SMALL_RESULT = DATA_ROOT / "processed/audits/small_object_training_ablation_v1/results.json"
SMALL_CONFIRM_RESULT = (
    DATA_ROOT / "processed/audits/small_object_canvas_confirm_v1/results.json"
)
REAL_RASTER_ROOT = (
    DATA_ROOT / "processed/audits/camera_real_raster_intervention_v1/global"
)
SMALL_INTERVENTION_ROOT = (
    DATA_ROOT / "processed/audits/small_object_selected_intervention_v1"
)
OUTPUT = DATA_ROOT / "processed/audits/camera_domain_report_v1"
REPO_PDF = PROJECT_ROOT / "docs/results/KAMERA_DOMAIN_VE_KUCUK_OT_DENEY_RAPORU.pdf"
REPO_SIMPLE_PDF = (
    PROJECT_ROOT / "docs/results/BASLA_BURADAN_KAMERA_DOMAIN_KARARI.pdf"
)
REPO_MD = PROJECT_ROOT / "docs/KAMERA_DOMAIN_VE_KUCUK_OT_DENEYLERI_V1.md"


def _json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def camera_metrics(name: str) -> dict[str, float]:
    data = _json(CAMERA_ROOT / "global" / f"{name}.json")["overall"]
    semantic = data["semantic_segmentation"]
    safe = data["frozen_safe_pixel_metrics"]
    components = data["modes"]["frozen_safe_action"]["component_metrics"]["all"]
    return {
        "miou": float(semantic["mean_iou"]),
        "crop": float(semantic["iou"]["target_crop"]),
        "weed": float(semantic["iou"]["other_vegetation"]),
        "risk": float(safe["crop_spray_risk_per_crop_pixel"]),
        "safe_recall": float(safe["safe_weed_pixel_recall"]),
        "component_hit": float(components["component_hit_recall_any_overlap"]),
    }


def camera_component_bins(name: str) -> list[dict[str, Any]]:
    metrics = _json(CAMERA_ROOT / "global" / f"{name}.json")["overall"]["modes"][
        "frozen_safe_action"
    ]["component_metrics"]
    bins = (
        ("<14 px", "sub_patch_lt14px"),
        ("14–28 px", "one_to_two_patches_14_28px"),
        ("28–56 px", "two_to_four_patches_28_56px"),
        ("≥56 px", "four_plus_patches_ge56px"),
    )
    return [
        {
            "label": label,
            "component_hit": float(metrics[key]["component_hit_recall_any_overlap"]),
            "components": int(metrics[key]["semantic_component_proxies"]),
            "pixel_recall": float(metrics[key]["pixel_recall_within_components"]),
        }
        for label, key in bins
        if metrics.get(key) is not None
    ]


def latency_metrics(size: int) -> dict[str, float]:
    payload = _json(CAMERA_ROOT / f"latency_{size}.json")
    return {
        "mean_ms": float(payload["latency_ms"]["mean"]),
        "p95_ms": float(payload["latency_ms"]["p95"]),
        "images_per_second": float(payload["images_per_second"]),
    }


def intervention_metrics(path: Path) -> dict[str, float]:
    """Read action-oriented metrics from a full intervention evaluation."""
    payload = _json(path)
    overall = payload["overall"]
    semantic = overall["semantic_segmentation"]
    safe = overall["frozen_safe_pixel_metrics"]
    component_metrics = overall["modes"]["frozen_safe_action"][
        "component_metrics"
    ]
    components = component_metrics["all"]
    small_components = component_metrics.get("sub_patch_lt14px") or {}
    runtime = payload.get("runtime") or {}
    return {
        "miou": float(semantic["mean_iou"]),
        "crop": float(semantic["iou"]["target_crop"]),
        "weed": float(semantic["iou"]["other_vegetation"]),
        "risk": float(safe["crop_spray_risk_per_crop_pixel"]),
        "safe_recall": float(safe["safe_weed_pixel_recall"]),
        "component_hit": float(components["component_hit_recall_any_overlap"]),
        "small_component_hit": float(
            small_components.get("component_hit_recall_any_overlap", 0.0)
        ),
        "coverage50": float(
            components["component_coverage_recall"]["at_least_50pct"]
        ),
        "center_within_radius": float(
            components["center_proxy"]["recall_within_equivalent_radius"]["1.0"]
        ),
        "perception_ms": float(runtime.get("perception_ms_per_image", 0.0)),
    }


def real_raster_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dataset, label in (("sugarbeets", "SugarBeets robot"), ("weedmap", "WeedMap UAV")):
        for scale in (100, 150, 200):
            rows.append(
                {
                    "dataset": dataset,
                    "label": label,
                    "scale": scale / 100.0,
                    **intervention_metrics(
                        REAL_RASTER_ROOT / f"{dataset}_scale{scale}.json"
                    ),
                }
            )
    return rows


def selected_intervention_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model, model_label in (
        ("control", "Global kontrol"),
        ("selected", "768 hedef adayı"),
    ):
        for evaluation, dataset_label in (
            ("sugarbeets_robot_holdout", "SugarBeets robot"),
            ("weedmap_uav_holdout", "WeedMap UAV"),
        ):
            rows.append(
                {
                    "model": model,
                    "model_label": model_label,
                    "evaluation": evaluation,
                    "dataset_label": dataset_label,
                    **intervention_metrics(
                        SMALL_INTERVENTION_ROOT / model / f"{evaluation}.json"
                    ),
                }
            )
    return rows


def real_domain_size_diagnostics() -> list[dict[str, Any]]:
    evaluations = (
        ("Sorghum final test", "sorghum_external_test.json"),
        ("SugarBeets robot", "sugarbeets_robot_holdout.json"),
        ("WeedMap UAV", "weedmap_uav_holdout.json"),
    )
    rows: list[dict[str, Any]] = []
    for label, filename in evaluations:
        payload = _json(INTERVENTION_ROOT / filename)["overall"]
        components = payload["modes"]["semantic_argmax"]["component_metrics"]
        total = int(components["all"]["semantic_component_proxies"])
        rows.append(
            {
                "label": label,
                "components": total,
                "sub_patch_share": int(
                    components["sub_patch_lt14px"]["semantic_component_proxies"]
                )
                / total,
                "large_share": int(
                    components["four_plus_patches_ge56px"][
                        "semantic_component_proxies"
                    ]
                )
                / total,
                "component_hit": float(
                    components["all"]["component_hit_recall_any_overlap"]
                ),
                "mean_iou": float(payload["semantic_segmentation"]["mean_iou"]),
            }
        )
    return rows


def benchmark_rows(path: Path) -> list[dict[str, Any]]:
    payload = _json(path)
    rows: list[dict[str, Any]] = []
    for run in payload["runs"]:
        row = {
            "candidate": run["candidate"],
            "source": float(run["source_validation"]["mean_iou"]),
            "source_risk": float(run["source_validation"]["crop_spray_risk"]),
            "source_safe_recall": float(
                run["source_validation"]["safe_weed_recall"]
            ),
        }
        for name, result in run["development"].items():
            row[name] = float(result["mean_iou"])
            row[f"{name}_risk"] = float(result["crop_spray_risk"])
            row[f"{name}_safe_recall"] = float(result["safe_weed_recall"])
        row["robust_min"] = min(
            value
            for key, value in row.items()
            if key == "source"
            or (
                not key.endswith(("_risk", "_safe_recall"))
                and key not in {"candidate", "robust_min"}
            )
        )
        rows.append(row)
    return rows


def domain_confirmation_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for seed, path in ((17, DOMAIN_RESULT), (29, DOMAIN_CONFIRM_RESULT)):
        payload = _json(path)
        by_frames = {
            int(run.get("target_train_frames", 0)): run for run in payload["runs"]
        }
        baseline, target = by_frames[0], by_frames[10]

        def value(run: Mapping[str, Any], name: str) -> float:
            if name == "source_validation":
                return float(run["source_validation"]["mean_iou"])
            return float(run["development"][name]["mean_iou"])

        metrics = (
            "source_validation",
            "sorghum_external_calibration",
            "cwfid_external_calibration",
            "sugarbeets_robot_holdout",
            "weedmap_uav_holdout",
        )
        diagnostics = {
            item["candidate"]: item
            for item in payload["selection"]["diagnostics"]
        }
        rows.append(
            {
                "seed": seed,
                **{
                    name: value(target, name) - value(baseline, name)
                    for name in metrics
                },
                "eligible": bool(diagnostics[target["candidate"]]["eligible"]),
                "selected": payload["selection"]["selected_candidate"]
                == target["candidate"],
            }
        )
    mean = {
        key: sum(float(row[key]) for row in rows) / len(rows)
        for key in (
            "source_validation",
            "sorghum_external_calibration",
            "cwfid_external_calibration",
            "sugarbeets_robot_holdout",
            "weedmap_uav_holdout",
        )
    }
    rows.append(
        {
            "seed": "ortalama",
            **mean,
            "eligible": all(bool(row["eligible"]) for row in rows),
            "selected": all(bool(row["selected"]) for row in rows),
        }
    )
    return rows


def small_target_confirmation_rows() -> list[dict[str, Any]]:
    """Paired seed deltas for the preselected 768 target-camera candidate."""
    confirm_config = yaml.safe_load(
        (PROJECT_ROOT / "configs/benchmark/small_object_canvas_confirm_semantic_eval_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    floors = {
        str(key): float(value)
        for key, value in confirm_config["selection"][
            "minimum_delta_vs_baseline"
        ].items()
    }
    specifications = (
        (
            17,
            SMALL_RESULT,
            "smallobj_control_512_e8_v1",
            "smallobj_canvas768_e8_v1",
        ),
        (
            43,
            SMALL_CONFIRM_RESULT,
            "smallobj_control_512_e8_seed43",
            "smallobj_canvas768_confirm_e8_v1",
        ),
    )

    def value(run: Mapping[str, Any], name: str) -> float:
        if name == "source_validation":
            return float(run["source_validation"]["mean_iou"])
        return float(run["development"][name]["mean_iou"])

    rows: list[dict[str, Any]] = []
    for seed, path, baseline_name, candidate_name in specifications:
        payload = _json(path)
        by_name = {str(run["candidate"]): run for run in payload["runs"]}
        baseline, candidate = by_name[baseline_name], by_name[candidate_name]
        deltas = {
            name: value(candidate, name) - value(baseline, name)
            for name in floors
        }
        failed = [name for name, floor in floors.items() if deltas[name] < floor]
        rows.append(
            {
                "seed": seed,
                **deltas,
                "eligible": not failed,
                "failed_gates": failed,
            }
        )
    rows.append(
        {
            "seed": "ortalama",
            **{
                name: sum(float(row[name]) for row in rows) / len(rows)
                for name in floors
            },
            "eligible": all(bool(row["eligible"]) for row in rows),
            "failed_gates": sorted(
                {gate for row in rows for gate in row["failed_gates"]}
            ),
        }
    )
    return rows


def row_prior_rows() -> list[dict[str, str]]:
    with (ROW_ROOT / "summary.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _line_chart(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    x_labels: Sequence[str],
    series: Sequence[tuple[str, Sequence[float], tuple[int, int, int]]],
    *,
    y_min: float | None = None,
    y_max: float | None = None,
) -> None:
    draw = ImageDraw.Draw(canvas)
    x1, y1, x2, y2 = box
    left, top, right, bottom = x1 + 90, y1 + 40, x2 - 30, y2 - 75
    values = [value for _, points, _ in series for value in points]
    low = min(values) if y_min is None else y_min
    high = max(values) if y_max is None else y_max
    margin = max(0.015, (high - low) * 0.12)
    low, high = max(0.0, low - margin), min(1.0, high + margin)
    if high <= low:
        high = low + 0.01
    for index in range(5):
        value = low + (high - low) * index / 4
        y = bottom - int((value - low) / (high - low) * (bottom - top))
        draw.line((left, y, right, y), fill=LINE, width=2)
        add_text(draw, (x1 + 8, y - 12), f"{value * 100:.0f}%", 18, fill=MUTED)
    spacing = (right - left) / max(1, len(x_labels) - 1)
    for index, label in enumerate(x_labels):
        x = int(left + spacing * index)
        add_text(draw, (x - 35, bottom + 16), label, 18, fill=MUTED, width=9)
    for name, points, color in series:
        coordinates = []
        for index, value in enumerate(points):
            x = int(left + spacing * index)
            y = bottom - int((value - low) / (high - low) * (bottom - top))
            coordinates.append((x, y))
        if len(coordinates) > 1:
            draw.line(coordinates, fill=color, width=6)
        for x, y in coordinates:
            draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=color, outline=WHITE, width=2)
    legend_x = left
    for name, _, color in series:
        draw.rounded_rectangle((legend_x, y1 + 4, legend_x + 30, y1 + 24), radius=5, fill=color)
        add_text(draw, (legend_x + 40, y1), name, 18, bold=True)
        legend_x += 40 + max(110, len(name) * 11)


def _bar_chart(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    labels: Sequence[str],
    values: Sequence[float],
    *,
    color: tuple[int, int, int] = GREEN,
) -> None:
    draw = ImageDraw.Draw(canvas)
    x1, y1, x2, y2 = box
    maximum = max(values) * 1.08
    width = (x2 - x1) / max(1, len(values))
    baseline = y2 - 75
    usable = baseline - y1 - 35
    for index, (label, value) in enumerate(zip(labels, values)):
        left = int(x1 + index * width + 16)
        right = int(x1 + (index + 1) * width - 16)
        top = baseline - int(value / maximum * usable)
        draw.rounded_rectangle((left, top, right, baseline), radius=10, fill=color)
        add_text(draw, (left + 6, top - 30), f"{value * 100:.1f}%", 18, bold=True)
        add_text(draw, (left + 2, baseline + 13), label, 16, fill=MUTED, width=max(8, int(width / 10)))


def _metric_card(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    label: str,
    value: str,
    note: str,
    fill: tuple[int, int, int],
) -> None:
    draw = ImageDraw.Draw(canvas)
    card(draw, box, fill=fill)
    x1, y1, x2, _ = box
    add_text(draw, (x1 + 24, y1 + 20), label, 22, bold=True, fill=MUTED, width=28)
    add_text(draw, (x1 + 24, y1 + 74), value, 45, bold=True, fill=INK)
    add_text(draw, (x1 + 24, y1 + 140), note, 20, fill=MUTED, width=max(20, int((x2 - x1) / 12)))


def build_pages() -> tuple[list[Image.Image], dict[str, Any]]:
    camera_names = (
        "resolution_256",
        "resolution_384",
        "reference_512",
        "resolution_768",
        "resolution_1024",
        "zoom_1p33",
        "zoom_1p67",
        "dim_no_led",
        "dim_led_energy30",
        "dim_led_energy60",
        "dim_led_energy120",
        "defocus_sigma1p5",
        "defocus_sigma3p0",
        "motion_blur_7px",
        "digital_input_256",
        "detail_loss_256_up512",
        "digital_upscale_1024",
    )
    camera = {name: camera_metrics(name) for name in camera_names}
    latency = {size: latency_metrics(size) for size in (256, 512, 768, 1024)}
    real_raster = real_raster_rows()
    component_bins = camera_component_bins("reference_512")
    real_size = real_domain_size_diagnostics()
    domain = benchmark_rows(DOMAIN_RESULT)
    domain_selection = _json(DOMAIN_RESULT)["selection"]
    small = benchmark_rows(SMALL_RESULT)
    small_selection = _json(SMALL_RESULT)["selection"]
    small_confirmation = small_target_confirmation_rows()
    small_intervention = selected_intervention_rows()
    confirmation = domain_confirmation_rows()
    confirmation_passed = bool(confirmation[-1]["selected"])
    row = row_prior_rows()
    n_pattern = re.compile(r"n(\d{3})")
    domain.sort(key=lambda item: int(n_pattern.search(item["candidate"]).group(1)))
    target_key = "sorghum_external_calibration"
    domain_selected = next(
        item
        for item in domain
        if item["candidate"] == domain_selection["selected_candidate"]
    )
    domain_baseline = next(
        item
        for item in domain
        if item["candidate"] == _json(DOMAIN_RESULT)["baseline_candidate"]
    )
    small_selected = next(
        item
        for item in small
        if item["candidate"] == small_selection["selected_candidate"]
    )
    small_baseline = next(
        item
        for item in small
        if item["candidate"] == _json(SMALL_RESULT)["baseline_candidate"]
    )
    small_target = next(
        item for item in small if item["candidate"] == "smallobj_canvas768_e8_v1"
    )
    small_target_confirmed = all(
        bool(item["eligible"])
        for item in small_confirmation
        if item["seed"] != "ortalama"
    )
    ref = camera["reference_512"]
    high = camera["resolution_1024"]

    pages: list[Image.Image] = []
    page = base_page(
        "Sonuç: önce piksel bütçesi, sonra hedef-domain veri",
        "Eşlenmiş kamera koşulları + eşit-bütçeli eğitim + crop-row prior",
    )
    _metric_card(page, (70, 205, 600, 435), "Native sentetik 512 → 1024", f"+{(high['miou'] - ref['miou']) * 100:.1f} puan", f"mIoU {ref['miou'] * 100:.1f}% → {high['miou'] * 100:.1f}%", LIGHT_GREEN)
    _metric_card(
        page,
        (695, 205, 1225, 435),
        "Dondurulmuş kuralla seçilen",
        f"{domain_selected[target_key] * 100:.1f}%",
        f"Sorghum mIoU; {domain_selection['selected_target_train_frames']} kare, seed29 "
        + ("teyit geçti" if confirmation_passed else "teyit geçmedi"),
        LIGHT_BLUE,
    )
    _metric_card(page, (1320, 205, 1850, 435), "Basit sıra prior", "küçük / koşullu", "Güçlü posterior prior reddedildi; guard yalnız riskli transferde anlamlı", LIGHT_ORANGE)
    bullet_list(
        page,
        [
            "Doğru anladın: en büyük iki eksen kamera/optik piksel bütçesi ve gerçek-benzer hedef-domain verisi.",
            "Focus/motion kaybı doğrudan ölçüldü; sabit güçlü ışık otomatik kazanç sağlamadı.",
            f"512→1024 dijital model rasterı +{(camera['digital_upscale_1024']['miou'] - ref['miou']) * 100:.1f} mIoU puan verdi; yalın model forward maliyeti {latency[1024]['mean_ms'] / latency[512]['mean_ms']:.1f}× oldu.",
            (
                "768 px hedef-kamera kolu iki-seed specialist kapısını geçti; global CWFID breadth kapısı nedeniyle genel model kontrol kaldı."
                if small_target_confirmed
                else "768 px hedef-kamera kolu iki-seed specialist kapısını geçmedi; genel model kontrol kaldı."
            ),
            "Sıra bilgisi bir emniyet veto katmanı olabilir; ana segmentasyon çözümü değildir.",
            "Sentetik dijital upscale kazancı gerçek holdout'ta tekrarlanmadı; kör inference upscale reddedildi ve gerçek kamera bench'i hâlâ zorunlu.",
        ],
        (100, 515),
        width=105,
        size=24,
        line_gap=12,
    )
    pages.append(page)

    page = base_page(
        "Gerçek holdout'ta yalnız model rasterını büyütmek",
        "Aynı native görüntü ve etiket grid'i; 1.5×/2× yalnız yazılımsal ölçekleme",
    )
    sugar_raster = [item for item in real_raster if item["dataset"] == "sugarbeets"]
    weedmap_raster = [item for item in real_raster if item["dataset"] == "weedmap"]
    _line_chart(
        page,
        (90, 170, 1830, 480),
        ("1.0×", "1.5×", "2.0×"),
        (
            ("SugarBeets mIoU", [item["miou"] for item in sugar_raster], GREEN),
            ("WeedMap mIoU", [item["miou"] for item in weedmap_raster], BLUE),
        ),
    )
    draw_table(
        page,
        (80, 505, 1840, 780),
        ("Alan", "Raster", "mIoU", "<14 px hit", "Crop risk", "Safe weed recall", "Perception ms"),
        [
            (
                item["label"],
                f"{item['scale']:.1f}×",
                pct(item["miou"]),
                pct(item["small_component_hit"]),
                pct(item["risk"]),
                pct(item["safe_recall"]),
                f"{item['perception_ms']:.1f}",
            )
            for item in real_raster
        ],
        (0.20, 0.10, 0.13, 0.16, 0.13, 0.16, 0.12),
        font_size=16,
        row_height=35,
    )
    bullet_list(
        page,
        [
            f"SugarBeets: 1× mIoU {sugar_raster[0]['miou'] * 100:.1f}%; 1.5× {sugar_raster[1]['miou'] * 100:.1f}%; 2× {sugar_raster[2]['miou'] * 100:.1f}%. Kör upscale crop riskini de yükseltti; reddedildi.",
            f"WeedMap mIoU yaklaşık düz kaldı; <14 px temas 1× %{weedmap_raster[0]['small_component_hit'] * 100:.2f} → 2× %{weedmap_raster[2]['small_component_hit'] * 100:.2f}, fakat mutlak başarı hâlâ çok düşük.",
            "Sonuç: gerçek görüntüde interpolasyon native optik ayrıntının veya 768'e göre eğitilmiş modelin yerini tutmuyor; model-raster değişimi train–inference uyumlu olmalı.",
        ],
        (105, 805),
        width=112,
        size=18,
        line_gap=3,
    )
    pages.append(page)

    page = base_page("Kamera çözünürlüğü ve optik zoom", "Aynı görülmemiş sentetik sahneler; model ve eşikler sabit")
    resolution_names = ("resolution_256", "resolution_384", "reference_512", "resolution_768", "resolution_1024")
    _line_chart(
        page,
        (80, 190, 1840, 625),
        ("256", "384", "512", "768", "1024"),
        (
            ("mIoU", [camera[name]["miou"] for name in resolution_names], GREEN),
            ("weed IoU", [camera[name]["weed"] for name in resolution_names], RED),
            ("crop IoU", [camera[name]["crop"] for name in resolution_names], BLUE),
        ),
    )
    draw_table(
        page,
        (110, 675, 1810, 940),
        ("Koşul", "mIoU", "Crop IoU", "Weed IoU", "Safe weed recall"),
        [
            (name.replace("resolution_", "").replace("reference_", ""), pct(camera[name]["miou"]), pct(camera[name]["crop"]), pct(camera[name]["weed"]), pct(camera[name]["safe_recall"]))
            for name in resolution_names
        ],
        (0.20, 0.20, 0.20, 0.20, 0.20),
        font_size=20,
        row_height=44,
    )
    pages.append(page)

    page = base_page(
        "Sensör detayı mı, model rasterı mı?",
        "Aynı 512 capture üzerinde deterministik resize; yeni sahne bilgisi eklenmez",
    )
    draw_table(
        page,
        (115, 235, 1805, 610),
        ("Koşul", "Capture detayı", "Model rasterı", "mIoU", "Weed IoU", "Core ms"),
        [
            ("512 referans", "512", "512", pct(camera["reference_512"]["miou"]), pct(camera["reference_512"]["weed"]), f"{latency[512]['mean_ms']:.2f}"),
            ("512 → 256", "256'ya düşürülmüş", "256", pct(camera["digital_input_256"]["miou"]), pct(camera["digital_input_256"]["weed"]), f"{latency[256]['mean_ms']:.2f}"),
            ("512 → 256 → 512", "256'ya düşürülmüş", "512", pct(camera["detail_loss_256_up512"]["miou"]), pct(camera["detail_loss_256_up512"]["weed"]), f"{latency[512]['mean_ms']:.2f}"),
            ("512 → 1024", "yeni detay yok", "1024", pct(camera["digital_upscale_1024"]["miou"]), pct(camera["digital_upscale_1024"]["weed"]), f"{latency[1024]['mean_ms']:.2f}"),
            ("Gerçek 1024 render", "native 1024", "1024", pct(camera["resolution_1024"]["miou"]), pct(camera["resolution_1024"]["weed"]), f"{latency[1024]['mean_ms']:.2f}"),
        ],
        (0.23, 0.20, 0.14, 0.14, 0.15, 0.14),
        font_size=17,
        row_height=52,
    )
    bullet_list(
        page,
        [
            "512→1024 yalnız interpolasyondur: kazanç varsa model raster/token bütçesinin etkisini gösterir, yeni optik detayın değil.",
            "Native 1024 ile interpolated 1024 farkı, sensör/GSD ile gerçekten kazanılan ayrıntının yaklaşık katkısıdır.",
            "256→512 kolu, daha büyük model girdisinin kaybolmuş bitki ayrıntısını geri getirip getiremeyeceğini test eder.",
            "Core latency, 30 warm-up + 100 tekrar AMP model forward'dır; preprocessing, tiling ve safety policy dahil değildir.",
        ],
        (140, 700),
        width=108,
        size=25,
        line_gap=15,
    )
    pages.append(page)

    page = base_page(
        "Darboğaz gerçekten nesne boyutu",
        "512 px referans holdout; DINOv2 patch boyutu 14 px",
    )
    _bar_chart(
        page,
        (100, 170, 1820, 500),
        [item["label"] for item in component_bins],
        [item["component_hit"] for item in component_bins],
        color=ORANGE,
    )
    draw_table(
        page,
        (260, 530, 1660, 690),
        ("GT weed proxy boyutu", "Proxy sayısı", "Herhangi temas", "Proxy içi pixel recall"),
        [
            (
                item["label"],
                str(item["components"]),
                pct(item["component_hit"]),
                pct(item["pixel_recall"]),
            )
            for item in component_bins
        ],
        (0.28, 0.20, 0.24, 0.28),
        font_size=19,
        row_height=32,
    )
    bullet_list(
        page,
        [
            "<14 px otlarda model neredeyse hiç temas kuramıyor; 28 px üstünde davranış keskin biçimde iyileşiyor.",
            "Bunlar bağlı semantik maske parçalarıdır, botanik instance değildir; ≥28 px grubunda yalnız 26 proxy vardır.",
            "≈28 px eşdeğer çap şimdilik kamera/GSD hedefi için güçlü bir başlangıç hipotezidir; gerçek kamera bench'inde doğrulanmalıdır.",
        ],
        (120, 720),
        width=112,
        size=18,
        line_gap=3,
    )
    pages.append(page)

    page = base_page(
        "28 px hedefini kamera şartına çevirme",
        "Ön tasarım hesabı; kesin değer gerçek bench ile seçilecek",
    )
    draw = ImageDraw.Draw(page)
    add_text(
        draw,
        (150, 220),
        "GSD_max (mm/pixel) = ölçmek istediğimiz en küçük weed çapı (mm) / 28",
        31,
        bold=True,
        fill=INK,
    )
    draw_table(
        page,
        (190, 330, 1730, 650),
        ("En küçük weed eşdeğer çapı", "En büyük GSD", "2048 px yatay kapsama", "4096 px yatay kapsama"),
        [
            (f"{diameter} mm", f"{diameter / 28:.2f} mm/px", f"{diameter / 28 * 2048 / 1000:.2f} m", f"{diameter / 28 * 4096 / 1000:.2f} m")
            for diameter in (10, 20, 30, 40)
        ],
        (0.28, 0.22, 0.25, 0.25),
        font_size=20,
        row_height=52,
    )
    bullet_list(
        page,
        [
            "Tablo örnektir: hedeflediğimiz fiziksel en küçük weed boyutu verilmeden kamera/lens kesin seçilemez.",
            "Yatay saha genişliği = 2 × çalışma yüksekliği × tan(yatay FOV/2); GSD = saha genişliği / yatay pixel.",
            "4096 px sensörü modele tek seferde 512'ye küçültmek avantajı siler; native tile/crop akışı gerçek pixelleri korumalıdır.",
            "Focus, kısa shutter ve yeterli ışık bu teorik GSD'nin sahada kullanılabilir ayrıntıya dönüşmesi için birlikte ayarlanır.",
        ],
        (130, 745),
        width=112,
        size=23,
        line_gap=12,
    )
    pages.append(page)

    page = base_page(
        "İyi ve kötü alanları ayıran ilk sebep",
        "Kabul edilmiş aynı model; bağlı GT weed semantik-proxy dağılımı",
    )
    draw_table(
        page,
        (120, 220, 1800, 455),
        ("Alan", "Weed proxy", "<14 px payı", "≥56 px payı", "Herhangi temas", "mIoU"),
        [
            (
                item["label"],
                str(item["components"]),
                pct(item["sub_patch_share"]),
                pct(item["large_share"]),
                pct(item["component_hit"]),
                pct(item["mean_iou"]),
            )
            for item in real_size
        ],
        (0.25, 0.13, 0.15, 0.15, 0.17, 0.15),
        font_size=19,
        row_height=52,
    )
    _line_chart(
        page,
        (120, 500, 1800, 770),
        [item["label"].split()[0] for item in real_size],
        (
            ("<14 px weed payı", [item["sub_patch_share"] for item in real_size], RED),
            ("component hit", [item["component_hit"] for item in real_size], GREEN),
        ),
        y_min=0.0,
        y_max=1.0,
    )
    bullet_list(
        page,
        [
            "Sorghum'un iyi görünmesinde weed'lerin neredeyse tamamının büyük olması; WeedMap'in zorluğunda UAV/GSD nedeniyle çoğunun patch-altı kalması başat etkidir.",
            "Bu nedenselliği tek başına kanıtlamaz: Sorghum hedef verisi görülmüştür; tür, kamera ve saha domain farkları da eşzamanlı değişir.",
        ],
        (120, 805),
        width=112,
        size=18,
        line_gap=3,
    )
    pages.append(page)

    for title, gallery, bullets in (
        (
            "Aynı sahnede çözünürlük: görsel kanıt",
            CAMERA_ROOT / "gallery/01_resolution_same_scene.jpg",
            ("Üst sıra model tahmini, alt sıra gerçek etiket.", "1024 px kazancı yalnız interpolasyon değil; sahne gerçekten daha yüksek rasterda render edildi."),
        ),
        (
            "Focus ve hareket: küçük ot sinyali siliniyor",
            CAMERA_ROOT / "gallery/03_focus_motion_same_scene.jpg",
            (f"Defocus σ=3: mIoU {camera['defocus_sigma3p0']['miou'] * 100:.1f}% (referans {ref['miou'] * 100:.1f}%).", f"7 px motion blur: mIoU {camera['motion_blur_7px']['miou'] * 100:.1f}%."),
        ),
        (
            "Düşük ışıkta kamera ışığı sweep'i",
            CAMERA_ROOT / "gallery/04_low_light_camera_light_same_scene.jpg",
            (
                "mIoU sweep — off "
                f"{camera['dim_no_led']['miou'] * 100:.1f}%, E30 {camera['dim_led_energy30']['miou'] * 100:.1f}%, "
                f"E60 {camera['dim_led_energy60']['miou'] * 100:.1f}%, E120 {camera['dim_led_energy120']['miou'] * 100:.1f}%.",
                "Simülatör enerji değeri lux/watt değildir; ışık pozlama ve mesafeyle birlikte kalibre edilmelidir.",
            ),
        ),
        (
            "Aynı capture üzerinde model rasterı",
            CAMERA_ROOT / "gallery/05_model_raster_same_capture.jpg",
            (
                "256 ve 1024 kolları aynı 512 capture'ın dijital resize'ıdır; yeni optik ayrıntı içermez.",
                f"512 referans {camera['reference_512']['miou'] * 100:.1f}%; dijital 1024 {camera['digital_upscale_1024']['miou'] * 100:.1f}%; native 1024 {camera['resolution_1024']['miou'] * 100:.1f}% mIoU.",
            ),
        ),
    ):
        page = base_page(title, "Tek örnek açıklama içindir; sayısal sonuç 16 eşlenmiş kareden gelir")
        paste_contain(page, gallery, (95, 195, 1825, 830), background=BG)
        bullet_list(page, bullets, (130, 850), width=110, size=22, line_gap=8)
        pages.append(page)

    page = base_page("Kaç hedef-domain karesi işe yarıyor?", "0/10/25/50/100/202 benzersiz Sorghum train karesi; hesap bütçesi eşit")
    n_labels = [str(int(n_pattern.search(item["candidate"]).group(1))) for item in domain]
    _line_chart(
        page,
        (80, 190, 1840, 700),
        n_labels,
        (
            ("Sorghum calibration mIoU", [item[target_key] for item in domain], GREEN),
            ("Genel kaynak validation mIoU", [item["source"] for item in domain], BLUE),
        ),
    )
    bullet_list(
        page,
        [
            "Alt kümeler RGB-thumbnail çeşitlilik sırasıyla strict-nested seçildi; calibration/test seçime girmedi.",
            f"Dondurulmuş target-ağırlıklı/breadth-gated seçim: {domain_selection['selected_candidate']}.",
            "Sorghum eğrisi aynı dataset/tek saha içidir; CWFID, SugarBeets ve WeedMap dağılım çeşitliliği ekler ama her biri yalnız bir capture group'tur.",
            "Eğri seed17 ekranıdır; seçilen 10-kare noktası seed29 kontrol+aday çiftiyle ayrıca teyit edilir.",
        ],
        (120, 755),
        width=112,
        size=23,
        line_gap=10,
    )
    pages.append(page)

    page = base_page(
        "Domain adaptation: aynı holdout görüntülerinde",
        "GT weed oranı kuantilleri; model çıktısına göre örnek seçilmedi",
    )
    paste_contain(
        page,
        OUTPUT / "gallery/domain_sorghum_control_vs_selected.jpg",
        (75, 185, 1845, 850),
        background=BG,
    )
    bullet_list(
        page,
        [
            f"Control Sorghum mIoU {domain_baseline[target_key] * 100:.1f}%; seçilen {domain_selected[target_key] * 100:.1f}%.",
            "Frozen-safe pixel — crop risk "
            f"{domain_baseline[f'{target_key}_risk'] * 100:.2f}% → {domain_selected[f'{target_key}_risk'] * 100:.2f}%; "
            f"weed recall {domain_baseline[f'{target_key}_safe_recall'] * 100:.1f}% → {domain_selected[f'{target_key}_safe_recall'] * 100:.1f}%.",
            "Bu calibration bölümüdür; final test selection için açılmadı.",
        ],
        (120, 875),
        width=112,
        size=22,
        line_gap=8,
    )
    pages.append(page)

    page = base_page(
        "10 hedef karesi: iki seed paired teyit",
        "Her seed kendi 0-kare kontrolünden çıkarılmış mIoU farkı",
    )
    draw_table(
        page,
        (95, 250, 1825, 560),
        ("Seed", "Source Δ", "Sorghum Δ", "CWFID Δ", "SugarBeets Δ", "WeedMap Δ", "Gate"),
        [
            (
                str(item["seed"]),
                f"{item['source_validation'] * 100:+.2f}",
                f"{item['sorghum_external_calibration'] * 100:+.2f}",
                f"{item['cwfid_external_calibration'] * 100:+.2f}",
                f"{item['sugarbeets_robot_holdout'] * 100:+.2f}",
                f"{item['weedmap_uav_holdout'] * 100:+.2f}",
                "geçti" if item["eligible"] else "kaldı",
            )
            for item in confirmation
        ],
        (0.10, 0.14, 0.16, 0.14, 0.17, 0.14, 0.15),
        font_size=20,
        row_height=55,
    )
    bullet_list(
        page,
        [
            "Seed17 seçimi dış sonuçlara bakılmadan donduruldu; seed29 yalnız kontrol+10-kare teyididir.",
            "Sonuç: "
            + (
                "10-kare kol iki seedde de dondurulmuş kapıyı geçti."
                if confirmation_passed
                else "10-kare kol iki seedde birden kapıyı geçmedi; nihai reçete reddedildi."
            ),
            "İki seed eğitim varyansını tamamen karakterize etmez; fakat tek-seed rastlantısına karşı paired kontrol sağlar.",
        ],
        (125, 665),
        width=112,
        size=26,
        line_gap=20,
    )
    pages.append(page)

    page = base_page(
        "Küçük-ot eğitim A/B",
        f"Global gate: {small_selected['candidate']} | hedef-kamera teyit adayı: canvas768",
    )
    labels = [
        item["candidate"]
        .replace("smallobj_", "")
        .replace("_512_e8_v1", "")
        .replace("_e8_v1", "")
        for item in small
    ]
    _bar_chart(page, (90, 210, 1830, 680), labels, [item["robust_min"] for item in small])
    draw_table(
        page,
        (90, 715, 1830, 945),
        ("Kol", "Source", "CWFID", "Sorghum", "SugarBeets", "WeedMap", "Robust min"),
        [
            (
                label,
                pct(item["source"]),
                pct(item["cwfid_external_calibration"]),
                pct(item["sorghum_external_calibration"]),
                pct(item["sugarbeets_robot_holdout"]),
                pct(item["weedmap_uav_holdout"]),
                pct(item["robust_min"]),
            )
            for label, item in zip(labels, small)
        ],
        (0.22, 0.13, 0.13, 0.13, 0.13, 0.13, 0.13),
        font_size=16,
        row_height=38,
    )
    pages.append(page)

    page = base_page(
        "768 px hedef-kamera adayı: iki seed teyit",
        "Seed17 keşif + seed43 paired confirmation; global CWFID kapısı ayrı",
    )
    draw_table(
        page,
        (90, 245, 1830, 585),
        ("Seed", "Source Δ", "CWFID Δ", "Sorghum Δ", "SugarBeets Δ", "WeedMap Δ", "Target gate"),
        [
            (
                str(item["seed"]),
                f"{item['source_validation'] * 100:+.2f}",
                f"{item['cwfid_external_calibration'] * 100:+.2f}",
                f"{item['sorghum_external_calibration'] * 100:+.2f}",
                f"{item['sugarbeets_robot_holdout'] * 100:+.2f}",
                f"{item['weedmap_uav_holdout'] * 100:+.2f}",
                "geçti" if item["eligible"] else "kaldı",
            )
            for item in small_confirmation
        ],
        (0.10, 0.13, 0.13, 0.14, 0.17, 0.14, 0.19),
        font_size=19,
        row_height=58,
    )
    bullet_list(
        page,
        [
            "Hedef-specialist kapısı sonuçtan önce seed43 için donduruldu: SugarBeets ≥+5 puan; source ≥−1,5, Sorghum ≥−2, WeedMap ≥−1, CWFID ≥−6 puan.",
            (
                "768 px kol iki seedde de hedef-specialist kapısını geçti."
                if small_target_confirmed
                else "768 px kol iki seedde birden hedef-specialist kapısını geçmedi; koşullu kabul yok."
            ),
            "Global generalist kararı değişmez: seed17'de CWFID −4,18 puan olduğu için daha sıkı −2 puan breadth kapısı kaldı.",
            "Bu ayrım tek datasete overfit olmayı önlerken hedef robot kamerasında yararlı specialist seçeneğini görünür tutar.",
        ],
        (120, 680),
        width=112,
        size=24,
        line_gap=16,
    )
    pages.append(page)

    page = base_page(
        "768 hedef adayı: müdahale açısından",
        "Dondurulmuş safety policy; semantik bileşenler botanik instance değildir",
    )
    draw_table(
        page,
        (75, 235, 1845, 625),
        ("Alan / model", "mIoU", "Crop risk", "Spray recall", "<14 px hit", "Merkez ≤1 yarıçap", "≥%50 coverage"),
        [
            (
                f"{item['dataset_label']} / {item['model_label']}",
                pct(item["miou"]),
                pct(item["risk"]),
                pct(item["safe_recall"]),
                pct(item["small_component_hit"]),
                pct(item["center_within_radius"]),
                pct(item["coverage50"]),
            )
            for item in small_intervention
        ],
        (0.25, 0.11, 0.13, 0.13, 0.12, 0.14, 0.12),
        font_size=17,
        row_height=56,
    )
    bullet_list(
        page,
        [
            "SugarBeets 768: crop risk %4,41→%1,45; spray recall %4,15→%9,72; tüm weed hit %4,92→%15,28. Hedef robotta belirgin yarar.",
            "WeedMap 768: spray recall %6,29→%3,24 ve <14 px hit %0,38→%0,04. Specialist UAV/genel alana route edilmemeli; kontrol fallback kalmalı.",
            "İlaçlama: crop riski + güvenli weed-pixel recall. Mekanik: component hit + merkez ≤1 yarıçap. Lazer/raster: ≥%50 güvenli coverage.",
            "Merkez/coverage bağlı semantik maske proxy'sidir; kök/meristem, mm kalibrasyonu, actuator ve kill/crop-injury sonucu değildir.",
            f"Global seçim: {small_selection['selected_candidate']}; bu sayfa seed17 kontrol–canvas768 tanısıdır.",
        ],
        (115, 685),
        width=112,
        size=20,
        line_gap=7,
    )
    pages.append(page)

    for title, gallery_name, metric_key in (
        (
            "Küçük-ot A/B: unseen SugarBeets robot",
            "small_sugarbeets_control_vs_selected.jpg",
            "sugarbeets_robot_holdout",
        ),
        (
            "Küçük-ot A/B: unseen WeedMap UAV",
            "small_weedmap_control_vs_selected.jpg",
            "weedmap_uav_holdout",
        ),
    ):
        page = base_page(
            title,
            "GT weed oranı kuantilleri; model çıktısına göre örnek seçilmedi",
        )
        paste_contain(
            page,
            OUTPUT / f"gallery/{gallery_name}",
            (75, 185, 1845, 850),
            background=BG,
        )
        bullet_list(
            page,
            [
                f"Control mIoU {small_baseline[metric_key] * 100:.1f}%; 768 hedef adayı {small_target[metric_key] * 100:.1f}%.",
                "Frozen-safe pixel — crop risk "
                f"{small_baseline[f'{metric_key}_risk'] * 100:.2f}% → {small_target[f'{metric_key}_risk'] * 100:.2f}%; "
                f"weed recall {small_baseline[f'{metric_key}_safe_recall'] * 100:.1f}% → {small_target[f'{metric_key}_safe_recall'] * 100:.1f}%.",
                "Yeşil=crop, kırmızı=weed; sayısal karar tüm holdout üzerinden verildi.",
            ],
            (120, 875),
            width=112,
            size=22,
            line_gap=8,
        )
        pages.append(page)

    page = base_page("Crop-row prior: nerede işe yarıyor?", "Practical=model crop olasılığı; oracle=GT-geometri tavanı")
    selected_rows = [
        item
        for item in row
        if item["mode"] in {"baseline", "practical_guard", "oracle_guard", "practical_0p35", "oracle_0p35"}
    ]
    compact = []
    for item in selected_rows:
        compact.append(
            (
                item["evaluation"].replace("_external_calibration", "").replace("_robot_holdout", "").replace("synthetic_v11_unseen_rows", "synthetic V11"),
                item["mode"],
                pct(float(item["mean_iou"])),
                pct(float(item["crop_spray_risk"])),
                pct(float(item["safe_weed_pixel_recall"])),
            )
        )
    draw_table(page, (80, 205, 1840, 795), ("Alan", "Prior modu", "mIoU", "Crop risk", "Safe weed recall"), compact, (0.25, 0.25, 0.16, 0.17, 0.17), font_size=17, row_height=35)
    bullet_list(
        page,
        [
            "0.35 posterior prior yalnız çok küçük mIoU değişimi verdi; 0.65 her alanda kötüleşti.",
            "Row guard yeni aksiyon yaratmaz; riskli SugarBeets transferinde crop riskini azaltırken weed recall'dan ödün verdi.",
            "In-row weed bulunduğu için 'sıra içi=crop' kuralı mutlak uygulanamaz. RTK/planter çizgisi veya temporal fit pratik tahminden daha değerlidir.",
        ],
        (110, 825),
        width=112,
        size=21,
        line_gap=5,
    )
    pages.append(page)

    page = base_page(
        "Sıra bilgisi ne yapıyor?",
        "SugarBeets unseen robot holdout; yeşil=crop, kırmızı=weed",
    )
    paste_contain(
        page,
        ROW_ROOT / "gallery/sugarbeets_robot_holdout/01.jpg",
        (80, 245, 1840, 685),
        background=BG,
    )
    bullet_list(
        page,
        [
            "Practical prior yalnız modelin crop olasılığından sıra çıkarır; hatalı crop tahmini sıra fitini de bozabilir.",
            "Oracle panel GT'den yalnız geometri aldığı için ulaşılabilir performans değil, prior'ın teorik tavanıdır.",
            "En güvenli kullanım: sıra dışındaki şüpheli crop/weed aksiyonlarını ölçülü biçimde veto etmek; sıra içini otomatik crop saymamak.",
        ],
        (120, 760),
        width=112,
        size=25,
        line_gap=14,
    )
    pages.append(page)

    page = base_page(
        "Dış kanıt aynı yönü gösteriyor",
        "Bağlam sağlar; bizim eşlenmiş A/B sonuçlarımızın yerine geçmez",
    )
    bullet_list(
        page,
        [
            "Carbon Robotics ürün bilgisi: 42 yüksek çözünürlüklü kamera + 9 yüksek yoğunluklu LED bar. Bu bir üretici beyanıdır; bizim kamera spesifikasyonumuzu belirlemez.",
            "Milioto, Lottes & Stachniss (ICRA 2018): RGB crop/weed sistemi görülmemiş tarlaya az miktarda veriyle yeniden eğitilebildi.",
            "Sa ve ark. (WeedMap, 2018): sınırlı GSD ve yüksek kaliteli görüntüyü küçültmek weed haritalamada temel sorunlar arasında.",
            "Saha LaserWeeder çalışması (2025): yüksek çözünürlüklü görüntü ve küçük/erken weed meristeminin hedeflenmesi pratik sistemin parçası.",
        ],
        (120, 235),
        width=108,
        size=28,
        line_gap=25,
    )
    add_text(
        ImageDraw.Draw(page),
        (125, 900),
        "Tam bağlantılar DETAYLI_SONUCLAR.md içindedir.",
        21,
        bold=True,
        fill=MUTED,
    )
    pages.append(page)

    page = base_page("Önerilen saha sırası", "En basit etkili çözüm önce")
    bullet_list(
        page,
        [
            "1. Kamera bench: gerçek çalışma yüksekliği/FOV'da GSD, focus, shutter ve hareket testi. Temsilî küçük weed için ≈28 px başlangıç hedefi native detail/tile ile sınansın; kör inference upscale kullanılmasın.",
            "2. Sabit exposure + kısa shutter + yeterli ışık; kamera ışığı lux/mesafe/pozlama ile kalibre edilmeden seçilmesin.",
            "3. Generalist kontrol fallback kalsın; canvas768 yalnız doğrulanmış hedef robot kamera profilinde route edilsin. Her yeni tarla/kameradan az etiketli kareyle domain adaptation yapılsın.",
            "4. Crop-row bilgisi modelin yerine değil, riskli aksiyonları veto eden opsiyonel safety prior olarak kullanılsın; in-row weed kaybı ölçülsün.",
            "5. Nihai kabul gerçek, yeni tarla ve robot hızında mm-kalibre actuator testiyle yapılmalı; sentetik tanı sayısı saha garantisi değildir.",
        ],
        (115, 230),
        width=108,
        size=27,
        line_gap=23,
    )
    pages.append(page)
    return pages, {
        "camera": camera,
        "latency": latency,
        "real_raster": real_raster,
        "component_bins": component_bins,
        "real_size": real_size,
        "domain": domain,
        "domain_selection": domain_selection,
        "domain_confirmation": confirmation,
        "small": small,
        "small_selection": small_selection,
        "small_confirmation": small_confirmation,
        "small_intervention": small_intervention,
        "row": row,
        "small_best": small_selected,
        "small_target": small_target,
        "small_target_confirmed": small_target_confirmed,
    }


def write_markdown(data: Mapping[str, Any], destination: Path) -> None:
    camera = data["camera"]
    latency = data["latency"]
    real_raster = data["real_raster"]
    component_bins = data["component_bins"]
    real_size = data["real_size"]
    domain = data["domain"]
    domain_selection = data["domain_selection"]
    confirmation = data["domain_confirmation"]
    small = data["small"]
    small_selection = data["small_selection"]
    small_confirmation = data["small_confirmation"]
    small_intervention = data["small_intervention"]
    small_target = data["small_target"]
    small_target_confirmed = bool(data["small_target_confirmed"])
    row = data["row"]
    domain_selected = next(
        item
        for item in domain
        if item["candidate"] == domain_selection["selected_candidate"]
    )
    small_selected = next(
        item
        for item in small
        if item["candidate"] == small_selection["selected_candidate"]
    )
    small_baseline = next(
        item
        for item in small
        if item["candidate"] == _json(SMALL_RESULT)["baseline_candidate"]
    )
    lines = [
        "# Kamera, domain adaptation ve küçük-ot deneyleri V1",
        "",
        "## Kısa karar",
        "",
        "En büyük iki etken doğrulandı: (1) sahnede bitkinin kaç gerçek piksel kapladığı ve focus/motion kalitesi, (2) hedef koşula benzer gerçek veri görülmesi. Crop-row prior yardımcı bir safety katmanıdır; ana çözüm değildir.",
        "",
        "Global generalist küçük-ot gate'i kontrolü korudu. Canvas768 iki seedde hedef-SugarBeets specialist kapısını geçti (ortalama +0,1301 mIoU), fakat ortalama CWFID farkı −0,0442 olduğu için yalnız hedef robot kamera koşuluna route edilmelidir. Gerçek holdout'ta kör 1,5×/2× inference upscale reddedildi.",
        "",
        "## Kamera/optik",
        "",
        "| Koşul | mIoU | Crop IoU | Weed IoU | Safe weed recall |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, values in camera.items():
        lines.append(f"| {name} | {values['miou']:.6f} | {values['crop']:.6f} | {values['weed']:.6f} | {values['safe_recall']:.6f} |")
    lines += [
        "",
        "Bu 8 görülmemiş sentetik geometri × 2 karelik eşlenmiş tanı setidir. 1024/768 koşulları gerçek yeniden renderdır; interpolation değildir. Işık enerjisi simulator kontrolüdür, ölçülmüş lux/watt değildir.",
        "",
        "### Sensör detayı ve model rasterını ayırma",
        "",
        "| Girdi | Model rasterı | mIoU | Weed IoU | AMP core latency |",
        "|---|---:|---:|---:|---:|",
        f"| 512 referans | 512 | {camera['reference_512']['miou']:.6f} | {camera['reference_512']['weed']:.6f} | {latency[512]['mean_ms']:.2f} ms |",
        f"| 512→256 | 256 | {camera['digital_input_256']['miou']:.6f} | {camera['digital_input_256']['weed']:.6f} | {latency[256]['mean_ms']:.2f} ms |",
        f"| 512→256→512 | 512 | {camera['detail_loss_256_up512']['miou']:.6f} | {camera['detail_loss_256_up512']['weed']:.6f} | {latency[512]['mean_ms']:.2f} ms |",
        f"| 512→1024 (yeni detay yok) | 1024 | {camera['digital_upscale_1024']['miou']:.6f} | {camera['digital_upscale_1024']['weed']:.6f} | {latency[1024]['mean_ms']:.2f} ms |",
        f"| Native 1024 | 1024 | {camera['resolution_1024']['miou']:.6f} | {camera['resolution_1024']['weed']:.6f} | {latency[1024]['mean_ms']:.2f} ms |",
        "",
        f"Dijital 512→1024 kolu yeni optik bilgi eklemeden `{(camera['digital_upscale_1024']['miou'] - camera['reference_512']['miou']) * 100:.2f}` mIoU puan kazandı; native 1024 ek olarak `{(camera['resolution_1024']['miou'] - camera['digital_upscale_1024']['miou']) * 100:.2f}` puan verdi. Bu temiz sentetik holdout'ta model raster/token darboğazı baskındır. 1024 core forward 512'ye göre `{latency[1024]['mean_ms'] / latency[512]['mean_ms']:.2f}×` maliyetlidir. Latency 30 warm-up + 100 tekrarlı yalın model forward'dır; preprocessing, tiling ve safety policy dahil değildir.",
        "",
        "### Gerçek holdout yazılımsal raster A/B",
        "",
        "| Alan | Raster | mIoU | <14 px component hit | Crop risk | Safe weed recall | Perception ms/image |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in real_raster:
        lines.append(
            f"| {item['label']} | {item['scale']:.1f}× | {item['miou']:.6f} | {item['small_component_hit']:.6f} | {item['risk']:.6f} | {item['safe_recall']:.6f} | {item['perception_ms']:.2f} |"
        )
    lines += [
        "",
        "Bu kol aynı gerçek capture'ı yalnız yazılımla büyütür; yeni optik bilgi eklemez. Tahmin aynı native etiket grid'ine geri alınır ve dondurulmuş safety policy yeniden ayarlanmaz. SugarBeets'te 1,5×/2× mIoU ciddi düştü ve crop riski yükseldi; WeedMap mIoU yaklaşık sabit kalırken <14 px temas mutlak olarak %0,24'ün altında kaldı. Kör inference upscale reddedildi; raster değişimi native detay veya train–inference uyumuyla birlikte tasarlanmalıdır.",
        "",
        "### Nesne boyutu darboğazı",
        "",
        "| Weed semantik-proxy boyutu | Proxy sayısı | Herhangi temas | Proxy içi pixel recall |",
        "|---|---:|---:|---:|",
    ]
    for item in component_bins:
        lines.append(
            f"| {item['label']} | {item['components']} | {item['component_hit']:.6f} | {item['pixel_recall']:.6f} |"
        )
    lines += [
        "",
        "Boyut, bağlı GT semantik bileşen alanından hesaplanan eşdeğer daire çapıdır; botanik instance veya bounding-box boyutu değildir. 28 px üstündeki güçlü sonuç yalnız 26 proxy'ye dayanır. Yaklaşık 28 px kamera/GSD hedefi gerçek kamera bench'inde teyit edilmesi gereken bir başlangıç hipotezidir.",
        "",
        "### Kamera ön-tasarım hesabı",
        "",
        "Başlangıç formülü `GSD_max (mm/pixel) = hedef en küçük weed eşdeğer çapı (mm) / 28` şeklindedir. Örneğin 20 mm weed için yaklaşık 0,71 mm/pixel gerekir; bu 2048 yatay pixelde yaklaşık 1,46 m, 4096 pixelde 2,93 m yatay kapsama karşılık gelir. Bunlar sentetik tanıdan türetilmiş ön-tasarım sayılarıdır; gerçek sensör/lens/focus/motion bench'iyle doğrulanmalıdır. Native çözünürlüğü modele girmeden küçültmek fiziksel kamera avantajını silebilir.",
        "",
        "### Gerçek alanlarda boyut dağılımı",
        "",
        "| Alan | Weed proxy | <14 px payı | ≥56 px payı | Herhangi temas | mIoU |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in real_size:
        lines.append(
            f"| {item['label']} | {item['components']} | {item['sub_patch_share']:.6f} | {item['large_share']:.6f} | {item['component_hit']:.6f} | {item['mean_iou']:.6f} |"
        )
    lines += [
        "",
        "Boyut dağılımı performansla güçlü biçimde hizalanır; fakat domainler arasında tür, kamera, GSD ve hedef-veri exposure'ı da birlikte değiştiği için bu tablo tek başına nedensel ablation değildir.",
        "",
        "## Domain-adaptation eğrisi",
        "",
        "| Kol | Source mIoU | Sorghum calibration mIoU | Robust min |",
        "|---|---:|---:|---:|",
    ]
    for item in domain:
        lines.append(f"| {item['candidate']} | {item['source']:.6f} | {item['sorghum_external_calibration']:.6f} | {item['robust_min']:.6f} |")
    lines += [
        "",
        f"Dondurulmuş seçim kuralı: `{domain_selection['selected_candidate']}` ({domain_selection['selected_target_train_frames']} hedef karesi). Sorghum %45, SugarBeets %20, source validation %15, CWFID %10 ve WeedMap %10 ağırlıklıdır; breadth regresyonları hard-gate edilir ve 0,005 skor toleransında daha az veri seçilir.",
        "",
        f"Seçilen kolun Sorghum frozen-safe crop risk / weed recall değerleri `{domain_selected['sorghum_external_calibration_risk']:.6f} / {domain_selected['sorghum_external_calibration_safe_recall']:.6f}`. Bunlar source-frozen eşiklerdir; target tuning yapılmadı.",
        "",
        "Tüm kollar aynı seed, epoch, samples/epoch ve optimizer bütçesini kullanır. Hedef alt kümeler strict-nested ve yalnız resmi train RGB'lerinden seçildi. Evaluation resmi external_calibration'dır; external_test açılmadı.",
        "",
        "### 10-kare seed29 paired confirmation",
        "",
        "| Seed | Source Δ | Sorghum Δ | CWFID Δ | SugarBeets Δ | WeedMap Δ | Gate |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in confirmation:
        lines.append(
            f"| {item['seed']} | {item['source_validation']:+.6f} | {item['sorghum_external_calibration']:+.6f} | {item['cwfid_external_calibration']:+.6f} | {item['sugarbeets_robot_holdout']:+.6f} | {item['weedmap_uav_holdout']:+.6f} | {'geçti' if item['eligible'] else 'kaldı'} |"
        )
    lines += [
        "",
        "## Küçük-ot eğitim A/B",
        "",
        "| Kol | Source | CWFID | Sorghum | SugarBeets | WeedMap | Robust min |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in small:
        lines.append(f"| {item['candidate']} | {item['source']:.6f} | {item['cwfid_external_calibration']:.6f} | {item['sorghum_external_calibration']:.6f} | {item['sugarbeets_robot_holdout']:.6f} | {item['weedmap_uav_holdout']:.6f} | {item['robust_min']:.6f} |")
    lines += [
        "",
        f"Dondurulmuş global küçük-ot seçim kuralı: `{small_selection['selected_candidate']}`. SugarBeets ve WeedMap küçük-nesne tanısı toplam %50, diğer gerçek alanlar %50 ağırlık alır; tümünde sıkı non-inferiority kapıları vardır.",
        "",
        f"Global gate kontrolü korudu. Buna rağmen hedef-kamera adayı canvas768, seed17 SugarBeets mIoU'yu `{small_baseline['sugarbeets_robot_holdout']:.6f}` → `{small_target['sugarbeets_robot_holdout']:.6f}` yükseltti; CWFID `{small_baseline['cwfid_external_calibration']:.6f}` → `{small_target['cwfid_external_calibration']:.6f}` geriledi. "
        + (
            "İkinci seed hedef-specialist kapısını da geçti."
            if small_target_confirmed
            else "İkinci seed hedef-specialist kapısını geçmedi; koşullu kabul verilmedi."
        ),
        "",
        "Replay yalnız train split'inden 4–28 px semantik weed bileşeni merkezli 512×512 kayıplardan oluşturuldu. Bunlar botanik instance değildir.",
        "",
        "### 768 hedef-kamera adayı — paired seed teyidi",
        "",
        "| Seed | Source Δ | CWFID Δ | Sorghum Δ | SugarBeets Δ | WeedMap Δ | Target gate |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in small_confirmation:
        lines.append(
            f"| {item['seed']} | {item['source_validation']:+.6f} | {item['cwfid_external_calibration']:+.6f} | {item['sorghum_external_calibration']:+.6f} | {item['sugarbeets_robot_holdout']:+.6f} | {item['weedmap_uav_holdout']:+.6f} | {'geçti' if item['eligible'] else 'kaldı'} |"
        )
    lines += [
        "",
        "Hedef-specialist kapısı seed43 sonucu görülmeden donduruldu: SugarBeets en az +0,05; source −0,015, Sorghum −0,02, WeedMap −0,01 ve CWFID −0,06 altına düşmeyecek. Bu geçiş global CWFID −0,02 breadth kapısını geçersiz kılmaz.",
        "",
        "### Müdahale-odaklı kontrol / 768 hedef adayı kıyası",
        "",
        "| Alan / model | mIoU | Crop risk | Spray recall | <14 px hit | Merkez ≤1 yarıçap | ≥%50 coverage |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in small_intervention:
        lines.append(
            f"| {item['dataset_label']} / {item['model_label']} | {item['miou']:.6f} | {item['risk']:.6f} | {item['safe_recall']:.6f} | {item['small_component_hit']:.6f} | {item['center_within_radius']:.6f} | {item['coverage50']:.6f} |"
        )
    lines += [
        "",
        "SugarBeets'te canvas768 crop riskini %4,41'den %1,45'e indirip spray recall'ı %4,15'ten %9,72'ye ve tüm-component hit'i %4,92'den %15,28'e yükseltti. WeedMap'te ise safe recall %6,29'dan %3,24'e, <14 px hit %0,38'den %0,04'e düştü. Bu nedenle 768 yalnız hedef robot kamerasına route edilen specialist; UAV/genel kullanımda kontrol fallback'tir.",
        "",
        "Spray recall dondurulmuş güvenli aksiyonun weed pixellerini yakalama oranıdır. Merkez ve coverage metrikleri bağlı semantik weed bileşenlerinden türetilen proxy'lerdir; kök/meristem veya gerçek botanik instance doğrulaması değildir.",
        "",
        "## Row prior",
        "",
        "| Alan | Mod | mIoU | Crop risk | Safe weed recall |",
        "|---|---|---:|---:|---:|",
    ]
    for item in row:
        lines.append(f"| {item['evaluation']} | {item['mode']} | {float(item['mean_iou']):.6f} | {float(item['crop_spray_risk']):.6f} | {float(item['safe_weed_pixel_recall']):.6f} |")
    lines += [
        "",
        "Oracle sonuç GT crop maskesinden yalnız sıra geometrisi çıkardığı için label-leaking üst sınırdır. Pratik sonuç model crop olasılığından fit edilir. Guard yalnız mevcut güvenli aksiyonu veto eder.",
        "",
        "## Kanıt yolları",
        "",
        f"- Kamera metrikleri: `{CAMERA_ROOT}`",
        f"- Row-prior metrik/görselleri: `{ROW_ROOT}`",
        f"- Domain curve: `{DOMAIN_RESULT}`",
        f"- Küçük-ot A/B: `{SMALL_RESULT}`",
        f"- 768 hedef-specialist seed43 teyidi: `{SMALL_CONFIRM_RESULT}`",
        f"- Gerçek holdout raster A/B: `{REAL_RASTER_ROOT.parent}`",
        f"- 768 hedef adayı müdahale metrikleri: `{SMALL_INTERVENTION_ROOT}`",
        f"- Self-contained veri/receipt kökü: `{OUTPUT}`",
        "",
        "## Sınırlamalar",
        "",
        "Tek seed ekranları eğitim varyansını tam ölçmez. Sentetik kamera eğrisi yön/duyarlılık kanıtıdır, gerçek sensör garantisi değildir. Sorghum adaptation aynı dataset/tek saha dağılımında olduğundan yeni-tarla performansı için iyimser olabilir. CWFID, SugarBeets ve WeedMap başka dataset dağılımlarıdır fakat bu panellerin her biri yalnız bir field/session capture group içerir; çok-çiftlik genellemesi kanıtlanmış değildir. Kesin donanım kararı gerçek kamera bench'i ve mm-kalibre actuator testi ister.",
        "",
        "## Dış kaynaklar",
        "",
        "- [Carbon Robotics LaserWeeder — kamera ve LED teknik bileşenleri](https://carbonrobotics.com/laserweeder) (üretici beyanı).",
        "- [Milioto, Lottes ve Stachniss — görülmemiş tarlaya az verili yeniden eğitim](https://www.ipb.uni-bonn.de/wp-content/papercite-data/pdf/milioto2018icra.pdf).",
        "- [Sa ve ark. — WeedMap; GSD ve downsampling etkisi](https://arxiv.org/abs/1808.00100).",
        "- [LaserWeeder saha çalışması; yüksek çözünürlüklü görüntü ve erken weed hedefleme](https://pmc.ncbi.nlm.nih.gov/articles/PMC12268811/).",
        "",
    ]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines), encoding="utf-8")


def build() -> Path:
    pages, data = build_pages()
    finalize_pages(pages, "Kamera + domain adaptation + küçük-ot deney raporu")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pdf = OUTPUT / "KAMERA_DOMAIN_VE_KUCUK_OT_DENEY_RAPORU.pdf"
    save_pdf(pages, pdf, title="Kamera, domain adaptation ve küçük-ot deneyleri")
    # Overview, native vs digital raster, size/GSD threshold, domain
    # curve/confirm, small-object A/B and final recommendation.  Intentionally
    # one idea per page.
    simple_indices = (0, 1, 3, 4, 5, 11, 13, 15, 16, len(pages) - 1)
    simple_pages = [pages[index] for index in simple_indices]
    simple_pdf = OUTPUT / "BASLA_BURADAN_KAMERA_DOMAIN_KARARI.pdf"
    save_pdf(simple_pages, simple_pdf, title="Kamera ve domain kararı — kısa rapor")
    markdown = OUTPUT / "DETAYLI_SONUCLAR.md"
    write_markdown(data, markdown)
    REPO_PDF.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf, REPO_PDF)
    shutil.copy2(simple_pdf, REPO_SIMPLE_PDF)
    write_markdown(data, REPO_MD)
    readme = OUTPUT / "README.md"
    readme.write_text(
        "# Kamera/domain deney paketi\n\n"
        "Önce `BASLA_BURADAN_KAMERA_DOMAIN_KARARI.pdf`, sonra "
        "`KAMERA_DOMAIN_VE_KUCUK_OT_DENEY_RAPORU.pdf`; gerektiğinde "
        "`DETAYLI_SONUCLAR.md` dosyasını açın.\n",
        encoding="utf-8",
    )
    return pdf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(build())


if __name__ == "__main__":
    main()
