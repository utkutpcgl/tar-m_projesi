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
| camera_angled:cylinder | 8 | [0.50234375, 0.5819444444444444, 0.23046875, 0.825] | [0.502, 0.594, 0.255, 0.809] | 0.024531250000000004 | PASS |
| camera_angled:cube | 8 | [0.526953125, 0.5888888888888889, 0.47734375, 0.8222222222222222] | [0.5, 0.574, 0.496, 0.852] | 0.029777777777777792 | PASS |
| camera_door:cylinder | 9 | [0.48359375, 0.5708333333333333, 0.2484375, 0.8583333333333333] | [0.511, 0.573, 0.267, 0.854] | 0.02740625000000002 | PASS |
| camera_door:cube | 7 | [0.49609375, 0.5638888888888889, 0.4859375, 0.8722222222222222] | [0.511, 0.575, 0.487, 0.849] | 0.023222222222222255 | PASS |

Partitions: `{'exclude': 4, 'hard_occlusion': 3, 'standard': 25}`

The ±0.03 framing gate is a visual calibration gate, not a claim of calibrated camera intrinsics.
