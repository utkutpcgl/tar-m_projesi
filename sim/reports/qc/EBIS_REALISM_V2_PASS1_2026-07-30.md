# EBIS realism-v2 — Pass 1/6

Date: 2026-07-30  
Run: `multi-repeat-ebis-realism-v2-clean-assets-208d7e89e2f6`  
Scope: concrete cast scale/BRDF, stable current outputs, cleanup, MCP and
actual-pixel regression.

## Outcome

The accepted releases are:

- Blender `realism_v8_cast_pores_release_60100`, generator `1.8.1`,
  physical revision
  `front_hinged_door_blue_chamber_cast_pores_pass8_2026-07-30`;
- Unreal `realism_r59_neutral_cast_brdf_release_60160`, material
  `M_ConcreteProceduralV27`, physical revision
  `front_hinged_door_blue_chamber_neutral_cast_brdf_pass8f_2026-07-30`.

Both are technical/visual QC candidates. This pass does not establish
photorealism, engine superiority or YOLO benefit.

## Fresh reference inspection

Actual pixels were re-opened from:

- task 9–14 LED RGB, both cam-10 and cam-11, early/mid/late batches;
- 18 `REF*` machine×camera groups, including IR/non-LED grayscale;
- current Blender and Unreal cam-10/cam-11 × cube/cylinder frames;
- the full-resolution real/synthetic pairs used in the
  [engine sheet](../../unreal-ebis/reports/qc/assets/real_blender_unreal_comparison.png).

IR was used only for invariant geometry, contact, door/camera layout and
surface micro-topology. It was not used as an RGB albedo or exposure target.

The largest remaining material gap was concrete scale. Real frames contain
clean and strongly load-damaged regimes, visible millimetre-scale cast pores,
local dirt/aggregate and much stronger upper-contact damage. Blender was too
sterile/satin; Unreal V24 read as cellular and V25 as broad marble clouds.

An 8%-inset concrete-label ROI gives this directional, non-calibration check:

| Pair | Mean RGB | Luma std | `FIND_EDGES` mean |
| --- | --- | ---: | ---: |
| real cam-10 cylinder | `(169.29,164.21,139.99)` | `40.11` | `8.75` |
| Blender cam-10 cylinder | `(191.92,183.52,177.02)` | `12.01` | `5.08` |
| Unreal cam-10 cylinder | `(158.51,151.90,144.97)` | `35.10` | `3.54` |
| real cam-11 cube | `(144.47,145.69,153.82)` | `40.49` | `5.70` |
| Blender cam-11 cube | `(190.03,180.39,172.44)` | `34.57` | `5.39` |
| Unreal cam-11 cube | `(170.18,161.16,149.50)` | `44.78` | `4.80` |

Frames are not the same instant/seed and the real boxes are human YOLO boxes,
so these values are only a direction check. They support the visible finding:
Blender remains too bright/clean; Unreal contrast is not equivalent to real
micro-detail.

## Implemented change

### Blender V8

- Retained straight nominal cube/cylinder hulls and made cast pores
  scale-bounded and small-biased: 68 base plus damage-dependent additions,
  radius `0.38–4.38 mm`, power `2.35`.
- Strengthened the already accepted ambientCG Concrete003 hybrid only within
  bounded color/roughness/bump weights.
- Recorded pore count/radius/distribution in metadata and hard-gated the V8
  surface profile in the validator.
- Trialled Poly Haven `Rough Concrete` 1K with official CC0 provenance and
  `1.23 m` declared scale. Same-seed `59303/59307` concrete-ROI mean absolute
  RGB differences were only `4.78/255` and `4.94/255`; stronger use imported
  outdoor plaster character. The asset was rejected as canonical and retained
  only as [compact A/B](../../ebis-blender/reports/qc/asset_ab/polyhaven_rough_concrete_1k_trial_rejected.png).

### Unreal r59

- Rejected V24 coarse cellular albedo, V25 broad cloud/marble albedo and V26
  residual noise-roughness variants after controlled actual-pixel trials.
- Accepted V27 constant neutral cast albedo `(0.045,0.047,0.045)` and
  roughness `0.86`; local variation now comes from 54–92 small-biased physical
  pores (`0.45–3.85 mm`, power `2.5`), edge relief, residue and bounded damage.
- Disabled unsupported cast shadows on LED strip proxies/contact spill. This
  lifted representative frames by roughly `12.8–17.7/255` and better matches
  the real chamber's lack of fully black contact shadows.
- Preserved the outward right-hinged grey door, blue pebbled fixed walls,
  two `Ø400 mm` platens, three-wall diffuser, instance identity and
  visible/amodal partition contract.
- The rejected iterations are summarized in
  [one six-panel sheet](../../unreal-ebis/reports/qc/asset_ab/procedural_concrete_v24_v29_ab.png).

## Validation evidence

Blender V8:

- 12/12 RGB, `PASS`, `errors=[]`;
- cam-10/cam-11 `6+6`; all four camera×shape cells present;
- 32 RFID, 56 binary masks;
- partitions `8 standard / 1 hard / 3 exclude`;
- regimes `2 clean / 5 pitted / 2 edge-worn / 3 spalled`;
- current source pinned by
  [`CURRENT.json`](../../ebis-blender/output/current_samples/CURRENT.json).

Unreal r59:

- 16/16 RGB, `ok=true`, `errors=[]`, `warnings=[]`;
- cam-10/cam-11 `8+8`, cube/cylinder `8+8`;
- 70 visible + 70 isolated-amodal masks;
- partitions `5 standard / 2 hard / 9 exclude`;
- all four concrete bbox cells within absolute `0.06`;
- current source pinned by
  [`CURRENT.json`](../../unreal-ebis/output/current_samples/CURRENT.json).

MCP:

- BlenderMCP loopback `127.0.0.1:9876`: V8 wide-open scene,
  `163→163` objects, nonce execution, `1200×698` viewport and
  `1920×1080 / 128 spp` RTX 3090 OptiX render
  [PASS](../../ebis-blender/evidence/mcp/20260730-cast-pores-v8/roundtrip.json);
- Epic official Unreal MCP loopback `127.0.0.1:8000`: r59 seed `60175`,
  9-call build/validate/status/render, validator `ok=true`, 1080p RGB, EXR
  and three visible/amodal instances
  [PASS](../../unreal-ebis/evidence/mcp/20260730-neutral-cast-r59-roundtrip.json);
- both processes and ports were closed after verification. Failed seed/lifecycle
  attempts were fail-closed and moved to trash, not promoted as evidence.

## Stable output and cleanup

The only review entrypoints are:

- [Blender current samples](../../ebis-blender/output/current_samples/contact_sheet.png);
- [Unreal current samples](../../unreal-ebis/output/current_samples/contact_sheet.png).

`CURRENT.json.engine_root` is now portable rather than an absolute host path.
Local promotion validates every source run, uses a staging directory and
atomic replace. The 3090 mirror validates `.current_samples.next` hashes before
atomic promotion. Local/remote equality passed for all 30 Blender and 51 Unreal
current files.

Recoverable cleanup:

- local: 11 targets, 1,102 files, 383,390,244 bytes;
- 3090: 23 targets, 1,660 files, 579,116,686 bytes;
- extra scratch: 15 local `/tmp` targets and one remote `/tmp` target;
- method: `gio-trash`; real datasets, source, V8/r59, current samples,
  final comparison, compact A/B, provenance and current MCP were excluded.

Manifests:

- [local](../cleanup/CLEANUP_MANIFEST_PASS1_2026-07-30.json);
- [3090](../cleanup/CLEANUP_MANIFEST_3090_PASS1_2026-07-30.json).
- [final evidence audit](EBIS_REALISM_V2_PASS1_EVIDENCE_AUDIT.json).

## Residual gap and next pass

The next highest-value change is a matched lighting/camera pass, not more
generic texture import:

1. remove Unreal's broad hard planar light bands while retaining non-black
   contact illumination;
2. lower Blender's clean white concrete bias and add bounded load-zone
   dirt/aggregate only in measured damage regimes;
3. fit cam-10/cam-11 fisheye proximity separately so real sample occupancy and
   service-cover position are matched without bending object geometry;
4. inspect RFID-to-surface contact so valid orange tags never read as floating
   machine hardware.

Frozen-real-test YOLO ablation remains unrun; no model-gain claim is made.
