# Spot-spray target-rig data capture and annotation contract v1

## Current decision

`capture_manifest_v1` is the canonical contract for the next target-rig RGB
collection. The schema, audit, split assignment, and tests are executable. No
real target-rig collection is included here, so this work does **not** establish
field performance or unlock training, deployment, or a GO decision.

The readiness rule is fail-closed:

- `INVALID`: schema, metadata, path, identity, polygon, temporal, or split
  integrity failed;
- `NOT_READY`: the manifest is structurally valid but real coverage or frozen
  roles are insufficient, the physical A-E collection acceptance is missing or
  unmeasured, required real-capture provenance is missing, or the input is
  explicitly a synthetic fixture;
- `READY`: valid `real_target_rig` evidence is byte-bound to decodable images
  and a hash-pinned physical-bench A-E evaluator result, has at least 3 fields
  and 4 field/session groups, contains train/validation/test, and passes every
  frozen integrity and leakage check.

Synthetic fixtures always remain `NOT_READY`, even when their mock counts meet
the numeric coverage thresholds. They test software behavior and are never
reported as real field evidence.

There is still no physical acceptance result or real target-rig image set in
this repository. Therefore actual `READY` is **unproven**. The fixtures do not
authorize collection, training, deployment, chemical fire, or a field claim.

## Frozen files

- Schema: `configs/data/spot_spray_capture_manifest_v1.schema.json`
- Audit policy: `configs/data/spot_spray_capture_audit_v1.yaml`
- Audit/split CLI: `scripts/audit_spot_spray_capture_v1.py`
- Contract tests and deliberately synthetic inputs:
  `tests/test_audit_spot_spray_capture_v1.py` and
  `tests/fixtures/spot_spray_capture_v1/`

The manifest is one JSON document containing `frames[]`. Each frame is the
equivalent of one canonical JSON record; JSON Lines is deliberately not part of
v1. The manifest hash binds the records, each `image_sha256` binds exact image
bytes, and `rig_acceptance.result_sha256` binds the physical acceptance output.
Changing any referenced bytes without updating the record is `INVALID`.

## Frozen contract identity

The CLI accepts only the exact frozen v1 policy and schema, both by canonical
semantics and by file SHA-256:

- policy: `cbebfea95f8b39dcd2d3189c874e7910f9fdb6d6e58b4e905eaabadc36e667f4`;
- schema: `d6a3a8c31a3fc762a9f71262074e724864fc265643c9a945f4d2ee742d125745`.

This prevents a caller from substituting a relaxed policy while still naming
it v1. In particular, the split ratios are exactly `0.60/0.20/0.20`, the seed
is exactly `spot_spray_capture_manifest_v1`, the normalized polygon-area floor
is exactly `1e-8`, adjacency is exactly one frame, and readiness thresholds are
exactly three fields plus four field/session groups. The remaining policy and
schema structure is also canonically pinned, not just these examples.

JSON and YAML are parsed fail-closed: duplicate keys, non-finite JSON numbers,
wrong root types, policy drift, schema drift, and even a formatting-only file
identity change are rejected. Updating this frozen v1 contract therefore
requires an intentional code/policy/schema revision and new validation receipt;
a command-line policy swap is not a supported tuning mechanism.

## Frame contract

Every frame has the original core fields below. Rows described as real-only
are additionally mandatory in the audit for `real_target_rig`; they remain
schema-optional solely to preserve v1 synthetic/model compatibility.

| Field | Meaning and v1 rule |
|---|---|
| `frame_id` | Unique stable ID in the manifest. |
| `image_path` | POSIX path relative to the selected repository or data root. Absolute paths, `..`, empty components, missing files, empty files, and duplicate resolved paths fail. Symlink escape from the data root also fails. |
| `image_sha256` | SHA-256 of the exact image bytes. Required and verified for `real_target_rig`; mutation is `INVALID`. |
| `field_id` | Physical field identity. One field belongs to exactly one split role. |
| `session_id` | Capture session identity. A session ID may not occur in multiple fields. |
| `video_id` | Contiguous camera stream identity. A video ID may not occur in multiple field/session scopes. |
| `frame_index` | Zero-based integer index, unique within a video. |
| `timestamp_ns` | Strictly increasing timestamp for the real-time controller event that hardware-triggers the camera and latches `encoder_mm`; never host-arrival time. |
| `camera_frame_counter` | Camera-emitted hardware frame counter. Real video records must be contiguous and its delta must equal the `frame_index` delta. |
| `camera_timestamp_ns` | Camera-emitted hardware timestamp; strictly increasing inside a video and never host-arrival time. |
| `encoder_mm` | Signed encoder position in millimetres. It is not forced monotonic because a rig may reverse. |
| `exposure_us` | Camera exposure in microseconds. The audit policy applies broad corruption bounds; the rig acceptance gate remains separate. |
| `gain_db` | Camera gain in dB. |
| `white_balance` | Exact manual red/green/blue gain state; automatic or missing WB cannot enter real `READY`. |
| `working_distance_mm` | Lens-to-ground working distance in millimetres. |
| `native_width_px`, `native_height_px`, `pixel_format` | Exact native sensor dimensions and camera pixel format. Decoded container dimensions must match. |
| `camera_id`, `rig_id` | Physical camera and rig identities. They may not drift within a video. |
| `capture_profile_id` | Frozen identity for camera/rig, dimensions, pixel format, exposure, gain, WB, working distance, and strobe binding. Reusing an ID with different values is `INVALID`. |
| `strobe_profile_id` | Frozen lighting/strobe recipe ID used for the frame. |
| `strobe_settings` | Exact profile binding, pulse width, and peak current. Its `profile_id` must equal `strobe_profile_id`. |
| `split` | `unassigned`, `train`, `validation`, or `test`. |
| `instances[]` | Exhaustive visible crop/weed/partial-unknown instance annotations for the accepted image envelope. Empty arrays are valid negative frames. |

The extra real-only fields are optional in the JSON Schema so existing
synthetic/model fixtures remain valid v1 inputs, but the audit requires all of
them before real `READY`. It hashes complete files and asks Pillow to verify the
image container and dimensions; it does not calculate scene-quality metrics or
infer agronomic evidence from pixels. Focus/MTF, distortion, blur, illumination
uniformity, nozzle registration, latency, deposition, kill, and crop injury
remain separate physical gates.

## Physical A-E acceptance binding

A `real_target_rig` manifest must contain:

```json
"rig_acceptance": {
  "result_path": "receipts/rig_acceptance_result_v1.json",
  "result_sha256": "<64 lowercase hex characters>"
}
```

`result_path` is POSIX and relative to `--data-root`. The path must stay inside
that root. The referenced JSON must match its hash and the frozen
`controlled_spot_spray_rig_acceptance_v1` evaluator interface. The capture
audit does not reimplement A-E thresholds; it verifies the evaluator's
receipt/source validation, measured A-E stage statuses, collection gate and
acceptance outcomes, and final decision.

The result is also bound to its producer. Its `contract_identity` must report
the exact rig contract byte SHA-256
`a6c0e69f1c489e58b7a6c94a92bf50d9dfd97eef0c1b6ec709b872b2f7b66e3c`
and canonical-policy SHA-256
`c05ae3837d98f313c32e81178045a9fef39965199c276ec06e9d01195e88ff21`,
with both verification flags true. Its `implementation` must report
`scripts/evaluate_spot_spray_rig_acceptance_v1.py` at SHA-256
`596c6db31e6ce90f06b1019657e58631415f1b90fdeeb9fdbd917b4ab461fda2`.
A missing, stale, or contradictory producer identity is `INVALID`, even when a
hash-matched JSON copies every PASS/GO field.

Only all of the following can remove this readiness blocker:

- `evidence_kind: physical_bench`;
- receipt validation and frozen-V2 source integrity are `PASS`;
- every A-E stage is `measured` and `PASS`;
- `collection_gate_outcome_A_E` and
  `collection_acceptance_outcome_A_E` are `PASS`;
- `decision.controlled_data_collection_allowed: true` and
  `decision.deployment_evidence_eligible: true`;
- the evaluator's passing `root.rig_unit_id` and Stage-A
  `camera.serial_number` checks exactly match every frame's `rig_id` and
  `camera_id`.

A missing result or a well-formed FAIL/NOT_MEASURED/synthetic result is
`NOT_READY`. Path escape, hash drift, malformed result content, or a positive
decision contradicting its evidence/status is `INVALID`. A synthetic receipt
can test the boundary but can never unlock real evidence.

## Instance-mask and track contract

Every item in `instances[]` contains:

- `instance_id`: stable ID for this frame's instance observation, unique in the frame;
- `track_id`: stable cross-frame track identity in the same scope;
- `class_name`: exactly `crop`, `weed`, or `partial_unknown`;
- `polygon`: one outer polygon with at least three unique `[x, y]` vertices,
  normalized to `[0, 1]` in image coordinates; do not repeat the first point;
- `visible_fraction`: visible fraction in `(0, 1]`;
- `canopy_span_mm`: measured canopy span when eligible, otherwise `null`;
- `partial`: true when the plant is truncated by the accepted image boundary;
- `occluded`: true when another object hides part of the plant.

Within a frame, an `instance_id` and a `track_id` each occur at most once.
`instance_id` identifies one frame-local mask observation and may therefore
change on the next frame; `track_id` is the stable cross-frame plant identity.
A track may move from `partial_unknown` to a known class when later evidence is
sufficient, but it may not conflict between known `crop` and `weed` classes.

`partial_unknown` is only for a border-truncated plant whose crop/weed identity
cannot be resolved: it requires `partial: true` and
`canopy_span_mm: null`. A completely visible, non-occluded crop or weed
(`visible_fraction >= 0.999999`) requires a measured canopy span. The policy
also rejects zero-area, repeated-vertex, out-of-range, and self-intersecting
polygons.

Stem points, stem masks, skeletons, and keypoints are intentionally deferred.
They are not accepted as extra v1 properties. The intervention foundation
remains crop/weed instance masks plus stable track IDs.

### Annotation order

1. Run the physical A-E evaluator; preserve its JSON output and SHA-256 beside
   the collection. A synthetic or unmeasured result is not collection approval.
2. On every hardware trigger, latch the controller timestamp/encoder state and
   persist the camera counter/timestamp plus the exact frozen capture settings.
3. Hash each closed image file, then freeze the manifest metadata before
   annotation. Do not use a host-arrival timestamp as either hardware clock.
4. Mark every visible crop and weed instance in the accepted image envelope.
5. Give every mask observation a stable frame-local `instance_id`, and reuse
   the same `track_id` for that plant through the video.
6. Use `partial_unknown` only for unresolved border truncation; do not turn
   ordinary uncertainty into background.
7. Measure `canopy_span_mm` for eligible complete plants using the rig's
   calibrated scale; never derive it from the PhenoBench 82 px proxy.
8. Run the audit before any split is used for training or evaluation.

## Deterministic split and leakage boundary

The strongest grouping boundary is the physical field. The deterministic
assignment hashes `deterministic_seed + field_id`, orders fields by that hash,
and allocates the frozen 60/20/20 target fractions. When at least three fields
exist, every role receives at least one field before the remaining quota is
allocated. All sessions, videos, frames, instances, and tracks in that field
inherit its role.

The audit independently rejects:

- one field crossing roles;
- one field/session group crossing roles;
- one `(field_id, session_id, video_id, track_id)` crossing roles;
- adjacent frames in a video crossing roles (v1 adjacency is an index gap of
  at most one);
- a fully assigned field whose role differs from the deterministic plan;
- a field mixing `unassigned` and frozen roles.

This makes field, session, video-track, and adjacent-frame leakage visible even
though field-level isolation already supplies the strongest containment.

The split writer accepts only a manifest whose frames are all `unassigned`. It
writes a new derived file and refuses to overwrite the source. Existing manual
roles are never silently changed.

## Output publication and collision rules

`--output` and `--assign-splits` are publication targets, never implicit
scratch files. A target that already exists is refused unless the operator
supplies the single explicit `--overwrite` flag. That flag applies only to
ordinary non-source targets. It can never authorize a collision with:

- the source manifest, audit policy, or manifest schema;
- any referenced image or rig-acceptance result;
- the capture-audit implementation, rig contract, or rig evaluator source;
- the other publication target.

The same resolved path may not occupy two source roles either. These checks use
resolved paths, so symlink aliases do not bypass the boundary. Both reports and
derived manifests are fully written and flushed to a temporary file in the
target directory, then published atomically. Without `--overwrite`, the final
publish also uses an exclusive operation so a target appearing during the run
is not replaced.

## Commands

Generate the frozen acceptance output from an actual receipt first (see
`docs/SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md`), place it under the capture data
root, and record the exact output SHA-256 in `rig_acceptance`:

```bash
python scripts/evaluate_spot_spray_rig_acceptance_v1.py \
  --receipt /path/to/physical_rig_receipt.yaml \
  --decision-target controlled-data-collection \
  --output /path/to/capture_data/receipts/rig_acceptance_result_v1.json
sha256sum /path/to/capture_data/receipts/rig_acceptance_result_v1.json
```

Audit a manifest whose paths are relative to a data root:

```bash
python scripts/audit_spot_spray_capture_v1.py \
  --manifest /path/to/capture_manifest_v1.json \
  --data-root /path/to/capture_data \
  --output /path/to/capture_audit_v1.json
```

Create a deterministic split manifest from an entirely `unassigned` source:

```bash
python scripts/audit_spot_spray_capture_v1.py \
  --manifest /path/to/capture_manifest_unassigned_v1.json \
  --data-root /path/to/capture_data \
  --assign-splits /path/to/capture_manifest_frozen_v1.json \
  --output /path/to/capture_split_audit_v1.json
```

To intentionally replace already-existing, non-source report and derived
targets, add exactly one flag:

```bash
python scripts/audit_spot_spray_capture_v1.py \
  --manifest /path/to/capture_manifest_unassigned_v1.json \
  --data-root /path/to/capture_data \
  --assign-splits /path/to/capture_manifest_frozen_v1.json \
  --output /path/to/capture_split_audit_v1.json \
  --overwrite
```

Omitting `--overwrite` preserves every existing target byte-for-byte and exits
`INVALID=2`. Supplying it does not change the audited decision: for example, a
synthetic audit may publish a replacement report but still exits
`NOT_READY=3`.

Exit codes are stable: `0=READY`, `2=INVALID`, `3=NOT_READY`. A valid but
insufficient collection therefore cannot be mistaken for command success in an
automated release gate.

Run the focused fixture suite:

```bash
pytest -q tests/test_audit_spot_spray_capture_v1.py
```

Legacy synthetic fixtures use non-image placeholder bytes. They remain valid
contract fixtures because container decoding and byte hashes are real-only
readiness requirements; simply relabelling one as `real_target_rig` now fails
closed. The dedicated rig-acceptance fixture is also explicitly synthetic.
None is a capture sample, hardware receipt, field result, or deploy claim.

## Compatibility and model-lane interface

This remains a backward-compatible hardening of `capture_manifest_v1`, not a
new schema version. Existing synthetic/model-lane manifests keep parsing and
remain `NOT_READY`; their prior required fields and instance/track semantics do
not change. Any consumer preparing or copying a real manifest must preserve
`rig_acceptance`, `image_sha256`, both hardware counter/timestamps, exact
WB/strobe state, native dimensions/pixel format, and camera/rig/profile
identities. The fine-tune contract pins this policy and audit implementation by
exact SHA-256; source drift therefore blocks preparation until the whole chain
is intentionally revalidated.

## Readiness is not performance

`READY` means only that the real collection is large and isolated enough to
enter the next controlled modelling step. It does not mean the model passed the
future track-action gate. That later, completely separate-session test still
must report track precision, recall, F1, crop-hit per attempted action,
duplicate-shot rate, and worst-field behavior before any field-fire decision.
