# Spot-spray simulation video inference smoke benchmark

This is a checkpoint-bound **synthetic diagnostic**, not field or deployment evidence.

- Checkpoint SHA-256: `3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100`
- Shared calibration-only threshold: `0.75`
- Locked-test evaluation count: `1`
- Descriptive target outcome: `neither_descriptive_target_met`

| condition | weed pixel F1 | weed instance F1 | eligible-track F1 | action F1 | crop-hit | duplicate-fire |
|---|---:|---:|---:|---:|---:|---:|
| ideal | 0.1424 | 0.0000 | 0.0000 | undefined | 0.0000 | 0.0000 |
| degraded | 0.1289 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

The ideal and degraded rows use the same held-out scene pairs and identical ground truth. The degraded transform was frozen in configuration before inference; no score was tuned toward a target.

The reporting-only target assessment checks ideal eligible mask-track F1 >= 0.97 and whether degraded F1 lies in [0.70, 0.80]. These values do not enter threshold selection.

V12 smoke sequences repeat one static frame three times. Their region IDs are connected-component proxies, not botanical tracks, and the result has zero weight in any real GO decision.
