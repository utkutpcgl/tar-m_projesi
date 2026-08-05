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
| camera_angled:cylinder | 2 | [0.50390625, 0.5777777777777777, 0.228125, 0.8222222222222222] | [0.502, 0.594, 0.255, 0.809] | 0.02687500000000001 | PASS |
| camera_angled:cube | 2 | [0.523828125, 0.5909722222222222, 0.44453125, 0.8180555555555555] | [0.5, 0.574, 0.496, 0.852] | 0.05146875000000001 | TUNE |
| camera_door:cylinder | 2 | [0.50390625, 0.5680555555555555, 0.259375, 0.8638888888888889] | [0.511, 0.573, 0.267, 0.854] | 0.009888888888888947 | PASS |
| camera_door:cube | 2 | [0.4828125, 0.6041666666666667, 0.5296875, 0.7916666666666666] | [0.511, 0.575, 0.487, 0.849] | 0.05733333333333335 | TUNE |

Partitions: `{'hard_occlusion': 1, 'standard': 7}`

The ±0.03 framing gate is a visual calibration gate, not a claim of calibrated camera intrinsics.
