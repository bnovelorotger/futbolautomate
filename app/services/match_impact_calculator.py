from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import ConfigurationError
from app.core.standings_zones import CompetitionStandingsZones, load_standings_zones
from app.db.models import Competition
from app.schemas.match_impact import (
    MatchImpactMatchView,
    MatchImpactOutcomeView,
    MatchImpactResult,
    MatchImpactScenario,
    MatchImpactTableRowView,
    MatchImpactTeamStateView,
    MatchImpactZoneCrossingView,
)
from app.schemas.reporting import CompetitionMatchView, StandingView
from app.services.competition_queries import CompetitionQueryService
from app.utils.time import utcnow

ZoneResolver = Callable[[str, list[StandingView]], dict[str, list[str]]]


@dataclass(slots=True)
class _MutableStandingRow:
    team: str
    position: int
    points: int | None
    played: int | None
    wins: int | None
    draws: int | None
    losses: int | None
    goals_for: int | None
    goals_against: int | None
    goal_difference: int | None


class MatchImpactCalculatorService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        queries: CompetitionQueryService | None = None,
        zones: dict[str, CompetitionStandingsZones] | None = None,
        zone_resolver: ZoneResolver | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.queries = queries or CompetitionQueryService(session)
        self.zones = zones or load_standings_zones()
        self.zone_resolver = zone_resolver

    def preview_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
        limit: int | None = None,
        relevant_only: bool = False,
    ) -> MatchImpactResult:
        competition = self._competition(competition_code)
        selected_date = self._reference_date(reference_date)
        standings = self.queries.current_standings(competition_code, limit=None)
        matches = self.queries.editorial_upcoming_matches(
            competition_code,
            limit=None,
            relevant_only=relevant_only,
            reference_date=selected_date,
        )

        rows: list[MatchImpactMatchView] = []
        standings_teams = {row.team for row in standings}
        for match in matches:
            if match.home_team not in standings_teams or match.away_team not in standings_teams:
                continue
            rows.append(
                self.analyze_match(
                    competition_code,
                    match,
                    standings=standings,
                    competition_name=competition.name,
                )
            )

        rows.sort(
            key=lambda row: (
                -row.max_zone_crossings,
                -row.total_zone_crossings,
                -row.impact_score,
                row.match_date or date.max,
                row.source_url,
            )
        )
        if limit is not None:
            rows = rows[:limit]

        return MatchImpactResult(
            competition_slug=competition_code,
            competition_name=competition.name,
            reference_date=selected_date,
            generated_at=utcnow(),
            rows=rows,
        )

    def analyze_match(
        self,
        competition_code: str,
        match: CompetitionMatchView,
        *,
        standings: list[StandingView] | None = None,
        competition_name: str | None = None,
    ) -> MatchImpactMatchView:
        competition = None
        resolved_competition_name = competition_name
        if resolved_competition_name is None:
            competition = self._competition(competition_code)
            resolved_competition_name = competition.name

        current_standings = standings or self.queries.current_standings(competition_code, limit=None)
        standings_map = {row.team: row for row in current_standings}
        home_row = standings_map.get(match.home_team)
        away_row = standings_map.get(match.away_team)
        if home_row is None or away_row is None:
            raise ConfigurationError(
                f"No hay clasificacion suficiente para simular {match.home_team} vs {match.away_team}"
            )

        current_zone_tags = self._resolve_zone_tags(competition_code, current_standings)
        scenarios = [
            self._simulate_scenario(
                competition_code,
                match,
                current_standings,
                current_zone_tags=current_zone_tags,
                scenario=scenario,
            )
            for scenario in (
                MatchImpactScenario.HOME_WIN,
                MatchImpactScenario.DRAW,
                MatchImpactScenario.AWAY_WIN,
            )
        ]

        max_zone_crossings = max((item.crossing_count for item in scenarios), default=0)
        total_zone_crossings = sum(item.crossing_count for item in scenarios)
        max_position_swing = max(
            max(
                abs(item.home_team.position_delta or 0),
                abs(item.away_team.position_delta or 0),
            )
            for item in scenarios
        )
        impact_score = (max_zone_crossings * 100) + (total_zone_crossings * 10) + max_position_swing

        return MatchImpactMatchView(
            competition_slug=competition_code,
            competition_name=resolved_competition_name or competition.name,
            round_name=match.round_name,
            match_date=match.match_date,
            source_url=match.source_url,
            home_team=match.home_team,
            away_team=match.away_team,
            home_team_state=self._baseline_team_state(
                home_row,
                current_zone_tags.get(match.home_team, []),
            ),
            away_team_state=self._baseline_team_state(
                away_row,
                current_zone_tags.get(match.away_team, []),
            ),
            max_zone_crossings=max_zone_crossings,
            total_zone_crossings=total_zone_crossings,
            impact_score=impact_score,
            scenarios=scenarios,
        )

    def _simulate_scenario(
        self,
        competition_code: str,
        match: CompetitionMatchView,
        current_standings: list[StandingView],
        *,
        current_zone_tags: dict[str, list[str]],
        scenario: MatchImpactScenario,
    ) -> MatchImpactOutcomeView:
        simulated_rows = self._clone_standings(current_standings)
        row_map = {row.team: row for row in simulated_rows}
        home_row = row_map[match.home_team]
        away_row = row_map[match.away_team]
        self._apply_result(home_row, away_row, scenario)

        ordered_rows = sorted(simulated_rows, key=self._sort_key)
        for position, row in enumerate(ordered_rows, start=1):
            row.position = position

        projected_standings = [self._standing_view(row) for row in ordered_rows]
        projected_zone_tags = self._resolve_zone_tags(competition_code, projected_standings)
        zone_crossings = self._detect_zone_crossings(
            competition_code,
            current_standings,
            projected_standings,
            current_zone_tags=current_zone_tags,
            projected_zone_tags=projected_zone_tags,
        )

        current_map = {row.team: row for row in current_standings}
        projected_map = {row.team: row for row in projected_standings}
        projected_table = [
            MatchImpactTableRowView(
                position=row.position,
                team=row.team,
                points=row.points,
                played=row.played,
                wins=row.wins,
                draws=row.draws,
                losses=row.losses,
                goals_for=row.goals_for,
                goals_against=row.goals_against,
                goal_difference=row.goal_difference,
                zone_tags=projected_zone_tags.get(row.team, []),
            )
            for row in projected_standings
        ]

        impacted_zones = self._ordered_impacted_zones(zone_crossings)
        return MatchImpactOutcomeView(
            scenario=scenario,
            label=self._scenario_label(match, scenario),
            crossing_count=len(zone_crossings),
            impacted_zones=impacted_zones,
            zone_crossings=zone_crossings,
            home_team=self._projected_team_state(
                current_map[match.home_team],
                projected_map[match.home_team],
                current_zone_tags=current_zone_tags.get(match.home_team, []),
                projected_zone_tags=projected_zone_tags.get(match.home_team, []),
            ),
            away_team=self._projected_team_state(
                current_map[match.away_team],
                projected_map[match.away_team],
                current_zone_tags=current_zone_tags.get(match.away_team, []),
                projected_zone_tags=projected_zone_tags.get(match.away_team, []),
            ),
            projected_table=projected_table,
        )

    def _detect_zone_crossings(
        self,
        competition_code: str,
        current_standings: list[StandingView],
        projected_standings: list[StandingView],
        *,
        current_zone_tags: dict[str, list[str]],
        projected_zone_tags: dict[str, list[str]],
    ) -> list[MatchImpactZoneCrossingView]:
        current_map = {row.team: row for row in current_standings}
        projected_map = {row.team: row for row in projected_standings}
        crossings: list[MatchImpactZoneCrossingView] = []

        zone_config = self.zones.get(competition_code, CompetitionStandingsZones())
        playoff_positions = set(zone_config.playoff_positions)
        relegation_positions = set(zone_config.relegation_positions)

        if self.zone_resolver is not None:
            all_zones = sorted(
                {
                    *(
                        zone
                        for tags in current_zone_tags.values()
                        for zone in tags
                    ),
                    *(
                        zone
                        for tags in projected_zone_tags.values()
                        for zone in tags
                    ),
                }
            )
            for team, current_row in current_map.items():
                projected_row = projected_map.get(team)
                if projected_row is None:
                    continue
                previous_tags = set(current_zone_tags.get(team, []))
                next_tags = set(projected_zone_tags.get(team, []))
                for zone in all_zones:
                    if zone in next_tags and zone not in previous_tags:
                        crossings.append(
                            MatchImpactZoneCrossingView(
                                team=team,
                                event_type=f"entered_{zone}",
                                zone=zone,
                                previous_position=current_row.position,
                                projected_position=projected_row.position,
                                previous_zone_tags=sorted(previous_tags),
                                projected_zone_tags=sorted(next_tags),
                            )
                        )
                    if zone in previous_tags and zone not in next_tags:
                        crossings.append(
                            MatchImpactZoneCrossingView(
                                team=team,
                                event_type=f"left_{zone}",
                                zone=zone,
                                previous_position=current_row.position,
                                projected_position=projected_row.position,
                                previous_zone_tags=sorted(previous_tags),
                                projected_zone_tags=sorted(next_tags),
                            )
                        )
            return sorted(crossings, key=self._crossing_sort_key)

        for team, current_row in current_map.items():
            projected_row = projected_map.get(team)
            if projected_row is None:
                continue
            previous_tags = current_zone_tags.get(team, [])
            next_tags = projected_zone_tags.get(team, [])

            current_in_playoff = current_row.position in playoff_positions
            projected_in_playoff = projected_row.position in playoff_positions
            current_in_relegation = current_row.position in relegation_positions
            projected_in_relegation = projected_row.position in relegation_positions

            if playoff_positions and projected_in_playoff and not current_in_playoff and current_row.position != 1:
                crossings.append(
                    MatchImpactZoneCrossingView(
                        team=team,
                        event_type="entered_playoff",
                        zone="playoff",
                        previous_position=current_row.position,
                        projected_position=projected_row.position,
                        previous_zone_tags=list(previous_tags),
                        projected_zone_tags=list(next_tags),
                    )
                )
            if playoff_positions and current_in_playoff and not projected_in_playoff and projected_row.position != 1:
                crossings.append(
                    MatchImpactZoneCrossingView(
                        team=team,
                        event_type="left_playoff",
                        zone="playoff",
                        previous_position=current_row.position,
                        projected_position=projected_row.position,
                        previous_zone_tags=list(previous_tags),
                        projected_zone_tags=list(next_tags),
                    )
                )
            if relegation_positions and projected_in_relegation and not current_in_relegation:
                crossings.append(
                    MatchImpactZoneCrossingView(
                        team=team,
                        event_type="entered_relegation",
                        zone="relegation",
                        previous_position=current_row.position,
                        projected_position=projected_row.position,
                        previous_zone_tags=list(previous_tags),
                        projected_zone_tags=list(next_tags),
                    )
                )
            if relegation_positions and current_in_relegation and not projected_in_relegation:
                crossings.append(
                    MatchImpactZoneCrossingView(
                        team=team,
                        event_type="left_relegation",
                        zone="relegation",
                        previous_position=current_row.position,
                        projected_position=projected_row.position,
                        previous_zone_tags=list(previous_tags),
                        projected_zone_tags=list(next_tags),
                    )
                )

        return sorted(crossings, key=self._crossing_sort_key)

    def _resolve_zone_tags(
        self,
        competition_code: str,
        standings: list[StandingView],
    ) -> dict[str, list[str]]:
        if self.zone_resolver is not None:
            resolved = self.zone_resolver(competition_code, standings)
            return {team: list(tags) for team, tags in resolved.items()}

        zone_config = self.zones.get(competition_code, CompetitionStandingsZones())
        playoff_positions = set(zone_config.playoff_positions)
        relegation_positions = set(zone_config.relegation_positions)
        resolved: dict[str, list[str]] = {}
        for row in standings:
            tags: list[str] = []
            if row.position in playoff_positions:
                tags.append("playoff")
            if row.position in relegation_positions:
                tags.append("relegation")
            resolved[row.team] = tags
        return resolved

    def _apply_result(
        self,
        home_row: _MutableStandingRow,
        away_row: _MutableStandingRow,
        scenario: MatchImpactScenario,
    ) -> None:
        home_row.played = self._increment(home_row.played)
        away_row.played = self._increment(away_row.played)

        if scenario == MatchImpactScenario.HOME_WIN:
            home_row.points = self._increment(home_row.points, amount=3)
            home_row.wins = self._increment(home_row.wins)
            away_row.losses = self._increment(away_row.losses)
            return

        if scenario == MatchImpactScenario.DRAW:
            home_row.points = self._increment(home_row.points)
            away_row.points = self._increment(away_row.points)
            home_row.draws = self._increment(home_row.draws)
            away_row.draws = self._increment(away_row.draws)
            return

        away_row.points = self._increment(away_row.points, amount=3)
        away_row.wins = self._increment(away_row.wins)
        home_row.losses = self._increment(home_row.losses)

    def _clone_standings(self, standings: list[StandingView]) -> list[_MutableStandingRow]:
        return [
            _MutableStandingRow(
                team=row.team,
                position=row.position,
                points=row.points,
                played=row.played,
                wins=row.wins,
                draws=row.draws,
                losses=row.losses,
                goals_for=row.goals_for,
                goals_against=row.goals_against,
                goal_difference=row.goal_difference,
            )
            for row in standings
        ]

    def _standing_view(self, row: _MutableStandingRow) -> StandingView:
        return StandingView(
            position=row.position,
            team=row.team,
            points=row.points,
            played=row.played,
            wins=row.wins,
            draws=row.draws,
            losses=row.losses,
            goals_for=row.goals_for,
            goals_against=row.goals_against,
            goal_difference=row.goal_difference,
        )

    def _baseline_team_state(
        self,
        row: StandingView,
        zone_tags: list[str],
    ) -> MatchImpactTeamStateView:
        return MatchImpactTeamStateView(
            team=row.team,
            current_position=row.position,
            current_points=row.points,
            current_zone_tags=list(zone_tags),
        )

    def _projected_team_state(
        self,
        current_row: StandingView,
        projected_row: StandingView,
        *,
        current_zone_tags: list[str],
        projected_zone_tags: list[str],
    ) -> MatchImpactTeamStateView:
        return MatchImpactTeamStateView(
            team=current_row.team,
            current_position=current_row.position,
            current_points=current_row.points,
            current_zone_tags=list(current_zone_tags),
            projected_position=projected_row.position,
            projected_points=projected_row.points,
            projected_zone_tags=list(projected_zone_tags),
            position_delta=current_row.position - projected_row.position,
            points_delta=(projected_row.points or 0) - (current_row.points or 0),
        )

    def _scenario_label(self, match: CompetitionMatchView, scenario: MatchImpactScenario) -> str:
        if scenario == MatchImpactScenario.HOME_WIN:
            return f"Gana {match.home_team}"
        if scenario == MatchImpactScenario.DRAW:
            return "Empate"
        return f"Gana {match.away_team}"

    def _ordered_impacted_zones(
        self,
        crossings: list[MatchImpactZoneCrossingView],
    ) -> list[str]:
        priority = {"playoff": 0, "relegation": 1}
        zones = {crossing.zone for crossing in crossings}
        return sorted(zones, key=lambda zone: (priority.get(zone, 99), zone))

    def _crossing_sort_key(self, crossing: MatchImpactZoneCrossingView) -> tuple[int, int, str, str]:
        priority = {
            "entered_playoff": 0,
            "left_playoff": 1,
            "left_relegation": 2,
            "entered_relegation": 3,
        }
        return (
            priority.get(crossing.event_type, 99),
            crossing.projected_position or 999,
            crossing.team.lower(),
            crossing.zone,
        )

    def _sort_key(self, row: _MutableStandingRow) -> tuple[int, int, int, int, str]:
        return (
            -(row.points or 0),
            -(row.goal_difference or 0),
            -(row.goals_for or 0),
            row.position,
            row.team.lower(),
        )

    def _increment(self, value: int | None, *, amount: int = 1) -> int:
        return (value or 0) + amount

    def _competition(self, competition_code: str) -> Competition:
        competition = self.session.scalar(
            select(Competition).where(Competition.code == competition_code)
        )
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_code}")
        return competition

    def _reference_date(self, reference_date: date | None = None) -> date:
        if reference_date is not None:
            return reference_date
        return datetime.now(ZoneInfo(self.settings.timezone)).date()
