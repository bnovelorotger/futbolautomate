from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import MatchEventType
from app.db.models import Match, MatchEvent
from app.schemas.match_event import TopScorerResult, TopScorerRowView
from app.utils.time import utcnow


class TopScorerTrackerService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def top_scorers_for_competition(
        self,
        competition_slug: str,
        *,
        limit: int = 10,
    ) -> TopScorerResult:
        rows = self.session.execute(
            select(MatchEvent, Match)
            .join(Match, Match.id == MatchEvent.match_id)
            .where(
                Match.competition.has(code=competition_slug),
                MatchEvent.event_type == str(MatchEventType.GOAL),
            )
            .order_by(Match.match_date.asc().nullslast(), MatchEvent.sort_order.asc(), MatchEvent.id.asc())
        ).all()

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
            key=lambda item: (-item.goals, item.latest_goal_date or utcnow().date(), item.player.lower(), item.team.lower()),
            reverse=False,
        )
        ordered = sorted(
            ordered,
            key=lambda item: (-item.goals, -(item.latest_goal_date.toordinal() if item.latest_goal_date else 0), item.player.lower(), item.team.lower()),
        )[:limit]

        return TopScorerResult(
            competition_slug=competition_slug,
            generated_at=utcnow(),
            rows=ordered,
        )
