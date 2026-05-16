from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Match
from app.db.repositories.match_events import MatchEventRepository
from app.schemas.match_event import MatchEventEnrichmentMatchView, MatchEventEnrichmentResult
from app.scrapers.futbolme.client import FutbolmeClient
from app.scrapers.futbolme.parser import FutbolmeParser, build_detail_url
from app.utils.time import utcnow


RECENT_MATCH_WINDOW_DAYS = 21
RECENT_PRIORITY_SHARE = 0.75
RETRY_COOLDOWN_DAYS = 1


class MatchEventEnricherService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        parser: FutbolmeParser | None = None,
        fetch_html: Callable[[str], str] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.parser = parser or FutbolmeParser()
        self.repository = MatchEventRepository(session)
        self.fetch_html = fetch_html or self._fetch_html

    def enrich_pending(
        self,
        *,
        limit: int = 25,
        competition_slug: str | None = None,
        dry_run: bool = False,
    ) -> MatchEventEnrichmentResult:
        matches = self._pending_matches(limit=limit, competition_slug=competition_slug)
        rows: list[MatchEventEnrichmentMatchView] = []
        total_events_found = 0
        enriched_count = 0

        for match in matches:
            try:
                if dry_run:
                    row = self.enrich_match(match.id, dry_run=True)
                else:
                    with self.session.begin_nested():
                        row = self.enrich_match(match.id, dry_run=False)
            except Exception as exc:
                if dry_run:
                    row = self._build_result_row(
                        match,
                        detail_url=self._safe_detail_url(match),
                        events_found=0,
                        persisted=False,
                        has_scorers=match.has_scorers,
                    )
                else:
                    recovered_match = self.session.get(Match, match.id) or match
                    try:
                        with self.session.begin_nested():
                            self._record_attempt_error(recovered_match, exc)
                    except Exception:
                        recovered_match = self.session.get(Match, match.id) or match
                    row = self._build_result_row(
                        recovered_match,
                        detail_url=self._safe_detail_url(recovered_match),
                        events_found=0,
                        persisted=False,
                        has_scorers=recovered_match.has_scorers if recovered_match is not None else False,
                    )
            rows.append(row)
            total_events_found += row.events_found
            enriched_count += int(row.persisted)

        return MatchEventEnrichmentResult(
            checked_count=len(matches),
            enriched_count=enriched_count,
            total_events_found=total_events_found,
            rows=rows,
        )

    def enrich_match(
        self,
        match_id: int,
        *,
        dry_run: bool = False,
    ) -> MatchEventEnrichmentMatchView:
        match = self.session.get(Match, match_id)
        if match is None:
            raise ValueError(f"Match desconocido: {match_id}")

        detail_url = self._detail_url(match)
        html = self.fetch_html(detail_url)
        events = self.parser.parse_match_events(html, detail_url)
        expected_goal_events = self._expected_goal_events(match)
        existing_events = self.repository.list_for_match(match.id)
        existing_count = len(existing_events)
        completed = expected_goal_events == 0 or len(events) >= expected_goal_events
        should_persist_events = self._should_persist_events(
            expected_goal_events=expected_goal_events,
            events_found=len(events),
            existing_count=existing_count,
        )
        retained_existing = not should_persist_events and existing_count > len(events)

        if not dry_run:
            if should_persist_events:
                payloads = [
                    {
                        "match_id": match.id,
                        "team_id": match.home_team_id if event.team_side == "home" else match.away_team_id,
                        "team_side": event.team_side,
                        "event_type": str(event.event_type),
                        "period": event.period,
                        "minute_raw": event.minute_raw,
                        "minute": event.minute,
                        "minute_extra": event.minute_extra,
                        "player_raw": event.player_raw,
                        "player_source_url": event.player_source_url,
                        "sort_order": event.sort_order,
                        "source_event_key": event.source_event_key,
                        "raw_payload": event.raw_payload,
                    }
                    for event in events
                ]
                self.repository.sync_for_match(match.id, payloads)
            extra_data = self._merge_match_events_metadata(
                match,
                detail_url=detail_url,
                expected_goal_events=expected_goal_events,
                events_found=len(events),
                existing_count=existing_count,
                completed=completed,
                retained_existing=retained_existing,
                error_message=None,
            )
            match.extra_data = extra_data
            match.has_scorers = completed
            self.session.add(match)
            self.session.flush()

        return self._build_result_row(
            match,
            detail_url=detail_url,
            events_found=len(events),
            persisted=not dry_run,
            has_scorers=completed if not dry_run else match.has_scorers,
        )

    def _pending_matches(
        self,
        *,
        limit: int,
        competition_slug: str | None,
    ) -> list[Match]:
        query = select(Match).where(
            Match.source_name == "futbolme",
            Match.status == "finished",
            Match.external_id.is_not(None),
            Match.has_scorers.is_(False),
        )
        if competition_slug is not None:
            query = query.where(Match.competition.has(code=competition_slug))
        candidates = self.session.execute(
            query.order_by(Match.match_date.desc().nullslast(), Match.id.desc())
        ).scalars().all()
        return self._prioritize_pending_matches(candidates, limit=limit)

    def _detail_url(self, match: Match) -> str:
        extra_data = match.extra_data if isinstance(match.extra_data, dict) else {}
        detail_url = extra_data.get("detail_url")
        if isinstance(detail_url, str) and detail_url.strip():
            return detail_url.strip()
        if match.external_id is None:
            raise ValueError(f"El partido {match.id} no tiene external_id para reconstruir detail_url")
        return build_detail_url(
            match.home_team_raw,
            match.away_team_raw,
            match.external_id,
        )

    def _fetch_html(self, url: str) -> str:
        return FutbolmeClient(self.settings).get(url).content

    def _prioritize_pending_matches(self, matches: list[Match], *, limit: int) -> list[Match]:
        if not matches:
            return []

        today = utcnow().date()
        recent_cutoff = today - timedelta(days=RECENT_MATCH_WINDOW_DAYS)
        recent_matches: list[Match] = []
        historical_matches: list[Match] = []

        for match in matches:
            if not self._eligible_for_retry(match, reference_date=today):
                continue
            if match.match_date and match.match_date >= recent_cutoff:
                recent_matches.append(match)
            else:
                historical_matches.append(match)

        recent_matches.sort(key=self._recent_priority_key)
        historical_matches.sort(key=self._historical_priority_key)

        recent_quota = min(len(recent_matches), max(1, round(limit * RECENT_PRIORITY_SHARE)))
        if not historical_matches:
            recent_quota = min(len(recent_matches), limit)
        selected: list[Match] = recent_matches[:recent_quota]

        historical_quota = min(len(historical_matches), max(limit - len(selected), 0))
        selected.extend(historical_matches[:historical_quota])

        if len(selected) < limit:
            overflow = recent_matches[recent_quota:] + historical_matches[historical_quota:]
            selected.extend(overflow[: limit - len(selected)])
        return selected[:limit]

    def _eligible_for_retry(self, match: Match, *, reference_date: date) -> bool:
        metadata = self._match_events_metadata(match)
        attempted_at_raw = metadata.get("last_attempted_at")
        if not isinstance(attempted_at_raw, str) or not attempted_at_raw:
            return True
        attempted_at = self._parse_iso_date(attempted_at_raw)
        if attempted_at is None:
            return True
        last_status = metadata.get("status")
        if last_status not in {"error", "partial_retry", "pending_retry"}:
            return True
        return reference_date >= attempted_at + timedelta(days=RETRY_COOLDOWN_DAYS)

    def _recent_priority_key(self, match: Match) -> tuple[object, ...]:
        metadata = self._match_events_metadata(match)
        return (
            0 if self._expected_goal_events(match) > 0 else 1,
            0 if self._attempt_count(metadata) == 0 else 1,
            -(match.match_date.toordinal() if match.match_date else 0),
            -match.id,
        )

    def _historical_priority_key(self, match: Match) -> tuple[object, ...]:
        metadata = self._match_events_metadata(match)
        return (
            0 if self._attempt_count(metadata) == 0 else 1,
            0 if self._expected_goal_events(match) > 0 else 1,
            match.match_date.toordinal() if match.match_date else 0,
            match.id,
        )

    def _record_attempt_error(self, match: Match, error: Exception) -> None:
        existing_count = len(self.repository.list_for_match(match.id))
        extra_data = self._merge_match_events_metadata(
            match,
            detail_url=self._safe_detail_url(match),
            expected_goal_events=self._expected_goal_events(match),
            events_found=existing_count,
            existing_count=existing_count,
            completed=False,
            retained_existing=False,
            error_message=str(error),
        )
        match.extra_data = extra_data
        match.has_scorers = False
        self.session.add(match)
        self.session.flush()

    def _merge_match_events_metadata(
        self,
        match: Match,
        *,
        detail_url: str,
        expected_goal_events: int,
        events_found: int,
        existing_count: int,
        completed: bool,
        retained_existing: bool,
        error_message: str | None,
    ) -> dict:
        extra_data = dict(match.extra_data or {})
        metadata = dict(extra_data.get("match_events") or {})
        attempts = self._attempt_count(metadata) + 1

        if error_message:
            status = "error"
        elif completed and expected_goal_events == 0:
            status = "scoreless_complete"
        elif completed:
            status = "complete"
        elif events_found == 0:
            status = "pending_retry"
        else:
            status = "partial_retry"

        metadata.update(
            {
                "status": status,
                "expected_goal_events": expected_goal_events,
                "events_found": events_found,
                "stored_events_count": max(existing_count, events_found) if retained_existing else events_found,
                "attempt_count": attempts,
                "last_attempted_at": utcnow().date().isoformat(),
                "last_error": error_message,
            }
        )
        if retained_existing:
            metadata["retained_existing_events"] = True
        else:
            metadata.pop("retained_existing_events", None)
        if completed:
            metadata["last_completed_at"] = utcnow().date().isoformat()
        else:
            metadata.pop("last_completed_at", None)
        extra_data["detail_url"] = detail_url
        extra_data["match_events"] = metadata
        return extra_data

    def _match_events_metadata(self, match: Match) -> dict:
        extra_data = match.extra_data if isinstance(match.extra_data, dict) else {}
        metadata = extra_data.get("match_events")
        if isinstance(metadata, dict):
            return metadata
        return {}

    def _attempt_count(self, metadata: dict) -> int:
        attempt_count = metadata.get("attempt_count")
        return attempt_count if isinstance(attempt_count, int) and attempt_count >= 0 else 0

    def _expected_goal_events(self, match: Match) -> int:
        return max((match.home_score or 0) + (match.away_score or 0), 0)

    def _should_persist_events(
        self,
        *,
        expected_goal_events: int,
        events_found: int,
        existing_count: int,
    ) -> bool:
        if expected_goal_events == 0:
            return events_found == 0 or existing_count > 0
        if events_found == 0:
            return existing_count == 0
        if events_found >= expected_goal_events:
            return True
        return events_found >= existing_count

    def _build_result_row(
        self,
        match: Match,
        *,
        detail_url: str,
        events_found: int,
        persisted: bool,
        has_scorers: bool,
    ) -> MatchEventEnrichmentMatchView:
        return MatchEventEnrichmentMatchView(
            match_id=match.id,
            source_url=match.source_url,
            detail_url=detail_url,
            home_team=match.home_team_raw,
            away_team=match.away_team_raw,
            events_found=events_found,
            persisted=persisted,
            has_scorers=has_scorers,
        )

    def _safe_detail_url(self, match: Match) -> str:
        try:
            return self._detail_url(match)
        except Exception:
            return match.source_url

    def _parse_iso_date(self, value: str) -> date | None:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
