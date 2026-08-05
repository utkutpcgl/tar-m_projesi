"""ONNX export and numerical parity checks."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

from .engine import load_checkpoint


class ExportWrapper(nn.Module):
    def __init__(self, model: nn.Module) -> None:
        super().__init__()
        self.model = model

    def forward(
        self, image: torch.Tensor, target_crop_id: torch.Tensor
    ) -> torch.Tensor:
        return self.model(image, target_crop_id).softmax(dim=1)


def export_onnx(
    checkpoint_path: str | Path,
    destination: str | Path,
    image_size: int = 512,
    opset: int = 18,
) -> dict[str, object]:
    import onnx
    import onnxruntime as ort

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, checkpoint = load_checkpoint(checkpoint_path, device)
    # The wrapper itself must be in eval mode. The legacy exporter temporarily
    # changes and then restores the wrapper mode recursively; leaving the
    # wrapper at its default training=True would reactivate decoder dropout for
    # the PyTorch parity reference after export.
    wrapper = ExportWrapper(model).eval()
    image = torch.randn(1, 3, image_size, image_size, device=device)
    crop_id = torch.zeros(1, dtype=torch.long, device=device)
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)

    export_started = time.monotonic()
    torch.onnx.export(
        wrapper,
        (image, crop_id),
        output,
        input_names=["image", "target_crop_id"],
        output_names=["probabilities"],
        dynamic_axes={
            "image": {0: "batch", 2: "height", 3: "width"},
            "target_crop_id": {0: "batch"},
            "probabilities": {0: "batch", 2: "height", 3: "width"},
        },
        opset_version=opset,
        do_constant_folding=True,
        dynamo=False,
    )
    graph = onnx.load(output)
    onnx.checker.check_model(graph)
    export_seconds = time.monotonic() - export_started

    session = ort.InferenceSession(
        str(output), providers=["CPUExecutionProvider"]
    )
    runtime_input_names = {item.name for item in session.get_inputs()}
    model_config = checkpoint["config"]["model"]
    head = str(model_config.get("head", "flat"))
    known_ids = [int(value) for value in model_config.get("known_crop_ids", [0])]
    known_id = known_ids[0] if known_ids else 0
    num_crop_ids = int(model_config.get("num_crop_ids", 32))
    unknown_id = next(
        (value for value in range(num_crop_ids) if value not in known_ids),
        num_crop_ids,
    )
    cases = [
        {
            "name": "square_batch1_known_crop",
            "shape": (1, 3, image_size, image_size),
            "crop_ids": [known_id],
        },
        {
            "name": "rectangular_batch2_known_and_unknown_crop",
            "shape": (2, 3, image_size, image_size + 32),
            "crop_ids": [known_id, unknown_id],
        },
    ]
    case_reports: list[dict[str, object]] = []
    runtime_seconds = 0.0
    generator = torch.Generator(device="cpu").manual_seed(20260730)
    for case in cases:
        case_image = torch.randn(
            case["shape"], generator=generator, dtype=torch.float32
        ).to(device)
        case_crop_id = torch.tensor(
            case["crop_ids"], dtype=torch.long, device=device
        )
        with torch.inference_mode():
            case_reference = (
                wrapper(case_image, case_crop_id).float().cpu().numpy()
            )
        runtime_inputs = {"image": case_image.float().cpu().numpy()}
        if "target_crop_id" in runtime_input_names:
            runtime_inputs["target_crop_id"] = case_crop_id.cpu().numpy()
        runtime_started = time.monotonic()
        try:
            candidate = session.run(["probabilities"], runtime_inputs)[0]
            elapsed = time.monotonic() - runtime_started
            runtime_seconds += elapsed
            absolute = np.abs(case_reference - candidate)
            agreement = float(
                (
                    case_reference.argmax(axis=1)
                    == candidate.argmax(axis=1)
                ).mean()
            )
            finite = bool(np.isfinite(candidate).all())
            probability_sum_error = float(
                np.abs(candidate.sum(axis=1) - 1.0).max()
            )
            case_passed = bool(
                finite
                and absolute.max() <= 1e-3
                and agreement >= 0.999
                and probability_sum_error <= 1e-4
            )
            case_reports.append(
                {
                    **case,
                    "onnxruntime_cpu_seconds": elapsed,
                    "max_absolute_error": float(absolute.max()),
                    "mean_absolute_error": float(absolute.mean()),
                    "argmax_agreement": agreement,
                    "probability_sum_max_error": probability_sum_error,
                    "finite": finite,
                    "pass": case_passed,
                }
            )
        except Exception as error:
            runtime_seconds += time.monotonic() - runtime_started
            case_reports.append(
                {
                    **case,
                    "pass": False,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    conditioning_retained = "target_crop_id" in runtime_input_names
    conditioning_requirement_met = head == "flat" or conditioning_retained
    passed = bool(
        conditioning_requirement_met
        and all(bool(case["pass"]) for case in case_reports)
    )
    report = {
        "checkpoint": str(Path(checkpoint_path).resolve()),
        "onnx": str(output.resolve()),
        "opset": opset,
        "image_size": image_size,
        "file_size_bytes": output.stat().st_size,
        "export_seconds": export_seconds,
        "onnxruntime_cpu_seconds": runtime_seconds,
        "parity_cases": case_reports,
        "pass": passed,
        "model_architecture": model_config["architecture"],
        "model_head": head,
        "runtime_inputs": sorted(runtime_input_names),
        "crop_conditioning_input_retained": conditioning_retained,
        "crop_conditioning_requirement_met": conditioning_requirement_met,
        "includes_tiled_inference": False,
        "includes_safety_policy": False,
        "provenance": checkpoint["runtime_provenance"],
    }
    report_path = output.with_suffix(".parity.json")
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not passed:
        raise RuntimeError(
            f"ONNX parity validation failed; inspect {report_path}"
        )
    return report
