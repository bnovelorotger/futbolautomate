from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import get_settings
from app.core.enums import MatchWindow
from app.core.exceptions import ConfigurationError
from app.db.models import Competition, Match
from app.schemas.editorial_summary import (
    CompetitionEditorialSummary,
    EditorialAggregateMetrics,
    EditorialCalendarWindows,
    EditorialCompetitionState,
    EditorialRankings,
    EditorialSummaryMetadata,
    EditorialSummaryNewsItem,
)
from app.schemas.reporting import EditorialNewsView
from app.services.competition_queries import CompetitionQueryService
from app.services.competition_relevance import CompetitionRelevanceService
from app.services.news_editorial_queries import NewsEditorialQueryService
from app.utils.time import utcnow
from app.normalizers.text import normalize_token


def _has_club_overlap(clubs: set[str], team_names: set[str]) -> bool:
    for club in clubs:
        if not club:
            continue
        for team_name in team_names:
            if not team_name:
                continue
            if club == team_name or club in team_name or team_name in club:
                return True
    return False


def prioritize_editorial_news(
    news_items: list[EditorialNewsView],
    competition_names: set[str],
    team_names: set[str],
    limit: int,
) -> list[EditorialSummaryNewsItem]:
    buckets = {
        "competition_detected": [],
        "club_overlap": [],
        "general_context": [],
    }

    for item in news_items:
        normalized_competition = normalize_token(item.competition_detected or "")
        normalized_clubs = {normalize_token(club) for club in item.clubs_detected or []}
        if normalized_competition and normalized_competition in competition_names:
            reason = "competition_detected"
        elif _has_club_overlap(normalized_clubs, team_names):
            reason = "club_overlap"
        else:
            reason = "general_context"
        buckets[reason].append(
            EditorialSummaryNewsItem(
                source_name=item.source_name,
                source_url=item.source_url,
                title=item.title,
                published_at=item.published_at,
                summary=item.summary,
                clubs_detected=item.clubs_detected,
                competition_detected=item.competition_detected,
                editorial_relevance_score=item.editorial_relevance_score,
                selection_reason=reason,
            )
        )

    ordered: list[EditorialSummaryNewsItem] = []
    seen_urls: set[str] = set()
    for reason in ("competition_detected", "club_overlap", "general_context"):
        for item in buckets[reason]:
            if item.source_url in seen_urls:
                continue
            seen_urls.add(item.source_url)
            ordered.append(item)
            if len(ordered) >= limit:
                return ordered
    return ordered


class CompetitionEditorialSummaryService:
    def __init__(self, session: Session, timezone_name: str | None = None) -> None:
        self.session = session
        self.timezone_name = timezone_name or get_settings().timezone
        self.competition_queries = CompetitionQueryService(session, timezone_name=self.timezone_name)
        self.relevance = CompetitionRelevanceService()
        self.news_queries = NewsEditorialQueryService(session)

    def _reference_date(self, reference_date: date | None) -> date:
        if reference_date is not None:
            return reference_date
        return datetime.now(ZoneInfo(self.timezone_name)).date()

    def _competition(self, competition_code: str) -> Competition:
        competition = self.session.scalar(select(Competition).where(Competition.code == competition_code))
        if competition is None:
            raise ValueError(f"Competicion desconocida: {competition_code}")
        return competition

    def _competition_names(self, competition_code: str, competition_name: str) -> set[str]:
        competition_entry = load_competition_catalog().get(competition_code)
        names = {normalize_token(competition_name), normalize_token(competition_code)}
        if competition_entry is not None:
            names.update(normalize_token(alias) for alias in competition_entry.aliases)
            names.add(normalize_token(competition_entry.name))
        return {value for value in names if value}

    def _team_names(self, competition_id: int, competition_code: str, relevant_only: bool) -> set[str]:
        if relevant_only and self.relevance.has_tracked_teams(competition_code):
            return {
                normalize_token(team_name)
                for team_name in self.relevance.tracked_teams(competition_code)
                if team_name
            }
        try:
            standings = self.competition_queries.current_standings(competition_code)
            team_names = {normalize_token(row.team) for row in standings if row.team}
            if team_names:
                return team_names
        except ConfigurationError:
            pass

        teams_subquery = union_all(
            select(Match.home_team_raw.label("team_name")).where(Match.competition_id == competition_id),
            select(Match.away_team_raw.label("team_name")).where(Match.competition_id == competition_id),
        ).subquery()
        rows = self.session.execute(select(teams_subquery.c.team_name)).scalars().all()
        return {normalize_token(team_name) for team_name in rows if team_name}

    def _aggregate_metrics(self, competition_id: int, played_matches: int, relevant_news_count: int) -> EditorialAggregateMetrics:
        goals_expr = func.coalesce(Match.home_score, 0) + func.coalesce(Match.away_score, 0)
        total_goals = self.session.scalar(
            select(func.coalesce(func.sum(goals_expr), 0)).where(
                Match.competition_id == competition_id,
                Match.status == "finished",
            )
        ) or 0
        average_goals = round(total_goals / played_matches, 2) if played_matches else None
        return EditorialAggregateMetrics(
            total_goals_scored=int(total_goals),
            average_goals_per_played_match=average_goals,
            relevant_news_count=relevant_news_count,
        )

    def build_competition_summary(
        self,
        competition_code: str,
        reference_date: date | None = None,
        results_limit: int = 5,
        upcoming_limit: int = 5,
        news_limit: int = 5,
        standings_limit: int = 5,
        relevant_only: bool = True,
    ) -> CompetitionEditorialSummary:
        current_date = self._reference_date(reference_date)
        competition = self._competition(competition_code)

        competition_state = self.competition_queries.summary(competition_code)
        latest_results = self.competition_queries.latest_results(
            competition_code,
            limit=results_limit,
            relevant_only=relevant_only,
        )
        upcoming_matches = self.competition_queries.upcoming_matches(
            competition_code,
            limit=upcoming_limit,
            relevant_only=relevant_only,
            reference_date=current_date,
        )
        try:
            standings_source = self.competition_queries.current_standings(competition_code)
            standings = self._editorial_standings(
                competition_code,
                standings_source,
                relevant_only=relevant_only,
                limit=standings_limit,
            )
            best_attack = next(
                iter(
                    self.relevance.top_scoring_teams_from_standings(
                        competition_code,
                        standings_source if relevant_only else standings,
                        limit=1,
                    )
                ),
                None,
            )
            best_defense = next(
                iter(
                    self.relevance.best_defense_teams_from_standings(
                        competition_code,
                        standings_source if relevant_only else standings,
                        limit=1,
                    )
                ),
                None,
            )
            most_wins = next(
                iter(
                    self.relevance.most_wins_teams_from_standings(
                        competition_code,
                        standings_source if relevant_only else standings,
                        limit=1,
                    )
                ),
                None,
            )
        except ConfigurationError:
            standings = []
            best_attack = None
            best_defense = None
            most_wins = None

        windows = EditorialCalendarWindows(
            today=self.competition_queries.matches_in_window(
                competition_code,
                MatchWindow.TODAY,
                reference_date=current_date,
                relevant_only=relevant_only,
            ).matches,
            tomorrow=self.competition_queries.matches_in_window(
                competition_code,
                MatchWindow.TOMORROW,
                reference_date=current_date,
                relevant_only=relevant_only,
            ).matches,
            next_weekend=self.competition_queries.matches_in_window(
                competition_code,
                MatchWindow.NEXT_WEEKEND,
                reference_date=current_date,
                relevant_only=relevant_only,
            ).matches,
        )

        relevant_news_candidates = self.news_queries.relevant_balearic_football(limit=200)
        prioritized_news = prioritize_editorial_news(
            news_items=relevant_news_candidates,
            competition_names=self._competition_names(competition_code, competition.name),
            team_names=self._team_names(competition.id, competition_code, relevant_only=relevant_only),
            limit=news_limit,
        )

        aggregate_metrics = self._aggregate_metrics(
            competition_id=competition.id,
            played_matches=competition_state.played_matches,
            relevant_news_count=len(prioritized_news),
        )

        return CompetitionEditorialSummary(
            metadata=EditorialSummaryMetadata(
                competition_slug=competition_code,
                competition_name=competition_state.competition_name,
                reference_date=current_date,
                generated_at=utcnow(),
            ),
            competition_state=EditorialCompetitionState(
                total_teams=competition_state.total_teams,
                total_matches=competition_state.total_matches,
                played_matches=competition_state.played_matches,
                pending_matches=competition_state.pending_matches,
            ),
            latest_results=latest_results,
            upcoming_matches=upcoming_matches,
            current_standings=standings,
            rankings=EditorialRankings(
                best_attack=best_attack,
                best_defense=best_defense,
                most_wins=most_wins,
            ),
            calendar_windows=windows,
            editorial_news=prioritized_news,
            aggregate_metrics=aggregate_metrics,
        )

    def _editorial_standings(
        self,
        competition_code: str,
        standings: list,
        *,
        relevant_only: bool,
        limit: int,
    ) -> list:
        rows = list(standings)
        if relevant_only:
            rows = self.relevance.filter_standing_views(competition_code, rows)
        return rows[:limit]
