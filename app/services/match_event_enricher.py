from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Match
from app.db.repositories.match_events import MatchEventRepository
from app.schemas.match_event import MatchEventEnrichmentMatchView, MatchEventEnrichmentResult
from app.scrapers.futbolme.client import FutbolmeClient
from app.scrapers.futbolme.parser import FutbolmeParser, build_detail_url


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
            row = self.enrich_match(match.id, dry_run=dry_run)
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

        if not dry_run:
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
            self.repository.replace_for_match(match.id, payloads)
            extra_data = dict(match.extra_data or {})
            extra_data["detail_url"] = detail_url
            match.extra_data = extra_data
            match.has_scorers = True
            self.session.add(match)
            self.session.flush()

        return MatchEventEnrichmentMatchView(
            match_id=match.id,
            source_url=match.source_url,
            detail_url=detail_url,
            home_team=match.home_team_raw,
            away_team=match.away_team_raw,
            events_found=len(events),
            persisted=not dry_run,
            has_scorers=not dry_run or match.has_scorers,
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
            query = query.join(Match.competition).where(Match.competition.has(code=competition_slug))
        query = query.order_by(Match.match_date.desc().nullslast(), Match.id.desc()).limit(limit)
        return self.session.execute(query).scalars().all()

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
