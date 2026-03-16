from __future__ import annotations

from app.core.enums import SourceName, TargetType
from app.schemas.common import FetchArtifact, ScrapeContext
from app.scrapers.base import BaseScraper
from app.scrapers.ffib.client import FFIBClient
from app.scrapers.ffib.parser import FFIBParser


class FFIBScraper(BaseScraper):
    source_name = SourceName.FFIB
    NEWS_URL = "https://www.ffib.es/Fed/NNws_LstNews?cod_primaria=1000097&cod_secundaria="

    def __init__(self, settings=None) -> None:
        super().__init__(settings=settings)
        self.client = FFIBClient(self.settings)
        self.parser = FFIBParser(self.source_definition.base_url)

    def default_url_for_target(self, target: TargetType) -> str | None:
        if target == TargetType.NEWS:
            return self.NEWS_URL
        return None

    def fetch(self, context: ScrapeContext) -> list[FetchArtifact]:
        return [self.client.get(self.resolve_target_url(context))]

    def parse_news(self, artifacts: list[FetchArtifact], context: ScrapeContext):
        return self.parser.parse_news(artifacts[0].content, artifacts[0].final_url)
