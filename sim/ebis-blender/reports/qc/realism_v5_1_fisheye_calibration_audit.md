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
| camera_angled:cylinder | 2 | [0.50390625, 0.5701388888888889, 0.246875, 0.8597222222222223] | [0.502, 0.594, 0.255, 0.809] | 0.050722222222222224 | TUNE |
| camera_angled:cube | 2 | [0.498046875, 0.5256944444444445, 0.48203125, 0.9486111111111111] | [0.5, 0.574, 0.496, 0.852] | 0.09661111111111109 | TUNE |
| camera_door:cylinder | 2 | [0.5042968750000001, 0.5541666666666667, 0.28046875, 0.8916666666666666] | [0.511, 0.573, 0.267, 0.854] | 0.037666666666666626 | TUNE |
| camera_door:cube | 2 | [0.53671875, 0.5291666666666667, 0.5234375, 0.9416666666666667] | [0.511, 0.575, 0.487, 0.849] | 0.09266666666666667 | TUNE |

Partitions: `{'exclude': 1, 'hard_occlusion': 2, 'standard': 5}`

The ±0.03 framing gate is a visual calibration gate, not a claim of calibrated camera intrinsics.
