#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -lt 1 ]]; then
  echo "Uso: $0 <refresh|readiness|editorial-day> [YYYY-MM-DD]" >&2
  exit 2
fi

slot_name="$1"
shift

case "$slot_name" in
  refresh)
    exec "$SCRIPT_DIR/refresh_data.sh" "$@"
    ;;
  readiness)
    exec "$SCRIPT_DIR/readiness_check.sh" "$@"
    ;;
  editorial-day)
    exec "$SCRIPT_DIR/run_editorial_day.sh" "$@"
    ;;
  *)
    echo "Slot no soportado: $slot_name" >&2
    exit 2
    ;;
esac
