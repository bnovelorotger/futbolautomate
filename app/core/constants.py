from __future__ import annotations

from app.core.enums import SourceName, TargetType

DEFAULT_DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d %b %Y",
    "%d %B %Y",
)

DEFAULT_HEADERS = {
    "Accept-Language": "es-ES,es;q=0.9",
}

DAILY_PRIORITY_COMPETITIONS = (
    "tercera_rfef_g11",
    "division_honor_mallorca",
)

SOURCE_TARGETS: dict[SourceName, tuple[TargetType, ...]] = {
    SourceName.SOCCERWAY: (TargetType.MATCHES, TargetType.STANDINGS),
    SourceName.FUTBOLME: (TargetType.MATCHES, TargetType.STANDINGS),
    SourceName.FFIB: (TargetType.NEWS,),
    SourceName.DIARIO_MALLORCA: (TargetType.NEWS,),
    SourceName.ULTIMA_HORA: (TargetType.NEWS,),
    SourceName.IB3: (TargetType.NEWS,),
}
