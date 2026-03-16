from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.editorial_schedule import (
    editorial_weekday_for_date,
    editorial_weekday_label,
    load_editorial_schedule,
    normalize_editorial_schedule,
)
from app.core.enums import ContentType, EditorialPlanningContent
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.editorial_summary import CompetitionEditorialSummary
from app.schemas.editorial_planner import (
    EditorialCampaignGenerationResult,
    EditorialCampaignPlan,
    EditorialCampaignTask,
    EditorialGeneratedTaskResult,
    EditorialWeekPlan,
    EditorialWeeklySchedule,
)
from app.services.editorial_content_generator import EditorialContentGenerator
from app.services.editorial_narratives import EditorialNarrativesService
from app.services.editorial_viral_stories import EditorialViralStoriesService

_PLANNING_CONTENT_MAP = {
    EditorialPlanningContent.LATEST_RESULTS: ContentType.MATCH_RESULT,
    EditorialPlanningContent.STANDINGS: ContentType.STANDINGS,
    EditorialPlanningContent.PREVIEW: ContentType.PREVIEW,
    EditorialPlanningContent.RANKING: ContentType.RANKING,
    EditorialPlanningContent.STAT_NARRATIVE: ContentType.STAT_NARRATIVE,
    EditorialPlanningContent.METRIC_NARRATIVE: ContentType.METRIC_NARRATIVE,
    EditorialPlanningContent.VIRAL_STORY: ContentType.VIRAL_STORY,
}


def _excerpt(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _matches_planning_type(
    candidate: ContentCandidateDraft,
    planning_type: EditorialPlanningContent,
) -> bool:
    return candidate.content_type == _PLANNING_CONTENT_MAP[planning_type]


class EditorialPlannerService:
    def __init__(
        self,
        session: Session,
        schedule: EditorialWeeklySchedule | None = None,
        settings: Settings | None = None,
        generator: EditorialContentGenerator | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.schedule = normalize_editorial_schedule(schedule) if schedule is not None else load_editorial_schedule()
        self.generator = generator or EditorialContentGenerator(session)
        self.narratives = EditorialNarrativesService(session)
        self.viral_stories = EditorialViralStoriesService(session)
        self.competition_catalog = load_competition_catalog()

    def today(self) -> date:
        timezone_name = self.schedule.timezone or self.settings.timezone
        return datetime.now(ZoneInfo(timezone_name)).date()

    def list_tasks_for_date(self, target_date: date | None = None) -> list[EditorialCampaignTask]:
        return self.plan_for_date(target_date).tasks

    def plan_for_date(self, target_date: date | None = None) -> EditorialCampaignPlan:
        selected_date = target_date or self.today()
        weekday_key = editorial_weekday_for_date(selected_date)
        weekday_label = editorial_weekday_label(weekday_key)
        rules = sorted(
            self.schedule.rules_for_weekday(weekday_key),
            key=lambda item: (-item.priority, item.competition_slug, str(item.content_type)),
        )
        tasks = [
            EditorialCampaignTask(
                date=selected_date,
                weekday_key=weekday_key,
                weekday_label=weekday_label,
                competition_slug=rule.competition_slug,
                competition_name=self._competition_name(rule.competition_slug),
                planning_type=rule.content_type,
                target_content_type=_PLANNING_CONTENT_MAP[rule.content_type],
                priority=rule.priority,
            )
            for rule in rules
        ]
        return EditorialCampaignPlan(
            date=selected_date,
            weekday_key=weekday_key,
            weekday_label=weekday_label,
            total_tasks=len(tasks),
            tasks=tasks,
        )

    def week_plan(self, reference_date: date | None = None) -> EditorialWeekPlan:
        selected_date = reference_date or self.today()
        week_start = selected_date - timedelta(days=selected_date.weekday())
        days = [self.plan_for_date(week_start + timedelta(days=index)) for index in range(7)]
        return EditorialWeekPlan(
            reference_date=selected_date,
            week_start=week_start,
            week_end=week_start + timedelta(days=6),
            days=days,
        )

    def generate_for_date(self, target_date: date | None = None) -> EditorialCampaignGenerationResult:
        plan = self.plan_for_date(target_date)
        grouped_tasks: dict[str, list[EditorialCampaignTask]] = defaultdict(list)
        for task in plan.tasks:
            grouped_tasks[task.competition_slug].append(task)

        rows: list[EditorialGeneratedTaskResult] = []
        generated_content_cache: dict[str, list[ContentCandidateDraft]] = {}
        generated_narratives_cache: dict[str, list[ContentCandidateDraft]] = {}
        generated_viral_cache: dict[str, list[ContentCandidateDraft]] = {}
        for competition_slug in sorted(grouped_tasks):
            for task in grouped_tasks[competition_slug]:
                if task.planning_type == EditorialPlanningContent.METRIC_NARRATIVE:
                    if competition_slug not in generated_narratives_cache:
                        generated_narratives_cache[competition_slug] = self.narratives.build_candidate_drafts(
                            competition_slug,
                            reference_date=plan.date,
                        )
                        self._validate_candidates_for_competition(
                            competition_slug,
                            generated_narratives_cache[competition_slug],
                        )
                    selected_candidates = generated_narratives_cache[competition_slug]
                    stats = self.narratives.store_candidates(selected_candidates)
                elif task.planning_type == EditorialPlanningContent.VIRAL_STORY:
                    if competition_slug not in generated_viral_cache:
                        generated_viral_cache[competition_slug] = self.viral_stories.build_candidate_drafts(
                            competition_slug,
                            reference_date=plan.date,
                        )
                        self._validate_candidates_for_competition(
                            competition_slug,
                            generated_viral_cache[competition_slug],
                        )
                    selected_candidates = generated_viral_cache[competition_slug]
                    stats = self.viral_stories.store_candidates(selected_candidates)
                else:
                    if competition_slug not in generated_content_cache:
                        generated_content_cache[competition_slug] = self._generate_competition_candidates(
                            competition_slug,
                            reference_date=plan.date,
                        )
                    selected_candidates = [
                        candidate
                        for candidate in generated_content_cache[competition_slug]
                        if _matches_planning_type(candidate, task.planning_type)
                    ]
                    self._validate_candidates_for_competition(competition_slug, selected_candidates)
                    stats = self.generator.store_candidates(selected_candidates)
                rows.append(
                    EditorialGeneratedTaskResult(
                        task=task,
                        generated_count=len(selected_candidates),
                        stats=stats,
                        excerpts=[_excerpt(candidate.text_draft) for candidate in selected_candidates[:3]],
                    )
                )

        return EditorialCampaignGenerationResult(
            date=plan.date,
            weekday_key=plan.weekday_key,
            weekday_label=plan.weekday_label,
            total_tasks=plan.total_tasks,
            total_generated=sum(row.generated_count for row in rows),
            total_inserted=sum(row.stats.inserted for row in rows),
            total_updated=sum(row.stats.updated for row in rows),
            rows=rows,
        )

    def _competition_name(self, competition_slug: str) -> str:
        competition = self.competition_catalog.get(competition_slug)
        if competition is None:
            return competition_slug
        return competition.editorial_name or competition.name

    def _generate_competition_candidates(
        self,
        competition_slug: str,
        *,
        reference_date: date,
    ) -> list[ContentCandidateDraft]:
        summary = self.generator.summary_service.build_competition_summary(
            competition_code=competition_slug,
            reference_date=reference_date,
        )
        self._validate_summary_competition(competition_slug, summary)
        candidates = self.generator.generate_from_summary(summary)
        self._validate_candidates_for_competition(competition_slug, candidates)
        return candidates

    def _validate_summary_competition(
        self,
        competition_slug: str,
        summary: CompetitionEditorialSummary,
    ) -> None:
        if summary.metadata.competition_slug != competition_slug:
            raise ValueError(
                "El resumen editorial devuelto no corresponde a la competicion pedida: "
                f"esperado={competition_slug} recibido={summary.metadata.competition_slug}"
            )

    def _validate_candidates_for_competition(
        self,
        competition_slug: str,
        candidates: list[ContentCandidateDraft],
    ) -> None:
        mismatched = [
            candidate.competition_slug
            for candidate in candidates
            if candidate.competition_slug != competition_slug
        ]
        if mismatched:
            raise ValueError(
                "Se detecto mezcla de competiciones en los candidatos generados: "
                f"esperado={competition_slug} recibidos={sorted(set(mismatched))}"
            )
