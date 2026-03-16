from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.reporting import EditorialNewsView
from app.services.editorial_summary import prioritize_editorial_news


def _news(
    news_id: int,
    title: str,
    score: int,
    *,
    clubs: list[str] | None = None,
    competition: str | None = None,
) -> EditorialNewsView:
    return EditorialNewsView(
        news_id=news_id,
        source_name="test",
        source_url=f"https://example.com/{news_id}",
        title=title,
        published_at=datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc),
        summary=None,
        raw_category="Deportes",
        sport_detected="football",
        is_football=True,
        is_balearic_related=True,
        clubs_detected=clubs or [],
        competition_detected=competition,
        editorial_relevance_score=score,
    )


def test_prioritize_editorial_news_prefers_competition_then_club_then_context() -> None:
    rows = [
        _news(1, "General balear context", 25, clubs=["Real Mallorca"]),
        _news(2, "Club overlap", 20, clubs=["CE Andratx"]),
        _news(3, "Competition direct", 18, competition="Division Honor Mallorca"),
    ]

    prioritized = prioritize_editorial_news(
        news_items=rows,
        competition_names={"division honor mallorca"},
        team_names={"ce andratx b", "cd ferriolense"},
        limit=3,
    )

    assert [item.selection_reason for item in prioritized] == [
        "competition_detected",
        "club_overlap",
        "general_context",
    ]
    assert prioritized[0].title == "Competition direct"
    assert prioritized[1].title == "Club overlap"
    assert prioritized[2].title == "General balear context"


def test_prioritize_editorial_news_deduplicates_by_source_url() -> None:
    repeated = _news(1, "Repeated", 21, clubs=["CE Andratx B"])
    duplicated = repeated.model_copy(update={"news_id": 2})
    prioritized = prioritize_editorial_news(
        news_items=[repeated, duplicated],
        competition_names={"division honor mallorca"},
        team_names={"ce andratx b"},
        limit=5,
    )

    assert len(prioritized) == 1
    assert prioritized[0].source_url == "https://example.com/1"
