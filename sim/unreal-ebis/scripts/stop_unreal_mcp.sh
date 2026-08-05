#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${EBIS_PROJECT_ROOT:-/home/ankaref/Documents/Projects/simulation/unreal-ebis}"
ENGINE_ROOT="${EBIS_ENGINE_ROOT:-/home/ankaref/Documents/Projects/simulation/.tools/unreal-engine-5.8.1}"
EDITOR="$ENGINE_ROOT/Engine/Binaries/Linux/UnrealEditor"
PROJECT="$PROJECT_ROOT/UnrealEBIS.uproject"
PID_FILE="$PROJECT_ROOT/evidence/mcp/unreal_editor.pid"

if [[ ! -f "$PID_FILE" ]]; then
  printf '%s\n' "not_running"
  exit 0
fi
pid="$(tr -cd '0-9' < "$PID_FILE")"
if [[ -z "$pid" || ! -r "/proc/$pid/cmdline" ]]; then
  rm -f "$PID_FILE"
  printf '%s\n' "stale_pid_file_removed"
  exit 0
fi
cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
if [[ "$cmd" != *"$EDITOR"* || "$cmd" != *"$PROJECT"* ]]; then
  printf '%s\n' "refusing_unmatched_process pid=$pid cmd=$cmd" >&2
  exit 3
fi
kill -TERM "$pid"
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    printf '%s\n' "stopped pid=$pid"
    exit 0
  fi
  sleep 1
done
printf '%s\n' "process_did_not_stop pid=$pid" >&2
exit 4
