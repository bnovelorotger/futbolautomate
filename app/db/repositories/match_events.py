from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select

from app.db.models import MatchEvent
from app.db.repositories.base import BaseRepository


class MatchEventRepository(BaseRepository[MatchEvent]):
    def replace_for_match(self, match_id: int, payloads: Sequence[dict]) -> tuple[int, int]:
        existing = self.session.scalars(
            select(MatchEvent).where(MatchEvent.match_id == match_id)
        ).all()
        deleted = len(existing)
        self.session.execute(delete(MatchEvent).where(MatchEvent.match_id == match_id))

        inserted = 0
        for payload in payloads:
            self.session.add(MatchEvent(**payload))
            inserted += 1
        self.session.flush()
        return inserted, deleted
