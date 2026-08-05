#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
test_root=$(mktemp -d)
cleanup() {
  if [[ -n "${test_root:-}" && -d "$test_root" && "$test_root" == /tmp/* ]]; then
    rm -rf -- "$test_root"
  fi
}
trap cleanup EXIT

real_images=(
  /bin/ls /bin/cp /bin/mv /bin/rm /bin/sed
  /bin/awk /bin/grep /bin/bash /bin/sh /bin/cat
  /bin/date /bin/echo /bin/true /bin/false /bin/pwd
  /bin/mkdir /bin/rmdir /bin/sleep /bin/touch /bin/chmod
)
synthetic_images=(
  /bin/chown /bin/ln /bin/readlink /bin/realpath /bin/sha256sum
  /bin/md5sum /bin/sort /bin/uniq /bin/head /bin/tail
  /bin/cut /bin/tr /bin/wc /bin/find /bin/xargs
  /bin/env /bin/id /bin/whoami /bin/dirname /bin/basename
)
hard_images=(/bin/stat /bin/df)
printf '%s\n' "${real_images[@]}" > "$test_root/val.txt"

write_standard_condition() {
  local condition=$1
  local synthetic_count=$2
  local manifest="$test_root/${condition}.txt"
  local composition="$test_root/${condition}.csv"
  local yaml="$test_root/${condition}.yaml"

  printf '%s\n' "${real_images[@]}" > "$manifest"
  if (( synthetic_count > 0 )); then
    printf '%s\n' "${synthetic_images[@]:0:synthetic_count}" >> "$manifest"
  fi
  {
    printf 'image_path,source,partition\n'
    for path in "${real_images[@]}"; do
      printf '%s,real,real\n' "$path"
    done
    for path in "${synthetic_images[@]:0:synthetic_count}"; do
      printf '%s,synthetic,standard\n' "$path"
    done
  } > "$composition"
  printf 'train: %s\nval: %s\nnames:\n  0: rfid_tag\n  1: concrete_sample\n' \
    "$manifest" "$test_root/val.txt" > "$yaml"
  python3 "$script_dir/validate_ablation_composition.py" \
    --condition "$condition" \
    --train-manifest "$manifest" \
    --composition-csv "$composition" > "$test_root/${condition}.audit.json"
}

write_standard_condition R_ONLY 0
write_standard_condition R_S025 5
write_standard_condition R_S050 10
write_standard_condition R_S100 20

matrix_lock="$test_root/standard_matrix_lock.json"
python3 "$script_dir/freeze_standard_matrix.py" \
  --r-only "$test_root/R_ONLY.csv" \
  --r-s025 "$test_root/R_S025.csv" \
  --r-s050 "$test_root/R_S050.csv" \
  --r-s100 "$test_root/R_S100.csv" \
  --output "$matrix_lock" >/dev/null

bad_s050="$test_root/R_S050_non_nested.csv"
{
  printf 'image_path,source,partition\n'
  for path in "${real_images[@]}"; do
    printf '%s,real,real\n' "$path"
  done
  for path in "${synthetic_images[@]:1:10}"; do
    printf '%s,synthetic,standard\n' "$path"
  done
} > "$bad_s050"
if python3 "$script_dir/freeze_standard_matrix.py" \
  --r-only "$test_root/R_ONLY.csv" \
  --r-s025 "$test_root/R_S025.csv" \
  --r-s050 "$bad_s050" \
  --r-s100 "$test_root/R_S100.csv" \
  --output "$test_root/invalid_matrix_lock.json" >/dev/null 2>&1; then
  echo "non-nested standard matrix unexpectedly passed" >&2
  exit 1
fi

common_env=(
  EBIS_YOLO_MODEL=/bin/true
  EBIS_YOLO_MODEL_SHA256=0000000000000000000000000000000000000000000000000000000000000000
  EBIS_YOLO_TARGET_UPDATES=120
  EBIS_YOLO_BATCH=5
  EBIS_YOLO_PREFLIGHT_ONLY=1
  EBIS_YOLO_STANDARD_MATRIX_LOCK="$matrix_lock"
)
env "${common_env[@]}" "$script_dir/run_ablation.sh" \
  R_S025 17 "$test_root/R_S025.yaml" "$test_root/R_S025.txt" \
  "$test_root/R_S025.csv" "$test_root/runs" |
  grep -q '^ABLATION_PREFLIGHT_PASS '

mkdir -p "$test_root/runs/contracts"
checkpoint_sha=$(sha256sum /bin/true | awk '{print $1}')
metrics_csv="$test_root/standard_val_metrics.csv"
printf 'condition,seed,rfid_ap50_95,rfid_recall,run_contract\n' > "$metrics_csv"
for condition in R_ONLY R_S025 R_S050 R_S100; do
  case "$condition" in
    R_ONLY)
      aps=(0.40 0.41 0.39)
      recalls=(0.60 0.61 0.59)
      ;;
    R_S025)
      aps=(0.42 0.43 0.41)
      recalls=(0.62 0.63 0.61)
      ;;
    R_S050)
      aps=(0.50 0.51 0.49)
      recalls=(0.70 0.71 0.69)
      ;;
    R_S100)
      aps=(0.45 0.46 0.44)
      recalls=(0.64 0.65 0.63)
      ;;
  esac
  composition_audit="$test_root/${condition}.audit.json"
  composition_audit_sha=$(sha256sum "$composition_audit" | awk '{print $1}')
  index=0
  for seed in 17 29 43; do
    contract="$test_root/runs/contracts/${condition}_seed${seed}.json"
    printf '{\n  "status": "PASS",\n  "condition": "%s",\n  "seed": %s,\n  "target_optimizer_updates": 120,\n  "composition_audit": "%s",\n  "composition_audit_sha256": "%s",\n  "primary_checkpoint": "/bin/true",\n  "primary_checkpoint_sha256": "%s"\n}\n' \
      "$condition" "$seed" "$composition_audit" "$composition_audit_sha" \
      "$checkpoint_sha" > "$contract"
    printf '%s,%s,%s,%s,%s\n' "$condition" "$seed" \
      "${aps[$index]}" "${recalls[$index]}" "$contract" >> "$metrics_csv"
    index=$((index + 1))
  done
done

selection_ledger="$test_root/sbest_selection.json"
python3 "$script_dir/select_sbest.py" \
  --metrics-csv "$metrics_csv" \
  --matrix-lock "$matrix_lock" \
  --output "$selection_ledger" |
  grep -q '"selected_condition": "R_S050"'

if python3 "$script_dir/select_sbest.py" \
  --verify-ledger "$selection_ledger" \
  --matrix-lock "$matrix_lock" \
  --sbest-composition "$test_root/R_S025.csv" \
  --runs-root "$test_root/runs" >/dev/null 2>&1; then
  echo "non-selected Sbest composition unexpectedly passed" >&2
  exit 1
fi

hard_manifest="$test_root/R_Sbest_HARD.txt"
hard_composition="$test_root/R_Sbest_HARD.csv"
hard_yaml="$test_root/R_Sbest_HARD.yaml"
printf '%s\n' "${real_images[@]}" "${synthetic_images[@]:0:8}" \
  "${hard_images[@]}" > "$hard_manifest"
{
  printf 'image_path,source,partition\n'
  for path in "${real_images[@]}"; do
    printf '%s,real,real\n' "$path"
  done
  for path in "${synthetic_images[@]:0:8}"; do
    printf '%s,synthetic,standard\n' "$path"
  done
  for path in "${hard_images[@]}"; do
    printf '%s,synthetic,hard_occlusion\n' "$path"
  done
} > "$hard_composition"
printf 'train: %s\nval: %s\nnames:\n  0: rfid_tag\n  1: concrete_sample\n' \
  "$hard_manifest" "$test_root/val.txt" > "$hard_yaml"

env "${common_env[@]}" \
  EBIS_YOLO_SBEST_SELECTION="$selection_ledger" \
  EBIS_YOLO_SBEST_COMPOSITION="$test_root/R_S050.csv" \
  "$script_dir/run_ablation.sh" \
  R_Sbest_HARD 43 "$hard_yaml" "$hard_manifest" \
  "$hard_composition" "$test_root/runs" |
  grep -q 'synthetic=10 hard=2'

if python3 "$script_dir/validate_ablation_composition.py" \
  --condition R_Sbest_HARD \
  --train-manifest "$test_root/R_S050.txt" \
  --composition-csv "$test_root/R_S050.csv" \
  --sbest-condition R_S050 \
  --sbest-composition-csv "$test_root/R_S050.csv" >/dev/null 2>&1; then
  echo "invalid hard replacement unexpectedly passed" >&2
  exit 1
fi

if env "${common_env[@]}" "$script_dir/run_ablation.sh" \
  R_B1N 17 "$test_root/R_S025.yaml" "$test_root/R_S025.txt" \
  "$test_root/R_S025.csv" "$test_root/runs" >/dev/null 2>&1; then
  echo "retired condition unexpectedly passed" >&2
  exit 1
fi

echo "YOLO_CONTRACT_SELF_TEST_PASS"
