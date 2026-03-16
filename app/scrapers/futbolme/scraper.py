from __future__ import annotations

from app.core.enums import SourceName
from app.schemas.common import FetchArtifact, ScrapeContext
from app.scrapers.base import BaseScraper
from app.scrapers.futbolme.client import FutbolmeClient
from app.scrapers.futbolme.parser import FutbolmeParser


class FutbolmeScraper(BaseScraper):
    source_name = SourceName.FUTBOLME

    def __init__(self, settings=None) -> None:
        super().__init__(settings=settings)
        self.client = FutbolmeClient(self.settings)
        self.parser = FutbolmeParser()

    def fetch(self, context: ScrapeContext) -> list[FetchArtifact]:
        return [self.client.get(self.resolve_target_url(context))]

    def parse_matches(self, artifacts: list[FetchArtifact], context: ScrapeContext):
        return self.parser.parse_matches(
            artifacts[0].content,
            artifacts[0].final_url,
            competition_code=context.competition_code,
        )

    def parse_standings(self, artifacts: list[FetchArtifact], context: ScrapeContext):
        return self.parser.parse_standings(
            artifacts[0].content,
            artifacts[0].final_url,
            competition_code=context.competition_code,
        )
