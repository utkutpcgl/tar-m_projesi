"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict
from pathlib import Path

from .benchmark import run_benchmark
from .engine import evaluate_checkpoint, train_from_config
from .export import export_onnx
from .gallery import create_error_gallery
from .manifest import combine_manifests
from .prepare import (
    acquire_dataset,
    audit_manifest,
    cross_split_near_duplicates,
    convert_acre,
    convert_carrot_weed,
    convert_cropandweed,
    convert_cwfid,
    convert_ewis1,
    convert_phenobench,
    convert_rice_seedling_weed,
    convert_rose,
    convert_sorghum_weed,
    convert_we3ds,
    convert_weedsgalore,
    load_registry,
    write_audit,
)
from .visualize import create_contact_sheet


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agri-seg")
    subparsers = parser.add_subparsers(dest="command", required=True)

    disk = subparsers.add_parser("disk-check", help="Check data-disk capacity")
    disk.add_argument("--registry", default="configs/datasets.yaml")

    download = subparsers.add_parser("download", help="Acquire a registered dataset")
    download.add_argument("dataset")
    download.add_argument("--registry", default="configs/datasets.yaml")
    download.add_argument("--no-extract", action="store_true")

    convert = subparsers.add_parser("convert", help="Create common masks and manifest")
    convert.add_argument(
        "dataset",
        choices=[
            "phenobench",
            "rice_seedling_weed",
            "rose",
            "cwfid",
            "acre",
            "carrot_weed",
            "cropandweed",
            "ewis1",
            "we3ds",
            "weedsgalore",
            "sorghum_weed",
        ],
    )
    convert.add_argument("--data-root")
    convert.add_argument("--registry", default="configs/datasets.yaml")
    convert.add_argument(
        "--gate-config", default="configs/data/cropandweed_real_gate_v1.yaml"
    )

    combine = subparsers.add_parser(
        "combine-manifests", help="Combine canonical manifests and check leakage"
    )
    combine.add_argument("sources", nargs="+")
    combine.add_argument("--output", required=True)

    audit = subparsers.add_parser("audit", help="Validate manifest images and masks")
    audit.add_argument("manifest")
    audit.add_argument("--data-root", required=True)
    audit.add_argument("--output")

    duplicates = subparsers.add_parser(
        "duplicate-audit", help="Find exact/near duplicate images across splits"
    )
    duplicates.add_argument("manifest")
    duplicates.add_argument("--data-root", required=True)
    duplicates.add_argument("--max-hamming", type=int, default=2)
    duplicates.add_argument("--output", required=True)

    visualize = subparsers.add_parser(
        "visualize-labels", help="Create a bounded label-overlay contact sheet"
    )
    visualize.add_argument("manifest")
    visualize.add_argument("--data-root", required=True)
    visualize.add_argument("--output", required=True)
    visualize.add_argument("--count", type=int, default=30)
    visualize.add_argument("--seed", type=int, default=17)

    train = subparsers.add_parser("train", help="Train one benchmark candidate")
    train.add_argument("config")

    evaluate = subparsers.add_parser(
        "evaluate", help="Evaluate with the source-calibrated frozen policy"
    )
    evaluate.add_argument("checkpoint")
    evaluate.add_argument("manifest")
    evaluate.add_argument("--data-root", required=True)
    evaluate.add_argument("--split", default="external_test")
    evaluate.add_argument("--output", required=True)
    evaluate.add_argument("--batch-size", type=int, default=1)
    evaluate.add_argument("--workers", type=int, default=4)

    gallery = subparsers.add_parser(
        "error-gallery",
        help="Create locked-policy best/worst external-test overlays",
    )
    gallery.add_argument("checkpoint")
    gallery.add_argument("manifest")
    gallery.add_argument("--data-root", required=True)
    gallery.add_argument("--split", default="external_test")
    gallery.add_argument("--output", required=True)
    gallery.add_argument("--workers", type=int, default=4)
    gallery.add_argument("--device", default="auto")
    gallery.add_argument("--overwrite", action="store_true")

    export = subparsers.add_parser("export", help="Export ONNX and check parity")
    export.add_argument("checkpoint")
    export.add_argument("output")
    export.add_argument("--image-size", type=int, default=512)
    export.add_argument("--opset", type=int, default=18)

    benchmark = subparsers.add_parser("benchmark", help="Run a model/seed matrix")
    benchmark.add_argument("matrix")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "disk-check":
        registry = load_registry(args.registry)
        root = Path(registry["data_root"]).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(root)
        registered = {
            name: int(spec.get("size_bytes", 0))
            for name, spec in registry["datasets"].items()
            if isinstance(spec, dict)
        }
        _print(
            {
                "data_root": str(root.resolve()),
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
                "registered_download_bytes": registered,
                "registered_total_bytes": sum(registered.values()),
                "fits_with_20_gib_reserve": (
                    sum(registered.values()) + 20 * 1024**3 <= usage.free
                ),
            }
        )
    elif args.command == "download":
        path = acquire_dataset(
            args.dataset, args.registry, extract=not args.no_extract
        )
        _print({"dataset": args.dataset, "path": str(path.resolve())})
    elif args.command == "convert":
        if args.data_root:
            data_root = args.data_root
        else:
            data_root = load_registry(args.registry)["data_root"]
        converters = {
            "phenobench": convert_phenobench,
            "rice_seedling_weed": convert_rice_seedling_weed,
            "rose": convert_rose,
            "cwfid": convert_cwfid,
            "acre": convert_acre,
            "carrot_weed": convert_carrot_weed,
            "ewis1": convert_ewis1,
            "we3ds": convert_we3ds,
            "weedsgalore": convert_weedsgalore,
            "sorghum_weed": convert_sorghum_weed,
        }
        if args.dataset == "cropandweed":
            path = convert_cropandweed(data_root, args.gate_config)
        else:
            path = converters[args.dataset](data_root)
        _print({"dataset": args.dataset, "manifest": str(path.resolve())})
    elif args.command == "combine-manifests":
        count = combine_manifests(args.sources, args.output)
        _print(
            {
                "manifest": str(Path(args.output).resolve()),
                "samples": count,
                "sources": [str(Path(path).resolve()) for path in args.sources],
            }
        )
    elif args.command == "audit":
        result = audit_manifest(args.manifest, args.data_root)
        if args.output:
            write_audit(result, args.output)
        _print(asdict(result))
    elif args.command == "duplicate-audit":
        result = cross_split_near_duplicates(
            args.manifest, args.data_root, args.max_hamming
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _print(result)
    elif args.command == "visualize-labels":
        output = create_contact_sheet(
            args.manifest,
            args.data_root,
            args.output,
            args.count,
            args.seed,
        )
        _print({"contact_sheet": str(output.resolve())})
    elif args.command == "train":
        _print({"run_dir": str(train_from_config(args.config).resolve())})
    elif args.command == "evaluate":
        _print(
            evaluate_checkpoint(
                args.checkpoint,
                args.manifest,
                args.data_root,
                args.split,
                args.output,
                args.batch_size,
                args.workers,
            )
        )
    elif args.command == "error-gallery":
        index = create_error_gallery(
            args.checkpoint,
            args.manifest,
            args.data_root,
            args.split,
            args.output,
            args.workers,
            args.device,
            args.overwrite,
        )
        _print({"gallery_index": str(index.resolve())})
    elif args.command == "export":
        _print(
            export_onnx(
                args.checkpoint, args.output, args.image_size, args.opset
            )
        )
    elif args.command == "benchmark":
        _print({"results": str(run_benchmark(args.matrix).resolve())})


if __name__ == "__main__":
    main()
