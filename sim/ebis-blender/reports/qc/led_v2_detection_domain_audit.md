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
| camera_angled:cylinder | 6 | [0.5005859375, 0.5864583333333333, 0.25546875, 0.8270833333333334] | [0.502, 0.594, 0.255, 0.809] | 0.01808333333333334 | PASS |
| camera_angled:cube | 10 | [0.4927734375, 0.5645833333333333, 0.47734375, 0.8708333333333333] | [0.5, 0.574, 0.496, 0.852] | 0.01883333333333337 | PASS |
| camera_door:cylinder | 8 | [0.4974609375, 0.5701388888888889, 0.269921875, 0.8597222222222223] | [0.511, 0.573, 0.267, 0.854] | 0.013539062500000032 | PASS |
| camera_door:cube | 8 | [0.5275390625, 0.5649305555555555, 0.512109375, 0.8701388888888889] | [0.511, 0.575, 0.487, 0.849] | 0.02510937499999999 | PASS |

Partitions: `{'exclude': 1, 'hard_occlusion': 6, 'standard': 25}`

The ±0.03 framing gate is a visual calibration gate, not a claim of calibrated camera intrinsics.
