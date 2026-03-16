from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.schemas.typefully_autoexport import (
    TypefullyAutoexportLastRun,
    TypefullyAutoexportPolicy,
    TypefullyAutoexportRunResult,
)


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "typefully_autoexport.json"


def _default_status_path() -> Path:
    return Path(__file__).resolve().parents[2] / "logs" / "typefully_autoexport_status.json"


@lru_cache(maxsize=2)
def load_typefully_autoexport_policy(path: Path | None = None) -> TypefullyAutoexportPolicy:
    config_path = path or _default_config_path()
    with config_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return TypefullyAutoexportPolicy.model_validate(payload)


def load_typefully_autoexport_last_run(path: Path | None = None) -> TypefullyAutoexportLastRun | None:
    status_path = path or _default_status_path()
    if not status_path.exists():
        return None
    with status_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return TypefullyAutoexportLastRun.model_validate(payload)


def store_typefully_autoexport_last_run(
    result: TypefullyAutoexportRunResult,
    path: Path | None = None,
) -> Path:
    status_path = path or _default_status_path()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    payload = TypefullyAutoexportLastRun(
        executed_at=result.executed_at,
        dry_run=result.dry_run,
        policy_enabled=result.policy_enabled,
        phase=result.phase,
        reference_date=result.reference_date,
        scanned_count=result.scanned_count,
        eligible_count=result.eligible_count,
        exported_count=result.exported_count,
        blocked_count=result.blocked_count,
        capacity_deferred_count=result.capacity_deferred_count,
        failed_count=result.failed_count,
        capacity_limit_reached=result.capacity_limit_reached,
        capacity_limit_reason=result.capacity_limit_reason,
    )
    with status_path.open("w", encoding="utf-8") as handle:
        json.dump(payload.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
    return status_path
