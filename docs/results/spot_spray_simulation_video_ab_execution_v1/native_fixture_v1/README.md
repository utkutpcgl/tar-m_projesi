# Native 2048 integration fixture receipt

Status: `PASS_NATIVE_FIXTURE_VALIDATION_SYNTHETIC_ONLY`.

This is the required one-calibration/one-locked-test integration fixture. It is
not the frozen 32/64-pair benchmark and carries no field, product, or chemical
authorization.

## Bound execution

- Protocol SHA-256: `de12cd76d3f497f1ea3a6ffa1d1c7fc8eea4e70a9af218c2769bae81da0f329f`
- Botanical receipt / patch: `491776943143ca486c0fda7f307db4ec7372cc35adfd216c9243ac5efd36c956` / `c2301376c2f1607d1abfeeb75a6b9ad9b29873c764b027bd6995b10ebcaddd24`
- Paired renderer receipt / code: `179410f6f975e1b7b43c369839ea3b58f74e6eb2ccc667dc4e64127b5ce7d5b3` / `3fa5b6a5838dc45126f55d54875c65da7fc6cc7ff0e3078104f207f5d3809082`
- Evaluator / checkpoint: `83c6fabd1acc3db47799e96aea91b46d29f514d891c5f19091d3fb14bf3811f7` / `3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100`
- Execution config / script: `a172b8b3c9fcab3ca57e5557e38a662d94b7660b3dd3a8d41533f722713618a7` / `413aa3b222b6709d9dd1bb37b74ee851683ac3b2f661763e56ed5418ba6e7820`
- Release lock: `f93b7450f28ec12c909e0e82bbf8b95f5204044f65411f9a8193037ce638a3c1`
- Threshold lock: `3e56891c4889b6314c90a2a2927cd6751744650c9d88654be9b4a5e307046795`

Both scenes have 30 native 2048x2048 frames per arm at 15 Hz. The
calibration/test source scenes contain 20/30 persistent botanical tracks and
2/4 visible eligible weed tracks, respectively. Every botanical validation
gate passed. Ideal and degraded arms use the same canonical GT paths and have
byte-identical GT digests (`02e6...58c9` calibration, `4065...025` test).
The degraded PSF paths are 0.321 px and 0.727 px, within the frozen 0.75 px
ceiling, with no noise, compression, or post-outcome rescaling.

All six capture videos decode to exactly 30 frames at 15 Hz. Native arm videos
are 2048x2048; paired previews are 2048x1024. The locked-test overlay preview
decodes to 30 frames at 15 Hz and is 2048x1076.

## Access-order proof and diagnostic result

The only threshold source was degraded calibration. The shared threshold was
locked at 0.80 before any test prediction; ideal calibration was diagnostic
only. Both test arms were then inferred and locked-test metrics were evaluated
exactly once. The access ledger records zero pre-lock test access.

The single calibration scene had no safety-feasible threshold, so the frozen
calibration-only diagnostic fallback selected 0.80. On the single test scene,
both arms had 0 TP, 0 FP, and 2 FN eligible tracks; track and action F1 are
therefore undefined rather than zero. Ideal/degraded weed pixel F1 was
0.0882/0.1064 and weed instance F1 was 0.2105/0.2564. Neither descriptive
track target is met by this fixture, and the fixture is too small to issue the
full-benchmark verdict.

## Measured capacity and scale gate

- Render/package wall time: 2,080.53 s for two pairs; peak RSS 5.22 GB; no swap.
- Inference/evaluation wall time: 166.32 s for 120 arm-frames; peak RSS 6.63 GB;
  measured model-call throughput 18.96 frame/s across the four sequences.
- Published synthetic fixture: 781,405,150 bytes; inference run: 19,925,147
  bytes; 342,373,941,248 bytes remained free after publication.
- A naive 48x pair-count projection is about 38.46 GB, 27.74 render hours, and
  2.22 inference/evaluation hours. This is planning evidence only: the full
  roster has different track density and candidate attempts.
- The fail-closed full-run gate remains the more conservative 180 GB estimate
  plus 30 GB reserve and the 61.44-hour isolated-render upper bound. The latest
  free-space observation clears that gate by about 132.37 GB, but it must be
  rerun immediately before scaling.

Authoritative machine-readable artifacts are `render_receipt.json`,
`preflight_receipt.json`, `fixture_validation_receipt.json`, and the files in
`inference/`. The synthetic dataset and videos live under
`data/synthetic/cropcraft/spot_spray_simulation_video_ab_execution_v1/native_fixture_v1`;
the prediction masks and overlays live under
`data/runs/spot_spray_simulation_video_ab_execution_v1/native_fixture_v1`.
