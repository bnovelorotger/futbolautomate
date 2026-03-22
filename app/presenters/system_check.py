from __future__ import annotations

from app.schemas.system_check import EditorialReadinessReport


def render_editorial_readiness(report: EditorialReadinessReport) -> str:
    lines = [
        "Editorial Readiness",
        f"checked_at={report.checked_at.isoformat()}",
        f"integrated_catalog_count={report.integrated_catalog_count}",
        f"seeded_integrated_count={report.seeded_integrated_count}",
        f"planner_ready_count={report.planner_ready_count}",
        f"export_json_ready={str(report.export_json_ready).lower()}",
        f"export_json_path={report.export_json_path}",
        f"content_candidates_total={report.content_candidates_total}",
        f"content_candidates_pending_export={report.content_candidates_pending_export}",
        "",
    ]
    for row in report.rows:
        missing = ",".join(row.missing_dependencies) if row.missing_dependencies else "-"
        planned = ",".join(str(item) for item in row.planner_weekly_types) if row.planner_weekly_types else "-"
        lines.append(
            f"{row.code} | seeded={str(row.seeded_in_db).lower()} | planner_ready={str(row.planner_ready).lower()} | "
            f"planned={planned} | matches={row.matches_count} | finished={row.finished_matches_count} | "
            f"scheduled={row.scheduled_matches_count} | standings={row.standings_count} | "
            f"candidates={row.content_candidates_count} | pending_export={row.pending_export_count} | missing={missing}"
        )
    return "\n".join(lines).rstrip()
