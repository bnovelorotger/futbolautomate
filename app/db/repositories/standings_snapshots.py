from __future__ import annotations

from sqlalchemy import select

from app.db.models import StandingSnapshot
from app.db.repositories.base import BaseRepository


class StandingSnapshotRepository(BaseRepository[StandingSnapshot]):
    def get_existing(self, payload: dict) -> StandingSnapshot | None:
        return self.session.scalar(
            select(StandingSnapshot).where(
                StandingSnapshot.source_name == payload["source_name"],
                StandingSnapshot.competition_id == payload["competition_id"],
                StandingSnapshot.season == payload.get("season"),
                StandingSnapshot.group_name == payload.get("group_name"),
                StandingSnapshot.team_raw == payload["team_raw"],
                StandingSnapshot.snapshot_timestamp == payload["snapshot_timestamp"],
            )
        )

    def insert(self, payload: dict) -> tuple[StandingSnapshot, bool]:
        existing = self.get_existing(payload)
        if existing is not None:
            return existing, False
        item = StandingSnapshot(**payload)
        self.session.add(item)
        self.session.flush()
        return item, True
