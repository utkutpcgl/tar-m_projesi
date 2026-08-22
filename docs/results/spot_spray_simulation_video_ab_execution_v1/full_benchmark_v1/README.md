# Full 32/64 benchmark execution

Status: `IN_PROGRESS_PREOUTCOME_SYNTHETIC_ONLY` (9/96 pairs published).

The source-locked roster still contains 32 calibration and 64 locked-test pair
slots, 960 predeclared candidates, and 4,800 unique candidate seeds. No full-run
checkpoint load, inference call, threshold selection, prediction output, or
locked-test metric access has occurred.

## Native integration pairs

- Published pair: `calibration_c000_r00`; selected predeclared candidate: 6.
- Terminal receipt SHA-256:
  `27892b2e2a8ed008fc04d7c890e4c839af84c70eac4c69a36ea7c8e3b680db43`.
- Source template: locked `scene_0004`, SHA-256
  `aa705dcfca611f3a91f9a9732361abeb50755956bc6fe9cd63b8d1cac38cdfe5`.
- Each arm contains exactly 30 lossless 2048x2048 RGB frames at 15 Hz. The
  ideal, degraded, and side-by-side H.264 videos each decode to exactly 30
  frames.
- Both sequence records reference the same 30 canonical semantic and uint16
  track masks; canonical GT SHA-256 is
  `ae319423d9133117c4f3c2af3d88d633fea69fabb4cf9fa1c7aa91168748cd29`.
- All six top-level non-model gates passed. Mean crop fraction was 0.106949,
  mean weed fraction 0.012373, weed-free frame fraction 0.0, and four eligible
  weed tracks contributed 6, 9, 10, and 8 observations.
- The ideal deterministic replay matched decoded RGB pixels in all 30 frames.
  PNG container bytes differed and remain a diagnostic, not the frozen gate
  basis.
- Ideal and degraded RGB differed in every frame; minimum changed-pixel
  fraction was 0.609792. The degraded PSF path was 0.350132 px with effectively
  zero centroid error.
- Accepted-candidate wall time was 2,416.46 seconds. A second invocation returned
  `SKIP_EXISTING_PASS_FULL_PAIR_PREOUTCOME_SYNTHETIC_ONLY` in 0.048 seconds with
  the same terminal receipt SHA-256 and no rerender.
- The published pair occupies 972,147,916 bytes. Post-run free space was
  341,396,795,392 bytes, above the frozen 180 GB admission requirement plus
  30 GB reserve.

Candidates 0 through 5 were rejected in roster order using only frozen
preoutcome gates. Their receipt/log evidence occupies about 0.81 MB; bulk
payloads were removed. Every rejection ledger row records
`model_or_outcome_inputs_used: false`.

## Locked GT-only roster scout

A separately sealed GT-only scout now runs before expensive three-arm RGB
rendering. It uses the unchanged full candidate derivation, role allowlist,
shared trajectory, all five seed bindings, native 2048-square semantic masks,
and source-object botanical track GT. It can append a canonical candidate
rejection only for the frozen semantic or eligible-track predicates. A scout
pass has no acceptance authority: the candidate must still pass the unchanged
full renderer and all RGB, replay, video, audit, and release gates.

- Scout execution-lock SHA-256:
  `5fe68dd43183a588b02724bfd0af090f405f7a27f2eacf74b109b84c40a3c3d3`.
- The pre-existing full-render implementation and execution-lock identities
  remain `7a28319b...3751` and `10490375...804` respectively.
- Published candidate 6 was regenerated through the GT-only path in 368.65
  seconds. All 30 semantic hashes, all 30 uint16 track hashes, every per-frame
  track label, semantic/temporal audit, source GT receipt, scene-graph identity,
  eligible-track count, and role-asset decision matched the published full pair
  exactly. Canonical GT remained `ae319423...cd29`.
- The compact equivalence result occupies 679,890 bytes after bounded removal
  of 22,589,790 bytes of source-scene and canonical-mask bulk payload. Relative
  to the same candidate's 2,416.46-second full render, the observed wall-time
  ratio was 6.55x; this is a measured integration result, not a whole-roster
  runtime promise.
- A dry-run on the next slot, `calibration_c000_r01`, automatically selected
  roster candidate 0 and finished in 422.98 seconds. Crop fraction was
  0.021672, weed fraction was 0.008168, and both eligibility checks passed with
  five eligible weed tracks. It honestly returned a GT-only rejection solely
  because mean weed fraction was below the frozen 0.01 lower bound.
- Dry-run mode left the canonical rejection ledger unchanged at six rows. A
  repeated invocation returned `SKIP_EXISTING` with the same terminal receipt
  `37c25cea...2f21` and did not rerender.
- The first attempted scout lock is retained as a failed-integration receipt:
  its patch placed the proxy call inside the botanical function call and the
  runner fail-closed at 0/30 frames. The corrected combined patch was applied
  to a pinned CropCraft archive and Python-compiled before the sealed successful
  runs; no failed result entered the ledger.

## Second canonical calibration slot

The candidate 0 dry-run decision for `calibration_c000_r01` was committed to
the canonical ledger exactly once. Its sole rejection remains
`semantic:mean_weed_fraction_in_range`; no model, prediction, metric, registered
target, or locked-test input contributed to the decision. The ledger is now
seven rows with SHA-256 `39be2c0d...5f20`.

- The next canonical candidate, index 1, passed the GT-only scout in 323.97
  seconds. It used locked `scene_0004`, all five exact slot seeds, and seven
  allowed botanical assets. Its terminal receipt is `4ca538f3...6170` and its
  canonical GT is `2a3679d6...38f0`.
- The scout measured mean crop fraction 0.086952, mean weed fraction 0.016457,
  crop-free fraction 0.0, and weed-free fraction 0.133333. Three eligible weed
  tracks contributed 6, 6, and 5 observations.
- The unchanged sealed full renderer accepted the same candidate in 2,310.18
  seconds. All six top-level non-model gates passed; all 30 replay frames were
  decoded-pixel exact. The terminal receipt SHA-256 is
  `12292c7753dbe52e2b1e749dfb4f349d7870bc3857b33def9a52b22af4b9219c`.
- Scout and full execution matched exactly on canonical GT, source scene-graph
  identity, semantic audit, temporal audit, native dimensions, source-track
  count, and eligible-weed-track count. Both arms share byte-identical GT.
- Ideal and degraded RGB differ in every frame; minimum changed-pixel fraction
  is 0.709006 and mean RGB RMSE is 10.802439. Independent ffprobe/ffmpeg checks
  decoded both 2048-square arm videos and the 2048x1024 side-by-side video as
  exactly 30 frames at 15 Hz.
- A second full-render invocation returned
  `SKIP_EXISTING_PASS_FULL_PAIR_PREOUTCOME_SYNTHETIC_ONLY` in 0.052 seconds with
  the same terminal receipt. No interrupted staging directory remains and the
  render state is 2 complete / 94 pending.

## Bounded calibration batch execution

A separately locked orchestration layer now wraps the unchanged scout and full
renderer. It accepts only explicit contiguous canonical calibration slots,
requires a positive `max-new-pairs` bound, atomically publishes an immutable
batch intent before work, and writes its terminal receipt only after exactly
that many new pairs exist. Repeating an exact completed request returns its
existing receipt and never advances to the next slot.

- Batch implementation SHA-256: `0afadc98...8769`; execution-lock SHA-256:
  `c9e46aee...7bf3`. The sealed scout/full implementation and lock hashes remain
  unchanged.
- The exact request targeted only `calibration_c000_r02` with
  `max-new-pairs=1`. Intent SHA-256 is `e562028d...d051`; batch receipt SHA-256
  is `c5b9cfaa...eea5`.
- Candidate 0 passed the GT-only scout on the first attempt in 386.86 seconds;
  no r02 rejection entered the ledger. Mean crop fraction was 0.079613, mean
  weed fraction 0.021210, and weed-free fraction 0.0. Five eligible weed
  tracks contributed 5, 11, 11, 10, and 8 observations.
- The unchanged full renderer accepted the same candidate in 2,747.90 seconds;
  the whole bounded batch took 3,135.73 seconds. Terminal full-pair receipt
  SHA-256 is `d1244523...4a93`, with canonical GT `41902db5...2d88`.
- Scout and full results matched exactly on canonical GT, source scene-graph,
  semantic audit, temporal audit, dimensions, source-track count, and eligible
  track count. All six full gates and all 30 deterministic replay pixel checks
  passed. Both arms share byte-identical GT.
- Ideal/degraded RGB differ in every frame; minimum changed-pixel fraction is
  0.707854 and mean RMSE is 10.700901. Independent full decode verified both
  2048-square arm videos and the 2048x1024 side-by-side video at exactly 30
  frames, 15 Hz, and 2 seconds.
- Repeating the exact batch returned
  `SKIP_EXISTING_PASS_CALIBRATION_BATCH_PREOUTCOME_SYNTHETIC_ONLY` in 0.101
  seconds with the same receipt. No `calibration_c000_r03` artifact was made;
  state is 3 complete / 93 pending with no interrupted staging.

## Two-slot calibration batch and zero-weed recovery

The exact request targeting `calibration_c000_r03` and
`calibration_c001_r00` with `max-new-pairs=2` published only those two slots.
Its immutable intent SHA-256 is `7c161031...b7ae`, request identity is
`9e163cf0...9d8`, and terminal batch receipt SHA-256 is
`1db8549a...5da2`. The terminal successful invocation took 6,941.83 seconds,
loaded no model, made zero inference calls, and did not access locked-test
outcomes.

- For `calibration_c000_r03`, candidate 0 failed only the frozen mean-crop
  semantic gate. Candidate 1 contained exactly seven crop tracks and zero weed
  tracks; the locked botanical validator failed closed with its exact
  `Too few source weed tracks: 0` error before the ordinary scout could publish
  a decision.
- A narrow, separately sealed source-cardinality recovery admitted only that
  exact validator error and could reject only
  `eligibility:source_weed_track_present`. Its implementation SHA-256 is
  `85a20e86...06fa`, execution-lock SHA-256 is `0d9ffc13...eab2`, and terminal
  receipt SHA-256 is `5ba5a931...813`. It verified 30 native 2048-square GT
  frames, the full track-frame grid, exact source template and all five seed
  bindings, then removed 8,183,226 bytes of bounded bulk payload. It has no
  acceptance authority and did not change the sealed scout, full renderer, or
  batch hashes.
- Candidate 2 then failed only the frozen mean-weed semantic gate. Candidate 3
  passed the GT-only scout and the unchanged full renderer. Its canonical GT
  is `261f8d04...ef0`, seven eligible weed tracks contribute observations, and
  all six full pair gates passed. Ideal/degraded RGB differ in every frame;
  minimum changed-pixel fraction is 0.710856 and mean RMSE is 5.904249.
- For `calibration_c001_r00`, candidates 0 and 1 failed only the frozen
  mean-crop and mean-weed gates respectively. Candidate 2 passed the scout and
  unchanged full renderer with canonical GT `b9c0527c...ddde`, three eligible
  weed tracks, all six full gates, a 0.703353 minimum changed-pixel fraction,
  and 4.169382 mean RGB RMSE.
- Scout/full equivalence is exact for both accepted candidates on candidate
  identity, canonical GT, source scene graph, semantic and temporal audits,
  native dimensions, source-track count, eligible-track count, and all five
  seed bindings. Within each pair the two sequence records share all 30
  semantic hashes, track hashes, and track metadata rows.
- Independent full decode verified each pair's ideal and degraded 2048-square
  videos plus its 2048x1024 side-by-side video as exactly 30 frames at 15 Hz
  and 2 seconds. Both preoutcome contact sheets were visually inspected as
  readable and prediction-free.
- The canonical rejection ledger now has 12 rows, SHA-256
  `4e83feb3...05d3`; all rows state that model/outcome inputs were unused. An
  exact repeat returned `SKIP_EXISTING_PASS_CALIBRATION_BATCH_PREOUTCOME_SYNTHETIC_ONLY`
  in 0.093 seconds with the same batch receipt. No next-slot artifact or
  interrupted staging remains, so the bounded stop is 5 complete / 91 pending.

## Four-slot cross-cell calibration batch

The exact batch targeting `calibration_c001_r01`, `calibration_c001_r02`,
`calibration_c001_r03`, and `calibration_c002_r00` with `max-new-pairs=4`
published exactly those four slots and stopped at 9 complete / 87 pending. Its
request identity is `52db7a3d...ad560`, immutable intent file SHA-256 is
`4b350ec0...3faf`, and terminal batch receipt SHA-256 is
`dc876f4a...f058f`. The terminal successful invocation took 10,498.62 seconds,
recovered the already published first target from the same intent, loaded no
model, made zero inference calls, and did not access locked-test outcomes.

- `calibration_c001_r01` rejected candidates 0 through 8 in roster order on
  only the frozen weed-free, mean-crop, and mean-weed semantic gates.
  Candidate 9 passed scout and full render with canonical GT
  `dd2f5675...f9adf`, 20 source tracks, nine eligible weed tracks, and all six
  full gates.
- `calibration_c001_r02` rejected candidates 0 and 1 on mean-weed and mean-crop
  respectively. Candidate 2 produced the exact locked validator failure
  `Too few source weed tracks: 0`; the separately sealed recovery recorded only
  `eligibility:source_weed_track_present` and removed 8,132,868 bytes of its
  bounded bulk payload. Candidate 3 then passed scout and full render with
  canonical GT `a751a91f...34bc`, 19 source tracks, seven eligible weed tracks,
  and all six full gates.
- `calibration_c001_r03` rejected candidates 0 and 1 only on mean crop.
  Candidate 2 passed with canonical GT `cdb81ebf...3111`, 26 source tracks,
  twelve eligible weed tracks, and all six full gates.
- `calibration_c002_r00` crossed the frozen cell boundary and passed candidate
  0 directly with canonical GT `5299cbc7...a219`, 21 source tracks, eight
  eligible weed tracks, and all six full gates.
- Scout/full equivalence is exact for every accepted candidate on candidate
  identity, canonical GT, scene graph, semantic/temporal audits, native
  dimensions, source/eligible track counts, and all five seed bindings. Within
  every pair, both arms share all 30 semantic hashes, track hashes, and track
  metadata rows. Independent byte checks matched all 480 unique files recorded
  by the four sequence manifests.
- All four deterministic replays matched decoded RGB pixels in all 30 frames;
  ideal/degraded RGB differed in every frame. Minimum changed-pixel fractions
  were 0.606039, 0.713716, 0.718035, and 0.708852 respectively.
- Independent ffprobe plus full ffmpeg decode validated all twelve videos:
  arm videos are 2048-square, side-by-side videos are 2048x1024, and every
  video has exactly 30 frames at 15 Hz for two seconds. All four preoutcome
  contact sheets were visually inspected as readable and prediction-free.
- The rejection ledger now has 26 rows, SHA-256 `3a3675ce...f61b`; the batch's
  fourteen new rows exactly equal the ledger suffix and every row records
  `model_or_outcome_inputs_used: false`. Bounded cleanup removed 199,185,117
  bytes across those fourteen rejected candidates.
- Repeating the exact batch returned
  `SKIP_EXISTING_PASS_CALIBRATION_BATCH_PREOUTCOME_SYNTHETIC_ONLY` in at most
  0.3 seconds with the same receipt. No `calibration_c002_r01` artifact,
  locked-test pair directory, prediction/threshold/metric output, or interrupted
  staging directory exists.
- The four accepted pair directories occupy 3,893,650,024 bytes. Full preflight
  observed 333,460,840,448 free bytes, leaving 123,460,840,448 bytes beyond the
  frozen 180 GB requirement plus 30 GB reserve. The measured candidate-stage
  work was 17,638.67 seconds (4.900 hours); this is evidence for batching, not a
  promise for later candidate distributions.

The next scaling step is one explicit eight-slot calibration batch over
`calibration_c002_r01`, `calibration_c002_r02`, `calibration_c002_r03`,
`calibration_c003_r00`, `calibration_c003_r01`, `calibration_c003_r02`,
`calibration_c003_r03`, and `calibration_c004_r00` with
`max-new-pairs=8`. It remains calibration-only, explicit, atomically resumable,
and outcome-blind while advancing the published state toward 17/96.

Pair publication is same-filesystem atomic and accepted outputs are never
overwritten. This evidence is synthetic-only and grants no field, product, or
chemical authorization.
