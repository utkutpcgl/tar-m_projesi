#!/usr/bin/env python3
"""Generate a V11 split-aware pilot using correlated scene profiles."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.generate_cropcraft_field_robustness_pilot as legacy


PROFILED_GENERATOR = (
    Path(__file__).resolve().parent / "generate_cropcraft_profiled_pilot.py"
)


def output_argument(argv: list[str]) -> Path:
    try:
        index = argv.index("--output")
        return Path(argv[index + 1]).expanduser().resolve()
    except (ValueError, IndexError) as error:
        raise ValueError("Expected --output PATH") from error


def main() -> None:
    destination = output_argument(sys.argv[1:])
    legacy.LEGACY_GENERATOR = PROFILED_GENERATOR
    legacy.main()
    receipt_path = destination / "release_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["base_split_generator"] = receipt["generator"]
    receipt["base_split_generator_sha256"] = receipt["generator_sha256"]
    receipt["generator"] = str(Path(__file__).resolve())
    receipt["generator_sha256"] = legacy.sha256(Path(__file__).resolve())
    receipt["profiled_role_generator"] = str(PROFILED_GENERATOR)
    receipt["profiled_role_generator_sha256"] = legacy.sha256(PROFILED_GENERATOR)
    receipt["limitations"].append(
        "correlated profiles reduce impossible independent extremes but do not reproduce a measured weather prior"
    )
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "release_receipt": str(receipt_path),
                "release_receipt_sha256": legacy.sha256(receipt_path),
                "all_quality_gates_passed": receipt["all_quality_gates_passed"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
