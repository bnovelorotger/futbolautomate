from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import case, func, or_, select, union_all
from sqlalchemy.orm import aliased

from app.db.models import Match, Standing, Team
from app.db.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class TeamVenueSplitRow:
    team: str
    venue: str
    played: int
    wins: int
    draws: int
    losses: int
    points: int
    goals_for: int
    goals_against: int

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against


@dataclass(frozen=True, slots=True)
class TeamScheduleRow:
    team: str
    total_matches: int


class StandingRepository(BaseRepository[Standing]):
    def get_existing(self, payload: dict) -> Standing | None:
        by_team_raw = self.session.scalar(
            select(Standing).where(
                Standing.source_name == payload["source_name"],
                Standing.competition_id == payload["competition_id"],
                Standing.season == payload.get("season"),
                Standing.group_name == payload.get("group_name"),
                Standing.team_raw == payload["team_raw"],
            )
        )
        if by_team_raw is not None:
            return by_team_raw

        team_id = payload.get("team_id")
        if team_id is not None:
            by_team_id = self.session.scalar(
                select(Standing).where(
                    Standing.source_name == payload["source_name"],
                    Standing.competition_id == payload["competition_id"],
                    Standing.season == payload.get("season"),
                    Standing.group_name == payload.get("group_name"),
                    Standing.team_id == team_id,
                )
            )
            if by_team_id is not None:
                return by_team_id

        return self.session.scalar(
            select(Standing).where(
                Standing.source_name == payload["source_name"],
                Standing.competition_id == payload["competition_id"],
                Standing.season == payload.get("season"),
                Standing.group_name == payload.get("group_name"),
                Standing.position == payload["position"],
            )
        )

    def upsert(self, payload: dict) -> tuple[Standing, bool, bool]:
        existing = self.get_existing(payload)
        if existing is None:
            item = Standing(**payload)
            self.session.add(item)
            self.session.flush()
            return item, True, False

        if existing.content_hash == payload["content_hash"]:
            return existing, False, False

        for key, value in payload.items():
            setattr(existing, key, value)
        self.session.flush()
        return existing, False, True

    def team_venue_splits(
        self,
        competition_id: int,
        *,
        reference_date: date | None = None,
    ) -> list[TeamVenueSplitRow]:
        home_team = aliased(Team)
        away_team = aliased(Team)
        filters = [
            Match.competition_id == competition_id,
            Match.status == "finished",
            Match.home_score.is_not(None),
            Match.away_score.is_not(None),
        ]
        if reference_date is not None:
            filters.append(or_(Match.match_date.is_(None), Match.match_date <= reference_date))

        home_rows = self.session.execute(
            select(
                func.coalesce(home_team.name, Match.home_team_raw).label("team"),
                func.count(Match.id).label("played"),
                func.sum(case((Match.home_score > Match.away_score, 1), else_=0)).label("wins"),
                func.sum(case((Match.home_score == Match.away_score, 1), else_=0)).label("draws"),
                func.sum(case((Match.home_score < Match.away_score, 1), else_=0)).label("losses"),
                func.sum(
                    case(
                        (Match.home_score > Match.away_score, 3),
                        (Match.home_score == Match.away_score, 1),
                        else_=0,
                    )
                ).label("points"),
                func.sum(Match.home_score).label("goals_for"),
                func.sum(Match.away_score).label("goals_against"),
            )
            .select_from(Match)
            .outerjoin(home_team, home_team.id == Match.home_team_id)
            .where(*filters)
            .group_by(func.coalesce(home_team.name, Match.home_team_raw))
        ).all()

        away_rows = self.session.execute(
            select(
                func.coalesce(away_team.name, Match.away_team_raw).label("team"),
                func.count(Match.id).label("played"),
                func.sum(case((Match.away_score > Match.home_score, 1), else_=0)).label("wins"),
                func.sum(case((Match.away_score == Match.home_score, 1), else_=0)).label("draws"),
                func.sum(case((Match.away_score < Match.home_score, 1), else_=0)).label("losses"),
                func.sum(
                    case(
                        (Match.away_score > Match.home_score, 3),
                        (Match.away_score == Match.home_score, 1),
                        else_=0,
                    )
                ).label("points"),
                func.sum(Match.away_score).label("goals_for"),
                func.sum(Match.home_score).label("goals_against"),
            )
            .select_from(Match)
            .outerjoin(away_team, away_team.id == Match.away_team_id)
            .where(*filters)
            .group_by(func.coalesce(away_team.name, Match.away_team_raw))
        ).all()

        results: list[TeamVenueSplitRow] = []
        for venue, rows in (("home", home_rows), ("away", away_rows)):
            for row in rows:
                results.append(
                    TeamVenueSplitRow(
                        team=str(row.team),
                        venue=venue,
                        played=int(row.played or 0),
                        wins=int(row.wins or 0),
                        draws=int(row.draws or 0),
                        losses=int(row.losses or 0),
                        points=int(row.points or 0),
                        goals_for=int(row.goals_for or 0),
                        goals_against=int(row.goals_against or 0),
                    )
                )
        return sorted(results, key=lambda item: (item.team, item.venue))

    def team_schedule_counts(self, competition_id: int) -> list[TeamScheduleRow]:
        home_team = aliased(Team)
        away_team = aliased(Team)
        statuses = ("finished", "scheduled")

        home_query = (
            select(
                func.coalesce(home_team.name, Match.home_team_raw).label("team"),
                func.count(Match.id).label("matches"),
            )
            .select_from(Match)
            .outerjoin(home_team, home_team.id == Match.home_team_id)
            .where(
                Match.competition_id == competition_id,
                Match.status.in_(statuses),
            )
            .group_by(func.coalesce(home_team.name, Match.home_team_raw))
        )
        away_query = (
            select(
                func.coalesce(away_team.name, Match.away_team_raw).label("team"),
                func.count(Match.id).label("matches"),
            )
            .select_from(Match)
            .outerjoin(away_team, away_team.id == Match.away_team_id)
            .where(
                Match.competition_id == competition_id,
                Match.status.in_(statuses),
            )
            .group_by(func.coalesce(away_team.name, Match.away_team_raw))
        )
        schedule_totals = union_all(home_query, away_query).subquery("schedule_totals")
        totals = (
            select(
                schedule_totals.c.team,
                func.coalesce(func.sum(schedule_totals.c.matches), 0).label("total_matches"),
            )
            .select_from(schedule_totals)
            .group_by(schedule_totals.c.team)
        )
        rows = self.session.execute(totals).all()
        return [
            TeamScheduleRow(team=str(row.team), total_matches=int(row.total_matches or 0))
            for row in rows
        ]
