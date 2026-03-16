from __future__ import annotations

from sqlalchemy import select

from app.db.models import Competition
from app.db.repositories.base import BaseRepository


class CompetitionRepository(BaseRepository[Competition]):
    def get_by_code(self, code: str) -> Competition | None:
        return self.session.scalar(select(Competition).where(Competition.code == code))

    def get_by_normalized_name(self, normalized_name: str) -> Competition | None:
        return self.session.scalar(
            select(Competition).where(Competition.normalized_name == normalized_name)
        )

    def create_or_update(self, **payload) -> Competition:
        competition = self.get_by_code(payload["code"])
        if competition is None:
            competition = Competition(**payload)
            self.session.add(competition)
            self.session.flush()
            return competition

        for key, value in payload.items():
            setattr(competition, key, value)
        self.session.flush()
        return competition

