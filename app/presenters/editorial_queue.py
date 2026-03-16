from __future__ import annotations

from collections.abc import Iterable

from app.schemas.editorial_queue import (
    EditorialQueueCandidateDetail,
    EditorialQueueCandidateView,
    EditorialQueueSummary,
)


def render_queue_rows(rows: Iterable[EditorialQueueCandidateView]) -> str:
    lines: list[str] = []
    for row in rows:
        scheduled_at = row.scheduled_at.isoformat() if row.scheduled_at else "-"
        lines.append(
            f"{row.id:>3} | {row.competition_slug} | {row.content_type} | priority={row.priority} | "
            f"status={row.status} | scheduled_at={scheduled_at} | created_at={row.created_at.isoformat()} | "
            f"{row.excerpt}"
        )
    return "\n".join(lines) if lines else "sin candidatos"


def render_queue_detail(row: EditorialQueueCandidateDetail) -> str:
    scheduled_at = row.scheduled_at.isoformat() if row.scheduled_at else "-"
    reviewed_at = row.reviewed_at.isoformat() if row.reviewed_at else "-"
    approved_at = row.approved_at.isoformat() if row.approved_at else "-"
    published_at = row.published_at.isoformat() if row.published_at else "-"
    lines = [
        f"id={row.id}",
        f"competition_slug={row.competition_slug}",
        f"content_type={row.content_type}",
        f"priority={row.priority}",
        f"status={row.status}",
        f"scheduled_at={scheduled_at}",
        f"created_at={row.created_at.isoformat()}",
        f"updated_at={row.updated_at.isoformat()}",
        f"reviewed_at={reviewed_at}",
        f"approved_at={approved_at}",
        f"published_at={published_at}",
        f"rejection_reason={row.rejection_reason or '-'}",
        "",
        "text_draft",
        row.text_draft,
    ]
    return "\n".join(lines)


def render_queue_summary(summary: EditorialQueueSummary) -> str:
    return "\n".join(
        [
            f"total_drafts={summary.total_drafts}",
            f"total_approved={summary.total_approved}",
            f"total_rejected={summary.total_rejected}",
            f"total_published={summary.total_published}",
            f"total_scheduled_pending={summary.total_scheduled_pending}",
        ]
    )
