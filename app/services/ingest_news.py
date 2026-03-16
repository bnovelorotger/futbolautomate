from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.repositories.news import NewsRepository
from app.schemas.common import IngestStats
from app.schemas.news import NewsRecord
from app.services.deduplication import news_content_hash
from app.services.validation import detect_clubs, detect_competition, infer_news_type


def ingest_news(session: Session, records: list[NewsRecord], dry_run: bool = False) -> IngestStats:
    stats = IngestStats(found=len(records))
    news_repo = NewsRepository(session)

    for record in records:
        if record.news_type.value == "other":
            record.news_type = infer_news_type(record)

        haystack = " ".join(filter(None, [record.title, record.subtitle, record.summary, record.body_text]))
        if not record.clubs_detected:
            record.clubs_detected = detect_clubs(haystack)
        if not record.competition_detected:
            record.competition_detected = detect_competition(haystack)

        payload = {
            "source_name": str(record.source_name),
            "source_url": record.source_url,
            "title": record.title,
            "subtitle": record.subtitle,
            "published_at": record.published_at,
            "summary": record.summary,
            "body_text": record.body_text,
            "news_type": str(record.news_type),
            "clubs_detected": record.clubs_detected,
            "competition_detected": record.competition_detected,
            "raw_category": record.raw_category,
            "scraped_at": record.scraped_at,
            "content_hash": news_content_hash(record),
        }
        if dry_run:
            continue
        _, inserted, updated = news_repo.upsert(payload)
        stats.inserted += int(inserted)
        stats.updated += int(updated)
    return stats
