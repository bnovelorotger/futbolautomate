from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, union_all
from sqlalchemy.orm import Session, aliased

from app.core.config import get_settings
from app.core.enums import MatchWindow
from app.core.exceptions import ConfigurationError
from app.db.models import Competition, Match, Standing, Team
from app.schemas.reporting import (
    CompetitionMatchView,
    CompetitionSummaryView,
    MatchWindowView,
    StandingView,
    TeamRankingView,
)
from app.services.competition_relevance import CompetitionRelevanceService


@dataclass(slots=True)
class WindowBounds:
    start_date: date
    end_date: date


class CompetitionQueryService:
    def __init__(self, session: Session, timezone_name: str | None = None) -> None:
        self.session = session
        self.timezone_name = timezone_name or get_settings().timezone
        self.relevance = CompetitionRelevanceService()

    def _get_competition(self, competition_code: str) -> Competition:
        competition = self.session.scalar(
            select(Competition).where(Competition.code == competition_code)
        )
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_code}")
        return competition

    def _match_view_query(self, competition_id: int):
        home_team = aliased(Team)
        away_team = aliased(Team)
        return (
            select(
                Match.round_name,
                Match.match_date,
                Match.raw_match_date.label("match_date_raw"),
                Match.match_time,
                Match.raw_match_time.label("match_time_raw"),
                Match.kickoff_datetime,
                func.coalesce(home_team.name, Match.home_team_raw).label("home_team"),
                func.coalesce(away_team.name, Match.away_team_raw).label("away_team"),
                Match.home_score,
                Match.away_score,
                Match.status,
                Match.source_url,
            )
            .select_from(Match)
            .outerjoin(home_team, home_team.id == Match.home_team_id)
            .outerjoin(away_team, away_team.id == Match.away_team_id)
            .where(Match.competition_id == competition_id)
        )

    def _standing_query(self, competition_id: int):
        has_rows = self.session.scalar(
            select(func.count()).select_from(Standing).where(Standing.competition_id == competition_id)
        ) or 0
        if has_rows == 0:
            raise ConfigurationError("No hay clasificacion disponible para esta competicion")
        return (
            select(
                Standing.position,
                func.coalesce(Team.name, Standing.team_raw).label("team"),
                Standing.points,
                Standing.played,
                Standing.wins,
                Standing.draws,
                Standing.losses,
                Standing.goals_for,
                Standing.goals_against,
                Standing.goal_difference,
            )
            .select_from(Standing)
            .outerjoin(Team, Team.id == Standing.team_id)
            .where(Standing.competition_id == competition_id)
        )

    def _match_views(
        self,
        competition_code: str,
        query,
        relevant_only: bool = False,
        limit: int | None = None,
    ) -> list[CompetitionMatchView]:
        rows = self.session.execute(query).all()
        matches = [CompetitionMatchView.model_validate(dict(row._mapping)) for row in rows]
        if relevant_only:
            matches = self.relevance.filter_match_views(competition_code, matches)
        if limit is not None:
            matches = matches[:limit]
        return matches

    def _window_bounds(self, window: MatchWindow, reference_date: date | None = None) -> WindowBounds:
        today = reference_date or datetime.now(ZoneInfo(self.timezone_name)).date()
        if window == MatchWindow.TODAY:
            return WindowBounds(start_date=today, end_date=today)
        if window == MatchWindow.TOMORROW:
            tomorrow = today + timedelta(days=1)
            return WindowBounds(start_date=tomorrow, end_date=tomorrow)

        weekday = today.weekday()
        if weekday >= 5:
            days_until_saturday = 12 - weekday
        else:
            days_until_saturday = 5 - weekday
        saturday = today + timedelta(days=days_until_saturday)
        sunday = saturday + timedelta(days=1)
        return WindowBounds(start_date=saturday, end_date=sunday)

    def latest_results(
        self,
        competition_code: str,
        limit: int = 10,
        relevant_only: bool = False,
    ) -> list[CompetitionMatchView]:
        return self.finished_matches(
            competition_code=competition_code,
            limit=limit,
            relevant_only=relevant_only,
        )

    def finished_matches(
        self,
        competition_code: str,
        limit: int | None = 10,
        relevant_only: bool = False,
        reference_date: date | None = None,
    ) -> list[CompetitionMatchView]:
        competition = self._get_competition(competition_code)
        query = (
            self._match_view_query(competition.id)
            .where(Match.status == "finished")
            .order_by(
                Match.match_date.desc().nullslast(),
                Match.match_time.desc().nullslast(),
                Match.id.desc(),
            )
        )
        if reference_date is not None:
            query = query.where(Match.match_date <= reference_date)
        if not relevant_only and limit is not None:
            query = query.limit(limit)
        return self._match_views(
            competition_code=competition_code,
            query=query,
            relevant_only=relevant_only,
            limit=limit,
        )

    def current_standings(self, competition_code: str, limit: int | None = None) -> list[StandingView]:
        competition = self._get_competition(competition_code)
        query = self._standing_query(competition.id).order_by(Standing.position.asc())
        if limit is not None:
            query = query.limit(limit)
        rows = self.session.execute(query).all()
        return [StandingView.model_validate(dict(row._mapping)) for row in rows]

    def upcoming_matches(
        self,
        competition_code: str,
        limit: int = 10,
        relevant_only: bool = False,
        reference_date: date | None = None,
    ) -> list[CompetitionMatchView]:
        competition = self._get_competition(competition_code)
        query = (
            self._match_view_query(competition.id)
            .where(Match.status == "scheduled")
            .order_by(
                Match.match_date.asc().nullslast(),
                Match.match_time.asc().nullslast(),
                Match.id.asc(),
            )
        )
        if reference_date is not None:
            query = query.where(
                or_(
                    Match.match_date.is_(None),
                    Match.match_date >= reference_date,
                )
            )
        if not relevant_only:
            query = query.limit(limit)
        return self._match_views(
            competition_code=competition_code,
            query=query,
            relevant_only=relevant_only,
            limit=limit,
        )

    def matches_by_round(
        self,
        competition_code: str,
        round_name: str,
        relevant_only: bool = False,
    ) -> list[CompetitionMatchView]:
        competition = self._get_competition(competition_code)
        normalized_round_name = round_name if not round_name.isdigit() else f"Jornada {round_name}"
        query = (
            self._match_view_query(competition.id)
            .where(Match.round_name == normalized_round_name)
            .order_by(
                Match.match_date.asc().nullslast(),
                Match.match_time.asc().nullslast(),
                Match.id.asc(),
            )
        )
        return self._match_views(
            competition_code=competition_code,
            query=query,
            relevant_only=relevant_only,
        )

    def top_scoring_teams(self, competition_code: str, limit: int = 5) -> list[TeamRankingView]:
        competition = self._get_competition(competition_code)
        query = (
            self._standing_query(competition.id)
            .order_by(Standing.goals_for.desc().nullslast(), Standing.position.asc())
            .limit(limit)
        )
        rows = self.session.execute(query).all()
        return [
            TeamRankingView(team=row.team, value=row.goals_for, position=row.position)
            for row in rows
        ]

    def best_defense_teams(self, competition_code: str, limit: int = 5) -> list[TeamRankingView]:
        competition = self._get_competition(competition_code)
        query = (
            self._standing_query(competition.id)
            .order_by(Standing.goals_against.asc().nullslast(), Standing.position.asc())
            .limit(limit)
        )
        rows = self.session.execute(query).all()
        return [
            TeamRankingView(team=row.team, value=row.goals_against, position=row.position)
            for row in rows
        ]

    def most_wins_teams(self, competition_code: str, limit: int = 5) -> list[TeamRankingView]:
        competition = self._get_competition(competition_code)
        query = (
            self._standing_query(competition.id)
            .order_by(Standing.wins.desc().nullslast(), Standing.position.asc())
            .limit(limit)
        )
        rows = self.session.execute(query).all()
        return [
            TeamRankingView(team=row.team, value=row.wins, position=row.position)
            for row in rows
        ]

    def matches_in_window(
        self,
        competition_code: str,
        window: MatchWindow,
        reference_date: date | None = None,
        relevant_only: bool = False,
    ) -> MatchWindowView:
        competition = self._get_competition(competition_code)
        bounds = self._window_bounds(window, reference_date=reference_date)
        query = (
            self._match_view_query(competition.id)
            .where(
                Match.match_date >= bounds.start_date,
                Match.match_date <= bounds.end_date,
            )
            .order_by(
                Match.match_date.asc().nullslast(),
                Match.match_time.asc().nullslast(),
                Match.id.asc(),
            )
        )
        return MatchWindowView(
            window=window,
            start_date=bounds.start_date,
            end_date=bounds.end_date,
            matches=self._match_views(
                competition_code=competition_code,
                query=query,
                relevant_only=relevant_only,
            ),
        )

    def tracked_teams(self, competition_code: str) -> list[str]:
        return self.relevance.tracked_teams(competition_code)

    def relevant_matches_count(self, competition_code: str) -> int:
        competition = self._get_competition(competition_code)
        if not self.relevance.has_tracked_teams(competition_code):
            return self.session.scalar(
                select(func.count()).select_from(Match).where(Match.competition_id == competition.id)
            ) or 0
        query = (
            self._match_view_query(competition.id)
            .order_by(
                Match.match_date.asc().nullslast(),
                Match.match_time.asc().nullslast(),
                Match.id.asc(),
            )
        )
        return len(
            self._match_views(
                competition_code=competition_code,
                query=query,
                relevant_only=True,
            )
        )

    def summary(self, competition_code: str) -> CompetitionSummaryView:
        competition = self._get_competition(competition_code)
        total_matches = self.session.scalar(
            select(func.count()).select_from(Match).where(Match.competition_id == competition.id)
        ) or 0
        played_matches = self.session.scalar(
            select(func.count())
            .select_from(Match)
            .where(Match.competition_id == competition.id, Match.status == "finished")
        ) or 0

        total_teams = self.session.scalar(
            select(func.count()).select_from(Standing).where(Standing.competition_id == competition.id)
        ) or 0
        if total_teams == 0:
            teams_subquery = union_all(
                select(Match.home_team_raw.label("team_name")).where(Match.competition_id == competition.id),
                select(Match.away_team_raw.label("team_name")).where(Match.competition_id == competition.id),
            ).subquery()
            total_teams = self.session.scalar(
                select(func.count(func.distinct(teams_subquery.c.team_name)))
            ) or 0

        return CompetitionSummaryView(
            competition_code=competition.code,
            competition_name=competition.name,
            total_teams=total_teams,
            total_matches=total_matches,
            played_matches=played_matches,
            pending_matches=total_matches - played_matches,
        )
