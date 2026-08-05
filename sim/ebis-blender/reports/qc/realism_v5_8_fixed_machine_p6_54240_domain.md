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
| camera_angled:cylinder | 3 | [0.516015625, 0.5805555555555555, 0.23125, 0.8222222222222222] | [0.502, 0.594, 0.255, 0.809] | 0.023749999999999993 | PASS |
| camera_angled:cube | 1 | [0.5265625, 0.5840277777777778, 0.4828125, 0.8319444444444445] | [0.5, 0.574, 0.496, 0.852] | 0.026562500000000044 | PASS |
| camera_door:cylinder | 1 | [0.47734375, 0.58125, 0.24375, 0.8375] | [0.511, 0.573, 0.267, 0.854] | 0.03365625 | TUNE |
| camera_door:cube | 3 | [0.497265625, 0.5736111111111111, 0.46484375, 0.8527777777777777] | [0.511, 0.575, 0.487, 0.849] | 0.02215624999999999 | PASS |

Partitions: `{'hard_occlusion': 5, 'standard': 3}`

The ±0.03 framing gate is a visual calibration gate, not a claim of calibrated camera intrinsics.
