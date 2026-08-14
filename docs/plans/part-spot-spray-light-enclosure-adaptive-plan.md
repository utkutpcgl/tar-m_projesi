Status: READY
Planner depth: 0
Parent plan: (root plan)

Spot-Spray Illumination and Enclosure Proof Architecture Plan
1. Outcome and primary bottleneck

This part shall produce one decision-complete research and physical-proof specification for docs/research/SPOT_SPRAY_LIGHT_ENCLOSURE_SURVEY_V1.md.

The primary bottleneck is not another camera, modality, or emitter catalog comparison. It is the absence of a hash-bound physical Stage-D result from one installed camera–window–hood–light assembly. The repository remains PRE_REAL_NOT_READY; physical A–E is the next controlled-capture unblock, while chemical fire remains unsupported. 

tarım-projesi-part-spot-spray-l…

The plan resolves the following baseline:

One central camera optical bay using the sensor lane’s frozen camera, lens, native ROI, FOV, working distance, aperture, exposure, trigger, and frame-rate contract.

Four independently current-limited, visible broad-spectrum white LED quadrants around the optical bay.

All four quadrants firing simultaneously for the default capture profile.

One removable opal diffuser per quadrant.

Camera ExposureActive driving an isolated strobe driver.

A rigid matte-black enclosure with no direct ground-to-sky line of sight.

A two-layer staggered flexible skirt and two-stage light labyrinth.

A replaceable, tilted, AR-coated optical window installed during all calibration and acceptance.

Light sealing measured through image-space ambient rejection, not claimed through an ingress rating.

Passive external heat rejection as the first cooling topology; externally forced heatsink airflow only as a bounded thermal challenger.

Cross-polarization disabled by default and promoted only by its existing paired wet-glare gate.

Exact LED SKU, diffuser SKU, quadrant aim, current vector, lux, optical energy, heatsink, and fan state left provisional until installed-rig evidence selects them.

A passing result may support FROZEN_FOR_CONTROLLED_CAPTURE only through the existing A–E contract. It shall not imply purchase approval, field readiness, production readiness, certified ingress, spray deposition success, crop safety, or chemical GO.

2. Goals

Stabilize visible crop, weed, soil, canopy-height, and local-structure cues within the existing single-camera RGB proof contract.

Select the simplest buildable illumination and enclosure architecture that can satisfy all existing Stage-B, Stage-C, and Stage-D dependencies without relaxing exposure, blur, optics, or safety constraints.

Separate source-backed facts, transparent calculations, engineering hypotheses, and bench-selected values.

Define the mechanical, optical, electrical, timing, thermal, metadata, and fail-closed interfaces needed by Codex.

Define deterministic baseline-selection, challenger-promotion, rollback, and re-plan rules.

Define a bounded installed-rig bench sequence that produces observable PASS, FAIL, or NOT_MEASURED evidence.

Preserve the existing acceptance contract and use the survey as explanatory and decision-support documentation rather than as a second authority.

End research once each material design choice has either direct evidence or a bounded physical decision rule.

3. Non-goals

Camera, lens, shutter, sensor format, RGB/monochrome, NIR, multispectral, thermal, or depth selection.

Changes to native ROI, FOV, working distance, focus plane, aperture, exposure, frame rate, tiling, or model input.

Model training, inference implementation, tracking implementation, or GPU capacity planning.

Nozzle design, nozzle placement, chemical selection, dose, deposition, crop-injury thresholds, or chemical enablement.

Purchase, supplier commitment, production-quantity BOM, or landed-price authorization.

Certified IP, NEMA, EMC, vibration, impact, washdown, dust, rain, or functional-safety certification.

A claim that high CRI alone proves crop/weed separability.

A claim that diffuse all-on lighting measures plant height.

A claim that an enclosure passing a bounded lux challenge is ready for arbitrary outdoor sunlight or terrain.

A full vehicle, boom, or multi-camera enclosure design.

Relaxation of an existing acceptance threshold to make a candidate pass.

4. Repository and authority boundary

The execution base is the tar-m_projesi repository on main; the supplied context records a clean base at 509aeef8189dfa50dbcba973e871b0d41febe239. 

tarım-projesi-part-spot-spray-l… +1

4.1 Read-only authorities

Codex shall treat these as read-only inputs for this part:

configs/deploy/spot_spray_capture_optimization_v2.yaml

configs/deploy/spot_spray_rig_acceptance_v1.yaml

docs/CONTROLLED_CAPTURE_OPTIMIZATION_V2.md

docs/SPOT_SPRAY_PRODUCT_IMAGING_DECISION_V1.md

docs/SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md

docs/SEGMENTASYON_95_SAHA_KANIT_PLANI_V1.md

The existing acceptance contract pins the frozen V2 sources and rejects missing or nonphysical evidence. This plan shall not modify those pins, thresholds, evaluator semantics, or stage ownership.

4.2 Evidence hierarchy

Material decisions shall use this order:

Installed physical receipt from the exact assembly

Same camera, lens, window, mount, hood, skirt, LEDs, diffusers, driver, power path, current profile, thermal design, and capture controls.

Raw artifacts present and SHA-256 verified.

Highest authority for installed optical, ambient, timing, power, and thermal performance.

Paired installed-rig A/B

One predefined design variable changed at a time.

Same scene, camera controls, pose, window, ambient challenge, and analysis.

Both candidates must satisfy all absolute gates before relative improvement is considered.

Manufacturer primary documentation

Component identity, spectral bin, CRI, pulse current, timing, thermal limits, optical transmission, material temperature limits, and electrical fault behavior.

Does not prove installed-rig performance.

Peer-reviewed machine-vision or agricultural-robotics evidence

Supports architectural patterns such as controlled active light, enclosure, diffusion, synchronization, or glare control.

Does not transfer a published performance result to this rig.

Distributor data and engineering calculations

Availability, budgetary price, approximate thermal or electrical sizing.

Never used as a physical PASS.

Engineering hypothesis

Permitted only when explicitly labeled and paired with a bounded physical test and a deterministic result rule.

Vendor marketing, search snippets, renderer units, unmeasured lux, and synthetic images cannot authorize the physical design.

4.3 Mandatory statement labels in the survey

Every material technical statement in the survey shall be identifiable as one of:

SOURCE FACT — directly supported by a dated citation.

CALCULATION — formula, units, source inputs, assumptions, and result are shown.

ENGINEERING HYPOTHESIS — plausible design choice not yet physically proven.

BENCH VARIABLE — intentionally unset until measured.

PHYSICAL RESULT — may appear only when an exact physical artifact exists.

LIMITATION — an explicit boundary on what the evidence does not prove.

A paragraph may contain more than one label only when each claim’s status remains unambiguous.

4.4 Citation requirements for the survey

For each external source, record:

Source tier.

Publisher or manufacturer.

Document or product title.

Direct URL.

Publication, release, or revision date when stated.

checked_on date.

Exact component or claim supported.

Any applicability limitation.

Rules:

Prefer manufacturer datasheets and official application notes over reseller summaries.

Use direct document or product URLs, not search-result URLs.

State revision date not stated rather than inventing one.

Recheck time-sensitive availability and price on the implementation date.

Public price remains comparison evidence, not purchase authority.

Do not cite one source for a different component family merely because the specifications look similar.

Do not use CRI, CCT, lux, or a vendor beam diagram as a substitute for installed image-space evidence.

5. Frozen upstream interface

The sensor lane owns camera and modality selection. This part must adapt around the following inputs rather than change them.

Interface	Frozen input	Illumination/enclosure obligation	Failure behavior
Camera	Basler a2A2464-77ucPRO, color, factory IR-cut, global shutter	Preserve body, connector, thermal, and service access	Hand back to sensor lane if the body cannot be packaged without violating FOV, temperature, or cable limits
Lens	Basler C23-0824-5M-P	No source, baffle, diffuser, gasket, or window edge may occlude its calibrated cone	Stage C FAIL; no digital crop or resize workaround
Active image	Native centered 2048×2048 ROI at offset (200,0)	Uniformity and ambient gates cover all nine existing regions	Any weak region fails; no center-only average
FOV	Measured 474–484 mm	Hood, skirts, baffles, and light bays must cover the full measured FOV and safe overlap	Rework light/enclosure geometry or re-plan; do not widen/narrow FOV
Working distance	Unit-adjusted and locked within 520–590 mm	Enclosure height and source geometry derive from the measured unit	No fixed catalog-distance assumption
Focus and aperture	Focus plane 55 mm above ground; f/5.6; witness-marked and locked	Window and lighting are accepted only in this installed state	Window or mount change invalidates Stage C onward
Canopy relief	0–110 mm above ground	Illumination shall not create a hard shadow or saturation failure at any accepted plane	Failing plane/region rejects the profile
Exposure	Fixed 170 µs	Light must achieve all gates without longer exposure	Candidate fails; exposure is not relaxed
Baseline rate	15 Hz; Stage-B transport challenge at 20 Hz	Driver supports the existing pulse envelope; no free-running light	Invalid timing or dropped frames fails the relevant stage
Trigger	Camera ExposureActive through isolation	Pulse is contained in the global exposure	Missing, extra, clipped, or jittering pulse invalidates the frame/profile
Camera controls	Fixed manual gain and white balance supplied by the sensor/capture lane before final D measurement	No auto exposure, auto gain, auto WB, or image-dependent current modulation	Any automatic drift makes D evidence noncomparable
Window	Installed during calibration and acceptance	Central optical bay shall use the frozen replaceable tilted AR window class	Removal or replacement invalidates C–E
Safety	Hood-open, overtemperature, E-stop, watchdog, and invalid timing are fail-closed	Strobe enable defaults off; faults must be observable	Invalid frame and downstream no-fire
Multi-bay scale	One proof bay; future pitch ≤430 mm in a continuous hood	Preserve the existing repeat-complete-bay rule	No second-bay readiness claim in this part

The current V2 authority already freezes the four-quadrant white-light class, timing envelope, image-space gates, hood, skirt, labyrinth, and window ranges. 

tarım-projesi-part-spot-spray-l… +1

6. Data and control flow

The survey shall specify this control chain:

The shared real-time controller generates the camera hardware trigger.

The camera exposes using the frozen global-shutter profile.

Camera ExposureActive enters an isolated strobe-driver input.

The driver emits one bounded pulse to the four calibrated LED channels.

The default profile fires all four channels simultaneously.

The driver or controller records:

commanded profile identity;

pulse start and width;

commanded per-channel current;

driver fault state;

bus voltage or droop evidence;

polarization state;

relevant temperatures.

Capture metadata binds the frame to:

capture_profile_id;

strobe_profile_id;

LED/diffuser/window/hood hardware revision;

fixed camera controls;

selected current vector;

thermal state;

evidence run identity.

E-stop, hood-open, watchdog fault, overtemperature, invalid trigger timing, or driver fault inhibits strobe enable.

A missing pulse, additional pulse, partial-channel fault, pulse outside the calibrated envelope, or profile mismatch invalidates the frame for intervention.

This part does not command, schedule, or enable a valve.

Implementation freedom remains for the exact electrical interface, telemetry bus, and driver topology, provided the observable timing, profile-binding, and fail-closed behavior are met.

7. Resolved baseline architecture
7.1 Visible spectrum

Resolved baseline

Broad-spectrum visible white LEDs.

Target CCT 4500–5500 K.

CRI ≥90.

One fixed LED spectral/bin identity per frozen profile.

Factory IR-cut remains installed.

Fixed manual white balance for the final Stage-D run.

No narrowband, NIR, UV, or mixed visible/NIR baseline.

Reasoning

Neutral high-CRI white is the least complex visible-light source compatible with the existing RGB color, texture, and soil/vegetation pipeline. It does not prove crop/weed separability; it creates a reproducible visible-spectrum starting point.

Bench variables

Exact LED manufacturer and part number.

Exact CCT bin and spectral power distribution.

Exact CRI report and measurement method.

LED board size and emitter count.

Pulse-current derating at installed temperature.

Source requirement

The candidate LED’s manufacturer documentation must cover pulse current, pulse duration or duty limits, forward voltage, thermal resistance or derating, CCT binning, CRI, and operating temperature. A generic “high-power white LED” listing is insufficient.

7.2 Emitter topology

Resolved engineering baseline

Four emitter quadrants arranged at the four cardinal positions around the central camera optical bay.

Each quadrant:

is independently current-limited;

has independently addressable enable or diagnostic control;

uses one removable opal diffuser;

has mechanically adjustable initial aim or stand-off;

is mechanically keyed after selection.

The default capture profile fires all four simultaneously.

Equal commanded current is tested first.

A fixed per-quadrant trim vector is allowed only if equal current cannot pass uniformity and the trim profile passes every absolute gate.

Dynamic per-frame current control is prohibited.

The emitter plane and baffle lips remain outside the calibrated lens cone.

Beam overlap shall cover the complete 474–484 mm FOV and 0–110 mm canopy relief.

No LED has a direct optical path to the camera window.

Intended cue behavior

All-on multi-directional illumination is intended to suppress severe single-source shadows while retaining mild local texture and relief. This is an engineering hypothesis, not a height estimate or photometric-stereo claim.

7.3 Default firing policy

Baseline: all four quadrants fire together on every valid exposure.

No alternating quadrant pattern in the default capture profile.

No frame-to-frame random lighting.

No image-content-driven source selection.

Independent channels are retained for:

installation diagnostics;

uniformity tuning;

partial-channel fault detection;

a strictly triggered directional-light challenger.

This preserves temporal appearance consistency for tracking and model input.

7.4 Strobe timing and electrical envelope

Hard requirements:

Camera exposure: 170 µs.

Nominal pulse: 150 µs.

Allowed pulse range: 150–170 µs.

Pulse fully contained inside the exposure.

Maximum supported pulse rate: 20 Hz.

Baseline operating rate: 15 Hz.

Trigger-to-light jitter p95: ≤5 µs.

Pulse-width error: ≤5%.

Bus: 24 V.

Programmable peak-current envelope: 0–10 A.

Peak electrical ceiling: 240 W; not an operating setpoint.

Bus droop during the pulse: ≤5%.

Light-branch average power: ≤20 W.

Complete capture-module average power, excluding compute: ≤60 W.

Selection rule:

Search upward from the lowest practical current.

Stop at the first stable profile that passes every image, timing, ambient, power, and thermal gate.

Do not select a brighter setting for aesthetic preference.

Do not cross the electrical ceiling.

Do not compensate for inadequate light by increasing exposure.

7.5 Diffuser

Resolved baseline

One opal diffuser per quadrant.

Diffuser is removable, replaceable, mechanically keyed, and recorded by part/lot.

No shared sheet spanning the central camera window.

Diffuser placement shall prevent a directly imaged LED die pattern.

Exact diffuser-to-LED spacing is adjustable during the bounded bench search and then mechanically frozen.

The installed diffuser must tolerate the selected pulse current and two-hour thermal test without visible deformation, discoloration, or image drift.

Bench variables

Material.

Thickness.

Haze.

Transmission.

Surface finish.

LED-to-diffuser stand-off.

Quadrant-to-ground aim.

No transmission or haze value is frozen before a cited component candidate and physical image result exist.

7.6 Central optical bay and window

Resolved baseline

Camera and lens occupy a central light-isolated optical bay.

Peripheral emitter bays are separated from the optical bay by matte-black baffle lips.

The camera looks through replaceable AR-coated optical glass:

thickness 2–3 mm;

tilt 3–5°;

gasketed;

cleanable;

installed during all calibration and acceptance.

Tilt direction is chosen so the dominant source reflection exits the active image; the exact axis is an installed geometry decision.

The window frame, gasket, and baffle may not intrude into the lens cone.

Window identity, orientation, tilt, and installation torque or retention state are frozen in the profile.

No flat, untilted, uncoated transparent plate is accepted merely because the image remains visible.

Any replacement, reorientation, or coating change invalidates Stage C through E.

A candidate fails if it creates a direct strobe ghost, localized flare, MTF failure, reprojection failure, clipping failure, or nonuniformity in any region.

7.7 Hood shell

Resolved baseline

Minimum internal plan for one bay: 600×600 mm.

Rigid top and sidewalls.

No direct ground-to-sky line of sight.

Interior finish: matte black and low reflectance.

External material, coating, and thickness remain fabrication variables.

Seams use overlapping joints, gaskets, or internal light traps.

Service opening uses a hood-open interlock.

No opening may create an unbaffled source-to-ground or sky-to-ground path.

Sharp internal corners, exposed wires, and dangling loops are prohibited.

The hood is an optical-control proof enclosure, not an ingress-certified product enclosure.

7.8 Skirts and terrain interface

Resolved baseline

Two independent layers.

Matte-black flexible EPDM or coated fabric.

Layer length: 100–150 mm.

Staggered overlap: 30–50 mm.

Operating ground clearance: 0–20 mm.

Outer and inner cuts are offset so no slit creates a direct sky path.

The inner layer forms the second light labyrinth when the outer layer is deflected.

Segments attach to a replaceable breakaway rail or equivalent fail-soft mount.

No closed loops, cords, or geometry likely to wind around vegetation or rotating equipment.

Skirt topology must remain removable and adjustable during proof.

The evidence does not provide a numeric acceptable breakaway force or snag fixture. Therefore:

The survey shall mark mechanical breakaway force as unresolved.

Before plant-contact use, the mechanical-safety owner must freeze a force, fixture, and snag protocol.

Until that separate criterion exists and passes, the skirt may be accepted only for stationary or controlled non-contact optical proof.

A successful light-leak test is not an entanglement-safety PASS.

7.9 Baffles and cable labyrinth

Resolved baseline

Two-stage labyrinth.

Minimum baffle depth: 50 mm.

Cable entry faces rearward.

Cable entry uses a gasketed S-path.

Internal surfaces are matte black.

Central optical-bay baffles prevent direct LED-to-window paths.

Baffles may not block the calibrated FOV or future safe-swath overlap.

For a future multi-bay extension, inter-bay baffles may not obstruct the existing overlap strip.

7.10 Functional sealing

Functional sealing means:

no direct sky path;

no visible unbaffled light leak;

gasketed optical window;

baffled cable path;

closed service panels during capture;

measured ambient rejection within the tested envelope.

It does not mean:

IP65 or IP67;

rain exposure;

pressure wash;

dust chamber performance;

chemical resistance;

stone impact resistance;

production ingress protection.

The decisive functional-sealing metric remains the existing dark-corrected strobe_off / strobe_on luma ratio in every region.

7.11 Cooling

Resolved engineering baseline

LED boards mount to a thermally conductive plate.

LED heat is conducted to a heatsink located outside the optical volume.

Baseline cooling is passive.

No ambient through-flow vent is opened into the optical volume.

Camera housing and LED plate have dedicated temperature measurement points.

The camera is not used as the LED heat sink.

Driver and power electronics are placed so their waste heat does not directly warm the camera or optical path.

Overtemperature disables strobe enable and invalidates capture.

Bounded thermal challenger

If passive cooling fails the exact two-hour test, one of the following may be tested as a single bounded remediation:

a larger external heatsink; or

an external fan blowing only across the external heatsink.

The fan may not exchange unfiltered ambient air through the optical volume. Fan failure must remain covered by overtemperature protection.

If one bounded thermal remediation still fails, the architecture becomes REPLAN_REQUIRED; the current or exposure is not forced beyond its contract.

7.12 Polarization

Default state: OFF.

Challenger: source polarizer sheets on all four diffuser outputs plus a lens analyzer crossed at 90°.

Paired wet-leaf and wet-soil challenge is mandatory.

Promotion requires:

saturated-glare area reduction ≥50%;

exposure remains 170 µs;

all nine-region luma, uniformity, clipping, SNR, ambient, timing, power, and thermal gates pass;

no new spatial artifact or color instability is introduced.

A polarization A/B shall include:

Same-current OFF versus ON capture to isolate optical attenuation and glare behavior.

If ON loses luma or SNR, a second ON run at its lowest passing current within the electrical envelope.

Promotion based on the complete selected ON profile, not on a glare-only image.

If the gate fails, polarization remains OFF; no continuing tuning loop is authorized.

7.13 Height and structure cues

The baseline does not claim metric height reconstruction.

The survey shall define a diagnostic fixture containing:

matte vegetation-like surfaces;

real crop/weed samples where available;

relief at 0, 55, and 110 mm;

representative overlap, curl, and leaf-angle conditions;

placement in all nine image regions.

The diagnostic records:

shadow consistency;

local edge and texture visibility;

saturation;

clipping;

temporal stability;

qualitative failure modes.

No new hard height/structure metric shall be invented in this part.

An opposed-pair or sequential directional-light challenger may open only when:

The sensor/model lane supplies a frozen height or structure task metric.

Its evaluation set and acceptance threshold are fixed before challenger images are inspected.

The all-on baseline passes Stage D but misses that task metric.

The challenger fits the unchanged exposure, frame-rate, tracking, and compute interfaces.

Any temporal light-state metadata needed by the downstream model is explicitly accepted.

Without all five conditions, all-on simultaneous lighting remains the baseline.

8. Existing hard acceptance gates

The survey must reproduce these values exactly and must identify the acceptance YAML as the authority.

8.1 Timing and electrical
Gate	Requirement
Exposure	170 µs
Pulse	150–170 µs
Pulse-width error	≤0.05
Trigger-to-light jitter p95	≤5 µs
Peak current	0–10 A
Bus droop	≤0.05
CCT	4500–5500 K
CRI	≥90
Light-branch average power	≤20 W
Capture-module average power excluding compute	≤60 W
8.2 Image-space light gates

For all nine regions under one fixed camera and light profile:

Gate	Requirement
Dark-corrected ambient off/on luma ratio	≤0.10 in every region
Nine-region luma min/max ratio	≥0.75
Frame mean luma, 8-bit equivalent	40–205
Fully clipped white fraction	≤0.002
Fully clipped black fraction	≤0.001
Temporal SNR on 18% gray	≥20 dB
8.3 Thermal
Gate	Requirement
Duration	≥120 min
Exterior ambient coverage	5–40 °C
Camera housing	≤50 °C
LED plate	≤60 °C
Frame drops	0
Thermal-throttle events	0
8.4 Wet glare
Gate	Requirement
Paired wet-glare test	Required
Polarization baseline	Disabled
Minimum glare reduction for promotion	≥0.50
All other gates	Must still pass

These thresholds are already part of the Stage-D contract and shall not be restated with rounded or weakened values. 

tarım-projesi-part-spot-spray-l…

9. Calculations to reproduce in the survey

Calculations are prescreens, not physical acceptance.

9.1 Peak pulse energy

E_pulse = V × I × t

At 24 V, 10 A, 150 µs: 0.036 J

At 24 V, 10 A, 170 µs: 0.0408 J

These are electrical ceiling calculations, not selected optical energy.

9.2 Duty cycle

duty = pulse_width × rate

150 µs × 20 Hz = 0.003 = 0.30%

170 µs × 20 Hz = 0.0034 = 0.34%

9.3 Idealized peak-envelope average

P_avg = V × I × duty

At the 150 µs, 20 Hz, 24 V, 10 A ceiling: 0.72 W

At the 170 µs, 20 Hz ceiling: 0.816 W

This does not replace measured light-branch average power because drivers, control electronics, losses, auxiliary loads, and nonideal waveforms remain.

9.4 Conservative local storage prescreen

C ≥ I × t / ΔV

With I = 10 A, t = 150 µs, and ΔV = 5% × 24 V = 1.2 V:

C ≥ 0.00125 F = 1250 µF

This assumes the upstream supply provides zero pulse current. Final capacitance, ESR, wiring inductance, protection, and driver stability require circuit-specific analysis and bench droop measurement.

9.5 Multi-bay hood scaling

Minimum continuous internal width:

600 mm + (camera_count - 1) × center_pitch_mm

center_pitch_mm ≤430

This preserves the existing geometric scale rule but does not authorize a second camera, shared compute, or multi-bay capture.

9.6 Prohibited calculations

Do not calculate or freeze these before measurement:

required lux from a generic camera equation;

optical joules from electrical pulse energy without measured efficiency and geometry;

plant-level irradiance from a catalog lumen value;

exact LED current from renderer energy;

cooling sufficiency from TDP alone;

field sunlight tolerance from a single indoor lux value;

glare reduction from polarizer extinction ratio alone.

10. Deterministic candidate-selection rule

A candidate is eligible only if every applicable hard gate passes in one installed profile.

Among eligible candidates, select in this order:

Lowest measured light-branch average power.

Lowest selected peak current.

Lowest maximum LED-plate temperature.

Equal-current symmetric profile over a trimmed profile.

Fewer optical layers and lower component count.

Lower budgetary cost and simpler replacement path.

A candidate with a better relative metric but any absolute-gate failure is rejected.

When two values differ by less than the measurement system’s declared resolution or repeatability, treat them as tied and use the next criterion.

No weighted score may compensate for:

a failed region;

a failed thermal endpoint;

a timing violation;

a window ghost;

a missing artifact;

an unmeasured CCT/CRI value;

an invalid fixed-camera-control state.

11. Credible alternatives and dispositions
Alternative	Disposition	Material reason	Reopen trigger
Four diffuse white quadrants, all-on	Selected baseline	Preserves current RGB contract, fixed temporal appearance, independent tuning, and full-volume coverage	Re-plan only after physical failure or frozen downstream cue metric
Ambient-only capture	Rejected	Cannot satisfy bounded short-exposure ambient invariance by assumption	None inside this part
Open hood with active light	Rejected	Uncontrolled exterior light remains a dominant variable	None inside this part
Continuous high-output light	Rejected as baseline	Higher average thermal load with no benefit to the frozen global-shutter pulse contract	Only if strobe timing is proven impossible and parent plan reopens capture timing
Single bare directional source	Rejected	Creates avoidable hard-shadow and uniformity risk	Four-quadrant packaging proven impossible
Near-coaxial ring as default	Rejected	Higher direct-return and flattened-texture risk; less control over quadrant balance	Four-quadrant geometry fails after one bounded remediation
Dynamic per-frame brightness	Rejected	Breaks repeatability and capture-profile identity	Separate closed-loop exposure plan
Always-on cross-polarization	Rejected	Light loss and thermal/current cost are not justified without measured wet-glare benefit	Existing ≥50% paired gate
Opposed-pair alternating light	Challenger only	May expose structure but changes temporal appearance and downstream data contract	Frozen height/structure task metric and baseline miss
Alternate visible white SPD	Challenger only	CRI/CCT do not prove task separability, but an SPD change needs a task-backed reason	Baseline passes D yet misses predeclared crop/weed task metric attributed to SPD
NIR, multispectral, thermal, depth	Out of scope	Sensor-lane modality decision	Sensor lane formally reopens modality
Open through-flow fan	Rejected	Breaks bounded light sealing and introduces uncontrolled ingress	Separate environmental contract
Passive external heatsink	Selected cooling baseline	Simplest sealed optical-volume topology	Fails two-hour thermal gate
External fan on external sink	Thermal challenger	Preserves optical-volume sealing	Passive thermal failure
No protective window	Rejected	Conflicts with installed-window calibration and cleanable proof architecture	Sensor lane changes optical interface
Certified IP enclosure	Not claimed	No certification evidence or production environmental contract	Separate product environmental plan
12. Smallest bounded physical discovery

The decisive discovery is one adjustable single-bay mockup using the frozen camera and window interface. It shall not compare cameras or modalities.

12.1 Maximum bounded shortlist

The survey may carry forward at most:

two credible high-CRI visible-white LED families;

two credible opal diffuser options;

two credible AR optical-window options if the inherited window class lacks a source-backed candidate;

one passive heatsink topology;

one external-fan thermal challenger;

one crossed-polarization challenger.

A broader catalog sweep requires a specific failure mode that none of these candidates can address.

12.2 Required fixture capabilities

The physical protocol shall require:

Frozen camera, lens, ROI, WD, focus, aperture, exposure, gain, and manual WB.

Adjustable but measurable quadrant position, aim, and diffuser stand-off.

Installed tilted optical window.

Nine-region diffuse target.

18% gray target.

Matte black and diffuse white clipping targets.

Real or representative dry and wet leaves and soil.

Relief fixture at 0, 55, and 110 mm.

Exterior light source or measured natural-light challenge movable around the enclosure.

Lux measurement outside the hood.

Pulse-capable CCT/CRI measurement or a validated equivalent method.

Oscilloscope timing evidence.

Current and bus-voltage measurement.

Light-branch and module average-power measurement.

Camera-housing and LED-plate temperature logging.

Raw or lossless frame capture.

Hardware identity photographs and dimensional record.

If pulse-capable spectral measurement is unavailable, vendor CCT/CRI data alone shall not create a physical Stage-D PASS. The survey must state the missing measurement and keep the result NOT_MEASURED.

12.3 Pre-registration before looking at results

Before candidate results are inspected, freeze:

region masks;

dark-correction method;

luma conversion;

clipping thresholds;

temporal-SNR computation;

glare ROI and saturation definition;

minimum frame count per static state;

warm-up time;

measurement resolution and uncertainty;

candidate order;

current-search method;

external-light positions;

thermal endpoint method;

pass/fail implementation.

The exact static-frame count is not frozen by V2. Codex may select a defensible count, but it must be fixed before candidate comparison and remain unchanged across arms.

13. Ordered bench sequence
13.1 Prerequisites

Stage-D testing shall not begin until:

Exact hardware identities are recorded.

Stage-B strobe timing, pulse width, droop, and trigger behavior are available or measured in the same setup.

Stage-C installed-window optical state passes or is explicitly marked as a prerequisite not yet met.

Camera controls are fixed.

All measurement instruments and processing definitions are recorded.

A visually good image cannot override a failed Stage B or C.

13.2 D0 — Mechanical and optical-path inspection

Purpose: eliminate packaging failures before photometric tuning.

Check:

No LED, diffuser, frame, baffle, gasket, or cable occludes the FOV.

No direct LED-to-window line exists.

Window is within 2–3 mm and 3–5°.

Hood internal plan is at least 600×600 mm.

Skirt, overlap, clearance, and labyrinth dimensions are recorded.

Hood-open and overtemperature signals are observable.

LED boards, diffusers, window, and temperature sensors are identifiable.

Acceptance evidence:

Dimensioned drawing.

Installed photographs.

Component identities.

Window orientation.

FOV witness image.

Fault-input witness.

Failure action:

Correct one mechanical conflict and repeat D0.

A second failure of the same root cause requires re-plan.

13.3 D1 — Single-channel diagnostic

Purpose: verify channel identity, aim, partial-channel observability, and absence of direct window return.

For each quadrant separately:

Fire at a low safe diagnostic current.

Record nine-region response.

Record window ghost or flare.

Confirm channel identity.

Disconnect or inhibit the quadrant and confirm the fault or startup witness detects it.

This run does not select the production profile.

Acceptance evidence:

Per-quadrant frame set.

Channel map.

Driver status or startup-flat-field detection record.

No FOV occlusion.

No unobservable partial-channel failure.

13.4 D2 — Equal-current all-on search

Purpose: find the simplest passing photometric profile.

Procedure:

Fire all four simultaneously.

Begin at the lowest practical equal current.

Increase current within the electrical envelope.

At each setting, record all hard image, spectral, power, timing, and preliminary thermal values.

Stop at the first stable setting that passes every non-soak gate.

Acceptance:

One equal-current setting passes all nine-region image gates.

CCT and CRI pass.

Pulse and droop pass.

Power limits pass.

No direct-return artifact appears.

Result:

If successful, this becomes the provisional baseline setting.

If no equal-current setting passes due only to spatial nonuniformity, proceed to D3.

If failure is SNR, clipping, spectral, timing, or electrical at all settings, classify the root cause before changing geometry.

13.5 D3 — Fixed quadrant trim

Trigger: equal-current all-on cannot achieve the uniformity gate, while the failure is attributable to repeatable spatial imbalance rather than window contamination, ambient leak, or camera optics.

Procedure:

Preserve geometry, diffuser, camera settings, and total envelope.

Change only the fixed per-quadrant current vector.

Derive one vector from the preregistered nine-region method.

Repeat all D2 gates.

Promotion:

Trimmed profile passes every hard gate.

Current vector is fixed and metadata-bound.

It is preferred only if no equal-current profile passes.

Failure:

Do not continue arbitrary channel tuning.

Open one geometry/diffuser remediation.

13.6 D4 — One geometry or diffuser remediation

Trigger: no current profile passes because of a verified hotspot, edge deficit, LED-die image, or source-window reflection.

Change only one category:

quadrant aim/stand-off; or

diffuser part/stand-off; or

internal source baffle.

Repeat D0–D3 as applicable.

Stopping rule:

One bounded remediation is allowed for the diagnosed failure class.

If the revised architecture still cannot pass, mark LIGHT_HOOD_ARCHITECTURE_REPLAN_REQUIRED.

Do not extend exposure, weaken uniformity, or hide a failed region.

13.7 D5 — Ambient and skirt challenge

Purpose: verify functional light sealing in the bounded proof envelope.

Procedure:

Use the selected all-on profile and fixed camera controls.

Record exterior lux.

Test skirt clearances at 0, 10, and 20 mm.

Move the external source around the perimeter, including front, rear, left, right, and overhead where mechanically relevant.

Include one controlled local skirt deflection within the intended proof geometry.

Retain the position that produces the worst corrected off/on ratio.

Report the exact external-light geometry and lux; do not generalize beyond it.

Acceptance:

Every region has dark-corrected off/on ratio ≤0.10.

All other image gates still pass.

No direct sky/light path is visible.

Hood-open invalidates capture.

Failure action:

One skirt-overlap or labyrinth remediation within the frozen ranges.

Repeat the complete ambient matrix.

A second failure requires enclosure re-plan.

13.8 D6 — Wet-glare and polarization A/B

Purpose: decide whether polarization earns its optical and thermal cost.

Procedure:

Use fixed wet-leaf and wet-soil ROIs.

Use the same pose, moisture application, camera controls, window, and ambient condition.

Define saturated-glare area using the preregistered raw or lossless saturation threshold.

Record OFF at the selected baseline setting.

Record ON at the same current.

If ON underexposes, find the lowest passing ON current without changing exposure.

Repeat all image, power, timing, and preliminary thermal gates.

Promotion:

Glare reduction ≥50%.

Every hard gate passes.

No unacceptable color, spatial, or temporal artifact appears.

Otherwise:

Freeze polarization OFF.

Do not test additional analyzer angles or polarizer families without a new material failure reason.

13.9 D7 — Two-hour thermal endpoint evidence

Purpose: freeze the operating cooling state.

Run the final selected optical profile at the required exterior ambient endpoints or a documented chamber/ramp method demonstrating 5–40 °C coverage.

Acceptance:

Duration ≥120 min.

Camera housing ≤50 °C.

LED plate ≤60 °C.

Zero frame drops.

Zero thermal-throttle events.

Image gates remain passing at the end of the run.

No diffuser, polarizer, window, adhesive, gasket, or mechanical alignment drift is observed.

Failure action:

Verify measurement and mounting root cause.

Apply one thermal remediation:

larger passive sink; or

external fan on the external sink.

Repeat the full two-hour endpoint evidence.

A second failure sets REPLAN_REQUIRED.

13.10 D8 — Structure-cue diagnostic

Purpose: document whether the all-on profile visibly preserves relief and local structure without creating a new product claim.

Record the 0/55/110 mm fixture and representative plant structures across all nine regions.

This run:

does not modify Stage-D thresholds;

does not authorize directional lighting;

does not claim height accuracy;

produces a failure catalogue for the sensor/model lane.

A directional challenger opens only under the five conditions in Section 7.13.

13.11 D9 — Fault and recovery witness

Inject or simulate:

one missing quadrant;

driver fault;

strobe absent;

extra or malformed pulse where safely testable;

hood open;

overtemperature input;

profile-ID mismatch;

interrupted fan if the fan challenger is selected.

Acceptance:

Strobe is inhibited or the affected frame/profile is invalidated.

No fault silently produces an intervention-valid frame.

Recovery requires a new valid profile state and startup witness.

No stale pre-fault profile remains active.

14. Physical evidence artifacts

Each measured run shall bind at least:

Run ID and UTC timestamp.

Rig and hardware revision.

Camera, lens, window, LED, diffuser, driver, polarizer, hood, skirt, baffle, heatsink, and fan identities.

Dimensioned geometry.

Fixed camera controls.

Current vector and pulse profile.

Exterior lux and light-source geometry.

CCT/CRI evidence.

Raw or lossless frames.

Region-level metric table.

Oscilloscope trace.

Current, voltage, droop, and power log.

Temperature log.

Photographs.

Analysis version or script identity.

Artifact path and SHA-256.

Explicit measurement status.

Missing, null, unreferenced, or hash-mismatched artifacts remain NOT_MEASURED or FAIL; they cannot be described as provisionally passing.

15. Challenger triggers and decision rules
Challenger	Opens only when	Changed variable	Promotion rule	Rollback
Fixed quadrant-current trim	Equal-current profile misses only uniformity	Current vector	All hard gates pass	Equal-current diagnostic state
Alternate diffuser	Verified hotspot, edge deficit, or LED-die image after current search	Diffuser and its frozen stand-off	All hard gates pass; deterministic selection rule wins	Previous diffuser
Quadrant aim/stand-off	Verified geometric nonuniformity or reflection	Aim/stand-off only	All hard gates pass	Previous geometry
Larger passive sink	Passive thermal failure	External sink	Full thermal and image gates pass	Previous sink; profile remains not ready
External heatsink fan	Passive sink remains inadequate	External fan only	Full thermal and image gates pass; fan failure is fail-closed	Passive profile if it passed; otherwise re-plan
Cross-polarization	Mandatory wet challenge	Polarization state and its selected current	≥50% glare reduction plus all hard gates	Polarization OFF
Alternate visible-white SPD	Baseline passes D but misses a predeclared task metric attributed to SPD	One visible-white LED family	Absolute D PASS plus frozen downstream metric improvement	Existing white profile
Opposed-pair directional mode	Frozen structure/height metric exists and all-on misses it	Firing pattern	Absolute gates, unchanged interface, and downstream metric pass	All-on profile
Revised window tilt within 3–5°	Direct-return artifact	Tilt only	Stage C and D pass	Previous tilt
Alternate AR window	Tilt cannot remove ghost or C fails due window	Window part	C–E rerun passes	Previous passing window
Revised skirt overlap/labyrinth	Ambient ratio fails within 0–20 mm envelope	One skirt/light-trap geometry	Full ambient matrix passes	Previous controlled non-ready state

No challenger may be promoted on a relative improvement alone.

16. Change and revalidation contract
Change	Minimum invalidated evidence
LED manufacturer, part, CCT bin, SPD, or board	Stage D and dependent E
Diffuser material, thickness, surface, stand-off, or lot with materially different optical data	Stage D and dependent E
Quadrant position, aim, or camera-light relative geometry	Stage C through E
Current vector or pulse profile	Stage B through E
Driver, isolation, timing path, supply, local storage, or wiring topology	Stage B through E
Polarizer sheet, analyzer, orientation, or removal	Stage D and E
Hood internal finish, wall geometry, light trap, skirt, clearance, or baffle	Stage D and E
Protective window part, thickness, tilt, coating, gasket, or installation	Stage C through E
Camera, lens, mount, WD, focus, or aperture	Hand back to sensor lane; Stage A–E as existing contract requires
Heatsink, fan, thermal interface, or electronics placement	Thermal portion of B/D and dependent E
Camera gain, WB, exposure, pixel format, or rate	Stage B through E
Second bay or changed bay pitch	Full applicable A–E per bay plus overlap and multi-bay evidence
Exterior cosmetic change with no optical, thermal, structural, or sealing effect	Document impact review; no automatic retest
Documentation-only clarification with no contract or hardware change	Citation and consistency audit only

When uncertain whether a change affects the optical path, timing, ambient sealing, or thermal state, invalidate the broader stage set.

17. Ordered implementation ledger
Package 1 — Scope and source lock

 - [ ] Create docs/research/SPOT_SPRAY_LIGHT_ENCLOSURE_SURVEY_V1.md as the only implementation output owned by this part.

 - [ ] Record repository base main@509aeef8189dfa50dbcba973e871b0d41febe239.

 - [ ] Record the existing frozen V2 source paths and hashes from spot_spray_rig_acceptance_v1.yaml.

 - [ ] State that the acceptance YAML, not the survey, owns quantitative PASS thresholds.

 - [ ] State that no camera, modality, ROI, FOV, WD, focus, aperture, exposure, rate, or compute decision is reopened.

 - [ ] State that no purchase, field-readiness, certified-ingress, production, deposition, crop-injury, or chemical-GO claim is made.

 - [ ] State the current status as pre-real and physically unmeasured.

 - [ ] Acceptance evidence: the survey has an explicit authority section, source pins, ownership boundary, and claim boundary with no conflicting wording.

Package 2 — Source-tiered evidence ledger

 - [ ] Add the required source-tier scheme.

 - [ ] Add direct dated citations for the existing Basler trigger and camera interface facts.

 - [ ] Add at least one primary manufacturer source for each shortlisted LED family.

 - [ ] Add a primary source for the candidate strobe driver or driver class.

 - [ ] Add primary optical data for each diffuser candidate.

 - [ ] Add primary optical data for each window candidate.

 - [ ] Add primary data for any polarizer candidate.

 - [ ] Add primary thermal/material data for heatsink interfaces and skirt material where available.

 - [ ] Add only peer-reviewed sources that materially support controlled lighting, enclosure, diffusion, or glare decisions.

 - [ ] Label publication/revision date and checked_on date for every source.

 - [ ] Mark absent revision dates explicitly.

 - [ ] Separate public price from technical performance and label it non-landed.

 - [ ] Reject search snippets, unsourced reseller claims, and marketing outcome metrics as design proof.

 - [ ] Acceptance evidence: every material sourced fact maps to a direct citation and every unsupported choice is labeled as hypothesis or bench variable.

Package 3 — Fixed interface contract

 - [ ] Reproduce the frozen sensor and capture inputs without changing them.

 - [ ] Define the trigger-to-strobe control chain.

 - [ ] Define all-on simultaneous firing as the baseline.

 - [ ] Define fixed manual camera controls as a prerequisite to final D measurement.

 - [ ] Define required profile IDs and frame metadata.

 - [ ] Define strobe default-off and invalid-frame/no-fire behavior.

 - [ ] Define partial-quadrant fault observability.

 - [ ] Define no-valve-control ownership.

 - [ ] Acceptance evidence: an interface table covers mechanical, optical, electrical, timing, thermal, metadata, and failure behavior without assigning sensor decisions to this lane.

Package 4 — Buildable baseline architecture

 - [ ] Specify four cardinal emitter quadrants around a central isolated optical bay.

 - [ ] Specify one independently current-limited channel per quadrant.

 - [ ] Specify one removable opal diffuser per quadrant.

 - [ ] Specify equal-current search before fixed current trim.

 - [ ] Prohibit dynamic per-frame current control.

 - [ ] Specify the 4500–5500 K, CRI ≥90, visible-white baseline.

 - [ ] Specify 150–170 µs pulse containment within the 170 µs exposure.

 - [ ] Specify the full electrical, power, droop, and thermal envelope.

 - [ ] Specify the 600×600 mm rigid matte-black hood.

 - [ ] Specify the two-layer 100–150 mm skirt, 30–50 mm stagger, and 0–20 mm clearance.

 - [ ] Specify the two-stage ≥50 mm labyrinth and rear-facing gasketed S-path.

 - [ ] Specify the 2–3 mm, 3–5° replaceable AR window.

 - [ ] Specify passive external heat rejection and no optical-volume through-flow.

 - [ ] Specify cross-polarization as disabled-by-default.

 - [ ] Mark exact LED, diffuser, aim, current, lux, optical energy, thermal interface, and fabrication material as bench variables.

 - [ ] Acceptance evidence: the architecture can be fabricated as one adjustable bay without requiring a sensor change or an unspecified active subsystem.

Package 5 — Transparent calculations

 - [ ] Reproduce pulse-energy calculations with units.

 - [ ] Reproduce duty-cycle calculations.

 - [ ] Reproduce idealized average pulse-power calculations.

 - [ ] Reproduce the 1250 µF conservative local-storage prescreen and its assumptions.

 - [ ] Reproduce the continuous-hood width formula for future bays.

 - [ ] Explain why none of these calculations freezes lux, optical joules, LED current, capacitance, or cooling.

 - [ ] Identify each source input and each engineering assumption.

 - [ ] Acceptance evidence: every numeric calculation is independently reproducible and no calculated prescreen is worded as physical PASS.

Package 6 — Bench fixture and preregistration

 - [ ] Define the maximum bounded shortlist.

 - [ ] Define required measurement instruments and fixtures.

 - [ ] Define the nine-region target and 18% gray method.

 - [ ] Define wet-leaf and wet-soil glare ROIs.

 - [ ] Define the 0/55/110 mm structure diagnostic.

 - [ ] Define dark correction, luma, clipping, SNR, and glare calculations before results.

 - [ ] Define the minimum frame count before results.

 - [ ] Define measurement uncertainty and tie handling.

 - [ ] Define external-light positions and worst-case selection.

 - [ ] Define thermal endpoint coverage.

 - [ ] Define required raw artifacts and hashes.

 - [ ] Acceptance evidence: a technician can execute the protocol without choosing an analysis method after seeing which candidate performs best.

Package 7 — Ordered physical test plan

 - [ ] Document D0 mechanical and optical-path inspection.

 - [ ] Document D1 single-channel diagnostic and partial-failure witness.

 - [ ] Document D2 equal-current all-on search.

 - [ ] Document D3 fixed quadrant trim.

 - [ ] Document the single allowed geometry/diffuser remediation.

 - [ ] Document the 0/10/20 mm skirt-clearance ambient matrix.

 - [ ] Document the same-current and compensated-current polarization A/B.

 - [ ] Document the two-hour 5–40 °C thermal evidence.

 - [ ] Document the structure-cue diagnostic without a height claim.

 - [ ] Document fault injection and recovery.

 - [ ] Give each step explicit prerequisites, changed variables, artifacts, PASS, FAIL, and stop behavior.

 - [ ] Acceptance evidence: no step permits a candidate to pass on relative improvement while an absolute gate fails.

Package 8 — Challenger register

 - [ ] Add the trigger, single changed variable, promotion rule, and rollback for each permitted challenger.

 - [ ] Keep polarization OFF unless its exact gate passes.

 - [ ] Keep all-on lighting unless a frozen downstream structure metric opens a directional challenger.

 - [ ] Keep the visible-white baseline unless a frozen task metric attributes failure to SPD.

 - [ ] Keep passive cooling unless the physical thermal gate fails.

 - [ ] Keep the inherited window class unless direct-return or Stage-C evidence fails.

 - [ ] Keep camera and modality challengers out of this document.

 - [ ] Limit each failure class to one bounded remediation before re-plan.

 - [ ] Acceptance evidence: every challenger ends as PROMOTED, REJECTED, NOT_TRIGGERED, or REPLAN_REQUIRED; no indefinite “continue research” state remains.

Package 9 — Failure and revalidation behavior

 - [ ] Add the change-to-stage invalidation table.

 - [ ] Define missing pulse, extra pulse, quadrant loss, driver fault, hood-open, overtemperature, and profile mismatch behavior.

 - [ ] Define window contamination as a Stage-C/Stage-D gate issue rather than an unsupported cleanliness score.

 - [ ] Define exterior ambient beyond the measured envelope as unproven rather than automatically accepted.

 - [ ] Define fan failure behavior if the fan challenger is selected.

 - [ ] Define rollback to the last fully passing hardware/profile identity.

 - [ ] Define that stale evidence cannot be rebound to a changed component.

 - [ ] Acceptance evidence: every material fault either invalidates the frame, disables strobe, triggers retest, or triggers re-plan.

Package 10 — Survey conclusion and handoff

 - [ ] State the selected proof hypothesis in one concise decision table.

 - [ ] List frozen, provisional, challenger-only, and out-of-scope values separately.

 - [ ] State the deterministic candidate tie-break.

 - [ ] State the exact Stage-D hard gates.

 - [ ] State that Stage-C installed-window PASS is a prerequisite.

 - [ ] State that physical A–E, not the survey, is required for controlled capture.

 - [ ] State that physical A–F does not authorize chemical fire under the current contract.

 - [ ] State the smallest next physical action: one adjustable single-bay installed-rig bench.

 - [ ] Acceptance evidence: a future integrator can identify exactly what to build, what remains unset, what to measure, what result selects each option, and what claims remain prohibited.

18. Exact validation
18.1 File-scope validation

The implementation change for this part shall be limited to:

docs/research/SPOT_SPRAY_LIGHT_ENCLOSURE_SURVEY_V1.md

The existing configs, acceptance evaluator, runbook, camera decision, tests, dependencies, and implementation code are read-only for this part.

Run:

git diff --check -- docs/research/SPOT_SPRAY_LIGHT_ENCLOSURE_SURVEY_V1.md

git diff --name-only -- <implementation-base>...HEAD

Acceptance:

No whitespace errors.

No unintended files.

No threshold or source-hash edits outside the survey.

18.2 Required-value audit

Confirm the survey contains exactly:

4500–5500 K

CRI ≥90

170 µs exposure

150–170 µs pulse

≤5 µs jitter p95

≤5% pulse-width error

24 V

0–10 A

240 W peak ceiling

≤5% bus droop

≤20 W light branch

≤60 W capture module excluding compute

120 min

5–40 °C

camera housing ≤50 °C

LED plate ≤60 °C

ambient off/on ≤0.10

luma min/max ≥0.75

luma 40–205

white clipping ≤0.002

black clipping ≤0.001

temporal SNR ≥20 dB

glare reduction ≥50%

hood ≥600×600 mm

skirt 100–150 mm

overlap 30–50 mm

clearance 0–20 mm

two-stage labyrinth ≥50 mm

window 2–3 mm, tilt 3–5°

Any discrepancy is a blocker, not a documentation preference.

18.3 Source audit

For every material source:

Open the direct URL.

Confirm publisher/manufacturer identity.

Confirm component/model match.

Record revision/publication date or absence.

Record current checked_on date.

Verify the cited claim appears in the source.

Confirm installed performance is not inferred from catalog data.

Acceptance:

No unsupported factual assertion.

No citation to a search result.

No stale price described as a quote.

No peer-reviewed result described as this rig’s performance.

18.4 Fact/calculation/hypothesis audit

Search the survey manually and confirm:

Every installed-performance statement is either a physical result or future gate.

Every calculation exposes inputs and assumptions.

Every unmeasured value is labeled BENCH VARIABLE.

Every design choice lacking direct evidence is labeled ENGINEERING HYPOTHESIS.

No hypothesis is written as a frozen fact.

No renderer value is described as lux, watts, joules, CRI, or CCT.

18.5 Contract-consistency audit

Compare the survey against:

configs/deploy/spot_spray_capture_optimization_v2.yaml

configs/deploy/spot_spray_rig_acceptance_v1.yaml

docs/SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md

Acceptance:

The survey adds explanation and bench planning only.

Existing stage thresholds and ownership remain unchanged.

Physical A–E is still required for controlled RGB collection.

Physical A–F is still required for dry-marker readiness.

Chemical fire remains false because quantitative deposition and crop-injury thresholds are absent. 

tarım-projesi-part-spot-spray-l…

18.6 Claim audit

Reject the survey if it says or materially implies:

purchase approved;

supplier selected for ordering;

field ready;

production ready;

ruggedized;

IP65 or IP67;

rainproof;

washdown safe;

dustproof;

chemical compatible;

plant-contact safe;

height measured;

crop/weed separation proven;

controlled capture ready without physical A–E;

dry-marker ready without physical A–F;

chemical GO.

Statements explicitly saying those claims are not made are permitted.

19. Material risks and rollback
19.1 Insufficient light at 170 µs

Impact: SNR or luma cannot pass without clipping, excessive current, or heat.

Response:

Verify camera controls and measurement.

Search current within the frozen envelope.

Allow one diffuser or geometry remediation.

If no profile passes, reject the light/hood architecture.

Rollback: no controlled-capture profile; do not increase exposure.

19.2 Spatial nonuniformity

Impact: center or edge passes while another region fails.

Response:

Equal-current search.

Fixed quadrant trim.

One aim/diffuser remediation.

Rollback: last complete passing profile; no averaging across regions.

19.3 Window ghost or optical degradation

Impact: glare, clipping, MTF, or reprojection failure.

Response:

Verify direct source path and contamination.

Adjust tilt within 3–5°.

If necessary, test one alternate AR window.

Rollback: prior passing window identity; any changed window requires C–E rerun.

19.4 Ambient leak through skirts or service seams

Impact: off/on ratio fails in one or more regions.

Response:

Identify worst external-light geometry.

Apply one overlap or labyrinth remediation.

Repeat full clearance and angle matrix.

Rollback: stationary controlled optical proof only; no terrain or field claim.

19.5 Thermal failure

Impact: temperature limit, frame drop, throttle, optical drift, or component deformation.

Response:

Verify thermal interface and sensors.

Test one larger passive sink or external-fan remediation.

Repeat full endpoint soak.

Rollback: no passing light profile. Do not reduce thermal evidence duration or ignore end-of-run image drift.

19.6 Polarization reduces useful signal

Impact: glare improves but luma, SNR, color, uniformity, or thermal limits fail.

Response: reject polarization.

Rollback: frozen OFF profile.

19.7 Partial quadrant failure is not detectable

Impact: degraded lighting could silently authorize intervention.

Response: add driver telemetry or startup flat-field witness and re-run the fault test.

Rollback: profile remains invalid until the failure is observable.

19.8 Height/structure cue remains weak

Impact: all-on diffuse light may flatten cues needed by a future task.

Response: do not infer a solution. Obtain a frozen downstream metric before opening directional lighting.

Rollback: all-on profile remains the only capture baseline; no height claim.

19.9 Source or component drift

Impact: selected component no longer matches documented SPD, pulse, thermal, or optical data.

Response: create a new component identity and invalidate affected stages.

Rollback: previous physically passing part/profile if still available and unchanged.

20. Stopping rules

Research stops when:

The visible-white four-quadrant baseline is fully specified.

Every material sourced fact has a direct dated citation.

Every unmeasured value has a physical decision rule.

The fixed sensor interface is preserved.

The exact Stage-D gates are reproduced without drift.

The bounded shortlist and bench sequence are complete.

Each challenger has a trigger, promotion rule, and rollback.

The claim boundary is explicit.

Physical tuning stops when:

A baseline profile passes all applicable gates; freeze it.

A challenger fails its promotion rule; reject it.

One bounded remediation for a diagnosed failure class fails; re-plan.

Passing would require longer exposure, relaxed gates, unbounded current, an unapproved sensor change, or missing evidence; fail closed.

A structure/spectrum challenger lacks a frozen downstream metric; do not open it.

The intended ambient, terrain, or environmental envelope exceeds the tested proof envelope; create a separate plan.

Certified ingress, rain, washdown, dust, vibration, impact, chemical compatibility, or production quantity becomes a requirement; route to a separate environmental/product-safety contract.

21. Re-plan triggers

Re-plan this part when any of the following occurs:

No current/diffuser/geometry setting passes all Stage-D gates.

A direct strobe-window reflection cannot be removed within the frozen window range and one alternate window.

Functional ambient sealing fails after one skirt/labyrinth remediation.

Passive cooling and one external thermal remediation both fail.

The sensor lane changes camera, lens, IR-cut, ROI, FOV, WD, aperture, exposure, rate, or modality.

Required operating speed or exposure changes.

The required canopy-relief range exceeds 0–110 mm.

The required proof ambient exceeds the documented lux/angle envelope.

Terrain requires skirt clearance greater than 20 mm.

Plant-contact operation is requested without a mechanical breakaway criterion.

A second camera or wider swath is requested.

A validated downstream height/structure metric requires a different lighting mode.

A validated downstream crop/weed task metric attributes a material failure to the visible-white SPD.

Certified environmental or chemical requirements are introduced.

22. Completion criteria

This part is complete only when all of the following are true:

 - [ ] docs/research/SPOT_SPRAY_LIGHT_ENCLOSURE_SURVEY_V1.md exists.

 - [ ] The document identifies the primary bottleneck as installed physical evidence.

 - [ ] The sensor lane’s fixed interface is preserved.

 - [ ] The four-quadrant visible-white, all-on, diffuse-strobe baseline is explicit.

 - [ ] Hood, skirt, labyrinth, window, functional sealing, and cooling topologies are explicit.

 - [ ] Exact unset variables remain bench variables rather than invented values.

 - [ ] Existing Stage-D thresholds are copied exactly from the authority.

 - [ ] Source facts, calculations, hypotheses, bench variables, and limitations are visibly separated.

 - [ ] Every external factual claim has a direct dated citation.

 - [ ] The physical discovery is bounded to one adjustable proof bay and a small shortlist.

 - [ ] The bench sequence is executable without post-result method selection.

 - [ ] Every permitted challenger has an evidence trigger and deterministic disposition.

 - [ ] Change invalidation and rollback behavior are explicit.

 - [ ] Missing evidence remains NOT_MEASURED.

 - [ ] No purchase, certified-ingress, field-readiness, production, plant-contact, deposition, crop-injury, or chemical-GO claim is made.

 - [ ] The final conclusion authorizes only a future physical test, not a hardware or deployment GO.
