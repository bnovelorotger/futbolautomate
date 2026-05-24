from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.catalog import CompetitionDefinition, load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.enums import ContentType, EditorialPlanningContent, EditorialSeasonPhase, MatchStatus
from app.db.models import Competition, ContentCandidate, Match
from app.schemas.editorial_phase import EditorialCompetitionPhaseState, EditorialGlobalPhaseReport

PRESEASON_DAYS_BEFORE_FIRST_MATCH = 14
SEASON_WRAP_DAYS_AFTER_LAST_MATCH = 14

_PLAYOFF_COMPETITION_MARKER = "playoff"
_PLAYOFF_COMPETITION_TYPE = "playoff"
_ACTIVE_MATCH_STATUSES = {str(MatchStatus.SCHEDULED), str(MatchStatus.LIVE)}
_FINISHED_MATCH_STATUSES = {str(MatchStatus.FINISHED)}

_REGULAR_AUTOMATIC_CONTENT_TYPES = {
    ContentType.MATCH_RESULT,
    ContentType.RESULTS_ROUNDUP,
    ContentType.STANDINGS,
    ContentType.STANDINGS_ROUNDUP,
    ContentType.RANKING,
    ContentType.RACE_NARRATIVE,
    ContentType.MILESTONE_STORY,
    ContentType.TOP_SCORER_UPDATE,
    ContentType.VIRAL_STORY,
    ContentType.METRIC_NARRATIVE,
    ContentType.STAT_NARRATIVE,
    ContentType.FEATURED_MATCH_PREVIEW,
    ContentType.MATCH_IMPACT_SCENARIO,
    ContentType.PREVIEW,
}
_PLAYOFF_CONTENT_TYPES = {
    ContentType.MATCH_RESULT,
    ContentType.RESULTS_ROUNDUP,
    ContentType.FEATURED_MATCH_PREVIEW,
    ContentType.PREVIEW,
    ContentType.PLAYOFF_BRACKET,
}
_PRESEASON_CONTENT_TYPES = {
    ContentType.FEATURED_MATCH_PREVIEW,
    ContentType.PREVIEW,
    ContentType.VIRAL_STORY,
}
_SEASON_WRAP_CONTENT_TYPES = {
    ContentType.MATCH_RESULT,
    ContentType.RESULTS_ROUNDUP,
    ContentType.STANDINGS,
    ContentType.STANDINGS_ROUNDUP,
    ContentType.RANKING,
    ContentType.MILESTONE_STORY,
    ContentType.TOP_SCORER_UPDATE,
    ContentType.VIRAL_STORY,
    ContentType.METRIC_NARRATIVE,
    ContentType.STAT_NARRATIVE,
    ContentType.SEASON_WRAP_STATS,
    ContentType.SEASON_WRAP_OUTCOMES,
    ContentType.PLAYOFF_BRACKET,
}
_PLANNING_TO_CONTENT = {
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
}


class EditorialPhaseService:
    """Detects the editorial season phase from local match data.

    The service is intentionally DB/date-driven for playoffs because playoff
    rows currently arrive from Futbolme without a season value.
    """

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        preseason_days: int = PRESEASON_DAYS_BEFORE_FIRST_MATCH,
        season_wrap_days: int = SEASON_WRAP_DAYS_AFTER_LAST_MATCH,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.preseason_days = preseason_days
        self.season_wrap_days = season_wrap_days
        self.catalog = load_competition_catalog()
        self._state_cache: dict[tuple[str, date], EditorialCompetitionPhaseState] = {}

    def today(self) -> date:
        return datetime.now(ZoneInfo(self.settings.timezone)).date()

    def global_phase(self, reference_date: date | None = None) -> EditorialGlobalPhaseReport:
        selected_date = reference_date or self.today()
        states = [
            self.phase_for_competition(slug, reference_date=selected_date)
            for slug, definition in self.catalog.items()
            if self._is_integrated_definition(definition)
        ]
        priority = {
            EditorialSeasonPhase.PLAYOFFS: 5,
            EditorialSeasonPhase.SEASON_WRAP: 4,
            EditorialSeasonPhase.REGULAR_SEASON: 3,
            EditorialSeasonPhase.PRESEASON: 2,
            EditorialSeasonPhase.OFFSEASON: 1,
        }
        relevant_states = [state for state in states if state.has_data]
        phase_state = max(relevant_states or states, key=lambda state: priority[state.phase], default=None)
        if phase_state is None:
            return EditorialGlobalPhaseReport(
                reference_date=selected_date,
                phase=EditorialSeasonPhase.OFFSEASON,
                reason="no_integrated_competitions",
                states=[],
            )
        return EditorialGlobalPhaseReport(
            reference_date=selected_date,
            phase=phase_state.phase,
            reason=phase_state.reason,
            states=states,
        )

    def phase_for_competition(
        self,
        competition_slug: str,
        *,
        reference_date: date | None = None,
    ) -> EditorialCompetitionPhaseState:
        selected_date = reference_date or self.today()
        cache_key = (competition_slug, selected_date)
        cached = self._state_cache.get(cache_key)
        if cached is not None:
            return cached
        state = self._compute_phase_for_competition(competition_slug, reference_date=selected_date)
        self._state_cache[cache_key] = state
        return state

    def is_playoff_competition(self, competition_slug: str) -> bool:
        definition = self.catalog.get(competition_slug)
        if definition is not None and definition.competition_type == _PLAYOFF_COMPETITION_TYPE:
            return True
        return _PLAYOFF_COMPETITION_MARKER in competition_slug.lower()

    def planning_content_allowed(
        self,
        competition_slug: str,
        planning_type: EditorialPlanningContent,
        *,
        reference_date: date | None = None,
    ) -> tuple[bool, EditorialCompetitionPhaseState, str | None]:
        content_type = _PLANNING_TO_CONTENT[planning_type]
        return self.content_type_allowed(
            competition_slug,
            content_type,
            reference_date=reference_date,
        )

    def content_type_allowed(
        self,
        competition_slug: str,
        content_type: ContentType,
        *,
        reference_date: date | None = None,
    ) -> tuple[bool, EditorialCompetitionPhaseState, str | None]:
        state = self.phase_for_competition(competition_slug, reference_date=reference_date)
        if not state.has_data:
            return True, state, None

        if self.is_playoff_competition(competition_slug):
            if state.phase == EditorialSeasonPhase.PLAYOFFS:
                allowed = content_type in _PLAYOFF_CONTENT_TYPES
            elif state.phase == EditorialSeasonPhase.SEASON_WRAP:
                allowed = content_type in {
                    ContentType.RESULTS_ROUNDUP,
                    ContentType.MATCH_RESULT,
                    ContentType.PLAYOFF_BRACKET,
                    ContentType.SEASON_WRAP_OUTCOMES,
                }
            else:
                allowed = False
        elif state.phase == EditorialSeasonPhase.REGULAR_SEASON:
            allowed = content_type in _REGULAR_AUTOMATIC_CONTENT_TYPES
        elif state.phase == EditorialSeasonPhase.PLAYOFFS:
            allowed = False
        elif state.phase == EditorialSeasonPhase.SEASON_WRAP:
            allowed = content_type in _SEASON_WRAP_CONTENT_TYPES
        elif state.phase == EditorialSeasonPhase.PRESEASON:
            allowed = content_type in _PRESEASON_CONTENT_TYPES
        else:
            allowed = False

        if allowed:
            return True, state, None
        return False, state, f"phase_content_type_blocked:{state.phase}:{content_type}"

    def is_candidate_allowed(
        self,
        candidate: ContentCandidate,
        *,
        reference_date: date | None = None,
    ) -> bool:
        try:
            content_type = ContentType(candidate.content_type)
        except ValueError:
            return False
        selected_date = reference_date or self._candidate_reference_date(candidate) or self.today()
        state = self.phase_for_competition(candidate.competition_slug, reference_date=selected_date)
        if state.phase != EditorialSeasonPhase.PLAYOFFS:
            return True
        allowed, _, _ = self.content_type_allowed(
            candidate.competition_slug,
            content_type,
            reference_date=selected_date,
        )
        return allowed

    def candidate_phase_errors(
        self,
        candidate: ContentCandidate,
        *,
        reference_date: date | None = None,
    ) -> list[str]:
        try:
            content_type = ContentType(candidate.content_type)
        except ValueError:
            return ["content_type_invalid"]
        selected_date = reference_date or self._candidate_reference_date(candidate) or self.today()
        state = self.phase_for_competition(candidate.competition_slug, reference_date=selected_date)
        if state.phase != EditorialSeasonPhase.PLAYOFFS:
            return []
        allowed, state, reason = self.content_type_allowed(
            candidate.competition_slug,
            content_type,
            reference_date=selected_date,
        )
        if allowed or reason is None or not state.has_data:
            return []
        return [reason]

    def _candidate_has_future_match_date(self, candidate: ContentCandidate, *, reference_date: date) -> bool:
        return any(match_date >= reference_date for match_date in self._candidate_match_dates(candidate))

    def _candidate_match_dates(self, candidate: ContentCandidate) -> list[date]:
        payload_json = candidate.payload_json or {}
        if not isinstance(payload_json, dict):
            return []
        source_payload = payload_json.get("source_payload")
        if not isinstance(source_payload, dict):
            return []
        raw_values: list[object] = [source_payload.get("match_date")]
        featured_match = source_payload.get("featured_match")
        if isinstance(featured_match, dict):
            raw_values.append(featured_match.get("match_date"))
        for match in source_payload.get("matches") or []:
            if isinstance(match, dict):
                raw_values.append(match.get("match_date"))
        return sorted(
            {
                parsed
                for parsed in (self._parse_date(value) for value in raw_values)
                if parsed is not None
            }
        )

    def _compute_phase_for_competition(
        self,
        competition_slug: str,
        *,
        reference_date: date,
    ) -> EditorialCompetitionPhaseState:
        definition = self.catalog.get(competition_slug)
        if self.is_playoff_competition(competition_slug):
            return self._playoff_state(competition_slug, definition, reference_date=reference_date)
        return self._regular_state(competition_slug, definition, reference_date=reference_date)

    def _playoff_state(
        self,
        competition_slug: str,
        definition: CompetitionDefinition | None,
        *,
        reference_date: date,
    ) -> EditorialCompetitionPhaseState:
        metrics = self._match_metrics(competition_slug, reference_date=reference_date)
        if metrics["future_scheduled_count"] > 0:
            phase = EditorialSeasonPhase.PLAYOFFS
            reason = "playoff_future_scheduled"
        elif self._date_within_wrap(metrics["latest_finished_date"], reference_date):
            phase = EditorialSeasonPhase.SEASON_WRAP
            reason = "playoff_recently_finished"
        else:
            phase = EditorialSeasonPhase.OFFSEASON
            reason = "playoff_inactive_or_stale" if metrics["has_data"] else "playoff_no_matches"
        return self._state_from_metrics(
            competition_slug,
            definition,
            reference_date=reference_date,
            phase=phase,
            reason=reason,
            metrics=metrics,
        )

    def _regular_state(
        self,
        competition_slug: str,
        definition: CompetitionDefinition | None,
        *,
        reference_date: date,
    ) -> EditorialCompetitionPhaseState:
        metrics = self._match_metrics(competition_slug, reference_date=reference_date)
        child_states = [
            self.phase_for_competition(child_slug, reference_date=reference_date)
            for child_slug in self._child_playoff_slugs(competition_slug)
        ]
        active_child = next(
            (state for state in child_states if state.phase == EditorialSeasonPhase.PLAYOFFS),
            None,
        )
        wrap_child = next(
            (state for state in child_states if state.phase == EditorialSeasonPhase.SEASON_WRAP),
            None,
        )
        if active_child is not None:
            phase = EditorialSeasonPhase.PLAYOFFS
            reason = f"child_playoff_active:{active_child.competition_slug}"
            child_phase = active_child.phase
            metrics = {**metrics, "has_data": True}
        elif wrap_child is not None:
            phase = EditorialSeasonPhase.SEASON_WRAP
            reason = f"child_playoff_recently_finished:{wrap_child.competition_slug}"
            child_phase = wrap_child.phase
            metrics = {**metrics, "has_data": True}
        elif metrics["future_scheduled_count"] > 0:
            if metrics["finished_count"] == 0 and self._date_within_preseason(metrics["next_scheduled_date"], reference_date):
                phase = EditorialSeasonPhase.PRESEASON
                reason = "regular_first_match_within_preseason_window"
            elif metrics["finished_count"] == 0:
                phase = EditorialSeasonPhase.OFFSEASON
                reason = "regular_first_match_not_near"
            else:
                phase = EditorialSeasonPhase.REGULAR_SEASON
                reason = "regular_future_scheduled"
            child_phase = None
        elif self._date_within_wrap(metrics["latest_finished_date"], reference_date):
            phase = EditorialSeasonPhase.SEASON_WRAP
            reason = "regular_recently_finished"
            child_phase = None
        else:
            phase = EditorialSeasonPhase.OFFSEASON
            reason = "regular_inactive_or_stale" if metrics["has_data"] else "regular_no_matches"
            child_phase = None

        return self._state_from_metrics(
            competition_slug,
            definition,
            reference_date=reference_date,
            phase=phase,
            reason=reason,
            metrics=metrics,
            child_playoff_slugs=[state.competition_slug for state in child_states],
            child_phase=child_phase,
        )

    def _match_metrics(self, competition_slug: str, *, reference_date: date) -> dict[str, object]:
        competition = self.session.scalar(select(Competition).where(Competition.code == competition_slug))
        if competition is None:
            return {
                "first_match_date": None,
                "last_match_date": None,
                "latest_finished_date": None,
                "next_scheduled_date": None,
                "future_scheduled_count": 0,
                "overdue_scheduled_count": 0,
                "finished_count": 0,
                "has_data": False,
            }
        match_base = select(Match).where(Match.competition_id == competition.id)
        first_match_date = self.session.scalar(
            select(func.min(Match.match_date)).where(Match.competition_id == competition.id, Match.match_date.is_not(None))
        )
        last_match_date = self.session.scalar(
            select(func.max(Match.match_date)).where(Match.competition_id == competition.id, Match.match_date.is_not(None))
        )
        latest_finished_date = self.session.scalar(
            select(func.max(Match.match_date)).where(
                Match.competition_id == competition.id,
                Match.match_date.is_not(None),
                Match.status.in_(_FINISHED_MATCH_STATUSES),
            )
        )
        next_scheduled_date = self.session.scalar(
            select(func.min(Match.match_date)).where(
                Match.competition_id == competition.id,
                Match.match_date.is_not(None),
                Match.match_date >= reference_date,
                Match.status.in_(_ACTIVE_MATCH_STATUSES),
            )
        )
        future_scheduled_count = (
            self.session.scalar(
                select(func.count())
                .select_from(Match)
                .where(
                    Match.competition_id == competition.id,
                    Match.match_date.is_not(None),
                    Match.match_date >= reference_date,
                    Match.status.in_(_ACTIVE_MATCH_STATUSES),
                )
            )
            or 0
        )
        overdue_scheduled_count = (
            self.session.scalar(
                select(func.count())
                .select_from(Match)
                .where(
                    Match.competition_id == competition.id,
                    Match.match_date.is_not(None),
                    Match.match_date < reference_date,
                    Match.status == str(MatchStatus.SCHEDULED),
                )
            )
            or 0
        )
        finished_count = (
            self.session.scalar(
                select(func.count())
                .select_from(Match)
                .where(Match.competition_id == competition.id, Match.status.in_(_FINISHED_MATCH_STATUSES))
            )
            or 0
        )
        has_data = (self.session.scalar(select(func.count()).select_from(match_base.subquery())) or 0) > 0
        return {
            "first_match_date": first_match_date,
            "last_match_date": last_match_date,
            "latest_finished_date": latest_finished_date,
            "next_scheduled_date": next_scheduled_date,
            "future_scheduled_count": int(future_scheduled_count),
            "overdue_scheduled_count": int(overdue_scheduled_count),
            "finished_count": int(finished_count),
            "has_data": bool(has_data),
        }

    def _state_from_metrics(
        self,
        competition_slug: str,
        definition: CompetitionDefinition | None,
        *,
        reference_date: date,
        phase: EditorialSeasonPhase,
        reason: str,
        metrics: dict[str, object],
        child_playoff_slugs: list[str] | None = None,
        child_phase: EditorialSeasonPhase | None = None,
    ) -> EditorialCompetitionPhaseState:
        return EditorialCompetitionPhaseState(
            competition_slug=competition_slug,
            reference_date=reference_date,
            phase=phase,
            reason=reason,
            competition_type=definition.competition_type if definition is not None else None,
            playoff_type=definition.playoff_type if definition is not None else None,
            parent_competition=definition.parent_competition if definition is not None else None,
            child_playoff_slugs=list(child_playoff_slugs or []),
            child_phase=child_phase,
            first_match_date=metrics["first_match_date"],
            last_match_date=metrics["last_match_date"],
            latest_finished_date=metrics["latest_finished_date"],
            next_scheduled_date=metrics["next_scheduled_date"],
            future_scheduled_count=int(metrics["future_scheduled_count"]),
            overdue_scheduled_count=int(metrics["overdue_scheduled_count"]),
            finished_count=int(metrics["finished_count"]),
            has_data=bool(metrics["has_data"]),
        )

    def _child_playoff_slugs(self, competition_slug: str) -> list[str]:
        return sorted(
            slug
            for slug, definition in self.catalog.items()
            if definition.parent_competition == competition_slug or (
                definition.parent_competition is None
                and self.is_playoff_competition(slug)
                and slug.startswith(f"{competition_slug}_")
            )
        )

    def _candidate_reference_date(self, candidate: ContentCandidate) -> date | None:
        payload_json = candidate.payload_json or {}
        if isinstance(payload_json, dict):
            parsed = self._parse_date(payload_json.get("reference_date"))
            if parsed is not None:
                return parsed
            source_payload = payload_json.get("source_payload")
            if isinstance(source_payload, dict):
                parsed = self._parse_date(source_payload.get("reference_date"))
                if parsed is not None:
                    return parsed
        for value in (candidate.published_at, candidate.approved_at, candidate.scheduled_at, candidate.created_at):
            parsed = self._parse_date(value)
            if parsed is not None:
                return parsed
        return None

    def _parse_date(self, value) -> date | None:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=ZoneInfo(self.settings.timezone)).date()
            return value.astimezone(ZoneInfo(self.settings.timezone)).date()
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                return None
        return None

    def _date_within_preseason(self, next_match_date: date | None, reference_date: date) -> bool:
        if next_match_date is None or next_match_date < reference_date:
            return False
        return next_match_date - timedelta(days=self.preseason_days) <= reference_date <= next_match_date

    def _date_within_wrap(self, latest_match_date: date | None, reference_date: date) -> bool:
        if latest_match_date is None or latest_match_date > reference_date:
            return False
        return reference_date <= latest_match_date + timedelta(days=self.season_wrap_days)

    def _is_integrated_definition(self, definition: CompetitionDefinition) -> bool:
        return str(definition.status) == "integrated"
