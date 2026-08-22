# Spot-Spray Ego-Motion Tracker V1 — Calibration-Only Release

Status: `TRACKER_RELEASE_FROZEN_CALIBRATION_ONLY`

This package freezes a GT-blind, class-blind encoder/homography tracker for later parent-benchmark integration. Its local evidence is a neutral synthetic planar-fiducial mechanics diagnostic. It is not installed-rig, field, product, target-performance, deposition, or chemical-fire evidence.

## Primary artifacts

| Artifact | SHA-256 |
|---|---|
| `calibration_only_receipt_v1.json` | `c54bf6c99177c4a5a02d95572cbe69b4522a557c87d2ae584e2dc958a8237dfb` |
| `tracker_release_lock_v1.json` | `a706bd0df72408cf61c20e3e6f650754bb6c66ba033449dd553a0922b5e3ec36` |
| Release identity | `07ebc955ba14ee29e173298fa79da34e304588554301f61cdc330729eaeb9ae5` |

The release lock binds the config, implementation, test file, architecture sources, frozen action interface, calibration inputs, calibration result, and two byte-identical hash-seed audit candidates.

## Decisive mechanics evidence

- 1.0 m/s raw pixel displacement p95: `568.887467 px` (greater than the former `160 px` gate)
- Positive-sign compensated residual p95: `0.006 mm`
- Positive-sign gate violations: `0`
- Wrong-sign negative-control gate violations: `2054`
- Maximum exercised dynamic gate: `45 mm`
- Hash-seed candidate SHA-256: `b59780272e4220feef28d3e86789406d40f7ca6041826bdf46aca460f673eaae`

These are geometry-mechanics results only; no segmentation, botanical tracking, or action result is inferred from them.

## Reproduction

The frozen config SHA-256 is `a7f01ee0f703ca7a3a2af7b8d6e94571edff5bce7f3e0d90ef8871f70452242a`. The exact neutral inputs are under `data/runs/spot_spray_ego_motion_tracker_v1/neutral_calibration_mechanics_v1/` and are individually bound in the config and release lock.

Run the audit twice with the frozen implementation and distinct `PYTHONHASHSEED` values, compare the candidate bytes, then use `--seal-calibration-release`. Immutable-output checks refuse divergent overwrites.

## Integration boundary

`ready_for_parent_integration` is true. `fresh_locked_test_inference_authorized_by_this_lane` is false. The parent must bind an accepted runtime homography and encoder receipt, bind this release-lock hash into a new parent release identity, preserve the exact tracker semantics, and own the one fresh untouched locked-test evaluation.

All of `model_loaded`, `model_outputs_present`, `target_gt_accessed`, `locked_test_accessed`, `field_go`, `product_go`, and `chemical_fire_allowed` are false.
