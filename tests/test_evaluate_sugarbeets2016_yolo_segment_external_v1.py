import numpy as np
import pytest

from scripts.evaluate_sugarbeets2016_yolo_segment_external_v1 import (
    fixed_threshold,
    semantic_region_instances,
)


def test_semantic_region_instances_uses_eight_connectivity_and_class_ids() -> None:
    semantics = np.zeros((16, 16), dtype=np.uint8)
    semantics[1:5, 1:5] = 2
    semantics[5:9, 5:9] = 2
    semantics[10:15, 2:8] = 1
    instances, counts = semantic_region_instances(semantics, 4)
    assert counts == {"weed": 1, "crop": 1, "below_minimum": 0}
    assert set(np.unique(instances)) == {0, 1, 2}
    assert np.all(semantics[instances == 1] == 2)
    assert np.all(semantics[instances == 2] == 1)


def test_semantic_region_instances_rejects_unknown_palette() -> None:
    with pytest.raises(ValueError, match="common mask"):
        semantic_region_instances(np.asarray([[3]], dtype=np.uint8), 1)


def test_fixed_threshold_reads_pheno_validation_lock() -> None:
    source = {
        "results": {
            "model": {
                "methods": {
                    "method": {
                        "eligible_size_views": {
                            "82": {
                                "validation_calibration": {
                                    "balanced_max_f1": {"threshold": 0.37}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    assert fixed_threshold(source, "model", "method", 82.0) == 0.37
