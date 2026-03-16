from app.scrapers.soccerway.parser import SoccerwayParser
from tests.helpers import read_fixture


def test_soccerway_parser_extracts_matches() -> None:
    parser = SoccerwayParser()

    records = parser.parse_matches(
        read_fixture("soccerway_matches.html"),
        source_url="https://example.com/matches",
        competition_code="tercera_rfef_g11",
    )

    assert len(records) == 2
    assert records[0].home_team == "CE Andratx"
    assert records[0].home_score == 2
    assert records[1].status.value == "scheduled"


def test_soccerway_parser_extracts_standings() -> None:
    parser = SoccerwayParser()

    records = parser.parse_standings(
        read_fixture("soccerway_standings.html"),
        source_url="https://example.com/standings",
        competition_code="tercera_rfef_g11",
    )

    assert len(records) == 2
    assert records[0].team_name == "Poblense"
    assert records[0].points == 53
