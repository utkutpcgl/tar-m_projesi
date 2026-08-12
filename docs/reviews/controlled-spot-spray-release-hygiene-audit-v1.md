# Controlled Spot-Spray Release Hygiene Audit V1

Status: `READ_ONLY_POINT_IN_TIME_AUDIT` — this is not release authorization and
contains no physical, field, dry-marker, or chemical-fire `GO` claim.

Audit window: `2026-08-12T11:37:05+03:00` through
`2026-08-12T11:45:22+03:00`. Repository:
`/home/ankaref/utku/tarım_projesi`; branch: `main`; audited base:
`dfd4fad4c5675cd1d23b484ce465d1616460c095`. Portfolio lane:
`release-hygiene-audit-v1`, run
`goal-multi-repeat-release-hygiene-audit-v1-5eb4f4c5fdca`.

Only this audit file was written. No data or cache was deleted or moved; no
process or service was changed; no fetch, commit, push, or GPU workload was
started. Because swap was nearly full, inspection stayed within the repository,
the exact spot-spray paths named by its contracts, and exact spot-spray names in
`/tmp`.

## Release decision summary

- **KEEP / integrate:** the pre-audit worktree contained 42 untracked files,
  516,626 bytes in total. All 42 matched the controller ledger's
  `contract-integration-v1` allowlist; none was unassigned. They are intentional
  contract, implementation, documentation, test, or explicitly synthetic
  fixture artifacts. This audit is the 43rd intentional untracked path and is
  covered by this lane's sole allowlist entry.
- **DELETE only after all lane validation:** three exact `/tmp` outputs are
  superseded fail-closed validation artifacts. Thirteen exact `.pyc` files and
  `.pytest_cache/` are reproducible caches, not evidence. The commands are
  recorded below but were not executed.
- **KEEP / protect:** the tracked report package, compute/capture/pre-real
  results, external report-input directories, synthetic source release, and
  selected 23 MiB foundation checkpoint remain live inputs or linked historical
  evidence. None is a cleanup candidate.
- **RECHECK before release:** two sibling lanes were active during this
  snapshot. The integration lane may add its two remaining allowlisted files;
  the report lane may update its tracked builder, tests, reports, root
  navigation, and plan. Therefore this snapshot cannot be used as a final
  staging list without the bounded recheck below.
- **Remote:** local `HEAD`, local `main`, cached `origin/main`, and a fresh
  non-mutating `git ls-remote origin refs/heads/main` all resolved to
  `dfd4fad4c5675cd1d23b484ce465d1616460c095`; local committed divergence was
  `0 ahead / 0 behind`. The untracked work means the release itself is not yet
  present on the remote.
- **Services:** an unrelated VLLM reranker owns the only reported GPU compute
  allocation and Ollama is active with no loaded model. They were observed and
  left untouched.

A closure recheck at `2026-08-12T11:45:22+03:00` found 44 dirty paths and zero
paths outside the portfolio ledger: the original 42 integration-lane files,
this audit, and one expected tracked report-lane modification at
`scripts/build_controlled_spot_spray_poc_report_v1.py`. That report edit landed
after the pre-audit manifest snapshot and confirms why a manager recheck after
both sibling handoffs is mandatory.

## Command-backed machine snapshot

| Check | Observed result | Release meaning |
|---|---:|---|
| `free -h` | RAM 125 GiB total, 94 GiB available; swap 7.9/8.0 GiB used | Avoid broad home/data scans; no evidence of RAM pressure that justifies service changes. |
| `df -hT <repo>` | root ext4 913 GiB, 683 GiB used, 184 GiB available, 79% | No urgent repository-disk cleanup. |
| `df -hT <known-data-root>` | data ext4 458 GiB, 115 GiB used, 320 GiB available, 27% | No reason to delete protected data evidence. |
| bounded `du -sh` | `.git` 70 MiB; `.venv` 290 MiB; `configs` 1.3 MiB; `docs` 42 MiB; `scripts` 7.6 MiB; `tests` 2.0 MiB | Environment and Git internals are not release artifacts or cleanup targets. |
| `git status --porcelain=v2 --branch -uall` | `main`, upstream `origin/main`, `+0 -0`; 42 `?` records; no tracked `1`, `2`, `u`, or deletion records | Point-in-time worktree delta was untracked-only. |
| ledger coverage script | 42/42 untracked files covered, 0 unassigned | Preserve and integrate rather than clean. |
| untracked manifest | 516,626 bytes; path+size+SHA-256 manifest digest `e06d4b9b7becbf6d7690f04baaaea8052f27f78f5ff6eb6bf8d2c03a89fd59db` | Recompute after sibling lanes finish; this digest authenticates only the pre-audit snapshot below. |
| `git rev-list --left-right --count main...origin/main` | `0  0` | Cached remote-tracking divergence was zero. |
| `git ls-remote --exit-code origin refs/heads/main` | `dfd4fad4… refs/heads/main` | Current remote query matched without fetching or changing refs. |

The untracked manifest was formed from sorted
`git ls-files --others --exclude-standard -z` results. Each manifest line is
`SHA256␠␠byte_count␠␠repo_relative_path\n`, then the complete UTF-8 manifest is
SHA-256 hashed. The following groups account for every one of its 42 paths:

| Intentional group | Files | Bytes | Required action |
|---|---:|---:|---|
| Contract configs | 5 | 34,179 | Keep; integration validation and stage. |
| Operator/contract docs | 3 | 44,033 | Keep; integration validation and stage. |
| Evaluators/trainers | 4 | 264,725 | Keep; CPU validation and stage. |
| Capture synthetic fixtures | 12 | 12,389 | Keep; fixture-only regression evidence. |
| Rig synthetic fixtures | 3 | 19,554 | Keep; fixture-only regression evidence. |
| Model synthetic fixtures | 11 | 41,991 | Keep; fixture-only regression evidence. |
| Focused tests | 4 | 99,755 | Keep; run and stage. |

### Exact intentional untracked paths at snapshot

All paths below belonged to `contract-integration-v1`; the use of “synthetic”
is material and must remain visible. The tiny `.jpg` files are test fixtures,
not collected field images.

```text
configs/benchmark/spot_spray_target_rig_action_eval_v1.yaml
configs/benchmark/spot_spray_target_rig_finetune_v1.yaml
configs/data/spot_spray_capture_audit_v1.yaml
configs/data/spot_spray_capture_manifest_v1.schema.json
configs/deploy/spot_spray_rig_acceptance_v1.yaml
docs/SPOT_SPRAY_DATA_CAPTURE_AND_ANNOTATION_V1.md
docs/SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md
docs/SPOT_SPRAY_TARGET_RIG_MODEL_PIPELINE_V1.md
scripts/audit_spot_spray_capture_v1.py
scripts/evaluate_spot_spray_rig_acceptance_v1.py
scripts/evaluate_spot_spray_target_rig_action_v1.py
scripts/train_spot_spray_target_rig_finetune_v1.py
tests/fixtures/spot_spray_capture_v1/adjacent_leakage_synthetic.json
tests/fixtures/spot_spray_capture_v1/images/frame_a1_000.jpg
tests/fixtures/spot_spray_capture_v1/images/frame_a1_001.jpg
tests/fixtures/spot_spray_capture_v1/images/frame_a2_000.jpg
tests/fixtures/spot_spray_capture_v1/images/frame_b1_000.jpg
tests/fixtures/spot_spray_capture_v1/images/frame_c1_000.jpg
tests/fixtures/spot_spray_capture_v1/insufficient_coverage_synthetic.json
tests/fixtures/spot_spray_capture_v1/invalid_polygon_synthetic.json
tests/fixtures/spot_spray_capture_v1/missing_metadata_synthetic.json
tests/fixtures/spot_spray_capture_v1/rig_acceptance_synthetic.json
tests/fixtures/spot_spray_capture_v1/track_identity_conflict_synthetic.json
tests/fixtures/spot_spray_capture_v1/valid_complete_synthetic.json
tests/fixtures/spot_spray_rig_acceptance_v1/synthetic_fail.yaml
tests/fixtures/spot_spray_rig_acceptance_v1/synthetic_not_measured.yaml
tests/fixtures/spot_spray_rig_acceptance_v1/synthetic_pass.yaml
tests/fixtures/spot_spray_target_rig_model_v1/README.md
tests/fixtures/spot_spray_target_rig_model_v1/capture_audit_result_v1.json
tests/fixtures/spot_spray_target_rig_model_v1/capture_manifest_v1.json
tests/fixtures/spot_spray_target_rig_model_v1/capture_manifest_v1.jsonl
tests/fixtures/spot_spray_target_rig_model_v1/finetune_capture_audit_v1.json
tests/fixtures/spot_spray_target_rig_model_v1/finetune_capture_manifest_v1.json
tests/fixtures/spot_spray_target_rig_model_v1/finetune_images/test_secret.jpg
tests/fixtures/spot_spray_target_rig_model_v1/finetune_images/train_known.jpg
tests/fixtures/spot_spray_target_rig_model_v1/finetune_images/train_unknown.jpg
tests/fixtures/spot_spray_target_rig_model_v1/finetune_images/validation_known.jpg
tests/fixtures/spot_spray_target_rig_model_v1/predictions_v1.jsonl
tests/test_audit_spot_spray_capture_v1.py
tests/test_evaluate_spot_spray_rig_acceptance_v1.py
tests/test_evaluate_spot_spray_target_rig_action_v1.py
tests/test_train_spot_spray_target_rig_finetune_v1.py
```

This audit itself is intentional and must be kept:

```text
docs/reviews/controlled-spot-spray-release-hygiene-audit-v1.md
```

At snapshot time these integration-lane allowlisted paths were not yet present;
their absence is not deletion authorization:

```text
docs/SPOT_SPRAY_INTEGRATED_CONTRACT_RELEASE_V1.md
tests/test_spot_spray_integrated_contract_v1.py
```

The active report lane had no dirty path in the snapshot. It is authorized to
update only its ledger paths, including
`scripts/build_controlled_spot_spray_poc_report_v1.py`, its focused test,
`docs/results/kontrollu_spot_spray_poc_v1/**`, `docs/results/README.md`,
`README.md`, and `plan.md`. Re-audit those exact paths after its handoff.

## Protected evidence and outputs

The tracked report package contained 11 files and 5,810,694 bytes. Its
`report_receipt.json` listed ten other files; all ten existed and all ten
SHA-256 values matched. It is an active report-lane output, not obsolete.

The following tracked inputs are referenced by source/config/docs and must
remain. Their audit-time hashes are recorded to distinguish them from temporary
copies:

| Path | SHA-256 | Why protected |
|---|---|---|
| `docs/results/spot_spray_deploy_compute_summary_v1.json` | `b03898f35891e304631bfb410089aefdea7f4c5e339f4a9ccef27dc947d28804` | Frozen compute input. |
| `docs/results/spot_spray_deploy_compute_halo_summary_v1.json` | `945c1e43ed9e672d58cc44a57a6a046f202bb285a43b9f385751e297e22de4e7` | Frozen halo-throughput input. |
| `docs/results/controlled_capture_optimization_v2.json` | `0808c68d40285ff3eba5fb3d13603bc42c12c16d9bacc4fd87470a3c26eafbc8` | Generated capture decision evidence. |
| `docs/results/pre_real_data_ceiling_result_v1.json` | `12648329337a392572b7e697ca0b359f60ef62af34765e37c46e2574e3ea8878` | Target-model decision input. |
| `docs/results/pre_real_data_ceiling_result_v1.md` | `508f73f823bff58e3674756283478fd52f033364633d5e538e46ef4283d93ba2` | Human-readable paired evidence. |
| `docs/results/SPOT_SPRAY_MODEL_KARARI_V2.pdf` | `7ded4f85ae3ab46f438aced6d17631df31360cda3381737ef944d3263af0613c` | Still linked from README/docs; historical decision, not superseded trash. |
| `docs/results/DETECTION_SPOT_SPRAY_BENCHMARK_V1.pdf` | `1dda1497952b6bbf65b35b1356f97c704cf2f588efe768777e1d5608beb54cdc` | Still linked from README/docs; historical benchmark. |

Only contract-named paths on the dedicated data disk were measured; no broad
data-tree scan was performed:

| Protected path | Footprint | Role |
|---|---:|---|
| `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/phenobench_cropcraft_deploy_action_ab_v1` | 272 KiB | Report metrics input. |
| `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/cropcraft_deploy_synthetic_diagnostic_v1` | 2.9 MiB | Synthetic diagnostic and gallery input. |
| `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/sugarbeets2016_yolo_segment_external_v1` | 11 MiB | External OOD metrics input. |
| `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/phenobench_cropcraft_deploy_ab_v1` | 3.6 GiB | Dataset receipt plus report evidence. |
| `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/cropcraft_deploy_segment_proxy_v12` | 136 MiB | Synthetic dataset receipt/input. |
| `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/synthetic/cropcraft/deploy_constrained_pilot_v12` | 62 MiB | Frozen synthetic release input. |
| `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/pre_real_data_ceiling_action_diagnostics_v1` | 4.5 MiB | Pre-real model diagnostics. |
| `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/pre_real_data_ceiling_gallery_v1` | 556 KiB | Selected-model gallery and receipt. |
| `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/pre_real_data_ceiling_robot_native_train_v1/yolo26s_seg_real1407_rose80_native1024_seed41_e8/weights/last.pt` | 23 MiB | Selected foundation checkpoint; SHA-256 matched `3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100`. |

Four ignored `.orig` files dated July 30–31 were observed under `configs/` and
`src/agri_seg/`. They predate this portfolio and are not attributable to this
work. Do not delete them under this release; owner review is required. The
ignored `.codex/`, simulation, environment, and unrelated cache/data trees are
also outside this cleanup boundary.

## Exact removable artifacts — not deleted by this audit

### Superseded fail-closed temporary outputs

| Exact path | Size | Evidence for removability |
|---|---:|---|
| `/tmp/spot_spray_target_rig_not_ready.json` | 648 B | JSON status `NOT_READY`; `fail_closed=true`; offline and chemical GO false; SHA-256 `e1676e56db8a8e1f039ac08d3222c8441e83354e8418a750b3666c7343a667a9`. |
| `/tmp/spot_spray_action_pass4.agpYKC.json` | 30,630 B | JSON status `FIXTURE_ONLY`; offline, field, and chemical GO false; SHA-256 `5002ed0830751af5ad4b585fdf8208e7e6e59bf4082bf15400ef81a10d809ec7`. |
| `/tmp/spot_spray_pass4_validate.6hUPPb` | 12,126 apparent B / 80 KiB allocated | Eleven-file/symlink manifest SHA-256 `274efc459dbd0ab5350fc88643c314a2d39af004cf5a4d4dcf58d9681f730b5a`; receipts are `NOT_READY`, `FIXTURE_ONLY`, `FIXTURE_ONLY_DRY_RUN`, or `NOT_PRODUCED_DRY_RUN`; `training_executed=false`; its two image entries are symlinks to repository synthetic fixtures. |

No `/tmp/spot_spray_target_rig_finetune_fixture` output existed. The real
fine-tune config keeps `capture_manifest_json`, `data_root`, and
`derived_output_directory` null; no real training output was identified or
authorized for cleanup.

### Reproducible cache

`.pytest_cache/` was 45,733 apparent bytes (76 KiB allocated) and is ignored by
`.gitignore`. Delete it only after the final test run, because live lanes may
still use/update it.

The following 13 ignored Python cache files total 780,029 bytes. They correspond
exactly to current portfolio scripts/tests and are reproducible from source.
Their path+size+SHA-256 manifest digest was
`6f58bc57a05254d2397776afa46fd01e39c70453fd725164a5e456096b98c1f7`.

```text
scripts/__pycache__/audit_spot_spray_capture_v1.cpython-312.pyc
scripts/__pycache__/evaluate_spot_spray_rig_acceptance_v1.cpython-312.pyc
scripts/__pycache__/evaluate_spot_spray_target_rig_action_v1.cpython-312.pyc
scripts/__pycache__/train_spot_spray_target_rig_finetune_v1.cpython-312.pyc
scripts/__pycache__/build_controlled_spot_spray_poc_report_v1.cpython-312.pyc
tests/__pycache__/test_audit_spot_spray_capture_v1.cpython-312-pytest-8.4.2.pyc
tests/__pycache__/test_evaluate_spot_spray_rig_acceptance_v1.cpython-312.pyc
tests/__pycache__/test_evaluate_spot_spray_rig_acceptance_v1.cpython-312-pytest-8.4.2.pyc
tests/__pycache__/test_evaluate_spot_spray_target_rig_action_v1.cpython-312.pyc
tests/__pycache__/test_evaluate_spot_spray_target_rig_action_v1.cpython-312-pytest-8.4.2.pyc
tests/__pycache__/test_train_spot_spray_target_rig_finetune_v1.cpython-312-pytest-8.4.2.pyc
tests/__pycache__/test_build_controlled_spot_spray_poc_report_v1.cpython-312.pyc
tests/__pycache__/test_build_controlled_spot_spray_poc_report_v1.cpython-312-pytest-8.4.2.pyc
```

No persistent superseded report output was proven safe to remove. In
particular, do not treat the current report PDFs, historical detection/model
decision PDFs, frozen JSONs, fixtures, or data-disk inputs as cache.

## GPU and unrelated service snapshot — preserve

At the snapshot, `nvidia-smi` reported one RTX 3090 (driver `580.159.04`),
24,576 MiB total, 7,331 MiB used, 16,785 MiB free, 4% utilization, 54 °C, and
P8. The only reported compute allocation was PID `3804985`,
`VLLM::EngineCore`, 7,158 MiB. Its parent was PID `3803177`, a root-owned VLLM
reranker server started `2026-07-20T17:38:13+03:00`, configured for
`dolfsai/Qwen3-Reranker-4B-seq-cls-vllm-W4A16_ASYM`, sleep mode, and port 8000.

System Ollama was active as PID `4042303`, user `ollama`, started
`2026-06-30T15:03:41+03:00`. `GET http://127.0.0.1:11434/api/ps` returned an
empty `models` list. The user-level Ollama unit was inactive. Read-only socket
inspection saw listeners on 11434, 8001, and 8080; it did not attribute the
latter two and did not show 8000. That mismatch is a recheck item, not authority
to diagnose, unload, kill, restart, or reclaim anything. No service or GPU
state was altered.

Before any later GPU window, the manager should repeat the same read-only
process/GPU checks and coordinate with the existing service owners. This audit
does not authorize a GPU job.

## Exact manager action sequence

1. Wait for both active sibling lanes to hand off. Then take a new bounded
   status and remote snapshot from the repository root:

   ```bash
   git status --short --branch --untracked-files=all
   git diff --check
   git rev-list --left-right --count main...origin/main
   git ls-remote --exit-code origin refs/heads/main
   ```

2. Compare every dirty path with the portfolio ledger. Expect this audit, the
   42 paths above, the integration lane's two possible additions, and only the
   report lane's exact allowed paths. Stop on any unassigned path. Do not use
   `git clean`, broad recursive deletion, or a wildcard staging command.

3. Run the manager's integrated CPU/report validation and inspect regenerated
   PDF/text/receipt outputs. Recheck that synthetic/FIXTURE_ONLY evidence still
   cannot produce physical READY or any chemical-fire permission.

4. Only after that validation, optionally remove the three exact temporary
   targets and exact caches. Reconfirm each target with `stat`/`find` first.
   The following commands are recommendations, **not commands executed by this
   audit**:

   ```bash
   rm -f -- /tmp/spot_spray_target_rig_not_ready.json
   rm -f -- /tmp/spot_spray_action_pass4.agpYKC.json
   rm -rf -- /tmp/spot_spray_pass4_validate.6hUPPb
   rm -rf -- /home/ankaref/utku/tarım_projesi/.pytest_cache
   rm -f -- /home/ankaref/utku/tarım_projesi/scripts/__pycache__/audit_spot_spray_capture_v1.cpython-312.pyc
   rm -f -- /home/ankaref/utku/tarım_projesi/scripts/__pycache__/evaluate_spot_spray_rig_acceptance_v1.cpython-312.pyc
   rm -f -- /home/ankaref/utku/tarım_projesi/scripts/__pycache__/evaluate_spot_spray_target_rig_action_v1.cpython-312.pyc
   rm -f -- /home/ankaref/utku/tarım_projesi/scripts/__pycache__/train_spot_spray_target_rig_finetune_v1.cpython-312.pyc
   rm -f -- /home/ankaref/utku/tarım_projesi/scripts/__pycache__/build_controlled_spot_spray_poc_report_v1.cpython-312.pyc
   rm -f -- /home/ankaref/utku/tarım_projesi/tests/__pycache__/test_audit_spot_spray_capture_v1.cpython-312-pytest-8.4.2.pyc
   rm -f -- /home/ankaref/utku/tarım_projesi/tests/__pycache__/test_evaluate_spot_spray_rig_acceptance_v1.cpython-312.pyc
   rm -f -- /home/ankaref/utku/tarım_projesi/tests/__pycache__/test_evaluate_spot_spray_rig_acceptance_v1.cpython-312-pytest-8.4.2.pyc
   rm -f -- /home/ankaref/utku/tarım_projesi/tests/__pycache__/test_evaluate_spot_spray_target_rig_action_v1.cpython-312.pyc
   rm -f -- /home/ankaref/utku/tarım_projesi/tests/__pycache__/test_evaluate_spot_spray_target_rig_action_v1.cpython-312-pytest-8.4.2.pyc
   rm -f -- /home/ankaref/utku/tarım_projesi/tests/__pycache__/test_train_spot_spray_target_rig_finetune_v1.cpython-312-pytest-8.4.2.pyc
   rm -f -- /home/ankaref/utku/tarım_projesi/tests/__pycache__/test_build_controlled_spot_spray_poc_report_v1.cpython-312.pyc
   rm -f -- /home/ankaref/utku/tarım_projesi/tests/__pycache__/test_build_controlled_spot_spray_poc_report_v1.cpython-312-pytest-8.4.2.pyc
   ```

   Newly generated integration/report `.pyc` files should be listed and
   reviewed explicitly before removal; they are not covered by the frozen list
   above.

5. Re-run `git status --ignored --short` only for the exact cache paths and
   `git status --short --branch --untracked-files=all` for release paths. Stage
   only ledger-authorized source/config/test/docs/report artifacts, inspect
   `git diff --cached --name-status` and `git diff --cached --check`, then let
   the manager own the single release commit and `git push origin main`.

## Residual integration risks

- This is a point-in-time record while two sibling lanes were active; the final
  dirty-set and report fingerprint must be recomputed after their handoffs.
- The 42-file manifest digest is invalidated by any legitimate integration-lane
  edit; use it to detect/understand drift, not to reject an independently
  validated successor artifact.
- High swap use remains an operational constraint even though available RAM is
  ample. Broad data/home scans and opportunistic service restarts add risk
  without release value.
- The only deletion candidates proven here reclaim roughly one MiB. Large
  data-disk directories are live evidence inputs and disk capacity is healthy;
  deleting them would create far more risk than value.
- Exact manager validation is required before cleanup, staging, commit, or
  push.
