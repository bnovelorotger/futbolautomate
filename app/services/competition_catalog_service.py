from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.catalog import CompetitionDefinition, load_competition_catalog
from app.core.enums import CompetitionIntegrationStatus
from app.db.models import Competition, Match, Standing
from app.db.repositories.competitions import CompetitionRepository
from app.normalizers.text import normalize_token
from app.schemas.competition_catalog import (
    CompetitionCatalogSeedResult,
    CompetitionCatalogSeedRow,
    CompetitionCatalogStatusRow,
)


class CompetitionCatalogService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CompetitionRepository(session)
        self.catalog = load_competition_catalog()

    def status(
        self,
        *,
        integrated_only: bool = False,
        codes: list[str] | None = None,
    ) -> list[CompetitionCatalogStatusRow]:
        rows: list[CompetitionCatalogStatusRow] = []
        for definition in self._definitions(integrated_only=integrated_only, codes=codes):
            competition = self.repository.get_by_code(definition.code)
            if competition is None:
                rows.append(
                    CompetitionCatalogStatusRow(
                        code=definition.code,
                        name=definition.editorial_name or definition.name,
                        catalog_status=definition.status,
                        seeded_in_db=False,
                        source_name=self._source_name(definition),
                        source_competition_id=self._source_competition_id(definition),
                    )
                )
                continue
            rows.append(
                CompetitionCatalogStatusRow(
                    code=definition.code,
                    name=definition.editorial_name or definition.name,
                    catalog_status=definition.status,
                    seeded_in_db=True,
                    source_name=competition.source_name,
                    source_competition_id=competition.source_competition_id,
                    matches_count=self._match_count(competition.id),
                    finished_matches_count=self._match_count(competition.id, status="finished"),
                    scheduled_matches_count=self._match_count(competition.id, status="scheduled"),
                    standings_count=self._standings_count(competition.id),
                )
            )
        return rows

    def seed_competitions(
        self,
        *,
        integrated_only: bool = False,
        missing_only: bool = False,
        codes: list[str] | None = None,
    ) -> CompetitionCatalogSeedResult:
        rows: list[CompetitionCatalogSeedRow] = []
        seeded_count = 0
        updated_count = 0
        skipped_count = 0
        for definition in self._definitions(integrated_only=integrated_only, codes=codes):
            existing = self.repository.get_by_code(definition.code)
            if existing is not None and missing_only:
                skipped_count += 1
                rows.append(
                    CompetitionCatalogSeedRow(
                        code=definition.code,
                        name=definition.editorial_name or definition.name,
                        action="skipped_existing",
                        source_name=existing.source_name,
                        source_competition_id=existing.source_competition_id,
                    )
                )
                continue

            payload = self._payload(definition)
            self.repository.create_or_update(**payload)
            if existing is None:
                seeded_count += 1
                action = "created"
            else:
                updated_count += 1
                action = "updated"
            rows.append(
                CompetitionCatalogSeedRow(
                    code=definition.code,
                    name=definition.editorial_name or definition.name,
                    action=action,
                    source_name=payload["source_name"],
                    source_competition_id=payload["source_competition_id"],
                )
            )

        return CompetitionCatalogSeedResult(
            integrated_only=integrated_only,
            missing_only=missing_only,
            seeded_count=seeded_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            rows=rows,
        )

    def _definitions(
        self,
        *,
        integrated_only: bool,
        codes: list[str] | None,
    ) -> list[CompetitionDefinition]:
        definitions = list(self.catalog.values())
        if integrated_only:
            definitions = [
                definition
                for definition in definitions
                if definition.status == CompetitionIntegrationStatus.INTEGRATED
            ]
        if codes:
            requested = set(codes)
            definitions = [definition for definition in definitions if definition.code in requested]
        return sorted(definitions, key=lambda item: (item.priority, item.code))

    def _payload(self, definition: CompetitionDefinition) -> dict:
        return {
            "code": definition.code,
            "name": definition.name,
            "normalized_name": normalize_token(definition.name),
            "category_level": definition.category_level,
            "gender": str(definition.gender),
            "region": definition.region,
            "country": definition.country,
            "federation": definition.federation,
            "source_name": self._source_name(definition),
            "source_competition_id": self._source_competition_id(definition),
        }

    def _source_name(self, definition: CompetitionDefinition) -> str | None:
        source_name = None
        if definition.primary_source:
            for candidate_name, candidate_mapping in definition.sources.items():
                if str(candidate_name) == definition.primary_source and candidate_mapping.enabled:
                    source_name = str(candidate_name)
                    break
        if source_name is not None:
            return source_name
        for candidate_name, candidate_mapping in definition.sources.items():
            if candidate_mapping.enabled:
                return str(candidate_name)
        return None

    def _source_competition_id(self, definition: CompetitionDefinition) -> str | None:
        preferred = self._source_name(definition)
        if preferred is None:
            return None
        for candidate_name, candidate_mapping in definition.sources.items():
            if str(candidate_name) == preferred:
                return candidate_mapping.competition_id
        return None

    def _match_count(self, competition_id: int, *, status: str | None = None) -> int:
        query = select(func.count()).select_from(Match).where(Match.competition_id == competition_id)
        if status is not None:
            query = query.where(Match.status == status)
        return self.session.scalar(query) or 0

    def _standings_count(self, competition_id: int) -> int:
        return self.session.scalar(
            select(func.count()).select_from(Standing).where(Standing.competition_id == competition_id)
        ) or 0
