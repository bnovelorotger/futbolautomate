from __future__ import annotations

from sqlalchemy import select

from app.db.models import Match
from app.db.repositories.base import BaseRepository


class MatchRepository(BaseRepository[Match]):
    def _ancillary_state_changed(self, existing: Match, payload: dict) -> bool:
        return any(
            getattr(existing, key) != payload.get(key)
            for key in ("has_lineups", "has_scorers", "extra_data")
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

        for key, value in payload.items():
            setattr(existing, key, value)
        self.session.flush()
        return existing, False, True

