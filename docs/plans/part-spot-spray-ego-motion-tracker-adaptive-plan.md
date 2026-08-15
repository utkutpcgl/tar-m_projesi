Status: READY
Planner depth: 0
Parent plan: (root plan)

GT-Blind Ego-Motion-Compensated Tracker V1
1. Decision

Freeze one tracker identity named spot_spray_ego_motion_tracker_v1 with the following baseline:

Association is performed in a two-dimensional odometric ground frame, not raw image pixels.

Each detection mask receives one geometry-only anchor: the centroid of its canonical binary mask.

The exact image-to-ground transform is a validated, hash-bound homography whose canonical direction is image pixels to camera-local ground millimetres.

Signed encoder position increases in product +X forward. Adding signed encoder travel to the camera-local ground coordinate produces the odometric coordinate used for association.

Association is class-blind, confidence-blind, arm-blind, pair-blind and GT-blind.

Candidate assignment is deterministic maximum-cardinality, minimum-total-residual one-to-one matching under a dynamic, architecture-derived residual gate.

The existing ambiguous maximum_frame_gap: 2 is resolved as a maximum frame-index delta of 2: a track may bridge exactly one intervening frame without a detection, not two.

Track IDs are deterministic, video-scoped monotonic labels: trk_000001, trk_000002, and so on.

Track output class is frozen from the birth observation. Later class disagreement never changes association or track identity; the emitted confidence for the disagreeing observation is 0.0, and the disagreement is recorded in a diagnostic sidecar.

Any invalid homography, stale or unsynchronised encoder sample, reverse/ambiguous travel, frame-order fault or source drift invalidates the complete video. There is no fallback to raw-pixel association.

Calibration-only non-target witness evidence must demonstrate that the compensation contract changes the supplied raw-motion case from “outside the 160 px raw gate” to “inside the frozen ground-residual gate.” This proves mechanics only, not target tracking or action performance.

No fresh locked-test inference may begin until the implementation, configuration, calibration receipt and deterministic diagnostic result are hash-frozen.

This is the simplest product-realizable design that removes the known raw-coordinate ceiling while preserving downstream fragmentation, duplicate-shot and fire-once semantics for the frozen action evaluator.

2. Goals

Freeze the exact coordinate transform, sign, state, association, output and failure semantics before any fresh locked-test model access.

Replace the raw 160 px motion gate with a ground-coordinate residual gate derived only from frozen architecture and measurement limits.

Produce stable predicted track IDs in the schema already consumed by the frozen action evaluator.

Prove transform direction and compensation mechanics using calibration witnesses and frame_timing.jsonl, without target GT or model outcomes.

Make all ordering, matching, class-output, gap and reset behavior byte-reproducible.

Keep the tracker isolated behind a narrow module contract so Codex can integrate it without changing its identity.

3. Non-goals

No model selection, threshold selection, NMS tuning, mask-postprocessing tuning or capture-profile tuning.

No use of botanical GT, source-object IDs, synthetic GT tracks, semantic connected-component IDs, optical-flow pseudo-tracks or manual identity repair.

No use of class, confidence, action point, arm name, pair ID, split name, renderer trajectory or locked-test result in association.

No repair of fragmentation or duplicate shots inside the tracker.

No fire-once state inside the tracker; the frozen action evaluator remains authoritative.

No interpolation of masks or synthetic observations across gaps.

No appearance embeddings, optical flow, Kalman filter, learned re-identification or target-specific motion model.

No yaw, lateral-odometry or multi-camera fusion in V1.

No edits to the frozen action evaluator, simulation protocol, active full-render outputs or target model.

No field, READY, product, deposition, crop-injury or chemical-fire claim.

4. Evidence ledger
4.1 Repository facts

The focused context identifies remote main as 9f558b10c6bebfa4c765b395b3dcfc3f5e0e75b9 and records unrelated dirty simulation-video work. This tracker lane must pin the remote base and must not absorb or overwrite that unrelated working-tree state.

The current fixture policy uses a raw 160 px centroid-distance gate and maximum_frame_gap: 2; its diagnostic sweep explicitly extends beyond approximately 455 px observed p95 motion because the raw gate is a geometry ceiling.

The simulation protocol already marks the prediction tracker as unresolved and fail-closed before model access.

The frozen latent envelope is native 2048 × 2048, 15 Hz, 30 frames, forward-only, with 0.5 and 1.0 m/s travel and a 64 px outer abstain ring.

The parent protocol requires one tracker identity fixed before calibration predictions, identical for both arms, with no GT or arm-label access, video-boundary reset and no duplicate repair.

The downstream action semantics are already frozen around three confirmations in a five-frame window, fire-once per predicted track, crop veto and one-to-one GT matching. The tracker must supply IDs, not reimplement these rules.

4.2 Supplied physical and telemetry limits

Treat these as frozen inputs to this part:

Product ground axes: +X forward, +Y vehicle right.

Frame rate: 15 Hz.

Trial speeds: 0.5 m/s and 1.0 m/s.

Encoder resolution: no worse than 1 mm/count.

Encoder scale error: no worse than 1 mm/m.

Camera-trigger to encoder-latch separation: no worse than 250 µs.

Encoder stale cutoff: 5 ms.

Ground-homography residual: p95 no worse than 1 mm, maximum no worse than 2 mm.

Daily registration drift: no worse than 2 mm.

Product working-distance lower bound used for the conservative gate: 520 mm.

Maximum relevant canopy relief: 110 mm.

Existing raw association threshold: 160 px.

Supplied raw apparent motion: median 351.5 px, p95 454.6 px.

The raw-motion statistics motivate changing coordinate systems. They are not inputs to the new gate.

4.3 Engineering inferences

For a static ground object, its camera-local +X coordinate decreases when the carrier travels in product +X. Therefore the world-stationary odometric coordinate is obtained by adding positive signed encoder travel to the camera-local ground coordinate.

A planar ground homography applied to elevated canopy points leaves a height-dependent residual after longitudinal compensation. The residual budget must therefore include worst-case canopy parallax rather than only calibration and encoder error.

A scalar encoder cannot distinguish longitudinal travel from yaw or lateral motion. Any calibration sequence whose residuals require those unmeasured degrees of freedom must trigger a 2D-odometry re-plan; the residual gate must not be widened to absorb it.

Stable class output is needed because the frozen action evaluator rejects class changes within one predicted track. Birth-label locking with zero confidence on later disagreement is the smallest online-compatible rule that preserves class-blind association and fails conservatively.

5. Ownership and compatibility boundary
5.1 Lane-owned implementation files

Codex may create or modify only these tracker-lane paths while executing this part:

configs/benchmark/spot_spray_ego_motion_tracker_v1.yaml

src/agri_seg/ego_motion_tracker.py

scripts/audit_spot_spray_ego_motion_tracker_v1.py

tests/test_spot_spray_ego_motion_tracker_v1.py

tests/test_audit_spot_spray_ego_motion_tracker_v1.py

tests/fixtures/spot_spray_ego_motion_tracker_v1/**

docs/results/spot_spray_ego_motion_tracker_v1/README.md

docs/results/spot_spray_ego_motion_tracker_v1/calibration_only_receipt_v1.json

docs/results/spot_spray_ego_motion_tracker_v1/tracker_release_lock_v1.json

The current plan file is the planning artifact and is not an implementation target.

5.2 Read-only dependencies

The tracker lane may read and hash, but must not modify:

configs/deploy/spot_spray_product_architecture_v1.yaml

configs/deploy/spot_spray_rig_acceptance_v1.yaml

configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml

scripts/evaluate_spot_spray_target_rig_action_v1.py

configs/benchmark/spot_spray_simulation_video_ab_protocol_v1.yaml, when present in the integration worktree

configs/benchmark/spot_spray_simulation_video_ab_execution_v1.yaml, when present in the integration worktree

The exact supplied frame_timing.jsonl

The exact validated homography/calibration receipt

Existing inference outputs only for schema-compatibility fixtures explicitly generated before locked-test access; no target result may enter calibration.

Known frozen downstream hashes from the focused context:

Action contract SHA-256: 210e6feddb93ca269d78a9947b48c2a84d0fb382828ba3265ff7debe06b74b09

Action evaluator SHA-256: 3943090f5b34d730426bbb23e255757f1af28a89b3bbfc2f5a093a57e8ce9e45

Any hash drift is a stop condition, not an invitation to adapt the tracker.

5.3 Integration handoff

The parent integrator may later import src.agri_seg.ego_motion_tracker and bind its exact code/config/release-lock hashes into the simulation release lock. That integration is outside this part.

This lane does not edit:

scripts/evaluate_spot_spray_simulation_video_v1.py

scripts/run_spot_spray_simulation_video_ab_execution_v1.py

Any active full-benchmark render state

Any ideal/degraded prediction files

Any threshold lock

Any locked-test result

6. Frozen tracker contract
6.1 Canonical pixel space

The tracker accepts detections only in the exact pixel space named by the homography receipt.

Required baseline:

Raster: 2048 × 2048.

Coordinates: zero-based pixel centres.

Pixel centre for integer raster location (column, row) is (u, v) = (column + 0.5, row + 0.5).

No implicit resize, crop, undistortion or axis swap inside the tracker.

The homography receipt must bind the exact upstream pixel-space ID and preprocessing hash.

The canonical trackable support is the intersection of:

the homography receipt’s validated support polygon; and

the central action rectangle [64, 1984) × [64, 1984).

A detection whose anchor is outside this intersection is not associated. It receives a new singleton track ID and is closed after that observation. It is not silently dropped and never falls back to raw-pixel tracking.

6.2 Homography direction

The only runtime-accepted canonical direction is:

active-image pixel coordinate → camera-local ground coordinate in millimetres

Define the canonical homography as H_i2g.

For pixel homogeneous coordinate:

p = [u, v, 1]^T

compute:

q = H_i2g p

and:

g_k = [q_x / q_w, q_y / q_w]

where:

g_k.x is forward distance in millimetres relative to the camera-ground origin at frame k;

g_k.y is distance to vehicle right in millimetres;

q_w must be finite and have absolute value greater than the frozen denominator tolerance.

The tracker must never guess direction from matrix values. A ground-to-image matrix must be explicitly converted and sealed by the calibration producer before tracker startup. Runtime matrix inversion is forbidden.

The receipt must include orientation witnesses proving:

a declared forward witness has larger F_ground.x than the origin witness;

a declared right witness has larger F_ground.y than the origin witness;

the witness residuals satisfy the frozen homography thresholds.

6.3 Signed encoder coordinate

The tracker consumes one canonical signed integer position:

encoder_position_um

Properties:

Unit: integer micrometres.

It is latched from the same hardware event as the camera trigger.

It increases when the carrier travels in product +X.

The first valid frame defines s_0.

Relative travel at frame k is:

Δs_epoch(k) = encoder_position_um(k) - encoder_position_um(0)

For this proof envelope, any negative relative increment is invalid reverse or ambiguous motion.

The upstream encoder adapter owns count-to-distance conversion. The tracker validates the bound receipt but does not estimate scale from images or target outcomes.

6.4 Exact compensation transform

For a detection in frame k, after homography projection and integer coordinate canonicalisation:

w_k.x = g_k.x + Δs_epoch(k)

w_k.y = g_k.y

w_k is the odometric ground anchor used for association.

Equivalent prediction of a previous observation into the current camera-local frame is:

ĝ_k.x = w_track.x - Δs_epoch(k)

ĝ_k.y = w_track.y

A static object under pure product-forward translation therefore remains approximately constant in w.

The opposite sign is contract-invalid. It is retained only as a diagnostic negative control.

6.5 Geometry-only detection anchor

For every post-NMS canonical binary mask:

Require mask shape exactly 2048 × 2048.

Require at least one foreground pixel.

Compute the arithmetic mean of all foreground pixel centres.

Project that centroid through H_i2g.

Canonicalise each ground component to the nearest 10 µm using round-half-even.

Compute a SHA-256 over the canonical packed mask bits.

The detection’s association key is:

(anchor_x_10um, anchor_y_10um, canonical_mask_sha256)

The key must not include:

class;

confidence;

action point;

source enumeration order;

frame ID text;

arm, pair or split;

target or GT identity.

Two detections with identical association keys in one frame are an ambiguous duplicate-geometry contract error. The frame and video are invalidated rather than ordered by class, confidence or incidental input order.

The tracker does not use bbox centre, raw polygon vertex average or action point as its association anchor.

6.6 Architecture-derived residual gate

The gate is computed from frozen physical limits, not from observed target outcomes.

Constants

Maximum canopy relief: z_max = 110 mm

Minimum camera-to-ground distance: h_min = 520 mm

Homography maximum residual: 2 mm per observation

Daily registration drift maximum: 2 mm

Encoder resolution maximum: 1 mm/count

Encoder scale error maximum: 1 mm/m

Trigger/latch maximum: 250 µs

Proof speed maximum: 1,000 mm/s

Association frame-index delta maximum: 2

Fixed error budget

In integer micrometres:

Two homography observations: 2 × 2,000 = 4,000 µm

Daily registration drift: 2,000 µm

Two encoder quantisation endpoints: 2 × 1,000 = 2,000 µm

Two trigger/latch endpoints at 1 m/s: 2 × 250 = 500 µm

Therefore:

fixed_budget_um = 8,500

The 5 ms stale cutoff is not added to the gate. A stale sample is invalid and cannot be converted into extra matching tolerance.

Dynamic terms

For an eligible track last observed at frame j and a detection at frame k:

travel_um = abs(encoder_position_um(k) - encoder_position_um(j))

Worst-case planar-homography parallax:

parallax_um = ceil_div(travel_um × 110, 520 - 110)

Encoder scale error:

scale_um = ceil_div(travel_um, 1000)

Raw budget:

budget_um = 8500 + parallax_um + scale_um

Frozen gate:

gate_um = 1000 × ceil_div(budget_um, 1000)

The association residual is Euclidean distance in the quantised odometric ground plane, and an edge is valid iff:

residual_squared_um2 <= gate_um²

Expected gate values

0.5 m/s, one frame interval: 18 mm

0.5 m/s, two frame intervals: 27 mm

1.0 m/s, one frame interval: 27 mm

1.0 m/s, two frame intervals: 45 mm

The V1 hard gate ceiling is therefore 45 mm.

If telemetry implies travel above the 1.0 m/s, two-frame proof envelope, the sequence is invalid. The gate must not expand beyond 45 mm.

6.7 Association objective

For each valid frame:

Expire tracks whose current frame-index delta exceeds 2.

Build edges only between trackable detections and non-expired tracks whose residual is within the dynamic gate.

Select a one-to-one assignment with this exact lexicographic objective:

maximise the number of matched track/detection pairs;

minimise the sum of integer squared residuals;

among exact ties, choose the lexicographically smallest assignment vector when tracks are ordered by numeric track ID and detections by canonical association key.

Update each matched track’s anchor to the current odometric anchor without filtering or velocity estimation.

Allocate new IDs to unmatched detections in canonical detection-key order.

Do not emit interpolated observations for unmatched active tracks.

Any assignment algorithm is acceptable only if it produces this exact objective and canonical bytes. A Hungarian implementation or an equivalent deterministic solver is allowed; greedy nearest-neighbour assignment is not contract-equivalent.

6.8 Class and confidence output

Association must be complete before class-output logic is applied.

For each new track:

emitted_class_name is frozen to the raw class of the birth observation.

Allowed values remain those accepted by the frozen action evaluator: crop, weed, partial_unknown.

The frozen class never changes.

For each later observation:

If raw_class_name == emitted_class_name, emit the raw confidence unchanged.

If raw_class_name != emitted_class_name:

keep the same track ID;

keep the frozen emitted class;

emit confidence 0.0;

increment raw_label_conflict_count;

record the conflict in the diagnostic sidecar;

do not change association, track lifetime or future gate calculations.

Geometry behavior:

Preserve the canonical polygon/mask geometry from the current detection.

The upstream adapter must provide one deterministic maximum-interior-distance action point for every mask, independent of class.

Serialize action_point only when the emitted class is weed.

A class-conflict observation on a weed-born track may therefore carry the canonical geometry action point but confidence 0.0.

The tracker must not create an extra crop/weed candidate to represent a conflicting raw label.

This rule is conservative and online: a track can never be promoted from crop or unknown to weed by later observations.

6.9 Track IDs and output ordering

Track IDs are strings trk_000001 through trk_999999.

The counter starts at one after every explicit video reset.

IDs are never reused within a video.

IDs contain no video, pair, arm, class, split, source or host text.

Track IDs are meaningful only under the external (field_id, session_id, video_id) scope already used by the action evaluator.

Candidate records within each frame are ordered by numeric track ID.

Frame records preserve input frame order.

Every valid input frame produces exactly one output frame record, including frames with zero candidates.

The tracker must preserve frame IDs as opaque values and must not parse their text.

Counter overflow invalidates the sequence.

6.10 Exact gap semantics

Freeze:

maximum_frame_index_delta = 2

Meaning:

Last observation at frame 10, detection at frame 11: matchable.

Last observation at frame 10, no detection at 11, detection at 12: matchable.

Last observation at frame 10, detections absent at 11 and 12, detection at 13: old track is expired; the detection receives a new ID.

Every frame must still be supplied. A missing frame record is a frame-drop fault, not a detection gap.

No mask, centroid, label or confidence is predicted into an absent observation.

6.11 Tracker state machine
UNINITIALIZED

No frame may be processed.

start_sequence requires valid source hashes, calibration receipt, encoder receipt and pixel-space identity.

Successful start enters ACTIVE.

Failed start enters INVALID_SEQUENCE.

ACTIVE

Frames must begin at the declared first frame index and increase exactly by one.

Timestamps must be strictly increasing.

Homography ID, calibration hash and encoder contract must remain unchanged.

A valid frame updates tracks and buffered output.

A terminal fault clears active tracks, discards publishable output and enters INVALID_SEQUENCE.

finish_sequence finalises labels, closes all tracks, serializes canonical output and enters FINALIZED.

INVALID_SEQUENCE

No tracker/action prediction file is published for the video.

A failure receipt is permitted.

Additional frames are rejected.

Recovery inside the same video is forbidden.

Only an explicit new-video reset with a newly validated start contract may return to ACTIVE.

FINALIZED

Additional frames are rejected.

Only explicit new-video reset may begin the next sequence.

6.12 Terminal invalid conditions

Any of the following invalidates the complete video:

Tracker config or implementation hash drift.

Frozen action contract/evaluator hash drift at release-lock verification.

Missing or malformed calibration receipt.

Homography direction other than canonical image-to-ground.

Homography p95 residual above 1 mm.

Homography maximum residual above 2 mm.

Daily drift above 2 mm.

Pixel-space or preprocessing hash mismatch.

Homography orientation witness failure.

Non-finite matrix, projection or anchor.

In-support projection denominator below the frozen tolerance.

Encoder resolution above 1 mm/count.

Encoder scale error above 1 mm/m.

Trigger/latch separation above 250 µs.

Encoder sample age above 5 ms.

Encoder position decrease or reverse/ambiguous direction.

Travel outside the frozen 1.0 m/s proof envelope.

Duplicate, missing or non-consecutive frame index.

Non-increasing timestamp.

Changed calibration/homography identity inside a video.

Ambiguous duplicate detection geometry.

Track-ID overflow.

Non-deterministic canonical output.

Any attempt to supply GT, source-object, pair, arm, condition or split fields to the tracker’s association input.

There is no raw-pixel fallback and no “best effort” partial video.

6.13 Observation-local non-terminal conditions

These conditions do not invalidate the complete video:

No detections in a valid frame.

A trackable detection with no gated association; it starts a new track.

Detection anchor outside the validated central support; it becomes a singleton, unassociated track.

Raw class disagreement on a matched track; association remains unchanged and confidence is zeroed.

A track expiring after the frozen gap.

All such cases must be counted in diagnostics.

7. Calibration-only evidence contract
7.1 Purpose

The calibration diagnostic answers only:

Does the signed encoder plus validated image-to-ground transform remove the known raw-coordinate association ceiling under the frozen fixture timing and geometry?

It does not estimate weed/crop track precision, recall, F1, ID switches, fragmentation, action F1 or field performance.

7.2 Permitted inputs

Exact frame_timing.jsonl.

Exact validated homography receipt.

Non-target planar calibration-witness observations.

Frozen tracker config and implementation.

Neutral geometry-only test detections.

Architecture constants and source hashes.

7.3 Forbidden inputs

Model predictions from locked test.

Ideal/degraded arm names.

Pair IDs.

Botanical or semantic GT tracks.

Crop/weed source-object IDs.

Action outcomes.

Segmentation, tracking or action metrics.

Registered 0.97 or 0.75 descriptive references.

Existing gt_motion_transitions.csv or any other GT-derived correspondence file.

Active full-render state.

7.4 Required calibration witness data

Preferred path:

Use calibration-witness coordinates already present beside frame_timing.jsonl, provided they are explicitly non-target fiducials and hash-bound.

Smallest bounded discovery when those coordinates are absent:

Capture one complete 30-frame planar fiducial sequence at 0.5 m/s.

Capture one complete 30-frame planar fiducial sequence at 1.0 m/s.

Use 15 Hz and the same camera-trigger/encoder-latch event.

Observe at least nine persistent, uniquely identified fiducials spanning the central action region.

Use the installed pixel space and exact validated homography.

Do not run the model.

Do not render a full synthetic pair.

Do not capture or annotate crop/weed targets.

Store only fiducial pixel coordinates, timing, encoder values and receipt hashes.

Decision rule:

If this bounded witness capture is unavailable or fails integrity, tracker runtime binding remains TRACKER_NOT_READY_CALIBRATION_EVIDENCE.

Do not replace it with target GT or model predictions.

7.5 Required diagnostic calculations

For each witness and eligible transition:

Raw pixel displacement.

Camera-local ground displacement before encoder compensation.

Odometric ground residual after positive-sign compensation.

Odometric ground residual under the intentionally wrong negative-sign control.

Actual dynamic gate for that transition.

Positive-sign gate pass/fail.

Frame delta, timestamp delta, encoder delta and latch age.

Speed and motion-path stratum for reporting only.

Required aggregate outputs:

Frame and transition counts by speed.

Raw pixel median, p95 and maximum.

Compensated residual median, p95 and maximum in millimetres.

Dynamic gate minimum, median and maximum.

Positive-sign gate-violation count.

Wrong-sign gate-violation count.

Homography p95/max and drift values.

Telemetry validity counters.

Deterministic result digest.

Explicit booleans showing no target GT, model output or locked-test input was accessed.

7.6 Calibration-only PASS

The audit status is TRACKER_FROZEN_CALIBRATION_ONLY only when all conditions hold:

Exact source hashes match.

Exact tracker config and implementation hashes match.

Homography and encoder receipts meet every frozen limit.

One complete valid 30-frame sequence exists at both 0.5 and 1.0 m/s.

At least nine calibration witnesses span the central support.

The supplied raw-motion condition is reproduced strongly enough that the 1.0 m/s raw p95 exceeds 160 px.

Every positive-sign compensated witness transition is within its dynamic gate.

Positive-sign gate violations equal zero.

The wrong-sign negative control violates the gate on at least one 1.0 m/s transition and has a larger p95 residual than the positive-sign result.

Repeated execution with different Python hash seeds produces byte-identical canonical receipt content.

No target, arm, pair, locked-test or model-output field is present.

All field, product and chemical claim flags are false.

Passing this gate proves only that the raw-motion ceiling has been removed for the bounded calibration mechanics.

7.7 Calibration-only failure

Residual failure does not authorize gate widening.

A failure in only curved/yaw-affected witnesses triggers REPLAN_REQUIRED_2D_EGOMOTION.

A failure in linear witnesses triggers REPLAN_REQUIRED_HOMOGRAPHY_OR_ENCODER.

Missing witness evidence yields TRACKER_NOT_READY_CALIBRATION_EVIDENCE.

Wrong-sign control failing to separate from the positive sign yields TRACKER_INVALID_TRANSFORM_DIRECTION_TEST.

Any forbidden data access yields TRACKER_INVALID_SCOPE_VIOLATION.

8. Deterministic output and release artifacts
8.1 Evaluator-compatible prediction output

The tracker integration must be able to produce the frozen action evaluator’s frame candidate schema:

predicted_track_id

stable class_name

confidence

unchanged canonical polygon

action_point only for emitted weed candidates

No tracker-only diagnostic field may be inserted into the evaluator prediction JSONL.

8.2 Tracker diagnostic sidecar

A separate sidecar may contain:

track ID;

frame index;

canonical detection key;

matched/new/singleton/expired state;

residual and gate;

frame delta and encoder delta;

raw-label conflict flag;

projection/support status;

terminal failure reason.

The sidecar is not consumed by the action evaluator and must not contain GT or pair/arm identity.

8.3 calibration_only_receipt_v1.json

Required fields:

schema version and contract ID;

terminal calibration-only status;

implementation base commit;

all source paths and SHA-256 values;

frame-timing SHA-256;

homography receipt SHA-256;

encoder receipt SHA-256;

tracker config and implementation SHA-256;

exact physical constants and gate formula;

pixel-space identity;

speed/frame/witness counts;

raw and compensated summaries;

wrong-sign negative-control summary;

violation counters;

deterministic output digest;

forbidden-access assertions;

locked_test_accessed: false;

model_loaded: false;

target_gt_accessed: false;

field_go: false;

product_go: false;

chemical_fire_allowed: false.

8.4 tracker_release_lock_v1.json

Seal this only after calibration-only PASS.

Required fields:

contract_id: spot_spray_ego_motion_tracker_v1

implementation base commit;

tracker config path and SHA-256;

tracker module path and SHA-256;

audit script path and SHA-256;

test-file SHA-256 values;

frozen action contract/evaluator SHA-256 values;

product architecture SHA-256;

homography receipt path and SHA-256;

encoder receipt path and SHA-256;

frame_timing.jsonl SHA-256;

calibration receipt path and SHA-256;

canonical coordinate direction;

exact gate constants and hard ceiling;

exact frame-gap semantics;

exact label-output semantics;

output schema identity;

deterministic canonical-result SHA-256;

model_outputs_present: false;

locked_test_accessed: false;

ready_for_parent_integration: true;

all deployment and chemical claim flags false.

The lock is immutable. Any subsequent tracker-code, config, calibration or source change requires a new version, not an overwrite.

9. Rejected alternatives
Raw image-pixel association

Rejected because the frozen 160 px gate is below supplied median and p95 raw motion. Increasing that raw gate would enlarge ambiguity without separating ego motion from object residual.

Convert 160 px directly to millimetres

Rejected because a constant pixel-to-mm conversion still omits canopy parallax, homography error, encoder uncertainty and gap duration.

Tune the gate from calibration or locked-test target tracks

Rejected because it would make the tracker outcome-dependent. The gate is derived only from product geometry and instrument limits.

Use class equality as an association gate or cost

Rejected because class flicker would create hidden fragmentation and class labels are not object identity. Class is applied only after geometry association.

Use model confidence in association or tie-breaking

Rejected because confidence is target/model dependent and would make identity sensitive to threshold behavior.

Use action point as the association anchor

Rejected because it is action-specific and can move discontinuously with mask interior geometry. The mask centroid is class-independent and defined for every detection.

Use source-object, botanical or renderer trajectory identity

Rejected because those values are unavailable in the product and constitute GT leakage.

Use optical flow, appearance embeddings or learned re-identification

Rejected for V1 because the primary observed bottleneck is known carrier translation, and these methods add target-dependent tuning and non-product evidence.

Use a Kalman filter or estimated target velocity

Rejected because plants are stationary in the proof frame and the encoder already supplies the dominant motion. Filtering would add state and tuning without solving unavailable yaw/lateral motion.

Use a greedy nearest-neighbour matcher

Rejected because input ordering can change results in crowded cases. The required maximum-cardinality/minimum-residual assignment has one canonical answer.

Continue after an invalid telemetry or calibration frame

Rejected because track identity after an unobserved or incorrectly transformed carrier motion is ambiguous.

Fall back to the legacy raw tracker

Rejected because silent fallback would reintroduce the exact ceiling this part is intended to remove.

Add yaw or lateral state immediately

Rejected because no frozen product-realizable yaw/lateral sensor input is supplied. Failure of the scalar design is a bounded re-plan trigger.

10. Ordered implementation ledger
Package 0 — Freeze sources and resolve the only missing calibration inputs

 - [ ] Record implementation base 9f558b10c6bebfa4c765b395b3dcfc3f5e0e75b9; verify every read-only dependency against its expected exact bytes before implementation.

Outcome: no unrelated dirty simulation file becomes an accidental source or edit.

Acceptance: source-lock draft lists path, exact SHA-256, role and availability for each dependency.

 - [ ] Resolve the exact local path and SHA-256 of the supplied frame_timing.jsonl without copying it into an active full-render tree.

Outcome: timing evidence is immutable before diagnostics.

Acceptance: hash is recorded before parsing, and later runs reject a mismatch.

 - [ ] Resolve the exact validated homography receipt and encoder-limit receipt.

Outcome: runtime transform and telemetry bounds are source-bound.

Acceptance: receipt contains exact pixel-space ID, image-to-ground direction, orientation witnesses, p95/max residual, daily drift, encoder resolution, encoder scale error and trigger/latch limits.

 - [ ] Inspect whether the permitted calibration evidence already contains persistent non-target fiducial correspondences.

Outcome: decide whether the bounded two-speed witness capture is required.

Acceptance:

correspondences present and valid → use them;

correspondences absent → execute only the bounded witness discovery in Section 7.4;

target/GT correspondences are never substituted.

 - [ ] Stop before implementation freeze if any required source hash, homography field or non-target witness source remains unresolved.

Observable status: TRACKER_NOT_READY_CALIBRATION_EVIDENCE.

Package 1 — Encode the contract in configuration

 - [ ] Create configs/benchmark/spot_spray_ego_motion_tracker_v1.yaml.

Include source locks, claim boundary, coordinate axes, pixel space, homography direction, telemetry limits, mask-anchor rule, integer quantisation, dynamic gate formula, assignment objective, gap semantics, label semantics, state machine, diagnostic contract, output fields and terminal failure codes.

Acceptance: no material constant or rule in Sections 6–8 remains implicit in Python.

 - [ ] Encode the gate using integer micrometre arithmetic and exact ceiling operations.

Acceptance test vectors:

0.5 m/s, one frame → 18,000 µm;

0.5 m/s, two frames → 27,000 µm;

1.0 m/s, one frame → 27,000 µm;

1.0 m/s, two frames → 45,000 µm.

 - [ ] Encode a hard maximum frame-index delta of 2 and explicitly document that it bridges one intervening no-detection frame.

Acceptance: config contains no ambiguous maximum_frame_gap interpretation.

 - [ ] Encode denylisted association inputs:

gt_*

source_object_id

stable_gt_track_id

pair_id

arm

condition

split

renderer or latent trajectory

previous predicted track ID

Acceptance: generic dictionary parsers reject unknown/denylisted fields before association.

 - [ ] Encode the exact terminal statuses and audit exit codes:

exit 0: TRACKER_FROZEN_CALIBRATION_ONLY

exit 2: TRACKER_NOT_READY_CALIBRATION_EVIDENCE

exit 3: tracker/homography/telemetry contract invalid

exit 4: forbidden-scope input

exit 5: non-deterministic output or source drift

Package 2 — Implement transform, validation and state lifecycle

 - [ ] Create src/agri_seg/ego_motion_tracker.py as a standalone module with no imports from Ultralytics, Torch, simulation GT builders or action metric code.

Outcome: product-realizable geometry tracker with no model or GT dependency.

Acceptance: module imports only standard-library and already-required numerical primitives.

 - [ ] Implement typed immutable inputs for:

calibration/homography binding;

encoder binding;

frame telemetry;

canonical detection geometry;

tracker result and failure receipt.

Acceptance: association cannot receive arbitrary metadata dictionaries after boundary validation.

 - [ ] Implement homography loading and validation.

Require canonical image-to-ground direction.

Verify exact pixel-space and preprocessing hashes.

Verify orientation witnesses.

Verify p95/max/drift thresholds.

Reject runtime inversion.

Acceptance: direction-swapped, axis-swapped, singular, non-finite and stale receipts fail before the first frame.

 - [ ] Implement exact signed compensation:

w.x = g.x + encoder_delta

w.y = g.y

Acceptance: a static synthetic witness remains constant under positive forward travel; the opposite sign fails the same fixture.

 - [ ] Implement mask centroid and geometry-key generation.

Use foreground pixel centres.

Quantise ground coordinates to 10 µm.

Hash canonical packed mask bits.

Acceptance: repeated execution and input-order permutations produce identical keys.

 - [ ] Implement the state machine and atomic video publishing.

Acceptance:

frames rejected before explicit start;

valid start enters active;

valid finish emits complete output;

any terminal fault discards publishable video output;

no recovery inside an invalid video;

explicit next-video reset restarts ID numbering at trk_000001.

 - [ ] Implement frame and telemetry checks.

Exact consecutive frame index.

Strictly increasing timestamps.

Stable homography identity.

Latch separation <=250 µs.

Stale age <=5 ms.

Forward-only encoder position.

Travel within proof envelope.

Acceptance: each violation maps to one canonical failure code.

Package 3 — Implement deterministic association and output semantics

 - [ ] Implement the dynamic gate with integer arithmetic.

Outcome: no floating threshold comparison.

Acceptance: gate vectors and hard 45 mm ceiling match the config exactly.

 - [ ] Implement eligible-track selection with maximum frame-index delta 2.

Acceptance:

delta 1 matches;

delta 2 may match;

delta 3 expires and creates a new ID.

 - [ ] Implement deterministic maximum-cardinality/minimum-total-squared-residual assignment.

Acceptance:

a fixture where greedy matching is suboptimal selects the global solution;

exact-cost ties resolve by canonical track/detection order;

random input permutation produces byte-identical association trace.

 - [ ] Ensure association code reads only:

track geometry/state;

current detection geometry;

frame index;

timestamp validity;

signed encoder travel;

homography binding.

Acceptance: mutating all classes, confidences and action points while holding masks and telemetry fixed leaves association pairs and track IDs unchanged.

 - [ ] Implement unmatched-detection births in canonical geometry-key order.

Acceptance: candidate input order cannot alter new track IDs.

 - [ ] Implement out-of-support singleton handling.

Acceptance: border detection is preserved as one output candidate with a unique one-observation track and never enters association.

 - [ ] Implement immutable birth-label semantics.

Acceptance:

same-class observations retain raw confidence;

conflicting-class observations retain ID and birth class but emit 0.0;

the output contains no class changes for one track;

conflict counts appear only in the sidecar.

 - [ ] Preserve geometry and serialize evaluator-compatible candidates.

Acceptance: frozen action evaluator parser accepts the generated prediction JSONL without modifying its schema or code.

 - [ ] Confirm the tracker performs no fire-once, duplicate suppression or GT matching.

Acceptance: fragmented predicted IDs remain fragmented and are visible to the action evaluator.

Package 4 — Implement calibration-only audit

 - [ ] Create scripts/audit_spot_spray_ego_motion_tracker_v1.py.

Outcome: one deterministic, model-free mechanics audit.

Acceptance: script never imports or loads the selected checkpoint.

 - [ ] Require exact SHA-256 for timing, homography, encoder, config and implementation inputs before parsing measurements.

Acceptance: one-byte mutation exits with source-drift status.

 - [ ] Reject any input schema containing target GT, arm, pair, condition, split or locked-test fields.

Acceptance: dedicated negative fixtures exit 4.

 - [ ] Compute raw, ground-local, compensated and wrong-sign witness residuals for both speeds.

Acceptance: all calculations use the same module functions as runtime association.

 - [ ] Apply the exact calibration-only PASS rules in Section 7.6.

Acceptance: no descriptive target or model metric appears in pass logic.

 - [ ] Write only:

docs/results/spot_spray_ego_motion_tracker_v1/calibration_only_receipt_v1.json

docs/results/spot_spray_ego_motion_tracker_v1/README.md

Acceptance: no write occurs under active full-render, prediction or locked-test roots.

 - [ ] Make failure output informative but fail-closed.

Include violated source, transition, witness, residual, gate and canonical failure code.

Do not emit a tracker prediction file on failure.

Package 5 — Build exhaustive bounded tests

 - [ ] Create neutral fixtures under tests/fixtures/spot_spray_ego_motion_tracker_v1/.

Include:

valid identity/scaled homography;

wrong-direction homography;

axis-swapped orientation;

singular/non-finite homography;

valid 0.5 and 1.0 m/s timing;

stale/latch-fault timing;

reverse encoder;

mask-order permutations;

class/confidence permutations;

global-assignment tie and greedy-failure cases;

border singleton;

frame-gap cases;

deterministic calibration witnesses.

Fixtures must be synthetic geometry or non-target fiducials only.

 - [ ] Create tests/test_spot_spray_ego_motion_tracker_v1.py.

Cover transform sign, gate arithmetic, quantisation, state transitions, gaps, global assignment, tie-breaking, ID allocation, labels, evaluator schema and every terminal fault.

 - [ ] Add a direct regression for the known raw ceiling.

Construct a transition with raw displacement above 160 px.

Assert a raw-pixel gate cannot associate it.

Assert the positive-sign odometric residual associates under the frozen gate.

Assert the wrong sign fails.

Do not use target labels or model predictions.

 - [ ] Add a class-blind association metamorphic test.

Hold masks and telemetry fixed.

Permute classes, confidences and action points.

Assert association trace and track IDs are identical.

Assert only emitted class/confidence fields change according to the frozen output rule.

 - [ ] Add input-order determinism tests.

Shuffle detections and internal mapping order.

Run under at least two PYTHONHASHSEED values.

Require byte-identical canonical output.

 - [ ] Add complete invalid-sequence tests.

Verify no partial evaluator prediction file survives a terminal fault.

 - [ ] Create tests/test_audit_spot_spray_ego_motion_tracker_v1.py.

Cover PASS, insufficient evidence, source drift, wrong sign, forbidden scope, homography failure, telemetry failure and non-deterministic receipt.

 - [ ] Run the existing frozen action-evaluator tests unchanged.

Acceptance: no downstream regression and no evaluator edit.

Package 6 — Produce and freeze calibration-only evidence

 - [ ] Run the audit first on the exact supplied timing and existing non-target witness evidence.

Acceptance: result reports both speed strata and the raw/compensated contrast.

 - [ ] If witness coordinates are absent, execute exactly the bounded two-speed planar-fiducial discovery and rerun.

Do not broaden into target capture or full rendering.

 - [ ] Require zero positive-sign gate violations.

Any violation stops V1 freeze.

 - [ ] Require the wrong-sign negative control to fail.

This is the observable proof that transform direction is not arbitrary.

 - [ ] Require the 1.0 m/s raw p95 to exceed 160 px.

This demonstrates the diagnostic covers the original raw-coordinate ceiling.

 - [ ] Re-run with a different Python hash seed and compare canonical receipt bytes.

Acceptance: byte-identical output.

 - [ ] Create tracker_release_lock_v1.json only after PASS.

Acceptance: lock records model_outputs_present: false and locked_test_accessed: false.

Package 7 — Handoff without running locked test

 - [ ] Provide the parent integrator with:

module path and SHA-256;

config path and SHA-256;

release-lock path and SHA-256;

callable API signature;

evaluator-compatible output schema;

explicit reset call sequence;

terminal failure codes.

Outcome: integration cannot reinterpret tracker semantics.

 - [ ] Require the parent release lock to bind the exact tracker release-lock SHA-256 before any model access.

Acceptance: unresolved or drifted tracker identity remains REPLAN_REQUIRED_TRACKER_CONTRACT.

 - [ ] Stop this part before running any calibration model inference, ideal/degraded inference or locked test.

Completion of this lane authorizes integration work only.

11. Exact validation

Codex must run these checks from the implementation branch without claiming any full-render or locked-test execution.

11.1 Focused tests
Bash
python -m pytest -q \
  tests/test_spot_spray_ego_motion_tracker_v1.py \
  tests/test_audit_spot_spray_ego_motion_tracker_v1.py \
  tests/test_evaluate_spot_spray_target_rig_action_v1.py \
  tests/test_temporal_action.py

Expected:

all tests pass;

no existing test is edited to weaken an assertion;

no model weight is loaded.

11.2 Calibration-only audit

Resolve these variables from the source-lock step:

Bash
export FRAME_TIMING_JSONL="<exact supplied frame_timing.jsonl path>"
export HOMOGRAPHY_RECEIPT="<exact validated image-to-ground receipt path>"
export ENCODER_RECEIPT="<exact encoder receipt path>"
export CALIBRATION_WITNESSES="<exact non-target witness path>"

Run:

Bash
PYTHONHASHSEED=0 python scripts/audit_spot_spray_ego_motion_tracker_v1.py \
  --config configs/benchmark/spot_spray_ego_motion_tracker_v1.yaml \
  --frame-timing "$FRAME_TIMING_JSONL" \
  --homography-receipt "$HOMOGRAPHY_RECEIPT" \
  --encoder-receipt "$ENCODER_RECEIPT" \
  --calibration-witnesses "$CALIBRATION_WITNESSES" \
  --output docs/results/spot_spray_ego_motion_tracker_v1/calibration_only_receipt_v1.json

Expected exit: 0

Expected status:

TRACKER_FROZEN_CALIBRATION_ONLY

11.3 Determinism

Write the second run to a temporary path:

Bash
PYTHONHASHSEED=1 python scripts/audit_spot_spray_ego_motion_tracker_v1.py \
  --config configs/benchmark/spot_spray_ego_motion_tracker_v1.yaml \
  --frame-timing "$FRAME_TIMING_JSONL" \
  --homography-receipt "$HOMOGRAPHY_RECEIPT" \
  --encoder-receipt "$ENCODER_RECEIPT" \
  --calibration-witnesses "$CALIBRATION_WITNESSES" \
  --output /tmp/spot_spray_ego_motion_calibration_only_receipt_v1.json


cmp \
  docs/results/spot_spray_ego_motion_tracker_v1/calibration_only_receipt_v1.json \
  /tmp/spot_spray_ego_motion_calibration_only_receipt_v1.json

Expected:

cmp exits 0;

canonical receipt bytes are identical.

11.4 Result assertions

Programmatically verify:

status == "TRACKER_FROZEN_CALIBRATION_ONLY"

raw_pixel_p95_1m_s > 160.0

positive_sign_gate_violation_count == 0

wrong_sign_gate_violation_count > 0

maximum_dynamic_gate_mm == 45

homography_p95_mm <= 1

homography_max_mm <= 2

daily_drift_mm <= 2

maximum_latch_delta_us <= 250

maximum_encoder_age_ms <= 5

model_loaded == false

target_gt_accessed == false

locked_test_accessed == false

all field/product/chemical claim flags are false.

11.5 Source and scope integrity
Bash
git diff --check
git diff --name-only 9f558b10c6bebfa4c765b395b3dcfc3f5e0e75b9...HEAD

The changed-file set must equal the tracker-lane allowlist in Section 5.1. Any additional path fails this part.

Also verify:

no writes under active full-render roots;

no ideal/degraded prediction file is created;

no threshold-lock file is created or modified;

frozen action files are byte-identical;

no model checkpoint access appears in audit logs;

the final release lock has model_outputs_present: false.

12. Completion criteria

This part is complete only when all are true:

The exact tracker contract exists in configuration and code.

The image-to-ground transform direction and signed encoder sign are explicit and tested.

The dynamic gate is implemented from architecture constants with a hard 45 mm ceiling.

The raw 160 px gate is no longer part of the approved tracker identity.

Association is class-, confidence-, arm-, pair- and GT-blind.

Global assignment and tie-breaking are deterministic.

Frame-gap semantics are unambiguous.

Video reset and invalid-state behavior are fail-closed.

Track labels are stable and evaluator-compatible.

Fragmentation and duplicate exposure remain visible to the frozen action evaluator.

The supplied/bounded calibration witness evidence reproduces raw motion above 160 px.

Positive-sign compensated residuals produce zero gate violations.

Wrong-sign compensation fails.

Two deterministic audit runs are byte-identical.

The calibration receipt and tracker release lock are hash-bound.

No model or locked-test output was accessed.

No field, product or chemical claim is made.

The parent integrator has an exact tracker identity to bind before future inference.

13. Material risks and responses
Scalar encoder does not observe yaw or lateral carrier motion

Risk: curved motion can leave systematic lateral residuals even when longitudinal travel is correct.

Response:

report residual vectors by motion stratum;

never widen the gate from those outcomes;

trigger REPLAN_REQUIRED_2D_EGOMOTION if valid calibration witnesses exceed the gate because of unobserved yaw/lateral motion.

Elevated canopy violates the planar ground assumption

Risk: mask centroids from high canopy points move under the ground homography.

Response:

the frozen gate already includes worst-case 110 mm parallax at the 520 mm minimum working distance;

do not claim the gate proves botanical identity;

if valid residuals still exceed the gate, re-plan height-aware geometry rather than tuning tolerance.

Dense neighbouring masks can remain geometrically ambiguous

Risk: residual-only geometry may swap nearby objects.

Response:

use global one-to-one assignment, not greedy matching;

expose later ID switches and fragmentation to the benchmark;

do not add appearance or class features before fresh independent evidence justifies a new tracker version.

Birth-label lock can preserve an early classification error

Risk: a crop-born track cannot later become weed.

Response:

this is intentionally conservative;

later disagreement receives confidence 0.0;

disagreement is reported;

no target-based relabeling or post-hoc repair is allowed in V1.

Pixel-space/homography mismatch

Risk: a valid matrix applied to the wrong raster silently produces plausible but wrong coordinates.

Response:

bind exact pixel-space and preprocessing hashes;

reject any mismatch before frame processing;

do not infer resize or undistortion.

Partial output after a mid-video fault

Risk: partial predictions could be mistaken for a valid sequence.

Response:

buffer and publish atomically;

invalidate and discard evaluator output for the whole video;

retain only a failure receipt.

14. Rollback

The tracker is additive and isolated.

If calibration-only validation or parent integration fails:

remove or unbind tracker_release_lock_v1.json from the parent release lock;

leave the tracker state unresolved and fail-closed;

retain the failure receipt for diagnosis;

do not reactivate the raw 160 px tracker as an approved fallback;

do not modify the frozen action evaluator;

do not reuse any locked-test output obtained after an invalid bind.

A corrected design must receive a new contract/version identity.

15. Re-plan triggers

Re-plan this part before locked-test inference when any occurs:

No exact validated image-to-ground homography receipt is available.

The homography does not bind the exact inference pixel space.

Homography p95/max or daily drift exceeds 1/2/2 mm.

Encoder resolution, scale, latch or stale limits are not met.

Positive forward encoder travel requires subtracting rather than adding travel to make calibration witnesses stationary.

Positive-sign compensation has any valid witness residual above the frozen dynamic gate.

The wrong-sign negative control does not fail.

Required motion includes reverse travel.

Curved calibration motion requires yaw or lateral state.

Proof speed exceeds 1.0 m/s.

Frame rate, maximum gap, working-distance lower bound or canopy-height upper bound changes.

Multi-camera or cross-video re-identification becomes required.

The frozen action evaluator cannot consume the output without changing class or candidate schema.

Exact duplicate geometry occurs materially and cannot be eliminated by frozen upstream postprocessing.

Parent integration would require class, confidence, arm, pair, GT or renderer trajectory in association.

Any fresh locked-test inference was run before the tracker release lock was sealed.

Any source hash drift is discovered.

16. Stopping rules

Stop after one calibration-only PASS and one immutable tracker release lock.

Do not run parameter sweeps over gate, gap, assignment, centroid definition or label semantics.

Do not use the observed 351.5/454.6 px motion values to tune the gate.

Do not use the registered ideal/degraded references to alter the tracker.

Do not inspect locked-test predictions to decide whether the tracker is acceptable.

Do not widen the gate after a failure.

Do not add optical flow, appearance or 2D pose unless a listed re-plan trigger fires.

Do not run any fresh locked-test inference inside this part.

The terminal successful status for this lane is only:

TRACKER_FROZEN_CALIBRATION_ONLY

It is not field readiness, product readiness or chemical authorization.
