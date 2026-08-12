# Spot-spray integrated contract release v1

## Release boundary

This release joins the frozen rig-acceptance, capture/audit, target-rig
fine-tune, and track-action interfaces into one fail-closed provenance chain.
Only public pre-real evidence and deliberately synthetic fixtures have been
used. There is no physical target-rig `READY`, real fine-tuning, offline-model
GO, field-fire GO, dry-marker READY, or chemical-fire claim.

## Exact identity chain

| Contract role | Exact SHA-256 |
|---|---|
| Rig acceptance policy | `a6c0e69f1c489e58b7a6c94a92bf50d9dfd97eef0c1b6ec709b872b2f7b66e3c` |
| Rig acceptance evaluator | `596c6db31e6ce90f06b1019657e58631415f1b90fdeeb9fdbd917b4ab461fda2` |
| Capture manifest schema | `d6a3a8c31a3fc762a9f71262074e724864fc265643c9a945f4d2ee742d125745` |
| Capture audit policy | `cbebfea95f8b39dcd2d3189c874e7910f9fdb6d6e58b4e905eaabadc36e667f4` |
| Capture audit implementation | `d75aaebe641b74ad920c701367dc7e0b6d14a3b749093a109690203a1c6834e6` |
| Fine-tune contract | `7231275a5e91b46ecf977377ebd3f88b2f3854fc821f0dea8f166386f831b6dc` |
| Fine-tune implementation | `97499755fdacf00d683ad25acb8cd35c1b01115dfe6c83243c592fa2b8dd1e76` |
| Track-action contract | `210e6feddb93ca269d78a9947b48c2a84d0fb382828ba3265ff7debe06b74b09` |
| Track-action evaluator | `3943090f5b34d730426bbb23e255757f1af28a89b3bbfc2f5a093a57e8ce9e45` |
| Selected pre-real evidence receipt | `12648329337a392572b7e697ca0b359f60ef62af34765e37c46e2574e3ea8878` |
| Selected ROSE-native foundation checkpoint | `3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100` |

The fine-tune contract pins the exact schema, capture policy, audit
implementation, and foundation checkpoint. The action evaluator resolves and
hash-verifies those same capture sources and binds its predictions to the exact
manifest, audit result, and final checkpoint. Synthetic score weight in every
real GO decision is `0.0`.

## Corrected cross-contract defect

Before this release, the capture audit trusted a hash-pinned rig evaluator JSON
but did not require the JSON to identify the exact rig policy or evaluator
implementation. A copied synthetic PASS result could be relabelled as physical,
have its producer identity removed, and satisfy the capture `READY` boundary.

The rig evaluator now emits both `contract_identity` and `implementation`. The
capture policy pins their paths and hashes; the audit verifies every exact and
canonical identity field before considering A–E statuses or collection
permission. Missing or stale provenance is `INVALID`. Publication collision
protection also covers the audit implementation, rig policy, and rig evaluator,
so `--overwrite` cannot replace a trusted producer source.

`tests/test_spot_spray_integrated_contract_v1.py` freezes this chain and
replays both the missing-contract-identity and stale-evaluator attacks. Both
must remain invalid with `physical_collection_allowed: false`.

## Deliberate model boundary

Rig Stage E retains the frozen V2 capture-compute proxy checkpoint
`0b30e1433cecb4ecaa71a1005c520604eaacab9a92595efb18f3966bcd57f6b8`.
That gate supports controlled RGB collection only; it is not latency or safety
evidence for the selected foundation or a future fine-tuned model. The action
contract therefore keeps its evaluated final checkpoint unset and all offline,
field, and chemical GO values false. A final target-rig checkpoint still needs
its own physical timing/safety evidence before any actuation claim.

## Next physical sequence

1. Produce a physical A–E rig receipt and the exact identity-bearing evaluator
   result; hash-bind it into a real capture manifest.
2. Audit decodable, hash-bound real frames and frozen field-level
   train/validation/test roles until the capture report is genuinely `READY`.
3. Record manager capture acceptance, prepare train/validation only, quarantine
   every `partial_unknown` frame, and run the pinned fine-tune protocol.
4. Freeze the final checkpoint hash, calibrate thresholds on validation only,
   and evaluate test once with pooled/per-field Wilson crop-hit safety gates.
5. Keep dry-marker and chemical fire disabled until their independent physical
   registration, deposition, and crop-injury evidence exists.
