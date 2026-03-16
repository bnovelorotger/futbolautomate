from __future__ import annotations

from app.core.enums import SourceName
from app.scrapers.base import BaseScraper
from app.scrapers.ffib.scraper import FFIBScraper
from app.scrapers.futbolme.scraper import FutbolmeScraper
from app.scrapers.media.diario_mallorca import DiarioMallorcaScraper
from app.scrapers.media.ib3 import IB3Scraper
from app.scrapers.media.ultima_hora import UltimaHoraScraper
from app.scrapers.soccerway.scraper import SoccerwayScraper


SCRAPER_REGISTRY: dict[SourceName, type[BaseScraper]] = {
    SourceName.SOCCERWAY: SoccerwayScraper,
    SourceName.FUTBOLME: FutbolmeScraper,
    SourceName.FFIB: FFIBScraper,
    SourceName.DIARIO_MALLORCA: DiarioMallorcaScraper,
    SourceName.ULTIMA_HORA: UltimaHoraScraper,
    SourceName.IB3: IB3Scraper,
}


def build_scraper(source_name: SourceName) -> BaseScraper:
    return SCRAPER_REGISTRY[source_name]()
