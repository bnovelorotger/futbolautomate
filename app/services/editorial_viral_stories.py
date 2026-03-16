from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import get_settings
from app.core.enums import ContentCandidateStatus, ContentType, ViralStoryType
from app.core.exceptions import ConfigurationError
from app.db.models import Competition, Match
from app.db.repositories.content_candidates import ContentCandidateRepository
from app.schemas.common import IngestStats
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.editorial_viral_stories import (
    EditorialViralStoriesGenerationResult,
    EditorialViralStoriesResult,
    EditorialViralStoryCandidateView,
)
from app.schemas.reporting import CompetitionMatchView, StandingView
from app.services.competition_queries import CompetitionQueryService
from app.utils.hashing import stable_hash
from app.utils.time import utcnow

_VIRAL_PRIORITY = {
    ViralStoryType.WIN_STREAK: 76,
    ViralStoryType.UNBEATEN_STREAK: 75,
    ViralStoryType.LOSING_STREAK: 74,
    ViralStoryType.HOT_FORM: 73,
    ViralStoryType.RECENT_TOP_SCORER: 72,
    ViralStoryType.COLD_FORM: 71,
    ViralStoryType.BEST_ATTACK: 70,
    ViralStoryType.BEST_DEFENSE: 69,
    ViralStoryType.GOALS_TREND: 68,
}

_MIN_WIN_STREAK = 3
_MIN_UNBEATEN_STREAK = 4
_MIN_LOSING_STREAK = 3
_MIN_FORM_MATCHES = 4
_FORM_WINDOW = 5
_MIN_HOT_FORM_POINTS = 10
_MIN_COLD_FORM_POINTS = 3
_MIN_COLD_FORM_LOSSES = 3
_RECENT_SCORING_WINDOW = 3
_MIN_RECENT_SCORING_GOALS = 5
_MIN_RECENT_SCORING_MARGIN = 2
_MIN_ATTACK_MARGIN = 2
_MIN_DEFENSE_MARGIN = 2
_TREND_WINDOW = 5
_MIN_TREND_MATCHES = 4
_MIN_SEASON_MATCHES_FOR_TREND = 6
_MIN_GOALS_TREND_DELTA = 0.6

VIRAL_STORY_THRESHOLDS = {
    ViralStoryType.WIN_STREAK: _MIN_WIN_STREAK,
    ViralStoryType.UNBEATEN_STREAK: _MIN_UNBEATEN_STREAK,
    ViralStoryType.LOSING_STREAK: _MIN_LOSING_STREAK,
    ViralStoryType.RECENT_TOP_SCORER: {
        "min_goals": _MIN_RECENT_SCORING_GOALS,
        "min_margin": _MIN_RECENT_SCORING_MARGIN,
    },
    ViralStoryType.HOT_FORM: {"min_points": _MIN_HOT_FORM_POINTS},
    ViralStoryType.COLD_FORM: {
        "max_points": _MIN_COLD_FORM_POINTS,
        "min_losses": _MIN_COLD_FORM_LOSSES,
    },
    ViralStoryType.BEST_ATTACK: {"min_margin": _MIN_ATTACK_MARGIN},
    ViralStoryType.BEST_DEFENSE: {"min_margin": _MIN_DEFENSE_MARGIN},
    ViralStoryType.GOALS_TREND: {
        "min_matches": _MIN_TREND_MATCHES,
        "min_delta": _MIN_GOALS_TREND_DELTA,
    },
}


def _excerpt(text: str, limit: int = 110) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _format_metric_value(value: float | int) -> str:
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _candidate_hash(
    competition_slug: str,
    content_key: str,
    source_payload: dict[str, Any],
) -> str:
    return stable_hash(
        {
            "competition_slug": competition_slug,
            "content_type": str(ContentType.VIRAL_STORY),
            "content_key": content_key,
            "source_payload": source_payload,
        }
    )


def _team_result(team_name: str, match: CompetitionMatchView) -> str:
    if match.home_score is None or match.away_score is None:
        raise ValueError("No se puede calcular una historia viral con un partido sin marcador final")
    if team_name == match.home_team:
        if match.home_score > match.away_score:
            return "W"
        if match.home_score == match.away_score:
            return "D"
        return "L"
    if team_name == match.away_team:
        if match.away_score > match.home_score:
            return "W"
        if match.home_score == match.away_score:
            return "D"
        return "L"
    raise ValueError(f"El equipo {team_name} no participa en el partido {match.source_url}")


class EditorialViralStoriesService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ContentCandidateRepository(session)
        self.queries = CompetitionQueryService(session)
        self.competition_catalog = load_competition_catalog()
        self.timezone_name = get_settings().timezone

    def preview_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> EditorialViralStoriesResult:
        competition = self._competition(competition_code)
        selected_date = self._reference_date(reference_date)
        candidates = self.build_candidate_drafts(competition_code, reference_date=selected_date)
        competition_name = self._competition_name(competition)
        return EditorialViralStoriesResult(
            competition_slug=competition_code,
            competition_name=competition_name,
            reference_date=selected_date,
            generated_at=utcnow(),
            rows=[self._candidate_to_view(competition_name, candidate) for candidate in candidates],
        )

    def generate_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> EditorialViralStoriesGenerationResult:
        preview = self.preview_for_competition(competition_code, reference_date=reference_date)
        candidates = self.build_candidate_drafts(competition_code, reference_date=preview.reference_date)
        stats = self.store_candidates(candidates)
        return EditorialViralStoriesGenerationResult(
            competition_slug=preview.competition_slug,
            competition_name=preview.competition_name,
            reference_date=preview.reference_date,
            generated_at=preview.generated_at,
            rows=preview.rows,
            stats=stats,
        )

    def build_candidate_drafts(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> list[ContentCandidateDraft]:
        competition = self._competition(competition_code)
        selected_date = self._reference_date(reference_date)
        competition_name = self._competition_name(competition)
        finished_matches = self.queries.finished_matches(
            competition_code,
            limit=None,
            reference_date=selected_date,
        )
        team_sequences = self._team_sequences(finished_matches)
        candidates: list[ContentCandidateDraft] = []

        win_story = self._build_win_streak_story(competition_code, competition_name, selected_date, team_sequences)
        if win_story is not None:
            candidates.append(win_story)

        unbeaten_story = self._build_unbeaten_story(
            competition_code,
            competition_name,
            selected_date,
            team_sequences,
            existing_team=win_story.payload_json["source_payload"].get("teams", [None])[0] if win_story else None,
        )
        if unbeaten_story is not None:
            candidates.append(unbeaten_story)

        losing_story = self._build_losing_story(competition_code, competition_name, selected_date, team_sequences)
        if losing_story is not None:
            candidates.append(losing_story)

        hot_form_story = self._build_hot_form_story(competition_code, competition_name, selected_date, team_sequences)
        if hot_form_story is not None:
            candidates.append(hot_form_story)

        cold_form_story = self._build_cold_form_story(competition_code, competition_name, selected_date, team_sequences)
        if cold_form_story is not None:
            candidates.append(cold_form_story)

        recent_scoring_story = self._build_recent_scoring_story(
            competition_code,
            competition_name,
            selected_date,
            team_sequences,
        )
        if recent_scoring_story is not None:
            candidates.append(recent_scoring_story)

        try:
            standings = self.queries.current_standings(competition_code)
        except ConfigurationError:
            standings = []

        best_attack_story = self._build_best_attack_story(
            competition_code,
            competition_name,
            selected_date,
            standings,
        )
        if best_attack_story is not None:
            candidates.append(best_attack_story)

        best_defense_story = self._build_best_defense_story(
            competition_code,
            competition_name,
            selected_date,
            standings,
        )
        if best_defense_story is not None:
            candidates.append(best_defense_story)

        goals_trend_story = self._build_goals_trend_story(
            competition.id,
            competition_code,
            competition_name,
            selected_date,
        )
        if goals_trend_story is not None:
            candidates.append(goals_trend_story)

        return sorted(candidates, key=lambda item: (-item.priority, item.source_summary_hash))

    def store_candidates(self, candidates: list[ContentCandidateDraft]) -> IngestStats:
        stats = IngestStats(found=len(candidates))
        for candidate in candidates:
            _, inserted, updated = self.repository.upsert(candidate.model_dump(mode="python"))
            stats.inserted += int(inserted)
            stats.updated += int(updated)
        return stats

    def _competition(self, competition_code: str) -> Competition:
        competition = self.session.scalar(select(Competition).where(Competition.code == competition_code))
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_code}")
        return competition

    def _competition_name(self, competition: Competition) -> str:
        catalog_entry = self.competition_catalog.get(competition.code)
        if catalog_entry is not None and catalog_entry.editorial_name:
            return catalog_entry.editorial_name
        return competition.name

    def _reference_date(self, reference_date: date | None) -> date:
        if reference_date is not None:
            return reference_date
        return datetime.now(ZoneInfo(self.timezone_name)).date()

    def _draft(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        reference_date: date,
        story_type: ViralStoryType,
        priority: int,
        title: str,
        teams: list[str],
        content_key: str,
        text_draft: str,
        metric_value: float | int | None,
        source_payload: dict[str, Any],
    ) -> ContentCandidateDraft:
        payload_json = {
            "content_key": content_key,
            "template_name": f"viral_story_{story_type}_v1",
            "competition_name": competition_name,
            "reference_date": reference_date.isoformat(),
            "source_payload": {
                "story_type": str(story_type),
                "title": title,
                "teams": teams,
                "metric_value": metric_value,
                **source_payload,
            },
        }
        return ContentCandidateDraft(
            competition_slug=competition_slug,
            content_type=ContentType.VIRAL_STORY,
            priority=priority,
            text_draft=text_draft,
            payload_json=payload_json,
            source_summary_hash=_candidate_hash(
                competition_slug=competition_slug,
                content_key=content_key,
                source_payload=payload_json["source_payload"],
            ),
            scheduled_at=None,
            status=ContentCandidateStatus.DRAFT,
        )

    def _candidate_to_view(
        self,
        competition_name: str,
        candidate: ContentCandidateDraft,
    ) -> EditorialViralStoryCandidateView:
        source_payload = candidate.payload_json.get("source_payload", {})
        return EditorialViralStoryCandidateView(
            competition_slug=candidate.competition_slug,
            competition_name=competition_name,
            content_type=ContentType(candidate.content_type),
            story_type=ViralStoryType(source_payload["story_type"]),
            priority=candidate.priority,
            title=source_payload.get("title", ""),
            teams=list(source_payload.get("teams", [])),
            metric_value=source_payload.get("metric_value"),
            excerpt=_excerpt(candidate.text_draft),
            text_draft=candidate.text_draft,
            source_summary_hash=candidate.source_summary_hash,
        )

    def _team_sequences(self, matches: list[CompetitionMatchView]) -> dict[str, list[dict[str, Any]]]:
        by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for match in matches:
            if match.home_score is None or match.away_score is None:
                continue
            by_team[match.home_team].append(
                {
                    "result": _team_result(match.home_team, match),
                    "goals_for": int(match.home_score),
                    "goals_against": int(match.away_score),
                    "match_date": match.match_date.isoformat() if match.match_date else None,
                    "round_name": match.round_name,
                    "source_url": match.source_url,
                }
            )
            by_team[match.away_team].append(
                {
                    "result": _team_result(match.away_team, match),
                    "goals_for": int(match.away_score),
                    "goals_against": int(match.home_score),
                    "match_date": match.match_date.isoformat() if match.match_date else None,
                    "round_name": match.round_name,
                    "source_url": match.source_url,
                }
            )
        return by_team

    def _build_win_streak_story(
        self,
        competition_slug: str,
        competition_name: str,
        reference_date: date,
        team_sequences: dict[str, list[dict[str, Any]]],
    ) -> ContentCandidateDraft | None:
        best_team: str | None = None
        best_value = 0
        for team, items in team_sequences.items():
            wins = 0
            for item in items:
                if item["result"] == "W":
                    wins += 1
                else:
                    break
            if wins > best_value or (wins == best_value and best_team is not None and team < best_team):
                best_team = team
                best_value = wins
        if best_team is None or best_value < _MIN_WIN_STREAK:
            return None
        return self._draft(
            competition_slug=competition_slug,
            competition_name=competition_name,
            reference_date=reference_date,
            story_type=ViralStoryType.WIN_STREAK,
            priority=_VIRAL_PRIORITY[ViralStoryType.WIN_STREAK],
            title=f"Racha de victorias de {best_team}",
            teams=[best_team],
            content_key=f"viral:win_streak:{best_team}",
            text_draft=f"{best_team} llega con {best_value} victorias seguidas en {competition_name}.",
            metric_value=best_value,
            source_payload={
                "streak_length": best_value,
                "reference_date": reference_date.isoformat(),
            },
        )

    def _build_unbeaten_story(
        self,
        competition_slug: str,
        competition_name: str,
        reference_date: date,
        team_sequences: dict[str, list[dict[str, Any]]],
        *,
        existing_team: str | None,
    ) -> ContentCandidateDraft | None:
        best_team: str | None = None
        best_value = 0
        for team, items in team_sequences.items():
            unbeaten = 0
            for item in items:
                if item["result"] in {"W", "D"}:
                    unbeaten += 1
                else:
                    break
            if unbeaten > best_value or (unbeaten == best_value and best_team is not None and team < best_team):
                best_team = team
                best_value = unbeaten
        if best_team is None or best_value < _MIN_UNBEATEN_STREAK:
            return None
        if existing_team == best_team and best_value <= _MIN_UNBEATEN_STREAK:
            return None
        return self._draft(
            competition_slug=competition_slug,
            competition_name=competition_name,
            reference_date=reference_date,
            story_type=ViralStoryType.UNBEATEN_STREAK,
            priority=_VIRAL_PRIORITY[ViralStoryType.UNBEATEN_STREAK],
            title=f"Racha sin perder de {best_team}",
            teams=[best_team],
            content_key=f"viral:unbeaten_streak:{best_team}",
            text_draft=f"{best_team} encadena {best_value} partidos sin perder en {competition_name}.",
            metric_value=best_value,
            source_payload={
                "streak_length": best_value,
                "reference_date": reference_date.isoformat(),
            },
        )

    def _build_losing_story(
        self,
        competition_slug: str,
        competition_name: str,
        reference_date: date,
        team_sequences: dict[str, list[dict[str, Any]]],
    ) -> ContentCandidateDraft | None:
        worst_team: str | None = None
        worst_value = 0
        for team, items in team_sequences.items():
            losses = 0
            for item in items:
                if item["result"] == "L":
                    losses += 1
                else:
                    break
            if losses > worst_value or (losses == worst_value and worst_team is not None and team < worst_team):
                worst_team = team
                worst_value = losses
        if worst_team is None or worst_value < _MIN_LOSING_STREAK:
            return None
        return self._draft(
            competition_slug=competition_slug,
            competition_name=competition_name,
            reference_date=reference_date,
            story_type=ViralStoryType.LOSING_STREAK,
            priority=_VIRAL_PRIORITY[ViralStoryType.LOSING_STREAK],
            title=f"Racha negativa de {worst_team}",
            teams=[worst_team],
            content_key=f"viral:losing_streak:{worst_team}",
            text_draft=f"{worst_team} arrastra {worst_value} derrotas consecutivas en {competition_name}.",
            metric_value=worst_value,
            source_payload={
                "streak_length": worst_value,
                "reference_date": reference_date.isoformat(),
            },
        )

    def _build_hot_form_story(
        self,
        competition_slug: str,
        competition_name: str,
        reference_date: date,
        team_sequences: dict[str, list[dict[str, Any]]],
    ) -> ContentCandidateDraft | None:
        best_payload: dict[str, Any] | None = None
        for team, items in team_sequences.items():
            recent = items[:_FORM_WINDOW]
            if len(recent) < _MIN_FORM_MATCHES:
                continue
            points = sum(3 if item["result"] == "W" else 1 if item["result"] == "D" else 0 for item in recent)
            wins = sum(1 for item in recent if item["result"] == "W")
            goal_diff = sum(item["goals_for"] - item["goals_against"] for item in recent)
            payload = {
                "team": team,
                "points": points,
                "wins": wins,
                "matches": len(recent),
                "goal_diff": goal_diff,
            }
            if best_payload is None or (
                payload["points"],
                payload["wins"],
                payload["goal_diff"],
                payload["team"],
            ) > (
                best_payload["points"],
                best_payload["wins"],
                best_payload["goal_diff"],
                best_payload["team"],
            ):
                best_payload = payload
        if best_payload is None or best_payload["points"] < _MIN_HOT_FORM_POINTS:
            return None
        team = best_payload["team"]
        matches_count = best_payload["matches"]
        points = best_payload["points"]
        return self._draft(
            competition_slug=competition_slug,
            competition_name=competition_name,
            reference_date=reference_date,
            story_type=ViralStoryType.HOT_FORM,
            priority=_VIRAL_PRIORITY[ViralStoryType.HOT_FORM],
            title=f"Gran forma reciente de {team}",
            teams=[team],
            content_key=f"viral:hot_form:{team}",
            text_draft=(
                f"{team} firma {points} de {matches_count * 3} puntos en sus ultimos "
                f"{matches_count} partidos de {competition_name}."
            ),
            metric_value=points,
            source_payload={
                "recent_matches": matches_count,
                "recent_points": points,
                "recent_wins": best_payload["wins"],
                "recent_goal_diff": best_payload["goal_diff"],
                "reference_date": reference_date.isoformat(),
            },
        )

    def _build_cold_form_story(
        self,
        competition_slug: str,
        competition_name: str,
        reference_date: date,
        team_sequences: dict[str, list[dict[str, Any]]],
    ) -> ContentCandidateDraft | None:
        worst_payload: dict[str, Any] | None = None
        for team, items in team_sequences.items():
            recent = items[:_FORM_WINDOW]
            if len(recent) < _MIN_FORM_MATCHES:
                continue
            points = sum(3 if item["result"] == "W" else 1 if item["result"] == "D" else 0 for item in recent)
            losses = sum(1 for item in recent if item["result"] == "L")
            goal_diff = sum(item["goals_for"] - item["goals_against"] for item in recent)
            payload = {
                "team": team,
                "points": points,
                "losses": losses,
                "matches": len(recent),
                "goal_diff": goal_diff,
            }
            if worst_payload is None or (
                payload["points"],
                -payload["losses"],
                payload["goal_diff"],
                payload["team"],
            ) < (
                worst_payload["points"],
                -worst_payload["losses"],
                worst_payload["goal_diff"],
                worst_payload["team"],
            ):
                worst_payload = payload
        if (
            worst_payload is None
            or worst_payload["points"] > _MIN_COLD_FORM_POINTS
            or worst_payload["losses"] < _MIN_COLD_FORM_LOSSES
        ):
            return None
        team = worst_payload["team"]
        matches_count = worst_payload["matches"]
        points = worst_payload["points"]
        return self._draft(
            competition_slug=competition_slug,
            competition_name=competition_name,
            reference_date=reference_date,
            story_type=ViralStoryType.COLD_FORM,
            priority=_VIRAL_PRIORITY[ViralStoryType.COLD_FORM],
            title=f"Mala dinamica de {team}",
            teams=[team],
            content_key=f"viral:cold_form:{team}",
            text_draft=(
                f"{team} solo ha sumado {points} de {matches_count * 3} puntos en sus ultimos "
                f"{matches_count} partidos de {competition_name}."
            ),
            metric_value=points,
            source_payload={
                "recent_matches": matches_count,
                "recent_points": points,
                "recent_losses": worst_payload["losses"],
                "recent_goal_diff": worst_payload["goal_diff"],
                "reference_date": reference_date.isoformat(),
            },
        )

    def _build_recent_scoring_story(
        self,
        competition_slug: str,
        competition_name: str,
        reference_date: date,
        team_sequences: dict[str, list[dict[str, Any]]],
    ) -> ContentCandidateDraft | None:
        ranking: list[dict[str, Any]] = []
        for team, items in team_sequences.items():
            recent = items[:_RECENT_SCORING_WINDOW]
            if len(recent) < _RECENT_SCORING_WINDOW:
                continue
            goals = sum(item["goals_for"] for item in recent)
            ranking.append({"team": team, "goals": goals, "matches": len(recent)})
        if not ranking:
            return None
        ranking.sort(key=lambda item: (-item["goals"], item["team"]))
        top = ranking[0]
        second_goals = ranking[1]["goals"] if len(ranking) > 1 else 0
        if (
            top["goals"] < _MIN_RECENT_SCORING_GOALS
            or top["goals"] - second_goals < _MIN_RECENT_SCORING_MARGIN
        ):
            return None
        team = top["team"]
        goals = top["goals"]
        matches_count = top["matches"]
        return self._draft(
            competition_slug=competition_slug,
            competition_name=competition_name,
            reference_date=reference_date,
            story_type=ViralStoryType.RECENT_TOP_SCORER,
            priority=_VIRAL_PRIORITY[ViralStoryType.RECENT_TOP_SCORER],
            title=f"Equipo mas goleador reciente: {team}",
            teams=[team],
            content_key=f"viral:recent_top_scorer:{team}",
            text_draft=(
                f"{team} es el equipo mas goleador en sus ultimos {matches_count} partidos "
                f"de {competition_name}: {goals} tantos."
            ),
            metric_value=goals,
            source_payload={
                "recent_matches": matches_count,
                "recent_goals_for": goals,
                "margin_vs_second": goals - second_goals,
                "reference_date": reference_date.isoformat(),
            },
        )

    def _build_best_attack_story(
        self,
        competition_slug: str,
        competition_name: str,
        reference_date: date,
        standings: list[StandingView],
    ) -> ContentCandidateDraft | None:
        rows = [row for row in standings if row.goals_for is not None]
        if len(rows) < 2:
            return None
        ranking = sorted(rows, key=lambda row: (-int(row.goals_for or 0), row.position, row.team))
        leader = ranking[0]
        runner_up = ranking[1]
        margin = int(leader.goals_for or 0) - int(runner_up.goals_for or 0)
        if margin < _MIN_ATTACK_MARGIN:
            return None
        goals_for = int(leader.goals_for or 0)
        return self._draft(
            competition_slug=competition_slug,
            competition_name=competition_name,
            reference_date=reference_date,
            story_type=ViralStoryType.BEST_ATTACK,
            priority=_VIRAL_PRIORITY[ViralStoryType.BEST_ATTACK],
            title=f"Mejor ataque destacado: {leader.team}",
            teams=[leader.team],
            content_key=f"viral:best_attack:{leader.team}",
            text_draft=(
                f"{leader.team} lidera el ataque de {competition_name} con {goals_for} goles, "
                f"{margin} mas que el siguiente registro."
            ),
            metric_value=goals_for,
            source_payload={
                "goals_for": goals_for,
                "position": leader.position,
                "margin_vs_second": margin,
                "runner_up_team": runner_up.team,
            },
        )

    def _build_best_defense_story(
        self,
        competition_slug: str,
        competition_name: str,
        reference_date: date,
        standings: list[StandingView],
    ) -> ContentCandidateDraft | None:
        rows = [row for row in standings if row.goals_against is not None]
        if len(rows) < 2:
            return None
        ranking = sorted(rows, key=lambda row: (int(row.goals_against or 0), row.position, row.team))
        leader = ranking[0]
        runner_up = ranking[1]
        margin = int(runner_up.goals_against or 0) - int(leader.goals_against or 0)
        if margin < _MIN_DEFENSE_MARGIN:
            return None
        goals_against = int(leader.goals_against or 0)
        return self._draft(
            competition_slug=competition_slug,
            competition_name=competition_name,
            reference_date=reference_date,
            story_type=ViralStoryType.BEST_DEFENSE,
            priority=_VIRAL_PRIORITY[ViralStoryType.BEST_DEFENSE],
            title=f"Mejor defensa destacada: {leader.team}",
            teams=[leader.team],
            content_key=f"viral:best_defense:{leader.team}",
            text_draft=(
                f"{leader.team} sostiene la mejor defensa de {competition_name} con {goals_against} "
                f"goles encajados, {margin} menos que el siguiente equipo."
            ),
            metric_value=goals_against,
            source_payload={
                "goals_against": goals_against,
                "position": leader.position,
                "margin_vs_second": margin,
                "runner_up_team": runner_up.team,
            },
        )

    def _build_goals_trend_story(
        self,
        competition_id: int,
        competition_slug: str,
        competition_name: str,
        reference_date: date,
    ) -> ContentCandidateDraft | None:
        payload = self._goals_trend_payload(competition_id, reference_date)
        if (
            payload["season_matches"] < _MIN_SEASON_MATCHES_FOR_TREND
            or payload["recent_matches"] < _MIN_TREND_MATCHES
            or abs(payload["delta"]) < _MIN_GOALS_TREND_DELTA
        ):
            return None
        trend_direction = "offensive" if payload["delta"] > 0 else "defensive"
        if trend_direction == "offensive":
            text_draft = (
                f"{competition_name} deja una tendencia ofensiva reciente: "
                f"{_format_metric_value(payload['recent_average'])} goles por partido en los ultimos "
                f"{payload['recent_matches']} encuentros, por encima del "
                f"{_format_metric_value(payload['season_average'])} del curso."
            )
            title = f"Tendencia ofensiva en {competition_name}"
        else:
            text_draft = (
                f"{competition_name} baja su media reciente a "
                f"{_format_metric_value(payload['recent_average'])} goles por partido en los ultimos "
                f"{payload['recent_matches']} encuentros, por debajo del "
                f"{_format_metric_value(payload['season_average'])} de la temporada."
            )
            title = f"Tendencia defensiva en {competition_name}"
        return self._draft(
            competition_slug=competition_slug,
            competition_name=competition_name,
            reference_date=reference_date,
            story_type=ViralStoryType.GOALS_TREND,
            priority=_VIRAL_PRIORITY[ViralStoryType.GOALS_TREND],
            title=title,
            teams=[],
            content_key=f"viral:goals_trend:{trend_direction}",
            text_draft=text_draft,
            metric_value=payload["recent_average"],
            source_payload={
                "trend_direction": trend_direction,
                "recent_matches": payload["recent_matches"],
                "season_matches": payload["season_matches"],
                "recent_average": payload["recent_average"],
                "season_average": payload["season_average"],
                "delta": payload["delta"],
            },
        )

    def _goals_trend_payload(self, competition_id: int, reference_date: date) -> dict[str, Any]:
        filters = [
            Match.competition_id == competition_id,
            Match.status == "finished",
            Match.match_date <= reference_date,
        ]
        goals_expr = func.coalesce(Match.home_score, 0) + func.coalesce(Match.away_score, 0)
        total_goals = self.session.scalar(
            select(func.coalesce(func.sum(goals_expr), 0)).where(*filters)
        ) or 0
        season_matches = self.session.scalar(
            select(func.count()).select_from(Match).where(*filters)
        ) or 0
        recent_rows = self.session.execute(
            select(Match.home_score, Match.away_score)
            .where(*filters)
            .order_by(Match.match_date.desc().nullslast(), Match.match_time.desc().nullslast(), Match.id.desc())
            .limit(_TREND_WINDOW)
        ).all()
        recent_goals = sum(int((row.home_score or 0) + (row.away_score or 0)) for row in recent_rows)
        recent_matches = len(recent_rows)
        season_average = round(total_goals / season_matches, 2) if season_matches else 0.0
        recent_average = round(recent_goals / recent_matches, 2) if recent_matches else 0.0
        return {
            "season_matches": int(season_matches),
            "recent_matches": int(recent_matches),
            "season_average": season_average,
            "recent_average": recent_average,
            "delta": round(recent_average - season_average, 2),
        }
