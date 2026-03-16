from __future__ import annotations

from collections import Counter

from app.schemas.editorial_content import ContentGenerationResult


def render_content_generation_result(result: ContentGenerationResult) -> str:
    type_counts = Counter(str(candidate.content_type) for candidate in result.candidates)
    lines = [
        f"Generacion Editorial | {result.competition_name} ({result.competition_slug})",
        f"generated_at={result.generated_at.isoformat()}",
        f"summary_hash={result.summary_hash}",
        f"found={result.stats.found}",
        f"inserted={result.stats.inserted}",
        f"updated={result.stats.updated}",
        "",
        "Tipos Generados",
    ]
    for content_type, count in sorted(type_counts.items()):
        lines.append(f"- {content_type}={count}")

    lines.append("")
    lines.append("Borradores")
    for candidate in result.candidates:
        preview = candidate.text_draft.splitlines()[0] if candidate.text_draft else "-"
        lines.append(
            f"- priority={candidate.priority} | type={candidate.content_type} | status={candidate.status} | {preview}"
        )
    return "\n".join(lines)
