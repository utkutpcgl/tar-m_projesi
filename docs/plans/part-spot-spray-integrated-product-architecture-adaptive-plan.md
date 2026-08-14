Status: READY
Planner depth: 0
Parent plan: (root plan)

Canonical Cross-Lane Integration Contract for the One-Bay Spot-Spray Proof Product
1. Decision and intended outcome

Create one canonical integration layer that reconciles the terminal sensor/optics, light/enclosure, and platform-product surveys without transferring ownership away from those lanes.

The selected integrated proof architecture is:

one Basler a2A2464-77ucPRO RGB action camera with the Basler C23-0824-5M-P lens;

native centered 2048×2048 ROI, offset (200, 0), with no full-frame digital resize;

measured 474–484 mm ground FOV, adjustable 520–590 mm working distance, f/5.6, 170 µs, and 15 Hz;

one four-quadrant, diffuse, broad-spectrum white, camera-triggered strobe assembly;

one minimum 600×600 mm internally clear matte hood with the inherited window, skirt, baffle, light-sealing, and cooling architecture;

one removable carrier-independent lower bay cassette mounted on a manually driven rear-three-point proof carrier;

one dedicated USB3 root, one currently supported RTX 3090 compute lane, and one shared real-time trigger/encoder controller;

one minimum 444.375 mm lateral action-safe swath derived from the calibrated image region, not from hood width;

no second camera, no 20 Hz product claim, no autonomous carrier, no chemical-enable path, and no unsupported physical-readiness claim.

The integration artifacts shall make this architecture understandable and reproducible while preserving four independent status axes:

Axis	Current canonical state
Architecture selection	FROZEN_BASELINE
Source/integration integrity	Determined by the integration derivation; must be PASS before artifacts are current
Host qualification	HOST_UNRESOLVED until an exact tractor and carrier interface pass the bounded host audit
Physical acceptance	PRE_REAL_NOT_READY; no physical A–E receipt exists
Controlled capture authority	Not granted by this contract
Dry-marker authority	Not granted by this contract
Chemical fire	UNSUPPORTED_BLOCKED under the frozen acceptance policy

The integration result may conclude only:

INTEGRATION_CONSISTENT_PRE_REAL;

INTEGRATION_INVALID_SOURCE_DRIFT;

INTEGRATION_INVALID_CROSS_LANE_CONFLICT;

REPLAN_REQUIRED.

It shall never emit READY, GO, FROZEN_FOR_CONTROLLED_CAPTURE, DRY_MARKER_READY, FIELD_GO, or CHEMICAL_GO.

2. Primary bottleneck

The primary bottleneck is no longer another market survey. It is the lack of one exact, hash-bound integration authority that answers all of the following without contradiction:

which lane owns each decision;

which values are frozen, measured later, challenger-only, host-unresolved, unsupported, or out of scope;

how enclosure dimensions differ from calibrated action coverage;

where the reusable cassette ends and the host-specific carrier begins;

which costs belong to the optical proof module versus the carrier;

which power values are measured, bounded, reference-only, or unknown;

which compute and safety constraints remain closed;

which dimensions and interfaces appear in all engineering views;

what source drift invalidates the integrated architecture.

The smallest useful response is therefore one canonical YAML contract, one deterministic derivation path, one human-readable architecture, one normalized BOM, and three generated engineering views. No additional sensor, light, carrier, or commercial candidate search is authorized by this part.

3. Goals

Preserve the terminal lane decisions exactly and reconcile only their shared boundaries.

Establish one machine-readable source lock for the three terminal surveys and the frozen capture, acceptance, compute, action, and release authorities.

Define the smallest ownership and status schema that prevents one lane from silently deciding another lane’s variables.

Distinguish enclosure footprint, optical FOV, action-safe region, intervention datum, nozzle footprint, and carrier width.

Define a carrier-independent cassette boundary that can migrate without converting the carrier into the camera-to-intervention calibration frame.

Recompute geometry, blur, data payload, mechanical payload status, swath, gross geometric throughput, power, and cost from primitive inputs.

Preserve unknown values as null; never substitute zero, a midpoint, an adjacent model, or an inferred host class.

Bind every derived artifact and engineering view to exact source and config hashes.

Fail closed on duplicate keys, source drift, cross-lane conflicts, stale generated artifacts, missing required values, or unauthorized status promotion.

Give Codex small ordered implementation packages with observable acceptance evidence.

Retain implementation freedom for equivalent local parsing, formatting, and SVG-layout choices that do not change the contract.

4. Non-goals

This part shall not:

reopen camera, modality, lens, ROI, FOV, exposure, frame-rate, lighting-spectrum, hood, platform-topology, or model selection;

choose exact LED, diffuser, heatsink, fan, skirt breakaway force, tractor, hitch adapter, toolbar dimensions, carrier material, or intervention hardware;

purchase, quote, reserve, fabricate, assemble, or physically test hardware;

modify any terminal survey or frozen upstream contract;

change any A–F acceptance threshold or evaluator behavior;

declare the hood to be ingress-certified, production-rugged, rain-safe, washdown-safe, dust-safe, vibration-safe, or field-ready;

treat 600 mm hood width as an action swath or throughput width;

treat 444.375 mm action-safe swath as a hood or carrier structural width;

assign chemical tank, pump, nozzle, valve, deposition, dose, crop injury, or kill-rate responsibility;

authorize controlled capture, dry-marker operation, field operation, or chemical fire;

claim the existing RTX 3090 sustains 20 Hz, two cameras, or a future target-rig checkpoint without a new end-to-end benchmark;

add autonomous steering, propulsion, route planning, or unattended operation;

produce fabrication drawings, structural certification, tolerance stacks, wiring harness release drawings, or production CAD;

hide unresolved host, carrier, mechanical-payload, whole-system-power, or integrated-cost values inside a nominal total;

introduce a weighted score that allows cost to compensate for a failed geometry, safety, provenance, compute, or ownership gate.

5. Evidence and authority boundary
5.1 Required terminal lane inputs

The integration contract shall pin exact bytes and SHA-256 identities for:

docs/research/SPOT_SPRAY_SENSOR_OPTICS_SURVEY_V1.md;

docs/research/SPOT_SPRAY_LIGHT_ENCLOSURE_SURVEY_V1.md;

docs/research/SPOT_SPRAY_PLATFORM_PRODUCT_SURVEY_V1.md.

It shall also pin the corresponding terminal lane plans because the plans define ownership, challenger, discovery, and stopping rules that may not all appear in concise survey conclusions:

docs/plans/part-spot-spray-sensor-optics-adaptive-plan.md;

docs/plans/part-spot-spray-light-enclosure-adaptive-plan.md;

docs/plans/part-spot-spray-platform-product-adaptive-plan.md.

The supplied repository context records that these lane artifacts were locally modified or untracked relative to the remote base. Codex shall not finalize the integration source lock against an uncommitted or partially visible source set.

Required admission rule:

all six lane files must exist;

their final bytes must be committed on the implementation base;

the integration config must record the exact containing commit and each file SHA-256;

the generator must verify those exact bytes before any calculation;

if any file is missing, dirty, or differs from its pin, stop with INTEGRATION_INVALID_SOURCE_DRIFT.

Neither remote main@509aeef8189dfa50dbcba973e871b0d41febe239 nor the recorded local HEAD may be used as the final integration source commit unless it contains the exact terminal survey bytes being integrated.

5.2 Frozen upstream authorities

Pin only the upstream files that materially constrain this integration:

configs/deploy/spot_spray_capture_optimization_v2.yaml;

docs/CONTROLLED_CAPTURE_OPTIMIZATION_V2.md;

configs/deploy/spot_spray_rig_acceptance_v1.yaml;

scripts/evaluate_spot_spray_rig_acceptance_v1.py;

docs/SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md;

docs/SPOT_SPRAY_PRODUCT_IMAGING_DECISION_V1.md;

docs/SPOT_SPRAY_INTEGRATED_CONTRACT_RELEASE_V1.md;

configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml;

docs/results/spot_spray_deploy_compute_summary_v1.json;

docs/results/spot_spray_deploy_compute_halo_summary_v1.json.

Known frozen identities that must be reproduced rather than manually retyped from memory include:

Authority	Required identity
Capture optimization V2	f9fd1cbed95118b4606199e9b67b317c07384e2cb063b60a00e5466848f657e9
V2 decision document	c5eb80d8eb074b36463906a4dee993776d2415ae1e41ad50a988c8592e8ed7aa
Rig acceptance exact bytes	a6c0e69f1c489e58b7a6c94a92bf50d9dfd97eef0c1b6ec709b872b2f7b66e3c
Rig acceptance canonical policy	c05ae3837d98f313c32e81178045a9fef39965199c276ec06e9d01195e88ff21
Rig acceptance evaluator	596c6db31e6ce90f06b1019657e58631415f1b90fdeeb9fdbd917b4ab461fda2
Frozen Stage-E proxy checkpoint	0b30e1433cecb4ecaa71a1005c520604eaacab9a92595efb18f3966bcd57f6b8
Selected pre-real foundation checkpoint	3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100

The Stage-E proxy checkpoint and the selected pre-real foundation serve different roles. The integration contract shall preserve that distinction and shall not present the Stage-E proxy timing result as evidence for the pre-real foundation or any future fine-tuned checkpoint.

5.3 Authority precedence

Apply this order when resolving a value:

exact frozen acceptance policy for acceptance semantics and quantitative safety gates;

exact frozen capture optimization V2 for baseline architecture constants;

terminal lane survey for values owned by that lane;

terminal lane plan for ownership, challengers, discovery, and re-plan rules;

deterministic integration calculation;

integration inference needed only to connect lane interfaces.

Rules:

The integration layer cannot override levels 1–4.

A lower-priority source cannot replace a higher-priority non-null value.

A non-owning lane cannot supply a value missing from the owning lane.

A conflict on a frozen value is terminal; do not choose the more convenient value.

A shared interface is valid only when both sides agree exactly or the integration config defines an explicit, unit-safe compatibility transformation.

null remains null unless the owning source or an authorized physical measurement supplies a value.

5.4 Evidence classes

Every material field shall carry one evidence class:

FROZEN_REPOSITORY_CONTRACT;

TERMINAL_LANE_DECISION;

DETERMINISTIC_CALCULATION;

ENGINEERING_INTEGRATION_INFERENCE;

PHYSICAL_MEASUREMENT;

NO_EVIDENCE_NULL.

ENGINEERING_INTEGRATION_INFERENCE may connect compatible interfaces but may not create a physical PASS, product metric, structural rating, or commercial value.

6. Resolved integrated architecture
6.1 Frozen one-bay proof baseline
Domain	Frozen integrated value	Owner
Action camera	1× Basler a2A2464-77ucPRO, order 109779	Sensor/optics
Sensor state	Color global shutter, factory IR-cut installed	Sensor/optics
Lens	Basler C23-0824-5M-P, order 2200000568	Sensor/optics
Lens use	Nominal 8.06 mm, catalog tolerance ±5%, selected f/5.6	Sensor/optics
Raw raster	2448×2048	Sensor/optics
Active raster	Native centered 2048×2048, offset (200, 0)	Sensor/optics
Resize	Full-frame digital resize forbidden	Sensor/optics
Ground FOV	Measured 474–484 mm; nominal reporting point 480 mm	Sensor/optics
Working distance	Unit-adjusted and locked in 520–590 mm	Sensor/optics
Focus plane	55 mm above ground	Sensor/optics
Test planes	0, 55, and 110 mm above ground	Sensor/optics
Exposure	170 µs	Sensor/optics
Proof acquisition	15 Hz	Compute/capture
Trial speeds	0.5 and 1.0 m/s	Platform/carrier
Service class	20 mm first action-eligible canopy span	Product/capture
Optical witness	10 mm; not an action promise	Sensor/optics
Outer action mask	64 px per image edge	Capture/action
One-bay action-safe width	Measured FOV × 0.9375; minimum 444.375 mm	Integration calculation
Proof camera count	One	Product/compute
Camera transport	Dedicated USB3 root, locking cable ≤3 m	Sensor/compute interface
Compute	Measured RTX 3090, one camera at 15 Hz only	Compute
Strobe	Four independently current-limited white quadrants, all-on by default	Light/enclosure
Light spectrum	4500–5500 K, CRI ≥90	Light/enclosure
Strobe timing	150–170 µs, fully inside exposure	Light/enclosure
Hood	Minimum 600×600 mm internal plan	Light/enclosure
Carrier topology	Manual rear-three-point proof toolbar	Platform/carrier
Reusable unit	One removable lower bay cassette	Integration/platform
Ground following	Passive, host-specific mechanism acting on the cassette interface	Platform/carrier
Travel source	Ground-referenced quadrature encoder baseline	Platform/carrier
Intervention	Local rigid mounting datum only; hardware and chemistry external	Platform/intervention boundary
Chemical path	Absent or verified disabled	Safety/acceptance
6.2 Reconciliation of 600 mm hood and 444.375 mm action-safe swath

These values describe different physical concepts and shall never be merged.

Hood footprint

600×600 mm is the minimum internal plan of the proof enclosure. It provides space for:

the central optical bay;

four emitter quadrants;

diffusers and source stand-off;

optical baffles;

protective-window framing;

skirt and labyrinth attachment;

cable routing;

thermal paths;

service and non-occlusion margins.

It is not an action width, calibrated image width, nozzle footprint, carrier width, or throughput width.

Ground FOV

The calibrated ground FOV is physically measured in the range 474–484 mm. Catalog or CAD geometry does not replace the measured FOV.

Action-safe region

The outer 64 px ring on each side of the 2048 px ROI is abstained. The usable fraction along one axis is:

(2048 - 2×64) / 2048 = 1920 / 2048 = 0.9375

Therefore:

minimum measured safe width: 474 × 0.9375 = 444.375 mm;

nominal safe width: 480 × 0.9375 = 450.000 mm;

maximum value within the allowed FOV range: 484 × 0.9375 = 453.750 mm.

Acceptance uses the actual measured FOV and requires at least 444.375 mm. Product throughput calculations shall use the measured safe width or the conservative minimum, never 600 mm and never the unmasked FOV.

The hood walls, skirts, baffles, light boards, window frame, carrier members, gauge wheels, and cables may not intrude into the calibrated optical cone or action-safe region.

The numerical difference between hood plan and ground FOV is not an automatic physical-clearance guarantee because they occur at different planes. Stage C remains the authority for non-occlusion and installed optical geometry.

6.3 Cassette and carrier ownership boundary

The reusable cassette is the lower calibrated bay assembly. The carrier is the host-specific structure that positions and transports it.

Cassette owns

one rigid local coordinate frame;

camera mounting datum;

hood/light/window mounting interfaces;

rigid camera-to-intervention datum relationship;

intervention mounting datum, but not intervention hardware;

fine working-height adjustment and hard witness marks;

local calibration and daily-registration fiducial locations;

local identity plate and hardware revision;

cable termination, strain relief, and service envelope;

no-intrusion volumes for the FOV and action-safe region;

interface points through which a carrier ground-following mechanism supports the cassette;

local mass, center-of-gravity, and mounting-load reporting points once measured.

The cassette does not own the camera, lens, LED, diffuser, window, or hood design decisions. Those remain lane-owned components installed into the cassette boundary.

Carrier owns

exact tractor or host selection;

rear-three-point adapter;

transverse proof toolbar;

anti-sway and pitch restraint;

upper carrier frame;

passive vertical guide, parallelogram, or equivalent ground-following mechanism;

gauge wheel or wheels;

quadrature encoder installation;

gross operating-height placement;

lift and transport;

transport lock;

deployed/lift-state sensing;

operator controls and E-stop routing;

compute/power tray;

host power source and conversion;

structural load path, ballast, axle, hitch, and moment qualification;

host-specific cable routing;

wheel-track and disturbed-lane avoidance.

Integration layer owns only

coordinate-frame definitions;

interface datums;

allowed envelopes;

ownership declarations;

compatibility checks;

source pins;

derived calculations;

annotations shared by the three engineering views.

The integration layer does not design any lane-owned component.

6.4 Coordinate frames

Use a right-handed convention in every artifact and view:

+X: direction of forward travel;

+Y: lateral right when viewed in the direction of travel;

+Z: upward from the ground plane.

Required frames:

F_world: local ground reference;

F_carrier: host-specific upper carrier datum;

F_cassette: rigid lower bay datum;

F_camera: camera optical frame;

F_ground_calibration: calibrated ground homography frame;

F_intervention_mount: physical intervention mounting datum;

F_encoder: signed travel-measurement frame.

The transform from F_camera to F_intervention_mount must remain mechanically rigid within the cassette. Its along-track distance remains null until physically measured. CAD may illustrate the datum but cannot populate the acceptance offset.

6.5 Data and control flow

The canonical flow is:

The manual carrier moves through the controlled proof lane.

Deployed-state, transport-lock, direction, encoder, power, E-stop, hood, and temperature states are checked.

One shared real-time controller emits the camera trigger and latches encoder count on the same hardware event.

The Basler camera captures one global-shutter exposure.

Camera ExposureActive drives the isolated strobe driver.

All four calibrated light quadrants fire according to the fixed profile.

The camera delivers the native frame through its dedicated USB3 root.

The one-camera RTX 3090 pipeline performs acquisition, tracking, and result transfer under the frozen 15 Hz Stage-E boundary.

A downstream scheduler may consume the frame, timestamp, encoder, calibration, bay, and result identities.

The intervention interface remains disabled unless the independent acceptance chain authorizes its requested decision target.

Any invalid or stale state produces no-fire.

Host-arrival timestamps, tractor display speed, GPS-only speed, CAD-assumed offset, or unbound client metadata may not enter the control authority.

7. Canonical ownership and status schema
7.1 Owner enum

Each decision item shall have exactly one owner:

sensor_optics;

light_enclosure;

platform_carrier;

compute_capture;

safety_acceptance;

intervention_external;

host_owner;

integration_only.

integration_only is valid only for shared coordinate frames, compatibility rules, derived values, source locks, and visual annotations.

7.2 Decision-state enum

Use only:

FROZEN_BASELINE;

OPEN_BENCH_VARIABLE;

HOST_UNRESOLVED;

CHALLENGER_CLOSED_NOT_TRIGGERED;

CHALLENGER_ELIGIBLE_BOUNDED_AB;

REJECTED;

UNSUPPORTED;

OUT_OF_SCOPE.

Rules:

A FROZEN_BASELINE field must be non-null and source-bound.

An OPEN_BENCH_VARIABLE or HOST_UNRESOLVED field may be null only when it has a bounded discovery and deterministic resolution rule.

A challenger cannot be FROZEN_BASELINE.

UNSUPPORTED is not a temporary PASS.

A null field cannot use FROZEN_BASELINE.

Unknown strings fail schema validation.

Status promotion cannot be inferred from prose; it requires the owning lane’s explicit rule and evidence.

7.3 Required decision-item fields

Each material decision item shall include:

item_id;

owner;

category;

decision_state;

value;

unit;

evidence_class;

source_path;

source_sha256;

source_locator;

rationale;

dependency_ids;

resolution_trigger;

resolution_rule;

invalidation_scope;

claim_limit.

For fixed enums or booleans, unit may be null. For unresolved physical values, value must be null.

7.4 Current integrated status ledger

At minimum, the YAML shall carry these records:

Item	Owner	State
Basler PRO camera	sensor_optics	FROZEN_BASELINE
C23 lens	sensor_optics	FROZEN_BASELINE
Native ROI and optical geometry	sensor_optics	FROZEN_BASELINE
Visible RGB modality	sensor_optics	FROZEN_BASELINE
Alternative sensor modalities	sensor_optics	Terminal survey disposition; never promoted by integration
Four-quadrant all-on white light	light_enclosure	FROZEN_BASELINE
Exact LED SKU and current	light_enclosure	OPEN_BENCH_VARIABLE
Exact diffuser and aim	light_enclosure	OPEN_BENCH_VARIABLE
Cross-polarization	light_enclosure	CHALLENGER_CLOSED_NOT_TRIGGERED
Passive cooling	light_enclosure	FROZEN_BASELINE architecture
External heatsink fan	light_enclosure	CHALLENGER_CLOSED_NOT_TRIGGERED
Rear-three-point proof topology	platform_carrier	FROZEN_BASELINE
Exact rear host	host_owner	HOST_UNRESOLVED
Front-three-point proof	platform_carrier	CHALLENGER_CLOSED_NOT_TRIGGERED
Existing-boom scale carrier	platform_carrier	Outside one-bay proof; conditional scale topology
Trailed scale carrier	platform_carrier	Conditional scale fallback
One camera at 15 Hz	compute_capture	FROZEN_BASELINE
One camera at 20 Hz	compute_capture	CHALLENGER_CLOSED_NOT_TRIGGERED
Second camera	compute_capture	CHALLENGER_CLOSED_NOT_TRIGGERED
Whole-system compute draw	compute_capture	OPEN_BENCH_VARIABLE with null value
Mechanical cassette mass and CG	platform_carrier	OPEN_BENCH_VARIABLE with null value
Camera-to-intervention offset	intervention_external	OPEN_BENCH_VARIABLE with null value
Chemical enable	safety_acceptance	UNSUPPORTED and false
8. Interface contracts
8.1 Mechanical interface

The YAML and side view shall define:

F_carrier and F_cassette datums;

primary, secondary, and tertiary locating surfaces;

cassette centerline;

nominal camera axis;

fine height-adjustment range;

carrier coarse-height range as host-unresolved;

gauge-wheel contact plane;

intervention mounting datum;

service-removal direction;

cable bend and strain-relief zones;

optical no-intrusion volume;

action-safe no-intrusion region;

mass and CG reporting point;

operating, lifted, and transport states.

No fastener grade, plate thickness, weld, bearing, spring, or structural member size shall be frozen without exact load evidence.

8.2 Optical and enclosure interface

The integration contract shall reproduce without owning:

474–484 mm measured ground FOV;

520–590 mm working distance;

focus plane at 55 mm;

test planes 0/55/110 mm;

installed tilted AR window;

minimum 600×600 mm hood internal plan;

four light quadrants;

no direct LED-to-window path;

no enclosure or carrier intrusion into the calibrated cone;

two-layer skirt, staggered overlap, and light labyrinth;

calibrated action-safe region;

no product claim for the outer masked ring.

The exact window, diffuser, LED, current, external lux, and thermal solution remain lane-owned bench values.

8.3 Timing and encoder interface

Freeze:

shared real-time controller clock;

camera trigger and encoder latch on the same hardware event;

quadrature resolution ≤1 mm/count;

encoder scale error ≤1 mm/m;

trigger–encoder p95 ≤100 µs;

trigger–encoder maximum ≤250 µs;

stale encoder no-fire at ≤5 ms;

camera ExposureActive to isolated strobe driver;

strobe jitter p95 ≤5 µs;

no host-arrival timestamp control;

signed direction;

pending-command cancellation on stop, reverse, lift, fold, stale data, or invalid state.

8.4 Data and compute interface

Freeze:

one camera;

one dedicated USB3 root;

locking camera cable ≤3 m;

Bayer10 packed preferred transport baseline;

frame counter and camera timestamp;

exact camera, bay, calibration, and capture-profile identity;

one measured RTX 3090 lane;

15 Hz end-to-end p95 deadline ≤66.6666667 ms;

zero deadline miss and zero frame drop under Stage E;

no second camera or 20 Hz assumption.

A new compute result may supersede this only when the compute owner supplies a hash-bound end-to-end benchmark that includes camera acquisition, tracking, and result transfer.

8.5 Power interface

Keep continuous, transient, reference, and unknown values separate.

Frozen values

camera external supply: 12–24 VDC;

light bus: 24 V;

programmable peak light current envelope: 0–10 A;

light peak electrical ceiling: 240 W, not an operating setpoint;

light-branch measured average maximum: 20 W;

complete capture-module measured average maximum, excluding compute: 60 W;

bus droop maximum during pulse: 5%;

RTX 3090 reference board power: 350 W;

NVIDIA reference minimum system PSU: 750 W, not vehicle draw.

Unresolved values

These remain null until measured or exact-host-qualified:

whole compute-system continuous input power;

whole compute-system transient input power;

integrated one-bay continuous host draw;

integrated pulse/transient host requirement;

converter efficiency;

host auxiliary continuous rating;

alternator headroom;

battery-only operating duration;

cable voltage drop;

exact fuse and conductor sizing.

The integration evaluator shall not compute:

60 W + 350 W = host requirement

or:

750 W PSU = vehicle draw.

Host power qualification requires the exact installed compute and capture assembly to be measured or conservatively bounded with explicit assumptions.

8.6 Safety interface

The integrated contract shall reference, not duplicate, the rig acceptance authority.

Required fail-closed states include:

E-stop;

watchdog;

hood open;

overtemperature;

invalid timestamp;

stale encoder;

frame drop;

calibration invalid;

profile mismatch;

missing or malformed strobe;

partial light-channel failure;

invalid carrier deployed state;

lifted or moving-to-transport state;

reverse or ambiguous direction;

brownout or uncontrolled reboot.

Required behavior:

strobe and intervention enable default off;

pending intervention commands are discarded after a fault;

recovery requires a new valid state and identity witness;

neighboring coverage does not expand to replace a failed bay;

chemical-enable hardware line remains disabled;

no integration status overrides the existing evaluator result.

8.7 Acceptance binding

The integration YAML shall contain an acceptance_binding section with:

acceptance contract path;

exact-byte SHA-256;

canonical-policy SHA-256;

evaluator path and SHA-256;

controlled-capture target semantics;

dry-marker target semantics;

chemical-fire prohibition;

statement that integration validation is not rig acceptance.

Any acceptance-policy or evaluator drift invalidates all generated integration artifacts before any other calculation.

9. Deterministic calculations

All calculations shall be generated from primitive source-bound inputs. Hand-copied derived values in the Markdown or SVGs are prohibited.

9.1 Active sensor span and GSD

active_sensor_span_mm = 2048 × 3.45 µm / 1000 = 7.0656 mm

GSD_mm_px = measured_FOV_mm / 2048

Golden values:

FOV	GSD
474 mm	0.2314453125 mm/px
480 mm	0.234375 mm/px
484 mm	0.236328125 mm/px
9.2 Target pixels

target_px = target_size_mm / GSD_mm_px

At nominal 480 mm FOV:

10 mm = 42.6666667 px;

20 mm = 85.3333333 px.

The acceptance minima remain 10 mm ≥41 px and 20 mm ≥82 px in every required cell. The integration result shall not replace physical Stage-C measurements with nominal calculations.

9.3 Action-safe swath

safe_fraction = (2048 - 2×64) / 2048 = 0.9375

safe_width_mm = measured_FOV_mm × 0.9375

Golden values:

at 474 mm: 444.375 mm;

at 480 mm: 450.000 mm;

at 484 mm: 453.750 mm.

The current product contract uses one camera and the conservative minimum 444.375 mm.

9.4 Motion smear and blur

smear_mm = speed_m_s × 1000 × exposure_us × 10^-6

At 1.0 m/s and 170 µs:

smear_mm = 0.17 mm

blur_px = smear_mm / GSD_mm_px

Expected FOV-envelope result:

approximately 0.719–0.735 px;

maximum must remain ≤0.75 px.

At 0.5 m/s, smear and blur are half the 1.0 m/s values.

This is an analytical screen. Physical Stage E remains authoritative.

9.5 Data payload

raw_payload_Mbit_s = width × height × rate × bits_per_pixel / 1,000,000

For the 2048×2048 active ROI:

Format/rate	Raw payload
Bayer10 packed, 15 Hz	629.1456 Mbit/s
Bayer10 packed, 20 Hz	838.8608 Mbit/s
Bayer12 packed, 15 Hz	754.97472 Mbit/s
Bayer12 packed, 20 Hz	1006.63296 Mbit/s

With 20% planning headroom:

Format/rate	Required link with headroom
Bayer10 packed, 15 Hz	754.97472 Mbit/s
Bayer10 packed, 20 Hz	1006.63296 Mbit/s
Bayer12 packed, 15 Hz	905.969664 Mbit/s
Bayer12 packed, 20 Hz	1207.959552 Mbit/s

These values do not authorize 20 Hz. They expose transport load only.

9.6 Gross geometric throughput

gross_coverage_ha_h = safe_swath_m × speed_m_s × 0.36

Using the conservative one-bay safe swath 0.444375 m:

Speed	Gross geometric coverage
0.5 m/s	0.0799875 ha/h
1.0 m/s	0.159975 ha/h

These values exclude:

turning;

field efficiency;

setup;

abstention;

terrain;

crop rows;

downtime;

refill;

operator behavior;

intervention availability;

chemical performance.

Real field capacity remains null.

9.7 Multi-bay formulas retained as closed compatibility rules

The one-bay product shall not present multi-bay results as current capability, but the contract may retain these interface formulas:

safe_swath_m = 0.444375 + (N - 1) × pitch_m

subject to:

N ≥1;

pitch_mm ≤430;

overlap ≥10 mm;

every bay and overlap strip independently accepted.

minimum_continuous_hood_internal_width_mm = 600 + (N - 1) × pitch_mm

For this product:

N = 1;

minimum hood width = 600 mm;

multi-bay fields are compatibility references only.

9.8 Mechanical payload and moments

The integration contract shall distinguish data payload from mechanical payload.

Required formula:

mechanical_payload_kg = Σ required_component_mass_kg

moment_about_carrier_datum_Nm = Σ mass_kg × 9.80665 × signed_distance_m

Rules:

if any required component mass is null, total mechanical payload is null;

if any required distance or installed location is null, the corresponding moment is null;

no nominal catalog or adjacent-tractor value fills a null;

hood, cassette, ground-following mechanism, gauge wheel, compute tray, enclosure electronics, cables, safety equipment, and intervention placeholder mass are reported separately;

exact host eligibility cannot pass on hitch lift capacity alone;

physical mass and CG must be measured before structural host qualification.

9.9 Power aggregation

Report:

capture_module_average_power_maximum_w_excluding_compute = 60;

light_branch_average_power_maximum_w = 20;

light_peak_electrical_ceiling_w = 240;

gpu_reference_board_power_w = 350;

reference_system_psu_w = 750;

whole_compute_system_measured_w = null;

integrated_host_continuous_power_w = null;

integrated_host_transient_power_w = null.

Integrated host power may be calculated only after the unresolved measured fields are populated.

9.10 Cost and BOM

The normalized BOM shall preserve evidence classes and avoid double counting.

Known V2 proof-module budget:

minimum before contingency: 3115 USD;

maximum before contingency: 6545 USD;

contingency: 15%;

minimum with contingency: 3582.25 USD;

maximum with contingency: 7526.75 USD.

Human-readable rounding may show 3582–7527 USD, while JSON and CSV retain exact decimal values.

The BOM shall distinguish:

proof_module_core;

compute_existing_asset;

carrier_increment;

host_increment;

intervention_external;

integration_NRE;

measurement_and_calibration;

unknown_required_cost.

Current rules:

public list prices are comparison evidence, not landed quotes;

existing RTX 3090 incremental acquisition cost may be 0, but its whole-system power and opportunity cost are not zero;

carrier and exact-host costs remain null;

intervention cost remains external and null;

integrated one-bay total remains null until all required carrier and host costs are complete;

an unknown cost is never zero;

no chemical saving, yield gain, labor saving, acreage benefit, or autonomy benefit is credited.

Each BOM line requires:

bom_item_id;

owner;

cost_scope;

description;

quantity;

unit;

minimum_cost;

maximum_cost;

currency;

evidence_class;

source_path;

source_sha256;

price_checked_on;

included_in_module_total;

included_in_integrated_total;

unknown_reason;

double_count_group.

Two included lines in the same double_count_group shall fail validation.

10. Three canonical engineering views

The views shall be generated from the canonical YAML, not hand-maintained separately.

10.1 Top view — optical and action geometry

Required annotations:

+X travel and +Y lateral axes;

minimum 600×600 mm internal hood boundary;

central camera optical axis;

four light quadrants;

central optical bay and window;

matte inter-bay or source baffles;

measured 474–484 mm FOV boundary;

64 px abstain ring;

action-safe region;

minimum action-safe lateral width 444.375 mm;

skirt/labyrinth boundary;

forbidden carrier, wheel, cable, or structural intrusion region;

note that the drawing is schematic and Stage C owns physical non-occlusion.

The view shall not depict the whole 600 mm hood as action coverage.

10.2 Side view — cassette, carrier, and vertical geometry

Required annotations:

rear-three-point host interface as host-unresolved;

transverse carrier bar;

carrier upper frame;

passive ground-following mechanism;

gauge wheel outside the action-safe region;

removable lower cassette;

camera, hood, window, and light assembly;

520–590 mm working-distance adjustment;

ground, 55 mm focus, and 110 mm canopy planes;

100–150 mm skirt length;

0–20 mm operating clearance;

intervention mounting datum;

camera-to-intervention along-track offset shown as null / physically measured later;

compute/power tray;

transport lock and operating/deployed-state sensor;

local and carrier coordinate frames.

No structural member dimension or load rating shall be implied unless source-bound.

10.3 Interface view — power, data, timing, and safety

Required nodes and flows:

exact host power source, shown unresolved;

regulated capture-module power;

separately fused camera, light, controller, and compute branches;

Basler external 12–24 VDC;

24 V light bus;

real-time controller;

quadrature encoder;

same-event trigger and encoder latch;

Basler camera;

ExposureActive;

isolated strobe driver;

four light channels;

dedicated USB3 root;

RTX 3090 compute lane;

frame/result identity path;

scheduler/intervention interface;

E-stop, watchdog, hood-open, overtemperature, deployed-state, and brownout inputs;

no-fire outputs;

chemical-enable line shown absent or disabled.

The interface view is a logical diagram, not a released wiring schematic.

10.4 View-generation contract

Each SVG shall:

use a fixed viewBox;

use deterministic ordering;

contain no timestamps, random IDs, hostnames, or absolute paths;

include the integration contract SHA-256 and generated result SHA-256;

include a NOT A FABRICATION DRAWING note;

derive all displayed values from the result JSON;

fail generation if a required annotation value is null unless the annotation explicitly displays UNRESOLVED;

use the same IDs and terminology as the YAML and Markdown;

be byte-identical for identical inputs.

11. Bounded unresolved evidence
11.1 Exact rear host

Current state: HOST_UNRESOLVED.

Smallest discovery:

inspect actual on-hand or immediately rentable rear-three-point tractor candidates;

cap the first pass at two rear candidates;

record exact make, model, year, configuration, and serial where available;

capture exact manuals and rating definitions;

measure hitch geometry, wheel tracks, ground clearance, mounting zones, power, cable route, and controlled speed;

record axle ratings, ballast, hitch rating measurement point, and proof-carrier load location;

preserve missing fields as null.

Decision rule:

a rear host becomes HOST_ARCHITECTURE_ELIGIBLE only when all structural, geometry, speed, power, cable, operating-state, and safety evidence is exact and complete;

apparent physical fit is insufficient;

if a rear candidate fails because of wheel disturbance, visibility, clearance, cable, registration, power, or documented capacity, open at most one front-three-point challenger;

if no exact host exists, retain the rear proof architecture but keep HOST_UNRESOLVED_NO_BUILD_AUTHORITY.

11.2 Whole-system power

Current state: OPEN_BENCH_VARIABLE.

Smallest discovery:

instrument the exact compute, camera, controller, light-driver, and conversion path;

measure steady-state and transient input at the one-camera 15 Hz profile;

include startup, strobe pulse, thermal soak, and induced brownout behavior;

record converter efficiency and cable drop;

hash-bind raw logs.

Decision rule:

exact host power eligibility remains unresolved until the host supply exceeds the measured requirement with a documented margin and without violating droop or brownout gates;

RTX board power and PSU nameplate values cannot close this gate.

11.3 Cassette mechanical payload and CG

Current state: OPEN_BENCH_VARIABLE.

Smallest discovery:

weigh the assembled cassette, carrier ground-following hardware, gauge wheel, compute tray, and cables separately;

locate each CG relative to the declared carrier datum;

calculate deployed and transport moments;

retain measurement artifacts and uncertainty.

Decision rule:

host structural eligibility remains unresolved if any required mass, CG, load location, or exact rating is absent.

11.4 Light/enclosure bench variables

Current state: OPEN_BENCH_VARIABLE.

The integration layer shall reference the terminal light/enclosure bounded bench sequence rather than restate or expand it.

Variables include:

exact LED;

diffuser;

current vector;

aim and stand-off;

external lux;

CCT/CRI physical evidence;

thermal interface;

heatsink/fan state;

window identity;

skirt implementation.

Decision rule:

only one exact installed profile passing the existing Stage-B, C, and D gates may populate these fields;

no physical result is created by the integration calculator;

each permitted failure class receives at most one terminal-lane remediation before re-plan.

11.5 Skirt mechanical safety

Current state: unresolved outside the optical acceptance.

Smallest discovery:

the mechanical-safety owner freezes one breakaway-force limit, one fixture, and one snag/entanglement protocol before plant-contact use.

Decision rule:

light rejection may be documented without a plant-contact safety claim;

until this criterion passes, the skirt is limited to stationary or controlled non-contact optical proof.

11.6 Camera-to-intervention registration

Current state: null and external to A–E architecture acceptance.

Decision rule:

populate only through physical Stage F using the existing accepted methods;

CAD cannot supply the offset, valve latency, footprint, or no-fire distance;

the integrated view may show the datum but must label all values unmeasured.

12. Rejected alternatives
Alternative	Disposition	Reason
Treat the hood’s 600 mm width as safe swath	Rejected	Confuses enclosure footprint with calibrated action region and overstates throughput
Shrink the hood to 444.375 mm because that is the safe swath	Rejected	Removes required light, baffle, skirt, window, and service volume
Use the unmasked 474–484 mm FOV as action width	Rejected	Ignores the frozen outer 64 px abstain ring
Mount camera and future intervention hardware independently to the tractor bar	Rejected	Loses the local rigid calibration relationship
Put the tractor hitch, gross lift, ballast, and host-specific structure inside the reusable cassette	Rejected	Makes the cassette non-portable and mixes host qualification with calibrated bay identity
Let the integration layer own camera, light, or carrier choices	Rejected	Reallocates lane ownership and permits silent overrides
Create one overloaded READY status	Rejected	Hides independent source, host, physical, and claim states
Duplicate A–F thresholds in a new integration acceptance policy	Rejected	Creates two safety authorities and drift risk
Hand-maintain view values separately from YAML	Rejected	Allows diagram/document drift
Use a weighted architecture score	Rejected	Lets cost compensate for failed hard interfaces
Sum the V2 module budget and unknown carrier cost	Rejected	Treats unknowns as zero and creates a false integrated price
Size host power from 60 W + 350 W	Rejected	Mixes measured module ceiling with GPU reference board power
Treat 750 W PSU guidance as measured vehicle draw	Rejected	Wrong measurement point
Use one central long USB trunk	Rejected	Violates the locking ≤3 m and dedicated-root boundary
Assume two cameras on the current RTX 3090	Rejected	No passing multi-camera end-to-end evidence
Open 20 Hz because camera transport can carry it	Rejected	Compute and end-to-end deadline remain unproven
Promote a sensor or light challenger in integration	Rejected	Promotion belongs to its terminal lane and physical A/B
Treat synthetic or diagram evidence as physical PASS	Rejected	Existing acceptance is physical and hash-bound
Include chemical hardware because a host sprayer already has it	Rejected	Existing host chemistry receives no authority credit
13. Failure behavior and edge cases
Condition	Required result
Terminal survey missing or uncommitted	INTEGRATION_INVALID_SOURCE_DRIFT
Source SHA mismatch	Stop before calculation
Duplicate YAML mapping key	Parse failure
YAML merge redefines a safety or ownership field	Parse failure
Unknown owner or decision state	Schema failure
Frozen field is null	Schema failure
Non-owning lane supplies a missing value	Cross-lane conflict
Two lane sources disagree on a frozen value	INTEGRATION_INVALID_CROSS_LANE_CONFLICT
Generated Markdown, JSON, CSV, or SVG has stale hashes	Invalid artifact set
Hood width used in throughput calculation	Test failure
Safe width computed without outer abstain ring	Test failure
Carrier structure enters FOV or safe region	Architecture conflict; no workaround by digital crop
Exact host absent	Keep host unresolved
Structural rating absent	Host unqualified
Mechanical mass or CG absent	Host structural state unresolved
Whole-system power absent	Host power state unresolved
Carrier cost absent	Integrated cost null
Cost field absent	Never zero
Existing RTX reused	Incremental acquisition may be zero; power remains non-zero or null
Camera or lens changes	Hand back to sensor lane; invalidate integrated geometry and A–E
Window, hood, light, or current changes	Invalidate the terminal lane’s required stages and regenerate integration
Carrier mount or height changes	Invalidate affected geometry, registration, and views
Encoder changes	Invalidate timing, scale, Stage E/F interfaces
Compute lane changes	Invalidate Stage E and power interface
Host lift, reverse, fold, transport, or deployed state invalid	No-fire
Camera or compute unavailable	Local bay no-fire
Light channel missing	Frame/profile invalid; no-fire
E-stop or watchdog fault	Hard disable strobe and intervention enable
Brownout/reboot	Default no-fire; do not recover pending commands
Physical A–E absent	No controlled-capture claim
Physical A–F absent	No dry-marker claim
Deposition/crop-injury thresholds absent	Chemical fire remains impossible
14. Change and invalidation matrix
Change	Minimum invalidation
Any terminal survey byte change	Regenerate YAML result, BOM, Markdown, and all three views
Capture V2 or acceptance source change	Full integration re-plan or explicit source re-freeze
Camera, lens, ROI, pixel pitch, FOV, WD, aperture, exposure	Geometry, blur, payload, views, BOM, compute interface, and physical A–E
Outer abstain ring	Safe swath, throughput, top view, action interface
LED, diffuser, current, pulse, driver, window, hood, skirt, cooling	Power, BOM, top/side/interface views, Stage B–E as owned by terminal lane
Cassette datum or camera-to-intervention relationship	Side view, registration interface, Stage C–F
Carrier host or hitch	Host qualification, payload, power, side view, Stage B/E and registration checks
Ground-following or gauge-wheel geometry	Side view, operating height, encoder, Stage C–F
Encoder or timing controller	Interface view, timing calculations, Stage B/E/F
USB root, cable, compute platform, checkpoint	Payload/compute/power interfaces and Stage B/E
Second camera or changed pitch	Full applicable multi-bay integration and separate compute evidence
Documentation-only clarification with no value or hash change	Consistency audit only
SVG layout-only change with identical annotations	View snapshot validation only

When impact is ambiguous, invalidate the broader set.

15. Allowed implementation artifacts

Codex shall create or modify only:

docs/research/SPOT_SPRAY_INTEGRATED_PRODUCT_ARCHITECTURE_V1.md;

configs/deploy/spot_spray_integrated_product_architecture_v1.yaml;

scripts/derive_spot_spray_integrated_product_architecture_v1.py;

docs/results/spot_spray_integrated_product_architecture_v1.json;

docs/results/spot_spray_integrated_product_bom_v1.csv;

docs/results/spot_spray_integrated_product_top_view_v1.svg;

docs/results/spot_spray_integrated_product_side_view_v1.svg;

docs/results/spot_spray_integrated_product_interface_view_v1.svg;

tests/test_spot_spray_integrated_product_architecture_v1.py.

Do not modify:

terminal lane plans or surveys;

capture or rig-acceptance configs;

evaluators;

compute results;

action contracts;

release documents;

dependencies;

workflows;

README files;

implementation code outside the one derivation script;

physical receipts;

CAD or binary artifacts.

No new dependency is permitted. SVG generation shall use the standard library and existing project dependencies only.

16. Ordered implementation ledger
Package 0 — Admit and freeze the terminal source set

Dependencies: none.

 - [ ] Verify that all three terminal surveys and all three terminal lane plans exist.

 - [ ] Verify that their exact bytes are committed on the implementation base.

 - [ ] Record the exact implementation-base commit that contains those bytes.

 - [ ] Compute and record each file’s SHA-256.

 - [ ] Record the supplied historical remote and local states only as provenance, not as the final source lock.

 - [ ] Pin the frozen capture, acceptance, evaluator, runbook, product decision, integrated release, action, and compute authorities.

 - [ ] Verify the known frozen hashes before reading lane decisions.

 - [ ] Reject any dirty or mismatched terminal source with INTEGRATION_INVALID_SOURCE_DRIFT.

 - [ ] Record source roles and lane ownership.

Intended outcome: one exact admissible source set.

Acceptance evidence:

every required source has a path, SHA-256, owner, role, and containing commit;

known frozen hashes match;

a one-byte mutation fails before calculations;

an uncommitted terminal survey cannot be integrated.

Package 1 — Implement the canonical ownership and status schema

Dependencies: Package 0.

 - [ ] Define the owner enum.

 - [ ] Define the decision-state enum.

 - [ ] Define the evidence-class enum.

 - [ ] Define required decision-item fields.

 - [ ] Add independent architecture, source-integrity, host, physical, and claim status axes.

 - [ ] Add explicit false claim boundaries for procurement, physical READY, field GO, dry-marker READY, and chemical fire.

 - [ ] Require non-null source-bound values for every frozen item.

 - [ ] Require a bounded discovery and decision rule for every null open item.

 - [ ] Reject unknown enum values, duplicate IDs, duplicate ownership, and missing dependencies.

 - [ ] Prevent integration-owned records from replacing lane-owned decisions.

Intended outcome: the smallest schema that distinguishes frozen, variable, challenger, host-unresolved, rejected, unsupported, and out-of-scope states.

Acceptance evidence:

valid baseline parses deterministically;

null frozen values fail;

unknown status fails;

duplicate owner assignment fails;

chemical enable cannot become true;

one overloaded READY state does not exist.

Package 2 — Encode the resolved one-bay architecture

Dependencies: Packages 0–1.

 - [ ] Populate the frozen camera, lens, ROI, FOV, WD, aperture, exposure, rate, and service-class values from sources.

 - [ ] Populate the four-quadrant light and hood architecture.

 - [ ] Populate the rear-three-point proof topology and host-unresolved state.

 - [ ] Define F_world, F_carrier, F_cassette, F_camera, F_ground_calibration, F_intervention_mount, and F_encoder.

 - [ ] Encode the cassette/carrier ownership split.

 - [ ] Encode the no-intrusion volumes and action-safe region.

 - [ ] Encode exact data, timing, encoder, compute, power, and safety interfaces.

 - [ ] Encode the local intervention datum with null physical offset.

 - [ ] Encode one camera and one active bay only.

 - [ ] Keep all multi-bay fields compatibility-only and closed.

Intended outcome: one human- and machine-readable architecture without lane reallocation.

Acceptance evidence:

every component and interface has one owner;

cassette and carrier responsibilities do not overlap ambiguously;

host-specific structure is absent from the reusable cassette;

camera/light internals remain lane-owned;

intervention values remain null and external;

no second camera or 20 Hz capability is active.

Package 3 — Reconcile geometry and deterministic calculations

Dependencies: Package 2.

 - [ ] Calculate active sensor span.

 - [ ] Calculate GSD at 474, 480, and 484 mm.

 - [ ] Calculate nominal 10 and 20 mm pixel spans.

 - [ ] Calculate the 0.9375 safe fraction.

 - [ ] Calculate minimum, nominal, and maximum action-safe widths.

 - [ ] Calculate 0.5 and 1.0 m/s smear and blur.

 - [ ] Calculate Bayer10 and Bayer12 data payload at 15 and 20 Hz.

 - [ ] Calculate 20% transport headroom.

 - [ ] Calculate conservative one-bay gross geometric throughput.

 - [ ] Retain multi-bay formulas as inactive compatibility rules.

 - [ ] Prohibit hood width and unmasked FOV in throughput calculations.

 - [ ] Add mechanical-payload and moment formulas with null propagation.

 - [ ] Add power aggregation with separate measured, reference, ceiling, and null fields.

 - [ ] Emit a terminal conflict if any calculated golden value disagrees with the frozen source.

Intended outcome: one reproducible calculation authority.

Acceptance evidence:

exact golden values are reproduced;

changing the outer ring changes safe width and throughput;

changing hood width does not change action-safe throughput;

missing mass yields null mechanical payload;

missing compute draw yields null integrated host power;

no calculation emits readiness.

Package 4 — Normalize the BOM and cost boundaries

Dependencies: Packages 1–3.

 - [ ] Copy the source-bound V2 module budget items with their evidence classes and dates.

 - [ ] Recompute the 3115–6545 USD subtotal.

 - [ ] Recompute the 3582.25–7526.75 USD contingency range.

 - [ ] Keep public prices, budgetary allowances, landed quotes, and unknowns distinct.

 - [ ] Mark the existing RTX 3090 as reused without converting power or opportunity cost to zero.

 - [ ] Create carrier, host, intervention, and whole-system-power rows with null costs where evidence is absent.

 - [ ] Define double_count_group for overlapping host-integration, compute-mount, and carrier-tray categories.

 - [ ] Reject two included BOM lines in the same double-count group.

 - [ ] Keep the integrated one-bay total null until every required cost is complete.

 - [ ] Generate deterministic CSV ordering by cost_scope, owner, then bom_item_id.

 - [ ] Exclude chemical, yield, acreage, labor-saving, and autonomy benefits.

Intended outcome: a useful BOM that is honest about incomplete integrated cost.

Acceptance evidence:

module subtotal and contingency values match the golden calculations;

carrier cost absence does not produce a numeric integrated total;

unknown values serialize as empty/null, never zero;

duplicate cost ownership fails;

the CSV and JSON totals agree exactly.

Package 5 — Bind acceptance and failure behavior

Dependencies: Packages 0–4.

 - [ ] Add exact acceptance contract and evaluator identities.

 - [ ] Add controlled-capture and dry-marker decision-target semantics.

 - [ ] Add the chemical-fire prohibition verbatim in meaning.

 - [ ] Define the integration result enum.

 - [ ] Reject source or acceptance drift before any architectural PASS.

 - [ ] Define no-fire behavior for every material carrier, timing, compute, lighting, calibration, and safety fault.

 - [ ] Define pending-command cancellation and recovery.

 - [ ] Define change invalidation from lane or interface changes.

 - [ ] Ensure the integration derivation cannot evaluate a physical receipt or imitate the rig evaluator.

 - [ ] Ensure synthetic fixtures, diagrams, and derived calculations cannot become physical evidence.

Intended outcome: one fail-closed compatibility layer that does not become a second safety evaluator.

Acceptance evidence:

a forged physical_ready: true field is rejected;

a changed acceptance hash invalidates the integration result;

every listed fault maps to no-fire or invalid evidence;

the result contains explicit controlled_capture_authorized: false, dry_marker_ready: false, and chemical_fire_allowed: false.

Package 6 — Generate the three engineering views

Dependencies: Packages 2–5.

 - [ ] Generate the top view from result JSON.

 - [ ] Show 600×600 mm hood, 474–484 mm FOV, outer abstain ring, and minimum 444.375 mm action-safe width as distinct annotations.

 - [ ] Generate the side view with carrier, ground following, cassette, WD, canopy planes, skirt, intervention datum, and unresolved host values.

 - [ ] Generate the interface view with power, trigger, encoder, USB3, compute, safety, and no-fire paths.

 - [ ] Include exact config and result hashes in every SVG.

 - [ ] Include NOT A FABRICATION DRAWING.

 - [ ] Keep coordinates, ordering, text, and IDs deterministic.

 - [ ] Display unresolved values explicitly rather than omitting them.

 - [ ] Prevent a manually edited SVG from passing hash validation.

 - [ ] Validate that every dimension shown in an SVG exists in result JSON.

Intended outcome: three coherent views that cannot contradict the machine-readable contract.

Acceptance evidence:

identical inputs produce byte-identical SVGs;

each SVG contains the expected source/result hashes;

the top view never labels 600 mm as safe swath;

the side view shows physical offset as unresolved;

the interface view shows chemical enable disabled;

every required annotation is present.

Package 7 — Write the human-readable architecture

Dependencies: Packages 0–6.

 - [ ] Create docs/research/SPOT_SPRAY_INTEGRATED_PRODUCT_ARCHITECTURE_V1.md.

 - [ ] Add the current five-axis status summary.

 - [ ] Add the source-lock table.

 - [ ] Separate source-derived facts from integration inferences.

 - [ ] Explain the 600 mm versus 444.375 mm boundary.

 - [ ] Explain cassette versus carrier responsibilities.

 - [ ] Include the canonical data/control flow.

 - [ ] Include mechanical, optical, timing, data, compute, power, safety, cost, and acceptance interfaces.

 - [ ] Embed or link all three generated views.

 - [ ] Include the normalized BOM and why the integrated total remains null.

 - [ ] Include the deterministic calculations and exact limitations.

 - [ ] Include host, power, payload, lighting, skirt, and intervention unresolved items.

 - [ ] Include bounded discovery and decision rules.

 - [ ] Include rejected alternatives.

 - [ ] Include change invalidation and re-plan triggers.

 - [ ] State that the next physical value is one exact host-qualified, hash-bound one-bay A–E bench, not another market survey.

 - [ ] State that the document makes no procurement, physical READY, field GO, dry-marker READY, certified-ingress, or chemical-fire claim.

Intended outcome: a future integrator can understand what is selected, what remains open, who owns each item, and what evidence changes each state.

Acceptance evidence:

every numeric table value comes from result JSON;

every BOM total comes from the CSV/JSON;

all three views match the contract;

no unsupported readiness wording appears;

no lane decision is silently altered.

Package 8 — Tests, determinism, and scope audit

Dependencies: Packages 0–7.

 - [ ] Add golden tests for all geometry, blur, payload, swath, throughput, power, and cost calculations.

 - [ ] Add source-drift tests.

 - [ ] Add duplicate-key tests.

 - [ ] Add null-propagation tests.

 - [ ] Add ownership-conflict tests.

 - [ ] Add status-promotion rejection tests.

 - [ ] Add hood-versus-safe-swath regression tests.

 - [ ] Add BOM double-count tests.

 - [ ] Add stale-view and stale-document hash tests.

 - [ ] Run the derivation twice in separate temporary directories and compare exact bytes.

 - [ ] Verify JSON key ordering, CSV row ordering, SVG ordering, UTF-8 encoding, and final newline behavior.

 - [ ] Verify only the allowed files changed.

 - [ ] Verify no dependency or workflow changed.

 - [ ] Verify no existing acceptance source changed.

Intended outcome: one deterministic and bounded integration package.

Acceptance evidence:

focused tests pass;

two derivations are byte-identical;

a one-byte source mutation fails;

all generated artifacts bind the same config/result hashes;

file-scope validation shows only allowed artifacts.

17. Exact validation
17.1 Derivation command

The script shall expose one deterministic command equivalent to:

Bash
PYTHONHASHSEED=0 TZ=UTC LC_ALL=C.UTF-8 \
.venv/bin/python scripts/derive_spot_spray_integrated_product_architecture_v1.py \
  --config configs/deploy/spot_spray_integrated_product_architecture_v1.yaml \
  --result docs/results/spot_spray_integrated_product_architecture_v1.json \
  --bom docs/results/spot_spray_integrated_product_bom_v1.csv \
  --top-view docs/results/spot_spray_integrated_product_top_view_v1.svg \
  --side-view docs/results/spot_spray_integrated_product_side_view_v1.svg \
  --interface-view docs/results/spot_spray_integrated_product_interface_view_v1.svg \
  --document docs/research/SPOT_SPRAY_INTEGRATED_PRODUCT_ARCHITECTURE_V1.md

The script shall not access the network or fetch current prices.

17.2 Focused tests
Bash
.venv/bin/python -m pytest -q \
  tests/test_spot_spray_integrated_product_architecture_v1.py
17.3 Golden numeric checks

Tests shall verify at least:

active_sensor_span_mm = 7.0656


gsd_474_mm_px = 0.2314453125
gsd_480_mm_px = 0.234375
gsd_484_mm_px = 0.236328125


safe_fraction = 0.9375
safe_width_474_mm = 444.375
safe_width_480_mm = 450.0
safe_width_484_mm = 453.75


smear_1m_s_170us_mm = 0.17
maximum_blur_px <= 0.75


bayer10_15hz_mbit_s = 629.1456
bayer10_20hz_mbit_s = 838.8608
bayer12_15hz_mbit_s = 754.97472
bayer12_20hz_mbit_s = 1006.63296


coverage_0_5m_s_ha_h = 0.0799875
coverage_1_0m_s_ha_h = 0.159975


module_budget_min_usd = 3115.0
module_budget_max_usd = 6545.0
module_budget_with_contingency_min_usd = 3582.25
module_budget_with_contingency_max_usd = 7526.75


hood_internal_minimum_mm = [600.0, 600.0]
proof_camera_count = 1
end_to_end_rate_hz = 15.0
end_to_end_p95_deadline_ms = 66.66666666666667

Floating calculations shall use one documented tolerance no looser than 1e-9 for these golden values.

17.4 Required failure tests

Tests shall prove:

600 mm never enters the safe-swath or throughput formula;

removing the outer abstain ring changes safe width and causes the frozen comparison to fail;

changing 444.375 to a rounded 444 fails;

changing proof camera count to two fails;

changing baseline rate to 20 Hz fails;

setting host make/model to a generic tractor class fails qualification;

setting an unknown cost or mass to zero fails;

setting integrated total while carrier cost is null fails;

setting whole-system draw to 410 W without measurement fails;

setting chemical enable true fails;

changing an acceptance hash fails before calculations;

duplicate YAML keys fail;

a stale SVG or Markdown hash fails;

manual changes to generated numeric values fail.

17.5 Determinism comparison

Run the generator twice into separate temporary directories. Compare:

Bash
cmp <run-1>/spot_spray_integrated_product_architecture_v1.json \
    <run-2>/spot_spray_integrated_product_architecture_v1.json


cmp <run-1>/spot_spray_integrated_product_bom_v1.csv \
    <run-2>/spot_spray_integrated_product_bom_v1.csv


cmp <run-1>/spot_spray_integrated_product_top_view_v1.svg \
    <run-2>/spot_spray_integrated_product_top_view_v1.svg


cmp <run-1>/spot_spray_integrated_product_side_view_v1.svg \
    <run-2>/spot_spray_integrated_product_side_view_v1.svg


cmp <run-1>/spot_spray_integrated_product_interface_view_v1.svg \
    <run-2>/spot_spray_integrated_product_interface_view_v1.svg


cmp <run-1>/SPOT_SPRAY_INTEGRATED_PRODUCT_ARCHITECTURE_V1.md \
    <run-2>/SPOT_SPRAY_INTEGRATED_PRODUCT_ARCHITECTURE_V1.md

Any difference is a failure.

17.6 File-scope validation
Bash
git diff --check -- \
  docs/research/SPOT_SPRAY_INTEGRATED_PRODUCT_ARCHITECTURE_V1.md \
  configs/deploy/spot_spray_integrated_product_architecture_v1.yaml \
  scripts/derive_spot_spray_integrated_product_architecture_v1.py \
  docs/results/spot_spray_integrated_product_architecture_v1.json \
  docs/results/spot_spray_integrated_product_bom_v1.csv \
  docs/results/spot_spray_integrated_product_top_view_v1.svg \
  docs/results/spot_spray_integrated_product_side_view_v1.svg \
  docs/results/spot_spray_integrated_product_interface_view_v1.svg \
  tests/test_spot_spray_integrated_product_architecture_v1.py


git diff --name-only <implementation-base>...HEAD

Acceptance:

no whitespace errors;

no unapproved files;

no lane-survey edits;

no acceptance edits;

no dependency or workflow edits;

no binary or CAD artifacts.

18. Material risks and rollback
18.1 Terminal source-set drift

Risk: the integration is generated from local survey bytes that are later changed or were never committed.

Mitigation:

exact commit and per-file SHA pins;

dirty-source rejection;

generated-output hash binding.

Rollback:

restore the last complete source bundle and regenerate every derived artifact;

never keep a newer Markdown or view with an older config/result.

18.2 Cross-lane ownership leakage

Risk: integration prose accidentally turns a lane-owned variable into a frozen integrated decision.

Mitigation:

one owner per item;

integration-only allowlist;

tests for non-owning values.

Rollback:

restore the owning lane’s terminal value;

remove the integration override;

regenerate all artifacts.

18.3 Hood/swath semantic confusion

Risk: a future user interprets 600 mm as coverage or reduces the enclosure to the safe image width.

Mitigation:

separate schema fields;

separate annotations;

regression tests;

throughput calculated only from safe width.

Rollback:

restore canonical field names and regenerate views/document.

18.4 False integrated cost

Risk: known module cost is summed with null carrier, host, or intervention values.

Mitigation:

null-propagating totals;

cost-scope separation;

double-count groups.

Rollback:

revert to the last BOM whose integrated total is null until cost completeness is restored.

18.5 Power under-sizing

Risk: reference GPU power or PSU guidance is mistaken for measured host demand.

Mitigation:

separate reference and measured fields;

host qualification blocked by null power;

bounded measurement.

Rollback:

remove any inferred integrated power value and restore null.

18.6 Mechanical payload under-definition

Risk: host selection proceeds without measured cassette mass, CG, or load location.

Mitigation:

null-propagating payload and moment;

no structural eligibility from nominal hitch capacity.

Rollback:

return host state to HOST_UNRESOLVED.

18.7 Diagram authority creep

Risk: generated views are treated as released fabrication or wiring drawings.

Mitigation:

explicit non-fabrication note;

schematic-only dimensions;

no unsupported structural or conductor data.

Rollback:

remove unsupported annotation and regenerate.

18.8 Physical-readiness leakage

Risk: a consistent architecture result is mistaken for physical A–E or A–F.

Mitigation:

independent status axes;

prohibited readiness strings;

exact acceptance binding;

explicit false claims.

Rollback:

invalidate the result and restore PRE_REAL_NOT_READY.

19. Stopping rules

Stop implementation and emit a blocking integration result when:

a terminal lane survey or plan is absent, uncommitted, or hash-mismatched;

a frozen upstream identity differs;

two lane sources conflict on a material frozen value;

a frozen decision has no owning source;

an integration calculation disagrees with a frozen golden value;

the normalized BOM double-counts a cost;

a generated view cannot be produced without inventing a required value;

the document or view would require a physical or structural claim unsupported by the sources;

the integration layer would need to modify a terminal lane or acceptance contract.

Stop research when:

every material item is frozen, explicitly open with one bounded discovery, challenger-only with a trigger, host-unresolved, rejected, unsupported, or out of scope;

every shared interface has an owner and failure behavior;

every required calculation is deterministic;

all three views are generated from the same result;

no unresolved field can change the selected one-bay architecture without meeting a documented re-plan trigger.

Do not continue catalog research merely because:

exact host values are missing;

the integrated cost is null;

LED bench values are unset;

cassette mass is unmeasured;

the intervention offset is null.

Those are physical or owner-supplied discovery items, not market-research gaps.

20. Re-plan triggers

Re-plan this integrated architecture rather than patching around it if any of the following occurs:

the Basler PRO/C23 baseline is rejected by the sensor lane;

the required 474–484 mm FOV or 444.375 mm safe width cannot be achieved;

the 600×600 mm enclosure cannot package the frozen optical/light design without occlusion;

no bounded light/enclosure remediation passes the frozen gates;

one-camera 15 Hz Stage E fails;

product speed exceeds 1.0 m/s;

required safe swath exceeds 444.375 mm;

action service class moves below 20 mm;

a second camera or multi-bay proof becomes required;

certified ingress, washdown, dust, shock, or vibration becomes a requirement;

no rear or triggered front host can preserve the frozen module;

exact host power or structure cannot support the measured one-bay assembly;

the intervention footprint or crop-safety contract changes the required optical/action geometry;

the acceptance authority changes materially;

chemical operation becomes a requested scope.

21. Completion criteria

This plan is complete when Codex can demonstrate all of the following:

 - [ ] The exact terminal lane source set is committed and hash-pinned.

 - [ ] The canonical YAML contains the resolved one-bay architecture and no unauthorized lane decisions.

 - [ ] Ownership, decision state, evidence class, null handling, and invalidation are explicit for every material item.

 - [ ] 600 mm hood and 444.375 mm action-safe swath are represented as different concepts everywhere.

 - [ ] Cassette and carrier responsibilities are unambiguous.

 - [ ] Geometry, blur, data payload, swath, throughput, power status, mechanical-payload status, and cost are deterministically derived.

 - [ ] Unknown host, power, mass, CG, carrier-cost, and intervention values remain null.

 - [ ] The BOM exposes module cost while keeping the incomplete integrated total null.

 - [ ] The existing acceptance contract remains the sole physical decision authority.

 - [ ] Top, side, and interface SVGs are generated from the same result JSON.

 - [ ] All generated artifacts carry matching source/config/result identities.

 - [ ] Golden, mutation, ownership, null, cost, hash, and determinism tests pass.

 - [ ] Only the allowed artifacts changed.

 - [ ] The human-readable architecture makes no procurement, physical READY, field GO, dry-marker READY, certified-ingress, or chemical-fire claim.

 - [ ] The final integration result is INTEGRATION_CONSISTENT_PRE_REAL, with host and physical states still explicitly unresolved.

22. Codex execution reconciliation

The worker lane contract is authoritative over three planner assumptions that
cannot be implemented literally in this shared manager-owned worktree:

- terminal surveys are admitted by exact-byte SHA-256 with fail-closed drift
  detection even while their owning lanes remain uncommitted; no containing
  commit is fabricated;
- the human-readable deliverable is the authorized
  `docs/SPOT_SPRAY_PRODUCT_ARCHITECTURE_V1.md`, not the planner-proposed
  `docs/research/` path;
- the authorized annotated views are exterior, underside, and optical
  cross-section. Together they carry the planner's carrier, action geometry,
  optics, timing, compute, safety, and no-fire interface content without
  becoming fabrication drawings.

Implementation completion is determined by the generated package manifest,
exact source re-verification, byte-determinism audit, and focused tests—not by
silently checking planner items whose literal premise was superseded. The
result remains `INTEGRATION_CONSISTENT_PRE_REAL`, `HOST_UNRESOLVED`, and
`PRE_REAL_NOT_READY`; all procurement, physical acceptance, field/product GO,
dry-marker readiness, and chemical-fire authority remain false.
