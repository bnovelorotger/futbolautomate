from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import ContentType
from app.db.models import ContentCandidate
from app.services.competition_queries import CompetitionQueryService
from app.utils.time import utcnow

_ROUND_PATTERN = re.compile(r"(?:j(?:ornada)?\.?\s*)0*(\d+)", re.IGNORECASE)
_PAST_ORIENTED_TYPES = {
    ContentType.MATCH_RESULT,
    ContentType.RESULTS_ROUNDUP,
    ContentType.STANDINGS,
    ContentType.STANDINGS_ROUNDUP,
}
_FUTURE_ORIENTED_TYPES = {
    ContentType.PREVIEW,
    ContentType.FEATURED_MATCH_PREVIEW,
    ContentType.FEATURED_MATCH_EVENT,
}
_WEDNESDAY_TYPES = {
    ContentType.RANKING,
    ContentType.STANDINGS_EVENT,
    ContentType.FORM_RANKING,
    ContentType.FORM_EVENT,
    ContentType.STAT_NARRATIVE,
    ContentType.METRIC_NARRATIVE,
    ContentType.VIRAL_STORY,
}


@dataclass(slots=True)
class CompetitionMatchdayWindow:
    current_round: str | None
    current_match_date: date | None
    next_round: str | None
    next_match_date: date | None


class EditorialCandidateWindowService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.queries = CompetitionQueryService(session)
        self._window_cache: dict[tuple[str, date], CompetitionMatchdayWindow] = {}

    def matches_release_window(
        self,
        candidate: ContentCandidate,
        *,
        reference_date: date | None = None,
    ) -> bool:
        selected_date = reference_date or self._today()
        content_type = ContentType(candidate.content_type)
        if content_type in _PAST_ORIENTED_TYPES:
            return self._matches_past_window(candidate, reference_date=selected_date)
        if content_type in _FUTURE_ORIENTED_TYPES:
            return self._matches_future_window(candidate, reference_date=selected_date)
        return self._matches_reference_date(candidate, reference_date=selected_date)

    def logical_day_index(
        self,
        candidate: ContentCandidate,
        *,
        reference_date: date | None = None,
    ) -> int:
        selected_date = reference_date or self._today()
        content_type = ContentType(candidate.content_type)
        if content_type in _FUTURE_ORIENTED_TYPES:
            return 2
        if content_type in _WEDNESDAY_TYPES:
            return 1
        if content_type in _PAST_ORIENTED_TYPES:
            match_date = self.candidate_match_date(candidate, reference_date=selected_date)
            if match_date is not None and match_date.weekday() == 6:
                return 3
            return 0
        return 1

    def candidate_match_date(
        self,
        candidate: ContentCandidate,
        *,
        reference_date: date | None = None,
    ) -> date | None:
        content_type = ContentType(candidate.content_type)
        dates = self._candidate_match_dates(candidate)
        if dates:
            if content_type in _FUTURE_ORIENTED_TYPES:
                return min(dates)
            return max(dates)
        candidate_reference_date = self._candidate_reference_date(candidate)
        if candidate_reference_date is not None:
            return candidate_reference_date
        return self._candidate_local_date(candidate)

    def competition_window(
        self,
        competition_slug: str,
        *,
        reference_date: date | None = None,
    ) -> CompetitionMatchdayWindow:
        selected_date = reference_date or self._today()
        cache_key = (competition_slug, selected_date)
        cached = self._window_cache.get(cache_key)
        if cached is not None:
            return cached

        past_reference_date = selected_date - timedelta(days=1)
        finished_matches = self.queries.finished_matches(
            competition_slug,
            limit=200,
            relevant_only=True,
            reference_date=past_reference_date,
        )
        current_group = self._group_matches(finished_matches, newest=True)

        upcoming_matches = self.queries.upcoming_matches(
            competition_slug,
            limit=200,
            relevant_only=True,
            reference_date=selected_date,
        )
        next_group = self._group_matches(upcoming_matches, newest=False)

        window = CompetitionMatchdayWindow(
            current_round=self._group_round(current_group),
            current_match_date=max((match.match_date for match in current_group if match.match_date is not None), default=None),
            next_round=self._group_round(next_group),
            next_match_date=min((match.match_date for match in next_group if match.match_date is not None), default=None),
        )
        self._window_cache[cache_key] = window
        return window

    def _matches_past_window(
        self,
        candidate: ContentCandidate,
        *,
        reference_date: date,
    ) -> bool:
        context = self.competition_window(candidate.competition_slug, reference_date=reference_date)
        candidate_round = self._candidate_round(candidate)
        match_dates = self._candidate_match_dates(candidate)
        if match_dates:
            latest_date = max(match_dates)
            if latest_date >= reference_date:
                return False
            if context.current_match_date is not None and latest_date != context.current_match_date:
                if candidate_round is None or context.current_round is None or candidate_round != context.current_round:
                    return False
        elif candidate_round and context.current_round and candidate_round != context.current_round:
            return False
        return self._matches_reference_date(candidate, reference_date=reference_date)

    def _matches_future_window(
        self,
        candidate: ContentCandidate,
        *,
        reference_date: date,
    ) -> bool:
        context = self.competition_window(candidate.competition_slug, reference_date=reference_date)
        candidate_round = self._candidate_round(candidate)
        match_dates = self._candidate_match_dates(candidate)
        if match_dates:
            earliest_date = min(match_dates)
            if earliest_date < reference_date:
                return False
            if context.next_match_date is not None and earliest_date != context.next_match_date:
                if candidate_round is None or context.next_round is None or candidate_round != context.next_round:
                    return False
        elif candidate_round and context.next_round and candidate_round != context.next_round:
            return False
        return self._matches_reference_date(candidate, reference_date=reference_date)

    def _matches_reference_date(
        self,
        candidate: ContentCandidate,
        *,
        reference_date: date,
    ) -> bool:
        candidate_reference_date = self._candidate_reference_date(candidate)
        if candidate_reference_date is not None:
            return candidate_reference_date == reference_date
        return self._candidate_local_date(candidate) == reference_date

    def _group_matches(self, matches: list[Any], *, newest: bool) -> list[Any]:
        if not matches:
            return []
        anchor = matches[0]
        anchor_round = self._normalized_round(anchor.round_name)
        if anchor_round is not None:
            return [match for match in matches if self._normalized_round(match.round_name) == anchor_round]
        anchor_date = anchor.match_date
        if anchor_date is not None:
            return [match for match in matches if match.match_date == anchor_date]
        return [anchor] if newest else [anchor]

    def _group_round(self, matches: list[Any]) -> str | None:
        for match in matches:
            normalized = self._normalized_round(getattr(match, "round_name", None))
            if normalized is not None:
                return normalized
        return None

    def _candidate_round(self, candidate: ContentCandidate) -> str | None:
        payload_json = candidate.payload_json or {}
        source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
        round_candidates = [
            source_payload.get("round_name"),
            source_payload.get("group_label"),
        ]
        featured_match = source_payload.get("featured_match")
        if isinstance(featured_match, dict):
            round_candidates.append(featured_match.get("round_name"))
        for match in source_payload.get("matches") or []:
            if isinstance(match, dict):
                round_candidates.append(match.get("round_name"))
        for value in round_candidates:
            normalized = self._normalized_round(value)
            if normalized is not None:
                return normalized
        return None

    def _candidate_match_dates(self, candidate: ContentCandidate) -> list[date]:
        payload_json = candidate.payload_json or {}
        source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
        raw_dates: list[Any] = []
        if isinstance(source_payload.get("match_date"), (str, date)):
            raw_dates.append(source_payload.get("match_date"))
        featured_match = source_payload.get("featured_match")
        if isinstance(featured_match, dict):
            raw_dates.append(featured_match.get("match_date"))
        for match in source_payload.get("matches") or []:
            if isinstance(match, dict):
                raw_dates.append(match.get("match_date"))
        dates = [parsed for parsed in (self._parse_date(value) for value in raw_dates) if parsed is not None]
        return sorted(set(dates))

    def _candidate_reference_date(self, candidate: ContentCandidate) -> date | None:
        payload_json = candidate.payload_json or {}
        if not isinstance(payload_json, dict):
            return None
        return self._parse_date(payload_json.get("reference_date"))

    def _candidate_local_date(self, candidate: ContentCandidate) -> date:
        timestamp = candidate.published_at or candidate.created_at or utcnow()
        timezone = ZoneInfo(self.settings.timezone)
        if timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone).date()
        return timestamp.astimezone(timezone).date()

    def _parse_date(self, value: Any) -> date | None:
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return None
        return None

    def _normalized_round(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        match = _ROUND_PATTERN.search(normalized)
        if match is not None:
            return f"J{int(match.group(1))}"
        if normalized.isdigit():
            return f"J{int(normalized)}"
        return None

    def _today(self) -> date:
        return datetime.now(ZoneInfo(self.settings.timezone)).date()
