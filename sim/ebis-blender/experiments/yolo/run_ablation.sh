#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 6 ]]; then
  echo "usage: $0 CONDITION SEED DATA_YAML TRAIN_MANIFEST COMPOSITION_CSV RUNS_ROOT" >&2
  exit 2
fi

condition=$1
seed=$2
data_yaml=$3
train_manifest=$4
composition_csv=$5
runs_root=$6

case "$condition" in
  R_ONLY|R_S025|R_S050|R_S100|R_Sbest_HARD) ;;
  *)
    echo "invalid condition: $condition" >&2
    echo "allowed: R_ONLY R_S025 R_S050 R_S100 R_Sbest_HARD" >&2
    exit 2
    ;;
esac
case "$seed" in
  17|29|43) ;;
  *)
    echo "invalid seed: $seed (allowed: 17, 29, 43)" >&2
    exit 2
    ;;
esac

: "${EBIS_YOLO_MODEL:?set EBIS_YOLO_MODEL to an existing absolute checkpoint path}"
: "${EBIS_YOLO_MODEL_SHA256:?set EBIS_YOLO_MODEL_SHA256 to the pinned checkpoint digest}"
: "${EBIS_YOLO_TARGET_UPDATES:?set one positive integer update budget for every condition}"
: "${EBIS_YOLO_STANDARD_MATRIX_LOCK:?set the immutable Day 11 standard matrix lock}"

model_path=$EBIS_YOLO_MODEL
expected_model_sha=${EBIS_YOLO_MODEL_SHA256,,}
target_updates=$EBIS_YOLO_TARGET_UPDATES
image_size=${EBIS_YOLO_IMGSZ:-960}
batch_size=${EBIS_YOLO_BATCH:-16}
device=${EBIS_YOLO_DEVICE:-0}
optimizer=${EBIS_YOLO_OPTIMIZER:-AdamW}
lr0=${EBIS_YOLO_LR0:-0.001}
lrf=${EBIS_YOLO_LRF:-0.01}
weight_decay=${EBIS_YOLO_WEIGHT_DECAY:-0.0005}

if [[ "$runs_root" != /* ]]; then
  echo "RUNS_ROOT must be absolute: $runs_root" >&2
  exit 2
fi
runs_root=$(realpath -m "$runs_root")
if [[ ! -f "$data_yaml" ]]; then
  echo "missing data yaml: $data_yaml" >&2
  exit 2
fi
if [[ ! -f "$train_manifest" ]]; then
  echo "missing flat train manifest: $train_manifest" >&2
  exit 2
fi
if [[ ! -f "$composition_csv" ]]; then
  echo "missing composition CSV: $composition_csv" >&2
  exit 2
fi
if [[ ! -f "$EBIS_YOLO_STANDARD_MATRIX_LOCK" ]]; then
  echo "missing EBIS_YOLO_STANDARD_MATRIX_LOCK: $EBIS_YOLO_STANDARD_MATRIX_LOCK" >&2
  exit 2
fi
if [[ "$model_path" != /* || ! -f "$model_path" ]]; then
  echo "EBIS_YOLO_MODEL must be an existing absolute checkpoint path: $model_path" >&2
  exit 2
fi
if [[ ! "$expected_model_sha" =~ ^[0-9a-f]{64}$ ]]; then
  echo "EBIS_YOLO_MODEL_SHA256 must be exactly 64 hexadecimal characters" >&2
  exit 2
fi
if [[ ! "$target_updates" =~ ^[1-9][0-9]*$ ]]; then
  echo "EBIS_YOLO_TARGET_UPDATES must be a positive integer" >&2
  exit 2
fi
if [[ ! "$batch_size" =~ ^[1-9][0-9]*$ ]]; then
  echo "EBIS_YOLO_BATCH must be a positive fixed integer; auto batch is forbidden" >&2
  exit 2
fi
if [[ ! "$image_size" =~ ^[1-9][0-9]*$ ]]; then
  echo "EBIS_YOLO_IMGSZ must be a positive integer" >&2
  exit 2
fi
if [[ ! "$device" =~ ^[0-9]+$ ]]; then
  echo "EBIS_YOLO_DEVICE must select exactly one CUDA device index" >&2
  exit 2
fi

data_yaml_abs=$(realpath "$data_yaml")
train_manifest_abs=$(realpath "$train_manifest")
composition_csv_abs=$(realpath "$composition_csv")
matrix_lock_abs=$(realpath "$EBIS_YOLO_STANDARD_MATRIX_LOCK")
matrix_lock_sha=$(sha256sum "$matrix_lock_abs" | awk '{print $1}')
yaml_paths=$(
  python3 - "$data_yaml_abs" <<'PY'
from pathlib import Path
import sys
import yaml

yaml_path = Path(sys.argv[1])
payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
if not isinstance(payload, dict):
    raise SystemExit("data YAML must be a mapping")
if "test" in payload:
    raise SystemExit("sealed test path is forbidden in a training YAML")
names = payload.get("names")
if names != {0: "rfid_tag", 1: "concrete_sample"}:
    raise SystemExit("data YAML names must equal {0: rfid_tag, 1: concrete_sample}")
for key in ("train", "val"):
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"data YAML '{key}' must be one flat manifest path")
    path = Path(value)
    if not path.is_absolute():
        path = yaml_path.parent / path
    print(path.resolve())
PY
)
mapfile -t yaml_path_rows <<<"$yaml_paths"
yaml_train_abs=${yaml_path_rows[0]:-}
yaml_val_abs=${yaml_path_rows[1]:-}
if [[ "$yaml_train_abs" != "$train_manifest_abs" ]]; then
  echo "data YAML train entry does not resolve to TRAIN_MANIFEST" >&2
  echo "yaml: $yaml_train_abs" >&2
  echo "arg:  $train_manifest_abs" >&2
  exit 2
fi
if [[ ! -f "$yaml_val_abs" ]]; then
  echo "data YAML val entry must resolve to an existing flat manifest: $yaml_val_abs" >&2
  exit 2
fi

duplicate_path=$(awk 'NF { if (++seen[$0] == 2) { print; exit } }' "$train_manifest_abs")
if [[ -n "$duplicate_path" ]]; then
  echo "duplicate image in train manifest: $duplicate_path" >&2
  exit 2
fi
train_images=0
while IFS= read -r image_path || [[ -n "$image_path" ]]; do
  [[ -z "${image_path//[[:space:]]/}" ]] && continue
  if [[ "$image_path" != /* || ! -f "$image_path" ]]; then
    echo "manifest entry must be an existing absolute image path: $image_path" >&2
    exit 2
  fi
  train_images=$((train_images + 1))
done < "$train_manifest_abs"
if (( train_images == 0 )); then
  echo "empty train manifest: $train_manifest_abs" >&2
  exit 2
fi
duplicate_val_path=$(awk 'NF { if (++seen[$0] == 2) { print; exit } }' "$yaml_val_abs")
if [[ -n "$duplicate_val_path" ]]; then
  echo "duplicate image in real-val manifest: $duplicate_val_path" >&2
  exit 2
fi
val_images=0
while IFS= read -r image_path || [[ -n "$image_path" ]]; do
  [[ -z "${image_path//[[:space:]]/}" ]] && continue
  if [[ "$image_path" != /* || ! -f "$image_path" ]]; then
    echo "real-val manifest entry must be an existing absolute image path: $image_path" >&2
    exit 2
  fi
  val_images=$((val_images + 1))
done < "$yaml_val_abs"
if (( val_images == 0 )); then
  echo "empty real-val manifest: $yaml_val_abs" >&2
  exit 2
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
composition_validator="$script_dir/validate_ablation_composition.py"
matrix_validator="$script_dir/freeze_standard_matrix.py"
sbest_selector="$script_dir/select_sbest.py"
composition_args=(
  --condition "$condition"
  --train-manifest "$train_manifest_abs"
  --composition-csv "$composition_csv_abs"
)
if [[ "$condition" == "R_Sbest_HARD" ]]; then
  : "${EBIS_YOLO_SBEST_SELECTION:?hard condition requires the Day 12 selection ledger}"
  : "${EBIS_YOLO_SBEST_COMPOSITION:?hard condition requires selected standard composition CSV}"
  if [[ ! -f "$EBIS_YOLO_SBEST_SELECTION" ]]; then
    echo "missing EBIS_YOLO_SBEST_SELECTION: $EBIS_YOLO_SBEST_SELECTION" >&2
    exit 2
  fi
  if [[ ! -f "$EBIS_YOLO_SBEST_COMPOSITION" ]]; then
    echo "missing EBIS_YOLO_SBEST_COMPOSITION: $EBIS_YOLO_SBEST_COMPOSITION" >&2
    exit 2
  fi
  sbest_selection_abs=$(realpath "$EBIS_YOLO_SBEST_SELECTION")
  sbest_composition_abs=$(realpath "$EBIS_YOLO_SBEST_COMPOSITION")
  selection_json=$(
    python3 "$sbest_selector" \
      --verify-ledger "$sbest_selection_abs" \
      --matrix-lock "$matrix_lock_abs" \
      --sbest-composition "$sbest_composition_abs" \
      --runs-root "$runs_root"
  )
  selection_summary=$(
    python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["selected_condition"], d["selection_ledger_sha256"])' \
      <<<"$selection_json"
  )
  read -r sbest_condition sbest_selection_sha <<<"$selection_summary"
  composition_args+=(
    --sbest-condition "$sbest_condition"
    --sbest-composition-csv "$sbest_composition_abs"
  )
else
  python3 "$matrix_validator" \
    --verify-lock "$matrix_lock_abs" \
    --condition "$condition" \
    --composition-csv "$composition_csv_abs" >/dev/null
  sbest_selection_abs="-"
  sbest_selection_sha="-"
  sbest_condition="-"
fi
if [[ "$condition" != "R_Sbest_HARD" ]] &&
  [[ -n "${EBIS_YOLO_SBEST_SELECTION:-}" || -n "${EBIS_YOLO_SBEST_COMPOSITION:-}" ]]; then
  echo "Sbest environment variables are allowed only for R_Sbest_HARD" >&2
  exit 2
fi
composition_json=$(python3 "$composition_validator" "${composition_args[@]}")
composition_summary=$(
  python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["real_set_sha256"], d["composition_csv_sha256"], d["synthetic_count"], d["hard_count"], d.get("sbest_composition_csv_sha256", "-"))' \
    <<<"$composition_json"
)
read -r real_set_sha composition_sha synthetic_count hard_count sbest_composition_sha \
  <<<"$composition_summary"

# nbs=batch and one GPU force one optimizer update per loader batch.
steps_per_epoch=$(((train_images + batch_size - 1) / batch_size))
floor_epochs=$((target_updates / steps_per_epoch))
ceil_epochs=$(((target_updates + steps_per_epoch - 1) / steps_per_epoch))
(( floor_epochs < 1 )) && floor_epochs=1
floor_updates=$((floor_epochs * steps_per_epoch))
ceil_updates=$((ceil_epochs * steps_per_epoch))
floor_delta=$((floor_updates > target_updates ? floor_updates - target_updates : target_updates - floor_updates))
ceil_delta=$((ceil_updates > target_updates ? ceil_updates - target_updates : target_updates - ceil_updates))
if (( floor_delta <= ceil_delta )); then
  epochs=$floor_epochs
  achieved_updates=$floor_updates
  update_delta=$floor_delta
else
  epochs=$ceil_epochs
  achieved_updates=$ceil_updates
  update_delta=$ceil_delta
fi
if (( update_delta * 100 > target_updates )); then
  echo "integer-epoch update mismatch exceeds 1%" >&2
  echo "condition=$condition images=$train_images batch=$batch_size steps_per_epoch=$steps_per_epoch" >&2
  echo "target=$target_updates nearest=$achieved_updates epochs=$epochs delta=$update_delta" >&2
  echo "choose a shared target update budget that all five frozen manifests can meet within 1%" >&2
  exit 2
fi

if [[ "${EBIS_YOLO_PREFLIGHT_ONLY:-0}" == "1" ]]; then
  echo "ABLATION_PREFLIGHT_PASS condition=$condition seed=$seed images=$train_images synthetic=$synthetic_count hard=$hard_count epochs=$epochs updates=$achieved_updates target=$target_updates delta=$update_delta"
  exit 0
fi

mkdir -p "$runs_root/environment/condition_pins" "$runs_root/contracts"
run_name="${condition}_seed${seed}"
run_dir="$runs_root/$run_name"
contract_file="$runs_root/contracts/${run_name}.json"
composition_audit_file="$runs_root/contracts/${run_name}.composition.json"
if [[ -e "$run_dir" || -e "$contract_file" || -e "$composition_audit_file" ]]; then
  echo "immutable run already exists: $run_name" >&2
  exit 2
fi

model_sha_before=$(sha256sum "$model_path" | awk '{print $1}')
if [[ "$model_sha_before" != "$expected_model_sha" ]]; then
  echo "checkpoint SHA-256 does not match EBIS_YOLO_MODEL_SHA256: $model_path" >&2
  exit 2
fi
model_pin="$runs_root/environment/model.sha256"
if [[ -f "$model_pin" ]]; then
  pinned_model_sha=$(awk 'NR == 1 {print $1}' "$model_pin")
  if [[ "$pinned_model_sha" != "$expected_model_sha" ]]; then
    echo "checkpoint differs from the model already pinned under RUNS_ROOT" >&2
    exit 2
  fi
else
  printf '%s  %s\n' "$expected_model_sha" "$model_path" > "$model_pin"
fi

software_pin="$runs_root/environment/software.json"
software_json=$(python3 -c 'import json, platform, torch, ultralytics; print(json.dumps({"python": platform.python_version(), "torch": torch.__version__, "cuda": torch.version.cuda, "ultralytics": ultralytics.__version__}, indent=2, sort_keys=True))')
software_sha=$(printf '%s\n' "$software_json" | sha256sum | awk '{print $1}')
if [[ -f "$software_pin" ]]; then
  pinned_software_sha=$(sha256sum "$software_pin" | awk '{print $1}')
  if [[ "$pinned_software_sha" != "$software_sha" ]]; then
    echo "Python/PyTorch/Ultralytics environment differs from the RUNS_ROOT pin" >&2
    exit 2
  fi
else
  printf '%s\n' "$software_json" > "$software_pin"
fi

common_pin="$runs_root/environment/training_contract.json"
common_json=$(
  python3 - "$expected_model_sha" "$target_updates" "$image_size" "$batch_size" \
    "$device" "$optimizer" "$lr0" "$lrf" "$weight_decay" \
    "$matrix_lock_sha" <<'PY'
import json
import sys

(model_sha, target, imgsz, batch, device, optimizer, lr0, lrf, wd,
 matrix_lock_sha) = sys.argv[1:]
print(json.dumps({
    "allowed_conditions": ["R_ONLY", "R_S025", "R_S050", "R_S100", "R_Sbest_HARD"],
    "allowed_seeds": [17, 29, 43],
    "amp": True,
    "batch": int(batch),
    "checkpoint_primary": "last.pt",
    "close_mosaic": 0,
    "cos_lr": True,
    "deterministic": True,
    "device": int(device),
    "early_stopping": False,
    "imgsz": int(imgsz),
    "lr0": float(lr0),
    "lrf": float(lrf),
    "model_sha256": model_sha,
    "nbs": int(batch),
    "optimizer": optimizer,
    "patience": 0,
    "standard_matrix_lock_sha256": matrix_lock_sha,
    "target_optimizer_updates": int(target),
    "warmup_epochs": 0.0,
    "weight_decay": float(wd),
}, indent=2, sort_keys=True))
PY
)
common_sha=$(printf '%s\n' "$common_json" | sha256sum | awk '{print $1}')
if [[ -f "$common_pin" ]]; then
  pinned_common_sha=$(sha256sum "$common_pin" | awk '{print $1}')
  if [[ "$pinned_common_sha" != "$common_sha" ]]; then
    echo "training contract differs from the RUNS_ROOT pin" >&2
    exit 2
  fi
else
  printf '%s\n' "$common_json" > "$common_pin"
fi

matrix_pin="$runs_root/environment/standard_matrix_lock.sha256"
if [[ -f "$matrix_pin" ]]; then
  if [[ "$(awk 'NR == 1 {print $1}' "$matrix_pin")" != "$matrix_lock_sha" ]]; then
    echo "standard matrix lock differs from the RUNS_ROOT pin" >&2
    exit 2
  fi
else
  printf '%s  %s\n' "$matrix_lock_sha" "$matrix_lock_abs" > "$matrix_pin"
fi

real_set_pin="$runs_root/environment/real_train_set.sha256"
if [[ -f "$real_set_pin" ]]; then
  if [[ "$(awk 'NR == 1 {print $1}' "$real_set_pin")" != "$real_set_sha" ]]; then
    echo "real training set differs from the RUNS_ROOT pin" >&2
    exit 2
  fi
else
  printf '%s  sorted_real_image_paths\n' "$real_set_sha" > "$real_set_pin"
fi

val_manifest_sha=$(sha256sum "$yaml_val_abs" | awk '{print $1}')
val_manifest_pin="$runs_root/environment/real_val_manifest.sha256"
if [[ -f "$val_manifest_pin" ]]; then
  if [[ "$(awk 'NR == 1 {print $1}' "$val_manifest_pin")" != "$val_manifest_sha" ]]; then
    echo "real-val manifest differs from the RUNS_ROOT pin" >&2
    exit 2
  fi
else
  printf '%s  %s\n' "$val_manifest_sha" "$yaml_val_abs" > "$val_manifest_pin"
fi

manifest_sha=$(sha256sum "$train_manifest_abs" | awk '{print $1}')
yaml_sha=$(sha256sum "$data_yaml_abs" | awk '{print $1}')
condition_pin="$runs_root/environment/condition_pins/${condition}.sha256"
condition_pin_text=$(
  printf '%s  train_manifest\n%s  data_yaml\n%s  composition_csv\n%s  sbest_composition_csv_or_dash\n%s  sbest_selection_ledger_or_dash\n' \
    "$manifest_sha" "$yaml_sha" "$composition_sha" "$sbest_composition_sha" \
    "$sbest_selection_sha"
)
if [[ -f "$condition_pin" ]]; then
  if [[ "$(cat "$condition_pin")" != "$condition_pin_text" ]]; then
    echo "condition manifest/YAML differs from the RUNS_ROOT pin: $condition" >&2
    exit 2
  fi
else
  printf '%s\n' "$condition_pin_text" > "$condition_pin"
fi

printf '%s\n' "$composition_json" > "$composition_audit_file"
composition_audit_sha=$(sha256sum "$composition_audit_file" | awk '{print $1}')
python3 - "$contract_file" "$condition" "$seed" "$data_yaml_abs" \
  "$yaml_sha" "$train_manifest_abs" "$manifest_sha" "$train_images" \
  "$batch_size" "$steps_per_epoch" "$target_updates" "$epochs" \
  "$achieved_updates" "$update_delta" "$composition_audit_file" \
  "$composition_audit_sha" "$synthetic_count" "$hard_count" \
  "$matrix_lock_abs" "$matrix_lock_sha" "$sbest_selection_abs" \
  "$sbest_selection_sha" "$sbest_condition" <<'PY'
from pathlib import Path
import json
import sys

(output, condition, seed, data_yaml, yaml_sha, manifest, manifest_sha,
 train_images, batch, steps, target, epochs, achieved, delta,
 composition_audit, composition_audit_sha, synthetic_count,
 hard_count, matrix_lock, matrix_lock_sha, sbest_selection,
 sbest_selection_sha, sbest_condition) = sys.argv[1:]
payload = {
    "status": "PREPARED",
    "condition": condition,
    "seed": int(seed),
    "data_yaml": data_yaml,
    "data_yaml_sha256": yaml_sha,
    "train_manifest": manifest,
    "train_manifest_sha256": manifest_sha,
    "train_images": int(train_images),
    "batch": int(batch),
    "optimizer_updates_per_epoch": int(steps),
    "target_optimizer_updates": int(target),
    "epochs": int(epochs),
    "contract_optimizer_updates": int(achieved),
    "absolute_update_delta": int(delta),
    "composition_audit": composition_audit,
    "composition_audit_sha256": composition_audit_sha,
    "synthetic_images": int(synthetic_count),
    "hard_occlusion_images": int(hard_count),
    "standard_matrix_lock": matrix_lock,
    "standard_matrix_lock_sha256": matrix_lock_sha,
    "sbest_selection_ledger": sbest_selection,
    "sbest_selection_ledger_sha256": sbest_selection_sha,
    "sbest_condition": sbest_condition,
}
Path(output).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

yolo detect train \
  model="$model_path" \
  data="$data_yaml_abs" \
  imgsz="$image_size" \
  epochs="$epochs" \
  patience=0 \
  batch="$batch_size" \
  nbs="$batch_size" \
  device="$device" \
  optimizer="$optimizer" \
  lr0="$lr0" \
  lrf="$lrf" \
  weight_decay="$weight_decay" \
  warmup_epochs=0.0 \
  cos_lr=True \
  close_mosaic=0 \
  amp=True \
  seed="$seed" \
  deterministic=True \
  project="$runs_root" \
  name="$run_name" \
  exist_ok=False

model_sha_after=$(sha256sum "$model_path" | awk '{print $1}')
if [[ "$model_sha_after" != "$expected_model_sha" || "$model_sha_before" != "$model_sha_after" ]]; then
  echo "checkpoint changed during training: $model_path" >&2
  exit 1
fi
if [[ ! -f "$run_dir/weights/last.pt" || ! -f "$run_dir/results.csv" ]]; then
  echo "training did not produce the required last.pt/results.csv: $run_dir" >&2
  exit 1
fi
completed_epochs=$(awk -F, 'NR > 1 && NF { n++ } END { print n + 0 }' "$run_dir/results.csv")
if [[ "$completed_epochs" -ne "$epochs" ]]; then
  echo "completed epoch count differs from fixed-update contract: expected=$epochs actual=$completed_epochs" >&2
  exit 1
fi

python3 - "$contract_file" "$run_dir/weights/last.pt" <<'PY'
from pathlib import Path
import hashlib
import json
import sys

contract_path = Path(sys.argv[1])
last_path = Path(sys.argv[2])
payload = json.loads(contract_path.read_text(encoding="utf-8"))
payload["status"] = "PASS"
payload["primary_checkpoint"] = str(last_path.resolve())
payload["primary_checkpoint_sha256"] = hashlib.sha256(last_path.read_bytes()).hexdigest()
contract_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

echo "ABLATION_RUN_PASS condition=$condition seed=$seed epochs=$epochs updates=$achieved_updates target=$target_updates"
