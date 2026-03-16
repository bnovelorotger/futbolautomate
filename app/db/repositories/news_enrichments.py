from __future__ import annotations

from sqlalchemy import select

from app.db.models import NewsEnrichment
from app.db.repositories.base import BaseRepository


class NewsEnrichmentRepository(BaseRepository[NewsEnrichment]):
    def get_by_news_id(self, news_id: int) -> NewsEnrichment | None:
        return self.session.scalar(select(NewsEnrichment).where(NewsEnrichment.news_id == news_id))

    def upsert(self, payload: dict) -> tuple[NewsEnrichment, bool, bool]:
        existing = self.get_by_news_id(payload["news_id"])
        if existing is None:
            item = NewsEnrichment(**payload)
            self.session.add(item)
            self.session.flush()
            return item, True, False

        comparable_keys = [key for key in payload.keys() if key != "analyzed_at"]
        changed = any(getattr(existing, key) != payload[key] for key in comparable_keys)
        if not changed:
            return existing, False, False

        for key, value in payload.items():
            setattr(existing, key, value)
        self.session.flush()
        return existing, False, changed
