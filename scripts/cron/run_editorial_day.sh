#!/usr/bin/env bash

set -Eeuo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

setup_runtime
prepare_log "cron_editorial.log"
acquire_lock "cron_editorial"
install_traps

TARGET_DATE="${1:-${TARGET_DATE:-$(TZ="$APP_TIMEZONE" date +%F)}}"
PREVIEW_ONLY="${PREVIEW_ONLY:-false}"

log INFO "=== run_editorial_day.sh date=$TARGET_DATE preview_only=$PREVIEW_ONLY ==="
run_step "preview_day_$TARGET_DATE" \
  "$PYTHON_BIN" -m app.pipelines.editorial_ops preview-day --date "$TARGET_DATE"

if [[ "${PREVIEW_ONLY,,}" == "true" ]]; then
  log WARN "PREVIEW_ONLY=true: se omite run-daily"
  exit 0
fi

run_step "run_editorial_day_$TARGET_DATE" \
  "$PYTHON_BIN" -m app.pipelines.editorial_ops run-daily --date "$TARGET_DATE"
