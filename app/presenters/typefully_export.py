from __future__ import annotations

from collections.abc import Iterable

from app.schemas.typefully_export import (
    TypefullyBatchExportResult,
    TypefullyConfigStatus,
    TypefullyExportCandidateView,
    TypefullyExportResult,
)


def render_typefully_rows(rows: Iterable[TypefullyExportCandidateView]) -> str:
    lines: list[str] = []
    for row in rows:
        attempted_at = row.external_publication_attempted_at.isoformat() if row.external_publication_attempted_at else "-"
        exported_at = row.external_exported_at.isoformat() if row.external_exported_at else "-"
        lines.append(
            f"{row.id:>3} | {row.competition_slug} | {row.content_type} | priority={row.priority} | "
            f"status={row.status} | has_rewrite={str(row.has_rewrite).lower()} | text_source={row.text_source} | "
            f"channel={row.external_channel or '-'} | external_ref={row.external_publication_ref or '-'} | "
            f"exported_at={exported_at} | attempted_at={attempted_at} | {row.excerpt}"
        )
    return "\n".join(lines) if lines else "sin piezas pendientes"


def render_typefully_result(result: TypefullyExportResult) -> str:
    return f"dry_run={str(result.dry_run).lower()}\n{render_typefully_rows([result.candidate])}"


def render_typefully_batch_result(result: TypefullyBatchExportResult) -> str:
    header = f"dry_run={str(result.dry_run).lower()}\nexported_count={result.exported_count}"
    rows = render_typefully_rows(result.rows)
    return f"{header}\n{rows}" if result.rows else header


def render_typefully_config_status(status: TypefullyConfigStatus) -> str:
    return "\n".join(
        [
            f"ready={str(status.ready).lower()}",
            f"api_key_configured={str(status.has_api_key).lower()}",
            f"api_url_configured={str(status.has_api_url).lower()}",
            f"api_url={status.api_url or '-'}",
            f"social_set_strategy={status.social_set_strategy}",
            f"social_set_id={status.social_set_id or '-'}",
        ]
    )
