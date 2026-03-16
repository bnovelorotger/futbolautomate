from __future__ import annotations

from collections.abc import Iterable

from app.schemas.editorial_quality_checks import (
    EditorialQualityCheckBatchResult,
    EditorialQualityCheckCandidateDetail,
    EditorialQualityCheckCandidateView,
    EditorialQualityCheckResult,
)


def render_quality_rows(rows: Iterable[EditorialQualityCheckCandidateView]) -> str:
    lines: list[str] = []
    for row in rows:
        checked_at = row.quality_checked_at.isoformat() if row.quality_checked_at else "-"
        errors = "; ".join(row.errors) if row.errors else "-"
        warnings = "; ".join(row.warnings) if row.warnings else "-"
        lines.append(
            f"{row.id:>3} | {row.competition_slug} | {row.content_type} | priority={row.priority} | "
            f"status={row.status} | text_source={row.text_source} | passed={str(row.passed).lower()} | "
            f"checked_at={checked_at} | errors={errors} | warnings={warnings} | {row.excerpt}"
        )
    return "\n".join(lines) if lines else "sin candidatos evaluables"


def render_quality_detail(row: EditorialQualityCheckCandidateDetail) -> str:
    checked_at = row.quality_checked_at.isoformat() if row.quality_checked_at else "-"
    lines = [
        f"id={row.id}",
        f"competition_slug={row.competition_slug}",
        f"content_type={row.content_type}",
        f"priority={row.priority}",
        f"status={row.status}",
        f"text_source={row.text_source}",
        f"passed={str(row.passed).lower()}",
        f"quality_checked_at={checked_at}",
        f"errors={'; '.join(row.errors) if row.errors else '-'}",
        f"warnings={'; '.join(row.warnings) if row.warnings else '-'}",
        "",
        "selected_text",
        row.selected_text,
    ]
    return "\n".join(lines)


def render_quality_result(result: EditorialQualityCheckResult) -> str:
    return f"dry_run={str(result.dry_run).lower()}\n\n{render_quality_detail(result.candidate)}"


def render_quality_batch_result(result: EditorialQualityCheckBatchResult) -> str:
    header = [
        f"dry_run={str(result.dry_run).lower()}",
        f"reference_date={result.reference_date.isoformat() if result.reference_date else '-'}",
        f"checked_count={result.checked_count}",
        f"passed_count={result.passed_count}",
        f"failed_count={result.failed_count}",
    ]
    rows = render_quality_rows(result.rows)
    return "\n".join(header) + ("\n" + rows if rows else "")
