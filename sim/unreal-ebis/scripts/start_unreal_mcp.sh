#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${EBIS_PROJECT_ROOT:-/home/ankaref/Documents/Projects/simulation/unreal-ebis}"
ENGINE_ROOT="${EBIS_ENGINE_ROOT:-/home/ankaref/Documents/Projects/simulation/.tools/unreal-engine-5.8.1}"
EDITOR="$ENGINE_ROOT/Engine/Binaries/Linux/UnrealEditor"
PROJECT="$PROJECT_ROOT/UnrealEBIS.uproject"
PID_FILE="$PROJECT_ROOT/evidence/mcp/unreal_editor.pid"
LOG_FILE="$PROJECT_ROOT/evidence/mcp/unreal_editor_stdout.log"
DDC_ROOT="${EBIS_DDC_ROOT:-/media/ankaref/SSD-MNT-500GB/unreal-ddc}"
DISPLAY_VALUE="${EBIS_DISPLAY:-:1}"
PORT="${EBIS_MCP_PORT:-8000}"

mkdir -p "$PROJECT_ROOT/evidence/mcp" "$DDC_ROOT"
if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(tr -cd '0-9' < "$PID_FILE")"
  if [[ -n "$existing_pid" && -r "/proc/$existing_pid/cmdline" ]]; then
    existing_cmd="$(tr '\0' ' ' < "/proc/$existing_pid/cmdline")"
    if [[ "$existing_cmd" == *"$EDITOR"* && "$existing_cmd" == *"$PROJECT"* ]]; then
      if ss -ltn "sport = :$PORT" | tail -n +2 | grep -q "127.0.0.1:$PORT"; then
        printf '%s\n' "already_running_ready pid=$existing_pid endpoint=http://127.0.0.1:$PORT/mcp"
        exit 0
      fi
      printf '%s\n' "editor_running_but_mcp_not_ready pid=$existing_pid" >&2
      exit 3
    fi
  fi
  rm -f "$PID_FILE"
fi

if ss -ltn "sport = :$PORT" | tail -n +2 | grep -q .; then
  printf '%s\n' "port_in_use port=$PORT" >&2
  exit 2
fi

nohup env DISPLAY="$DISPLAY_VALUE" "UE-LocalDataCachePath=$DDC_ROOT" \
  "$EDITOR" "$PROJECT" \
  -ModelContextProtocolStartServer -ModelContextProtocolPort="$PORT" \
  -unattended -nop4 -nosplash -nosound -RenderOffscreen \
  >"$LOG_FILE" 2>&1 </dev/null &
pid=$!
printf '%s\n' "$pid" > "$PID_FILE"
for _ in $(seq 1 180); do
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PID_FILE"
    printf '%s\n' "editor_exited_before_mcp_ready pid=$pid log=$LOG_FILE" >&2
    exit 3
  fi
  if ss -ltn "sport = :$PORT" | tail -n +2 | grep -q "127.0.0.1:$PORT"; then
    # The listener is registered before all editor startup callbacks finish.
    # A short bounded settle avoids racing the first JSON-RPC request.
    sleep 2
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PID_FILE"
      printf '%s\n' "editor_exited_during_mcp_settle pid=$pid log=$LOG_FILE" >&2
      exit 3
    fi
    printf '%s\n' "started_ready pid=$pid endpoint=http://127.0.0.1:$PORT/mcp log=$LOG_FILE"
    exit 0
  fi
  sleep 0.25
done
kill -TERM "$pid" 2>/dev/null || true
rm -f "$PID_FILE"
printf '%s\n' "mcp_readiness_timeout pid=$pid port=$PORT log=$LOG_FILE" >&2
exit 4
