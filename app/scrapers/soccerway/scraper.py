from __future__ import annotations

from app.core.enums import SourceName
from app.core.exceptions import FetchError
from app.schemas.common import FetchArtifact, ScrapeContext
from app.scrapers.base import BaseScraper
from app.scrapers.soccerway.client import SoccerwayClient
from app.scrapers.soccerway.parser import SoccerwayParser


class SoccerwayScraper(BaseScraper):
    source_name = SourceName.SOCCERWAY

    def __init__(self, settings=None) -> None:
        super().__init__(settings=settings)
        self.client = SoccerwayClient(self.settings)
        self.parser = SoccerwayParser()

    def fetch(self, context: ScrapeContext) -> list[FetchArtifact]:
        artifact = self.client.get(self.resolve_target_url(context))
        if artifact.final_url.rstrip("/") == self.source_definition.base_url.rstrip("/"):
            raise FetchError(
                "Soccerway redirigio la URL de competicion a la home. Revisa mapping o estrategia Playwright."
            )
        return [artifact]

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
