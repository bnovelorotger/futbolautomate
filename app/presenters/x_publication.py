from __future__ import annotations

from collections.abc import Iterable

from app.schemas.x_publication import (
    XBatchPublicationResult,
    XPublicationCandidateView,
    XPublicationResult,
)


def render_x_rows(rows: Iterable[XPublicationCandidateView]) -> str:
    lines: list[str] = []
    for row in rows:
        scheduled_at = row.scheduled_at.isoformat() if row.scheduled_at else "-"
        attempted_at = row.external_publication_attempted_at.isoformat() if row.external_publication_attempted_at else "-"
        lines.append(
            f"{row.id:>3} | {row.competition_slug} | {row.content_type} | priority={row.priority} | "
            f"status={row.status} | scheduled_at={scheduled_at} | external_ref={row.external_publication_ref or '-'} | "
            f"attempted_at={attempted_at} | {row.excerpt}"
        )
    return "\n".join(lines) if lines else "sin piezas pendientes"


def render_x_result(result: XPublicationResult) -> str:
    return f"dry_run={str(result.dry_run).lower()}\n{render_x_rows([result.candidate])}"


def render_x_batch_result(result: XBatchPublicationResult) -> str:
    header = f"dry_run={str(result.dry_run).lower()}\npublished_count={result.published_count}"
    rows = render_x_rows(result.rows)
    return f"{header}\n{rows}" if result.rows else header
