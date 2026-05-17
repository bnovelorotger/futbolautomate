from app.scrapers.futbolme.parser import FutbolmeParser, build_detail_url
from tests.helpers import read_fixture


def test_futbolme_parser_extracts_matches() -> None:
    parser = FutbolmeParser()

    records = parser.parse_matches(
        read_fixture("futbolme_matches.html"),
        source_url="https://example.com/futbolme/matches",
        competition_code="division_honor_mallorca",
    )

    assert len(records) == 3
    assert records[0].home_team == "Sta Catalina Atl"
    assert records[0].away_team == "UD Alaro"
    assert records[0].round_name == "Jornada 24"
    assert records[0].match_date_raw == "sabado, 07 de marzo de 2026"
    assert records[0].status.value == "finished"
    assert records[0].home_score == 1
    assert records[0].away_score == 1
    assert records[1].match_time_raw == "16:00"
    assert records[1].status.value == "scheduled"
    assert records[2].match_time_raw is None
    assert records[2].source_url == "https://example.com/resultados-directo/partido/platges-calvia-b-cd-ferriolense/1302054"


def test_futbolme_parser_extracts_standings() -> None:
    parser = FutbolmeParser()

    records = parser.parse_standings(
        read_fixture("futbolme_standings.html"),
        source_url="https://example.com/futbolme/standings",
        competition_code="division_honor_mallorca",
    )

    assert len(records) == 2
    assert records[0].team_name == "CE Andratx B"
    assert records[0].points == 54
    assert records[1].goal_difference == 24


def test_futbolme_parser_prefers_desktop_team_name_when_mobile_and_desktop_are_both_present() -> None:
    parser = FutbolmeParser()
    html = """
    <html>
      <head><title>Jornada - TERCERA FEDERACION - Grupo 11 - Temporada 2025-26</title></head>
      <body>
        <div id="contenedorCentral">
          <table id="latabla">
            <tr>
              <td>1.</td>
              <td>
                <a href="/resultados-directo/equipo/rcd-mallorca-b/220&amp;modelo=Calendario">
                  <strong itemprop="name">
                    <span class="d-inline-block d-sm-none">Mallorca B</span>
                    <span class="d-none d-sm-inline-block">RCD Mallorca B</span>
                  </strong>
                </a>
              </td>
              <td>63</td>
              <td>25</td>
              <td>20</td>
              <td>3</td>
              <td>2</td>
              <td>73</td>
              <td>16</td>
              <td>57</td>
            </tr>
          </table>
        </div>
      </body>
    </html>
    """

    records = parser.parse_standings(
        html,
        source_url="https://example.com/futbolme/standings",
        competition_code="tercera_rfef_g11",
    )

    assert len(records) == 1
    assert records[0].team_name == "RCD Mallorca B"


def test_futbolme_parser_extracts_positions_when_badge_repeats_rank_value() -> None:
    parser = FutbolmeParser()
    html = """
    <html>
      <head><title>Clasificacion - SEGUNDA FEDERACION - Grupo 3 - Temporada 2025-26</title></head>
      <body>
        <div id="contenedorCentral">
          <table id="latabla">
            <tr>
              <td><span class="badge badge-primary">2-1</span></td>
              <td><a href="/equipo/ue-sant-andreu">UE Sant Andreu</a></td>
              <td>49</td>
              <td>25</td>
              <td>14</td>
              <td>7</td>
              <td>4</td>
              <td>37</td>
              <td>20</td>
              <td>17</td>
            </tr>
            <tr>
              <td><span class="badge badge-primary">1-2</span></td>
              <td><a href="/equipo/cd-castellon-b">CD Castellon B</a></td>
              <td>33</td>
              <td>25</td>
              <td>8</td>
              <td>9</td>
              <td>8</td>
              <td>29</td>
              <td>27</td>
              <td>2</td>
            </tr>
          </table>
        </div>
      </body>
    </html>
    """

    records = parser.parse_standings(
        html,
        source_url="https://example.com/futbolme/standings",
        competition_code="segunda_rfef_g3_baleares",
    )

    assert len(records) == 2
    assert records[0].position == 1
    assert records[0].team_name == "UE Sant Andreu"
    assert records[1].position == 2
    assert records[1].team_name == "CD Castellon B"


def test_futbolme_parser_prefers_desktop_team_name_in_match_cards() -> None:
    parser = FutbolmeParser()
    html = """
    <html>
      <head><title>Calendario - TERCERA FEDERACION - Grupo 11 - Temporada 2025-26</title></head>
      <body>
        <div id="contenedorCentral">
          <div class="contenedorTitularTorneoCalendario">Jornada 26 - sabado, 14 de marzo de 2026</div>
          <div class="cajaPartido">
            <div class="equipoPartidoLocal">
              <p><span itemprop="name"><span class="d-block d-sm-none">CE Santanyi</span><span class="d-none d-sm-block">CE Santanyi</span></span></p>
            </div>
            <div class="resultadoPartido">17:15</div>
            <div class="equipoPartidoVisitante">
              <p><span itemprop="name"><span class="d-block d-sm-none">Mallorca B</span><span class="d-none d-sm-block">RCD Mallorca B</span></span></p>
            </div>
          </div>
        </div>
      </body>
    </html>
    """

    records = parser.parse_matches(
        html,
        source_url="https://example.com/futbolme/matches",
        competition_code="tercera_rfef_g11",
    )

    assert len(records) == 1
    assert records[0].home_team == "CE Santanyi"
    assert records[0].away_team == "RCD Mallorca B"


def test_build_detail_url_reconstructs_futbolme_match_detail_url() -> None:
    assert (
        build_detail_url("CE Constancia", "Inter Ibiza CD", "1258230")
        == "https://futbolme.com/resultados-directo/partido/ce-constancia-inter-ibiza-cd/1258230"
    )
    assert (
        build_detail_url("Pena Deportiva", "Platges Calvia", "999")
        == "https://futbolme.com/resultados-directo/partido/pena-deportiva-platges-calvia/999"
    )


def test_futbolme_parser_extracts_goal_events_for_home_and_away_teams() -> None:
    parser = FutbolmeParser()

    records = parser.parse_match_events(
        read_fixture("futbolme_match_detail_goals_home_away.html"),
        source_url="https://futbolme.com/resultados-directo/partido/cd-manacor-rcd-mallorca-b/1258227",
    )

    assert len(records) == 2
    assert records[0].team_side == "home"
    assert records[0].period == "Primer Tiempo"
    assert records[0].minute_raw == "45+1"
    assert records[0].minute == 45
    assert records[0].minute_extra == 1
    assert records[0].player_raw == "Nando"
    assert records[1].team_side == "away"
    assert records[1].period == "Segundo Tiempo"
    assert records[1].minute_raw == "54"
    assert records[1].player_raw == "Nico"
    assert records[1].player_source_url == "https://futbolme.com/jugador.php?id=60223"


def test_futbolme_parser_extracts_multiple_goal_events_with_periods() -> None:
    parser = FutbolmeParser()

    records = parser.parse_match_events(
        read_fixture("futbolme_match_detail_multiple_goals.html"),
        source_url="https://futbolme.com/resultados-directo/partido/ce-constancia-inter-ibiza-cd/1258230",
    )

    assert len(records) == 3
    assert [record.period for record in records] == [
        "Primer Tiempo",
        "Segundo Tiempo",
        "Segundo Tiempo",
    ]
    assert [record.player_raw for record in records] == ["Gerard", "Socias", "Llabres"]


def test_futbolme_parser_returns_empty_event_list_for_scoreless_match() -> None:
    parser = FutbolmeParser()

    records = parser.parse_match_events(
        read_fixture("futbolme_match_detail_nil_nil.html"),
        source_url="https://futbolme.com/resultados-directo/partido/ce-constancia-inter-ibiza-cd/1258230",
    )

    assert records == []


def test_futbolme_parser_extracts_halftime_score_when_present() -> None:
    parser = FutbolmeParser()

    ht_home, ht_away = parser.parse_halftime_score(
        read_fixture("futbolme_match_detail_with_halftime.html"),
    )

    assert ht_home == 1
    assert ht_away == 0


def test_futbolme_parser_returns_none_halftime_scores_when_element_absent() -> None:
    parser = FutbolmeParser()

    ht_home, ht_away = parser.parse_halftime_score(
        read_fixture("futbolme_match_detail_nil_nil.html"),
    )

    assert ht_home is None
    assert ht_away is None


def test_futbolme_parser_returns_none_halftime_scores_for_match_without_ht_data() -> None:
    parser = FutbolmeParser()
    html = """
    <html>
      <head><title>Match without HT</title></head>
      <body>
        <div id="contenedorCentral">
          <div class="marcadorDescanso">Descanso</div>
        </div>
      </body>
    </html>
    """

    ht_home, ht_away = parser.parse_halftime_score(html)

    assert ht_home is None
    assert ht_away is None
