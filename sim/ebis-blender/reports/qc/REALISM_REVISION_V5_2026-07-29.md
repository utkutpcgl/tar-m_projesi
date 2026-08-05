# EBIS Blender reference-fit v5 realism revision

Date: 2026-07-29
Generator family: `v1.7.3`
Target profile: `REF-65218_IVEDIK_LED_TARGET`
Decision: **framing distribution + reference-fit pilot + BlenderMCP PASS; production realism HOLD**

## What this revision establishes

This revision replaces the earlier generic/three-grey/open-room
interpretation with a single target-machine contract inferred from
temporally separated LED RGB images and `REF*` IR frames:

- fixed grey back/left shell and cobalt-blue right/local aperture;
- a true hinged access door on the left opening, with bounded full/partial
  angle profiles;
- narrow, full-length back + left + right opal LED channels at the upper
  platen level;
- two coaxial circular steel platens, fallback `400 mm` diameter, with
  the cube edge ratio constrained to approximately two;
- visible rear and side small-camera stacks rather than anonymous black
  dots;
- regular cube/cylinder concrete rather than arbitrary rock shapes;
- printed paper as a physical non-target occluder in front of an RFID;
- per-camera bounded lens, mount, distortion, focus, exposure and
  door-fill realizations;
- visible per-instance mask → tight bbox → cautious
  standard/hard/exclude partition.

The v5 material pass also removes three artefacts that were only obvious
at 1920×1080: periodic Wave-texture rings over the whole platen, large
smooth aggregate pieces that read as objects glued to the concrete, and
copied side-wall access covers that became two dominant white rectangles.
Platen normals now come from faint non-periodic micro-wear, large rubble
and concrete fragments are bounded to smaller physical scales, moderate
samples no longer receive protruding aggregate geometry, and side camera
hardware is a compact fisheye/service stack.

This does **not** establish CAD accuracy, calibrated fisheye optics,
photorealism or a YOLO gain.

## Reference review

The reference pass sampled 85 unique frames:

- 52 LED RGB frames across cam-10/cam-11 and separated capture batches;
- 33 IR frames across all 18 `REF*` directories and dates from
  2024-12-02 through 2025-02-21.

The available inventory is 2,960 LED PNG images and 17,081 REF PNG
images. The sampled contact sheets are:

- `reports/qc/reference_forensics/led_160126_temporal_18.png`
- `reports/qc/reference_forensics/led_cam10_cam11_batches.png`
- `reports/qc/reference_forensics/ref_cam10_early_mid_late.png`
- `reports/qc/reference_forensics/ref_cam11_a_early_mid_late.png`
- `reports/qc/reference_forensics/ref_cam11_b_early_mid_late.png`

IR evidence was used only for persistent geometry, camera placement,
door/occlusion and sample-shape evidence. It was not used to infer RGB
albedo, LED power, white balance or exposure.

### Direct real-versus-v5.1 checks

Two labelled, same-camera-role comparison sheets make the residual gap
reviewable without treating either pair as a calibrated pixel match:

- [`real_vs_v5_1_cam10_cube.png`](real_vs_v5_1_cam10_cube.png): a
  temporally separated real cam-10 cube beside the selected v5.1
  `camera_angled` cube hero.
- [`real_vs_v5_1_cam11_cube.png`](real_vs_v5_1_cam11_cube.png): a real
  cam-11 cube with operator/door occlusion beside the selected v5.1
  `camera_door` cube/tag hero.

Comparison output SHA-256 values are respectively
`25c4d9e6553e6db0d61fdf91082aeb64d641de8c2a9a68aea442d463172473e0`
and
`6121ae9524f13d120ed9d56d10cbd1cf5770dc4b248c0893d7b07504d16a4fc9`.
The source real frames are pinned in the same order as
`fbf3b7199b0c4444d640a1b572b3219f965ae573bca67dbda4ce88f5130c1118`
and
`e2f9a12a2d3ee3cef70eec86088ca643700838344157785aac47c57f6a44b940`.

Repeated visual comparison supports these concrete findings:

| Layer | Stable real-image cue | Remaining v5.1 mismatch | Bounded next action |
| --- | --- | --- | --- |
| Concrete | cast-skin pores, torn/chipped corners, locally exposed aggregate and different face/end texture | too smooth, low-contrast and uniformly clean; damage lacks the real high-frequency hierarchy | measured-scale scan/photogrammetry or a tile-safe face/end damage atlas; randomize severity, not arbitrary rock geometry |
| Steel platens | darker aged steel, uneven radial wear/oxidation and spatially varying highlights | too bright and even; micro-wear does not yet form the same aged specular field | cross-polarized close-ups plus roughness/normal calibration; keep periodic rings forbidden |
| Painted panels | true fine pebbled/hammertone coat, seams and grime accumulated at fixed edges | procedural stipple is softer and too homogeneous | scale-referenced grey/blue swatches and localized edge-grime masks; preserve the fixed two-tone topology |
| LED and shadows | thin three-wall diffuser, local clipping/contact highlight and dark but nonzero chamber fill | synthetic band is broader/more even, with weaker local sensor clipping and a cleaner shadow field | measure fixed exposure, CCT and grey-card response; fit emitter/diffuser/contact spill per camera within a narrow prior |
| Camera response | strong small-camera wide-angle signature, timestamp/OSD, sharpening/noise and exposure roll-off | plausible wide angle only; no measured intrinsics, distortion, MTF, noise or response curve | ChArUco/checkerboard calibration plus static grey/color chart pairs; keep OSD out of training unless deployment frames retain it |
| Paper and RFID | wrinkled/taped forms, partial tag tips, plate-gap placement and fully hidden cases | paper and tag are too flat, clean and saturated; cylinder-conformed paper is absent | capture controlled 0/15/30/50/70/100% visibility series and scan both clean/used paper/tag variants |
| Door/operator context | door angle and hand/body occlusion change while chamber hardware remains fixed | generic door/workshop proxy and no human occluder model | measured door-angle series; add operator only as an explicit, sliceable domain variable |

The comparison does **not** justify forcing a single photograph's
lighting, pose or damage into every synthetic frame. Unmeasured residuals
belong in documented, bounded randomization ranges. Fixed machine parts,
camera identity, platen/sample contact and annotation policy must not be
randomized to hide a topology error.

### Repeated same-machine observations

| Observation | Contract decision |
| --- | --- |
| Back/service region is grey while the right/local aperture is cobalt-blue | Fix panel map by region; do not randomize whole walls between blue and grey |
| Rounded service cover, dark seam/gasket, four screws and adjacent narrow plate repeat | Keep as invariant scene geometry |
| Cam-10 and cam-11 see materially different aperture/door context | Separate `camera_angled` and `camera_door` profiles |
| Thin LED line continues across chamber sides near upper platen | Three full-length channel/diffuser/emitter segments; no giant ceiling panel |
| Door openness changes by capture | Bimodal bounded door angle, not unconstrained random rotation |
| Concrete is normally regular cube or cylinder | Shape weights `.42/.58`; bounded damage, not arbitrary rock |
| Printed forms occur on concrete and may cover RFID | Paper is opaque non-target geometry; linked tag remains one physical instance |
| Tags may be partly visible between concrete and platen | Keep plate-gap placements and visible-mask annotation |

Cross-machine REF differences were not merged into the target machine.

## Implementation delta

| Area | v5 implementation | Remaining uncertainty |
| --- | --- | --- |
| Chamber | REF-65218 two-tone panel map and enclosed shell | no CAD or measured panel dimensions |
| Door | left access-opening pivot; 82% `78–108°`, 18% `28–68°` | hinge, glass, gasket and handle measurements missing |
| Platens | two `Ø0.40 m` discs; upper/lower contact; non-periodic worn steel variation | diameter and axial stack are fallback |
| LED | full back/left/right U-channel, opal cover, hidden emitter, contact spill | lux/CCT/CRI and fixed exposure unmeasured |
| Camera hardware | dominant rear hatch plus compact side bezel/lens/port stacks | exact camera SKU and physical dimensions unconfirmed |
| Render cameras | separate cam-10/cam-11 lens/location/target/distortion/exposure ranges; unpaired stills use camera-conditioned bounded cube yaw | perspective + radial approximation, not calibrated fisheye; paired-camera mode must share one physical yaw |
| Concrete | mixed cube/cylinder, darker multiscale material, small casting voids, bounded damage/moisture | procedural and still weaker than scan data |
| Paper/RFID | cube-face paper, printed lines/tape, partial/fully hidden linkage | no conformed cylinder paper; placement prior incomplete |
| Post-processing | vignette, sharpen and bloom disabled in current config | measured sensor pipeline unavailable |
| Annotation | per-RFID visible mask, largest-component/visibility gates and physical partitions | amodal visibility is still a proxy |

## Current v5.1 evidence

### A. 32-image framing distribution gate

- Dataset: `output/realism_v5_1_distribution_gate_54120/`
- Audit: `reports/qc/realism_v5_1_distribution_gate_audit.md`
- Visual sheet:
  `reports/qc/realism_v5_1_distribution_gate_contact_sheet.png`
- Resolution/sampling: `640×360`, 20 spp, no depth.
- Seeds: `54120–54151`.
- Validator: `32/32 PASS`; 25 standard, 3 hard, 4 exclude.
- Physical RFID instances: 99.
- Camera/shape cells and maximum absolute real-bbox median delta:
  angled/cylinder `N=8, 0.02453`; angled/cube `N=8, 0.02978`;
  door/cylinder `N=9, 0.02741`; door/cube `N=7, 0.02322`.
- All four cells pass the visual `±0.03` gate.

This is a distributional framing check, not calibrated intrinsics or a
production-quality visual dataset. The camera-conditioned cube-yaw profile
is restricted to independent detection stills; synchronized camera pairs
must share one physical sample pose.

### B. 1280×720 two-camera reference-fit visual pilot

- Dataset: `output/realism_v5_1_referencefit_pilot_54120/`
- Visual sheet:
  `reports/qc/realism_v5_1_referencefit_pilot_contact_sheet.png`
- Resolution/sampling: `1280×720`, 64 spp, no depth.
- Seeds: `54120–54127`; four frames per camera.
- Validator: `8/8 PASS`; all eight images are standard partition.
- Physical RFID instances: 23; 11 standard-positive, 10 fully occluded,
  2 outside frame.
- Checks: 39 binary masks and 55 file hashes.
- This small pilot is for visual review. Its two-sample door/cube bbox
  cell is outside the visual gate; the 32-image run above is the release
  framing evidence.
- Snapshot pins:
  - raw config file SHA-256:
    `f7e69142090359b4bba43d956d6fa3a587c40d98b4e4d0515854ed2c5a57d5fe`
  - canonical config contract SHA-256:
    `5d8a6776fd50af904c65240f3cc306a720d367c825815ff2b44ffc94a54b0e4d`
  - generator SHA-256:
    `32c99dd1b92585ef37cfe3cf10bfc2382b998320942be54986f52d312d5a983d`

### C. 1920×1080 camera heroes

- `output/realism_v5_1_hero_cam10_54121/`: cam-10/camera-angled,
  cube with independent printed paper and plate-gap tags.
- `output/realism_v5_1_hero_cam11_54120/`: cam-11/camera-door,
  cylinder and top-plate-gap RFID state.
- `output/realism_v5_1_hero_cam11_tag_54128/`: cam-11/camera-door,
  cube, paper, three standard-positive and one fully hidden RFID.
- All three are 128 spp, save a reopenable `.blend`, and validate `PASS`.

These are selected visual/QC cases, not a distributional production
dataset.

### D. Same-seed control

`realism_v5_1_determinism_a_54121` and
`realism_v5_1_determinism_b_54121` used the same seed, resolution, samples,
Blender build, generator and config. Scenario metadata is identical after
removing elapsed time, output paths and file hashes. Label, semantic masks
and every RFID instance mask are byte-identical. OptiX-denoised RGB hashes
differ; therefore the release contract promises deterministic
scenario/annotation decisions, not byte-identical GPU-denoised RGB.

### E. Current BlenderMCP round-trip

- Pin: `evidence/mcp/pins_v1_7_3.json`
- Round-trip:
  `evidence/mcp/20260729T171933Z-v173/roundtrip.json`
- Scene: v5.1 cam-10 hero `.blend`, SHA-256
  `401372b39d415a8a852c0940351ecff625d39fd2689f5a38d951f4d4c8cb58af`.
- Result: scene query before/after retained 160 objects, nonce-bearing
  code executed, 1200×698 viewport PNG and 1920×1080/128 spp OptiX PNG
  were verified, and the loopback-only listener was stopped.

This proves the pinned BlenderMCP add-on JSON/TCP path against the current
scene. It does not prove the separate stdio process, photorealism or model
benefit.

## Historical low-resolution calibration evidence

### F. Topology/material calibration4

- Dataset:
  `output/realism_v4_calibration4_low_54100/`
- Visual sheet:
  `reports/qc/realism_v4_calibration4_low_54100_contact_sheet.png`
- Resolution/sampling: `640×360`, 32 spp, no depth.
- Seeds: `54100–54107`.
- Camera balance: 4 `camera_door`, 4 `camera_angled`.
- Validator: `8/8 PASS`.
- Partitions: 6 standard, 2 hard, 0 exclude.
- Physical RFID instances: 23.
- Checks: 39 binary masks and 55 file hashes.
- Snapshot pins:
  - config SHA-256:
    `59de36d894faba164cd6efa8169205fef383b5673aeefa11b9d7d9ca430a5070`
  - generator SHA-256:
    `fc60c613a8b6d4c70d661738d07df7710f407a44d22bf4814a8a9bf4fc70a363`

This run predates later v1.7 generator changes. It is useful as a visual
calibration checkpoint, not as the current source pin.

### G. Occlusion calibration

- Dataset:
  `output/realism_v4_occlusion_calibration_54120/`
- Visual sheet:
  `reports/qc/realism_v4_occlusion_calibration_54120_contact_sheet.png`
- Resolution/sampling: `640×360`, 20 spp, no depth.
- Seeds: `54120–54135`.
- Camera balance: 8 `camera_door`, 8 `camera_angled`.
- Validator: `16/16 PASS`.
- Partitions: 10 standard, 5 hard, 1 exclude.
- Physical RFID instances: 46.
- RFID decisions: 27 standard-positive, 7 hard-positive,
  1 excluded-too-small/occluded, 4 fully-occluded and 7 outside-frame.
- Paper evidence: 7 paper forms; one linked partial-tip scenario checked.
- Checks: 78 binary masks and 110 file hashes.
- Snapshot pins:
  - config SHA-256:
    `59de36d894faba164cd6efa8169205fef383b5673aeefa11b9d7d9ca430a5070`
  - generator SHA-256:
    `20db98071992f490fdbcc5670187fddf6c2bc6f23136a4e126ebe835610ca8b5`

The generator snapshot equals the v1.7 source SHA at the time of this
run, but the config subsequently changed. The metadata and manifests in
the run are the only authoritative pins for that run.

## Visual QC reading

The v5.1 distribution gate, visual pilot, heroes and historical contact sheets show a material
improvement in structural
consistency:

- both cameras now see the same fixed two-tone machine;
- upper/lower circular platen context and sample contact are stable;
- the LED route is continuous rather than a free-floating panel;
- cube/cylinder silhouettes are regular;
- service hardware and aperture cues make the chamber legible;
- paper can occlude a tag while the bbox follows only visible tag pixels;
- no wide black shadow void dominates the chamber.

They also show why production remains on hold:

- v5 removes periodic platen ripples and oversized aggregate, but concrete
  remains procedural and cleaner/smoother than many damaged real crops;
- panel and platen wear remain weaker and more uniform than the aged machine;
- the bright upper region can dominate the image while the true thin LED
  diffuser is not always separately legible;
- paper is planar, clean-edged and weakly conformed; it is not valid on
  cylinders yet;
- RFID appearance is often too saturated/clean and some frame-edge tags
  are compositionally artificial;
- workshop and door hardware are generic proxy geometry;
- the camera model has plausible wide-angle distortion but is not the
  real fisheye/intrinsics solution;
- 1080p hero review exposes proxy paper, workshop and camera-shell detail
  that low-resolution contact sheets conceal.

Therefore the correct phrase is “reference-fit technical pilot,”
not “photorealistic release.”

## Annotation safety finding

The occlusion calibration demonstrates the intended policy mechanics:

1. every physical RFID has a unique pass index;
2. each bbox is derived from that instance’s rendered visible mask;
3. fully hidden and outside-frame instances receive no YOLO row;
4. low-visibility/disconnected visible tags are moved to hard or exclude;
5. if one visible positive is exclude, the entire frame is isolated from
   the standard train partition.

This avoids the known failure mode in which a semantic class-union mask
creates one large bbox for multiple tags. It does not prove that the
thresholds maximize AP; threshold variants remain an ablation.

## Reproduction without the nested-path rsync bug

Local is source of truth:

```bash
export EBIS_LOCAL=/home/utkutopcuoglu/Documents/utku/stajyerler/simulation/ebis-blender
export EBIS_REMOTE=/home/ankaref/Documents/Projects/simulation/ebis-blender
export BLENDER_REMOTE=/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender
```

Direct root → root sync; inspect dry-run first:

```bash
rsync -anic -s --delay-updates --safe-links \
  --exclude='__pycache__/' --exclude='*.pyc' --exclude='*.pyo' \
  --exclude='output/' --exclude='.rsync-partial/' \
  "$EBIS_LOCAL/" "3090:$EBIS_REMOTE/"

rsync -aic -s --delay-updates --safe-links \
  --partial-dir=.rsync-partial \
  --exclude='__pycache__/' --exclude='*.pyc' --exclude='*.pyo' \
  --exclude='output/' --exclude='.rsync-partial/' \
  "$EBIS_LOCAL/" "3090:$EBIS_REMOTE/"
```

Do not add `--relative` and do not use an
`.../ebis-blender/./...` source. Both roots already identify the intended
directory.

Fresh low-res calibration command:

```bash
run_name=reference_fit_calibration_640_64000

ssh 3090 "$BLENDER_REMOTE -b --factory-startup \
  --python $EBIS_REMOTE/scripts/generate_ebis.py -- \
  --config $EBIS_REMOTE/configs/ebis_led_v2.json \
  --action batch --seed 64000 --count 16 \
  --output $EBIS_REMOTE/output/$run_name \
  --resolution 640x360 --samples 32 --no-depth"

ssh 3090 "$BLENDER_REMOTE -b --factory-startup \
  --python $EBIS_REMOTE/scripts/generate_ebis.py -- \
  --config $EBIS_REMOTE/configs/ebis_led_v2.json \
  --action validate \
  --output $EBIS_REMOTE/output/$run_name \
  --expected-count 16 --require-both-cameras"
```

Direct run → run pull:

```bash
mkdir -p "$EBIS_LOCAL/output/$run_name"
rsync -aic -s --partial-dir=.rsync-partial \
  "3090:$EBIS_REMOTE/output/$run_name/" \
  "$EBIS_LOCAL/output/$run_name/"
```

QC sheet:

```bash
python3 "$EBIS_LOCAL/scripts/create_qc_contact_sheet.py" \
  --dataset "$EBIS_LOCAL/output/$run_name" \
  --output "$EBIS_LOCAL/reports/qc/${run_name}_contact_sheet.png" \
  --columns 4 --limit 16
```

Production candidate uses a fresh name, `1920x1080`, at least 128 spp,
then repeats validator, pull and QC. Old calibration directories are not
overwritten and are not revalidated against different source/config
pins.

## Production release gates

All must pass:

1. measured chamber/platen/sample or explicitly owner-approved fallback;
2. expand the current 8-frame visual pilot to a fresh 32-frame
   1920×1080/128 spp production candidate;
3. confirm both cameras and cube/cylinder coverage in that candidate;
4. targeted paper partial/fully-hidden, plate-gap, frame-edge and
   multi-tag cases;
5. validator PASS and manual mask/bbox inspection;
6. 100-frame two-person material/light/geometry/annotation QC;
7. current BlenderMCP scene-info + viewport + Cycles render round-trip;
8. fixed real test split and nano-YOLO ablation.

Model acceptance is based only on the frozen real test set. No AP,
recall, robustness or sim-to-real gain is claimed by this revision.
