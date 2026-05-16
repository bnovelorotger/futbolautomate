from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.core.standings_zones import CompetitionStandingsZones, load_standings_zones
from app.schemas.race_narrative import (
    RaceNarrativeCandidateView,
    RaceNarrativeConfig,
    RaceNarrativeResult,
    RaceNarrativeSeasonContext,
    RaceNarrativeTeamSnapshot,
    RaceNarrativeType,
)
from app.schemas.reporting import StandingView
from app.utils.hashing import stable_hash
from app.utils.time import utcnow

DEFAULT_ZONES = CompetitionStandingsZones(playoff_positions=[], relegation_positions=[])

_PRIORITY_BASE = {
    RaceNarrativeType.TITLE_RACE: 80,
    RaceNarrativeType.PLAYOFF_RACE: 77,
    RaceNarrativeType.RELEGATION_RACE: 76,
    RaceNarrativeType.ALIVE_MATHEMATICS: 72,
}


@dataclass(frozen=True, slots=True)
class _NormalizedStanding:
    team: str
    position: int
    points: int
    goal_difference: int | None
    played: int | None


class RaceNarrativeService:
    def __init__(
        self,
        *,
        config: RaceNarrativeConfig | None = None,
        zones_map: dict[str, CompetitionStandingsZones] | None = None,
    ) -> None:
        self.config = config or RaceNarrativeConfig()
        self.zones_map = zones_map or load_standings_zones()

    def preview_for_standings(
        self,
        competition_slug: str,
        standings: list[StandingView],
        *,
        competition_name: str | None = None,
        season_context: RaceNarrativeSeasonContext | None = None,
        reference_date: date | None = None,
        zones: CompetitionStandingsZones | None = None,
    ) -> RaceNarrativeResult:
        selected_date = reference_date or utcnow().date()
        selected_name = competition_name or competition_slug
        rows = self.build_rows(
            competition_slug,
            standings,
            competition_name=selected_name,
            season_context=season_context,
            zones=zones,
        )
        return RaceNarrativeResult(
            competition_slug=competition_slug,
            competition_name=selected_name,
            reference_date=selected_date,
            generated_at=utcnow(),
            rows=rows,
        )

    def build_rows(
        self,
        competition_slug: str,
        standings: list[StandingView],
        *,
        competition_name: str,
        season_context: RaceNarrativeSeasonContext | None = None,
        zones: CompetitionStandingsZones | None = None,
    ) -> list[RaceNarrativeCandidateView]:
        ordered = self._normalize_standings(standings)
        if not ordered:
            return []

        selected_zones = zones or self.zones_map.get(competition_slug, DEFAULT_ZONES)
        rounds_remaining = self._rounds_remaining(ordered, season_context)

        rows: list[RaceNarrativeCandidateView] = []
        title_row = self._title_race_row(
            competition_slug,
            competition_name,
            ordered,
            rounds_remaining=rounds_remaining,
        )
        if title_row is not None:
            rows.append(title_row)

        playoff_row = self._playoff_race_row(
            competition_slug,
            competition_name,
            ordered,
            selected_zones,
            rounds_remaining=rounds_remaining,
        )
        if playoff_row is not None:
            rows.append(playoff_row)

        relegation_row = self._relegation_race_row(
            competition_slug,
            competition_name,
            ordered,
            selected_zones,
            rounds_remaining=rounds_remaining,
        )
        if relegation_row is not None:
            rows.append(relegation_row)

        alive_row = self._alive_mathematics_row(
            competition_slug,
            competition_name,
            ordered,
            selected_zones,
            rounds_remaining=rounds_remaining,
        )
        if alive_row is not None:
            rows.append(alive_row)

        return sorted(rows, key=lambda row: (-row.priority, row.source_summary_hash))

    def _title_race_row(
        self,
        competition_slug: str,
        competition_name: str,
        standings: list[_NormalizedStanding],
        *,
        rounds_remaining: int | None,
    ) -> RaceNarrativeCandidateView | None:
        leader_points = standings[0].points
        contenders = [row for row in standings if leader_points - row.points <= self.config.title_max_gap_points]
        if len(contenders) < self.config.min_title_teams:
            return None

        points_span = contenders[0].points - contenders[-1].points
        title = self._race_title(RaceNarrativeType.TITLE_RACE, contenders)
        text = self._title_race_text(competition_name, contenders, points_span, rounds_remaining)
        target_label = "liderato"
        intensity = self._race_intensity(
            team_count=len(contenders),
            points_span=points_span,
            rounds_remaining=rounds_remaining,
            max_gap=self.config.title_max_gap_points,
        )
        return self._candidate_view(
            competition_slug,
            competition_name,
            narrative_type=RaceNarrativeType.TITLE_RACE,
            title=title,
            standings=contenders,
            target_label=target_label,
            target_position=1,
            rounds_remaining=rounds_remaining,
            points_span=points_span,
            intensity_score=intensity,
            text_draft=text,
        )

    def _playoff_race_row(
        self,
        competition_slug: str,
        competition_name: str,
        standings: list[_NormalizedStanding],
        zones: CompetitionStandingsZones,
        *,
        rounds_remaining: int | None,
    ) -> RaceNarrativeCandidateView | None:
        if not zones.playoff_positions:
            return None
        target_position = max(zones.playoff_positions)
        cutoff_row = self._row_for_position(standings, target_position)
        if cutoff_row is None:
            return None

        contenders = [row for row in standings if abs(row.points - cutoff_row.points) <= self.config.playoff_max_gap_points]
        inside_zone = [row for row in contenders if row.position in zones.playoff_positions]
        outside_zone = [row for row in contenders if row.position > target_position]
        if len(contenders) < self.config.min_playoff_teams or not inside_zone or not outside_zone:
            return None

        points_span = contenders[0].points - contenders[-1].points
        title = self._race_title(RaceNarrativeType.PLAYOFF_RACE, contenders)
        target_label = f"{self._ordinal(target_position)} plaza de playoff"
        text = self._cut_line_race_text(
            competition_name,
            contenders,
            points_span,
            rounds_remaining,
            target_label=target_label,
            cutoff_points=cutoff_row.points,
            context_phrase="pelean por la ultima plaza de playoff",
        )
        intensity = self._race_intensity(
            team_count=len(contenders),
            points_span=points_span,
            rounds_remaining=rounds_remaining,
            max_gap=self.config.playoff_max_gap_points,
        )
        return self._candidate_view(
            competition_slug,
            competition_name,
            narrative_type=RaceNarrativeType.PLAYOFF_RACE,
            title=title,
            standings=contenders,
            target_label=target_label,
            target_position=target_position,
            rounds_remaining=rounds_remaining,
            points_span=points_span,
            intensity_score=intensity,
            text_draft=text,
        )

    def _relegation_race_row(
        self,
        competition_slug: str,
        competition_name: str,
        standings: list[_NormalizedStanding],
        zones: CompetitionStandingsZones,
        *,
        rounds_remaining: int | None,
    ) -> RaceNarrativeCandidateView | None:
        if not zones.relegation_positions:
            return None
        safe_position = min(zones.relegation_positions) - 1
        if safe_position < 1:
            return None
        safe_row = self._row_for_position(standings, safe_position)
        if safe_row is None:
            return None

        contenders = [row for row in standings if abs(row.points - safe_row.points) <= self.config.relegation_max_gap_points]
        safe_teams = [row for row in contenders if row.position == safe_position]
        relegation_teams = [row for row in contenders if row.position in zones.relegation_positions]
        if len(contenders) < self.config.min_relegation_teams or not safe_teams or not relegation_teams:
            return None

        points_span = contenders[0].points - contenders[-1].points
        title = self._race_title(RaceNarrativeType.RELEGATION_RACE, contenders)
        target_label = f"{self._ordinal(safe_position)} plaza de salvacion"
        text = self._cut_line_race_text(
            competition_name,
            contenders,
            points_span,
            rounds_remaining,
            target_label=target_label,
            cutoff_points=safe_row.points,
            context_phrase="pelean por salir del descenso",
        )
        intensity = self._race_intensity(
            team_count=len(contenders),
            points_span=points_span,
            rounds_remaining=rounds_remaining,
            max_gap=self.config.relegation_max_gap_points,
        )
        return self._candidate_view(
            competition_slug,
            competition_name,
            narrative_type=RaceNarrativeType.RELEGATION_RACE,
            title=title,
            standings=contenders,
            target_label=target_label,
            target_position=safe_position,
            rounds_remaining=rounds_remaining,
            points_span=points_span,
            intensity_score=intensity,
            text_draft=text,
        )

    def _alive_mathematics_row(
        self,
        competition_slug: str,
        competition_name: str,
        standings: list[_NormalizedStanding],
        zones: CompetitionStandingsZones,
        *,
        rounds_remaining: int | None,
    ) -> RaceNarrativeCandidateView | None:
        if rounds_remaining is None:
            return None
        if rounds_remaining < self.config.alive_math_min_rounds_remaining:
            return None
        if (
            self.config.alive_math_max_rounds_remaining is not None
            and rounds_remaining > self.config.alive_math_max_rounds_remaining
        ):
            return None

        target_definitions: list[tuple[int, str]] = [(1, "liderato")]
        if zones.playoff_positions:
            playoff_target = max(zones.playoff_positions)
            target_definitions.append((playoff_target, f"{self._ordinal(playoff_target)} plaza de playoff"))
        if zones.relegation_positions:
            safe_position = min(zones.relegation_positions) - 1
            if safe_position >= 1:
                target_definitions.append((safe_position, f"{self._ordinal(safe_position)} plaza de salvacion"))

        best_row: RaceNarrativeCandidateView | None = None
        best_signature: tuple[int, int, int] | None = None
        for target_position, target_label in target_definitions:
            target_row = self._row_for_position(standings, target_position)
            if target_row is None:
                continue
            alive_rows = []
            for row in standings:
                max_points = self._max_points(row, rounds_remaining)
                if max_points is None or max_points < target_row.points:
                    continue
                alive_rows.append(row)
            if len(alive_rows) < self.config.alive_math_min_teams:
                continue
            if self.config.alive_math_max_teams is not None and len(alive_rows) > self.config.alive_math_max_teams:
                continue

            points_span = alive_rows[0].points - alive_rows[-1].points
            intensity = self._alive_math_intensity(
                team_count=len(alive_rows),
                points_span=points_span,
                rounds_remaining=rounds_remaining,
                target_position=target_position,
            )
            text = self._alive_math_text(
                competition_name,
                alive_rows,
                rounds_remaining,
                target_label=target_label,
            )
            candidate = self._candidate_view(
                competition_slug,
                competition_name,
                narrative_type=RaceNarrativeType.ALIVE_MATHEMATICS,
                title=f"Matematicas vivas por {target_label}",
                standings=alive_rows,
                target_label=target_label,
                target_position=target_position,
                rounds_remaining=rounds_remaining,
                points_span=points_span,
                intensity_score=intensity,
                text_draft=text,
            )
            signature = (intensity, -len(alive_rows), -target_position)
            if best_signature is None or signature > best_signature:
                best_signature = signature
                best_row = candidate
        return best_row

    def _candidate_view(
        self,
        competition_slug: str,
        competition_name: str,
        *,
        narrative_type: RaceNarrativeType,
        title: str,
        standings: list[_NormalizedStanding],
        target_label: str,
        target_position: int | None,
        rounds_remaining: int | None,
        points_span: int,
        intensity_score: int,
        text_draft: str,
    ) -> RaceNarrativeCandidateView:
        target_points = standings[0].points if target_position == 1 else None
        if target_position is not None:
            target_row = self._row_for_position(standings, target_position)
            if target_row is not None:
                target_points = target_row.points
        team_snapshots = [
            self._snapshot(row, target_points=target_points, rounds_remaining=rounds_remaining)
            for row in standings
        ]
        source_payload = {
            "narrative_type": str(narrative_type),
            "target_label": target_label,
            "target_position": target_position,
            "target_points": target_points,
            "team_count": len(team_snapshots),
            "points_span": points_span,
            "rounds_remaining": rounds_remaining,
            "teams": [snapshot.model_dump(mode="python") for snapshot in team_snapshots],
        }
        content_key = (
            f"race_narrative:{narrative_type}:{competition_slug}:{target_position or 0}:"
            f"{'-'.join(snapshot.team for snapshot in team_snapshots)}"
        )
        source_summary_hash = stable_hash(
            {
                "competition_slug": competition_slug,
                "content_key": content_key,
                "source_payload": source_payload,
            }
        )
        priority = min(95, _PRIORITY_BASE[narrative_type] + intensity_score // 10)
        return RaceNarrativeCandidateView(
            competition_slug=competition_slug,
            competition_name=competition_name,
            narrative_type=narrative_type,
            title=title,
            priority=priority,
            intensity_score=intensity_score,
            teams=team_snapshots,
            team_count=len(team_snapshots),
            points_span=points_span,
            target_position=target_position,
            target_label=target_label,
            rounds_remaining=rounds_remaining,
            excerpt=self._excerpt(text_draft),
            text_draft=text_draft,
            content_key=content_key,
            template_name=f"race_narrative_{narrative_type}_v1",
            source_payload=source_payload,
            source_summary_hash=source_summary_hash,
        )

    def _normalize_standings(self, standings: list[StandingView]) -> list[_NormalizedStanding]:
        rows = [
            _NormalizedStanding(
                team=row.team,
                position=row.position,
                points=int(row.points or 0),
                goal_difference=row.goal_difference,
                played=row.played,
            )
            for row in standings
        ]
        return sorted(rows, key=lambda row: (row.position, -row.points, row.team))

    def _rounds_remaining(
        self,
        standings: list[_NormalizedStanding],
        season_context: RaceNarrativeSeasonContext | None,
    ) -> int | None:
        if season_context is None:
            return None
        if season_context.rounds_remaining is not None:
            return max(season_context.rounds_remaining, 0)
        if season_context.total_matchdays is None:
            return None
        played_values = [row.played for row in standings if row.played is not None]
        if not played_values:
            return None
        return max(season_context.total_matchdays - max(played_values), 0)

    def _row_for_position(
        self,
        standings: list[_NormalizedStanding],
        position: int,
    ) -> _NormalizedStanding | None:
        return next((row for row in standings if row.position == position), None)

    def _snapshot(
        self,
        row: _NormalizedStanding,
        *,
        target_points: int | None,
        rounds_remaining: int | None,
    ) -> RaceNarrativeTeamSnapshot:
        max_points = self._max_points(row, rounds_remaining)
        gap_to_target = None if target_points is None else target_points - row.points
        return RaceNarrativeTeamSnapshot(
            team=row.team,
            position=row.position,
            points=row.points,
            goal_difference=row.goal_difference,
            played=row.played,
            matches_remaining=rounds_remaining,
            max_points=max_points,
            gap_to_target=gap_to_target,
        )

    def _max_points(self, row: _NormalizedStanding, rounds_remaining: int | None) -> int | None:
        if rounds_remaining is None:
            return None
        if row.played is None:
            return row.points + rounds_remaining * 3
        return row.points + rounds_remaining * 3

    def _race_intensity(
        self,
        *,
        team_count: int,
        points_span: int,
        rounds_remaining: int | None,
        max_gap: int,
    ) -> int:
        closeness = max(0, max_gap - points_span)
        rounds_bonus = 0 if rounds_remaining is None else min(rounds_remaining, 6)
        return 48 + team_count * 6 + closeness * 7 + rounds_bonus

    def _alive_math_intensity(
        self,
        *,
        team_count: int,
        points_span: int,
        rounds_remaining: int,
        target_position: int,
    ) -> int:
        count_tension = max(0, 8 - team_count) * 4
        position_bonus = max(0, 6 - target_position)
        return 44 + count_tension + min(rounds_remaining, 6) * 3 + position_bonus - points_span

    def _race_title(
        self,
        narrative_type: RaceNarrativeType,
        contenders: list[_NormalizedStanding],
    ) -> str:
        label = {
            RaceNarrativeType.TITLE_RACE: "Carrera por el liderato",
            RaceNarrativeType.PLAYOFF_RACE: "Carrera por el playoff",
            RaceNarrativeType.RELEGATION_RACE: "Pelea por la permanencia",
            RaceNarrativeType.ALIVE_MATHEMATICS: "Matematicas vivas",
        }[narrative_type]
        teams = ", ".join(row.team for row in contenders[:3])
        if len(contenders) > 3:
            teams = f"{teams} y mas"
        return f"{label}: {teams}"

    def _title_race_text(
        self,
        competition_name: str,
        contenders: list[_NormalizedStanding],
        points_span: int,
        rounds_remaining: int | None,
    ) -> str:
        if len(contenders) == 2 and points_span == 0:
            opening = (
                f"Solo la diferencia de goles separa a {contenders[0].team} y {contenders[1].team} "
                f"en la pelea por el liderato de {competition_name}."
            )
        elif len(contenders) == 2:
            opening = (
                f"{contenders[0].team} y {contenders[1].team} estan separados por "
                f"{self._points_text(points_span)} en la pelea por el liderato de {competition_name}."
            )
        else:
            opening = (
                f"{len(contenders)} equipos separados por {self._points_text(points_span)} "
                f"pelean por el liderato de {competition_name}."
            )
        return self._append_rounds(opening, rounds_remaining)

    def _cut_line_race_text(
        self,
        competition_name: str,
        contenders: list[_NormalizedStanding],
        points_span: int,
        rounds_remaining: int | None,
        *,
        target_label: str,
        cutoff_points: int,
        context_phrase: str,
    ) -> str:
        opening = (
            f"{len(contenders)} equipos separados por {self._points_text(points_span)} "
            f"{context_phrase} en {competition_name}."
        )
        detail = f"El corte ahora mismo esta en la {target_label} con {cutoff_points} puntos."
        return self._append_rounds(f"{opening} {detail}", rounds_remaining)

    def _alive_math_text(
        self,
        competition_name: str,
        contenders: list[_NormalizedStanding],
        rounds_remaining: int,
        *,
        target_label: str,
    ) -> str:
        opening = (
            f"{len(contenders)} equipos mantienen opciones matematicas de alcanzar {self._target_phrase(target_label)} "
            f"en {competition_name}."
        )
        return self._append_rounds(opening, rounds_remaining)

    def _append_rounds(self, text: str, rounds_remaining: int | None) -> str:
        if rounds_remaining is None:
            return text
        return f"{text} Quedan {rounds_remaining} jornadas."

    def _points_text(self, points_span: int) -> str:
        return f"{points_span} punto" if points_span == 1 else f"{points_span} puntos"

    def _ordinal(self, position: int) -> str:
        return f"{position}a"

    def _target_phrase(self, target_label: str) -> str:
        if target_label == "liderato":
            return "el liderato"
        return f"la {target_label}"

    def _excerpt(self, text: str, limit: int = 110) -> str:
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."
