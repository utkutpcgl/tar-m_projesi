# Spot-Spray Ego-Motion Tracker V1

## Status and claim boundary

`spot_spray_ego_motion_tracker_v1` is frozen for parent-benchmark integration under a new release identity. It is not a field, product, dry-marker, deposition, or chemical-fire approval. The local calibration result is deliberately limited to neutral synthetic planar-fiducial mechanics. It does not validate an installed rig homography and contains no model output, botanical ground truth, arm/pair identity, locked-test input, segmentation metric, tracking metric, or action metric.

The parent integrator must bind the exact runtime image-to-ground homography and encoder receipt, verify every acceptance limit, bind the tracker release-lock SHA-256, create a new parent release identity, and only then perform the one fresh untouched locked-test evaluation. This lane does not authorize that inference.

## Frozen decision

The tracker uses the simplest product-realizable compensation already supported by the architecture:

1. Project the arithmetic mean of each canonical binary mask's foreground pixel centres through a validated image-pixel-to-camera-local-ground homography.
2. Quantize local ground coordinates to 10 micrometres using round-half-even.
3. Add trigger-latched signed encoder travel to camera-local ground `+X`; retain local `Y` unchanged.
4. Associate in that odometric ground frame using deterministic maximum-cardinality, minimum-total-integer-squared-residual, lexicographically resolved one-to-one assignment.

The canonical anchor is:

```text
world_x_mm = camera_local_ground_x_mm + relative_encoder_travel_mm
world_y_mm = camera_local_ground_y_mm
```

Positive encoder travel is product-forward `+X`. Runtime matrix inversion, raw-pixel fallback, optical flow, appearance embeddings, target velocity filtering, interpolation, class gating, and outcome-driven tuning are forbidden.

## Frozen residual gate

The gate is derived from architecture and calibration limits, never target outcomes:

```text
gate_um = ceil_to_mm(
    8500
    + ceil(travel_um * 110 / (520 - 110))
    + ceil(travel_um / 1000)
)
```

The fixed 8.5 mm budget covers two homography observations, daily registration drift, two encoder quantization endpoints, and two worst-case trigger-latch endpoints. The dynamic terms cover bounded 110 mm canopy parallax at the 520 mm minimum working distance and the 1 mm/m encoder-scale limit. The hard ceiling is 45 mm.

Frozen acceptance vectors are 18 mm for 0.5 m/s over one frame, 27 mm for 0.5 m/s over two frames, 27 mm for 1.0 m/s over one frame, and 45 mm for 1.0 m/s over two frames. A track may bridge exactly one intervening no-detection frame (`maximum_frame_index_delta = 2`).

## Association and output contract

Association reads geometry, frame order, trigger time, signed encoder travel, and the stable homography binding only. It does not read class labels, confidence, action points, arm identity, pair identity, source-object identity, renderer trajectory, ground truth, or benchmark outcome.

IDs are deterministic and video-scoped (`trk_000001`, ...). Every explicit video reset restarts at `trk_000001`; no state can cross a video boundary. The class emitted at track birth is immutable. A later raw-label disagreement keeps the same ID and birth class but emits confidence `0.0` and records the conflict only in the diagnostic sidecar.

The evaluator-facing candidate schema remains unchanged: `predicted_track_id`, `class_name`, `confidence`, `polygon`, plus `action_point` only for an emitted weed class. The tracker performs no fire-once logic, duplicate repair, or GT matching.

## Fail-closed lifecycle

The state machine is `UNINITIALIZED -> ACTIVE -> FINALIZED`, or terminally `INVALID_SEQUENCE`. Predictions are buffered for a whole video and become publishable only after valid finish. A missing, stale, unsynchronized, reversed, or out-of-envelope encoder sample; timestamp/frame-order fault; homography drift; invalid geometry; duplicate canonical geometry; forbidden metadata; or source-lock drift discards the entire buffered video output. There is no in-video recovery and no raw-coordinate fallback.

## Neutral calibration-mechanics diagnostic

The diagnostic uses two generated forward-only planar-fiducial sequences:

- 30 frames at 15 Hz and 0.5 m/s;
- 30 frames at 15 Hz and 1.0 m/s;
- a nominal 480 mm ground FOV in the frozen native 2048 x 2048 pixel space;
- at least nine persistent, uniquely identified non-target fiducials spanning the central support;
- dense one-frame observations plus deterministic two-frame gaps to exercise the full 45 mm gate.

The fixture is a mechanics witness, not an installed-rig calibration. Its purpose is to test transform direction, encoder timing, gate arithmetic, and the former raw-coordinate ceiling without reading a model or target outcome.

| Diagnostic | 0.5 m/s | 1.0 m/s |
|---|---:|---:|
| Frames | 30 | 30 |
| Eligible fiducial transitions | 1,075 | 979 |
| Raw displacement median | 142.220800 px | 284.445867 px |
| Raw displacement p95 | 284.445867 px | 568.887467 px |
| Positive compensated residual p95 | 0.006 mm | 0.006 mm |
| Maximum dynamic gate | 27 mm | 45 mm |
| Positive-sign gate violations | 0 | 0 |
| Wrong-sign gate violations | 1,075 | 979 |

The 1.0 m/s raw p95 exceeds the former 160 px gate while every positive-sign compensated residual remains inside the architecture-derived gate. The wrong-sign negative control fails, proving that the transform sign is not arbitrary. These numbers do not estimate or predict weed/crop tracking performance.

Independent audit processes with `PYTHONHASHSEED=0` and `PYTHONHASHSEED=1` produced byte-identical canonical candidate receipts with SHA-256 `b59780272e4220feef28d3e86789406d40f7ca6041826bdf46aca460f673eaae`.

## Release identity

The frozen inputs are:

- Config: `configs/benchmark/spot_spray_ego_motion_tracker_v1.yaml`, SHA-256 `a7f01ee0f703ca7a3a2af7b8d6e94571edff5bce7f3e0d90ef8871f70452242a`
- Tracker/audit implementation: `scripts/evaluate_spot_spray_ego_motion_tracker_v1.py`, SHA-256 `7f73e8e2e95270421f0ef97ab3c6ad6fb6dc3028933293dc46ea26c25ff4aca9`
- Focused test file: `tests/test_evaluate_spot_spray_ego_motion_tracker_v1.py`, SHA-256 `0c2379a2f11e3e75c2e34acd0cdad0f834df4d5f9aa113dfd0ae64d771507db0`
- Integrated adaptive plan: SHA-256 `d2543422b95a00cc1dc72a8af6e2655af884873dcc2a6f2490e3cf02a506aa56`
- Calibration-only receipt: SHA-256 `c54bf6c99177c4a5a02d95572cbe69b4522a557c87d2ae584e2dc958a8237dfb`
- Tracker release lock: SHA-256 `a706bd0df72408cf61c20e3e6f650754bb6c66ba033449dd553a0922b5e3ec36`
- Release identity: `07ebc955ba14ee29e173298fa79da34e304588554301f61cdc330729eaeb9ae5`

The release lock also binds the product architecture, capture optimization, rig-acceptance limits, frozen action contract/evaluator, fairness audit, every neutral calibration input, deterministic candidate receipt, and calibration receipt.

## Validation

Current command-backed validation produced:

- 35/35 tracker and calibration tests passing;
- 66/66 tests passing when the unchanged frozen action evaluator and temporal action suites are included;
- 1,600/1,600 small random assignment cases matching an exhaustive brute-force oracle;
- byte-identical calibration candidates across two Python hash seeds;
- zero positive-sign residual-gate violations;
- source/config/implementation hash verification before calibration measurements are parsed.

No training, checkpoint loading, full-render write, ideal/degraded inference, locked-test evaluation, or target-metric tuning occurred in this lane.

## Parent integration sequence

1. Verify `tracker_release_lock_v1.json` SHA-256 exactly.
2. Import `load_tracker_contract`, `homography_binding_from_mapping`, `encoder_binding_from_mapping`, and `EgoMotionTracker` from the frozen implementation.
3. Bind the exact runtime homography and encoder receipts before `start_sequence`.
4. For each video, call `start_sequence`, process strictly consecutive frames, call `finish_sequence`, then call `reset_sequence` before another video.
5. Treat any tracker exception or `INVALID_SEQUENCE` receipt as a whole-video fail-closed result.
6. Preserve evaluator candidate fields exactly and keep the diagnostic sidecar separate.
7. Bind the tracker release-lock hash into a new parent release identity before the single fresh locked-test evaluation.

Any code, config, calibration, source, frame-rate, speed envelope, gate, gap, label, or output-schema change requires a new tracker version and new release identity.
