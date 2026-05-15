from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.db.models import ScraperRun
from app.db.repositories.base import BaseRepository
from app.utils.time import utcnow


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

    def get_zero_record_runs(self, days: int = 7) -> list[ScraperRun]:
        """Returns successful runs with records_found == 0 in last N days."""
        cutoff = utcnow() - timedelta(days=days)
        stmt = (
            select(ScraperRun)
            .where(
                ScraperRun.status == "success",
                ScraperRun.records_found == 0,
                ScraperRun.started_at >= cutoff,
            )
            .order_by(ScraperRun.started_at.desc())
        )
        return list(self.session.scalars(stmt))
