from __future__ import annotations

from collections.abc import Iterable

from app.schemas.editorial_rewrite import (
    EditorialRewriteBatchResult,
    EditorialRewriteCandidateDetail,
    EditorialRewriteCandidateView,
    EditorialRewriteResult,
)


def render_rewrite_rows(rows: Iterable[EditorialRewriteCandidateView]) -> str:
    lines: list[str] = []
    for row in rows:
        rewrite_timestamp = row.rewrite_timestamp.isoformat() if row.rewrite_timestamp else "-"
        lines.append(
            f"{row.id:>3} | {row.competition_slug} | {row.content_type} | priority={row.priority} | "
            f"status={row.status} | rewrite_status={row.rewrite_status or '-'} | rewrite_model={row.rewrite_model or '-'} | "
            f"rewrite_timestamp={rewrite_timestamp} | {row.excerpt}"
        )
    return "\n".join(lines) if lines else "sin candidatos elegibles"


def render_rewrite_detail(row: EditorialRewriteCandidateDetail) -> str:
    rewrite_timestamp = row.rewrite_timestamp.isoformat() if row.rewrite_timestamp else "-"
    lines = [
        f"id={row.id}",
        f"competition_slug={row.competition_slug}",
        f"content_type={row.content_type}",
        f"priority={row.priority}",
        f"status={row.status}",
        f"rewrite_status={row.rewrite_status or '-'}",
        f"rewrite_model={row.rewrite_model or '-'}",
        f"rewrite_timestamp={rewrite_timestamp}",
        f"rewrite_error={row.rewrite_error or '-'}",
        f"created_at={row.created_at.isoformat()}",
        f"updated_at={row.updated_at.isoformat()}",
        "",
        "text_draft",
        row.text_draft,
        "",
        "rewritten_text",
        row.rewritten_text or "-",
    ]
    return "\n".join(lines)


def render_rewrite_result(result: EditorialRewriteResult) -> str:
    header = [
        f"dry_run={str(result.dry_run).lower()}",
        f"overwritten={str(result.overwritten).lower()}",
        "",
    ]
    return "\n".join(header) + render_rewrite_detail(result.candidate)


def render_rewrite_batch_result(result: EditorialRewriteBatchResult) -> str:
    header = f"dry_run={str(result.dry_run).lower()}\nrewritten_count={result.rewritten_count}"
    rows = render_rewrite_rows(result.rows)
    return f"{header}\n{rows}" if result.rows else header
