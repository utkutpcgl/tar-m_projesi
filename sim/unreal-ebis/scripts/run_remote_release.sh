#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 6 ]]; then
  echo "usage: $0 RUN_NAME [COUNT=16] [START_SEED=58200] [WIDTH=1280] [HEIGHT=720] [DEPTH=0]" >&2
  exit 2
fi

run_name=$1
count=${2:-16}
start_seed=${3:-58200}
width=${4:-1280}
height=${5:-720}
depth=${6:-0}

if [[ ! "$run_name" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "RUN_NAME may contain only letters, digits, dot, underscore and dash" >&2
  exit 2
fi
for value in "$count" "$start_seed" "$width" "$height"; do
  if [[ ! "$value" =~ ^[0-9]+$ ]]; then
    echo "count, seed, width and height must be non-negative integers" >&2
    exit 2
  fi
done
if (( count < 1 || width < 64 || height < 64 )); then
  echo "COUNT must be >=1 and WIDTH/HEIGHT must be >=64" >&2
  exit 2
fi
if [[ "$depth" != 0 && "$depth" != 1 ]]; then
  echo "DEPTH must be 0 or 1" >&2
  exit 2
fi

project_root=${EBIS_PROJECT_ROOT:-/home/ankaref/Documents/Projects/simulation/unreal-ebis}
engine_root=${EBIS_ENGINE_ROOT:-/home/ankaref/Documents/Projects/simulation/.tools/unreal-engine-5.8.1}
ddc_root=${EBIS_DDC_ROOT:-/media/ankaref/SSD-MNT-500GB/unreal-ddc}
output_root="$project_root/output/$run_name"
log_path="$project_root/evidence/engine/${run_name}_stdout.log"

if [[ -e "$output_root" ]]; then
  echo "refusing to overwrite existing output: $output_root" >&2
  exit 2
fi
mkdir -p "$project_root/evidence/engine" "$ddc_root"

export DISPLAY=${EBIS_DISPLAY:-:1}
export XAUTHORITY=${EBIS_XAUTHORITY:-/run/user/1000/gdm/Xauthority}
export EBIS_CONFIG="$project_root/configs/ebis_unreal_v1.json"
export EBIS_OUTPUT="$output_root"
export EBIS_START_SEED="$start_seed"
export EBIS_COUNT="$count"
export EBIS_WIDTH="$width"
export EBIS_HEIGHT="$height"
export EBIS_DEPTH="$depth"

env "UE-LocalDataCachePath=$ddc_root" \
  "$engine_root/Engine/Binaries/Linux/UnrealEditor-Cmd" \
  "$project_root/UnrealEBIS.uproject" \
  -RenderOffscreen -Unattended -NoSplash -NoSound -NoLiveCoding \
  -stdout -FullStdOutLogOutput \
  -ExecutePythonScript="$project_root/scripts/run_unreal_batch.py" \
  >"$log_path" 2>&1

python3 "$project_root/scripts/apply_camera_model.py" \
  --root "$output_root" \
  --config "$project_root/configs/ebis_unreal_v1.json"
python3 "$project_root/scripts/apply_sensor_response.py" \
  --root "$output_root" \
  --config "$project_root/configs/sensor_response_v1.json"
python3 "$project_root/scripts/build_visible_bboxes.py" \
  --root "$output_root" \
  --config "$project_root/configs/ebis_unreal_v1.json"
python3 "$project_root/scripts/create_qc_contact_sheet.py" \
  --dataset "$output_root" \
  --output "$project_root/reports/qc/assets/${run_name}_contact_sheet.png" \
  --columns 4

echo "UNREAL_EBIS_RELEASE_OK output=$output_root log=$log_path"
