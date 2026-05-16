from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import MatchEventType, MatchStatus
from app.db.models import Match, MatchEvent
from app.schemas.match_event import TopScorerResult, TopScorerRowView
from app.utils.time import utcnow

MIN_TOP_SCORER_SCORER_MATCHES = 2
MIN_TOP_SCORER_GOAL_EVENTS = 4
MIN_TOP_SCORER_LEADER_GOALS = 3


class TopScorerTrackerService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def top_scorers_for_competition(
        self,
        competition_slug: str,
        *,
        limit: int = 10,
        reference_date: date | None = None,
    ) -> TopScorerResult:
        selected_date = reference_date or utcnow().date()
        season = self._current_season_for_competition(
            competition_slug,
            reference_date=selected_date,
        )
        query = (
            select(MatchEvent, Match)
            .join(Match, Match.id == MatchEvent.match_id)
            .where(
                Match.competition.has(code=competition_slug),
                Match.status == str(MatchStatus.FINISHED),
                Match.match_date.is_not(None),
                Match.match_date <= selected_date,
                MatchEvent.event_type == str(MatchEventType.GOAL),
            )
            .order_by(Match.match_date.asc().nullslast(), MatchEvent.sort_order.asc(), MatchEvent.id.asc())
        )
        if season:
            query = query.where(Match.season == season)
        rows = self.session.execute(query).all()
        scorer_match_ids = {
            row.Match.id
            for row in rows
            if row.Match.id is not None
        }

        player_rows: dict[tuple[str, str], TopScorerRowView] = {}
        goal_counts: dict[tuple[str, str], int] = defaultdict(int)
        latest_dates: dict[tuple[str, str], object] = {}

        for row in rows:
            event = row.MatchEvent
            match = row.Match
            player = (event.player_raw or "").strip()
            if not player:
                continue
            team = match.home_team_raw if event.team_side == "home" else match.away_team_raw
            key = (player, team)
            goal_counts[key] += 1
            latest_dates[key] = match.match_date

        for key, goals in goal_counts.items():
            player, team = key
            player_rows[key] = TopScorerRowView(
                player=player,
                team=team,
                goals=goals,
                latest_goal_date=latest_dates.get(key),
            )

        ordered = sorted(
            player_rows.values(),
            key=lambda item: (-item.goals, -(item.latest_goal_date.toordinal() if item.latest_goal_date else 0), item.player.lower(), item.team.lower()),
        )[:limit]

        return TopScorerResult(
            competition_slug=competition_slug,
            season=season,
            reference_date=selected_date,
            scorer_matches_count=len(scorer_match_ids),
            goal_events_count=len(rows),
            distinct_scorers_count=len(player_rows),
            generated_at=utcnow(),
            rows=ordered,
        )

    def _current_season_for_competition(
        self,
        competition_slug: str,
        *,
        reference_date: date,
    ) -> str | None:
        return self.session.scalar(
            select(Match.season)
            .where(
                Match.competition.has(code=competition_slug),
                Match.status == str(MatchStatus.FINISHED),
                Match.match_date.is_not(None),
                Match.match_date <= reference_date,
                Match.season.is_not(None),
            )
            .order_by(Match.match_date.desc(), Match.id.desc())
            .limit(1)
        )
