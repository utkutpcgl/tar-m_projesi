#!/usr/bin/env python3
"""Run the fixed evaluator with the frozen V7-R2 sensor dataset identity."""

from __future__ import annotations

import evaluate_sensor_motion_fixed_epoch_development as evaluator


evaluator.SENSOR_DATASET_ID = "cropcraft_sensor_motion_pilot_v7_r2"
# The shared evaluator records and hashes this wrapper as the executable policy.
# Its unchanged implementation is separately hash-locked by the R2 protocol.
evaluator.__file__ = __file__


if __name__ == "__main__":
    evaluator.main()
