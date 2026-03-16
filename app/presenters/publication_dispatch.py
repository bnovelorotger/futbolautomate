from __future__ import annotations

from collections.abc import Iterable

from app.schemas.publication_dispatch import (
    PublicationCandidateView,
    PublicationDispatchResult,
    PublicationDispatchSummary,
)


def render_dispatch_rows(rows: Iterable[PublicationCandidateView]) -> str:
    lines: list[str] = []
    for row in rows:
        scheduled_at = row.scheduled_at.isoformat() if row.scheduled_at else "-"
        published_at = row.published_at.isoformat() if row.published_at else "-"
        lines.append(
            f"{row.id:>3} | {row.competition_slug} | {row.content_type} | priority={row.priority} | "
            f"status={row.status} | scheduled_at={scheduled_at} | published_at={published_at} | "
            f"created_at={row.created_at.isoformat()} | {row.excerpt}"
        )
    return "\n".join(lines) if lines else "sin piezas elegibles"


def render_dispatch_result(result: PublicationDispatchResult) -> str:
    header = f"dry_run={str(result.dry_run).lower()}\ndispatched_count={result.dispatched_count}"
    rows = render_dispatch_rows(result.rows)
    return f"{header}\n{rows}" if result.rows else header


def render_dispatch_summary(summary: PublicationDispatchSummary) -> str:
    return "\n".join(
        [
            f"total_ready={summary.total_ready}",
            f"total_approved_future={summary.total_approved_future}",
            f"total_published={summary.total_published}",
            f"total_rejected={summary.total_rejected}",
            f"total_drafts={summary.total_drafts}",
        ]
    )
