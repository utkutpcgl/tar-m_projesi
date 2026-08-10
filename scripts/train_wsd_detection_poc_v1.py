#!/usr/bin/env python3
"""Train the date-disjoint WSD detection-only spot-spray baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.train_wsd_pose_poc_v1 import run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="configs/benchmark/wsd_detection_poc_v1.yaml",
    )
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--fraction", type=float, default=1.0)
    parser.add_argument("--name-suffix", default="")
    arguments = parser.parse_args()
    receipt = run(
        Path(arguments.config),
        epochs_override=arguments.epochs,
        fraction=arguments.fraction,
        name_suffix=arguments.name_suffix,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
