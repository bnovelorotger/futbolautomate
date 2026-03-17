#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/logs}"
LOCK_DIR="${LOCK_DIR:-$PROJECT_ROOT/.locks}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_TIMEZONE="${APP_TIMEZONE:-Europe/Madrid}"
LOCK_CLEANUP_DIR=""


trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}


log() {
  local level="$1"
  shift
  printf '[%s] [%s] %s\n' "$(TZ="$APP_TIMEZONE" date '+%Y-%m-%d %H:%M:%S %Z')" "$level" "$*"
}


load_env_file() {
  local env_file="$1"
  [[ -f "$env_file" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" != *=* ]] && continue

    local key="${line%%=*}"
    local value="${line#*=}"
    key="$(trim "$key")"

    if [[ "$value" =~ ^\".*\"$ ]] || [[ "$value" =~ ^\'.*\'$ ]]; then
      value="${value:1:${#value}-2}"
    fi

    export "$key=$value"
  done < "$env_file"
}


setup_runtime() {
  mkdir -p "$LOG_DIR" "$LOCK_DIR"
  cd "$PROJECT_ROOT"

  load_env_file "$PROJECT_ROOT/.env.cron"
  load_env_file "$PROJECT_ROOT/.env"

  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    log ERROR "No se encuentra el interprete configurado: $PYTHON_BIN"
    exit 127
  fi
}


prepare_log() {
  local log_name="$1"
  local log_file="$LOG_DIR/$log_name"

  if command -v tee >/dev/null 2>&1; then
    exec > >(tee -a "$log_file") 2>&1
  else
    exec >>"$log_file" 2>&1
  fi
}


acquire_lock() {
  local slot_name="$1"
  local lock_file="$LOCK_DIR/$slot_name.lock"

  if command -v flock >/dev/null 2>&1; then
    exec 9>"$lock_file"
    if ! flock -n 9; then
      log WARN "Otra ejecucion sigue activa para $slot_name"
      exit 1
    fi
    return 0
  fi

  local fallback_dir="$LOCK_DIR/$slot_name.lockdir"
  if ! mkdir "$fallback_dir" 2>/dev/null; then
    log WARN "No se pudo adquirir lock para $slot_name"
    exit 1
  fi
  LOCK_CLEANUP_DIR="$fallback_dir"
}


finalize_script() {
  local status="${1:-0}"

  if [[ -n "$LOCK_CLEANUP_DIR" ]]; then
    rmdir "$LOCK_CLEANUP_DIR" 2>/dev/null || true
  fi

  if [[ $status -ne 0 ]]; then
    log ERROR "Script fallido con exit=$status"
  else
    log INFO "Script completado"
  fi
}


install_traps() {
  trap 'finalize_script "$?"' EXIT
}


run_step() {
  local label="$1"
  shift
  log INFO "Inicio: $label"
  "$@"
  log INFO "Fin: $label"
}


sync_draft_temp_snapshot() {
  log INFO "Inicio: draft_temp_sync"
  if "$PYTHON_BIN" -m app.pipelines.draft_temp sync; then
    log INFO "Fin: draft_temp_sync"
    return 0
  fi
  log WARN "No se pudo actualizar draft_temp.json"
}
