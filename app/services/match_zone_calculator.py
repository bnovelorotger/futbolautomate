from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.core.standings_zones import CompetitionStandingsZones, load_standings_zones
from app.schemas.reporting import StandingView

ZoneTag = Literal["leader", "playoff", "relegation", "safe"]
ScenarioResult = Literal["win", "draw", "loss"]


class TeamZoneGaps(BaseModel):
    points_to_leader: int | None = None
    points_to_playoff: int | None = None
    margin_above_playoff: int | None = None
    points_to_safety: int | None = None
    margin_above_relegation: int | None = None


class TeamZoneSnapshot(BaseModel):
    team: str
    position: int | None = None
    points: int | None = None
    zone: ZoneTag | None = None
    zone_label: str | None = None
    gaps: TeamZoneGaps = Field(default_factory=TeamZoneGaps)


class TeamZoneScenario(BaseModel):
    result: ScenarioResult
    points_delta: int
    simulated_position: int | None = None
    simulated_points: int | None = None
    simulated_zone: ZoneTag | None = None
    simulated_zone_label: str | None = None
    position_change: int = 0
    crosses_into: ZoneTag | None = None
    crosses_out_of: ZoneTag | None = None
    implication: str | None = None


class TeamZoneContext(BaseModel):
    team: str
    current: TeamZoneSnapshot
    win_scenario: TeamZoneScenario
    draw_scenario: TeamZoneScenario
    loss_scenario: TeamZoneScenario


class MatchZoneContext(BaseModel):
    home_team: TeamZoneContext
    away_team: TeamZoneContext


_ZONE_LABELS: dict[ZoneTag, str] = {
    "leader": "liderato",
    "playoff": "playoff",
    "relegation": "descenso",
    "safe": "zona media",
}

_RESULT_TO_POINTS: dict[ScenarioResult, int] = {
    "win": 3,
    "draw": 1,
    "loss": 0,
}


class MatchZoneCalculator:
    def __init__(
        self,
        *,
        zones: dict[str, CompetitionStandingsZones] | None = None,
    ) -> None:
        self.zones = zones or load_standings_zones()

    def build_match_context(
        self,
        competition_code: str,
        standings: list[StandingView],
        *,
        home_team: str,
        away_team: str,
    ) -> MatchZoneContext:
        return MatchZoneContext(
            home_team=self.build_team_context(competition_code, standings, team_name=home_team),
            away_team=self.build_team_context(competition_code, standings, team_name=away_team),
        )

    def build_team_context(
        self,
        competition_code: str,
        standings: list[StandingView],
        *,
        team_name: str,
    ) -> TeamZoneContext:
        ordered = self._ordered_rows(standings)
        current_row = next((row for row in ordered if row.team == team_name), None)
        current_zone = self._zone_for_row(competition_code, current_row)
        current_snapshot = TeamZoneSnapshot(
            team=team_name,
            position=current_row.position if current_row is not None else None,
            points=current_row.points if current_row is not None else None,
            zone=current_zone,
            zone_label=self._zone_label(current_zone),
            gaps=self._gaps_for_row(competition_code, ordered, current_row),
        )
        return TeamZoneContext(
            team=team_name,
            current=current_snapshot,
            win_scenario=self._scenario_for_result(
                competition_code,
                ordered,
                team_name=team_name,
                current_snapshot=current_snapshot,
                result="win",
            ),
            draw_scenario=self._scenario_for_result(
                competition_code,
                ordered,
                team_name=team_name,
                current_snapshot=current_snapshot,
                result="draw",
            ),
            loss_scenario=self._scenario_for_result(
                competition_code,
                ordered,
                team_name=team_name,
                current_snapshot=current_snapshot,
                result="loss",
            ),
        )

    def _scenario_for_result(
        self,
        competition_code: str,
        standings: list[StandingView],
        *,
        team_name: str,
        current_snapshot: TeamZoneSnapshot,
        result: ScenarioResult,
    ) -> TeamZoneScenario:
        points_delta = _RESULT_TO_POINTS[result]
        current_position = current_snapshot.position
        current_zone = current_snapshot.zone
        simulated_rows = self._simulate_points_delta(standings, team_name=team_name, points_delta=points_delta)
        simulated_row = next((row for row in simulated_rows if row.team == team_name), None)
        simulated_zone = self._zone_for_row(competition_code, simulated_row)
        simulated_position = simulated_row.position if simulated_row is not None else None
        position_change = (
            0
            if current_position is None or simulated_position is None
            else current_position - simulated_position
        )
        crosses_into, crosses_out_of = self._zone_transition(current_zone, simulated_zone)
        return TeamZoneScenario(
            result=result,
            points_delta=points_delta,
            simulated_position=simulated_position,
            simulated_points=simulated_row.points if simulated_row is not None else None,
            simulated_zone=simulated_zone,
            simulated_zone_label=self._zone_label(simulated_zone),
            position_change=position_change,
            crosses_into=crosses_into,
            crosses_out_of=crosses_out_of,
            implication=self._implication_text(
                result=result,
                current_position=current_position,
                simulated_position=simulated_position,
                current_zone=current_zone,
                simulated_zone=simulated_zone,
            ),
        )

    def _ordered_rows(self, standings: list[StandingView]) -> list[StandingView]:
        return sorted(standings, key=lambda row: row.position)

    def _simulate_points_delta(
        self,
        standings: list[StandingView],
        *,
        team_name: str,
        points_delta: int,
    ) -> list[StandingView]:
        adjusted: list[StandingView] = []
        for row in standings:
            points = row.points if row.points is not None else 0
            if row.team == team_name:
                points += points_delta
            adjusted.append(row.model_copy(update={"points": points}))

        adjusted = sorted(
            adjusted,
            key=lambda row: (
                -(row.points if row.points is not None else -1),
                -(row.goal_difference if row.goal_difference is not None else -10_000),
                -(row.goals_for if row.goals_for is not None else -10_000),
                row.position,
                row.team,
            ),
        )
        return [
            row.model_copy(update={"position": index})
            for index, row in enumerate(adjusted, start=1)
        ]

    def _gaps_for_row(
        self,
        competition_code: str,
        standings: list[StandingView],
        row: StandingView | None,
    ) -> TeamZoneGaps:
        if row is None or row.points is None:
            return TeamZoneGaps()

        zone_config = self.zones.get(competition_code, CompetitionStandingsZones())
        rows_by_position = {item.position: item for item in standings}
        leader_row = rows_by_position.get(1)
        playoff_cutoff_position = max(zone_config.playoff_positions, default=0)
        playoff_cutoff = rows_by_position.get(playoff_cutoff_position) if playoff_cutoff_position else None
        playoff_outside = rows_by_position.get(playoff_cutoff_position + 1) if playoff_cutoff_position else None
        relegation_line = min(zone_config.relegation_positions, default=0)
        safe_row = rows_by_position.get(relegation_line - 1) if relegation_line else None
        relegation_row = rows_by_position.get(relegation_line) if relegation_line else None

        current_zone = self._zone_for_row(competition_code, row)
        return TeamZoneGaps(
            points_to_leader=(
                max((leader_row.points or 0) - row.points, 0)
                if leader_row is not None and leader_row.points is not None
                else None
            ),
            points_to_playoff=(
                max((playoff_cutoff.points or 0) - row.points, 0)
                if playoff_cutoff is not None
                and playoff_cutoff.points is not None
                and current_zone not in {"leader", "playoff"}
                else 0
                if current_zone in {"leader", "playoff"} and playoff_cutoff is not None
                else None
            ),
            margin_above_playoff=(
                row.points - (playoff_outside.points or 0)
                if playoff_outside is not None
                and playoff_outside.points is not None
                and current_zone in {"leader", "playoff"}
                else None
            ),
            points_to_safety=(
                max((safe_row.points or 0) - row.points, 0)
                if safe_row is not None
                and safe_row.points is not None
                and current_zone == "relegation"
                else 0
                if current_zone != "relegation" and safe_row is not None
                else None
            ),
            margin_above_relegation=(
                row.points - (relegation_row.points or 0)
                if relegation_row is not None
                and relegation_row.points is not None
                and current_zone != "relegation"
                else None
            ),
        )

    def _zone_transition(
        self,
        current_zone: ZoneTag | None,
        simulated_zone: ZoneTag | None,
    ) -> tuple[ZoneTag | None, ZoneTag | None]:
        if current_zone == simulated_zone:
            return None, None
        if simulated_zone == "leader":
            return "leader", "leader" if current_zone == "leader" else None
        if current_zone == "relegation" and simulated_zone != "relegation":
            return simulated_zone if simulated_zone in {"leader", "playoff"} else None, "relegation"
        if current_zone in {"safe", None} and simulated_zone == "playoff":
            return "playoff", None
        if current_zone in {"safe", "playoff", "leader", None} and simulated_zone == "relegation":
            return "relegation", None
        if current_zone in {"playoff", "leader"} and simulated_zone == "safe":
            return None, "playoff" if current_zone == "playoff" else "leader"
        if current_zone == "leader" and simulated_zone == "playoff":
            return "playoff", "leader"
        return simulated_zone, current_zone

    def _implication_text(
        self,
        *,
        result: ScenarioResult,
        current_position: int | None,
        simulated_position: int | None,
        current_zone: ZoneTag | None,
        simulated_zone: ZoneTag | None,
    ) -> str | None:
        subject = {
            "win": "Una victoria",
            "draw": "Un empate",
            "loss": "Una derrota",
        }[result]
        if current_zone != "leader" and simulated_zone == "leader":
            return f"{subject} lo llevaria al liderato"
        if current_zone not in {"leader", "playoff"} and simulated_zone in {"leader", "playoff"}:
            return f"{subject} lo meteria en playoff"
        if current_zone == "relegation" and simulated_zone != "relegation":
            return f"{subject} lo sacaria del descenso"
        if current_zone != "relegation" and simulated_zone == "relegation":
            return f"{subject} lo meteria en descenso"
        if (
            current_position is not None
            and simulated_position is not None
            and simulated_position < current_position
        ):
            return f"{subject} lo subiria al puesto {simulated_position}"
        if (
            current_position is not None
            and simulated_position is not None
            and simulated_position > current_position
        ):
            return f"{subject} lo bajaria al puesto {simulated_position}"
        return None

    def _zone_for_row(
        self,
        competition_code: str,
        row: StandingView | None,
    ) -> ZoneTag | None:
        if row is None:
            return None
        zone_config = self.zones.get(competition_code, CompetitionStandingsZones())
        if row.position == 1:
            return "leader"
        if row.position in zone_config.playoff_positions:
            return "playoff"
        if row.position in zone_config.relegation_positions:
            return "relegation"
        return "safe"

    def _zone_label(self, zone: ZoneTag | None) -> str | None:
        if zone is None:
            return None
        return _ZONE_LABELS[zone]
