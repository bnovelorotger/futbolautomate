from __future__ import annotations

from pydantic import BaseModel

from app.core.enums import CompetitionIntegrationStatus


class CompetitionCatalogStatusRow(BaseModel):
    code: str
    name: str
    catalog_status: CompetitionIntegrationStatus
    seeded_in_db: bool
    source_name: str | None = None
    source_competition_id: str | None = None
    matches_count: int = 0
    finished_matches_count: int = 0
    scheduled_matches_count: int = 0
    standings_count: int = 0


class CompetitionCatalogSeedRow(BaseModel):
    code: str
    name: str
    action: str
    source_name: str | None = None
    source_competition_id: str | None = None


class CompetitionCatalogSeedResult(BaseModel):
    integrated_only: bool
    missing_only: bool
    seeded_count: int
    updated_count: int
    skipped_count: int
    rows: list[CompetitionCatalogSeedRow]
