# Target-rig model and track-action pipeline v1

This lane is fail-closed until canonical real-rig data and predictions exist. The
directional pre-real starting checkpoint is:

```text
/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/
  pre_real_data_ceiling_robot_native_train_v1/
  yolo26s_seg_real1407_rose80_native1024_seed41_e8/weights/last.pt
SHA-256: 3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100
```

It is the pinned fine-tuning foundation, not a deployment or chemical-fire
model. `model.evaluated_checkpoint` intentionally remains `null` before real
training. A real evaluation is `NOT_READY` until the later training pass freezes
both the final path and SHA-256 there; fixture predictions may use the foundation
hash without becoming real evidence. The frozen evaluator is
[`configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml`](../configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml),
implemented by
[`scripts/evaluate_spot_spray_target_rig_action_v1.py`](../scripts/evaluate_spot_spray_target_rig_action_v1.py).
The provenance-bound dataset/training contract is
[`configs/benchmark/spot_spray_target_rig_finetune_v1.yaml`](../configs/benchmark/spot_spray_target_rig_finetune_v1.yaml),
implemented by
[`scripts/train_spot_spray_target_rig_finetune_v1.py`](../scripts/train_spot_spray_target_rig_finetune_v1.py).

## Inputs

The capture manifest is one canonical JSON object. It consumes the
manager-frozen `capture_manifest_v1` without changing the shared capture schema.
Its self-declared `evidence_scope` is not proof of real data. Real evaluation
also requires the capture lane's exact audit JSON: it must bind the canonical
manifest path and SHA-256, report `READY`, `valid=true`, `ready=true`,
`real_target_rig`, no errors, and explicit non-fixture eligibility. Its schema,
policy, and audit-script paths and hashes must match the current trusted capture
lane sources. The audit must also attest complete real-capture metadata,
verified image hashes and decodable image content, and passed physical rig
acceptance. `synthetic_fixture` can never become real evidence. Real manifests
now require a hash-pinned `rig_acceptance` result plus the exact hardware
provenance added by the current capture interface. Synthetic manifests retain
backward compatibility, but any optional provenance they provide is parsed
strictly. A minimal real frame has this shape:

```json
{
  "schema_version": "capture_manifest_v1",
  "manifest_id": "rig_release_01",
  "evidence_scope": "real_target_rig",
  "rig_acceptance": {
    "result_path": "receipts/rig_acceptance_v1.json",
    "result_sha256": "<64-lowercase-hex>"
  },
  "frames": [{
    "frame_id": "field03_session04_video02_frame000123",
    "image_path": "images/frame000123.png",
    "image_sha256": "<64-lowercase-hex>",
    "field_id": "field03",
    "session_id": "session04",
    "video_id": "video02",
    "frame_index": 123,
    "timestamp_ns": 1720000000000,
    "camera_frame_counter": 123,
    "camera_timestamp_ns": 1720000000100,
    "encoder_mm": 8123.4,
    "exposure_us": 170.0,
    "gain_db": 0.0,
    "white_balance": {
      "mode": "manual",
      "red_gain": 1.2,
      "green_gain": 1.0,
      "blue_gain": 1.3
    },
    "working_distance_mm": 552.1,
    "native_width_px": 2048,
    "native_height_px": 1536,
    "pixel_format": "BayerRG10p",
    "camera_id": "camera01",
    "rig_id": "rig01",
    "capture_profile_id": "capture_profile_v1",
    "strobe_profile_id": "hood_v1_current_3p2A",
    "strobe_settings": {
      "profile_id": "hood_v1_current_3p2A",
      "pulse_width_us": 50.0,
      "peak_current_a": 3.2
    },
    "split": "test",
    "instances": [{
      "instance_id": "weed_17_frame_123",
      "track_id": "weed_17",
      "class_name": "weed",
      "polygon": [[0.10, 0.12], [0.18, 0.12], [0.18, 0.22]],
      "visible_fraction": 0.91,
      "canopy_span_mm": 27.4,
      "partial": false,
      "occluded": false
    }]
  }]
}
```

Polygons are non-degenerate normalized `[x, y]` point lists. Frame IDs and
field/session/video/frame indices must be unique; timestamps must increase
inside each video. A video cannot cross splits and one track can appear at most
once in a frame. A track may transition between `partial_unknown` and one known
class, but a known `crop`/`weed` conflict is rejected.

Prediction JSONL starts with exactly one provenance record. The manifest hash
binds predictions to the labels being evaluated, the audit hash binds the
capture proof used for that exact evaluation, and the model hash binds them to
the checkpoint that emitted them. For a real run the model hash must equal the
final target-rig checkpoint hash frozen in the evaluator config:

```json
{"record_type":"prediction_metadata","schema_version":1,"model_checkpoint_sha256":"3aba4b19...73100","capture_manifest_sha256":"<manifest-sha256>","capture_audit_result_sha256":"<audit-result-sha256>"}
```

Every validation and test frame then has exactly one record, including empty
frames:

```json
{
  "record_type": "frame_prediction",
  "frame_id": "field03_session04_video02_frame000123",
  "candidates": [
    {
      "predicted_track_id": "predicted_weed_41",
      "class_name": "weed",
      "confidence": 0.87,
      "polygon": [[0.10, 0.12], [0.18, 0.12], [0.18, 0.22]],
      "action_point": [0.14, 0.17]
    },
    {
      "predicted_track_id": "predicted_crop_09",
      "class_name": "crop",
      "confidence": 0.99,
      "polygon": [[0.50, 0.40], [0.70, 0.40], [0.70, 0.70]]
    }
  ]
}
```

`predicted_track_id` is stable only inside its field/session/video. The
evaluator consumes these IDs; it does not repair association or perform ReID.
Only weed candidates carry an action point, which must lie in their own mask.
An action point inside a predicted crop mask at the frozen crop-mask confidence
is vetoed before it can confirm a fire event.

## Frozen evaluation semantics

An eligible GT weed track enters the denominator if any non-partial weed
observation has canopy span at least `20 mm` and visible fraction at least
`0.70`. This set is frozen from labels before any prediction is scored.

A predicted weed track must have three qualifying observations inside five
frame indices. It fires at the third qualifying observation's action point and
can never fire again. Separate predicted IDs that hit the same eligible GT
track reveal fragmentation: the first one-to-one hit is a TP; later hits are
both duplicate shots and false positives.

Scoring precedence is:

1. GT crop contact: crop-collision false positive.
2. Partial weed or `partial_unknown` contact: false positive.
3. First contact with one unmatched eligible weed track: true positive.
4. Repeat eligible-track contact: duplicate-shot false positive.
5. Contact with a non-partial weed outside the `20 mm / 0.70` denominator:
   ignored for P/R/F1, but retained in attempted-shot crop/duplicate safety
   denominators.
6. Everything else: background false positive.

Validation alone selects the weed-confidence threshold. It maximizes recall
among thresholds meeting validation precision, crop-hit, and duplicate safety;
ties use F1, precision, then the higher threshold. If no threshold is feasible,
validation-only maximum-F1 fallback is diagnostic and forces NO GO. Test is
read once at that frozen threshold and cannot tune it.

The test result reports pooled and per-field track P/R/F1, crop hits with the
Wilson 95% upper bound, duplicate shots, and worst-field values. The same
Wilson upper bound is a hard validation-feasibility and pooled/per-field gate;
reporting a zero point estimate from a tiny sample is not sufficient. Offline model
GO requires pooled **and every field** to meet:

- precision `>= 0.98`;
- recall `>= 0.95`;
- F1 `>= 0.965`;
- crop-hit point rate `<= 0.005` and Wilson upper 95% bound `<= 0.005`;
- duplicate-shot rate `<= 0.01`.

Synthetic scores have exactly zero weight. Fixture mode always forces real GO
false. Even a passing real offline model evaluation leaves
`chemical_fire_go=false`; registration, deposition, crop-injury, emergency
stop, and physical safety gates are separate.

## Commands and status

Before real inputs exist, the default command returns exit code `2` and a
machine-readable `NOT_READY` result:

```bash
.venv/bin/python scripts/evaluate_spot_spray_target_rig_action_v1.py
```

Run the contract fixture without touching the GPU (it deliberately exits `4`):

```bash
.venv/bin/python scripts/evaluate_spot_spray_target_rig_action_v1.py \
  --manifest tests/fixtures/spot_spray_target_rig_model_v1/capture_manifest_v1.json \
  --capture-audit tests/fixtures/spot_spray_target_rig_model_v1/capture_audit_result_v1.json \
  --predictions tests/fixtures/spot_spray_target_rig_model_v1/predictions_v1.jsonl
```

Run real evaluation only after the capture lane freezes the canonical manifest
and prediction generation is complete:

```bash
.venv/bin/python scripts/evaluate_spot_spray_target_rig_action_v1.py \
  --manifest /path/to/capture_manifest_v1.json \
  --capture-audit /path/to/capture_audit_v1.json \
  --predictions /path/to/predictions_v1.jsonl \
  --output /path/to/target_rig_action_result_v1.json
```

Evaluator exit codes are stable and fail closed:

- `0`: `EVALUATED_OFFLINE_MODEL_GO` only;
- `2`: `NOT_READY`;
- `3`: `EVALUATED_NO_GO`;
- `4`: `FIXTURE_ONLY`;
- `5`: `CONTRACT_ERROR`.

The CLI refuses missing inputs, schema/provenance drift, split leakage,
incomplete prediction coverage, invalid masks, unstable track classes, and
overwriting an existing result without `--overwrite`.

## Fine-tuning preparation and training boundary

The model lane is synchronized to the current capture schema, audit policy, and
audit implementation by exact path and SHA-256. Any change to one of those
three files fails config validation until this model contract is reviewed and
repinned. The integrated capture audit implementation pinned by this revision
is `d75aaebe641b74ad920c701367dc7e0b6d14a3b749093a109690203a1c6834e6`;
its policy identity is
`cbebfea95f8b39dcd2d3189c874e7910f9fdb6d6e58b4e905eaabadc36e667f4`.
That audit in turn requires the exact rig contract and evaluator producer
identities before a physical acceptance result can contribute to `READY`. Real
preparation additionally requires all of the following:

- the manifest and audit both declare `real_target_rig`;
- the audit is bound to the exact manifest path, manifest SHA-256, and data root;
- every capture-audit real-proof check passes, including physical rig
  acceptance, complete frame provenance, image-byte hashes, and decoded native
  dimensions;
- `capture_interface.manager_acceptance` is frozen to `accepted` with a
  non-empty acceptance identity.

The checked-in contract intentionally keeps that last status at
`pending_manager_acceptance`. Therefore no physical real fine-tuning can start
from this revision. `--fixture-mode` is accepted only when both manifest and
audit are explicitly synthetic; it cannot relabel unproven real evidence.

Preparation materializes symlinks and YOLO segmentation labels for `train` and
`validation` only. It never materializes a test image or test label and never
reads test image bytes. A whole frame is quarantined before image access when
any annotation is `partial_unknown`; Ultralytics segmentation has no ignored
mask-region target, so retaining such a frame would silently teach unresolved
pixels as background. Known crop and weed masks map to class IDs 0 and 1.

The prepared dataset contains no `test` key. Training starts from the exact
pinned foundation checkpoint, runs the frozen 30-epoch/batch-3/1024/seed-41
protocol, and selects only the fixed epoch-30 `last.pt`; `best.pt` and test data
cannot select the checkpoint. Validation is monitoring-only during training and
is reserved for the later frozen action-threshold calibration. Receipt, source
image, symlink, label, manifest, audit, config, and foundation hashes are
rechecked immediately before and after execution. No fixture or dry run can
call Ultralytics or produce a checkpoint.

Run deterministic fixture preparation without touching the GPU (exit `4`):

```bash
.venv/bin/python scripts/train_spot_spray_target_rig_finetune_v1.py \
  --manifest tests/fixtures/spot_spray_target_rig_model_v1/finetune_capture_manifest_v1.json \
  --capture-audit tests/fixtures/spot_spray_target_rig_model_v1/finetune_capture_audit_v1.json \
  --data-root tests/fixtures/spot_spray_target_rig_model_v1 \
  --output-directory /tmp/spot_spray_target_rig_finetune_fixture \
  --fixture-mode
```

After capture-manager acceptance and a physical `READY` audit, prepare a real
dataset without training:

```bash
.venv/bin/python scripts/train_spot_spray_target_rig_finetune_v1.py \
  --manifest /path/to/capture_manifest_v1.json \
  --capture-audit /path/to/capture_audit_result_v1.json \
  --data-root /path/to/audited/data_root \
  --output-directory /path/to/new/derived_output
```

Add `--execute-training` to that exact command only after reviewing the dry-run
receipts and securing a GPU window. The command never unloads or modifies other
GPU processes. Its stable exits are `0` for real dry-run readiness or completed
training, `2` for missing/external readiness, `4` for fixture-only success, and
`5` for a contract violation.

Every preparation emits `dataset_receipt.json`, `training_receipt.json`, and
`final_checkpoint_receipt.json`. The dataset receipt binds the config,
manifest, audit, data root, foundation, capture release, materialized counts,
quarantine list, dataset files, and explicit test-isolation facts. Dry-run
training/final receipts say `training_executed=false` and contain no checkpoint.
A successful physical run binds the exact arguments, runtime, 30-row results
history, fixed `last.pt` path/SHA-256, and the unchanged foundation and dataset
receipts. That final checkpoint remains `NOT_EVALUATED`: it must be frozen into
the action evaluator, generate validation/test predictions, and pass the frozen
offline action gates before any model GO. Training never implies field-fire or
chemical-fire GO.
