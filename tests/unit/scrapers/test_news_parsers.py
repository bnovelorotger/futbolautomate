from app.core.enums import SourceName
from app.scrapers.ffib.parser import FFIBParser
from app.scrapers.media.rss import RSSParser
from tests.helpers import read_fixture


def test_ffib_parser_extracts_news_cards() -> None:
    parser = FFIBParser(base_url="https://www.ffib.es")

    records = parser.parse_news(read_fixture("ffib_news.html"), source_url="https://www.ffib.es/Fed/NNws_LstNews")

    assert len(records) == 2
    assert records[0].title == "La FFIB rep el Premi Ramon Llull"
    assert records[1].source_url.endswith("codigo=1008610")


def test_rss_parser_supports_rss_and_atom() -> None:
    parser = RSSParser()

    diario = parser.parse(read_fixture("diario_mallorca_rss.xml"), source_name=SourceName.DIARIO_MALLORCA)
    ultima = parser.parse(read_fixture("ultima_hora_atom.xml"), source_name=SourceName.ULTIMA_HORA)

    assert len(diario) == 2
    assert diario[0].title == "Atlético Baleares vuelve al liderato"
    assert diario[0].raw_category == "Deportes"
    assert diario[1].summary == "Previa del encuentro en Son Moix."

    assert len(ultima) == 2
    assert ultima[0].title.startswith("Horario y dónde ver")
    assert ultima[0].raw_category == "Deportes | Real Mallorca"
    assert ultima[1].summary == "Resumen previo a la jornada del Palma Futsal."
