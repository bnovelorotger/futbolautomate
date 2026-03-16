from __future__ import annotations

from bs4 import BeautifulSoup

from app.core.enums import MatchStatus, SourceName
from app.core.exceptions import SelectorDriftError
from app.normalizers.statuses import normalize_match_status
from app.schemas.match import MatchRecord
from app.schemas.standing import StandingRecord
from app.utils.time import utcnow


def _text(node) -> str:
    return node.get_text(" ", strip=True)


def _parse_score(value: str) -> tuple[int | None, int | None]:
    parts = [segment.strip() for segment in value.replace(":", "-").split("-") if segment.strip()]
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


class SoccerwayParser:
    def parse_matches(self, html: str, source_url: str, competition_code: str | None = None) -> list[MatchRecord]:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.matches tbody tr, table[data-role='matches'] tbody tr, tr.match-row")
        if not rows:
            raise SelectorDriftError("No se encontraron partidos en Soccerway")

        records: list[MatchRecord] = []
        for row in rows:
            home = row.select_one(".team-home, td.home, .home-team")
            away = row.select_one(".team-away, td.away, .away-team")
            date_cell = row.select_one(".date, td.date")
            time_cell = row.select_one(".time, td.time")
            score_cell = row.select_one(".score, td.score, .full-score")
            status_cell = row.select_one(".status, td.status")
            round_cell = row.select_one(".round, td.round")
            venue_cell = row.select_one(".venue, td.venue")
            link = row.select_one("a[href]")
            if not home or not away:
                continue
            home_score, away_score = _parse_score(_text(score_cell)) if score_cell else (None, None)
            status_raw = _text(status_cell) if status_cell else None
            status = normalize_match_status(status_raw)
            if status == MatchStatus.UNKNOWN and home_score is not None and away_score is not None:
                status = MatchStatus.FINISHED
            records.append(
                MatchRecord(
                    source_name=SourceName.SOCCERWAY,
                    source_url=link["href"] if link and link["href"].startswith("http") else source_url,
                    competition_code=competition_code,
                    round_name=_text(round_cell) if round_cell else None,
                    match_date_raw=_text(date_cell) if date_cell else None,
                    match_time_raw=_text(time_cell) if time_cell else None,
                    home_team=_text(home),
                    away_team=_text(away),
                    home_score=home_score,
                    away_score=away_score,
                    status_raw=status_raw,
                    status=status,
                    venue=_text(venue_cell) if venue_cell else None,
                    scraped_at=utcnow(),
                )
            )
        return records

    def parse_standings(
        self,
        html: str,
        source_url: str,
        competition_code: str | None = None,
    ) -> list[StandingRecord]:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table.standings tbody tr, table.leaguetable tbody tr, tr.standing-row")
        if not rows:
            raise SelectorDriftError("No se encontro clasificacion en Soccerway")

        records: list[StandingRecord] = []
        for row in rows:
            cells = row.find_all("td")
            team_cell = row.select_one(".team, td.team, .team-name")
            if len(cells) < 10 or not team_cell:
                continue
            team_td = team_cell if team_cell.name == "td" else team_cell.find_parent("td")
            team_index = cells.index(team_td)
            records.append(
                StandingRecord(
                    source_name=SourceName.SOCCERWAY,
                    source_url=source_url,
                    competition_code=competition_code,
                    position=int(_text(cells[0])),
                    team_name=_text(team_cell),
                    played=int(_text(cells[team_index + 1])),
                    wins=int(_text(cells[team_index + 2])),
                    draws=int(_text(cells[team_index + 3])),
                    losses=int(_text(cells[team_index + 4])),
                    goals_for=int(_text(cells[team_index + 5])),
                    goals_against=int(_text(cells[team_index + 6])),
                    goal_difference=int(_text(cells[team_index + 7])),
                    points=int(_text(cells[team_index + 8])),
                    scraped_at=utcnow(),
                )
            )
        return records
