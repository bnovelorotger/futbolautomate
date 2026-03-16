from __future__ import annotations

from app.schemas.match_importance import MatchImportanceGenerationResult, MatchImportanceResult


def render_match_importance(result: MatchImportanceResult) -> str:
    lines = [
        f"Match Importance | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"generated_at={result.generated_at.isoformat()}",
        f"count={len(result.rows)}",
    ]
    if not result.rows:
        lines.append("sin partidos destacados detectados")
        return "\n".join(lines)

    lines.append("")
    for row in result.rows:
        lines.append(
            f"- score={row.importance_score} | {row.home_team} vs {row.away_team} | "
            f"date={row.match_date.isoformat() if row.match_date else '-'} | "
            f"tags={','.join(row.tags) if row.tags else '-'} | reasons={','.join(row.score_reasoning) if row.score_reasoning else '-'}"
        )
    return "\n".join(lines)


def render_match_importance_generation(result: MatchImportanceGenerationResult) -> str:
    header = [
        f"Match Importance | {result.competition_name} ({result.competition_slug})",
        f"reference_date={result.reference_date.isoformat()}",
        f"generated_at={result.generated_at.isoformat()}",
        f"found={result.stats.found}",
        f"inserted={result.stats.inserted}",
        f"updated={result.stats.updated}",
    ]
    if not result.generated_candidates:
        header.append("sin drafts generados")
        return "\n".join(header)

    lines = header + ["", f"generated_candidates={len(result.generated_candidates)}", ""]
    for candidate in result.generated_candidates:
        lines.append(
            f"- priority={candidate.priority} | type={candidate.content_type} | "
            f"{candidate.home_team} vs {candidate.away_team} | score={candidate.importance_score} | "
            f"tags={','.join(candidate.tags) if candidate.tags else '-'} | {candidate.text_draft}"
        )
    return "\n".join(lines)
