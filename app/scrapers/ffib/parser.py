from __future__ import annotations

from bs4 import BeautifulSoup

from app.core.enums import NewsType, SourceName
from app.core.exceptions import SelectorDriftError
from app.schemas.news import NewsRecord
from app.utils.time import utcnow
from app.utils.urls import absolutize


def _text(node) -> str:
    return node.get_text(" ", strip=True)


class FFIBParser:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def parse_news(self, html: str, source_url: str) -> list[NewsRecord]:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("article.news-item, div.news-card, div.row.news-row")
        if not cards:
            raise SelectorDriftError("No se encontraron noticias FFIB")

        items: list[NewsRecord] = []
        for card in cards:
            title_node = card.select_one(".news-title, h2, h3")
            link_node = card.select_one("a[href]")
            summary_node = card.select_one(".news-summary, .excerpt, p")
            subtitle_node = card.select_one(".news-subtitle, .subtitle")
            category_node = card.select_one(".news-category, .category")
            date_node = card.select_one(".news-date, time, .date")
            if not title_node or not link_node:
                continue
            items.append(
                NewsRecord(
                    source_name=SourceName.FFIB,
                    source_url=absolutize(self.base_url, link_node.get("href")) or source_url,
                    title=_text(title_node),
                    subtitle=_text(subtitle_node) if subtitle_node else None,
                    summary=_text(summary_node) if summary_node else None,
                    raw_category=_text(category_node) if category_node else None,
                    scraped_at=utcnow(),
                    news_type=NewsType.OTHER,
                    raw_payload={"published_at_raw": _text(date_node) if date_node else None},
                )
            )
        if not items:
            raise SelectorDriftError("No se pudieron construir noticias FFIB")
        return items
