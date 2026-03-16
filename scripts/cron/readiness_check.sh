#!/usr/bin/env bash

set -Eeuo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

setup_runtime
prepare_log "cron_readiness.log"
acquire_lock "cron_readiness"
install_traps

log INFO "=== readiness_check.sh ==="
run_step "competition_catalog_status" \
  "$PYTHON_BIN" -m app.pipelines.competition_catalog status --integrated-only
run_step "editorial_readiness" \
  "$PYTHON_BIN" -m app.pipelines.system_check editorial-readiness
