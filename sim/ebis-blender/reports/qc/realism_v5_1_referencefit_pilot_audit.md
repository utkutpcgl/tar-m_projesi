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
| camera_angled:cylinder | 2 | [0.503515625, 0.578125, 0.228125, 0.820138888888889] | [0.502, 0.594, 0.255, 0.809] | 0.02687500000000001 | PASS |
| camera_angled:cube | 2 | [0.512890625, 0.5791666666666666, 0.5054687499999999, 0.8416666666666667] | [0.5, 0.574, 0.496, 0.852] | 0.012890625000000044 | PASS |
| camera_door:cylinder | 2 | [0.50390625, 0.5677083333333334, 0.25859375, 0.8645833333333333] | [0.511, 0.573, 0.267, 0.854] | 0.010583333333333278 | PASS |
| camera_door:cube | 2 | [0.490234375, 0.6024305555555556, 0.528125, 0.7951388888888888] | [0.511, 0.575, 0.487, 0.849] | 0.05386111111111114 | TUNE |

Partitions: `{'standard': 8}`

The ±0.03 framing gate is a visual calibration gate, not a claim of calibrated camera intrinsics.
