from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.db.models import Competition, Match, Team
from app.schemas.reporting import CompetitionMatchView
from app.schemas.team_analytics import TeamAnalyticsRowView
from app.schemas.team_form import TeamFormEntryView
from app.services.competition_queries import CompetitionQueryService
from app.services.match_zone_calculator import MatchZoneContext, MatchZoneCalculator
from app.services.team_analytics import TeamAnalyticsService
from app.services.team_form import DEFAULT_FORM_WINDOW, TeamFormService

DEFAULT_PREVIEW_MATCH_LIMIT = 3
DEFAULT_H2H_SEASON_LIMIT = 3


class HeadToHeadTeamRecord(BaseModel):
    team: str
    wins: int = 0
    draws: int = 0
    losses: int = 0
    goals_for: int = 0
    goals_against: int = 0
    avg_goals_for: float | None = None
    avg_goals_against: float | None = None


class HeadToHeadRecord(BaseModel):
    matches_played: int = 0
    seasons: list[str] = Field(default_factory=list)
    home_team: HeadToHeadTeamRecord
    away_team: HeadToHeadTeamRecord


class FeaturedMatchPreviewContext(BaseModel):
    competition_slug: str
    reference_date: date
    form_window: int
    featured_match: CompetitionMatchView
    matches: list[CompetitionMatchView] = Field(default_factory=list)
    head_to_head: HeadToHeadRecord
    home_form: TeamFormEntryView | None = None
    away_form: TeamFormEntryView | None = None
    home_analytics: TeamAnalyticsRowView | None = None
    away_analytics: TeamAnalyticsRowView | None = None
    zone_context: MatchZoneContext
    editorial_hooks: list[str] = Field(default_factory=list)

    def to_source_payload(self) -> dict[str, object]:
        return {
            "matches": [match.model_dump(mode="json") for match in self.matches],
            "featured_match": self.featured_match.model_dump(mode="json"),
            "head_to_head": self.head_to_head.model_dump(mode="json"),
            "form_window": self.form_window,
            "home_form": self.home_form.model_dump(mode="json") if self.home_form is not None else None,
            "away_form": self.away_form.model_dump(mode="json") if self.away_form is not None else None,
            "home_analytics": self.home_analytics.model_dump(mode="json") if self.home_analytics is not None else None,
            "away_analytics": self.away_analytics.model_dump(mode="json") if self.away_analytics is not None else None,
            "zone_context": self.zone_context.model_dump(mode="json"),
            "editorial_hooks": list(self.editorial_hooks),
            "teams": [self.featured_match.home_team, self.featured_match.away_team],
        }


class FeaturedMatchPreviewGenerator:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        zone_calculator: MatchZoneCalculator | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.queries = CompetitionQueryService(session)
        self.team_form = TeamFormService(session, settings=self.settings)
        self.team_analytics = TeamAnalyticsService(session, settings=self.settings)
        self.zone_calculator = zone_calculator or MatchZoneCalculator()

    def preview_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
        form_window: int = DEFAULT_FORM_WINDOW,
        match_limit: int = DEFAULT_PREVIEW_MATCH_LIMIT,
        h2h_season_limit: int = DEFAULT_H2H_SEASON_LIMIT,
    ) -> FeaturedMatchPreviewContext | None:
        selected_date = self._reference_date(reference_date)
        matches = self.queries.editorial_upcoming_matches(
            competition_code,
            limit=match_limit,
            relevant_only=True,
            reference_date=selected_date,
        )
        if not matches:
            return None
        return self.build_match_context(
            competition_code,
            featured_match=matches[0],
            matches=matches,
            reference_date=selected_date,
            form_window=form_window,
            h2h_season_limit=h2h_season_limit,
        )

    def build_source_payload(
        self,
        competition_code: str,
        *,
        featured_match: CompetitionMatchView,
        matches: list[CompetitionMatchView] | None = None,
        reference_date: date | None = None,
        form_window: int = DEFAULT_FORM_WINDOW,
        h2h_season_limit: int = DEFAULT_H2H_SEASON_LIMIT,
    ) -> dict[str, object]:
        return self.build_match_context(
            competition_code,
            featured_match=featured_match,
            matches=matches,
            reference_date=reference_date,
            form_window=form_window,
            h2h_season_limit=h2h_season_limit,
        ).to_source_payload()

    def build_match_context(
        self,
        competition_code: str,
        *,
        featured_match: CompetitionMatchView,
        matches: list[CompetitionMatchView] | None = None,
        reference_date: date | None = None,
        form_window: int = DEFAULT_FORM_WINDOW,
        h2h_season_limit: int = DEFAULT_H2H_SEASON_LIMIT,
    ) -> FeaturedMatchPreviewContext:
        competition = self._competition(competition_code)
        selected_date = self._reference_date(reference_date)
        selected_matches = list(matches or [featured_match])
        standings = self.queries.current_standings(competition_code)
        form_map = {
            row.team: row
            for row in self.team_form.build_form_rows(
                competition_code,
                window_size=form_window,
                reference_date=selected_date,
                respect_tracking=False,
            )
        }
        analytics_map = {
            row.team: row
            for row in self.team_analytics.preview_for_competition(
                competition_code,
                reference_date=selected_date,
            ).rows
        }
        zone_context = self.zone_calculator.build_match_context(
            competition_code,
            standings,
            home_team=featured_match.home_team,
            away_team=featured_match.away_team,
        )
        db_match = self._load_match(competition.id, featured_match)
        head_to_head = self._head_to_head(
            competition_id=competition.id,
            db_match=db_match,
            featured_match=featured_match,
            cutoff_date=featured_match.match_date or selected_date,
            season_limit=h2h_season_limit,
        )
        context = FeaturedMatchPreviewContext(
            competition_slug=competition_code,
            reference_date=selected_date,
            form_window=form_window,
            featured_match=featured_match,
            matches=selected_matches,
            head_to_head=head_to_head,
            home_form=form_map.get(featured_match.home_team),
            away_form=form_map.get(featured_match.away_team),
            home_analytics=analytics_map.get(featured_match.home_team),
            away_analytics=analytics_map.get(featured_match.away_team),
            zone_context=zone_context,
        )
        context.editorial_hooks = self._editorial_hooks(context)
        return context

    def _head_to_head(
        self,
        *,
        competition_id: int,
        db_match: Match | None,
        featured_match: CompetitionMatchView,
        cutoff_date: date,
        season_limit: int,
    ) -> HeadToHeadRecord:
        home_team = aliased(Team)
        away_team = aliased(Team)
        pair_filter = self._pair_filter(db_match, featured_match)
        query = (
            select(Match, home_team.name.label("home_name"), away_team.name.label("away_name"))
            .select_from(Match)
            .outerjoin(home_team, home_team.id == Match.home_team_id)
            .outerjoin(away_team, away_team.id == Match.away_team_id)
            .where(
                Match.competition_id == competition_id,
                Match.status == "finished",
                Match.home_score.is_not(None),
                Match.away_score.is_not(None),
                or_(Match.match_date.is_(None), Match.match_date <= cutoff_date),
                pair_filter,
            )
            .order_by(Match.match_date.desc().nullslast(), Match.id.desc())
        )
        rows = self.session.execute(query).all()
        filtered_rows = self._limit_h2h_rows_by_season(rows, season_limit=season_limit)
        home_record = HeadToHeadTeamRecord(team=featured_match.home_team)
        away_record = HeadToHeadTeamRecord(team=featured_match.away_team)
        seasons: list[str] = []

        for row in filtered_rows:
            match = row.Match
            home_name = row.home_name or match.home_team_raw
            away_name = row.away_name or match.away_team_raw
            if match.season and match.season not in seasons:
                seasons.append(match.season)
            if home_name == featured_match.home_team and away_name == featured_match.away_team:
                home_goals = int(match.home_score or 0)
                away_goals = int(match.away_score or 0)
            else:
                home_goals = int(match.away_score or 0)
                away_goals = int(match.home_score or 0)
            home_record.goals_for += home_goals
            home_record.goals_against += away_goals
            away_record.goals_for += away_goals
            away_record.goals_against += home_goals
            if home_goals > away_goals:
                home_record.wins += 1
                away_record.losses += 1
            elif home_goals < away_goals:
                home_record.losses += 1
                away_record.wins += 1
            else:
                home_record.draws += 1
                away_record.draws += 1

        matches_played = len(filtered_rows)
        if matches_played:
            home_record.avg_goals_for = round(home_record.goals_for / matches_played, 2)
            home_record.avg_goals_against = round(home_record.goals_against / matches_played, 2)
            away_record.avg_goals_for = round(away_record.goals_for / matches_played, 2)
            away_record.avg_goals_against = round(away_record.goals_against / matches_played, 2)

        return HeadToHeadRecord(
            matches_played=matches_played,
            seasons=seasons,
            home_team=home_record,
            away_team=away_record,
        )

    def _pair_filter(self, db_match: Match | None, featured_match: CompetitionMatchView):
        if db_match is not None and db_match.home_team_id is not None and db_match.away_team_id is not None:
            return or_(
                and_(
                    Match.home_team_id == db_match.home_team_id,
                    Match.away_team_id == db_match.away_team_id,
                ),
                and_(
                    Match.home_team_id == db_match.away_team_id,
                    Match.away_team_id == db_match.home_team_id,
                ),
            )
        return or_(
            and_(
                Match.home_team_raw == featured_match.home_team,
                Match.away_team_raw == featured_match.away_team,
            ),
            and_(
                Match.home_team_raw == featured_match.away_team,
                Match.away_team_raw == featured_match.home_team,
            ),
        )

    def _limit_h2h_rows_by_season(self, rows, *, season_limit: int):
        if season_limit <= 0:
            return list(rows)
        selected = []
        seasons: list[str] = []
        for row in rows:
            season = row.Match.season
            if season is not None and season not in seasons:
                if len(seasons) >= season_limit:
                    continue
                seasons.append(season)
            selected.append(row)
        return selected

    def _load_match(self, competition_id: int, featured_match: CompetitionMatchView) -> Match | None:
        return self.session.scalar(
            select(Match).where(
                Match.competition_id == competition_id,
                Match.source_url == featured_match.source_url,
            )
        )

    def _editorial_hooks(self, context: FeaturedMatchPreviewContext) -> list[str]:
        hooks: list[str] = []
        home_form = context.home_form
        away_form = context.away_form
        if home_form is not None and away_form is not None:
            hooks.append(
                f"Forma ultimos {context.form_window}: {context.featured_match.home_team} {home_form.sequence} ({home_form.points} pts) "
                f"vs {context.featured_match.away_team} {away_form.sequence} ({away_form.points} pts)"
            )
        if context.home_analytics is not None and context.away_analytics is not None:
            home_trend = context.home_analytics.recent_trend
            away_trend = context.away_analytics.recent_trend
            hooks.append(
                f"Tendencia PPG: {context.featured_match.home_team} {home_trend.recent_points_per_game} "
                f"vs {context.featured_match.away_team} {away_trend.recent_points_per_game}"
            )
            hooks.append(
                f"Ritmo de temporada: {context.featured_match.home_team} proyecta "
                f"{context.home_analytics.season_pace.projected_final_points} pts y "
                f"{context.featured_match.away_team} {context.away_analytics.season_pace.projected_final_points}"
            )

        home_implication = context.zone_context.home_team.win_scenario.implication
        away_implication = context.zone_context.away_team.win_scenario.implication
        if home_implication:
            hooks.append(f"{context.featured_match.home_team}: {home_implication}.")
        if away_implication:
            hooks.append(f"{context.featured_match.away_team}: {away_implication}.")

        home_gap_text = self._gap_hook(context.featured_match.home_team, context.zone_context.home_team)
        away_gap_text = self._gap_hook(context.featured_match.away_team, context.zone_context.away_team)
        if home_gap_text:
            hooks.append(home_gap_text)
        if away_gap_text:
            hooks.append(away_gap_text)

        if context.head_to_head.matches_played:
            h2h = context.head_to_head
            hooks.append(
                f"H2H ultimos {h2h.matches_played}: {h2h.home_team.team} {h2h.home_team.wins}V {h2h.home_team.draws}E {h2h.home_team.losses}D "
                f"ante {h2h.away_team.team}"
            )
        return hooks

    def _gap_hook(self, team_name: str, zone_context) -> str | None:
        snapshot = zone_context.current
        gaps = snapshot.gaps
        if snapshot.zone == "relegation" and gaps.points_to_safety is not None:
            return f"{team_name} arranca a {gaps.points_to_safety} puntos de la salvacion."
        if snapshot.zone not in {"leader", "playoff"} and gaps.points_to_playoff is not None:
            return f"{team_name} empieza a {gaps.points_to_playoff} puntos del playoff."
        if snapshot.zone == "leader" and gaps.points_to_leader == 0:
            return f"{team_name} defiende el liderato."
        if snapshot.zone == "playoff" and gaps.margin_above_playoff is not None:
            return f"{team_name} protege el playoff con {gaps.margin_above_playoff} puntos de margen."
        if snapshot.zone == "safe" and gaps.margin_above_relegation is not None:
            return f"{team_name} tiene {gaps.margin_above_relegation} puntos sobre el descenso."
        return None

    def _competition(self, competition_code: str) -> Competition:
        competition = self.session.scalar(
            select(Competition).where(Competition.code == competition_code)
        )
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_code}")
        return competition

    def _reference_date(self, reference_date: date | None) -> date:
        if reference_date is not None:
            return reference_date
        return datetime.now(ZoneInfo(self.settings.timezone)).date()
