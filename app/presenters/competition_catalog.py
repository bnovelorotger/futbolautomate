from __future__ import annotations

from collections.abc import Iterable

from app.schemas.competition_catalog import (
    CompetitionCatalogSeedResult,
    CompetitionCatalogStatusRow,
)


def render_competition_catalog_status(rows: Iterable[CompetitionCatalogStatusRow]) -> str:
    lines: list[str] = []
    for row in rows:
        lines.append(
            f"{row.code} | status={row.catalog_status} | seeded={str(row.seeded_in_db).lower()} | "
            f"matches={row.matches_count} | finished={row.finished_matches_count} | "
            f"scheduled={row.scheduled_matches_count} | standings={row.standings_count} | "
            f"source={row.source_name or '-'} | source_id={row.source_competition_id or '-'}"
        )
    return "\n".join(lines) if lines else "sin competiciones"


def render_competition_catalog_seed_result(result: CompetitionCatalogSeedResult) -> str:
    lines = [
        f"integrated_only={str(result.integrated_only).lower()}",
        f"missing_only={str(result.missing_only).lower()}",
        f"seeded_count={result.seeded_count}",
        f"updated_count={result.updated_count}",
        f"skipped_count={result.skipped_count}",
    ]
    if result.rows:
        lines.append("")
        for row in result.rows:
            lines.append(
                f"- {row.code} | action={row.action} | source={row.source_name or '-'} | source_id={row.source_competition_id or '-'}"
            )
    return "\n".join(lines)
