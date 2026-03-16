from __future__ import annotations

from app.schemas.editorial_planner import (
    EditorialCampaignGenerationResult,
    EditorialCampaignPlan,
    EditorialWeekPlan,
)


def render_campaign_plan(plan: EditorialCampaignPlan) -> str:
    lines = [
        f"Plan Editorial | {plan.date.isoformat()} ({plan.weekday_label})",
        f"total_tasks={plan.total_tasks}",
    ]
    if not plan.tasks:
        lines.append("sin tareas planificadas")
        return "\n".join(lines)

    lines.append("")
    for task in plan.tasks:
        lines.append(
            f"- priority={task.priority} | competition={task.competition_name} ({task.competition_slug}) | "
            f"content={task.planning_type} | target={task.target_content_type}"
        )
    return "\n".join(lines)


def render_week_plan(week_plan: EditorialWeekPlan) -> str:
    lines = [
        f"Plan Semanal | {week_plan.week_start.isoformat()} -> {week_plan.week_end.isoformat()}",
        f"reference_date={week_plan.reference_date.isoformat()}",
        "",
    ]
    for day in week_plan.days:
        lines.append(f"{day.date.isoformat()} | {day.weekday_label} | tasks={day.total_tasks}")
        if not day.tasks:
            lines.append("- sin tareas")
        else:
            for task in day.tasks:
                lines.append(
                    f"- priority={task.priority} | {task.competition_slug} | "
                    f"{task.planning_type} -> {task.target_content_type}"
                )
        lines.append("")
    return "\n".join(lines).rstrip()


def render_campaign_generation_result(result: EditorialCampaignGenerationResult) -> str:
    lines = [
        f"Generacion Planificada | {result.date.isoformat()} ({result.weekday_label})",
        f"total_tasks={result.total_tasks}",
        f"total_generated={result.total_generated}",
        f"total_inserted={result.total_inserted}",
        f"total_updated={result.total_updated}",
    ]
    if not result.rows:
        lines.append("sin tareas generadas")
        return "\n".join(lines)

    lines.append("")
    for row in result.rows:
        lines.append(
            f"- priority={row.task.priority} | {row.task.competition_slug} | "
            f"{row.task.planning_type} -> {row.task.target_content_type} | "
            f"selected={row.generated_count} | inserted={row.stats.inserted} | updated={row.stats.updated}"
        )
        for excerpt in row.excerpts:
            lines.append(f"  {excerpt}")
    return "\n".join(lines)
