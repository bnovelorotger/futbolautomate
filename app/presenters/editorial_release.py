from __future__ import annotations

from app.presenters.editorial_approval import render_approval_rows
from app.presenters.publication_dispatch import render_dispatch_rows
from app.schemas.editorial_release import EditorialReleaseResult


def render_release_result(result: EditorialReleaseResult) -> str:
    lines = [
        f"dry_run={str(result.dry_run).lower()}",
        f"reference_date={result.reference_date.isoformat() if result.reference_date else '-'}",
        f"drafts_found={result.drafts_found}",
        f"autoapprovable_count={result.autoapprovable_count}",
        f"autoapproved_count={result.autoapproved_count}",
        f"manual_review_count={result.manual_review_count}",
        f"dispatched_count={result.dispatched_count}",
        f"autoexport_scanned_count={result.autoexport_scanned_count}",
        f"autoexport_eligible_count={result.autoexport_eligible_count}",
        f"autoexport_exported_count={result.autoexport_exported_count}",
        f"autoexport_blocked_count={result.autoexport_blocked_count}",
        f"autoexport_failed_count={result.autoexport_failed_count}",
    ]
    if result.approval_rows:
        lines.extend(["", "[approval]", render_approval_rows(result.approval_rows)])
    if result.dispatched_rows:
        lines.extend(["", "[dispatch]", render_dispatch_rows(result.dispatched_rows)])
    if result.autoexport_rows:
        lines.extend(
            [
                "",
                "[autoexport]",
                f"scanned_count={result.autoexport_scanned_count}",
                f"eligible_count={result.autoexport_eligible_count}",
                f"exported_count={result.autoexport_exported_count}",
                f"blocked_count={result.autoexport_blocked_count}",
                f"failed_count={result.autoexport_failed_count}",
            ]
        )
        for row in result.autoexport_rows:
            lines.append(
                f"{row.id:>3} | {row.competition_slug} | {row.content_type} | "
                f"allowed={str(row.autoexport_allowed).lower()} | policy={row.policy_reason} | "
                f"external_ref={row.external_publication_ref or '-'} | {row.excerpt}"
            )
    return "\n".join(lines)
