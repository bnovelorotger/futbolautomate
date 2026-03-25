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
        f"export_base_total_items={result.export_base_total_items}",
        f"export_base_path={result.export_base_path}",
        f"legacy_export_json_count={result.legacy_export_json_count}",
        f"legacy_export_blocked_series_count={result.legacy_export_blocked_series_count}",
        f"legacy_export_json_path={result.legacy_export_json_path or '-'}",
    ]
    if result.approval_rows:
        lines.extend(["", "[approval]", render_approval_rows(result.approval_rows)])
    if result.dispatched_rows:
        lines.extend(["", "[dispatch]", render_dispatch_rows(result.dispatched_rows)])
    lines.extend(
        [
            "",
            "[export_base]",
            f"total_items={result.export_base_total_items}",
            f"path={result.export_base_path}",
        ]
    )
    if result.legacy_export_json_rows:
        lines.extend(
            [
                "",
                "[legacy_export_json]",
                f"count={result.legacy_export_json_count}",
                f"blocked_series={result.legacy_export_blocked_series_count}",
                f"path={result.legacy_export_json_path or '-'}",
            ]
        )
        for row in result.legacy_export_json_rows:
            lines.append(
                f"{row.id:>3} | {row.content_type} | {row.competition} | "
                f"group={row.group or '-'} | match_date={row.match_date.isoformat() if row.match_date else '-'}"
            )
    if result.legacy_export_blocked_series:
        lines.extend(["", "[legacy_blocked_series]"])
        for row in result.legacy_export_blocked_series:
            lines.append(
                f"{row.content_type} | {row.competition} | group={row.group or '-'} | "
                f"round={row.round_label or '-'} | expected={row.expected_parts} | "
                f"available={row.available_parts} | passed={row.passed_parts} | reason={row.blocked_reason or '-'}"
            )
    return "\n".join(lines)
