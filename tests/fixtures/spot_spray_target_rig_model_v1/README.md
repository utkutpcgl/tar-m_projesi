# Target-rig evaluator fixtures

- `capture_manifest_v1.json` is the canonical `capture_manifest_v1` synthetic
  fixture and declares `evidence_scope=synthetic_fixture`.
- `capture_audit_result_v1.json` is an explicitly synthetic, valid-but-NOT_READY
  audit-interface fixture bound to that manifest.
- `predictions_v1.jsonl` is bound to that exact manifest, audit result, and the
  directional foundation checkpoint hash.
- `capture_manifest_v1.jsonl` is intentionally retained as a malformed legacy
  frame-row format. A regression test proves that the evaluator rejects it;
  production capture input must be the canonical single JSON object.
- `finetune_capture_manifest_v1.json` exercises the exact current rig-acceptance
  and per-frame hardware provenance fields. Its four synthetic records include
  a known train frame, a quarantined `partial_unknown` train frame, a known
  validation frame, and a test frame that must never be materialized or
  byte-read.
- `finetune_capture_audit_v1.json` is the synthetic, hash-bound capture-audit
  companion for dry-run dataset preparation.
- `finetune_images/` contains tiny non-image byte fixtures. Fixture preparation
  hashes and symlinks them but never decodes them or invokes Ultralytics; this
  keeps contract tests CPU-only and makes accidental test-byte access visible.

The fixture deliberately contains one excluded small weed, a 3-of-5 confirmed
track with a later observation, a predicted crop veto, two predicted track IDs
hitting one GT track, a crop collision, and a failing worst field. Fixture mode
can never produce real or chemical-fire GO. The selected validation threshold
remains `0.8`, but its single zero-hit action has Wilson upper 95% `0.79345`, so
validation safety feasibility and both per-field gates correctly fail.
