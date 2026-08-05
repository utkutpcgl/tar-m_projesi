#!/usr/bin/env python3
"""Build the post-selection research refit manifest deterministically.

CWFID is architecture-development data during screening. Only after the model
recipe is frozen is its single capture sequence relabelled as training data;
locked test manifests are never accepted by this helper.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from agri_seg.manifest import manifest_sha256, read_manifest, write_manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("core_manifest")
    parser.add_argument("cwfid_manifest")
    parser.add_argument("output_manifest")
    args = parser.parse_args()

    core = read_manifest(args.core_manifest)
    cwfid = read_manifest(args.cwfid_manifest)
    unexpected = sorted({record.split for record in cwfid} - {"external_calibration"})
    if unexpected:
        raise ValueError(
            "CWFID input must contain only external_calibration records; got "
            f"{unexpected}"
        )
    if any(record.dataset_id != "cwfid" for record in cwfid):
        raise ValueError("The development manifest contains a non-CWFID record")
    refit_records = [*core, *(replace(record, split="train") for record in cwfid)]
    output = Path(args.output_manifest)
    count = write_manifest(refit_records, output)
    print(
        json.dumps(
            {
                "manifest": str(output.resolve()),
                "samples": count,
                "cwfid_training_samples": len(cwfid),
                "sha256": manifest_sha256(output),
                "locked_test_samples_added": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
