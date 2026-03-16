from __future__ import annotations

from sqlalchemy import select

from app.db.models import News
from app.db.repositories.base import BaseRepository


class NewsRepository(BaseRepository[News]):
    def get_existing(self, payload: dict) -> News | None:
        existing = self.session.scalar(
            select(News).where(
                News.source_name == payload["source_name"],
                News.source_url == payload["source_url"],
            )
        )
        if existing is not None:
            return existing
        return self.session.scalar(
            select(News).where(
                News.source_name == payload["source_name"],
                News.content_hash == payload["content_hash"],
            )
        )

    def upsert(self, payload: dict) -> tuple[News, bool, bool]:
        existing = self.get_existing(payload)
        if existing is None:
            item = News(**payload)
            self.session.add(item)
            self.session.flush()
            return item, True, False

        if existing.content_hash == payload["content_hash"]:
            return existing, False, False

        for key, value in payload.items():
            setattr(existing, key, value)
        self.session.flush()
        return existing, False, True
