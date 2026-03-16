from __future__ import annotations

from app.core.catalog import load_source_catalog
from app.core.enums import SourceName, TargetType
from app.schemas.common import FetchArtifact, ScrapeContext
from app.scrapers.base import BaseScraper
from app.scrapers.http import HTTPClient
from app.scrapers.media.rss import RSSParser


class UltimaHoraScraper(BaseScraper):
    source_name = SourceName.ULTIMA_HORA
    DEFAULT_FEED_URL = "https://www.ultimahora.es/deportes.rss"

    def __init__(self, settings=None) -> None:
        super().__init__(settings=settings)
        source = load_source_catalog()[self.source_name]
        self.client = HTTPClient(self.source_name, source.base_url, self.settings, source.headers)
        self.parser = RSSParser()

    def default_url_for_target(self, target: TargetType) -> str | None:
        return self.DEFAULT_FEED_URL if target == TargetType.NEWS else None

    def fetch(self, context: ScrapeContext) -> list[FetchArtifact]:
        return [self.client.get(self.resolve_target_url(context))]

    def parse_news(self, artifacts: list[FetchArtifact], context: ScrapeContext):
        return self.parser.parse(artifacts[0].content, self.source_name)
