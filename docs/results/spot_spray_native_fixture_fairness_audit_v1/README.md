# Native fixture fairness audit v1

**Status:** PASS — hash-bound post-hoc diagnostic recomputation.

This package reads the frozen native fixture and persisted predictions only. It did not run inference, change the locked threshold, tune the tracker, or write into the active full-benchmark lane. The evidence is synthetic-only and authorizes no field, product, or chemical action.

## What was independently verified

- All configured anchor SHA-256 values matched, including the checkpoint, manifest,   threshold lock, four prediction JSONL files, metrics, and run receipt.
- The deserialized checkpoint declares `0=weed, 1=crop`; each prediction NPZ agrees.   GT declares `0=background, 1=crop, 2=weed`, and every labelled track pixel agrees.
- Every RGB, GT semantic mask, GT track mask, prediction NPZ, and raw detection mask   consumed by the audit passed its declared hash/content checks.
- Frozen tracker IDs reproduced exactly from the persisted detections and frozen native   association parameters.
- Independent weed/crop pixel, instance, and eligible-track counts exactly match the   stored locked-test metrics.

## Why eligible-track F1 is null, not zero

- **Ideal:** `TP=0, FP=0, FN=2`. Precision has denominator `TP+FP=0`, so precision is undefined. Recall is numerically zero because `TP+FN=2` is non-zero. This metric contract defines F1 only when both precision and recall are defined, so F1 is `null`; coercing it to `0.0` would misreport the evaluator semantics.
- **Degraded:** `TP=0, FP=0, FN=2`. Precision has denominator `TP+FP=0`, so precision is undefined. Recall is numerically zero because `TP+FN=2` is non-zero. This metric contract defines F1 only when both precision and recall are defined, so F1 is `null`; coercing it to `0.0` would misreport the evaluator semantics.

A numeric zero F1 is a different case: it requires both denominators to exist, for example at least one qualifying predicted track (`TP+FP>0`) and at least one eligible GT track (`TP+FN>0`), with no true positives.

## Valid interpretation

The fixture demonstrates low weed-mask coverage, crop/weed class confusion, threshold attrition, and track fragmentation. It does **not** demonstrate a class-index swap: checkpoint, prediction arrays, and GT semantic IDs are mutually consistent. Because eligible-track F1 is undefined in both arms, neither the ideal `>=0.97` reference nor the degraded `[0.70, 0.80]` reference is reached or meaningfully estimated here. Non-zero pixel/instance scores remain valid narrow diagnostics, not whole-model accuracy.

## Motion versus association limit

Test-weed apparent inter-frame motion has median `351.5px`, p95 `454.6px`, and `79.3%` of transitions fail the frozen geometry gate. The descriptive grid extends beyond that p95; it remains a counterfactual diagnostic, not a tracker recommendation.

- **Ideal:** `18` of `54` swept settings form a qualifying locked weed track; `0` produce an eligible-track TP. Result: `geometry_relaxation_forms_qualifying_tracks_but_none_match_eligible_gt`.
- **Degraded:** `18` of `54` swept settings form a qualifying locked weed track; `0` produce an eligible-track TP. Result: `geometry_relaxation_forms_qualifying_tracks_but_none_match_eligible_gt`.

See `diagnostic_contact_sheet.png` for five matched frames. `threshold_sweep.csv` and `association_sweep.csv` are explicitly post-hoc descriptive sweeps and must never be used to replace the locked test configuration.

## Corrective full-benchmark acceptance rule

A correction must be selected using fixture/calibration evidence only, assigned a new hash-bound release identity, and evaluated exactly once on a fresh untouched full locked test. The checkpoint/class/semantic mapping, full manifest, inference/tracker config, and degraded-calibration-only threshold lock must all verify before test access. Both arms must have non-empty eligible GT denominators and a defined primary F1; undefined F1 automatically fails target assessment. Only then may the frozen point estimates be compared with ideal `>=0.97` and degraded `[0.70, 0.80]`, without tuning to those values. Synthetic scores still authorize no field or chemical action.
