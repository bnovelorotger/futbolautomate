from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType, FormEventType
from app.core.exceptions import ConfigurationError
from app.db.models import Competition
from app.db.repositories.content_candidates import ContentCandidateRepository
from app.schemas.common import IngestStats
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.reporting import CompetitionMatchView
from app.schemas.team_form import (
    TeamFormEntryView,
    TeamFormEventView,
    TeamFormGenerationResult,
    TeamFormResult,
)
from app.services.competition_queries import CompetitionQueryService
from app.services.competition_relevance import CompetitionRelevanceService
from app.services.editorial_formatter import EditorialFormatterService
from app.utils.hashing import stable_hash
from app.utils.time import utcnow

DEFAULT_FORM_WINDOW = 5
DEFAULT_FORM_RANKING_LIMIT = 3
MIN_FORM_MATCHES = 3
MIN_SIGNAL_STREAK = 3

_FORM_EVENT_PRIORITY = {
    FormEventType.BEST_FORM_TEAM: 69,
    FormEventType.WORST_FORM_TEAM: 66,
    FormEventType.LONGEST_WIN_STREAK_RECENT: 68,
    FormEventType.LONGEST_LOSS_STREAK_RECENT: 65,
}


def _excerpt(text: str, limit: int = 110) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _team_result(team_name: str, match: CompetitionMatchView) -> str:
    if match.home_score is None or match.away_score is None:
        raise ValueError("No se puede calcular forma con un partido sin marcador final")
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


def _points_for_sequence(sequence: str) -> int:
    mapping = {"W": 3, "D": 1, "L": 0}
    return sum(mapping.get(item, 0) for item in sequence)


def _current_streak(sequence: str, symbol: str) -> int:
    streak = 0
    for item in sequence:
        if item != symbol:
            break
        streak += 1
    return streak


def _longest_streak(sequence: str, symbol: str) -> int:
    best = 0
    current = 0
    for item in sequence:
        if item == symbol:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _candidate_hash(
    competition_slug: str,
    content_type: ContentType,
    content_key: str,
    source_payload: dict[str, Any],
) -> str:
    return stable_hash(
        {
            "competition_slug": competition_slug,
            "content_type": str(content_type),
            "content_key": content_key,
            "source_payload": source_payload,
        }
    )


class TeamFormService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.queries = CompetitionQueryService(session)
        self.relevance = CompetitionRelevanceService()
        self.repository = ContentCandidateRepository(session)
        self.catalog = load_competition_catalog()

    def preview_for_competition(
        self,
        competition_code: str,
        *,
        window_size: int = DEFAULT_FORM_WINDOW,
        reference_date: date | None = None,
    ) -> TeamFormResult:
        competition = self._competition(competition_code)
        selected_date = self._reference_date(reference_date)
        rows = self.build_form_rows(
            competition_code,
            window_size=window_size,
            reference_date=selected_date,
        )
        competition_name = self._competition_name(competition)
        return TeamFormResult(
            competition_slug=competition_code,
            competition_name=competition_name,
            reference_date=selected_date,
            window_size=window_size,
            generated_at=utcnow(),
            rows=rows,
            events=self._build_event_views(
                competition_code,
                competition_name,
                rows,
                window_size=window_size,
            ),
        )

    def ranking_for_competition(
        self,
        competition_code: str,
        *,
        window_size: int = DEFAULT_FORM_WINDOW,
        reference_date: date | None = None,
    ) -> TeamFormResult:
        return self.preview_for_competition(
            competition_code,
            window_size=window_size,
            reference_date=reference_date,
        )

    def generate_for_competition(
        self,
        competition_code: str,
        *,
        window_size: int = DEFAULT_FORM_WINDOW,
        reference_date: date | None = None,
    ) -> TeamFormGenerationResult:
        preview = self.preview_for_competition(
            competition_code,
            window_size=window_size,
            reference_date=reference_date,
        )
        candidates = self.build_candidate_drafts(
            competition_code,
            window_size=window_size,
            reference_date=preview.reference_date,
        )
        stats = self.store_candidates(candidates)
        return TeamFormGenerationResult(
            competition_slug=preview.competition_slug,
            competition_name=preview.competition_name,
            reference_date=preview.reference_date,
            window_size=preview.window_size,
            generated_at=preview.generated_at,
            rows=preview.rows,
            events=preview.events,
            stats=stats,
        )

    def build_form_rows(
        self,
        competition_code: str,
        *,
        window_size: int = DEFAULT_FORM_WINDOW,
        reference_date: date | None = None,
        respect_tracking: bool = True,
    ) -> list[TeamFormEntryView]:
        if window_size <= 0:
            raise ConfigurationError("window_size debe ser mayor que cero")
        self._competition(competition_code)
        matches = self.queries.finished_matches(
            competition_code,
            limit=None,
            reference_date=reference_date,
        )
        by_team: dict[str, list[dict[str, int | str | None]]] = defaultdict(list)
        for match in matches:
            if match.home_score is None or match.away_score is None:
                continue
            home_team = self._resolved_team_name(
                competition_code,
                match.home_team,
                respect_tracking=respect_tracking,
            )
            away_team = self._resolved_team_name(
                competition_code,
                match.away_team,
                respect_tracking=respect_tracking,
            )
            if home_team is not None and len(by_team[home_team]) < window_size:
                by_team[home_team].append(
                    {
                        "result": _team_result(match.home_team, match),
                        "goals_for": int(match.home_score),
                        "goals_against": int(match.away_score),
                    }
                )
            if away_team is not None and len(by_team[away_team]) < window_size:
                by_team[away_team].append(
                    {
                        "result": _team_result(match.away_team, match),
                        "goals_for": int(match.away_score),
                        "goals_against": int(match.home_score),
                    }
                )

        rows: list[TeamFormEntryView] = []
        for team, entries in by_team.items():
            sequence = "".join(str(entry["result"]) for entry in entries)
            goals_for = sum(int(entry["goals_for"]) for entry in entries)
            goals_against = sum(int(entry["goals_against"]) for entry in entries)
            wins = sequence.count("W")
            draws = sequence.count("D")
            losses = sequence.count("L")
            rows.append(
                TeamFormEntryView(
                    rank=0,
                    team=team,
                    matches_considered=len(entries),
                    sequence=sequence,
                    points=_points_for_sequence(sequence),
                    wins=wins,
                    draws=draws,
                    losses=losses,
                    goals_for=goals_for,
                    goals_against=goals_against,
                    goal_difference=goals_for - goals_against,
                    current_win_streak=_current_streak(sequence, "W"),
                    current_loss_streak=_current_streak(sequence, "L"),
                    longest_win_streak=_longest_streak(sequence, "W"),
                    longest_loss_streak=_longest_streak(sequence, "L"),
                )
            )

        rows = sorted(
            rows,
            key=lambda row: (
                -row.points,
                -row.goal_difference,
                -row.goals_for,
                row.team,
            ),
        )
        return [
            row.model_copy(update={"rank": index})
            for index, row in enumerate(rows, start=1)
        ]

    def build_candidate_drafts(
        self,
        competition_code: str,
        *,
        window_size: int = DEFAULT_FORM_WINDOW,
        reference_date: date | None = None,
    ) -> list[ContentCandidateDraft]:
        preview = self.preview_for_competition(
            competition_code,
            window_size=window_size,
            reference_date=reference_date,
        )
        candidates: list[ContentCandidateDraft] = []
        ranking_draft = self._ranking_draft(preview)
        if ranking_draft is not None:
            candidates.append(ranking_draft)
        for event in preview.events:
            candidates.append(self._event_draft(preview, event))
        return sorted(candidates, key=lambda item: (-item.priority, item.source_summary_hash))

    def store_candidates(self, candidates: list[ContentCandidateDraft]) -> IngestStats:
        candidates = EditorialFormatterService(self.session).apply_to_drafts(candidates)
        stats = IngestStats(found=len(candidates))
        for candidate in candidates:
            _, inserted, updated = self.repository.upsert(candidate.model_dump(mode="python"))
            stats.inserted += int(inserted)
            stats.updated += int(updated)
        return stats

    def _ranking_draft(self, preview: TeamFormResult) -> ContentCandidateDraft | None:
        top_rows = preview.rows[:DEFAULT_FORM_RANKING_LIMIT]
        if not top_rows:
            return None
        lines = [
            f"Forma ultimos {preview.window_size} partidos en {preview.competition_name}:",
            "",
        ]
        for row in top_rows:
            lines.append(f"{row.rank}. {row.team} -> {row.sequence} ({row.points} pts)")
        text_draft = "\n".join(lines)
        source_payload = {
            "window_size": preview.window_size,
            "top_count": len(top_rows),
            "ranking": [
                {
                    "rank": row.rank,
                    "team": row.team,
                    "sequence": row.sequence,
                    "points": row.points,
                    "goal_difference": row.goal_difference,
                    "goals_for": row.goals_for,
                }
                for row in top_rows
            ],
            "teams": [row.team for row in top_rows],
        }
        return ContentCandidateDraft(
            competition_slug=preview.competition_slug,
            content_type=ContentType.FORM_RANKING,
            priority=67,
            text_draft=text_draft,
            payload_json={
                "content_key": f"form_ranking:window_{preview.window_size}",
                "template_name": "form_ranking_v1",
                "competition_name": preview.competition_name,
                "reference_date": preview.reference_date.isoformat(),
                "source_payload": source_payload,
            },
            source_summary_hash=_candidate_hash(
                preview.competition_slug,
                ContentType.FORM_RANKING,
                f"form_ranking:window_{preview.window_size}",
                source_payload,
            ),
            status=ContentCandidateStatus.DRAFT,
        )

    def _event_draft(
        self,
        preview: TeamFormResult,
        event: TeamFormEventView,
    ) -> ContentCandidateDraft:
        source_payload = {
            "event_type": str(event.event_type),
            "title": event.title,
            "team": event.team,
            "teams": [event.team],
            "sequence": event.sequence,
            "matches_considered": event.matches_considered,
            "points": event.points,
            "metric_value": event.metric_value,
            "window_size": preview.window_size,
        }
        content_key = f"form_event:{event.event_type}:{event.team}:window_{preview.window_size}"
        return ContentCandidateDraft(
            competition_slug=preview.competition_slug,
            content_type=ContentType.FORM_EVENT,
            priority=event.priority,
            text_draft=event.text_draft,
            payload_json={
                "content_key": content_key,
                "template_name": f"form_event_{event.event_type}_v1",
                "competition_name": preview.competition_name,
                "reference_date": preview.reference_date.isoformat(),
                "source_payload": source_payload,
            },
            source_summary_hash=_candidate_hash(
                preview.competition_slug,
                ContentType.FORM_EVENT,
                content_key,
                source_payload,
            ),
            status=ContentCandidateStatus.DRAFT,
        )

    def _build_event_views(
        self,
        competition_code: str,
        competition_name: str,
        rows: list[TeamFormEntryView],
        *,
        window_size: int,
    ) -> list[TeamFormEventView]:
        events: list[TeamFormEventView] = []
        signal_rows = [row for row in rows if row.matches_considered >= MIN_FORM_MATCHES]
        if not signal_rows:
            return events

        best_form = signal_rows[0]
        worst_form = signal_rows[-1]
        events.append(
            self._event_view(
                competition_slug=competition_code,
                competition_name=competition_name,
                event_type=FormEventType.BEST_FORM_TEAM,
                row=best_form,
                window_size=window_size,
                text_draft=(
                    f"{best_form.team} es el equipo mas en forma de {competition_name}: "
                    f"{best_form.points} puntos de {best_form.matches_considered * 3} posibles "
                    f"en los ultimos {best_form.matches_considered} partidos."
                ),
                metric_value=best_form.points,
            )
        )
        events.append(
            self._event_view(
                competition_slug=competition_code,
                competition_name=competition_name,
                event_type=FormEventType.WORST_FORM_TEAM,
                row=worst_form,
                window_size=window_size,
                text_draft=(
                    f"{worst_form.team} firma la peor dinamica reciente de {competition_name}: "
                    f"{worst_form.points} puntos en los ultimos {worst_form.matches_considered} partidos."
                ),
                metric_value=worst_form.points,
            )
        )

        best_win_run = max(
            signal_rows,
            key=lambda row: (
                row.longest_win_streak,
                row.points,
                row.goal_difference,
                row.goals_for,
                -row.rank,
            ),
        )
        if best_win_run.longest_win_streak >= MIN_SIGNAL_STREAK:
            events.append(
                self._event_view(
                    competition_slug=competition_code,
                    competition_name=competition_name,
                    event_type=FormEventType.LONGEST_WIN_STREAK_RECENT,
                    row=best_win_run,
                    window_size=window_size,
                    text_draft=(
                        f"{best_win_run.team} presenta la mejor racha reciente de {competition_name}: "
                        f"{best_win_run.longest_win_streak} victorias seguidas dentro de sus ultimos "
                        f"{min(window_size, best_win_run.matches_considered)} partidos."
                    ),
                    metric_value=best_win_run.longest_win_streak,
                )
            )

        worst_loss_run = max(
            signal_rows,
            key=lambda row: (
                row.longest_loss_streak,
                -row.points,
                -row.goal_difference,
                -row.goals_for,
                row.rank,
            ),
        )
        if worst_loss_run.longest_loss_streak >= MIN_SIGNAL_STREAK:
            events.append(
                self._event_view(
                    competition_slug=competition_code,
                    competition_name=competition_name,
                    event_type=FormEventType.LONGEST_LOSS_STREAK_RECENT,
                    row=worst_loss_run,
                    window_size=window_size,
                    text_draft=(
                        f"{worst_loss_run.team} arrastra la peor racha reciente de {competition_name}: "
                        f"{worst_loss_run.longest_loss_streak} derrotas seguidas dentro de sus ultimos "
                        f"{min(window_size, worst_loss_run.matches_considered)} partidos."
                    ),
                    metric_value=worst_loss_run.longest_loss_streak,
                )
            )

        return sorted(events, key=lambda item: (-item.priority, item.team))

    def _event_view(
        self,
        *,
        competition_slug: str,
        competition_name: str,
        event_type: FormEventType,
        row: TeamFormEntryView,
        window_size: int,
        text_draft: str,
        metric_value: int,
    ) -> TeamFormEventView:
        title = {
            FormEventType.BEST_FORM_TEAM: f"Mejor forma reciente: {row.team}",
            FormEventType.WORST_FORM_TEAM: f"Peor forma reciente: {row.team}",
            FormEventType.LONGEST_WIN_STREAK_RECENT: f"Mejor racha reciente: {row.team}",
            FormEventType.LONGEST_LOSS_STREAK_RECENT: f"Peor racha reciente: {row.team}",
        }[event_type]
        source_payload = {
            "event_type": str(event_type),
            "team": row.team,
            "sequence": row.sequence,
            "points": row.points,
            "metric_value": metric_value,
            "window_size": window_size,
        }
        return TeamFormEventView(
            competition_slug=competition_slug,
            competition_name=competition_name,
            event_type=event_type,
            priority=_FORM_EVENT_PRIORITY[event_type],
            title=title,
            team=row.team,
            sequence=row.sequence,
            matches_considered=row.matches_considered,
            points=row.points,
            metric_value=metric_value,
            excerpt=_excerpt(text_draft),
            text_draft=text_draft,
            source_summary_hash=_candidate_hash(
                competition_slug,
                ContentType.FORM_EVENT,
                f"form_event:{event_type}:{row.team}:window_{window_size}",
                source_payload,
            ),
        )

    def _resolved_team_name(
        self,
        competition_code: str,
        team_name: str,
        *,
        respect_tracking: bool,
    ) -> str | None:
        if not respect_tracking or not self.relevance.has_tracked_teams(competition_code):
            return team_name
        return self.relevance.canonical_team(competition_code, team_name)

    def _competition(self, competition_code: str) -> Competition:
        competition = self.session.scalar(
            select(Competition).where(Competition.code == competition_code)
        )
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_code}")
        return competition

    def _competition_name(self, competition: Competition) -> str:
        definition = self.catalog.get(competition.code)
        if definition is not None and definition.editorial_name:
            return definition.editorial_name
        return competition.name

    def _reference_date(self, reference_date: date | None) -> date:
        if reference_date is not None:
            return reference_date
        return datetime.now(ZoneInfo(self.settings.timezone)).date()
