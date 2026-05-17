from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy import case, func, select

from app.core.config import get_settings
from app.core.enums import ContentType
from app.core.logging import configure_logging
from app.core.run_context import set_run_id
from app.db.models import ContentCandidate
from app.db.session import init_db, session_scope
from app.llm.providers import editorial_rewrite_provider_ready, missing_editorial_rewrite_config
from app.llm.providers.base import LLMConfigurationError, LLMProviderError
from app.services.editorial_rewriter import ALLOWED_REWRITE_STATUSES, EditorialRewriterService

PHASE3_SMOKE_CONTENT_TYPES = (ContentType.PREVIEW, ContentType.VIRAL_STORY)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test real del proveedor de editorial rewrite.")
    parser.add_argument("--candidate-id", type=int, help="ID concreto a probar en dry-run sin persistencia.")
    parser.add_argument("--json", action="store_true", help="Imprime el resultado en JSON.")
    return parser.parse_args()


def _dump(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _settings_summary() -> dict[str, Any]:
    settings = get_settings()
    return {
        "app_env": settings.app_env,
        "database_url": settings.database_url,
        "provider": settings.editorial_rewrite_provider,
        "provider_ready": editorial_rewrite_provider_ready(settings),
        "editorial_rewrite_model": settings.editorial_rewrite_model,
        "editorial_rewrite_api_key_present": bool(settings.editorial_rewrite_api_key),
        "editorial_rewrite_humanized_local_enabled": settings.editorial_rewrite_humanized_local_enabled,
        "editorial_phase3_rollout_enabled": settings.editorial_phase3_rollout_enabled,
    }


def _find_candidate_id(service: EditorialRewriterService) -> int | None:
    rows = (
        service.session.execute(
            select(ContentCandidate)
            .where(
                ContentCandidate.content_type.in_([str(content_type) for content_type in PHASE3_SMOKE_CONTENT_TYPES]),
                ContentCandidate.status.in_([str(status) for status in ALLOWED_REWRITE_STATUSES]),
                func.length(func.trim(ContentCandidate.text_draft)) > 0,
            )
            .order_by(
                case((ContentCandidate.rewrite_timestamp.is_(None), 0), else_=1),
                ContentCandidate.priority.desc(),
                ContentCandidate.created_at.asc(),
            )
            .limit(100)
        )
        .scalars()
        .all()
    )
    for row in rows:
        if service._phase3_decision(row).eligible:
            return row.id
    return None


def main() -> int:
    args = _parse_args()
    set_run_id()
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    payload: dict[str, Any] = {"settings": _settings_summary()}

    if not editorial_rewrite_provider_ready(settings):
        payload.update(
            {
                "status": "config_missing",
                "missing": missing_editorial_rewrite_config(settings),
                "message": "Completa las variables faltantes en .env para ejecutar un smoke test real.",
            }
        )
        _dump(payload)
        return 1

    init_db()
    with session_scope() as session:
        service = EditorialRewriterService(session)
        candidate_id = args.candidate_id or _find_candidate_id(service)
        if candidate_id is None:
            payload.update(
                {
                    "status": "no_phase3_candidate",
                    "message": "No hay candidatos elegibles de PREVIEW o VIRAL_STORY en la base local.",
                }
            )
            _dump(payload)
            return 1
        try:
            result = service.rewrite_candidate(candidate_id, dry_run=True, overwrite=True)
        except (LLMConfigurationError, LLMProviderError) as exc:
            payload.update(
                {
                    "status": "provider_failed",
                    "candidate_id": candidate_id,
                    "error": str(exc),
                }
            )
            _dump(payload)
            return 1

    candidate = result.candidate
    payload.update(
        {
            "status": "ok",
            "candidate_id": candidate.id,
            "competition_slug": candidate.competition_slug,
            "content_type": str(candidate.content_type),
            "rewrite_status": candidate.rewrite_status,
            "rewrite_model": candidate.rewrite_model,
            "rewritten_text": candidate.rewritten_text,
            "rewritten_length": len(candidate.rewritten_text or ""),
        }
    )
    _dump(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
