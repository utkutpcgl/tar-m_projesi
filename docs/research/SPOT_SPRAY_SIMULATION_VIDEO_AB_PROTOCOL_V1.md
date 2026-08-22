# Spot-Spray Simulation Video A/B Protocol V1

Protocol ID: `spot_spray_simulation_video_ab_protocol_v1`

Status: `FROZEN_PRE_EXECUTION_CONTRACT`

Evidence class: **Synthetic diagnostic only**

## Decision

V1 is one outcome-blind matched-pair benchmark of the frozen one-bay
spot-spray perception-to-action stack. Every accepted latent sequence produces
one ideal video and one degraded video. The pair shares scene content, plant
identity, ground truth, camera mid-exposure trajectory, encoder trajectory,
frame clock, and random draws. Only the capture differences explicitly listed
in the machine contract may change.

The primary effect is degraded action F1 minus ideal action F1 on the locked
test. It is a **paired composite capture-profile effect**, not a blur-only causal
effect: the degraded arm combines bounded subpixel exposure integration with
predeclared renderer-light variation. V1 must not separate or reinterpret those
components after outcomes are visible.

The references `0.97` for ideal action F1 and `0.75` for degraded action F1 are
registered descriptive hypotheses. They are not gates, targets, tuning inputs,
or reasons to rerender, replace pairs, alter thresholds, or increase sample
size. V1 intentionally defines no “near” band.

## Authority and claim boundary

This protocol can produce a reproducible synthetic sensitivity estimate. It is
not field proof, physical rig acceptance, installed-camera validation, product
proof, dry-marker authority, deposition or crop-injury evidence, or chemical
fire authority. Synthetic metrics have weight `0.0` in every real GO decision.

All of the following remain false regardless of the measured scores:

- controlled-capture authorization;
- dry-marker readiness;
- field or product GO;
- chemical-fire permission;
- deposition and crop-injury proof;
- procurement or fabrication authority.

Synthetic `field_id` and `session_id` values exist only to exercise the frozen
evaluator’s grouped reports. They are not real fields, farms, sessions, seasons,
cameras, or countries.

## Frozen sources

The canonical machine-readable authority is
[`configs/benchmark/spot_spray_simulation_video_ab_protocol_v1.yaml`](../../configs/benchmark/spot_spray_simulation_video_ab_protocol_v1.yaml).
It locks exact bytes rather than relying on filenames or labels.

| Authority | Frozen identity |
|---|---|
| Repository source base | `9f558b10c6bebfa4c765b395b3dcfc3f5e0e75b9` |
| Planner decision commit | `8053f5e9f9f496c4a5a69b21884e9f73031c51c5` |
| Product architecture | `09dd57d852f0517b8716fc5056bc04121e3e6c072521931425f89cd002517dbd` |
| CropCraft V12 contract | `f006c709249cee0e9d8b8f74fd22fa0e1fdccde55ac90a6e2c474608607c0ec4` |
| CropCraft V12 release receipt | `ff733bff9458af8afebbfdc84a5c5ee4377df0f7635c55638b61889a22b57cf0` |
| V7 sensor-motion protocol | `4654e5e9625f5d2d8e6f8a8df1e4e072f095b24921aad068f226fd8faba94bee` |
| V7 sensor-motion asset gate | `05aada33bd5fafd9f152c4568a4f870b2976bf991a866856bebf68ee04592638` |
| V7 selection receipt | `8b78085b6ce6e4bc1a9bacc2d6437fc0c2ea859168421156b02e3502ab68c601` |
| Selected ROSE-native checkpoint | `3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100` |
| Frozen action contract | `210e6feddb93ca269d78a9947b48c2a84d0fb382828ba3265ff7debe06b74b09` |
| Frozen action evaluator | `3943090f5b34d730426bbb23e255757f1af28a89b3bbfc2f5a093a57e8ce9e45` |

The V7 receipt retained the accepted control, rejected the sensor-motion
challenger, and set `spray_deployment_eligible=false`. V7 therefore supplies PSF
mechanics and quality discipline only. Its rejected checkpoint is not used.

Renderer/export, native inference, and tracker implementations must each add an
exact path, resolved configuration, and SHA-256 to the release lock before they
may run. Their current machine-contract state is `UNRESOLVED_FAIL_CLOSED`.
Choosing one of those lineages from model outcomes is forbidden.

## Experimental unit and pairing

The sole experimental unit is a complete latent video sequence identified by
`pair_id`. Frames, masks, instances, and fire events are repeated observations
inside that unit; they are not independent samples.

Each `pair_id` has exactly two arms and exactly 30 frames per arm. Both arms
must have identical canonical digests for:

- source scene graph and asset identities;
- persistent crop and weed source-object identities;
- object geometry, materials, pose, and world transforms;
- ground, tillage, environment, and ambient state;
- camera mid-exposure trajectory and encoder trajectory;
- frame indices, timestamps, and latent frame IDs;
- GT classes, instance IDs, track IDs, masks, and polygons;
- canopy span, visible fraction, partial, and occluded fields;
- split and synthetic grouping;
- base capture draw vector.

The only arm differences are capture profile, arm-prefixed output identities,
temporal integration, pulse width, PSF path and weights, declared artificial
light settings, and the resulting RGB pixels and hashes. Any other difference
invalidates the entire release. A failed locked pair is never dropped from the
analysis set.

## Allocation and time base

The balanced design crosses:

- speed: `0.5` and `1.0 m/s`;
- V12 profile: `hood_dry_nominal` and
  `hood_moist_glare_challenge`;
- degraded motion path: `linear` and `smooth_curved`.

These factors form eight cells. Calibration uses four replicates per cell and
locked test uses eight. The complete frozen allocation is **96 latent pairs**,
192 videos, and **5,760 rendered frames**:

| Split | V12 source role | Pairs | Videos | Frames/video | Frames |
|---|---:|---:|---:|---:|---:|
| Calibration | `val` | 32 | 64 | 30 | 1,920 |
| Locked test | `test` | 64 | 128 | 30 | 3,840 |

Every video is exactly 30 frames at 15 Hz. Frame indices are `0..29` and
timestamps are derived from `round(i × 1e9 / 15)`. Encoder distance is computed
from signed forward speed and exact time before canonical decimal
serialization. Reverse motion, frame drops, duplicate timestamps, missing
frames, and arm-specific clocks are forbidden.

## Seed and identity rules

Each seed channel is the first unsigned big-endian 64 bits of:

```text
SHA256(protocol_id | split | cell_id | replicate_index |
       candidate_index | channel_name | V12_split_base_seed)
```

Calibration uses the V12 base `440000`; locked test uses `540000`. The channels
are `scene_seed`, `trajectory_seed`, `capture_draw_seed`, `renderer_seed`, and
`audit_sample_seed`.

`replicate_index` is intentionally included. The initial planner formula
omitted it, which would have duplicated candidate streams for replicate slots
inside one cell. This correction is part of the integrated protocol and is
covered by an exhaustive uniqueness assertion across all 4,800 planned
split/cell/replicate/candidate/channel combinations.

Arm name and hypothesis values do not enter the seed payload. No raw seed may
repeat across split or channel.

## Shared latent envelope

Both arms use the frozen architecture intersection with V12:

- native `2048×2048` RGB raster, with no full-frame resize;
- ground FOV `474–484 mm`;
- working distance `550–590 mm`;
- roll and pitch `-1°..+1°`, yaw `-4°..+4°`;
- lateral camera offset `0.01–0.10 m`;
- focus reference 55 mm above ground and test planes at 0, 55, and 110 mm;
- 64 px outer abstain ring, leaving a central `1920×1920` action region;
- global-shutter metadata, 170 µs exposure metadata, and 15 Hz acquisition;
- deterministic Latin-hypercube midpoint allocation before outcomes.

The dry and moist/glare parameter ranges are the exact calibration/test
intersections of the V12 profile ranges. Renderer light “energy” and “warmth”
remain proxy units. They are not irradiance, lumens, CCT, CRI, current, or an
installed strobe measurement.

## Capture arms

### Ideal upper-bound proxy

`IDEAL_CAPTURE_UPPER_BOUND_V1` samples the shared mid-exposure pose once, has no
temporal PSF, uses four equal all-on light quadrants at fixed profile midpoints,
fixed neutral white-balance proxy, `0 dB` gain, common deterministic tone
mapping, and lossless RGB8 sRGB PNG output. It adds no sensor noise,
compression, contamination, defocus perturbation, chromatic aberration,
vignetting perturbation, dropped frames, or rolling shutter.

It retains real scene difficulty within the simulation: plant overlap,
occlusion, soil and ambient variation, off-axis geometry, height variation, and
model-domain limitations. It is not a GT cartoon and is not a claim that an
installed camera can produce the same pixels.

### Degraded bounded proxy

`DEGRADED_CAPTURE_PROXY_V1` applies global-shutter integration over a
predeclared 150–170 µs light pulse. The physical path is:

```text
gsd_mm_per_px = ground_fov_mm / 2048
blur_px = speed_m_s × pulse_width_us × 0.001 / gsd_mm_per_px
```

Across the frozen geometry and speeds the maximum is approximately `0.734515
px`, below the architecture ceiling of `0.75 px`. Linear motion follows
projected travel. The smooth-curved path may reuse the pinned V7 curve mechanics
only after rescaling to that same physical path length. PSF weights must sum to
one and centroid error must be at most `0.15 px`.

V7’s original 5–25 px kernels and random 0–180° angles are forbidden. So are
extra Gaussian blur and any post-outcome rescaling. Uncalibrated noise, Bayer
response, lens MTF, contamination, defocus, severe vibration, frame loss,
compression, and light-channel failures are outside V1.

## Pre-outcome acceptance

For each required cell and replicate, the implementation evaluates candidate
indices `0..9` in the frozen derived order. It accepts the first candidate that
passes source, geometry, GT, temporal, pixel, and capture-operator gates. Every
rejection and exact reason is retained. Candidate selection cannot read the
checkpoint, predictions, confidence, segmentation, tracking, action metrics,
or distance to `0.97` or `0.75`.

If no candidate passes for a required slot after ten attempts, the run ends as
`SIM_AB_INVALID_INSUFFICIENT_PREOUTCOME_CANDIDATES`. Counts are not reduced,
cells are not borrowed, and ranges are not widened.

Machine gates verify exact source hashes; native dimensions; V12 brightness,
clipping, class coverage, and asset diversity; split purity; pair equality;
PSF normalization and length; monotonic time and encoder values; and minimum
eligible-track operability. A fixed calibration review sample may be inspected
only for renderer corruption, GT overlay correctness, pair mismatch, and
capture-envelope violations. It contains no model overlay or metric. Locked
test receives no discretionary human selection.

## Persistent GT gate

Track and action evidence requires persistent source-object identity. Every
plant must expose a stable object and GT track ID across frames, valid visible
mask or polygon, class, canopy span in world millimetres, visible fraction,
partial/occluded flags, world transform, and asset identity.

The current processed V12 proxy explicitly reports
`botanical_instance_ids_available=false`: its connected semantic regions may
merge touching plants or split occluded plants. It is valid semantic diagnostic
evidence but cannot be used as temporal track truth. Optical-flow tracks,
connected-component IDs, model tracker IDs, and manual repair are also
forbidden GT substitutes.

Before full rendering, the runtime lane must prove a pinned renderer/export
lineage with persistent source-object identity. If it cannot, V1 stops with
`REPLAN_REQUIRED_GT_TRACK_IDENTITY`. This honest stopping rule prevents a
semantic proxy from masquerading as track/action ground truth.

## Frozen inference and tracking interfaces

Only the checkpoint ending in SHA-256 `3aba4b19…73100` may run. It remains a
directional pre-real foundation, not a target-rig deployment model. Weights,
model graph, test-time augmentation, NMS, mask filtering, and preprocessing are
frozen. Both arms must use the same native 2048² tiling, halo, merge, class map,
mask postprocessing, action-point derivation, and numeric precision. Full-frame
resize is forbidden.

The tracker must be fixed before any calibration prediction, consume no GT or
arm/pair label, use identical code and parameters for both arms, reset at each
video boundary, and produce video-scoped stable predicted IDs. Fragmentation
must remain visible to the action evaluator; the tracker cannot pre-repair
duplicates or fire-once outcomes.

Four calibration pairs covering both speeds and scene profiles are run twice as
a determinism preflight. Canonical prediction bytes must match. Missing native
inference, missing stable tracking, ambiguous lineages, and nondeterminism each
have named fail-closed or re-plan states.

## Calibration and locked-test order

The order is irreversible for one V1 release:

1. Freeze protocol, sources, seeds, cells, envelopes, estimands, and code hashes.
2. Generate and pre-outcome-audit both arms in both splits.
3. Complete the fixed calibration-only visual review.
4. Seal `release_lock_v1.json` with `model_outputs_present=false`.
5. Run inference only on the **degraded calibration** videos.
6. Select the confidence threshold with the frozen action semantics.
7. Seal `threshold_lock_v1.json` with `test_predictions_present=false`.
8. Optionally compute ideal calibration diagnostics with zero selection weight.
9. Unlock both test arms, evaluate each once, and seal the paired result.

The frozen threshold grid is `0.05..0.95` in `0.05` steps. Selection maximizes
recall subject to frozen precision, crop-hit, Wilson upper-bound, and duplicate
safety constraints, then applies the frozen tie breakers. If no threshold is
feasible, maximum validation F1 is retained only as a diagnostic fallback and
the status is `SIM_AB_CALIBRATION_INFEASIBLE_SYNTHETIC_ONLY`.

The same degraded calibration bytes and **one shared threshold** are used for
both ideal and degraded test runs. Separate thresholds are structurally
forbidden. Test data never enters calibration.

## Metrics

### Segmentation

At the locked weed threshold and crop threshold `0.25`, predictions and GT are
rasterized at native 2048². Same-class instances are matched one-to-one at mask
IoU `≥0.50`, with canonical-ID tie breaks. Crop and weed instance precision,
recall, F1, matched IoU, and unmatched counts are reported. Border/partial
observations are separate. Segmentation does not replace action F1.

### Tracking

Frame matches form a GT/predicted overlap table. Deterministic one-to-one track
assignment maximizes matched observations. V1 reports three-observation track
precision/recall/F1, confirmation coverage, fragmentation, fragments per GT,
ID switches, consecutive matches, and five-frame continuity. These diagnostics
do not replace the action evaluator’s fire and duplicate semantics.

### Action

The existing evaluator remains authoritative for eligibility (`20 mm`, visible
fraction `0.70`, non-partial), three confirmations in five frames, crop veto,
fire-once, one-to-one eligible-track matching, crop-collision precedence,
duplicate and background false positives, attempted-shot safety denominators,
and the crop-hit Wilson upper bound.

The primary estimand is:

```text
delta_action_f1 = action_f1_degraded - action_f1_ideal
```

Precision, recall, F1, TP/FP/FN, attempts, crop hits, Wilson bound, duplicates,
and eligible tracks are reported per arm and as paired deltas. Speed, V12
profile, motion path, and synthetic-field summaries are descriptive only.

## Uncertainty

V1 uses a stratified paired cluster bootstrap with **10,000** replicates and
seed `1729`. The resampling unit is `pair_id`; both arms always travel together.
Sampling is within the eight design cells. Exact sufficient counts are summed
and metrics recomputed. Rounded frame-level scores are not resampled and the
threshold is never recalibrated inside a replicate.

Percentile 95% intervals use `0.025` and `0.975`. Undefined denominators remain
null. If more than 1% of replicates are undefined, the interval is omitted with
`UNSTABLE_DENOMINATOR`; the point counts remain visible. The evaluator’s Wilson
crop-hit bound is not replaced.

These intervals cover only the bounded synthetic latent-pair sample. They omit
training/checkpoint, renderer-model, real-camera, installed-optics, farm,
season, weather, carrier, operator, deposition, and biological uncertainty.

## Terminal behavior

A valid one-time run ends after the locked test even if ideal F1 is far below
`0.97`, degraded F1 is far from `0.75`, degraded outperforms ideal, intervals
are wide, or calibration is infeasible. None of those outcomes changes V1.

Named invalidity states cover source drift, pair mismatch, split leakage,
candidate exhaustion, nondeterministic inference, premature test access, and
outcome-conditioned changes. Re-plan states cover absent persistent GT, absent
native inference, absent stable tracking, and ambiguous runtime lineage. V1
never silently repairs, drops, or overwrites a locked pair. A material change
requires a separately frozen V2.

## Executable contract evidence

The focused test
[`tests/test_spot_spray_simulation_video_ab_protocol_v1.py`](../../tests/test_spot_spray_simulation_video_ab_protocol_v1.py)
checks:

- duplicate and unknown YAML keys;
- every repository and external source hash;
- architecture, checkpoint, and evaluator alignment;
- exact allocation and seed uniqueness;
- pair-equality and capture-difference closure;
- V12 profile intersections and the physical subpixel blur ceiling;
- pre-outcome selection and release/threshold lock order;
- the known connected-region GT gap and its stopping status;
- degraded-only calibration and frozen evaluator reuse;
- segmentation, tracking, action, and pair-bootstrap definitions;
- all false authority flags and terminal failure behavior;
- consistency between this document and the YAML authority.

It validates the V1 protocol. It does not claim that rendering, inference, or a
locked test has already run.
