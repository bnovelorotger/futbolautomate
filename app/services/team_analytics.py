from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.db.models import Competition
from app.db.repositories.standings import StandingRepository, TeamVenueSplitRow
from app.schemas.reporting import StandingView
from app.schemas.team_analytics import (
    TeamAnalyticsFormWindowView,
    TeamAnalyticsResult,
    TeamAnalyticsRowView,
    TeamAnalyticsTrendView,
    TeamAnalyticsVenueSplitView,
    TeamGoalDifferenceTrendView,
    TeamRecentOutputView,
    TeamSeasonPaceView,
)
from app.schemas.team_form import TeamFormEntryView
from app.services.competition_queries import CompetitionQueryService
from app.services.team_form import TeamFormService
from app.utils.time import utcnow

DEFAULT_RECENT_WINDOW = 5
DEFAULT_MEDIUM_WINDOW = 10
_TREND_STABLE_THRESHOLD = 0.15


def _round_metric(value: float) -> float:
    return round(value, 2)


def _points_per_game(points: int, matches_played: int) -> float:
    if matches_played <= 0:
        return 0.0
    return _round_metric(points / matches_played)


def _goals_per_match(goals: int, matches_played: int) -> float:
    if matches_played <= 0:
        return 0.0
    return _round_metric(goals / matches_played)


def _trend_direction(delta: float) -> str:
    if delta > _TREND_STABLE_THRESHOLD:
        return "improving"
    if delta < -_TREND_STABLE_THRESHOLD:
        return "declining"
    return "stable"


class TeamAnalyticsService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.queries = CompetitionQueryService(session)
        self.team_form = TeamFormService(session, settings=self.settings)
        self.standings_repository = StandingRepository(session)
        self.catalog = load_competition_catalog()

    def preview_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> TeamAnalyticsResult:
        competition = self._competition(competition_code)
        selected_date = self._reference_date(reference_date)
        standings = self.queries.current_standings(competition_code)
        last_ten = {
            row.team: row
            for row in self.team_form.build_form_rows(
                competition_code,
                window_size=DEFAULT_MEDIUM_WINDOW,
                reference_date=selected_date,
                respect_tracking=False,
            )
        }
        last_five = {
            row.team: row
            for row in self.team_form.build_form_rows(
                competition_code,
                window_size=DEFAULT_RECENT_WINDOW,
                reference_date=selected_date,
                respect_tracking=False,
            )
        }
        venue_splits = self._venue_split_map(
            self.standings_repository.team_venue_splits(
                competition.id,
                reference_date=selected_date,
            )
        )
        schedule_counts = {
            row.team: row.total_matches
            for row in self.standings_repository.team_schedule_counts(competition.id)
        }
        team_histories = self._team_match_histories(
            competition_code,
            reference_date=selected_date,
        )
        return TeamAnalyticsResult(
            competition_slug=competition_code,
            competition_name=self._competition_name(competition),
            reference_date=selected_date,
            generated_at=utcnow(),
            rows=[
                self._build_row(
                    standing,
                    medium_window=last_ten.get(standing.team),
                    recent_window=last_five.get(standing.team),
                    venue_splits=venue_splits.get(standing.team, {}),
                    scheduled_matches=schedule_counts.get(standing.team),
                    history=team_histories.get(standing.team, []),
                )
                for standing in standings
            ],
        )

    def _build_row(
        self,
        standing: StandingView,
        *,
        medium_window: TeamFormEntryView | None,
        recent_window: TeamFormEntryView | None,
        venue_splits: dict[str, TeamVenueSplitRow],
        scheduled_matches: int | None,
        history: list[tuple[int, int]],
    ) -> TeamAnalyticsRowView:
        played = int(standing.played or 0)
        points = int(standing.points or 0)
        overall_ppg = _points_per_game(points, played)
        last_ten_view = self._form_window(medium_window)
        last_five_view = self._form_window(recent_window)
        home_split = self._venue_split_view("home", venue_splits.get("home"))
        away_split = self._venue_split_view("away", venue_splits.get("away"))
        matches_scheduled = max(int(scheduled_matches or 0), played)
        matches_remaining = max(matches_scheduled - played, 0)
        projected_additional_points = _round_metric(overall_ppg * matches_remaining)
        projected_final_points = _round_metric(points + projected_additional_points)
        baseline_ppg = (
            last_ten_view.points_per_game
            if last_ten_view.matches_considered > 0
            else overall_ppg
        )
        recent_ppg = (
            last_five_view.points_per_game
            if last_five_view.matches_considered > 0
            else overall_ppg
        )
        trend_delta = _round_metric(recent_ppg - baseline_ppg)
        gd_trend = self._goal_difference_trend(history)
        return TeamAnalyticsRowView(
            position=standing.position,
            team=standing.team,
            points=standing.points,
            played=standing.played,
            wins=standing.wins,
            draws=standing.draws,
            losses=standing.losses,
            goals_for=standing.goals_for,
            goals_against=standing.goals_against,
            goal_difference=standing.goal_difference,
            overall_points_per_game=overall_ppg,
            last_ten=last_ten_view,
            last_five=last_five_view,
            recent_trend=TeamAnalyticsTrendView(
                direction=_trend_direction(trend_delta),
                baseline_points_per_game=baseline_ppg,
                recent_points_per_game=recent_ppg,
                delta_points_per_game=trend_delta,
            ),
            home_split=home_split,
            away_split=away_split,
            season_pace=TeamSeasonPaceView(
                current_points=points,
                current_points_per_game=overall_ppg,
                matches_played=played,
                matches_scheduled=matches_scheduled,
                matches_remaining=matches_remaining,
                projected_additional_points=projected_additional_points,
                projected_final_points=projected_final_points,
            ),
            goal_difference_trend=gd_trend,
            defensive_solidity=TeamRecentOutputView(
                matches_considered=last_five_view.matches_considered,
                total_goals=last_five_view.goals_against,
                goals_per_match=_goals_per_match(
                    last_five_view.goals_against,
                    last_five_view.matches_considered,
                ),
            ),
            attacking_efficiency=TeamRecentOutputView(
                matches_considered=last_five_view.matches_considered,
                total_goals=last_five_view.goals_for,
                goals_per_match=_goals_per_match(
                    last_five_view.goals_for,
                    last_five_view.matches_considered,
                ),
            ),
        )

    def _form_window(self, row: TeamFormEntryView | None) -> TeamAnalyticsFormWindowView:
        if row is None:
            return TeamAnalyticsFormWindowView()
        return TeamAnalyticsFormWindowView(
            matches_considered=row.matches_considered,
            sequence=row.sequence,
            points=row.points,
            points_per_game=_points_per_game(row.points, row.matches_considered),
            wins=row.wins,
            draws=row.draws,
            losses=row.losses,
            goals_for=row.goals_for,
            goals_against=row.goals_against,
            goal_difference=row.goal_difference,
        )

    def _venue_split_view(
        self,
        venue: str,
        row: TeamVenueSplitRow | None,
    ) -> TeamAnalyticsVenueSplitView:
        if row is None:
            return TeamAnalyticsVenueSplitView(venue=venue)
        return TeamAnalyticsVenueSplitView(
            venue=venue,
            played=row.played,
            wins=row.wins,
            draws=row.draws,
            losses=row.losses,
            points=row.points,
            points_per_game=_points_per_game(row.points, row.played),
            goals_for=row.goals_for,
            goals_against=row.goals_against,
            goal_difference=row.goal_difference,
            win_rate_percentage=_round_metric((row.wins / row.played) * 100) if row.played else 0.0,
        )

    def _goal_difference_trend(
        self,
        history: list[tuple[int, int]],
    ) -> TeamGoalDifferenceTrendView:
        if not history:
            return TeamGoalDifferenceTrendView()
        opening_slice = history[:DEFAULT_RECENT_WINDOW]
        recent_slice = history[-DEFAULT_RECENT_WINDOW:]
        opening_total = sum(goals_for - goals_against for goals_for, goals_against in opening_slice)
        recent_total = sum(goals_for - goals_against for goals_for, goals_against in recent_slice)
        opening_per_match = _goals_per_match(opening_total, len(opening_slice))
        recent_per_match = _goals_per_match(recent_total, len(recent_slice))
        delta = _round_metric(recent_per_match - opening_per_match)
        return TeamGoalDifferenceTrendView(
            opening_window_matches=len(opening_slice),
            opening_goal_difference_per_match=opening_per_match,
            recent_window_matches=len(recent_slice),
            recent_goal_difference_per_match=recent_per_match,
            delta_goal_difference_per_match=delta,
            direction=_trend_direction(delta),
        )

    def _team_match_histories(
        self,
        competition_code: str,
        *,
        reference_date: date,
    ) -> dict[str, list[tuple[int, int]]]:
        matches = self.queries.finished_matches(
            competition_code,
            limit=None,
            reference_date=reference_date,
        )
        histories: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for match in reversed(matches):
            if match.home_score is None or match.away_score is None:
                continue
            histories[match.home_team].append((int(match.home_score), int(match.away_score)))
            histories[match.away_team].append((int(match.away_score), int(match.home_score)))
        return histories

    def _venue_split_map(
        self,
        rows: list[TeamVenueSplitRow],
    ) -> dict[str, dict[str, TeamVenueSplitRow]]:
        split_map: dict[str, dict[str, TeamVenueSplitRow]] = defaultdict(dict)
        for row in rows:
            split_map[row.team][row.venue] = row
        return split_map

    def _competition(self, competition_code: str) -> Competition:
        competition = self.session.scalar(
            select(Competition).where(Competition.code == competition_code)
        )
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_code}")
        return competition

    def _competition_name(self, competition: Competition) -> str:
        definition = self.catalog.get(competition.code)
        if definition is not None and definition.editorial_name:
            return definition.editorial_name
        return competition.name

    def _reference_date(self, reference_date: date | None) -> date:
        if reference_date is not None:
            return reference_date
        return datetime.now(ZoneInfo(self.settings.timezone)).date()
