from __future__ import annotations

from sqlalchemy import select

from app.db.models import Standing
from app.db.repositories.base import BaseRepository


class StandingRepository(BaseRepository[Standing]):
    def get_existing(self, payload: dict) -> Standing | None:
        by_team_raw = self.session.scalar(
            select(Standing).where(
                Standing.source_name == payload["source_name"],
                Standing.competition_id == payload["competition_id"],
                Standing.season == payload.get("season"),
                Standing.group_name == payload.get("group_name"),
                Standing.team_raw == payload["team_raw"],
            )
        )
        if by_team_raw is not None:
            return by_team_raw

        team_id = payload.get("team_id")
        if team_id is not None:
            by_team_id = self.session.scalar(
                select(Standing).where(
                    Standing.source_name == payload["source_name"],
                    Standing.competition_id == payload["competition_id"],
                    Standing.season == payload.get("season"),
                    Standing.group_name == payload.get("group_name"),
                    Standing.team_id == team_id,
                )
            )
            if by_team_id is not None:
                return by_team_id

        return self.session.scalar(
            select(Standing).where(
                Standing.source_name == payload["source_name"],
                Standing.competition_id == payload["competition_id"],
                Standing.season == payload.get("season"),
                Standing.group_name == payload.get("group_name"),
                Standing.position == payload["position"],
            )
        )

    def upsert(self, payload: dict) -> tuple[Standing, bool, bool]:
        existing = self.get_existing(payload)
        if existing is None:
            item = Standing(**payload)
            self.session.add(item)
            self.session.flush()
            return item, True, False

        if existing.content_hash == payload["content_hash"]:
            return existing, False, False

        for key, value in payload.items():
            setattr(existing, key, value)
        self.session.flush()
        return existing, False, True
