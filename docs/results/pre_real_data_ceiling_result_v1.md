# Pre-real-data segmentation ceiling — READY_FOR_MANAGER_VALIDATION

CHILD SESSION / RUN / PASS / STRATEGY / STATE: `019ff001-b472-76a3-93bf-4dd2e9838ab6` / `goal-multi-repeat-pre-real-data-ceiling-a56b0ea9e8dc` / `2` / same-checkpoint, same-budget `80 V12 synthetic → 80 native-pixel ROSE robot crops` / `READY_FOR_MANAGER_VALIDATION`.

RESULT: The ROSE native-detail challenger completes the exact matched `8` epochs at batch `3` and displaces the frozen pre-real best under all four declared real-panel rules. At the primary ≥82 px action view, PhenoBench F1 rises `0.7258 → 0.7540` while crop-hit rate falls `0.1132 → 0.1047`; fixed-Pheno-threshold BoniRob F1 rises `0.0536 → 0.0896` while crop-hit falls `0.1217 → 0.1031`. The result is directional: the paired PhenoBench F1-difference interval is `[-0.0136, 0.0710]`, BoniRob is one consumed correlated session, and there is no own-rig holdout. `field_fire_go=false` and every public-panel GO check fails.

The fixed-real-threshold V12 diagnostic exposes the tradeoff: ≥82 px F1 falls `0.6341 → 0.0000` and the challenger attempts no actions. The legacy `0.7576` synthetic-calibrated F1 remains context only. Synthetic weight in the real winner and GO decisions is exactly `0.0`.

FILES OR ARTIFACTS:

- Final challenger: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/pre_real_data_ceiling_robot_native_train_v1/yolo26s_seg_real1407_rose80_native1024_seed41_e8/weights/last.pt` — SHA-256 `3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100`.
- Training receipt / results: `run_receipt.json` SHA-256 `9b45ca71b656e1e988d7cbffcb47a3ba708907562417c16797f7bf45e2cb427e`; `results.csv` SHA-256 `0a3f358c829d1e732913a03b36af097649825fac0494c5899d6e543daca80d52`.
- Diagnostics: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/pre_real_data_ceiling_action_diagnostics_v1/diagnostics.json` SHA-256 `e4b95a08611fee29d79c146d3001f9b0163d053c58519cd1c2d3ed65a0fd17a2`; `summary.json` SHA-256 `470ef715dc000fca8743fc03dfb9de10f1a4d510ab37806aff6753e2b77baf56`.
- Machine-readable compact result: `docs/results/pre_real_data_ceiling_result_v1.json`.

VALIDATION EVIDENCE: Nine scoped tests pass. `results.csv` contains exactly eight completed epoch rows. The epoch-4 resume checkpoint SHA-256 was `2feb7c3d1020a0bac51d8a54966fdd0d458c54802724c2ba5b1d9e4209e8e2c4`, with optimizer state present; same-run resume repeated no completed epoch. The successful final run receipt locks eight epochs, `1487` images/epoch, seed `41`, 1024 px, batch `3`, and the final checkpoint hash. Frozen current-best PhenoBench and BoniRob metrics reproduce exactly. No VLLM/Ollama process was altered or awakened.

Primary ≥82 px comparison:

| Panel | Model | Threshold | Precision | Recall | F1 | Crop hits / attempts | Crop-hit rate | Wilson upper 95% |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| PhenoBench | Current | 0.77 | 0.8239 | 0.6485 | 0.7258 | 18 / 159 | 0.1132 | 0.1718 |
| PhenoBench | ROSE challenger | 0.76 | 0.8198 | 0.6980 | 0.7540 | 18 / 172 | 0.1047 | 0.1593 |
| BoniRob | Current | 0.77 | 0.1376 | 0.0333 | 0.0536 | 23 / 189 | 0.1217 | 0.1760 |
| BoniRob | ROSE challenger | 0.76 | 0.2018 | 0.0576 | 0.0896 | 23 / 223 | 0.1031 | 0.1500 |
| V12 synthetic | Current | 0.77 | 1.0000 | 0.4643 | 0.6341 | 0 / 13 | 0.0000 | 0.2281 |
| V12 synthetic | ROSE challenger | 0.76 | 0.0000 | 0.0000 | 0.0000 | 0 / 0 | 0.0000 | undefined |

Size-stratum F1 / crop-hit-rate traces:

| Panel | Size views (px) | Current F1 | Challenger F1 | Current crop-hit | Challenger crop-hit |
|---|---|---|---|---|---|
| PhenoBench | 0 / 28 / 42 / 56 / 82 | .7798 / .8189 / .8155 / .7995 / .7258 | .7772 / .8257 / .8148 / .8140 / .7540 | .0376 / .0513 / .0623 / .0564 / .1132 | .0340 / .0452 / .0485 / .0541 / .1047 |
| BoniRob | 0 / 42 / 82 | .1478 / .1405 / .0536 | .1292 / .1336 / .0896 | .0825 / .0835 / .1217 | .0709 / .0755 / .1031 |
| V12 synthetic | 0 / 41 / 82 | .7246 / .7356 / .6341 | .1379 / .0714 / .0000 | .0175 / .0000 / .0000 | .0000 / .0000 / no attempts |

The V12 41 px view uses the explicitly declared frozen PhenoBench 42 px validation threshold; the first diagnostic attempt stopped before writing metrics when that compatibility mapping was absent. No target-panel result selected the mapping.

NEXT MOST EFFECTIVE STEP: Freeze this checkpoint as the directional pre-real candidate, then collect and label one independent own-rig field/session safety holdout. Calibrate and evaluate once with crop-hit confidence bounds before any spray authorization; additional model-zoo complexity is lower information than resolving the real rig/domain uncertainty.

INTEGRATION OR BLOCKER RISK: This is not deployment proof. The PhenoBench paired interval crosses zero, BoniRob is not an independent holdout, ROSE has bean rather than sugar-beet crop morphology, fixed-threshold synthetic transfer collapsed, and no independent own-rig safety test exists. The only supported integration action is pre-real checkpoint selection; spray GO remains blocked.
