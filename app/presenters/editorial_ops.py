from __future__ import annotations

from app.schemas.editorial_ops import EditorialOpsPreviewResult, EditorialOpsRunResult


def render_editorial_ops_preview(result: EditorialOpsPreviewResult) -> str:
    lines = [
        f"Preview Day | {result.date.isoformat()}",
        f"total_tasks={result.total_tasks}",
        f"ready_tasks={result.ready_tasks}",
        f"blocked_tasks={result.blocked_tasks}",
        f"expected_total={result.expected_total}",
    ]
    if not result.rows:
        lines.append("sin tareas")
        return "\n".join(lines)
    lines.append("")
    for row in result.rows:
        missing = ",".join(row.missing_dependencies) if row.missing_dependencies else "-"
        lines.append(
            f"- priority={row.priority} | {row.competition_slug} | {row.planning_type} -> {row.target_content_type} | "
            f"expected={row.expected_count} | missing={missing}"
        )
        for excerpt in row.excerpts:
            lines.append(f"  {excerpt}")
    return "\n".join(lines)


def render_editorial_ops_run(result: EditorialOpsRunResult) -> str:
    lines = [
        f"Run Daily | {result.date.isoformat()}",
        f"total_tasks={result.total_tasks}",
        f"generated_total={result.generated_total}",
        f"inserted_total={result.inserted_total}",
        f"updated_total={result.updated_total}",
        f"blocked_tasks={result.blocked_tasks}",
    ]
    if not result.rows:
        lines.append("sin tareas")
        return "\n".join(lines)
    lines.append("")
    for row in result.rows:
        missing = ",".join(row.missing_dependencies) if row.missing_dependencies else "-"
        lines.append(
            f"- priority={row.priority} | {row.competition_slug} | {row.planning_type} -> {row.target_content_type} | "
            f"generated={row.generated_count} | inserted={row.inserted} | updated={row.updated} | missing={missing}"
        )
        for excerpt in row.excerpts:
            lines.append(f"  {excerpt}")
    return "\n".join(lines)
