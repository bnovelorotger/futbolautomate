from __future__ import annotations

from sqlalchemy import select

from app.core.enums import MatchScorerStatus
from app.db.models import Match
from app.db.repositories.base import BaseRepository


class MatchRepository(BaseRepository[Match]):
    def _ancillary_state_changed(self, existing: Match, payload: dict) -> bool:
        prepared = self._preserve_scorer_enrichment(existing, dict(payload))
        return any(
            getattr(existing, key) != prepared.get(key)
            for key in (
                "has_lineups",
                "has_scorers",
                "scorer_status",
                "scorer_checked_at",
                "extra_data",
            )
        )

    def get_existing(self, payload: dict) -> Match | None:
        external_id = payload.get("external_id")
        if external_id:
            return self.session.scalar(
                select(Match).where(
                    Match.source_name == payload["source_name"],
                    Match.external_id == external_id,
                )
            )

        return self.session.scalar(
            select(Match).where(
                Match.source_name == payload["source_name"],
                Match.source_url == payload["source_url"],
            )
        )

    def upsert(self, payload: dict) -> tuple[Match, bool, bool]:
        existing = self.get_existing(payload)
        if existing is None:
            item = Match(**payload)
            self.session.add(item)
            self.session.flush()
            return item, True, False

        if existing.content_hash == payload["content_hash"] and not self._ancillary_state_changed(existing, payload):
            return existing, False, False

        payload = self._preserve_scorer_enrichment(existing, dict(payload))
        for key, value in payload.items():
            setattr(existing, key, value)
        self.session.flush()
        return existing, False, True

    def _preserve_scorer_enrichment(self, existing: Match, payload: dict) -> dict:
        incoming_has_scorers = bool(payload.get("has_scorers"))
        if existing.has_scorers and not incoming_has_scorers:
            payload["has_scorers"] = existing.has_scorers

        incoming_status = payload.get("scorer_status")
        if incoming_status in {None, str(MatchScorerStatus.PENDING)} and existing.scorer_status:
            payload["scorer_status"] = existing.scorer_status

        if payload.get("scorer_checked_at") is None and existing.scorer_checked_at is not None:
            payload["scorer_checked_at"] = existing.scorer_checked_at

        incoming_extra = dict(payload.get("extra_data") or {})
        existing_extra = existing.extra_data if isinstance(existing.extra_data, dict) else {}
        merged_extra = dict(existing_extra)
        merged_extra.update(incoming_extra)
        existing_match_events = existing_extra.get("match_events")
        if isinstance(existing_match_events, dict) and "match_events" not in merged_extra:
            merged_extra["match_events"] = existing_match_events
        payload["extra_data"] = merged_extra
        return payload
