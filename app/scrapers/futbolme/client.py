from __future__ import annotations

from app.core.catalog import load_source_catalog
from app.core.config import Settings
from app.core.enums import SourceName
from app.scrapers.http import HTTPClient


class FutbolmeClient(HTTPClient):
    def __init__(self, settings: Settings):
        source = load_source_catalog()[SourceName.FUTBOLME]
        super().__init__(
            source_name=SourceName.FUTBOLME,
            base_url=source.base_url,
            settings=settings,
            headers=source.headers,
        )

