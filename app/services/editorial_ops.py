from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.orm import Session

from app.core.enums import ContentType, EditorialPlanningContent
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.editorial_ops import (
    EditorialOpsPreviewResult,
    EditorialOpsRunResult,
    EditorialOpsTaskPreview,
    EditorialOpsTaskRunResult,
)
from app.schemas.editorial_planner import EditorialCampaignTask
from app.services.editorial_narratives import EditorialNarrativesService
from app.services.editorial_phase import EditorialPhaseService
from app.services.editorial_planner import EditorialPlannerService
from app.services.editorial_viral_stories import EditorialViralStoriesService
from app.services.match_importance import MatchImportanceService
from app.services.playoff_editorial import PlayoffEditorialService
from app.services.results_roundup import ResultsRoundupService
from app.services.season_wrap_editorial import SeasonWrapEditorialService
from app.services.standings_roundup import StandingsRoundupService
from app.services.system_check import SystemCheckService


@dataclass(slots=True)
class _TaskEvaluation:
    task: EditorialCampaignTask
    candidates: list[ContentCandidateDraft] = field(default_factory=list)
    missing_dependencies: list[str] = field(default_factory=list)


class EditorialOperationsService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.planner = EditorialPlannerService(session)
        self.results_roundup = ResultsRoundupService(session)
        self.standings_roundup = StandingsRoundupService(session)
        self.narratives = EditorialNarrativesService(session)
        self.viral_stories = EditorialViralStoriesService(session)
        self.match_importance = MatchImportanceService(session)
        self.phase_service = EditorialPhaseService(session)
        self.playoff_editorial = PlayoffEditorialService(session)
        self.season_wrap_editorial = SeasonWrapEditorialService(session)
        self.system_check = SystemCheckService(session)

    def preview_day(self, target_date: date) -> EditorialOpsPreviewResult:
        evaluations = self._evaluate_day(target_date)
        return EditorialOpsPreviewResult(
            date=target_date,
            total_tasks=len(evaluations),
            ready_tasks=sum(int(not item.missing_dependencies) for item in evaluations),
            blocked_tasks=sum(int(bool(item.missing_dependencies)) for item in evaluations),
            expected_total=sum(len(item.candidates) for item in evaluations),
            rows=[
                EditorialOpsTaskPreview(
                    competition_slug=item.task.competition_slug,
                    competition_name=item.task.competition_name,
                    planning_type=item.task.planning_type,
                    target_content_type=item.task.target_content_type,
                    priority=item.task.priority,
                    expected_count=len(item.candidates),
                    missing_dependencies=item.missing_dependencies,
                    excerpts=[self._excerpt(candidate.text_draft) for candidate in item.candidates[:3]],
                )
                for item in evaluations
            ],
        )

    def run_day(self, target_date: date) -> EditorialOpsRunResult:
        evaluations = self._evaluate_day(target_date)
        rows: list[EditorialOpsTaskRunResult] = []
        for item in evaluations:
            if item.missing_dependencies:
                rows.append(
                    EditorialOpsTaskRunResult(
                        competition_slug=item.task.competition_slug,
                        competition_name=item.task.competition_name,
                        planning_type=item.task.planning_type,
                        target_content_type=item.task.target_content_type,
                        priority=item.task.priority,
                        generated_count=0,
                        inserted=0,
                        updated=0,
                        missing_dependencies=item.missing_dependencies,
                        excerpts=[],
                    )
                )
                continue

            if item.task.planning_type == EditorialPlanningContent.METRIC_NARRATIVE:
                stats = self.narratives.store_candidates(item.candidates)
            elif item.task.planning_type == EditorialPlanningContent.VIRAL_STORY:
                stats = self.viral_stories.store_candidates(item.candidates)
            else:
                stats = self.planner.generator.store_candidates(item.candidates)
            rows.append(
                EditorialOpsTaskRunResult(
                    competition_slug=item.task.competition_slug,
                    competition_name=item.task.competition_name,
                    planning_type=item.task.planning_type,
                    target_content_type=item.task.target_content_type,
                    priority=item.task.priority,
                    generated_count=len(item.candidates),
                    inserted=stats.inserted,
                    updated=stats.updated,
                    missing_dependencies=[],
                    excerpts=[self._excerpt(candidate.text_draft) for candidate in item.candidates[:3]],
                )
            )

        return EditorialOpsRunResult(
            date=target_date,
            total_tasks=len(evaluations),
            generated_total=sum(row.generated_count for row in rows),
            inserted_total=sum(row.inserted for row in rows),
            updated_total=sum(row.updated for row in rows),
            blocked_tasks=sum(int(bool(row.missing_dependencies)) for row in rows),
            rows=rows,
        )

    def _evaluate_day(self, target_date: date) -> list[_TaskEvaluation]:
        plan = self.planner.plan_for_date(target_date)
        readiness = {row.code: row for row in self.system_check.editorial_readiness(reference_date=target_date).rows}
        candidate_cache: dict[tuple[str, str], list[ContentCandidateDraft]] = {}
        evaluations: list[_TaskEvaluation] = []

        for task in plan.tasks:
            readiness_row = readiness.get(task.competition_slug)
            missing = self._task_missing_dependencies(task, readiness_row)
            key = (task.competition_slug, str(task.planning_type))
            if task.planning_type == EditorialPlanningContent.RESULTS_ROUNDUP:
                if not missing:
                    candidate_cache[key] = self.results_roundup.build_candidate_drafts(
                        task.competition_slug,
                        reference_date=target_date,
                    )
            elif task.planning_type == EditorialPlanningContent.STANDINGS_ROUNDUP:
                if not missing:
                    candidate_cache[key] = self.standings_roundup.build_candidate_drafts(
                        task.competition_slug,
                        reference_date=target_date,
                    )
            elif task.planning_type == EditorialPlanningContent.METRIC_NARRATIVE:
                if not missing:
                    candidate_cache[key] = self.narratives.build_candidate_drafts(
                        task.competition_slug,
                        reference_date=target_date,
                    )
            elif task.planning_type == EditorialPlanningContent.FEATURED_MATCH_PREVIEW:
                if not missing:
                    if self.phase_service.is_playoff_competition(task.competition_slug):
                        candidate_cache[key] = self.playoff_editorial.build_featured_preview_drafts(
                            task.competition_slug,
                            reference_date=target_date,
                            limit=1,
                        )
                    else:
                        candidate_cache[key] = self.match_importance.build_candidate_drafts(
                            task.competition_slug,
                            reference_date=target_date,
                            limit=1,
                        )
            elif task.planning_type == EditorialPlanningContent.MATCH_IMPACT_SCENARIO:
                if not missing:
                    candidate_cache[key] = self.planner._build_match_impact_candidates(
                        task.competition_slug,
                        reference_date=target_date,
                    )
            elif task.planning_type == EditorialPlanningContent.RACE_NARRATIVE:
                if not missing:
                    candidate_cache[key] = self.planner._build_race_narrative_candidates(
                        task.competition_slug,
                        reference_date=target_date,
                    )
            elif task.planning_type == EditorialPlanningContent.MILESTONE_STORY:
                if not missing:
                    candidate_cache[key] = self.planner._build_milestone_candidates(
                        task.competition_slug,
                        reference_date=target_date,
                    )
            elif task.planning_type == EditorialPlanningContent.TOP_SCORER_UPDATE:
                if not missing:
                    candidate_cache[key] = self.planner._build_top_scorer_candidates(
                        task.competition_slug,
                        reference_date=target_date,
                    )
            elif task.planning_type == EditorialPlanningContent.VIRAL_STORY:
                if not missing:
                    candidate_cache[key] = self.viral_stories.build_candidate_drafts(
                        task.competition_slug,
                        reference_date=target_date,
                    )
            elif task.planning_type == EditorialPlanningContent.SEASON_WRAP_STATS:
                if not missing:
                    candidate_cache[key] = self.season_wrap_editorial.build_stats_drafts(
                        task.competition_slug,
                        reference_date=target_date,
                    )
            elif task.planning_type == EditorialPlanningContent.SEASON_WRAP_OUTCOMES:
                if not missing:
                    candidate_cache[key] = self.season_wrap_editorial.build_outcome_drafts(
                        task.competition_slug,
                        reference_date=target_date,
                    )
            elif task.planning_type == EditorialPlanningContent.PLAYOFF_BRACKET:
                if not missing:
                    candidate_cache[key] = self.playoff_editorial.build_bracket_drafts(
                        task.competition_slug,
                        reference_date=target_date,
                    )
            else:
                if not missing:
                    generated_key = (task.competition_slug, "standard")
                    if generated_key not in candidate_cache:
                        candidate_cache[generated_key] = self.planner._generate_competition_candidates(
                            task.competition_slug,
                            reference_date=target_date,
                        )
                    candidate_cache[key] = [
                        candidate
                        for candidate in candidate_cache[generated_key]
                        if candidate.content_type == self._target_content_type(task.planning_type)
                    ]
            candidates = candidate_cache.get(key, [])
            if not candidates and not missing:
                missing = self._infer_missing_dependencies(task, readiness_row)
            evaluations.append(
                _TaskEvaluation(
                    task=task,
                    candidates=candidates,
                    missing_dependencies=missing,
                )
            )
        return evaluations

    def _infer_missing_dependencies(
        self,
        task: EditorialCampaignTask,
        readiness_row,
    ) -> list[str]:
        if readiness_row is None:
            return ["competition_seed"]
        if not readiness_row.seeded_in_db:
            return ["competition_seed"]
        configured_missing = self.system_check.missing_dependencies_for_planning_type(
            readiness_row,
            task.planning_type,
        )
        if configured_missing:
            return configured_missing
        if task.planning_type == EditorialPlanningContent.TOP_SCORER_UPDATE:
            return ["signal_threshold"]
        return ["no_candidates_available"]

    def _task_missing_dependencies(
        self,
        task: EditorialCampaignTask,
        readiness_row,
    ) -> list[str]:
        if readiness_row is None or not readiness_row.seeded_in_db:
            return ["competition_seed"]
        return self.system_check.missing_dependencies_for_planning_type(
            readiness_row,
            task.planning_type,
        )

    def _target_content_type(self, planning_type: EditorialPlanningContent) -> ContentType:
        return {
            EditorialPlanningContent.LATEST_RESULTS: ContentType.MATCH_RESULT,
            EditorialPlanningContent.RESULTS_ROUNDUP: ContentType.RESULTS_ROUNDUP,
            EditorialPlanningContent.STANDINGS: ContentType.STANDINGS,
            EditorialPlanningContent.STANDINGS_ROUNDUP: ContentType.STANDINGS_ROUNDUP,
            EditorialPlanningContent.PREVIEW: ContentType.PREVIEW,
            EditorialPlanningContent.FEATURED_MATCH_PREVIEW: ContentType.FEATURED_MATCH_PREVIEW,
            EditorialPlanningContent.MATCH_IMPACT_SCENARIO: ContentType.MATCH_IMPACT_SCENARIO,
            EditorialPlanningContent.RANKING: ContentType.RANKING,
            EditorialPlanningContent.STAT_NARRATIVE: ContentType.STAT_NARRATIVE,
            EditorialPlanningContent.METRIC_NARRATIVE: ContentType.METRIC_NARRATIVE,
            EditorialPlanningContent.RACE_NARRATIVE: ContentType.RACE_NARRATIVE,
            EditorialPlanningContent.MILESTONE_STORY: ContentType.MILESTONE_STORY,
            EditorialPlanningContent.TOP_SCORER_UPDATE: ContentType.TOP_SCORER_UPDATE,
            EditorialPlanningContent.VIRAL_STORY: ContentType.VIRAL_STORY,
            EditorialPlanningContent.SEASON_WRAP_STATS: ContentType.SEASON_WRAP_STATS,
            EditorialPlanningContent.SEASON_WRAP_OUTCOMES: ContentType.SEASON_WRAP_OUTCOMES,
            EditorialPlanningContent.PLAYOFF_BRACKET: ContentType.PLAYOFF_BRACKET,
        }[planning_type]

    def _excerpt(self, text: str, limit: int = 110) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."
