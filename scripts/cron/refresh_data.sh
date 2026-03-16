#!/usr/bin/env bash

set -Eeuo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

setup_runtime
prepare_log "cron_refresh.log"
acquire_lock "cron_refresh"
install_traps

REFRESH_SOURCE="${REFRESH_SOURCE:-futbolme}"
COMPETITIONS=(
  "tercera_rfef_g11"
  "segunda_rfef_g3_baleares"
  "division_honor_mallorca"
)
TARGETS=("matches" "standings")

log INFO "=== refresh_data.sh ==="
run_step "seed_competitions_integrated" \
  "$PYTHON_BIN" -m app.pipelines.competition_catalog seed --integrated-only --missing-only

for competition in "${COMPETITIONS[@]}"; do
  for target in "${TARGETS[@]}"; do
    run_step "refresh_${competition}_${target}" \
      "$PYTHON_BIN" -m app.pipelines.run_source \
      --source "$REFRESH_SOURCE" \
      --competition "$competition" \
      --target "$target"
  done
done
