# EBIS detection-domain audit

- Real images: 2960
- Real split leakage warning: YES
- Overlapping capture groups: 7

## Real class counts

| Class | Instances | Images | Image fraction | Median short px | Median long px | Edge-touch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| tag | 15596 | 2897 | 0.979 | 40.43 | 117.82 | 0.079 |
| concrete | 2945 | 2944 | 0.995 | 774.15 | 923.11 | 0.552 |
| apriltag | 516 | 516 | 0.174 | 158.96 | 182.83 | 0.000 |
| person | 2664 | 2474 | 0.836 | 553.75 | 930.29 | 0.692 |

## Synthetic concrete framing gate

| Camera/shape | N | Synthetic median | Real target | max |delta| | Gate |
| --- | ---: | --- | --- | ---: | --- |
| camera_angled:cylinder | 4 | [0.49453125, 0.578125, 0.21796875, 0.7805555555555556] | [0.502, 0.594, 0.255, 0.809] | 0.037031250000000016 | TUNE |
| camera_angled:cube | 2 | [0.517578125, 0.5909722222222222, 0.49609375, 0.8180555555555555] | [0.5, 0.574, 0.496, 0.852] | 0.033944444444444444 | TUNE |
| camera_door:cylinder | 5 | [0.5, 0.5680555555555555, 0.24921875, 0.8638888888888889] | [0.511, 0.573, 0.267, 0.854] | 0.017781250000000026 | PASS |
| camera_door:cube | 1 | [0.4984375, 0.5833333333333333, 0.4375, 0.8333333333333334] | [0.511, 0.575, 0.487, 0.849] | 0.04949999999999999 | TUNE |

Partitions: `{'exclude': 1, 'hard_occlusion': 4, 'standard': 7}`

The ±0.03 framing gate is a visual calibration gate, not a claim of calibrated camera intrinsics.
