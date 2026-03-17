from __future__ import annotations

from app.schemas.story_importance import StoryImportanceListResult, StoryImportanceScoreResult


def render_story_importance_list(title: str, result: StoryImportanceListResult) -> str:
    lines = [
        title,
        f"reference_date={result.reference_date.isoformat() if result.reference_date else '-'}",
        f"generated_at={result.generated_at.isoformat()}",
        f"count={len(result.rows)}",
    ]
    if not result.rows:
        lines.append("sin candidatos puntuados")
        return "\n".join(lines)

    lines.append("")
    for row in result.rows:
        lines.append(
            f"- id={row.candidate_id} | score={row.importance_score} | bucket={row.priority_bucket} | "
            f"{row.competition_slug} | {row.content_type} | status={row.status} | "
            f"tags={','.join(row.tags) if row.tags else '-'} | "
            f"reasons={','.join(row.importance_reasoning) if row.importance_reasoning else '-'} | "
            f"{row.excerpt}"
        )
    return "\n".join(lines)


def render_story_importance_score(result: StoryImportanceScoreResult) -> str:
    row = result.candidate
    return "\n".join(
        [
            "Story Importance Score",
            f"generated_at={result.generated_at.isoformat()}",
            f"candidate_id={row.candidate_id}",
            f"competition_slug={row.competition_slug}",
            f"content_type={row.content_type}",
            f"status={row.status}",
            f"current_priority={row.current_priority}",
            f"importance_score={row.importance_score}",
            f"priority_bucket={row.priority_bucket}",
            f"tags={','.join(row.tags) if row.tags else '-'}",
            f"importance_reasoning={','.join(row.importance_reasoning) if row.importance_reasoning else '-'}",
            f"excerpt={row.excerpt}",
        ]
    )
