from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from pydantic import BaseModel

from app.core.catalog import load_competition_catalog, load_source_catalog
from app.core.config import Settings, get_settings
from app.core.enums import SourceName, TargetType
from app.core.exceptions import ConfigurationError, UnsupportedTargetError
from app.schemas.common import FetchArtifact, ScrapeContext, ScrapeResult


class BaseScraper(ABC):
    source_name: SourceName

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.source_definition = load_source_catalog()[self.source_name]
        self.logger = logging.getLogger(self.__class__.__name__)

    def ensure_supported(self, target: TargetType) -> None:
        if target not in self.source_definition.supports:
            raise UnsupportedTargetError(f"{self.source_name} no soporta target={target}")

    def get_competition_mapping(self, competition_code: str | None, target: TargetType) -> str | None:
        if not competition_code:
            return None
        competition = load_competition_catalog().get(competition_code)
        if competition is None:
            raise ConfigurationError(f"Competición desconocida: {competition_code}")
        source_mapping = competition.sources.get(self.source_name)
        if source_mapping is None:
            raise ConfigurationError(
                f"La competición {competition_code} no está configurada para {self.source_name}"
            )
        if not source_mapping.enabled:
            raise ConfigurationError(
                f"La competición {competition_code} tiene {self.source_name} deshabilitada para scraping automático"
            )
        return source_mapping.urls.get(target)

    def resolve_target_url(self, context: ScrapeContext) -> str:
        if context.override_url:
            return context.override_url
        resolved = self.get_competition_mapping(context.competition_code, context.target)
        if resolved:
            return resolved
        fallback = self.default_url_for_target(context.target)
        if fallback:
            return fallback
        raise ConfigurationError(
            f"No hay URL configurada para {self.source_name}/{context.target}"
        )

    def default_url_for_target(self, target: TargetType) -> str | None:
        return None

    @abstractmethod
    def fetch(self, context: ScrapeContext) -> list[FetchArtifact]:
        raise NotImplementedError

    def parse_matches(self, artifacts: list[FetchArtifact], context: ScrapeContext) -> list[BaseModel]:
        raise UnsupportedTargetError(f"{self.source_name} no implementa parse_matches")

    def parse_standings(self, artifacts: list[FetchArtifact], context: ScrapeContext) -> list[BaseModel]:
        raise UnsupportedTargetError(f"{self.source_name} no implementa parse_standings")

    def parse_news(self, artifacts: list[FetchArtifact], context: ScrapeContext) -> list[BaseModel]:
        raise UnsupportedTargetError(f"{self.source_name} no implementa parse_news")

    def scrape(self, context: ScrapeContext) -> ScrapeResult:
        self.ensure_supported(context.target)
        artifacts = self.fetch(context)
        parser = {
            TargetType.MATCHES: self.parse_matches,
            TargetType.STANDINGS: self.parse_standings,
            TargetType.NEWS: self.parse_news,
        }[context.target]
        return ScrapeResult(
            scraper_name=self.__class__.__name__,
            source_name=self.source_name,
            target=context.target,
            competition_code=context.competition_code,
            records=parser(artifacts, context),
        )
