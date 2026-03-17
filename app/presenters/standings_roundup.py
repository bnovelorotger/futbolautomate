from __future__ import annotations

from app.schemas.standings_roundup import StandingsRoundupGenerationResult, StandingsRoundupPreviewResult


def render_standings_roundup(result: StandingsRoundupPreviewResult) -> str:
    lines = [
        f"Standings Roundup | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"generated_at={result.generated_at.isoformat()}",
        f"group_label={result.group_label or '-'}",
        f"selected_rows_count={result.selected_rows_count}",
        f"omitted_rows_count={result.omitted_rows_count}",
        f"max_characters={result.max_characters}",
    ]
    if not result.text_draft:
        lines.append("sin roundup disponible")
        return "\n".join(lines)
    lines.extend(["", result.text_draft])
    return "\n".join(lines)


def render_standings_roundup_generation(result: StandingsRoundupGenerationResult) -> str:
    lines = [
        f"Standings Roundup | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"generated_at={result.generated_at.isoformat()}",
        f"group_label={result.group_label or '-'}",
        f"selected_rows_count={result.selected_rows_count}",
        f"omitted_rows_count={result.omitted_rows_count}",
        f"found={result.stats.found}",
        f"inserted={result.stats.inserted}",
        f"updated={result.stats.updated}",
    ]
    if not result.generated_candidates:
        lines.append("sin drafts generados")
        return "\n".join(lines)
    lines.append("")
    for candidate in result.generated_candidates:
        lines.append(
            f"- priority={candidate.priority} | type={candidate.content_type} | "
            f"group={candidate.group_label or '-'} | rows={candidate.selected_rows_count} | omitted={candidate.omitted_rows_count}"
        )
        lines.append(f"  {candidate.text_draft}")
    return "\n".join(lines)
