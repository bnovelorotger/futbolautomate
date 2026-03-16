from __future__ import annotations

from app.schemas.editorial_approval import (
    EditorialApprovalCandidateView,
    EditorialApprovalRunResult,
    EditorialApprovalStatusView,
)


def render_approval_rows(rows: list[EditorialApprovalCandidateView]) -> str:
    if not rows:
        return "sin drafts evaluables"
    lines: list[str] = []
    for row in rows:
        autoapproved = (
            row.autoapproved_at.isoformat() if row.autoapproved_at else "-"
        )
        lines.append(
            f"{row.id:>3} | {row.competition_slug} | {row.content_type} | priority={row.priority} | "
            f"status={row.status} | autoapprovable={str(row.autoapprovable).lower()} | "
            f"policy={row.policy_reason} | autoapproved_at={autoapproved} | {row.excerpt}"
        )
    return "\n".join(lines)


def render_approval_status(status: EditorialApprovalStatusView) -> str:
    return "\n".join(
        [
            f"enabled={str(status.enabled).lower()}",
            "autoapprovable_content_types="
            + (", ".join(str(item) for item in status.autoapprovable_content_types) or "-"),
            "manual_review_content_types="
            + (", ".join(str(item) for item in status.manual_review_content_types) or "-"),
            f"drafts_found={status.drafts_found}",
            f"autoapprovable_count={status.autoapprovable_count}",
            f"manual_review_count={status.manual_review_count}",
        ]
    )


def render_approval_result(result: EditorialApprovalRunResult) -> str:
    lines = [
        f"dry_run={str(result.dry_run).lower()}",
        f"reference_date={result.reference_date.isoformat() if result.reference_date else '-'}",
        f"drafts_found={result.drafts_found}",
        f"autoapprovable_count={result.autoapprovable_count}",
        f"autoapproved_count={result.autoapproved_count}",
        f"manual_review_count={result.manual_review_count}",
    ]
    if result.rows:
        lines.append("")
        lines.append(render_approval_rows(result.rows))
    return "\n".join(lines)
