from __future__ import annotations

from app.core.catalog import load_competition_catalog, load_team_alias_catalog
from app.core.enums import MatchStatus, NewsType
from app.normalizers.text import normalize_token
from app.schemas.match import MatchRecord
from app.schemas.news import NewsRecord


NEWS_KEYWORDS = {
    NewsType.PREVIEW: ("previa", "horario", "donde ver"),
    NewsType.CHRONICLE: ("cronica", "cronica del partido", "resumen"),
    NewsType.TRANSFER: ("fichaje", "renueva", "firma por"),
    NewsType.SANCTION: ("sancion", "expediente", "suspendido"),
    NewsType.OFFICIAL_STATEMENT: ("comunicat oficial", "comunicado oficial"),
    NewsType.RESULTS: ("resultado", "resultados", "gana", "empata", "pierde"),
    NewsType.STANDINGS: ("clasificacion",),
    NewsType.INJURY: ("lesion", "baja", "parte medico"),
    NewsType.INSTITUTIONAL: ("ffib", "fundacio", "fundacion", "asamblea", "institucional"),
}


def validate_match_record(record: MatchRecord) -> MatchRecord:
    if record.status == MatchStatus.FINISHED and (
        record.home_score is None or record.away_score is None
    ):
        raise ValueError(f"Match finished without score: {record.source_url}")
    return record


def infer_news_type(record: NewsRecord) -> NewsType:
    if record.news_type != NewsType.OTHER:
        return record.news_type

    haystack = normalize_token(
        " ".join(
            filter(
                None,
                [record.title, record.subtitle, record.raw_category],
            )
        )
    )
    for news_type, keywords in NEWS_KEYWORDS.items():
        if any(normalize_token(keyword) in haystack for keyword in keywords):
            return news_type
    return NewsType.OTHER


def detect_clubs(text: str) -> list[str]:
    aliases = load_team_alias_catalog().aliases
    normalized = normalize_token(text)
    detected = {canonical for alias, canonical in aliases.items() if alias in normalized}
    return sorted(detected)


def detect_competition(text: str) -> str | None:
    normalized = normalize_token(text)
    for competition in load_competition_catalog().values():
        names = [competition.name, *competition.aliases]
        if any(normalize_token(name) in normalized for name in names):
            return competition.name
    return None
