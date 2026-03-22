from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.editorial_schedule import load_editorial_schedule
from app.core.enums import CompetitionIntegrationStatus, ContentCandidateStatus, EditorialPlanningContent
from app.db.models import ContentCandidate
from app.schemas.system_check import EditorialCompetitionReadinessRow, EditorialReadinessReport
from app.services.competition_catalog_service import CompetitionCatalogService
from app.utils.time import utcnow


class SystemCheckService:
    def __init__(self, session: Session, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.catalog = load_competition_catalog()
        self.schedule = load_editorial_schedule()
        self.competitions = CompetitionCatalogService(session)

    def editorial_readiness(self) -> EditorialReadinessReport:
        integrated_codes = [
            definition.code
            for definition in self.catalog.values()
            if definition.status == CompetitionIntegrationStatus.INTEGRATED
        ]
        catalog_rows = {
            row.code: row
            for row in self.competitions.status(integrated_only=True)
        }
        planned_types = self._planned_types_by_competition()
        rows: list[EditorialCompetitionReadinessRow] = []

        for code in integrated_codes:
            catalog_row = catalog_rows[code]
            weekly_types = planned_types.get(code, [])
            missing_dependencies = self._missing_dependencies_for_weekly_types(catalog_row, weekly_types)
            ready_types = [
                content_type
                for content_type in weekly_types
                if not self._missing_dependencies_for_planning_type(catalog_row, content_type)
            ]
            planner_ready = catalog_row.seeded_in_db and bool(ready_types)

            content_candidates_count = self.session.scalar(
                select(func.count()).select_from(ContentCandidate).where(ContentCandidate.competition_slug == code)
            ) or 0
            pending_export_count = self.session.scalar(
                select(func.count())
                .select_from(ContentCandidate)
                .where(
                    ContentCandidate.competition_slug == code,
                    ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                    ContentCandidate.external_publication_ref.is_(None),
                )
            ) or 0

            rows.append(
                EditorialCompetitionReadinessRow(
                    code=code,
                    name=catalog_row.name,
                    catalog_status=catalog_row.catalog_status,
                    seeded_in_db=catalog_row.seeded_in_db,
                    planner_weekly_types=weekly_types,
                    matches_count=catalog_row.matches_count,
                    finished_matches_count=catalog_row.finished_matches_count,
                    scheduled_matches_count=catalog_row.scheduled_matches_count,
                    standings_count=catalog_row.standings_count,
                    content_candidates_count=content_candidates_count,
                    pending_export_count=pending_export_count,
                    planner_ready=planner_ready,
                    missing_dependencies=missing_dependencies,
                )
            )

        content_candidates_total = self.session.scalar(
            select(func.count()).select_from(ContentCandidate)
        ) or 0
        content_candidates_pending_export = self.session.scalar(
            select(func.count())
            .select_from(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.external_publication_ref.is_(None),
            )
        ) or 0

        return EditorialReadinessReport(
            checked_at=utcnow(),
            integrated_catalog_count=len(integrated_codes),
            seeded_integrated_count=sum(int(row.seeded_in_db) for row in rows),
            planner_ready_count=sum(int(row.planner_ready) for row in rows),
            export_json_ready=True,
            export_json_path=str(self.settings.app_root / "export" / "export_base.json"),
            content_candidates_total=content_candidates_total,
            content_candidates_pending_export=content_candidates_pending_export,
            rows=rows,
        )

    def _planned_types_by_competition(self) -> dict[str, list[EditorialPlanningContent]]:
        mapping: dict[str, list[EditorialPlanningContent]] = defaultdict(list)
        for rules in self.schedule.weekly_plan.values():
            for rule in rules:
                if rule.content_type not in mapping[rule.competition_slug]:
                    mapping[rule.competition_slug].append(rule.content_type)
        return mapping

    def _missing_dependencies_for_weekly_types(
        self,
        catalog_row,
        weekly_types: list[EditorialPlanningContent],
    ) -> list[str]:
        missing_dependencies: list[str] = []
        if not catalog_row.seeded_in_db:
            missing_dependencies.append("competition_seed")
        for content_type in weekly_types:
            for dependency in self._missing_dependencies_for_planning_type(catalog_row, content_type):
                if dependency not in missing_dependencies:
                    missing_dependencies.append(dependency)
        return missing_dependencies

    def _missing_dependencies_for_planning_type(
        self,
        catalog_row,
        content_type: EditorialPlanningContent,
    ) -> list[str]:
        missing_dependencies: list[str] = []
        if not catalog_row.seeded_in_db:
            return ["competition_seed"]
        if content_type in {
            EditorialPlanningContent.LATEST_RESULTS,
            EditorialPlanningContent.RESULTS_ROUNDUP,
            EditorialPlanningContent.STAT_NARRATIVE,
            EditorialPlanningContent.METRIC_NARRATIVE,
            EditorialPlanningContent.VIRAL_STORY,
        } and catalog_row.finished_matches_count == 0:
            missing_dependencies.append("finished_matches")
        if content_type == EditorialPlanningContent.PREVIEW and catalog_row.scheduled_matches_count == 0:
            missing_dependencies.append("scheduled_matches")
        if content_type == EditorialPlanningContent.FEATURED_MATCH_PREVIEW:
            if catalog_row.scheduled_matches_count == 0:
                missing_dependencies.append("scheduled_matches")
            if catalog_row.standings_count == 0:
                missing_dependencies.append("standings")
        if content_type in {
            EditorialPlanningContent.STANDINGS,
            EditorialPlanningContent.STANDINGS_ROUNDUP,
            EditorialPlanningContent.RANKING,
            EditorialPlanningContent.METRIC_NARRATIVE,
        } and catalog_row.standings_count == 0:
            missing_dependencies.append("standings")
        return missing_dependencies
