from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import News, NewsEnrichment
from app.normalizers.text import normalize_token
from app.schemas.reporting import EditorialNewsView, EditorialSummaryView


class NewsEditorialQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _base_rows(self):
        return self.session.execute(
            select(
                News.id.label("news_id"),
                News.source_name,
                News.source_url,
                News.title,
                News.published_at,
                News.summary,
                News.raw_category,
                NewsEnrichment.sport_detected,
                NewsEnrichment.is_football,
                NewsEnrichment.is_balearic_related,
                NewsEnrichment.clubs_detected,
                NewsEnrichment.competition_detected,
                NewsEnrichment.editorial_relevance_score,
            )
            .join(NewsEnrichment, NewsEnrichment.news_id == News.id)
            .order_by(
                NewsEnrichment.editorial_relevance_score.desc(),
                News.published_at.desc().nullslast(),
                News.id.desc(),
            )
        ).all()

    def _views(self, rows: Iterable) -> list[EditorialNewsView]:
        return [EditorialNewsView.model_validate(dict(row._mapping)) for row in rows]

    def relevant_balearic_football(self, limit: int = 20) -> list[EditorialNewsView]:
        rows = [
            row
            for row in self._base_rows()
            if row.is_football and row.is_balearic_related
        ][:limit]
        return self._views(rows)

    def football_non_balearic(self, limit: int = 20) -> list[EditorialNewsView]:
        rows = [
            row
            for row in self._base_rows()
            if row.is_football and not row.is_balearic_related
        ][:limit]
        return self._views(rows)

    def by_club(self, club: str, limit: int = 20) -> list[EditorialNewsView]:
        target = normalize_token(club)
        rows = []
        for row in self._base_rows():
            clubs = row.clubs_detected or []
            if any(normalize_token(item) == target for item in clubs):
                rows.append(row)
            if len(rows) >= limit:
                break
        return self._views(rows)

    def by_competition(self, competition: str, limit: int = 20) -> list[EditorialNewsView]:
        target = normalize_token(competition)
        rows = [
            row
            for row in self._base_rows()
            if row.competition_detected and normalize_token(row.competition_detected) == target
        ][:limit]
        return self._views(rows)

    def top_scores(self, limit: int = 20) -> list[EditorialNewsView]:
        return self._views(self._base_rows()[:limit])

    def summary_counts(self) -> EditorialSummaryView:
        rows = self._base_rows()
        relevant = sum(1 for row in rows if row.is_football and row.is_balearic_related)
        football_non_balearic = sum(1 for row in rows if row.is_football and not row.is_balearic_related)
        other = sum(1 for row in rows if not row.is_football)
        return EditorialSummaryView(
            relevant_balearic_football=relevant,
            football_non_balearic=football_non_balearic,
            other_sports_or_unknown=other,
        )
