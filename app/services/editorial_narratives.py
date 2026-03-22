from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import get_settings
from app.core.enums import ContentCandidateStatus, ContentType, NarrativeMetricType
from app.core.exceptions import ConfigurationError
from app.db.models import Competition, Match
from app.db.repositories.content_candidates import ContentCandidateRepository
from app.schemas.common import IngestStats
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.editorial_narratives import (
    EditorialNarrativeCandidateView,
    EditorialNarrativesGenerationResult,
    EditorialNarrativesResult,
)
from app.schemas.reporting import CompetitionMatchView
from app.services.competition_queries import CompetitionQueryService
from app.services.competition_relevance import CompetitionRelevanceService
from app.services.editorial_formatter import EditorialFormatterService
from app.utils.hashing import stable_hash
from app.utils.time import utcnow

_NARRATIVE_PRIORITY = {
    NarrativeMetricType.WIN_STREAK: 68,
    NarrativeMetricType.UNBEATEN_STREAK: 67,
    NarrativeMetricType.BEST_ATTACK: 66,
    NarrativeMetricType.BEST_DEFENSE: 65,
    NarrativeMetricType.MOST_WINS: 64,
    NarrativeMetricType.GOALS_AVERAGE: 63,
}

_MIN_WIN_STREAK = 3
_MIN_UNBEATEN_STREAK = 4

METRIC_NARRATIVE_THRESHOLDS = {
    NarrativeMetricType.WIN_STREAK: _MIN_WIN_STREAK,
    NarrativeMetricType.UNBEATEN_STREAK: _MIN_UNBEATEN_STREAK,
}


def _excerpt(text: str, limit: int = 110) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _format_metric_value(value: float | int) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _candidate_hash(
    competition_slug: str,
    content_key: str,
    source_payload: dict[str, Any],
) -> str:
    return stable_hash(
        {
            "competition_slug": competition_slug,
            "content_type": str(ContentType.METRIC_NARRATIVE),
            "content_key": content_key,
            "source_payload": source_payload,
        }
    )


def _team_result(team_name: str, match: CompetitionMatchView) -> str:
    if match.home_score is None or match.away_score is None:
        raise ValueError("No se puede calcular una racha con un partido sin marcador final")
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


class EditorialNarrativesService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ContentCandidateRepository(session)
        self.queries = CompetitionQueryService(session)
        self.relevance = CompetitionRelevanceService()
        self.competition_catalog = load_competition_catalog()
        self.timezone_name = get_settings().timezone

    def preview_for_competition(
        self,
        competition_code: str,
        *,
        reference_date: date | None = None,
    ) -> EditorialNarrativesResult:
        competition = self._competition(competition_code)
        selected_date = self._reference_date(reference_date)
        candidates = self.build_candidate_drafts(competition_code, reference_date=selected_date)
        competition_name = self._competition_name(competition)
        return EditorialNarrativesResult(
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
    ) -> EditorialNarrativesGenerationResult:
        preview = self.preview_for_competition(competition_code, reference_date=reference_date)
        candidates = self.build_candidate_drafts(competition_code, reference_date=preview.reference_date)
        stats = self.store_candidates(candidates)
        return EditorialNarrativesGenerationResult(
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
        candidates: list[ContentCandidateDraft] = []

        finished_matches = self.queries.finished_matches(
            competition_code,
            limit=None,
            reference_date=selected_date,
        )
        streaks = self._current_team_streaks(finished_matches)
        top_win_streak = max(streaks, key=lambda item: (item["wins"], item["unbeaten"], item["team"]), default=None)
        top_unbeaten = max(streaks, key=lambda item: (item["unbeaten"], item["wins"], item["team"]), default=None)

        if top_win_streak and top_win_streak["wins"] >= _MIN_WIN_STREAK:
            value = int(top_win_streak["wins"])
            team = str(top_win_streak["team"])
            candidates.append(
                self._draft(
                    competition_slug=competition_code,
                    competition_name=competition_name,
                    reference_date=selected_date,
                    narrative_type=NarrativeMetricType.WIN_STREAK,
                    priority=_NARRATIVE_PRIORITY[NarrativeMetricType.WIN_STREAK],
                    content_key=f"metric:win_streak:{team}",
                    text_draft=f"{team} suma {value} victorias consecutivas en {competition_name}.",
                    source_payload={
                        "narrative_type": str(NarrativeMetricType.WIN_STREAK),
                        "team": team,
                        "metric_value": value,
                        "reference_date": selected_date.isoformat(),
                    },
                )
            )

        if (
            top_unbeaten
            and top_unbeaten["unbeaten"] >= _MIN_UNBEATEN_STREAK
            and (
                top_win_streak is None
                or top_unbeaten["team"] != top_win_streak["team"]
                or top_unbeaten["unbeaten"] > top_win_streak["wins"]
            )
        ):
            value = int(top_unbeaten["unbeaten"])
            team = str(top_unbeaten["team"])
            candidates.append(
                self._draft(
                    competition_slug=competition_code,
                    competition_name=competition_name,
                    reference_date=selected_date,
                    narrative_type=NarrativeMetricType.UNBEATEN_STREAK,
                    priority=_NARRATIVE_PRIORITY[NarrativeMetricType.UNBEATEN_STREAK],
                    content_key=f"metric:unbeaten_streak:{team}",
                    text_draft=f"{team} encadena {value} partidos sin perder en {competition_name}.",
                    source_payload={
                        "narrative_type": str(NarrativeMetricType.UNBEATEN_STREAK),
                        "team": team,
                        "metric_value": value,
                        "reference_date": selected_date.isoformat(),
                    },
                )
            )

        try:
            standings = self.queries.current_standings(competition_code)
            best_attack = next(iter(self.relevance.top_scoring_teams_from_standings(competition_code, standings, limit=1)), None)
            best_defense = next(iter(self.relevance.best_defense_teams_from_standings(competition_code, standings, limit=1)), None)
            most_wins = next(iter(self.relevance.most_wins_teams_from_standings(competition_code, standings, limit=1)), None)
        except ConfigurationError:
            best_attack = None
            best_defense = None
            most_wins = None

        if best_attack is not None and best_attack.value is not None:
            candidates.append(
                self._draft(
                    competition_slug=competition_code,
                    competition_name=competition_name,
                    reference_date=selected_date,
                    narrative_type=NarrativeMetricType.BEST_ATTACK,
                    priority=_NARRATIVE_PRIORITY[NarrativeMetricType.BEST_ATTACK],
                    content_key=f"metric:best_attack:{best_attack.team}",
                    text_draft=(
                        f"{best_attack.team} firma el mejor ataque de {competition_name} "
                        f"con {best_attack.value} goles a favor."
                    ),
                    source_payload={
                        "narrative_type": str(NarrativeMetricType.BEST_ATTACK),
                        "team": best_attack.team,
                        "metric_value": best_attack.value,
                        "position": best_attack.position,
                    },
                )
            )

        if best_defense is not None and best_defense.value is not None:
            candidates.append(
                self._draft(
                    competition_slug=competition_code,
                    competition_name=competition_name,
                    reference_date=selected_date,
                    narrative_type=NarrativeMetricType.BEST_DEFENSE,
                    priority=_NARRATIVE_PRIORITY[NarrativeMetricType.BEST_DEFENSE],
                    content_key=f"metric:best_defense:{best_defense.team}",
                    text_draft=(
                        f"{best_defense.team} presenta la mejor defensa de {competition_name} "
                        f"con solo {best_defense.value} goles encajados."
                    ),
                    source_payload={
                        "narrative_type": str(NarrativeMetricType.BEST_DEFENSE),
                        "team": best_defense.team,
                        "metric_value": best_defense.value,
                        "position": best_defense.position,
                    },
                )
            )

        if most_wins is not None and most_wins.value is not None:
            candidates.append(
                self._draft(
                    competition_slug=competition_code,
                    competition_name=competition_name,
                    reference_date=selected_date,
                    narrative_type=NarrativeMetricType.MOST_WINS,
                    priority=_NARRATIVE_PRIORITY[NarrativeMetricType.MOST_WINS],
                    content_key=f"metric:most_wins:{most_wins.team}",
                    text_draft=(
                        f"{most_wins.team} es el equipo con mas victorias de {competition_name}: "
                        f"{most_wins.value}."
                    ),
                    source_payload={
                        "narrative_type": str(NarrativeMetricType.MOST_WINS),
                        "team": most_wins.team,
                        "metric_value": most_wins.value,
                        "position": most_wins.position,
                    },
                )
            )

        average_payload = self._goals_average_payload(competition.id, selected_date)
        if average_payload["played_matches"] > 0:
            average_goals = average_payload["average_goals"]
            candidates.append(
                self._draft(
                    competition_slug=competition_code,
                    competition_name=competition_name,
                    reference_date=selected_date,
                    narrative_type=NarrativeMetricType.GOALS_AVERAGE,
                    priority=_NARRATIVE_PRIORITY[NarrativeMetricType.GOALS_AVERAGE],
                    content_key="metric:goals_average",
                    text_draft=(
                        f"En {competition_name} se marcan {_format_metric_value(average_goals)} goles por partido "
                        f"tras {average_payload['played_matches']} encuentros disputados."
                    ),
                    source_payload={
                        "narrative_type": str(NarrativeMetricType.GOALS_AVERAGE),
                        "metric_value": average_goals,
                        "played_matches": average_payload["played_matches"],
                        "total_goals": average_payload["total_goals"],
                    },
                )
            )

        return sorted(candidates, key=lambda item: (-item.priority, item.source_summary_hash))

    def store_candidates(self, candidates: list[ContentCandidateDraft]) -> IngestStats:
        candidates = EditorialFormatterService(self.session).apply_to_drafts(candidates)
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
        narrative_type: NarrativeMetricType,
        priority: int,
        content_key: str,
        text_draft: str,
        source_payload: dict[str, Any],
    ) -> ContentCandidateDraft:
        payload_json = {
            "content_key": content_key,
            "template_name": f"metric_narrative_{narrative_type}_v1",
            "competition_name": competition_name,
            "reference_date": reference_date.isoformat(),
            "source_payload": source_payload,
        }
        return ContentCandidateDraft(
            competition_slug=competition_slug,
            content_type=ContentType.METRIC_NARRATIVE,
            priority=priority,
            text_draft=text_draft,
            payload_json=payload_json,
            source_summary_hash=_candidate_hash(
                competition_slug=competition_slug,
                content_key=content_key,
                source_payload=source_payload,
            ),
            scheduled_at=None,
            status=ContentCandidateStatus.DRAFT,
        )

    def _candidate_to_view(
        self,
        competition_name: str,
        candidate: ContentCandidateDraft,
    ) -> EditorialNarrativeCandidateView:
        source_payload = candidate.payload_json.get("source_payload", {})
        return EditorialNarrativeCandidateView(
            competition_slug=candidate.competition_slug,
            competition_name=competition_name,
            content_type=ContentType(candidate.content_type),
            narrative_type=NarrativeMetricType(source_payload["narrative_type"]),
            priority=candidate.priority,
            team=source_payload.get("team"),
            metric_value=source_payload.get("metric_value"),
            excerpt=_excerpt(candidate.text_draft),
            text_draft=candidate.text_draft,
            source_summary_hash=candidate.source_summary_hash,
        )

    def _current_team_streaks(self, matches: list[CompetitionMatchView]) -> list[dict[str, Any]]:
        by_team: dict[str, list[str]] = defaultdict(list)
        for match in matches:
            if match.home_score is None or match.away_score is None:
                continue
            by_team[match.home_team].append(_team_result(match.home_team, match))
            by_team[match.away_team].append(_team_result(match.away_team, match))

        streaks: list[dict[str, Any]] = []
        for team, results in by_team.items():
            wins = 0
            unbeaten = 0
            for result in results:
                if result == "W":
                    wins += 1
                else:
                    break
            for result in results:
                if result in {"W", "D"}:
                    unbeaten += 1
                else:
                    break
            streaks.append({"team": team, "wins": wins, "unbeaten": unbeaten})
        return streaks

    def _goals_average_payload(self, competition_id: int, reference_date: date) -> dict[str, Any]:
        filters = [
            Match.competition_id == competition_id,
            Match.status == "finished",
            Match.match_date <= reference_date,
        ]
        goals_expr = func.coalesce(Match.home_score, 0) + func.coalesce(Match.away_score, 0)
        total_goals = self.session.scalar(
            select(func.coalesce(func.sum(goals_expr), 0)).where(*filters)
        ) or 0
        played_matches = self.session.scalar(
            select(func.count()).select_from(Match).where(*filters)
        ) or 0
        average_goals = round(total_goals / played_matches, 2) if played_matches else 0.0
        return {
            "total_goals": int(total_goals),
            "played_matches": int(played_matches),
            "average_goals": average_goals,
        }
