# CropCraft botanical track ground truth V1

Status: **PASS_PROTOCOL_ADMISSION_PILOT_SYNTHETIC_ONLY**

This is a deterministic, synthetic-only protocol-admission pilot. It proves
source-bound botanical identity and occlusion accounting; it is not the native
2048 px benchmark release, physical capture evidence, or field/product approval.

- Source tracks: 5 (4 crop, 1 weed)
- Frames: 4
- Track-frame rows: 20
- Frames with overlapping isolated silhouettes: 4
- Occluded track-frame rows: 4
- Field-state/actual source-object disagreements recorded: 4
- Determinism replay byte-identical: true
- Ideal/degraded GT byte-identical: true

Identity is assigned from CropCraft bed points and Geometry Nodes dependency-
graph instances before rendering. Semantic connected components, model
predictions, and rendered pixel topology are explicitly forbidden as identity
inputs.
