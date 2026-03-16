from __future__ import annotations

from sqlalchemy import select

from app.db.models import Team
from app.db.repositories.base import BaseRepository


class TeamRepository(BaseRepository[Team]):
    def get_by_normalized_name(self, normalized_name: str) -> Team | None:
        return self.session.scalar(select(Team).where(Team.normalized_name == normalized_name))

    def get_or_create(self, **payload) -> tuple[Team, bool]:
        team = self.get_by_normalized_name(payload["normalized_name"])
        if team is None:
            team = Team(**payload)
            self.session.add(team)
            self.session.flush()
            return team, True

        updated = False
        for key, value in payload.items():
            if value is not None and getattr(team, key) != value:
                setattr(team, key, value)
                updated = True
        self.session.flush()
        return team, updated

