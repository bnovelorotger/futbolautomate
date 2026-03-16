from __future__ import annotations

from sqlalchemy import select

from app.db.models import ScraperRun
from app.db.repositories.base import BaseRepository


class ScraperRunRepository(BaseRepository[ScraperRun]):
    def create(self, **payload) -> ScraperRun:
        run = ScraperRun(**payload)
        self.session.add(run)
        self.session.flush()
        return run

    def get(self, run_id: int) -> ScraperRun | None:
        return self.session.scalar(select(ScraperRun).where(ScraperRun.id == run_id))

    def update(self, run: ScraperRun, **payload) -> ScraperRun:
        for key, value in payload.items():
            setattr(run, key, value)
        self.session.flush()
        return run
