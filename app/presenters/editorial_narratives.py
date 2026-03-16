from __future__ import annotations

from app.schemas.editorial_narratives import (
    EditorialNarrativesGenerationResult,
    EditorialNarrativesResult,
)


def render_editorial_narratives(result: EditorialNarrativesResult) -> str:
    lines = [
        f"Narrativas Editoriales | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"generated_at={result.generated_at.isoformat()}",
        f"count={len(result.rows)}",
    ]
    if not result.rows:
        lines.append("sin narrativas disponibles")
        return "\n".join(lines)

    lines.append("")
    for row in result.rows:
        metric_value = row.metric_value if row.metric_value is not None else "-"
        lines.append(
            f"- priority={row.priority} | type={row.narrative_type} | team={row.team or '-'} | "
            f"value={metric_value} | {row.text_draft}"
        )
    return "\n".join(lines)


def render_editorial_narratives_generation(
    result: EditorialNarrativesGenerationResult,
) -> str:
    header = [
        f"Narrativas Editoriales | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"generated_at={result.generated_at.isoformat()}",
        f"found={result.stats.found}",
        f"inserted={result.stats.inserted}",
        f"updated={result.stats.updated}",
    ]
    if not result.rows:
        header.append("sin narrativas generadas")
        return "\n".join(header)
    return "\n".join(header) + "\n\n" + render_editorial_narratives(result)
