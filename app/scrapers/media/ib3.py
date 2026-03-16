from __future__ import annotations

from bs4 import BeautifulSoup

from app.core.catalog import load_source_catalog
from app.core.enums import NewsType, SourceName, TargetType
from app.schemas.common import FetchArtifact, ScrapeContext
from app.schemas.news import NewsRecord
from app.scrapers.base import BaseScraper
from app.scrapers.http import HTTPClient
from app.utils.time import utcnow
from app.utils.urls import absolutize


class IB3Scraper(BaseScraper):
    source_name = SourceName.IB3
    DEFAULT_URL = "https://ib3.org/esports"

    def __init__(self, settings=None) -> None:
        super().__init__(settings=settings)
        source = load_source_catalog()[self.source_name]
        self.client = HTTPClient(self.source_name, source.base_url, self.settings, source.headers)

    def default_url_for_target(self, target: TargetType) -> str | None:
        return self.DEFAULT_URL if target == TargetType.NEWS else None

    def fetch(self, context: ScrapeContext) -> list[FetchArtifact]:
        return [self.client.get(self.resolve_target_url(context))]

    def parse_news(self, artifacts: list[FetchArtifact], context: ScrapeContext):
        soup = BeautifulSoup(artifacts[0].content, "html.parser")
        items: list[NewsRecord] = []
        for article in soup.select("article, .news-item"):
            link = article.select_one("a[href]")
            title = article.select_one("h2, h3")
            if not link or not title:
                continue
            items.append(
                NewsRecord(
                    source_name=self.source_name,
                    source_url=absolutize(self.source_definition.base_url, link.get("href")) or "",
                    title=title.get_text(" ", strip=True),
                    summary=article.select_one("p").get_text(" ", strip=True)
                    if article.select_one("p")
                    else None,
                    scraped_at=utcnow(),
                    news_type=NewsType.OTHER,
                )
            )
        return items
