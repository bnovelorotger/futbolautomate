from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.enums import StrEnum
from app.core.exceptions import ConfigurationError
from app.db.models import Competition
from app.schemas.reporting import CompetitionMatchView, StandingView
from app.services.competition_queries import CompetitionQueryService
from app.utils.time import utcnow


class MilestoneType(StrEnum):
    LONGEST_WINLESS_STREAK = "longest_winless_streak"
    LONGEST_CLEAN_SHEET_STREAK = "longest_clean_sheet_streak"
    TOP_SCORING_TEAM = "top_scoring_team"
    FIRST_HOME_DEFEAT = "first_home_defeat"
    FIRST_SCORELESS_MATCH = "first_scoreless_match"
    ROUND_BIGGEST_WIN = "round_biggest_win"
    ROUND_GOALS_RECORD = "round_goals_record"


class MilestoneDetectorConfig(BaseModel):
    min_winless_streak: int = 5
    min_clean_sheet_streak: int = 3
    min_top_scoring_goals: int = 25
    min_top_scoring_margin: int = 2
    min_home_unbeaten_before_loss: int = 4
    min_scoring_run_before_blank: int = 5
    min_biggest_win_margin: int = 4
    min_round_total_goals: int = 8


class MilestoneStory(BaseModel):
    content_key: str
    milestone_type: MilestoneType
    priority: int
    title: str
    summary: str
    teams: list[str] = Field(default_factory=list)
    metric_value: float | int | None = None
    round_name: str | None = None
    match_date: date | None = None
    source_payload: dict[str, Any] = Field(default_factory=dict)


class MilestoneDetectionResult(BaseModel):
    competition_slug: str
    competition_name: str
    reference_date: date
    generated_at: datetime
    rows: list[MilestoneStory] = Field(default_factory=list)


@dataclass(slots=True)
class TeamMatchEntry:
    team: str
    opponent: str
    venue: str
    goals_for: int
    goals_against: int
    match_date: date | None
    match_time: time | None
    round_name: str | None
    source_url: str


_MILESTONE_PRIORITY = {
    MilestoneType.FIRST_HOME_DEFEAT: 82,
    MilestoneType.FIRST_SCORELESS_MATCH: 79,
    MilestoneType.LONGEST_WINLESS_STREAK: 76,
    MilestoneType.ROUND_BIGGEST_WIN: 74,
    MilestoneType.ROUND_GOALS_RECORD: 73,
    MilestoneType.LONGEST_CLEAN_SHEET_STREAK: 72,
    MilestoneType.TOP_SCORING_TEAM: 68,
}


def _match_order_key(match: CompetitionMatchView) -> tuple[date, time, str]:
    return (
        match.match_date or date.min,
        match.match_time or time.min,
        match.source_url,
    )


def _entry_order_key(entry: TeamMatchEntry) -> tuple[date, time, str]:
    return (
        entry.match_date or date.min,
        entry.match_time or time.min,
        entry.source_url,
    )


def _match_points(entry: TeamMatchEntry) -> int:
    if entry.goals_for > entry.goals_against:
        return 3
    if entry.goals_for == entry.goals_against:
        return 1
    return 0


class MilestoneDetectorService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        config: MilestoneDetectorConfig | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.config = config or MilestoneDetectorConfig()
        self.queries = CompetitionQueryService(session, timezone_name=self.settings.timezone)
        self.catalog = load_competition_catalog()

    def preview_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> MilestoneDetectionResult:
        competition = self._competition(competition_code)
        selected_date = self._reference_date(reference_date)
        competition_name = self._competition_name(competition)
        return MilestoneDetectionResult(
            competition_slug=competition_code,
            competition_name=competition_name,
            reference_date=selected_date,
            generated_at=utcnow(),
            rows=self.build_milestones(competition_code, reference_date=selected_date),
        )

    def build_milestones(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> list[MilestoneStory]:
        self._competition(competition_code)
        matches = self.queries.finished_matches(
            competition_code,
            limit=None,
            reference_date=reference_date,
        )
        if not matches:
            return []

        histories = self._team_histories(matches)
        latest_round_matches = self._latest_round_matches(matches)
        standings = self._standings(competition_code)

        rows = [
            self._detect_winless_streak(histories),
            self._detect_clean_sheet_streak(histories),
            self._detect_top_scoring_team(standings),
            self._detect_first_home_defeat(histories, latest_round_matches),
            self._detect_first_scoreless_match(histories, latest_round_matches),
            self._detect_round_biggest_win(latest_round_matches),
            self._detect_round_goals_record(latest_round_matches),
        ]
        return sorted(
            [row for row in rows if row is not None],
            key=lambda row: (-row.priority, row.content_key),
        )

    def _competition(self, competition_code: str) -> Competition:
        competition = self.session.scalar(select(Competition).where(Competition.code == competition_code))
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_code}")
        return competition

    def _competition_name(self, competition: Competition) -> str:
        catalog_entry = self.catalog.get(competition.code)
        if catalog_entry is not None and catalog_entry.editorial_name:
            return catalog_entry.editorial_name
        return competition.name

    def _reference_date(self, reference_date: date | None) -> date:
        if reference_date is not None:
            return reference_date
        return datetime.now(ZoneInfo(self.settings.timezone)).date()

    def _standings(self, competition_code: str) -> list[StandingView]:
        try:
            return self.queries.current_standings(competition_code)
        except ConfigurationError:
            return []

    def _team_histories(self, matches: list[CompetitionMatchView]) -> dict[str, list[TeamMatchEntry]]:
        histories: dict[str, list[TeamMatchEntry]] = defaultdict(list)
        for match in sorted(matches, key=_match_order_key):
            if match.home_score is None or match.away_score is None:
                continue
            histories[match.home_team].append(
                TeamMatchEntry(
                    team=match.home_team,
                    opponent=match.away_team,
                    venue="home",
                    goals_for=int(match.home_score),
                    goals_against=int(match.away_score),
                    match_date=match.match_date,
                    match_time=match.match_time,
                    round_name=match.round_name,
                    source_url=match.source_url,
                )
            )
            histories[match.away_team].append(
                TeamMatchEntry(
                    team=match.away_team,
                    opponent=match.home_team,
                    venue="away",
                    goals_for=int(match.away_score),
                    goals_against=int(match.home_score),
                    match_date=match.match_date,
                    match_time=match.match_time,
                    round_name=match.round_name,
                    source_url=match.source_url,
                )
            )
        return histories

    def _latest_round_matches(self, matches: list[CompetitionMatchView]) -> list[CompetitionMatchView]:
        ordered = sorted(matches, key=_match_order_key)
        if not ordered:
            return []
        anchor = ordered[-1]
        if anchor.round_name:
            selected = [match for match in ordered if match.round_name == anchor.round_name]
        elif anchor.match_date is not None:
            selected = [match for match in ordered if match.match_date == anchor.match_date]
        else:
            selected = [anchor]
        return selected

    def _find_entry_index(self, entries: list[TeamMatchEntry], source_url: str) -> int | None:
        for index, entry in enumerate(entries):
            if entry.source_url == source_url:
                return index
        return None

    def _story(
        self,
        *,
        milestone_type: MilestoneType,
        content_key: str,
        title: str,
        summary: str,
        teams: list[str],
        metric_value: float | int | None = None,
        round_name: str | None = None,
        match_date: date | None = None,
        source_payload: dict[str, Any] | None = None,
    ) -> MilestoneStory:
        payload = source_payload or {}
        return MilestoneStory(
            content_key=content_key,
            milestone_type=milestone_type,
            priority=_MILESTONE_PRIORITY[milestone_type],
            title=title,
            summary=summary,
            teams=teams,
            metric_value=metric_value,
            round_name=round_name,
            match_date=match_date,
            source_payload={
                "milestone_type": str(milestone_type),
                "title": title,
                "teams": teams,
                "metric_value": metric_value,
                **payload,
            },
        )

    def _detect_winless_streak(self, histories: dict[str, list[TeamMatchEntry]]) -> MilestoneStory | None:
        best_story: MilestoneStory | None = None
        best_rank: tuple[int, date, str] | None = None
        for team, entries in histories.items():
            best_segment: list[TeamMatchEntry] = []
            current_segment: list[TeamMatchEntry] = []
            for entry in entries:
                if _match_points(entry) == 3:
                    if len(current_segment) > len(best_segment):
                        best_segment = current_segment.copy()
                    current_segment = []
                    continue
                current_segment.append(entry)
            if len(current_segment) > len(best_segment):
                best_segment = current_segment.copy()
            if len(best_segment) < self.config.min_winless_streak:
                continue

            draws = sum(1 for entry in best_segment if _match_points(entry) == 1)
            losses = len(best_segment) - draws
            end_entry = best_segment[-1]
            story = self._story(
                milestone_type=MilestoneType.LONGEST_WINLESS_STREAK,
                content_key=f"longest_winless_streak:{team}:{len(best_segment)}:{end_entry.source_url}",
                title=f"{team} enlaza {len(best_segment)} partidos sin ganar",
                summary=f"{team} acumula {draws} empates y {losses} derrotas en su peor racha sin victoria del curso.",
                teams=[team],
                metric_value=len(best_segment),
                round_name=end_entry.round_name,
                match_date=end_entry.match_date,
                source_payload={
                    "team": team,
                    "streak_length": len(best_segment),
                    "draws": draws,
                    "losses": losses,
                    "is_active": entries[-1].source_url == end_entry.source_url,
                    "start_date": best_segment[0].match_date.isoformat() if best_segment[0].match_date else None,
                    "end_date": end_entry.match_date.isoformat() if end_entry.match_date else None,
                },
            )
            rank = (len(best_segment), end_entry.match_date or date.min, team)
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_story = story
        return best_story

    def _detect_clean_sheet_streak(self, histories: dict[str, list[TeamMatchEntry]]) -> MilestoneStory | None:
        best_story: MilestoneStory | None = None
        best_rank: tuple[int, date, str] | None = None
        for team, entries in histories.items():
            best_segment: list[TeamMatchEntry] = []
            current_segment: list[TeamMatchEntry] = []
            for entry in entries:
                if entry.goals_against == 0:
                    current_segment.append(entry)
                    continue
                if len(current_segment) > len(best_segment):
                    best_segment = current_segment.copy()
                current_segment = []
            if len(current_segment) > len(best_segment):
                best_segment = current_segment.copy()
            if len(best_segment) < self.config.min_clean_sheet_streak:
                continue

            end_entry = best_segment[-1]
            goals_for = sum(entry.goals_for for entry in best_segment)
            story = self._story(
                milestone_type=MilestoneType.LONGEST_CLEAN_SHEET_STREAK,
                content_key=f"longest_clean_sheet_streak:{team}:{len(best_segment)}:{end_entry.source_url}",
                title=f"{team} firma {len(best_segment)} porterias a cero seguidas",
                summary=f"{team} sostiene una racha defensiva de {len(best_segment)} partidos sin encajar y {goals_for} goles a favor en ese tramo.",
                teams=[team],
                metric_value=len(best_segment),
                round_name=end_entry.round_name,
                match_date=end_entry.match_date,
                source_payload={
                    "team": team,
                    "streak_length": len(best_segment),
                    "goals_for_during_streak": goals_for,
                    "is_active": entries[-1].source_url == end_entry.source_url,
                    "start_date": best_segment[0].match_date.isoformat() if best_segment[0].match_date else None,
                    "end_date": end_entry.match_date.isoformat() if end_entry.match_date else None,
                },
            )
            rank = (len(best_segment), end_entry.match_date or date.min, team)
            if best_rank is None or rank > best_rank:
                best_rank = rank
                best_story = story
        return best_story

    def _detect_top_scoring_team(self, standings: list[StandingView]) -> MilestoneStory | None:
        valid = [row for row in standings if row.goals_for is not None]
        if not valid:
            return None
        ordered = sorted(valid, key=lambda row: (-int(row.goals_for or 0), row.position, row.team))
        leader = ordered[0]
        runner_up_goals = int(ordered[1].goals_for or 0) if len(ordered) > 1 else 0
        leader_goals = int(leader.goals_for or 0)
        margin = leader_goals - runner_up_goals
        if leader_goals < self.config.min_top_scoring_goals:
            return None
        if len(ordered) > 1 and margin < self.config.min_top_scoring_margin:
            return None
        return self._story(
            milestone_type=MilestoneType.TOP_SCORING_TEAM,
            content_key=f"top_scoring_team:{leader.team}:{leader_goals}",
            title=f"{leader.team} lidera el gol con {leader_goals} tantos",
            summary=f"{leader.team} manda en produccion ofensiva con {leader_goals} goles y {margin} de ventaja sobre el siguiente registro.",
            teams=[leader.team],
            metric_value=leader_goals,
            source_payload={
                "team": leader.team,
                "goals_for": leader_goals,
                "leader_margin": margin,
                "position": leader.position,
            },
        )

    def _detect_first_home_defeat(
        self,
        histories: dict[str, list[TeamMatchEntry]],
        latest_round_matches: list[CompetitionMatchView],
    ) -> MilestoneStory | None:
        candidates: list[tuple[int, date, str, MilestoneStory]] = []
        for match in latest_round_matches:
            if match.home_score is None or match.away_score is None or match.home_score >= match.away_score:
                continue
            home_entries = sorted(
                [entry for entry in histories.get(match.home_team, []) if entry.venue == "home"],
                key=_entry_order_key,
            )
            index = self._find_entry_index(home_entries, match.source_url)
            if index is None or index == 0:
                continue
            previous_entries = home_entries[:index]
            if len(previous_entries) < self.config.min_home_unbeaten_before_loss:
                continue
            if any(entry.goals_for < entry.goals_against for entry in previous_entries):
                continue
            unbeaten_before_loss = len(previous_entries)
            candidates.append(
                (
                    unbeaten_before_loss,
                    match.match_date or date.min,
                    match.home_team,
                    self._story(
                        milestone_type=MilestoneType.FIRST_HOME_DEFEAT,
                        content_key=f"first_home_defeat:{match.home_team}:{match.source_url}",
                        title=f"{match.home_team} cae en casa por primera vez",
                        summary=f"{match.away_team} rompe una racha de {unbeaten_before_loss} partidos como local sin perder para {match.home_team}.",
                        teams=[match.home_team, match.away_team],
                        metric_value=unbeaten_before_loss,
                        round_name=match.round_name,
                        match_date=match.match_date,
                        source_payload={
                            "team": match.home_team,
                            "opponent": match.away_team,
                            "home_unbeaten_before_loss": unbeaten_before_loss,
                            "scoreline": f"{match.home_score}-{match.away_score}",
                            "source_url": match.source_url,
                        },
                    ),
                )
            )
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][3]

    def _detect_first_scoreless_match(
        self,
        histories: dict[str, list[TeamMatchEntry]],
        latest_round_matches: list[CompetitionMatchView],
    ) -> MilestoneStory | None:
        candidates: list[tuple[int, date, str, MilestoneStory]] = []
        latest_entries: list[TeamMatchEntry] = []
        for match in latest_round_matches:
            if match.home_score is None or match.away_score is None:
                continue
            latest_entries.append(
                TeamMatchEntry(
                    team=match.home_team,
                    opponent=match.away_team,
                    venue="home",
                    goals_for=int(match.home_score),
                    goals_against=int(match.away_score),
                    match_date=match.match_date,
                    match_time=match.match_time,
                    round_name=match.round_name,
                    source_url=match.source_url,
                )
            )
            latest_entries.append(
                TeamMatchEntry(
                    team=match.away_team,
                    opponent=match.home_team,
                    venue="away",
                    goals_for=int(match.away_score),
                    goals_against=int(match.home_score),
                    match_date=match.match_date,
                    match_time=match.match_time,
                    round_name=match.round_name,
                    source_url=match.source_url,
                )
            )

        for latest_entry in latest_entries:
            if latest_entry.goals_for != 0:
                continue
            team_entries = sorted(histories.get(latest_entry.team, []), key=_entry_order_key)
            index = self._find_entry_index(team_entries, latest_entry.source_url)
            if index is None or index == 0:
                continue
            scoring_run = 0
            for prior in reversed(team_entries[:index]):
                if prior.goals_for <= 0:
                    break
                scoring_run += 1
            if scoring_run < self.config.min_scoring_run_before_blank:
                continue
            candidates.append(
                (
                    scoring_run,
                    latest_entry.match_date or date.min,
                    latest_entry.team,
                    self._story(
                        milestone_type=MilestoneType.FIRST_SCORELESS_MATCH,
                        content_key=f"first_scoreless_match:{latest_entry.team}:{latest_entry.source_url}",
                        title=f"{latest_entry.team} se queda sin marcar tras {scoring_run} jornadas",
                        summary=f"{latest_entry.team} rompe una secuencia de {scoring_run} partidos viendo puerta al quedarse a cero ante {latest_entry.opponent}.",
                        teams=[latest_entry.team, latest_entry.opponent],
                        metric_value=scoring_run,
                        round_name=latest_entry.round_name,
                        match_date=latest_entry.match_date,
                        source_payload={
                            "team": latest_entry.team,
                            "opponent": latest_entry.opponent,
                            "scoring_run_matches": scoring_run,
                            "venue": latest_entry.venue,
                            "scoreline": (
                                f"{latest_entry.goals_for}-{latest_entry.goals_against}"
                                if latest_entry.venue == "home"
                                else f"{latest_entry.goals_against}-{latest_entry.goals_for}"
                            ),
                            "source_url": latest_entry.source_url,
                        },
                    ),
                )
            )
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0][3]

    def _detect_round_biggest_win(self, latest_round_matches: list[CompetitionMatchView]) -> MilestoneStory | None:
        valid = [match for match in latest_round_matches if match.home_score is not None and match.away_score is not None]
        if not valid:
            return None
        ordered = sorted(
            valid,
            key=lambda match: (
                abs(int(match.home_score or 0) - int(match.away_score or 0)),
                int(match.home_score or 0) + int(match.away_score or 0),
                match.home_team,
                match.away_team,
            ),
            reverse=True,
        )
        best = ordered[0]
        margin = abs(int(best.home_score or 0) - int(best.away_score or 0))
        if margin < self.config.min_biggest_win_margin or int(best.home_score or 0) == int(best.away_score or 0):
            return None
        winner = best.home_team if int(best.home_score or 0) > int(best.away_score or 0) else best.away_team
        loser = best.away_team if winner == best.home_team else best.home_team
        return self._story(
            milestone_type=MilestoneType.ROUND_BIGGEST_WIN,
            content_key=f"round_biggest_win:{winner}:{best.source_url}",
            title=f"Mayor goleada de la jornada: {winner} firma un +{margin}",
            summary=f"{winner} supera a {loser} por {best.home_score}-{best.away_score} en el marcador mas amplio de la jornada.",
            teams=[winner, loser],
            metric_value=margin,
            round_name=best.round_name,
            match_date=best.match_date,
            source_payload={
                "winner": winner,
                "loser": loser,
                "scoreline": f"{best.home_score}-{best.away_score}",
                "goal_margin": margin,
                "source_url": best.source_url,
            },
        )

    def _detect_round_goals_record(self, latest_round_matches: list[CompetitionMatchView]) -> MilestoneStory | None:
        valid = [match for match in latest_round_matches if match.home_score is not None and match.away_score is not None]
        if not valid:
            return None
        total_goals = sum(int(match.home_score or 0) + int(match.away_score or 0) for match in valid)
        if total_goals < self.config.min_round_total_goals:
            return None
        unique_teams = sorted({team for match in valid for team in (match.home_team, match.away_team)})
        anchor = valid[-1]
        return self._story(
            milestone_type=MilestoneType.ROUND_GOALS_RECORD,
            content_key=f"round_goals_record:{anchor.round_name or anchor.match_date}:{total_goals}",
            title=f"La jornada deja {total_goals} goles en total",
            summary=f"La ronda cierra con {total_goals} goles en {len(valid)} partidos, una carga ofensiva claramente por encima del umbral editorial.",
            teams=unique_teams,
            metric_value=total_goals,
            round_name=anchor.round_name,
            match_date=anchor.match_date,
            source_payload={
                "total_goals": total_goals,
                "match_count": len(valid),
                "average_goals_per_match": round(total_goals / len(valid), 2),
            },
        )
