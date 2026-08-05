#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: $0 CONDITION SEED DATA_YAML RUNS_ROOT" >&2
  exit 2
fi

condition=$1
seed=$2
data_yaml=$3
runs_root=$4

: "${EBIS_YOLO_MODEL:?set EBIS_YOLO_MODEL to an existing absolute checkpoint path}"
: "${EBIS_YOLO_MODEL_SHA256:?set EBIS_YOLO_MODEL_SHA256 to the pinned checkpoint digest}"
model_path=$EBIS_YOLO_MODEL
expected_model_sha=${EBIS_YOLO_MODEL_SHA256,,}
image_size=${EBIS_YOLO_IMGSZ:-960}
epochs=${EBIS_YOLO_EPOCHS:-60}
batch_size=${EBIS_YOLO_BATCH:-16}

if [[ ! "$condition" =~ ^(R|R_B1N|R_U1N|R_U2N|U_only)$ ]]; then
  echo "unknown condition: $condition" >&2
  exit 2
fi
if [[ ! "$seed" =~ ^(17|29|43)$ ]]; then
  echo "seed must be 17, 29 or 43" >&2
  exit 2
fi
if [[ ! -f "$data_yaml" || "$data_yaml" != /* ]]; then
  echo "DATA_YAML must be an existing absolute path: $data_yaml" >&2
  exit 2
fi
if [[ "$model_path" != /* || ! -f "$model_path" ]]; then
  echo "EBIS_YOLO_MODEL must be an existing absolute checkpoint path" >&2
  exit 2
fi
if [[ ! "$expected_model_sha" =~ ^[0-9a-f]{64}$ ]]; then
  echo "EBIS_YOLO_MODEL_SHA256 must be 64 lowercase/uppercase hex characters" >&2
  exit 2
fi

mkdir -p "$runs_root/environment"
model_pin="$runs_root/environment/model.sha256"
model_sha_before=$(sha256sum "$model_path" | awk '{print $1}')
if [[ "$model_sha_before" != "$expected_model_sha" ]]; then
  echo "checkpoint SHA mismatch: $model_path" >&2
  exit 2
fi
if [[ -f "$model_pin" ]]; then
  pinned_model_sha=$(awk 'NR == 1 {print $1}' "$model_pin")
  [[ "$pinned_model_sha" == "$expected_model_sha" ]] || { echo "RUNS_ROOT model pin differs" >&2; exit 2; }
else
  printf '%s  %s\n' "$expected_model_sha" "$model_path" > "$model_pin"
fi

software_pin="$runs_root/environment/software.json"
software_json=$(python3 -c 'import json, platform, torch, ultralytics; print(json.dumps({"python": platform.python_version(), "torch": torch.__version__, "cuda": torch.version.cuda, "ultralytics": ultralytics.__version__}, indent=2, sort_keys=True))')
software_sha=$(printf '%s\n' "$software_json" | sha256sum | awk '{print $1}')
if [[ -f "$software_pin" ]]; then
  pinned_software_sha=$(sha256sum "$software_pin" | awk '{print $1}')
  [[ "$pinned_software_sha" == "$software_sha" ]] || { echo "RUNS_ROOT software pin differs" >&2; exit 2; }
else
  printf '%s\n' "$software_json" > "$software_pin"
fi

yolo detect train \
  model="$model_path" \
  data="$data_yaml" \
  imgsz="$image_size" \
  epochs="$epochs" \
  patience=12 \
  batch="$batch_size" \
  seed="$seed" \
  deterministic=True \
  project="$runs_root" \
  name="${condition}_seed${seed}" \
  exist_ok=False

model_sha_after=$(sha256sum "$model_path" | awk '{print $1}')
if [[ "$model_sha_after" != "$expected_model_sha" ]]; then
  echo "checkpoint changed during training" >&2
  exit 1
fi
