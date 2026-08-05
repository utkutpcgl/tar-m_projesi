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
| camera_angled:cylinder | 2 | [0.5044921874999999, 0.5642361111111112, 0.24960937500000002, 0.8715277777777777] | [0.502, 0.594, 0.255, 0.809] | 0.06252777777777763 | TUNE |
| camera_angled:cube | 2 | [0.498046875, 0.5232638888888889, 0.48750000000000004, 0.9534722222222223] | [0.5, 0.574, 0.496, 0.852] | 0.1014722222222223 | TUNE |
| camera_door:cylinder | 2 | [0.5041015625, 0.5496527777777778, 0.27851562500000004, 0.9006944444444445] | [0.511, 0.573, 0.267, 0.854] | 0.04669444444444448 | TUNE |
| camera_door:cube | 2 | [0.5326171875, 0.5430555555555556, 0.501171875, 0.9138888888888889] | [0.511, 0.575, 0.487, 0.849] | 0.06488888888888888 | TUNE |

Partitions: `{'exclude': 1, 'hard_occlusion': 2, 'standard': 5}`

The ±0.03 framing gate is a visual calibration gate, not a claim of calibrated camera intrinsics.
