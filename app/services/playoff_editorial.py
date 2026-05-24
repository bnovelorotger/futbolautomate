from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog
from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.core.exceptions import ConfigurationError
from app.db.models import Competition
from app.db.repositories.content_candidates import ContentCandidateRepository
from app.schemas.common import IngestStats
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.reporting import CompetitionMatchView
from app.services.competition_queries import CompetitionQueryService
from app.services.editorial_formatter import EditorialFormatterService
from app.utils.hashing import stable_hash


class PlayoffEditorialService:
    """Playoff-specific draft builder that does not require standings rows."""

    def __init__(self, session: Session, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.queries = CompetitionQueryService(session)
        self.repository = ContentCandidateRepository(session)
        self.catalog = load_competition_catalog()

    def build_featured_preview_drafts(
        self,
        competition_slug: str,
        *,
        reference_date: date | None = None,
        limit: int = 1,
    ) -> list[ContentCandidateDraft]:
        selected_date = self._reference_date(reference_date)
        matches = self.queries.editorial_upcoming_matches(
            competition_slug,
            limit=max(limit, 1),
            relevant_only=True,
            reference_date=selected_date,
            max_days_ahead=10,
        )
        if not matches:
            return []
        competition_name = self._competition_name(competition_slug)
        candidates: list[ContentCandidateDraft] = []
        for match in matches[:limit]:
            source_payload = self._source_payload(
                competition_slug,
                match,
                matches=matches,
                reference_date=selected_date,
            )
            content_key = self._content_key(competition_slug, match, selected_date)
            candidates.append(
                ContentCandidateDraft(
                    competition_slug=competition_slug,
                    content_type=ContentType.FEATURED_MATCH_PREVIEW,
                    priority=92,
                    text_draft=self._preview_text(competition_name, match, source_payload),
                    payload_json={
                        "content_key": content_key,
                        "template_name": "playoff_featured_match_preview_v1",
                        "competition_name": competition_name,
                        "reference_date": selected_date.isoformat(),
                        "source_payload": source_payload,
                    },
                    source_summary_hash=stable_hash(
                        {
                            "competition_slug": competition_slug,
                            "content_type": str(ContentType.FEATURED_MATCH_PREVIEW),
                            "content_key": content_key,
                            "source_payload": source_payload,
                        }
                    ),
                    scheduled_at=self._scheduled_at(match),
                    status=ContentCandidateStatus.DRAFT,
                )
            )
        return candidates

    def build_bracket_drafts(
        self,
        competition_slug: str,
        *,
        reference_date: date | None = None,
    ) -> list[ContentCandidateDraft]:
        selected_date = self._reference_date(reference_date)
        matches = self._bracket_matches(competition_slug, reference_date=selected_date)
        if not matches:
            return []
        competition_name = self._competition_name(competition_slug)
        source_payload = self._bracket_source_payload(
            competition_slug,
            matches,
            reference_date=selected_date,
        )
        content_key = f"playoff_bracket:{competition_slug}:{stable_hash(source_payload)[:16]}"
        return [
            ContentCandidateDraft(
                competition_slug=competition_slug,
                content_type=ContentType.PLAYOFF_BRACKET,
                priority=93,
                text_draft=self._bracket_text(competition_name, source_payload),
                payload_json={
                    "content_key": content_key,
                    "template_name": "playoff_bracket_v1",
                    "competition_name": competition_name,
                    "reference_date": selected_date.isoformat(),
                    "media": {"kind": "playoff_bracket"},
                    "source_payload": source_payload,
                },
                source_summary_hash=stable_hash(
                    {
                        "competition_slug": competition_slug,
                        "content_type": str(ContentType.PLAYOFF_BRACKET),
                        "content_key": content_key,
                        "source_payload": source_payload,
                    }
                ),
                scheduled_at=self._next_scheduled_at(matches),
                status=ContentCandidateStatus.DRAFT,
            )
        ]

    def store_candidates(self, candidates: list[ContentCandidateDraft]) -> IngestStats:
        formatted_candidates = EditorialFormatterService(self.session, settings=self.settings).apply_to_drafts(
            candidates
        )
        stats = IngestStats(found=len(formatted_candidates))
        for candidate in formatted_candidates:
            _, inserted, updated = self.repository.upsert(candidate.model_dump(mode="python"))
            stats.inserted += int(inserted)
            stats.updated += int(updated)
        return stats

    def _source_payload(
        self,
        competition_slug: str,
        match: CompetitionMatchView,
        *,
        matches: list[CompetitionMatchView],
        reference_date: date,
    ) -> dict[str, Any]:
        definition = self.catalog.get(competition_slug)
        playoff_type = definition.playoff_type if definition is not None else None
        phase_label = self._playoff_phase_label(playoff_type)
        return {
            "editorial_phase": "playoffs",
            "primary_tag": "playoff_clash",
            "playoff_type": playoff_type,
            "parent_competition": definition.parent_competition if definition is not None else None,
            "reference_date": reference_date.isoformat(),
            "matches": [row.model_dump(mode="json") for row in matches],
            "featured_match": match.model_dump(mode="json"),
            "teams": [match.home_team, match.away_team],
            "editorial_hooks": [
                f"{phase_label}: {match.home_team} y {match.away_team} se cruzan en una eliminatoria sin tabla."
            ],
        }

    def _bracket_source_payload(
        self,
        competition_slug: str,
        matches: list[CompetitionMatchView],
        *,
        reference_date: date,
    ) -> dict[str, Any]:
        definition = self.catalog.get(competition_slug)
        finished_count = sum(1 for match in matches if match.status == "finished")
        pending_count = sum(1 for match in matches if match.status != "finished")
        bracket_rounds = self._bracket_rounds(matches)
        teams = sorted(
            {
                team
                for match in matches
                for team in (match.home_team, match.away_team)
                if team
            }
        )
        return {
            "editorial_phase": "playoffs",
            "summary_kind": "playoff_bracket",
            "primary_tag": "playoff_bracket",
            "playoff_type": definition.playoff_type if definition is not None else None,
            "parent_competition": definition.parent_competition if definition is not None else None,
            "reference_date": reference_date.isoformat(),
            "finished_matches_count": finished_count,
            "pending_matches_count": pending_count,
            "total_matches_count": len(matches),
            "bracket_rounds": bracket_rounds,
            "matches": [match.model_dump(mode="json") for match in matches],
            "teams": teams,
        }

    def _preview_text(
        self,
        competition_name: str,
        match: CompetitionMatchView,
        source_payload: dict[str, Any],
    ) -> str:
        date_part = match.match_date.isoformat() if match.match_date is not None else "fecha pendiente"
        time_part = match.match_time.strftime("%H:%M") if match.match_time is not None else "hora pendiente"
        phase_label = self._playoff_phase_label(str(source_payload.get("playoff_type") or ""))
        return (
            f"PREVIA | {competition_name}\n\n"
            f"{match.home_team} vs {match.away_team}, {date_part} {time_part}. "
            f"{phase_label} con foco balear y margen minimo."
        )

    def _bracket_text(self, competition_name: str, source_payload: dict[str, Any]) -> str:
        total = int(source_payload.get("total_matches_count") or 0)
        finished = int(source_payload.get("finished_matches_count") or 0)
        pending = int(source_payload.get("pending_matches_count") or 0)
        next_match = self._next_match_label(source_payload)
        text = f"Bracket actualizado de {competition_name}: {finished}/{total} partidos cerrados"
        if pending:
            text += f" y {pending} pendientes"
        if next_match:
            text += f". Proximo foco: {next_match}"
        return text + "."

    def _playoff_phase_label(self, playoff_type: str | None) -> str:
        if playoff_type == "permanencia":
            return "Playoff de permanencia"
        if playoff_type == "ascenso":
            return "Playoff de ascenso"
        return "Playoff"

    def _content_key(self, competition_slug: str, match: CompetitionMatchView, reference_date: date) -> str:
        match_key = match.source_url or f"{match.home_team}:{match.away_team}:{match.match_date}"
        return f"playoff_featured_match_preview:{competition_slug}:{stable_hash(match_key)[:12]}:{reference_date.isoformat()}"

    def _bracket_matches(
        self,
        competition_slug: str,
        *,
        reference_date: date,
    ) -> list[CompetitionMatchView]:
        finished = self.queries.finished_matches(
            competition_slug,
            limit=None,
            relevant_only=False,
            reference_date=None,
        )
        upcoming = self.queries.upcoming_matches(
            competition_slug,
            limit=None,
            relevant_only=False,
            reference_date=None,
        )
        rows = [*finished, *upcoming]
        return sorted(
            rows,
            key=lambda match: (
                match.match_date or date.max,
                match.match_time or datetime.min.time(),
                match.home_team,
                match.away_team,
            ),
        )

    def _bracket_rounds(self, matches: list[CompetitionMatchView]) -> list[dict[str, Any]]:
        rounds: dict[str, list[CompetitionMatchView]] = {}
        for match in matches:
            label = match.round_name or (match.match_date.strftime("%d/%m") if match.match_date else "Fecha pendiente")
            rounds.setdefault(label, []).append(match)
        return [
            {
                "label": label,
                "matches": [self._bracket_match_payload(match) for match in rows],
            }
            for label, rows in rounds.items()
        ]

    def _bracket_match_payload(self, match: CompetitionMatchView) -> dict[str, Any]:
        score = None
        if match.home_score is not None and match.away_score is not None:
            score = f"{match.home_score}-{match.away_score}"
        return {
            "round_name": match.round_name,
            "match_date": match.match_date.isoformat() if match.match_date is not None else None,
            "match_time": match.match_time.strftime("%H:%M") if match.match_time is not None else None,
            "home_team": match.home_team,
            "away_team": match.away_team,
            "home_score": match.home_score,
            "away_score": match.away_score,
            "score": score,
            "status": match.status,
        }

    def _next_match_label(self, source_payload: dict[str, Any]) -> str | None:
        matches = [
            match
            for match in source_payload.get("matches") or []
            if isinstance(match, dict) and match.get("status") != "finished"
        ]
        if not matches:
            return None
        match = matches[0]
        return f"{match.get('home_team')} vs {match.get('away_team')}"

    def _next_scheduled_at(self, matches: list[CompetitionMatchView]) -> datetime | None:
        scheduled = [match for match in matches if match.status != "finished" and match.match_date is not None]
        if not scheduled:
            return None
        return self._scheduled_at(scheduled[0])

    def _scheduled_at(self, match: CompetitionMatchView) -> datetime | None:
        if match.match_date is None:
            return None
        match_time = match.match_time or datetime.min.time()
        return datetime.combine(match.match_date, match_time, tzinfo=ZoneInfo(self.settings.timezone))

    def _competition_name(self, competition_slug: str) -> str:
        definition = self.catalog.get(competition_slug)
        if definition is not None and definition.editorial_name:
            return definition.editorial_name
        competition = self.session.scalar(select(Competition).where(Competition.code == competition_slug))
        if competition is None:
            raise ConfigurationError(f"Competicion desconocida o no sembrada: {competition_slug}")
        return competition.name

    def _reference_date(self, reference_date: date | None) -> date:
        if reference_date is not None:
            return reference_date
        return datetime.now(ZoneInfo(self.settings.timezone)).date()
