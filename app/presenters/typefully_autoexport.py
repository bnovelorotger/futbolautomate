from __future__ import annotations

from app.schemas.typefully_autoexport import (
    TypefullyAutoexportLastRun,
    TypefullyAutoexportRunResult,
    TypefullyAutoexportStatusView,
)


def _summary_line(result: TypefullyAutoexportRunResult | TypefullyAutoexportLastRun) -> str:
    return (
        f"AUTOEXPORT phase={result.phase} scanned={result.scanned_count} eligible={result.eligible_count} "
        f"exported={result.exported_count} blocked={result.blocked_count} "
        f"capacity_deferred={result.capacity_deferred_count} failed={result.failed_count}"
    )


def render_typefully_autoexport_candidates(
    rows,
    *,
    title: str,
) -> str:
    lines = [f"{title}_count={len(rows)}"]
    if not rows:
        lines.append("sin piezas evaluadas")
        return "\n".join(lines)
    lines.append("")
    for row in rows:
        quality = (
            "pass" if row.quality_check_passed is True else
            "fail" if row.quality_check_passed is False else
            "-"
        )
        quality_errors = "; ".join(row.quality_check_errors) if row.quality_check_errors else "-"
        lines.append(
            f"{row.id:>3} | {row.competition_slug} | {row.content_type} | priority={row.priority} | "
            f"status={row.status} | outcome={row.export_outcome} | allowed={str(row.autoexport_allowed).lower()} | "
            f"policy={row.policy_reason} | quality={quality} | quality_errors={quality_errors} | "
            f"text_source={row.text_source} | external_ref={row.external_publication_ref or '-'} | "
            f"external_error={row.external_publication_error or '-'} | {row.excerpt}"
        )
    return "\n".join(lines)


def render_typefully_autoexport_result(result: TypefullyAutoexportRunResult) -> str:
    lines = [
        _summary_line(result),
        f"executed_at={result.executed_at.isoformat()}",
        f"dry_run={str(result.dry_run).lower()}",
        f"policy_enabled={str(result.policy_enabled).lower()}",
        f"phase={result.phase}",
        f"reference_date={result.reference_date.isoformat() if result.reference_date else '-'}",
        f"scanned_count={result.scanned_count}",
        f"eligible_count={result.eligible_count}",
        f"exported_count={result.exported_count}",
        f"blocked_count={result.blocked_count}",
        f"capacity_deferred_count={result.capacity_deferred_count}",
        f"failed_count={result.failed_count}",
        f"capacity_limit_reached={str(result.capacity_limit_reached).lower()}",
        f"capacity_limit_reason={result.capacity_limit_reason or '-'}",
    ]
    if not result.rows:
        lines.append("sin piezas evaluadas")
        return "\n".join(lines)

    lines.append("")
    for row in result.rows:
        quality = (
            "pass" if row.quality_check_passed is True else
            "fail" if row.quality_check_passed is False else
            "-"
        )
        quality_errors = "; ".join(row.quality_check_errors) if row.quality_check_errors else "-"
        lines.append(
            f"{row.id:>3} | {row.competition_slug} | {row.content_type} | priority={row.priority} | "
            f"status={row.status} | outcome={row.export_outcome} | allowed={str(row.autoexport_allowed).lower()} | "
            f"policy={row.policy_reason} | quality={quality} | quality_errors={quality_errors} | "
            f"has_rewrite={str(row.has_rewrite).lower()} | "
            f"text_source={row.text_source} | external_ref={row.external_publication_ref or '-'} | "
            f"external_error={row.external_publication_error or '-'} | {row.excerpt}"
        )
    return "\n".join(lines)


def render_typefully_autoexport_status(status: TypefullyAutoexportStatusView) -> str:
    lines = [
        f"enabled={str(status.enabled).lower()}",
        f"phase={status.phase}",
        f"max_exports_per_run={status.max_exports_per_run if status.max_exports_per_run is not None else '-'}",
        f"max_exports_per_day={status.max_exports_per_day if status.max_exports_per_day is not None else '-'}",
        f"stop_on_capacity_limit={str(status.stop_on_capacity_limit).lower()}",
        "capacity_error_codes=" + (", ".join(status.capacity_error_codes) or "-"),
        "allowed_content_types=" + (", ".join(str(item) for item in status.allowed_content_types) or "-"),
        "validation_required_content_types=" + (
            ", ".join(str(item) for item in status.validation_required_content_types) or "-"
        ),
        "manual_review_content_types=" + (
            ", ".join(str(item) for item in status.manual_review_content_types) or "-"
        ),
        f"pending_capacity_count={status.pending_capacity_count}",
        f"pending_normal_count={status.pending_normal_count}",
    ]
    if status.last_run is None:
        lines.append("last_execution=-")
        lines.append("last_summary=-")
        return "\n".join(lines)

    lines.extend(
        [
            f"last_execution={status.last_run.executed_at.isoformat()}",
            f"last_dry_run={str(status.last_run.dry_run).lower()}",
            f"last_reference_date={status.last_run.reference_date.isoformat() if status.last_run.reference_date else '-'}",
            f"last_capacity_limit_reached={str(status.last_run.capacity_limit_reached).lower()}",
            f"last_capacity_limit_reason={status.last_run.capacity_limit_reason or '-'}",
            f"last_summary={_summary_line(status.last_run)}",
        ]
    )
    return "\n".join(lines)
