Status: READY
Planner depth: 0
Parent plan: (root plan)

Matched Ideal/Degraded Simulation-Video A/B Protocol Plan

Codex integration scope (2026-08-14): this worker owns the protocol contract,
human-readable protocol, and executable contract assertions only. Packages 2–5
describe downstream renderer/inference/evaluation consumers and are not
implemented or claimed by this lane. The integrated protocol therefore freezes
their interfaces and fails closed while their exact runtime bindings remain
unresolved. Two planner details were refined during repository validation:
`replicate_index` is part of every seed payload to avoid same-cell replicate
collisions, and the primary delta is named a composite capture-profile effect
rather than a blur-only causal effect.

1. Decision

Implement one hash-bound, outcome-blind synthetic-video experiment that evaluates the frozen one-bay spot-spray perception-to-action stack on paired ideal and realistically degraded captures of the same latent scenes.

The experiment shall:

generate exactly one ideal and one degraded video for every latent sequence;

preserve identical scene geometry, plant identities, ground truth, camera trajectory, encoder trajectory, frame timing, and base random draws across the pair;

vary only the capture operators explicitly allowed by this plan;

use the selected foundation checkpoint unchanged;

use one pre-frozen inference and tracking path unchanged across both arms;

select one weed-confidence threshold from degraded calibration videos only;

apply that same threshold to both locked-test arms;

reuse the frozen track-action evaluator without changing its eligibility, confirmation, crop-veto, fire-once, matching, threshold-selection, or safety-rate semantics;

estimate the ideal-versus-degraded effect with paired video-level uncertainty;

treat ideal action F1 0.97 and degraded action F1 near 0.75 only as registered descriptive hypotheses;

never tune scenes, degradation, thresholds, tracking, or the model to approach those hypotheses;

emit synthetic diagnostic evidence only.

A completed experiment may produce only:

SIM_AB_COMPLETE_SYNTHETIC_ONLY;

SIM_AB_CALIBRATION_INFEASIBLE_SYNTHETIC_ONLY;

a named fail-closed invalidity status;

or a named re-plan status.

It shall never emit or imply READY, GO, controlled-capture authority, dry-marker authority, field proof, product proof, deposition proof, crop-injury proof, or chemical-fire authority.

2. Primary bottleneck

The primary bottleneck is not rendering more images. It is preserving a valid temporal causal comparison through four interfaces that are not interchangeable:

persistent source-object identity and ground-truth track identity across video frames;

native-resolution inference for the selected foundation checkpoint without forbidden full-frame resizing;

stable predicted track IDs produced without ground-truth access;

exact reuse of the frozen action evaluator with one shared calibration threshold.

The experiment is invalid if any of these interfaces is invented after outcomes are visible, differs between arms, or cannot be pinned to exact source bytes.

3. Evidence and authority boundary
3.1 Source facts

The implementation base is the clean repository state at main@9f558b10c6bebfa4c765b395b3dcfc3f5e0e75b9. 

tarım-projesi-part-spot-spray-s…

The frozen one-bay architecture establishes one native 2048×2048 RGB ROI, no full-frame digital resize, measured 474–484 mm ground FOV, 170 µs, 15 Hz, one camera, a 64 px outer abstain ring, a 20 mm action service class, one selected foundation checkpoint, and no physical or chemical readiness claim. 

tarım-projesi-part-spot-spray-s…

CropCraft V12 supplies asset-disjoint synthetic validation/test roles, constrained hooded RGB scene profiles, native-detail geometry ranges, visual brightness and clipping gates, and an explicit rule that synthetic roles have zero weight in real selection. Its physical light values are not calibrated. 

tarım-projesi-part-spot-spray-s… +1

V7 supplies evidence for exact-mask paired nuisance generation, linear and smooth-curved motion trajectories, source-scene split isolation, deterministic quality auditing, and the need for a matched control. Its trained sensor-motion challenger improved the single-field motion-blur diagnostic but failed several robustness and non-inferiority gates; the accepted control was unchanged and confirmation was not opened. 

cropcraft_sensor_motion_additiv… +1

The frozen action contract requires persistent predicted track IDs, a validation-only confidence threshold, three confirmations, fire-once behavior, crop veto, one-to-one eligible-track matching, attempted-shot crop and duplicate denominators, and zero synthetic weight in real GO decisions. 

tarım-projesi-part-spot-spray-s…

3.2 Protocol decisions and engineering inferences

The following are decisions made by this plan rather than sourced physical measurements:

32 calibration pairs and 64 locked-test pairs;

30 frames per arm at 15 Hz;

degraded-only threshold calibration;

one shared threshold for both test arms;

stratified paired bootstrap at the latent-video level;

use of V7 trajectory shapes only after rescaling to the frozen architecture’s subpixel physical motion envelope;

exclusion of uncalibrated sensor noise, contamination, defocus, chromatic aberration, compression, channel failure, and severe multi-pixel blur;

use of V12 validation and test asset roles as the calibration/test source boundary;

use of synthetic pseudo-field and pseudo-session identifiers solely to exercise the frozen evaluator’s grouped reporting.

None of these decisions is physical validation.

3.3 Exact authorities to pin

The new protocol shall record and verify exact SHA-256 identities for:

repository base commit 9f558b10c6bebfa4c765b395b3dcfc3f5e0e75b9;

configs/deploy/spot_spray_product_architecture_v1.yaml;

configs/simulation/cropcraft_deploy_constrained_pilot_v12.yaml;

the exact V12 source manifests, release receipts, accepted asset families, and renderer/export implementation used;

configs/benchmark/simulation_sensor_motion_additive_protocol_v7_r1.yaml, expected frozen protocol SHA-256 4654e5e9625f5d2d8e6f8a8df1e4e072f095b24921aad068f226fd8faba94bee;

configs/simulation/cropcraft_sensor_motion_asset_gate_v7_r1.yaml;

the exact V7 selection receipt whose result retains the accepted control;

configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml, expected SHA-256 210e6feddb93ca269d78a9947b48c2a84d0fb382828ba3265ff7debe06b74b09;

scripts/evaluate_spot_spray_target_rig_action_v1.py, expected SHA-256 3943090f5b34d730426bbb23e255757f1af28a89b3bbfc2f5a093a57e8ce9e45;

selected foundation checkpoint SHA-256 3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100;

the accepted native-resolution inference adapter;

the accepted prediction-to-track implementation and its full resolved configuration;

the renderer executable version, build identity, relevant Python environment, and any deterministic post-processing implementation.

Source hashes absent from this plan shall be computed from the exact files reachable at the pinned base or from the pinned external data receipts before any render or model execution. A hash computed after outcomes exist cannot retroactively authorize a changed source.

4. Goals

Isolate the effect of the declared capture degradation while holding latent content and the model stack fixed.

Preserve complete temporal identity at the sequence, frame, object, track, camera, and encoder levels.

Use V12 asset and scene boundaries without presenting V12 as a physically calibrated camera simulator.

Use V7 only for supported nuisance-generation mechanics and quality discipline.

Keep the V7 rejected model challenger out of the experiment.

Evaluate the selected foundation checkpoint as a frozen pre-real model, not as a deployment checkpoint.

Reuse the frozen action evaluator rather than duplicating or weakening its behavior.

Prevent test access from influencing the renderer, capture envelopes, model, tracker, thresholds, metric definitions, or sample selection.

Report segmentation, tracking, and action decomposition without changing the primary action semantics.

Quantify scene-sampling uncertainty through paired sequence resampling.

Produce deterministic manifests, audits, threshold receipts, and results that can be independently regenerated.

Fail closed on source drift, pair mismatch, split leakage, unsupported preprocessing, tracker ambiguity, invalid degradation, missing provenance, or test contamination.

5. Non-goals

This part shall not:

reopen the camera, lens, ROI, FOV, exposure, rate, light architecture, hood, carrier, checkpoint, or action-policy decisions;

train, fine-tune, distill, calibrate, or select a model;

use the V7 sensor-motion challenger checkpoint;

use V7’s original 5–25 px motion kernels as a representation of the frozen one-bay capture;

search degradation magnitudes to make action F1 approach 0.75;

clean, simplify, or brighten ideal frames to make action F1 approach 0.97;

use separate confidence thresholds for ideal and degraded test arms;

tune tracking parameters on calibration or test outcomes;

derive predicted track IDs from ground-truth track IDs;

use semantic connected components as a substitute for persistent source-object truth;

modify the frozen action evaluator or its config;

add synthetic metrics to any real GO decision;

authorize physical capture, dry marker, field operation, product release, purchase, fabrication, deposition, crop safety, or chemical operation;

claim that V12 light parameters reproduce the installed Basler sensor, lens, strobe, hood, Bayer response, noise, or optics;

add unmeasured rain, dust, lens soil, fogging, vibration, rolling shutter, dropped frames, compression, severe defocus, channel outage, or electronic noise to V1;

use test renders, labels, predictions, or metrics to choose seeds or replace failed pairs;

extend V1 sample counts after seeing a wide interval or an inconvenient result;

treat a synthetic pseudo-field as a real field, session, season, camera, or country.

6. Resolved experimental design
6.1 Experimental unit

The sole paired experimental unit is one complete latent video sequence.

A pair_id binds:

one source scene graph;

all crop and weed source-object identities;

all object geometry, material, phenotype, pose, and world transforms;

ground, tillage, environment, and ambient-light state;

one camera mid-exposure trajectory;

one encoder trajectory;

one exact frame clock;

one set of per-frame visible and amodal ground truth;

one capture-nuisance draw vector;

one ideal arm;

one degraded arm.

Frames are repeated observations within a pair. They are not independent experimental units.

The two arms shall have bit-identical:

frame count;

latent frame IDs;

timestamps;

encoder positions;

camera mid-exposure poses;

world geometry;

object transforms;

GT instance classes;

GT instance IDs;

GT track IDs;

GT polygons and masks;

canopy spans;

visibility and occlusion values;

split, synthetic field, synthetic session, and latent video grouping.

Only the allowlisted capture operator may differ.

6.2 Pair and seed identity

Canonical identities shall use SHA-256 over canonical UTF-8 JSON with:

recursively sorted keys;

no NaN or infinity;

physical decimals represented as canonical decimal strings;

compact separators;

one final newline in identity-bearing files;

no timestamps, absolute paths, random UUIDs, or host-specific values in identity payloads.

Use separate deterministic seed channels:

scene_seed;

trajectory_seed;

capture_draw_seed;

renderer_seed;

audit_sample_seed.

Each seed shall be derived from:

SHA256(protocol_id | split | cell_id | replicate_index | candidate_index | channel_name | V12_split_base_seed)

`replicate_index` is mandatory. Without it, replicate slots in one experimental
cell would derive the same candidate stream and violate the allocation and seed
uniqueness contracts.

where the V12 split base is:

440000 for calibration;

540000 for locked test.

No raw seed may appear in more than one split or channel.

Define:

latent_id from the protocol identity, split, cell, replicate index, accepted candidate index, scene seed, and trajectory seed;

pair_id = latent_id;

arm_id = SHA256(pair_id | capture_profile_id);

frame_id = arm_id + ":" + zero_padded_frame_index;

latent_frame_id = pair_id + ":" + zero_padded_frame_index;

GT track IDs prefixed by pair_id;

predicted track IDs prefixed by arm_id or video ID.

6.3 Allocation

Use three balanced factors:

Factor	Levels
Travel speed	0.5 m/s, 1.0 m/s
V12 scene profile	hood_dry_nominal, hood_moist_glare_challenge
Degraded motion path	linear, smooth_curved

This creates 8 cells.

Allocate:

Split	Replicates per cell	Latent pairs	Arms per pair	Frames per arm	Rendered frames
Calibration	4	32	2	30	1,920
Locked test	8	64	2	30	3,840
Total	—	96	2	30	5,760

The ideal arm remains paired with the degraded motion-path stratum even though the ideal capture operator does not apply motion integration. This preserves balanced one-to-one pairing and prevents post-outcome regrouping.

6.4 Temporal contract

For every arm:

frame rate: exactly 15 Hz;

frame count: exactly 30;

frame indices: 0 through 29;

timestamp rule: timestamp_ns(i) = round(i × 1,000,000,000 / 15);

encoder rule: derive signed forward encoder distance from exact speed and timestamp using integer or rational arithmetic before canonical decimal serialization;

camera trajectory: constant nominal forward speed plus the frozen shared pose offsets;

scene-strip length: at least total camera travel plus maximum ground FOV plus 100 mm guard;

no reverse motion;

no frame drops;

no duplicated timestamps;

no non-monotonic encoder value;

no interpolated or synthesized missing frame;

no arm-specific frame clock or camera pose.

Thirty frames provide a two-second sequence and allow the frozen three-confirmation and preferred five-frame temporal behavior to be exercised without claiming that every GT track will remain visible for five frames.

6.5 Split and grouping contract

Use only the V12 validation role as the calibration source role and only the V12 test role as the locked-test source role.

The following may not cross calibration and test:

asset identity;

crop model variant identity;

weed asset identity;

ground family;

environment family;

source scene;

source seed;

trajectory seed;

nuisance seed;

latent pair;

video;

GT track.

Use split-prefixed synthetic grouping IDs:

calibration fields: sim_cal_field_00 through sim_cal_field_03;

test fields: sim_test_field_00 through sim_test_field_03;

sessions shall be unique within split, field slot, and V12 scene profile;

each latent pair is one video;

ideal and degraded arms have distinct video IDs but the same pair_id;

no video, frame, or track may span evaluator validation and test roles.

These IDs exist only to exercise the frozen evaluator’s grouped checks. Reports shall call them synthetic_field_strata and synthetic_session_strata, never real fields or sessions.

6.6 Deterministic candidate selection before outcomes

For each required cell and replicate slot:

enumerate candidate seeds in the frozen derived order;

generate the latent scene and both arm renders;

apply only the predeclared source, geometry, GT, and pixel realism gates;

accept the first candidate that passes every pre-outcome gate;

record every rejected candidate seed, exact failure reason, and audit hash;

stop after 10 candidate attempts for a slot.

Candidate selection may not use:

model inference;

confidence values;

predicted masks;

predicted tracks;

action outcomes;

segmentation metrics;

tracking metrics;

action metrics;

similarity to the 0.97 or 0.75 hypotheses;

human preference among multiple passing candidates.

If any required slot lacks a passing candidate after 10 attempts, stop with SIM_AB_INVALID_INSUFFICIENT_PREOUTCOME_CANDIDATES. Do not reduce counts, borrow another cell, or widen the envelope.

7. Shared latent scene and geometry envelope
7.1 Source assets

Use the V12 validation/test asset families and the V11-derived scene diversity inherited by V12. Do not introduce new crop, weed, soil, HDRI, residue, or botanical assets in this part.

Use the source renderer scene graph, not the processed semantic connected-region proxy, as the GT authority.

A valid source renderer must expose persistent per-plant object identity. If the available V12 path has only RGB and semantic masks and cannot export stable source-object identities, stop with REPLAN_REQUIRED_GT_TRACK_IDENTITY.

7.2 Shared camera geometry

Both arms share the exact values sampled for each pair from these source-compatible bounds:

Variable	Frozen pair envelope
Native raster	2048×2048
Ground FOV	474–484 mm
Working distance	550–590 mm
Roll	-1° to +1°
Pitch	-1° to +1°
Yaw	-4° to +4°
Lateral camera offset	0.01–0.10 m
Focus reference plane	55 mm above ground
Test height references	0, 55, 110 mm above ground
Outer action abstain ring	64 px
Exposure metadata	170 µs
Acquisition rate	15 Hz
Shutter	global
Travel speed	cell-fixed 0.5 or 1.0 m/s

The working-distance range is the intersection of the frozen product range and V12’s range. The product FOV range overrides V12’s nominal 0.50 m rendering width.

Continuous variables shall use deterministic Latin-hypercube allocation within each cell:

with n=4 strata for calibration;

with n=8 strata for locked test;

with one deterministic permutation per variable derived from the protocol seed;

using stratum midpoint values;

with no reallocation after model outputs.

7.3 Shared scene profiles

Use the common calibration/test intersection of V12 profile ranges.

hood_dry_nominal:

Variable	Range
Environment strength	0.03–0.07
Soil moisture	0.08–0.35
Sun energy	0.00–0.03
Sun elevation	30–68°
Sun angle	8–12°
Local shadow fraction	0.00–0.04
Artificial light energy envelope	35–55 renderer units
Artificial light size	0.50–0.72 m
Artificial light warmth	0.30–0.52

hood_moist_glare_challenge:

Variable	Range
Environment strength	0.05–0.09
Soil moisture	0.38–0.78
Sun energy	0.02–0.05
Sun elevation	15–55°
Sun angle	7–12°
Local shadow fraction	0.02–0.08
Artificial light energy envelope	30–48 renderer units
Artificial light size	0.58–0.80 m
Artificial light warmth	0.40–0.70

The artificial-light values remain renderer proxies. They are not lumens, irradiance, CCT, CRI, current, or installed strobe measurements.

8. Capture arms
8.1 Ideal arm: IDEAL_CAPTURE_UPPER_BOUND_V1

The ideal arm is an intentionally idealized optical upper-bound proxy, not a claim about achievable installed camera output.

It shall use:

the shared scene, geometry, camera pose, timestamp, and encoder state;

one point sample at the exposure midpoint rather than temporal integration;

no motion PSF;

four equal all-on light quadrants;

profile-specific midpoint artificial-light settings;

fixed neutral white-balance gains;

gain metadata 0 dB;

deterministic common tone mapping;

no sensor noise;

no compression;

no lens contamination;

no defocus perturbation;

no chromatic aberration;

no vignetting perturbation;

no dropped frame;

no rolling shutter;

lossless RGB8 sRGB PNG proxy output.

Profile-specific ideal artificial-light values are the exact midpoints:

Profile	Energy	Size	Warmth
Dry nominal	45.0	0.61 m	0.41
Moist/glare	39.0	0.69 m	0.55

The ideal arm shall retain scene occlusion, plant overlap, soil variation, ambient variation, off-axis pose, height variation, and model-domain limitations. It is not a GT raster or a simplified segmentation cartoon.

8.2 Degraded arm: DEGRADED_CAPTURE_PROXY_V1

The degraded arm shall use:

the same shared latent frame and mid-exposure camera pose;

global-shutter temporal integration during one light pulse;

pulse width sampled from 150–170 µs;

profile-specific V12 artificial-light settings sampled by the frozen Latin-hypercube allocation;

one cell-fixed motion path family: linear or smooth_curved;

exact projected forward-travel direction as the dominant motion direction;

a normalized subpixel PSF;

V7-compatible deterministic trajectory generation mechanics;

V7-compatible reflect_101 convolution border behavior if a post-render convolution path is used;

the same deterministic tone mapper and lossless output format as the ideal arm.

The physical translational integration length shall be calculated from:

blur_px = speed_m_s × pulse_width_us × 0.001 / gsd_mm_per_px

where:

gsd_mm_per_px = ground_fov_mm / 2048

Rules:

total PSF path length shall not exceed 0.75 px;

PSF weights shall sum to 1.0 within numeric tolerance;

PSF centroid error shall be no greater than 0.15 px;

the linear path shall follow the projected camera travel direction;

the smooth-curved path shall use the pinned V7 curve generator rescaled to the same physically calculated path length;

no original V7 5–25 px kernel length is permitted;

no random 0–180° blur angle is permitted;

no post-outcome rescaling is permitted;

no extra Gaussian blur shall be added;

no effect absent from the degraded V1 allowlist shall be introduced.

The degraded arm is a bounded capture proxy. Because sensor response, lens MTF, installed light uniformity, noise, contamination, and defocus are not physically calibrated, this arm does not establish absolute camera realism.

8.3 Pair-difference allowlist

The only permitted arm differences are:

temporal integration enabled versus disabled;

sampled pulse width versus ideal midpoint impulse;

linear or smooth-curved subpixel PSF versus no PSF;

profile-sampled artificial-light energy, size, and warmth versus fixed profile midpoints;

resulting RGB pixel values;

arm-prefixed frame and video identities;

capture-profile metadata.

Any other arm difference invalidates the pair.

9. Ground-truth contract
9.1 Required persistent truth

For every plant source object, export:

stable source-object ID;

stable GT track ID;

class name: crop or weed;

per-frame visible polygon or mask;

per-frame amodal identity reference where supported;

visible fraction;

occluded flag;

partial flag;

canopy span in millimetres;

world transform;

source asset identity.

GT track IDs shall come from persistent scene objects. They shall not be reconstructed from per-frame semantic connected components.

9.2 Action-compatible observation fields

The synthetic capture manifest shall populate the frozen evaluator fields:

frame_id;

image_path;

field_id;

session_id;

video_id;

frame_index;

timestamp_ns;

encoder_mm;

exposure_us;

gain_db;

working_distance_mm;

strobe_profile_id;

split;

instances;

instance track_id;

instance class_name;

instance polygon;

visible_fraction;

canopy_span_mm;

partial;

occluded.

Use evidence_scope: synthetic_fixture.

9.3 Safe-region treatment

For action evaluation:

an observation whose visible instance polygon is clipped by the image boundary is partial=true;

an observation whose canonical GT interior action region does not enter the central 1920×1920 region after the 64 px outer ring is removed is partial=true;

a track may still become eligible if a later observation satisfies all frozen eligibility conditions inside the safe region;

canopy span is determined in world millimetres, not inferred from a resized model input;

segmentation diagnostics may report border observations separately, but they may not change the action denominator.

9.4 Decisive GT discovery rule

Before rendering the full experiment, Codex shall verify that the pinned V12 renderer path can provide:

stable object IDs across frames;

valid per-frame polygons or masks;

canopy span in world units;

a defensible visibility or occlusion field;

split-pure asset provenance.

If stable object identity or required physical-size metadata cannot be produced without inventing labels from per-frame connected components, stop with REPLAN_REQUIRED_GT_TRACK_IDENTITY.

10. Pre-outcome realism and integrity gates

All gates in this section are independent of model outputs.

10.1 Source and environment gates

Require:

every pinned source hash matches;

selected checkpoint hash matches;

renderer and environment identities match the protocol;

no unpinned asset or source path is loaded;

no asset or seed crosses calibration/test;

all generated files reside under a versioned V1 output root;

no existing V1 release is overwritten.

10.2 Pair identity gates

For every pair, assert:

exactly two arms;

exactly 30 frames per arm;

identical latent frame ID sequence;

identical timestamp sequence;

identical encoder sequence;

identical camera mid-exposure poses;

identical GT instance and track tables;

bit-identical GT masks and polygons after canonical serialization;

identical class, canopy-span, visibility, partial, and occlusion fields;

no missing or extra frame;

no duplicated frame or track ID;

pair differences limited to the capture allowlist.

A single locked pair failure invalidates the full release. Do not drop the pair from analysis.

10.3 Pixel and visual gates

Apply separately to both arms and both splits:

native dimensions exactly 2048×2048;

lossless decode succeeds;

no full-frame resize;

mean frame brightness between 40 and 205;

fully clipped-white fraction no greater than 0.002;

fully clipped-black fraction no greater than 0.001;

crop-free frame fraction no greater than 0.05;

weed-free frame fraction no greater than 0.25;

mean crop fraction between 0.01 and 0.60;

mean weed fraction between 0.01 and 0.50;

at least 6 crop model variants per split;

at least 2 ground families per split;

at least 2 environment families per split;

both declared scene profiles present in exact balanced counts;

no exact RGB duplicate across distinct latent frames;

no ideal/degraded pair with exact-identical RGB bytes;

every degraded PSF passes normalization, path-length, and centroid gates;

exact GT reuse across arms;

deterministic output on rerender in the pinned environment.

10.4 Temporal and denominator gates

Require before release lock:

at least 64 eligible GT weed tracks in calibration;

at least 128 eligible GT weed tracks in locked test;

at least one eligible GT weed track in every synthetic test field stratum;

monotonic timestamps and encoder positions;

every eligible GT track belongs to exactly one pair and one split;

no GT track crosses video boundaries;

no adjacent frames of a source sequence cross calibration/test;

at least three GT observations are available for a nonzero subset of eligible tracks in every experimental cell.

These minima are benchmark-operability gates, not model success gates.

10.5 Human review boundary

Human visual review is permitted only for a frozen calibration review sample selected before model execution:

exactly two calibration pairs per experimental cell;

both arms shown side by side;

fixed sample IDs derived from audit_sample_seed;

review limited to renderer corruption, class/track overlay correctness, obvious pair mismatch, and capture-envelope violations;

no model prediction overlay;

no threshold or metric;

no choosing between multiple passing renders.

Locked-test RGB pixels shall receive machine audit only until the threshold receipt is sealed. If a machine audit fails, the release is invalid; do not manually choose substitute test pairs.

11. Model, inference, and tracker compatibility contract
11.1 Frozen model

Use only the checkpoint with SHA-256:

3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100

Its role remains:

directional_pre_real_candidate_not_deployment_proof

Forbidden changes include:

weight modification;

fine-tuning;

model surgery;

test-time augmentation;

arm-specific preprocessing;

arm-specific confidence thresholds;

stochastic augmentation;

outcome-driven NMS or mask filtering;

checkpoint fallback;

substitution of the V7 semantic model or challenger.

11.2 Native inference requirement

The inference path shall:

consume the native 2048×2048 simulation frame;

avoid full-frame digital resizing;

preserve the architecture’s 64 px outer abstain behavior;

use the same tiling, halo, merge, class map, mask post-processing, action-point derivation, and numeric precision for both arms;

emit the frozen prediction JSONL fields;

bind predictions to exact image and checkpoint hashes.

A narrow format adapter may be added if it changes no masks, confidences, classes, action points, or predicted track IDs.

11.3 Stable tracker requirement

The tracker shall:

be fixed before any calibration model output;

use no GT masks, polygons, classes beyond predicted classes, GT IDs, pair labels, or arm labels;

use the same code and resolved parameters for both arms;

output stable predicted track IDs;

restart state at every video boundary;

never reuse a predicted track ID across videos;

preserve fire-once behavior through the frozen evaluator rather than pre-removing duplicate actions;

expose fragmentation rather than repairing it with GT.

11.4 Smallest bounded compatibility discovery

Codex shall inspect only the existing target-rig model pipeline and directly referenced inference/tracking components for:

native 2048² inference;

selected-checkpoint loading and hash verification;

prediction JSONL emission;

action-point production;

64 px abstain behavior;

stable predicted track IDs;

deterministic resolved configuration.

Acceptance requires one exact compatible lineage whose files and config can be pinned.

Outcomes:

compatible inference and tracker found: pin them and continue;

compatible inference exists but only a lossless output-format adapter is missing: implement the adapter and continue after equivalence tests;

inference performs forbidden full-frame resize: stop with REPLAN_REQUIRED_NATIVE_INFERENCE;

no stable tracker exists: stop with REPLAN_REQUIRED_TRACKER_CONTRACT;

more than one materially different unresolved path exists: stop with REPLAN_REQUIRED_AMBIGUOUS_INFERENCE_PATH;

tracker or adapter requires GT information: reject it and stop.

This part shall not invent or tune a new tracker if the bounded discovery fails.

11.5 Determinism preflight

Before full inference:

run the exact model and tracker twice on four calibration pairs covering all speeds and scene profiles;

sort and canonicalize predictions;

round serialized floating values only at the declared canonical precision, no coarser than 1e-6;

require identical candidate counts, classes, IDs, frame coverage, and canonical prediction hashes;

require exact checkpoint and manifest binding.

Failure produces SIM_AB_INVALID_NONDETERMINISTIC_INFERENCE.

12. Calibration and test locking
12.1 Lock order

The order is mandatory:

freeze protocol sources, config, seeds, cells, capture envelopes, metric definitions, and code hashes;

generate both arms for all calibration and test pairs;

audit all sources, pair identities, GT, and machine realism gates;

complete the permitted calibration-only manual review;

write and hash the immutable release manifest;

prevent test prediction generation;

run inference and tracking on degraded calibration only;

select the weed-confidence threshold with the frozen evaluator;

write and hash the threshold-lock receipt;

optionally compute ideal calibration diagnostics without changing any input;

unlock test inference;

run both test arms;

compute paired metrics and uncertainty once;

seal the final result.

12.2 Threshold source

Only degraded calibration predictions may select the weed-confidence threshold.

Use the frozen evaluator exactly:

threshold grid 0.05 through 0.95;

step 0.05;

maximize recall subject to frozen precision, crop-hit, crop-hit upper-bound, and duplicate-shot constraints;

frozen tie breakers;

frozen fallback when no feasible threshold exists;

crop confidence threshold remains 0.25;

minimum confirmations remains 3;

preferred window remains 5;

fire once per predicted track remains enabled.

The ideal calibration arm is diagnostic only and has no selection weight.

12.3 One shared threshold

The same selected threshold shall be applied to:

ideal locked test;

degraded locked test;

segmentation diagnostics in both arms;

tracking diagnostics in both arms.

Separate arm thresholds are forbidden.

12.4 Frozen-evaluator invocation

Do not modify the frozen evaluator.

Preferred orchestration:

build one ideal evaluation manifest whose validation section is the degraded calibration set and whose test section is the ideal locked-test set;

build one degraded evaluation manifest whose validation section is the same degraded calibration set and whose test section is the degraded locked-test set;

provide the exact same degraded calibration prediction bytes to both evaluator runs;

require both runs to select the same threshold and emit identical calibration statistics;

fail if threshold or calibration receipt differs.

This approach allows exact evaluator reuse even if it does not expose a fixed-threshold CLI override.

12.5 Infeasible calibration

If no threshold satisfies the frozen calibration safety constraints:

retain the evaluator’s validation-only maximum-F1 fallback threshold;

set calibration_feasible=false;

set result status SIM_AB_CALIBRATION_INFEASIBLE_SYNTHETIC_ONLY;

continue locked-test evaluation only as a descriptive benchmark;

do not alter the degradation envelope, tracker, model, threshold grid, or sample set;

do not label the fallback threshold safe.

13. Prediction and action contracts
13.1 Prediction format

The prediction stream shall retain the frozen required fields:

metadata record first;

schema version;

model checkpoint SHA-256;

capture manifest SHA-256;

capture audit SHA-256;

frame records covering every required frame exactly once;

candidate predicted track ID;

class name;

confidence;

polygon;

weed action point.

Predictions shall exactly cover calibration and test frames required by each evaluator manifest.

13.2 Action semantics

The new protocol shall not reinterpret:

eligible weed track;

20 mm minimum canopy span;

0.70 minimum visible fraction;

non-partial requirement;

denominator freeze when any observation becomes eligible;

minimum three confirmations;

crop veto;

confirmation-frame action point;

fire once per predicted track;

crop-collision precedence;

one-to-one eligible-track matching;

partial/unknown hit as false positive;

repeat hit as duplicate and false positive;

background hit as false positive;

noneligible nonpartial weed treatment;

attempted-shot crop-hit and duplicate denominators;

Wilson upper confidence behavior.

The frozen evaluator output is the authority for action counts and rates.

14. Estimands
14.1 Registered descriptive hypotheses

The hypotheses attach only to pooled locked-test action F1:

ideal action F1 reference: 0.97;

degraded action F1 reference: 0.75.

For each, report:

observed action F1;

observed minus reference;

confidence interval for the observed F1.

Do not define a “near” acceptance band. Do not accept, reject, tune, rerender, extend, or promote based on closeness to either reference.

14.2 Primary estimand

Primary estimand:

Δ_action_F1 = action_F1_degraded - action_F1_ideal

on the full locked-test set, using:

the same selected threshold;

the same model;

the same inference path;

the same tracker;

the same frozen evaluator;

paired latent videos.

Negative values indicate worse action F1 under degraded capture.

14.3 Secondary action estimands

Report each arm and paired delta for:

action precision;

action recall;

action F1;

true-positive fire count;

false-positive fire count;

false-negative eligible-track count;

attempted fire count;

crop-hit count and rate;

crop-hit Wilson upper 95% bound;

duplicate-shot count and rate;

selected confidence threshold;

eligible GT weed track count;

calibration feasibility.

Report pooled locked-test values and descriptive values by:

speed;

V12 scene profile;

degraded motion path;

synthetic field stratum.

Per-stratum values are descriptive and shall not create new acceptance rules.

14.4 Segmentation estimands

Using the locked weed threshold and frozen crop threshold:

rasterize predicted and GT polygons at native 2048²;

perform deterministic one-to-one same-class matching within each frame by descending mask IoU;

require mask IoU ≥0.50 for a matched instance true positive;

break exact ties by canonical GT ID and predicted ID;

exclude partial_unknown from primary class denominators;

report border/partial observations separately.

Report for crop and weed:

instance-mask precision at IoU 0.50;

instance-mask recall at IoU 0.50;

instance-mask F1 at IoU 0.50;

mean matched mask IoU;

median matched mask IoU;

unmatched GT count;

unmatched prediction count.

Report macro crop/weed instance-mask F1 as a secondary segmentation summary.

These are benchmark decomposition metrics. They do not replace action F1.

14.5 Tracking estimands

Build the GT/predicted track overlap table from the frame-level same-class IoU matches.

Use deterministic one-to-one track assignment maximizing matched observation count, with ties broken by canonical IDs.

A track match qualifies for the three-confirmation diagnostic when it contains at least three matched observations.

Report:

track_precision_3;

track_recall_3;

track_F1_3;

fraction of eligible GT tracks receiving at least three matched predicted observations;

predicted tracks reaching three confirmations;

eligible-track fragmentation rate;

mean fragments per matched eligible GT track;

ID-switch count;

ID switches per eligible GT track;

median consecutive matched observations;

fraction of eligible GT tracks with at least five consecutive matched observations.

The action evaluator remains authoritative for actual fire-once and duplicate-shot outcomes.

14.6 Pair-level sufficient statistics

For every pair and arm, retain sufficient counts needed to recompute:

segmentation precision, recall, and F1;

track precision, recall, and F1;

action precision, recall, and F1;

crop-hit rate;

duplicate-shot rate.

Do not bootstrap already rounded scalar metrics when exact counts can be resummed.

15. Uncertainty contract
15.1 Sampling unit

Uncertainty shall resample pair_id, never individual frames, instances, or fire events.

This preserves within-video temporal dependence and ideal/degraded pairing.

15.2 Bootstrap

Use a stratified paired cluster bootstrap:

10,000 resamples;

bootstrap seed 1729;

strata are the exact 8 speed × scene-profile × motion-path cells;

within every stratum, sample locked-test pair IDs with replacement;

include both arms whenever a pair is sampled;

sum sufficient counts and recompute each metric;

keep the calibration-selected threshold fixed;

do not recalibrate inside bootstrap samples.

Report percentile 95% intervals from the 2.5 and 97.5 percentiles.

15.3 Interval scope

The paired bootstrap represents variability across the bounded synthetic latent-video sample only.

It does not represent:

model-training seed uncertainty;

checkpoint uncertainty;

renderer-model uncertainty;

real camera variation;

field, farm, crop, season, country, weather, lens, strobe, carrier, or operator uncertainty;

deposition or biological outcome uncertainty.

15.4 Null and unstable denominators

Do not coerce undefined rates to zero.

If a bootstrap replicate has an undefined denominator:

emit null for that metric in the replicate;

compute the interval from valid replicates only;

report the valid replicate count.

If more than 1% of bootstrap replicates are undefined for a metric:

omit its interval;

set uncertainty_status=UNSTABLE_DENOMINATOR;

report the point estimate and exact counts only.

The frozen evaluator’s Wilson crop-hit upper bound remains authoritative for its safety-rate output and shall not be replaced by the bootstrap interval.

16. Canonical artifacts and interfaces
16.1 Preferred minimal repository layout

Implement the following bounded artifacts:

configs/benchmark/spot_spray_simulation_video_ab_protocol_v1.yaml

scripts/build_spot_spray_simulation_video_ab_v1.py

scripts/audit_spot_spray_simulation_video_ab_v1.py

scripts/evaluate_spot_spray_simulation_video_ab_v1.py

tests/test_spot_spray_simulation_video_ab_v1.py

docs/SPOT_SPRAY_SIMULATION_VIDEO_AB_PROTOCOL_V1.md

Codex may merge builder and auditor implementation into one script only if all declared CLI stages, fail-closed behaviors, outputs, and tests remain independently observable.

Do not modify:

the integrated architecture config;

V12;

V7;

the selected checkpoint;

the frozen action config;

the frozen action evaluator;

unrelated model, training, capture, acceptance, or product artifacts.

16.2 Protocol config sections

The canonical YAML shall contain:

schema_version;

protocol_id;

scope;

source_lock;

claim_boundary;

registered_hypotheses;

pairing_contract;

seed_derivation;

allocation;

shared_latent_envelope;

ideal_capture_profile;

degraded_capture_profile;

preoutcome_gates;

gt_contract;

inference_contract;

tracker_contract;

calibration_contract;

action_evaluator_binding;

segmentation_estimands;

tracking_estimands;

action_estimands;

uncertainty;

output_contract;

failure_states;

stopping_rules.

Reject unknown top-level keys unless explicitly designated as metadata.

16.3 Generated local outputs

Under one versioned data root, generate:

pair_manifest_v1.jsonl;

source_lock_receipt_v1.json;

candidate_rejection_ledger_v1.jsonl;

preoutcome_audit_v1.json;

calibration_review_manifest_v1.json;

release_lock_v1.json;

degraded_calibration_predictions_v1.jsonl;

threshold_lock_v1.json;

ideal_test_predictions_v1.jsonl;

degraded_test_predictions_v1.jsonl;

ideal_action_result_v1.json;

degraded_action_result_v1.json;

paired_metric_result_v1.json;

reproduction_receipt_v1.json.

Large RGB frames and model outputs remain outside Git.

Small repository result summaries may be added only if separately authorized by the implementing task. This plan does not require committing generated results.

16.4 Release-lock receipt

The immutable release receipt shall bind:

protocol config SHA-256;

source-lock receipt SHA-256;

renderer and environment identities;

pair manifest SHA-256;

exact counts;

split counts;

cell counts;

GT identity digest;

ideal image-set digest;

degraded image-set digest;

pre-outcome audit SHA-256;

calibration review manifest SHA-256;

locked-test access state;

model_outputs_present=false.

16.5 Threshold-lock receipt

The threshold receipt shall bind:

release-lock SHA-256;

checkpoint SHA-256;

inference code and resolved config SHA-256;

tracker code and resolved config SHA-256;

degraded calibration prediction SHA-256;

frozen action config and evaluator SHA-256;

exact threshold;

feasibility flag;

calibration sufficient counts;

calibration evaluator result SHA-256;

test_predictions_present=false.

16.6 Final paired result

The final result shall include:

final status;

complete source identities;

release and threshold receipt hashes;

both evaluator result hashes;

shared selected threshold;

proof that calibration inputs were identical between evaluator runs;

all primary and secondary point estimates;

paired deltas;

bootstrap intervals and valid replicate counts;

per-cell descriptive results;

hypothesis-reference differences;

all claim-boundary flags set false;

explicit statement that synthetic evidence has zero real GO weight.

17. Failure behavior and edge cases
17.1 Source drift

If any pinned source, checkpoint, renderer, inference component, tracker, config, or evaluator differs:

stop before outcomes;

emit SIM_AB_INVALID_SOURCE_DRIFT;

record expected and observed identities;

do not substitute a nearby version.

17.2 Pair mismatch

If any arm differs in latent frames, trajectory, timestamps, encoder values, GT, or grouping:

emit SIM_AB_INVALID_PAIR_MISMATCH;

invalidate the entire release;

do not analyze surviving pairs.

17.3 Split leakage

Any shared asset, source scene, seed, video, frame, or track across calibration/test produces:

SIM_AB_INVALID_SPLIT_LEAKAGE

No exception is permitted for visually different renders of the same latent source.

17.4 Missing persistent truth

If source-object GT cannot produce stable temporal IDs or required action fields:

REPLAN_REQUIRED_GT_TRACK_IDENTITY

Do not use connected components, optical flow, or the model tracker to construct GT tracks.

17.5 Inference or tracker incompatibility

Use the re-plan states defined in Section 11.4. Do not weaken native-resolution or stable-ID requirements.

17.6 Missing arm frame

Before release lock, the candidate may fail and the deterministic candidate sequence may advance.

After release lock:

no pair may be repaired or replaced;

the release is revoked;

V1 results are not produced.

17.7 Identical ideal and degraded RGB

An exact-identical arm pair fails the degraded-effect gate before release lock. Do not increase degradation based on model results; inspect only capture-operator execution.

17.8 Degraded arm outperforming ideal

A degraded arm may legitimately outperform the ideal arm through model-domain effects.

If:

source;

pair;

capture;

preprocessing;

tracker;

threshold;

and evaluator audits all pass,

report the positive delta as observed. Do not reverse labels, add degradation, rerender, or assume the result is invalid.

17.9 No feasible threshold

Follow Section 12.5. The benchmark may complete descriptively but shall carry the infeasible-calibration status.

17.10 No attempted action

Preserve the frozen evaluator’s count and null behavior. Do not invent precision or crop-hit values.

17.11 Post-lock implementation defect

A genuine implementation defect may justify revocation only when it violates a frozen contract independently of model outcomes.

Required response:

mark V1 release and dependent receipts revoked;

preserve all old bytes;

document the exact defect;

prove that capture envelopes, seeds, hypotheses, estimands, and acceptance rules did not change;

create a versioned V2 release;

rerun from the same deterministic seed derivation where possible.

Never silently overwrite V1.

18. Rejected alternatives
Separate ideal and degraded thresholds

Rejected because arm-specific calibration would mix capture sensitivity with threshold optimization and could hide degraded confidence shift.

Pooled ideal-plus-degraded threshold calibration

Rejected because the easier arm could compensate for degraded-arm safety or recall failures. Degraded-only calibration is the conservative operationally relevant choice.

Calibrating on ideal and applying to degraded

Rejected because it would knowingly select the threshold on the less difficult arm.

V7 original 5–25 px kernels

Rejected because they exceed the frozen architecture’s subpixel blur envelope and were created for a different development nuisance study.

V7 sensor-motion challenger checkpoint

Rejected because its selection receipt kept the accepted control unchanged after robustness regressions.

Independent random scenes for the two arms

Rejected because scene variability would dominate the capture effect and break paired inference.

Frame-level random split

Rejected because it leaks scene, trajectory, track, and adjacent-frame information across calibration/test.

GT-derived predicted track IDs

Rejected because it eliminates the tracking problem and invalidates fragmentation and duplicate-shot evidence.

Semantic connected-component GT tracks

Rejected because per-frame components can merge or split and are not persistent source-object identities.

Full-frame resize to the checkpoint raster

Rejected by the frozen architecture and because it would change the native-detail question being measured.

Adding severe blur or uncalibrated noise to reach degraded F1 near 0.75

Rejected as direct target-driven tuning.

Extending test pairs after observing uncertainty

Rejected because it creates an outcome-conditioned sample size. A larger experiment requires a separately frozen V2 protocol.

Treating synthetic fields as deployment breadth

Rejected because synthetic grouping is evaluator plumbing, not real field evidence.

19. Ordered implementation packages
Package 0 — Pin sources and resolve decisive compatibility

Outcome: prove that the experiment can preserve persistent GT, native inference, and stable prediction tracks before any full render.

 - [ ] Verify the repository base is 9f558b10c6bebfa4c765b395b3dcfc3f5e0e75b9.

 - [ ] Compute and record exact hashes for the architecture, V12, V7, action, renderer, and environment sources.

 - [ ] Verify the selected foundation checkpoint bytes match 3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100.

 - [ ] Verify the V7 selection receipt retains the accepted control and does not authorize its challenger.

 - [ ] Inspect the V12 renderer/export path for persistent source-object IDs, masks/polygons, canopy span, and visibility metadata.

 - [ ] Inspect only the existing target-rig inference and tracking lineage for native 2048², no full-frame resize, 64 px abstention, prediction JSONL, action points, and stable predicted track IDs.

 - [ ] Pin one exact inference path and one exact tracker path.

 - [ ] Run a four-pair synthetic smoke fixture through the proposed interfaces without generating experiment outcomes.

 - [ ] Emit source_lock_receipt_v1.json.

 - [ ] Stop with the exact re-plan status if persistent GT, native inference, or stable tracking is absent.

Acceptance evidence:

all required source identities recorded;

checkpoint identity verified;

one unambiguous compatible inference/tracker lineage;

no GT consumed by prediction tracking;

no frozen upstream file modified;

compatibility receipt status PASS.

Package 1 — Implement the canonical protocol contract

Outcome: one machine-readable authority defines all seeds, cells, envelopes, gates, estimands, and stopping rules before rendering.

 - [x] Add configs/benchmark/spot_spray_simulation_video_ab_protocol_v1.yaml.

 - [x] Encode exactly 32 calibration and 64 test pairs.

 - [x] Encode exactly 30 frames, 15 Hz, and the eight balanced cells.

 - [x] Encode the canonical seed and identity rules.

 - [x] Encode shared latent, ideal, and degraded envelopes.

 - [x] Encode the V12 profile intersections and V7 subpixel motion use.

 - [x] Encode all pre-outcome gates.

 - [x] Encode degraded-only calibration and one shared threshold.

 - [x] Encode the segmentation, track, action, and bootstrap estimands.

 - [x] Encode all claim-boundary flags as false.

 - [x] Reject unknown or duplicate YAML keys through the executable contract test.

 - [x] Add unit tests for config parsing and forbidden values.

Acceptance evidence:

config parses deterministically;

exact expected counts derive from the config;

changing a hypothesis value cannot affect seeds, capture parameters, thresholds, or gates;

any V7 kernel length above the calculated 0.75 px cap is rejected;

separate arm thresholds are structurally impossible.

Package 2 — Build deterministic latent pairs and manifests

Outcome: generate the complete paired image/GT release without model access.

 - [ ] Implement deterministic seed derivation and candidate ordering.

 - [ ] Extend the pinned V12 scene path to one static scene strip and one moving camera sequence per pair.

 - [ ] Preserve persistent source-object GT across all frames.

 - [ ] Export the ideal arm.

 - [ ] Export the degraded arm using only the capture allowlist.

 - [ ] Export one pair manifest with shared and arm-specific fields.

 - [ ] Export action-compatible synthetic capture records.

 - [ ] Record all rejected candidates and pre-outcome reasons.

 - [ ] Enforce ten attempts per required slot.

 - [ ] Generate exactly 96 accepted latent pairs and 5,760 RGB frames.

 - [ ] Verify no calibration/test source or seed overlap.

 - [ ] Verify no arm-specific GT or trajectory difference.

 - [ ] Verify all source, pixel, temporal, and denominator gates.

 - [ ] Select the fixed calibration visual-review sample.

 - [ ] Complete calibration-only manual review.

 - [ ] Seal release_lock_v1.json before any model prediction exists.

Acceptance evidence:

exact cell and split counts;

every pair has two complete arms;

all shared latent digests match;

all capture differences are allowlisted;

test images have hashes but no predictions;

pre-outcome audit status PASS;

release receipt binds model_outputs_present=false.

Package 3 — Bind deterministic inference and tracking

Outcome: prove the frozen checkpoint and tracker produce stable, action-compatible predictions without changing between arms.

 - [ ] Implement only the narrow simulation-manifest adapter required by the accepted existing inference path.

 - [ ] Verify native 2048² input and no full-frame resize.

 - [ ] Verify the exact checkpoint hash before loading.

 - [ ] Apply the same tiling, halo, merge, class map, thresholds, and tracker config to both arms.

 - [ ] Ensure inference code cannot read GT fields or arm labels.

 - [ ] Ensure tracker state resets at video boundaries.

 - [ ] Ensure predicted track IDs are stable and video-scoped.

 - [ ] Run the four-pair determinism preflight twice.

 - [ ] Require canonical prediction hashes to match.

 - [ ] Add negative tests for checkpoint mismatch, full-frame resize, GT access, arm-specific config, and nondeterministic output.

Acceptance evidence:

deterministic smoke prediction receipt;

identical resolved inference/tracker config for both arms;

prediction format satisfies frozen action input requirements;

no test prediction generated.

Package 4 — Calibrate once on degraded calibration

Outcome: produce one immutable threshold selected only through the frozen evaluator.

 - [ ] Run inference and tracking on the 32 degraded calibration videos only.

 - [ ] Bind predictions to exact calibration images, release receipt, checkpoint, inference, and tracker identities.

 - [ ] Invoke the frozen threshold-selection semantics.

 - [ ] Record the selected threshold and feasibility state.

 - [ ] Seal threshold_lock_v1.json.

 - [ ] Assert no test prediction file exists before threshold lock.

 - [ ] Optionally run ideal calibration diagnostics only after the threshold receipt is immutable.

 - [ ] Prevent any calibration result from changing capture, seeds, model, tracker, or estimands.

Acceptance evidence:

threshold receipt hash;

degraded calibration was the sole threshold source;

exact frozen grid and tie breakers used;

test prediction absence proven;

fallback status explicit when no feasible threshold exists.

Package 5 — Run the locked paired test once

Outcome: obtain ideal and degraded action results with one shared threshold and no test-driven changes.

 - [ ] Generate ideal locked-test predictions.

 - [ ] Generate degraded locked-test predictions.

 - [ ] Build the two evaluator manifests with identical degraded calibration validation inputs.

 - [ ] Run the frozen action evaluator for the ideal test arm.

 - [ ] Run the frozen action evaluator for the degraded test arm.

 - [ ] Assert identical selected threshold and calibration statistics across runs.

 - [ ] Preserve all frozen action counts and rates.

 - [ ] Compute segmentation diagnostics.

 - [ ] Compute tracking diagnostics.

 - [ ] Compute pair-level sufficient statistics.

 - [ ] Run the 10,000-replicate stratified paired bootstrap with seed 1729.

 - [ ] Report hypothesis-reference differences without acceptance labels.

 - [ ] Seal paired_metric_result_v1.json.

 - [ ] Set every field, product, physical, and chemical authority flag false.

Acceptance evidence:

exact prediction and evaluator hashes for both arms;

identical calibration threshold across evaluator runs;

full frame coverage;

primary paired action-F1 delta and interval;

all denominator and interval statuses explicit;

final status synthetic-only.

Package 6 — Regression validation and human protocol document

Outcome: make the experiment reproducible and difficult to misuse.

 - [x] Add the lane-owned tests/test_spot_spray_simulation_video_ab_protocol_v1.py.

 - [ ] Add positive fixtures for valid pair, valid split, feasible calibration, and infeasible calibration.

 - [ ] Add negative fixtures for every material fail-closed status.

 - [x] Add the lane-owned docs/research/SPOT_SPRAY_SIMULATION_VIDEO_AB_PROTOCOL_V1.md.

 - [x] Document facts separately from protocol decisions.

 - [x] Document why V7 magnitudes and challenger checkpoint are excluded.

 - [x] Document the descriptive-only role of 0.97 and 0.75.

 - [x] Document the exact threshold and evaluator reuse path.

 - [x] Document bootstrap scope and omitted uncertainty sources.

 - [x] Document that synthetic pseudo-fields are not real breadth.

 - [ ] Reproduce the final canonical JSON from the same locked inputs.

 - [ ] Require byte-identical canonical result and receipt hashes.

Acceptance evidence:

focused test suite passes;

canonical result reproduction passes;

frozen upstream diff is empty;

documentation contains no physical, field, product, or chemical promotion.

20. Exact validation

Codex shall run the equivalent of the following commands and retain their outputs. These commands are specifications for implementation; this plan does not claim they have run.

20.1 Focused tests

python -m pytest -q tests/test_spot_spray_simulation_video_ab_v1.py

Required result:

all tests pass;

no skipped material fail-closed case;

no network access;

no real hardware dependency.

20.2 Source and compatibility preflight

python scripts/audit_spot_spray_simulation_video_ab_v1.py preflight --config configs/benchmark/spot_spray_simulation_video_ab_protocol_v1.yaml --output "$SPOT_SPRAY_DATA_ROOT/processed/audits/spot_spray_simulation_video_ab_v1/source_lock_receipt_v1.json"

Required result:

status=PASS;

all source hashes verified;

selected checkpoint verified;

inference and tracker compatibility verified.

20.3 Pair generation

python scripts/build_spot_spray_simulation_video_ab_v1.py --config configs/benchmark/spot_spray_simulation_video_ab_protocol_v1.yaml --data-root "$SPOT_SPRAY_DATA_ROOT" --output-root "$SPOT_SPRAY_DATA_ROOT/processed/spot_spray_simulation_video_ab_v1"

Required result:

96 pairs;

192 videos;

5,760 frames;

exact 32/64 split;

exact balanced cell counts.

20.4 Pre-outcome audit and release lock

python scripts/audit_spot_spray_simulation_video_ab_v1.py release --config configs/benchmark/spot_spray_simulation_video_ab_protocol_v1.yaml --manifest "$SPOT_SPRAY_DATA_ROOT/processed/spot_spray_simulation_video_ab_v1/pair_manifest_v1.jsonl" --output "$SPOT_SPRAY_DATA_ROOT/processed/audits/spot_spray_simulation_video_ab_v1/preoutcome_audit_v1.json" --lock-output "$SPOT_SPRAY_DATA_ROOT/processed/audits/spot_spray_simulation_video_ab_v1/release_lock_v1.json"

Required result:

every source, split, pair, temporal, GT, pixel, PSF, and denominator gate passes;

model_outputs_present=false.

20.5 Calibration threshold lock

python scripts/evaluate_spot_spray_simulation_video_ab_v1.py calibrate --config configs/benchmark/spot_spray_simulation_video_ab_protocol_v1.yaml --release-lock "$SPOT_SPRAY_DATA_ROOT/processed/audits/spot_spray_simulation_video_ab_v1/release_lock_v1.json" --arm degraded --output "$SPOT_SPRAY_DATA_ROOT/processed/audits/spot_spray_simulation_video_ab_v1/threshold_lock_v1.json"

Required result:

degraded calibration only;

one selected threshold;

feasibility explicit;

no test predictions present.

20.6 Locked test

python scripts/evaluate_spot_spray_simulation_video_ab_v1.py locked-test --config configs/benchmark/spot_spray_simulation_video_ab_protocol_v1.yaml --release-lock "$SPOT_SPRAY_DATA_ROOT/processed/audits/spot_spray_simulation_video_ab_v1/release_lock_v1.json" --threshold-lock "$SPOT_SPRAY_DATA_ROOT/processed/audits/spot_spray_simulation_video_ab_v1/threshold_lock_v1.json" --output "$SPOT_SPRAY_DATA_ROOT/processed/audits/spot_spray_simulation_video_ab_v1/paired_metric_result_v1.json"

Required result:

both arms evaluated;

identical degraded calibration bytes and threshold used;

all metrics and intervals emitted;

synthetic-only status.

20.7 Reproduction

python scripts/evaluate_spot_spray_simulation_video_ab_v1.py reproduce --config configs/benchmark/spot_spray_simulation_video_ab_protocol_v1.yaml --result "$SPOT_SPRAY_DATA_ROOT/processed/audits/spot_spray_simulation_video_ab_v1/paired_metric_result_v1.json" --output "$SPOT_SPRAY_DATA_ROOT/processed/audits/spot_spray_simulation_video_ab_v1/paired_metric_result_v1.reproduced.json"

Then:

cmp "$SPOT_SPRAY_DATA_ROOT/processed/audits/spot_spray_simulation_video_ab_v1/paired_metric_result_v1.json" "$SPOT_SPRAY_DATA_ROOT/processed/audits/spot_spray_simulation_video_ab_v1/paired_metric_result_v1.reproduced.json"

Required result:

byte-identical canonical result.

20.8 Frozen-source diff

Verify no changes to the frozen inputs, including:

product architecture config;

V12 config;

V7 protocol and asset-gate configs;

frozen action config;

frozen action evaluator.

Any diff in those files fails this part.

21. Material risks and rollback
V12 is not a calibrated camera model

Risk: the degraded arm may be directionally useful but quantitatively unlike the installed sensor.

Control:

restrict V1 to source-supported geometry, radiometry gates, and subpixel motion;

exclude unmeasured effects;

label all results synthetic-only;

do not interpret absolute F1 as field expectation.

Persistent instance truth may be unavailable

Risk: V12’s processed semantic proxy may not preserve source-object temporal identity.

Control:

require source-scene object IDs;

stop before rendering if unavailable;

do not fabricate GT tracks.

Existing inference may resize or lack stable tracking

Risk: the selected checkpoint may not have one pinned native-video path.

Control:

bounded compatibility discovery first;

stop rather than implement a target-tuned tracker in this part.

Renderer nondeterminism

Risk: GPU, renderer, or dependency differences may change image bytes.

Control:

pin renderer build and environment;

canonicalize manifests and outputs;

perform rerender checks;

revoke rather than partially repair a locked release.

Calibration leakage

Risk: ideal or test outcomes may influence threshold or experiment settings.

Control:

degraded calibration only;

test prediction absence in threshold receipt;

immutable release before inference;

one-time locked test.

Hypothesis anchoring

Risk: implementers may treat 0.97 and 0.75 as desired outputs.

Control:

hypotheses excluded from seed derivation, capture operators, thresholds, gates, and sample size;

report signed differences only;

stop after the predeclared run regardless of result.

Narrow uncertainty

Risk: the bootstrap interval may look more general than it is.

Control:

state that it covers only bounded synthetic-pair sampling;

retain zero synthetic weight in real decisions;

report unmodelled uncertainty sources.

Rollback

All new data, manifests, predictions, and receipts shall live under a versioned V1 output root.

Rollback is:

mark the release revoked;

preserve evidence;

remove no upstream source;

leave the accepted architecture, checkpoint, V12, V7 control, and action evaluator unchanged;

delete or archive only generated V1 outputs if operational cleanup is required;

create V2 for any material protocol change.

No V1 result may be silently regenerated under the same identity.

22. Completion criteria

This part is complete only when all of the following are true:

 - [ ] Exact source and checkpoint identities are verified.

 - [ ] Persistent GT object and track identity is available.

 - [ ] One compatible native inference and stable tracker lineage is pinned.

 - [ ] The canonical protocol config contains all resolved decisions in this plan.

 - [ ] Exactly 32 calibration and 64 locked-test latent pairs exist.

 - [ ] Every pair has exactly two arms and 30 frames per arm.

 - [ ] All shared latent and GT fields match across arms.

 - [ ] All arm differences are allowlisted.

 - [ ] All V12-derived visual and split gates pass.

 - [ ] All subpixel motion gates pass and no V7 multi-pixel kernel is used.

 - [ ] The immutable release is sealed before model outputs.

 - [ ] Degraded calibration alone selects the threshold.

 - [ ] Test predictions are absent before threshold lock.

 - [ ] Both action-evaluator runs use identical degraded calibration bytes and select the same threshold.

 - [ ] Segmentation, tracking, action, and paired uncertainty results are complete.

 - [ ] Ideal 0.97 and degraded 0.75 remain descriptive references only.

 - [ ] Canonical reproduction is byte-identical.

 - [ ] Frozen upstream files remain unchanged.

 - [ ] The final status is synthetic-only.

 - [ ] No field, product, physical, deposition, crop-safety, or chemical claim is made.

23. Stopping rules and re-plan triggers

Stop before full rendering when:

persistent source-object GT is unavailable;

the selected checkpoint cannot be verified;

native 2048² inference without full-frame resize is unavailable;

stable predicted tracking is unavailable;

inference/tracking lineage is materially ambiguous;

source hashes drift;

required V12 calibration/test assets are not split-disjoint.

Stop before calibration when:

any pair or realism gate fails;

exact counts are not achieved within the ten-attempt candidate limit;

test or calibration source overlap exists;

release identity cannot be sealed deterministically.

Stop before test when:

threshold receipt is absent or invalid;

test predictions already exist before threshold lock;

calibration used ideal or test outputs;

inference or tracker config changed after release lock.

Complete and stop after one valid locked-test run even when:

ideal F1 is far below 0.97;

degraded F1 is far from 0.75;

degraded outperforms ideal;

the paired interval is wide;

calibration is infeasible and fallback reporting is required;

a secondary metric conflicts with the primary metric.

A V2 re-plan is required, rather than extending V1, when:

more pair units are desired;

a second checkpoint is proposed;

a new tracker is proposed;

a different confidence-calibration policy is proposed;

sensor noise, lens MTF, defocus, contamination, severe vibration, dropped frames, compression, or light-channel failures are added;

physical bench measurements become available and materially change the degraded envelope;

the action evaluator changes;

real target-rig video replaces synthetic evidence;

any result is proposed for controlled-capture, dry-marker, field, product, deposition, crop-injury, or chemical authorization.

The terminal conclusion of V1 is one measured, reproducible synthetic sensitivity estimate for the frozen stack—nothing more.
