from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any
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
from app.schemas.race_narrative import RaceNarrativeSeasonContext
from app.schemas.editorial_planner import (
    EditorialCampaignGenerationResult,
    EditorialCampaignPlan,
    EditorialCampaignTask,
    EditorialGeneratedTaskResult,
    EditorialWeekPlan,
    EditorialWeeklySchedule,
)
from app.services.editorial_content_generator import EditorialContentGenerator
from app.services.competition_queries import CompetitionQueryService
from app.services.match_impact_calculator import MatchImpactCalculatorService
from app.services.milestone_detector import MilestoneDetectorService
from app.services.race_narrative_generator import RaceNarrativeService
from app.services.results_roundup import ResultsRoundupService
from app.services.standings_roundup import StandingsRoundupService
from app.services.match_importance import MatchImportanceService
from app.services.editorial_narratives import EditorialNarrativesService
from app.services.team_analytics import TeamAnalyticsService
from app.services.editorial_viral_stories import EditorialViralStoriesService
from app.utils.hashing import stable_hash

_PLANNING_CONTENT_MAP = {
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
        self.queries = CompetitionQueryService(session)
        self.results_roundup = ResultsRoundupService(session, settings=self.settings)
        self.standings_roundup = StandingsRoundupService(session, settings=self.settings)
        self.match_importance = MatchImportanceService(session, settings=self.settings)
        self.match_impact = MatchImpactCalculatorService(session, settings=self.settings)
        self.narratives = EditorialNarrativesService(session)
        self.race_narratives = RaceNarrativeService()
        self.milestones = MilestoneDetectorService(session, settings=self.settings)
        self.team_analytics = TeamAnalyticsService(session, settings=self.settings)
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
        generated_roundup_cache: dict[str, list[ContentCandidateDraft]] = {}
        generated_standings_roundup_cache: dict[str, list[ContentCandidateDraft]] = {}
        generated_featured_cache: dict[str, list[ContentCandidateDraft]] = {}
        generated_match_impact_cache: dict[str, list[ContentCandidateDraft]] = {}
        generated_narratives_cache: dict[str, list[ContentCandidateDraft]] = {}
        generated_race_cache: dict[str, list[ContentCandidateDraft]] = {}
        generated_milestone_cache: dict[str, list[ContentCandidateDraft]] = {}
        generated_viral_cache: dict[str, list[ContentCandidateDraft]] = {}
        for competition_slug in sorted(grouped_tasks):
            for task in grouped_tasks[competition_slug]:
                if task.planning_type == EditorialPlanningContent.RESULTS_ROUNDUP:
                    if competition_slug not in generated_roundup_cache:
                        generated_roundup_cache[competition_slug] = self.results_roundup.build_candidate_drafts(
                            competition_slug,
                            reference_date=plan.date,
                        )
                        self._validate_candidates_for_competition(
                            competition_slug,
                            generated_roundup_cache[competition_slug],
                        )
                    selected_candidates = generated_roundup_cache[competition_slug]
                    stats = self.results_roundup.store_candidates(selected_candidates)
                elif task.planning_type == EditorialPlanningContent.STANDINGS_ROUNDUP:
                    if competition_slug not in generated_standings_roundup_cache:
                        generated_standings_roundup_cache[competition_slug] = self.standings_roundup.build_candidate_drafts(
                            competition_slug,
                            reference_date=plan.date,
                        )
                        self._validate_candidates_for_competition(
                            competition_slug,
                            generated_standings_roundup_cache[competition_slug],
                        )
                    selected_candidates = generated_standings_roundup_cache[competition_slug]
                    stats = self.standings_roundup.store_candidates(selected_candidates)
                elif task.planning_type == EditorialPlanningContent.FEATURED_MATCH_PREVIEW:
                    if competition_slug not in generated_featured_cache:
                        generated_featured_cache[competition_slug] = self.match_importance.build_candidate_drafts(
                            competition_slug,
                            reference_date=plan.date,
                            limit=1,
                        )
                        self._validate_candidates_for_competition(
                            competition_slug,
                            generated_featured_cache[competition_slug],
                        )
                    selected_candidates = generated_featured_cache[competition_slug]
                    stats = self.match_importance.store_candidates(selected_candidates)
                elif task.planning_type == EditorialPlanningContent.MATCH_IMPACT_SCENARIO:
                    if competition_slug not in generated_match_impact_cache:
                        generated_match_impact_cache[competition_slug] = self._build_match_impact_candidates(
                            competition_slug,
                            reference_date=plan.date,
                        )
                        self._validate_candidates_for_competition(
                            competition_slug,
                            generated_match_impact_cache[competition_slug],
                        )
                    selected_candidates = generated_match_impact_cache[competition_slug]
                    stats = self.generator.store_candidates(selected_candidates)
                elif task.planning_type == EditorialPlanningContent.METRIC_NARRATIVE:
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
                elif task.planning_type == EditorialPlanningContent.RACE_NARRATIVE:
                    if competition_slug not in generated_race_cache:
                        generated_race_cache[competition_slug] = self._build_race_narrative_candidates(
                            competition_slug,
                            reference_date=plan.date,
                        )
                        self._validate_candidates_for_competition(
                            competition_slug,
                            generated_race_cache[competition_slug],
                        )
                    selected_candidates = generated_race_cache[competition_slug]
                    stats = self.generator.store_candidates(selected_candidates)
                elif task.planning_type == EditorialPlanningContent.MILESTONE_STORY:
                    if competition_slug not in generated_milestone_cache:
                        generated_milestone_cache[competition_slug] = self._build_milestone_candidates(
                            competition_slug,
                            reference_date=plan.date,
                        )
                        self._validate_candidates_for_competition(
                            competition_slug,
                            generated_milestone_cache[competition_slug],
                        )
                    selected_candidates = generated_milestone_cache[competition_slug]
                    stats = self.generator.store_candidates(selected_candidates)
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
                        excerpts=[
                            f"{candidate.content_type}: {_excerpt(candidate.text_draft)}"
                            for candidate in selected_candidates[:3]
                        ],
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

    def _build_match_impact_candidates(
        self,
        competition_slug: str,
        *,
        reference_date: date,
    ) -> list[ContentCandidateDraft]:
        result = self.match_impact.preview_for_competition(
            competition_slug,
            reference_date=reference_date,
            limit=1,
            relevant_only=True,
        )
        candidates: list[ContentCandidateDraft] = []
        for row in result.rows:
            source_payload = row.model_dump(mode="json")
            source_payload["teams"] = [row.home_team, row.away_team]
            content_key = (
                f"match_impact_scenario:{competition_slug}:{row.home_team}:{row.away_team}:"
                f"{reference_date.isoformat()}"
            )
            candidates.append(
                ContentCandidateDraft(
                    competition_slug=competition_slug,
                    content_type=ContentType.MATCH_IMPACT_SCENARIO,
                    priority=max(70, min(95, 65 + row.max_zone_crossings * 6 + row.impact_score // 10)),
                    text_draft=self._match_impact_text(row),
                    payload_json={
                        "content_key": content_key,
                        "template_name": "match_impact_scenario_v1",
                        "competition_name": result.competition_name,
                        "reference_date": reference_date.isoformat(),
                        "source_payload": source_payload,
                    },
                    source_summary_hash=stable_hash(
                        {
                            "competition_slug": competition_slug,
                            "content_key": content_key,
                            "source_payload": source_payload,
                        }
                    ),
                )
            )
        return candidates

    def _build_race_narrative_candidates(
        self,
        competition_slug: str,
        *,
        reference_date: date,
    ) -> list[ContentCandidateDraft]:
        standings = self.queries.current_standings(competition_slug)
        season_context = self._race_season_context(standings)
        result = self.race_narratives.preview_for_standings(
            competition_slug,
            standings,
            competition_name=self._competition_name(competition_slug),
            season_context=season_context,
            reference_date=reference_date,
        )
        analytics_map = {
            row.team: row
            for row in self.team_analytics.preview_for_competition(
                competition_slug,
                reference_date=reference_date,
            ).rows
        }
        return [
            ContentCandidateDraft(
                competition_slug=competition_slug,
                content_type=ContentType.RACE_NARRATIVE,
                priority=row.priority,
                text_draft=self._race_narrative_text(row.text_draft, row.source_payload, analytics_map),
                payload_json={
                    "content_key": row.content_key,
                    "template_name": row.template_name,
                    "competition_name": result.competition_name,
                    "reference_date": reference_date.isoformat(),
                    "source_payload": self._race_narrative_payload(row.source_payload, analytics_map),
                },
                source_summary_hash=row.source_summary_hash,
            )
            for row in result.rows
        ]

    def _build_milestone_candidates(
        self,
        competition_slug: str,
        *,
        reference_date: date,
    ) -> list[ContentCandidateDraft]:
        result = self.milestones.preview_for_competition(
            competition_slug,
            reference_date=reference_date,
        )
        candidates: list[ContentCandidateDraft] = []
        for row in result.rows:
            source_payload = dict(row.source_payload)
            source_payload.setdefault("teams", list(row.teams))
            candidates.append(
                ContentCandidateDraft(
                    competition_slug=competition_slug,
                    content_type=ContentType.MILESTONE_STORY,
                    priority=row.priority,
                    text_draft=row.summary,
                    payload_json={
                        "content_key": row.content_key,
                        "template_name": f"milestone_story_{row.milestone_type}_v1",
                        "competition_name": result.competition_name,
                        "reference_date": reference_date.isoformat(),
                        "source_payload": source_payload,
                    },
                    source_summary_hash=stable_hash(
                        {
                            "competition_slug": competition_slug,
                            "content_key": row.content_key,
                            "source_payload": source_payload,
                        }
                    ),
                )
            )
        return candidates

    def _match_impact_text(self, row) -> str:
        parts = [self._match_impact_outcome_text(outcome) for outcome in row.scenarios]
        return " ".join(part for part in parts if part)

    def _match_impact_outcome_text(self, outcome) -> str | None:
        prefix = self._match_impact_scenario_prefix(outcome)
        team_summaries = [
            summary
            for summary in (
                self._match_impact_team_summary(outcome.home_team),
                self._match_impact_team_summary(outcome.away_team),
            )
            if summary
        ]
        if not team_summaries:
            if outcome.crossing_count > 0:
                return f"{prefix}: hay {outcome.crossing_count} cruces de zona."
            return f"{prefix}: sin cruces de zona."
        return f"{prefix}: {'; '.join(team_summaries)}."

    def _match_impact_scenario_prefix(self, outcome) -> str:
        scenario = str(getattr(outcome, "scenario", ""))
        if scenario == "home_win":
            return f"Si gana {outcome.home_team.team}"
        if scenario == "away_win":
            return f"Si gana {outcome.away_team.team}"
        return "Si empatan"

    def _match_impact_team_summary(self, team_state) -> str | None:
        zone_text = self._match_impact_zone_text(
            current_zone_tags=list(team_state.current_zone_tags),
            projected_zone_tags=list(team_state.projected_zone_tags),
        )
        position_text = self._match_impact_position_text(
            current_position=team_state.current_position,
            projected_position=team_state.projected_position,
        )
        details = [item for item in (position_text, zone_text) if item]
        if not details:
            return None
        return f"{team_state.team} {' y '.join(details)}"

    def _match_impact_position_text(
        self,
        *,
        current_position: int | None,
        projected_position: int | None,
    ) -> str | None:
        if projected_position is None or current_position is None:
            return None
        if projected_position < current_position:
            return f"sube al puesto {projected_position}"
        if projected_position > current_position:
            return f"cae al puesto {projected_position}"
        return None

    def _match_impact_zone_text(
        self,
        *,
        current_zone_tags: list[str],
        projected_zone_tags: list[str],
    ) -> str | None:
        current = set(current_zone_tags)
        projected = set(projected_zone_tags)
        if "playoff" in projected and "playoff" not in current:
            return "entra en playoff"
        if "playoff" in current and "playoff" not in projected:
            return "sale del playoff"
        if "relegation" in projected and "relegation" not in current:
            return "cae a descenso"
        if "relegation" in current and "relegation" not in projected:
            return "sale del descenso"
        return None

    def _race_season_context(
        self,
        standings: list[Any],
    ) -> RaceNarrativeSeasonContext | None:
        played_values = [
            int(row.played)
            for row in standings
            if getattr(row, "played", None) is not None
        ]
        if not played_values:
            return None
        total_teams = len(standings)
        if total_teams < 4:
            return None
        total_matchdays = max((total_teams - 1) * 2, max(played_values))
        return RaceNarrativeSeasonContext(
            total_matchdays=total_matchdays,
            rounds_remaining=max(total_matchdays - max(played_values), 0),
        )

    def _race_narrative_payload(
        self,
        source_payload: dict[str, Any],
        analytics_map: dict[str, Any],
    ) -> dict[str, Any]:
        payload = dict(source_payload)
        teams = [
            dict(team)
            for team in list(source_payload.get("teams") or [])
            if isinstance(team, dict)
        ]
        analytics_payload: list[dict[str, Any]] = []
        for team in teams:
            team_name = team.get("team")
            if not isinstance(team_name, str):
                continue
            analytics = analytics_map.get(team_name)
            if analytics is None:
                continue
            analytics_payload.append(
                {
                    "team": team_name,
                    "recent_points_per_game": analytics.recent_trend.recent_points_per_game,
                    "recent_trend_direction": analytics.recent_trend.direction,
                    "projected_final_points": analytics.season_pace.projected_final_points,
                    "defensive_goals_per_match": analytics.defensive_solidity.goals_per_match,
                    "attacking_goals_per_match": analytics.attacking_efficiency.goals_per_match,
                }
            )
        if analytics_payload:
            payload["team_analytics"] = analytics_payload
        return payload

    def _race_narrative_text(
        self,
        base_text: str,
        source_payload: dict[str, Any],
        analytics_map: dict[str, Any],
    ) -> str:
        teams = [
            dict(team)
            for team in list(source_payload.get("teams") or [])
            if isinstance(team, dict)
        ]
        note = self._race_narrative_analytics_note(teams, analytics_map)
        if note is None:
            return base_text
        return f"{base_text} {note}"

    def _race_narrative_analytics_note(
        self,
        teams: list[dict[str, Any]],
        analytics_map: dict[str, Any],
    ) -> str | None:
        best_team_name: str | None = None
        best_team_analytics = None
        for team in teams:
            team_name = team.get("team")
            if not isinstance(team_name, str):
                continue
            analytics = analytics_map.get(team_name)
            if analytics is None:
                continue
            if (
                best_team_analytics is None
                or analytics.recent_trend.recent_points_per_game > best_team_analytics.recent_trend.recent_points_per_game
            ):
                best_team_name = team_name
                best_team_analytics = analytics
        if best_team_name is None or best_team_analytics is None:
            return None
        return (
            f"El mejor ritmo reciente lo trae {best_team_name} con "
            f"{best_team_analytics.recent_trend.recent_points_per_game} puntos por partido en sus ultimos 5."
        )
