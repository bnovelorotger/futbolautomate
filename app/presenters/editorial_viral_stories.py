from __future__ import annotations

from app.schemas.editorial_viral_stories import (
    EditorialViralStoriesGenerationResult,
    EditorialViralStoriesResult,
)


def render_editorial_viral_stories(result: EditorialViralStoriesResult) -> str:
    lines = [
        f"Historias Virales | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"generated_at={result.generated_at.isoformat()}",
        f"count={len(result.rows)}",
    ]
    if not result.rows:
        lines.append("sin historias virales disponibles")
        return "\n".join(lines)

    lines.append("")
    for row in result.rows:
        teams = ", ".join(row.teams) if row.teams else "-"
        metric_value = row.metric_value if row.metric_value is not None else "-"
        lines.append(
            f"- priority={row.priority} | type={row.story_type} | title={row.title} | "
            f"teams={teams} | value={metric_value} | {row.text_draft}"
        )
    return "\n".join(lines)


def render_editorial_viral_stories_generation(
    result: EditorialViralStoriesGenerationResult,
) -> str:
    header = [
        f"Historias Virales | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"generated_at={result.generated_at.isoformat()}",
        f"found={result.stats.found}",
        f"inserted={result.stats.inserted}",
        f"updated={result.stats.updated}",
    ]
    if not result.rows:
        header.append("sin historias virales generadas")
        return "\n".join(header)
    return "\n".join(header) + "\n\n" + render_editorial_viral_stories(result)
