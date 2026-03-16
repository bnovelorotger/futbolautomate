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
from app.services.editorial_planner import EditorialPlannerService
from app.services.editorial_viral_stories import EditorialViralStoriesService
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
        self.narratives = EditorialNarrativesService(session)
        self.viral_stories = EditorialViralStoriesService(session)
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
        readiness = {
            row.code: row
            for row in self.system_check.editorial_readiness().rows
        }
        candidate_cache: dict[tuple[str, str], list[ContentCandidateDraft]] = {}
        evaluations: list[_TaskEvaluation] = []

        for task in plan.tasks:
            readiness_row = readiness.get(task.competition_slug)
            missing = self._task_missing_dependencies(task, readiness_row)
            key = (task.competition_slug, str(task.planning_type))
            if task.planning_type == EditorialPlanningContent.METRIC_NARRATIVE:
                if not missing:
                    candidate_cache[key] = self.narratives.build_candidate_drafts(
                        task.competition_slug,
                        reference_date=target_date,
                    )
            elif task.planning_type == EditorialPlanningContent.VIRAL_STORY:
                if not missing:
                    candidate_cache[key] = self.viral_stories.build_candidate_drafts(
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
        if task.planning_type in {
            EditorialPlanningContent.LATEST_RESULTS,
            EditorialPlanningContent.STAT_NARRATIVE,
            EditorialPlanningContent.METRIC_NARRATIVE,
            EditorialPlanningContent.VIRAL_STORY,
        } and readiness_row.finished_matches_count == 0:
            return ["finished_matches"]
        if task.planning_type == EditorialPlanningContent.PREVIEW and readiness_row.scheduled_matches_count == 0:
            return ["scheduled_matches"]
        if task.planning_type in {
            EditorialPlanningContent.STANDINGS,
            EditorialPlanningContent.RANKING,
        } and readiness_row.standings_count == 0:
            return ["standings"]
        return ["no_candidates_available"]

    def _task_missing_dependencies(
        self,
        task: EditorialCampaignTask,
        readiness_row,
    ) -> list[str]:
        if readiness_row is None or not readiness_row.seeded_in_db:
            return ["competition_seed"]
        if task.planning_type in {
            EditorialPlanningContent.LATEST_RESULTS,
            EditorialPlanningContent.STAT_NARRATIVE,
            EditorialPlanningContent.METRIC_NARRATIVE,
            EditorialPlanningContent.VIRAL_STORY,
        } and readiness_row.finished_matches_count == 0:
            return ["finished_matches"]
        if task.planning_type == EditorialPlanningContent.PREVIEW and readiness_row.scheduled_matches_count == 0:
            return ["scheduled_matches"]
        if task.planning_type in {
            EditorialPlanningContent.STANDINGS,
            EditorialPlanningContent.RANKING,
        } and readiness_row.standings_count == 0:
            return ["standings"]
        return []

    def _target_content_type(self, planning_type: EditorialPlanningContent) -> ContentType:
        return {
            EditorialPlanningContent.LATEST_RESULTS: ContentType.MATCH_RESULT,
            EditorialPlanningContent.STANDINGS: ContentType.STANDINGS,
            EditorialPlanningContent.PREVIEW: ContentType.PREVIEW,
            EditorialPlanningContent.RANKING: ContentType.RANKING,
            EditorialPlanningContent.STAT_NARRATIVE: ContentType.STAT_NARRATIVE,
            EditorialPlanningContent.METRIC_NARRATIVE: ContentType.METRIC_NARRATIVE,
            EditorialPlanningContent.VIRAL_STORY: ContentType.VIRAL_STORY,
        }[planning_type]

    def _excerpt(self, text: str, limit: int = 110) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."
