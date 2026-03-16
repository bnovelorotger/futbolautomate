from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import SourceName
from app.db.models import News
from app.schemas.reporting import NewsView


class NewsQueryService:
    def __init__(self, session: Session, timezone_name: str | None = None) -> None:
        self.session = session
        self.timezone_name = timezone_name or get_settings().timezone

    def _base_query(self):
        return select(
            News.source_name,
            News.source_url,
            News.title,
            News.published_at,
            News.summary,
            News.raw_category,
            News.news_type,
            News.scraped_at,
        )

    def latest(self, limit: int = 10) -> list[NewsView]:
        rows = self.session.execute(
            self._base_query()
            .order_by(News.published_at.desc().nullslast(), News.scraped_at.desc(), News.id.desc())
            .limit(limit)
        ).all()
        return [NewsView.model_validate(dict(row._mapping)) for row in rows]

    def today(self, limit: int = 20, reference_date: date | None = None) -> list[NewsView]:
        madrid_tz = ZoneInfo(self.timezone_name)
        current_date = reference_date or datetime.now(madrid_tz).date()
        start_local = datetime.combine(current_date, time.min, tzinfo=madrid_tz)
        end_local = start_local + timedelta(days=1)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)

        rows = self.session.execute(
            self._base_query()
            .where(News.published_at.is_not(None), News.published_at >= start_utc, News.published_at < end_utc)
            .order_by(News.published_at.desc(), News.id.desc())
            .limit(limit)
        ).all()
        return [NewsView.model_validate(dict(row._mapping)) for row in rows]

    def by_source(self, source: SourceName, limit: int = 20) -> list[NewsView]:
        rows = self.session.execute(
            self._base_query()
            .where(News.source_name == str(source))
            .order_by(News.published_at.desc().nullslast(), News.scraped_at.desc(), News.id.desc())
            .limit(limit)
        ).all()
        return [NewsView.model_validate(dict(row._mapping)) for row in rows]

    def search_titles(self, text: str, limit: int = 20) -> list[NewsView]:
        pattern = f"%{text.strip().lower()}%"
        rows = self.session.execute(
            self._base_query()
            .where(func.lower(News.title).like(pattern))
            .order_by(News.published_at.desc().nullslast(), News.scraped_at.desc(), News.id.desc())
            .limit(limit)
        ).all()
        return [NewsView.model_validate(dict(row._mapping)) for row in rows]
