from __future__ import annotations

from app.core.catalog import load_source_catalog
from app.core.config import Settings
from app.core.enums import SourceName
from app.scrapers.playwright_client import PlaywrightClient


class SoccerwayClient(PlaywrightClient):
    def __init__(self, settings: Settings):
        load_source_catalog()[SourceName.SOCCERWAY]
        super().__init__(source_name=SourceName.SOCCERWAY, settings=settings)

