from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.core.enums import MatchEventType, MatchStatus, SourceName
from app.core.exceptions import SelectorDriftError
from app.schemas.match import MatchRecord
from app.schemas.match_event import MatchEventRecord
from app.schemas.standing import StandingRecord
from app.scrapers.futbolme import selectors
from app.utils.time import utcnow

_SEASON_PATTERN = re.compile(r"Temporada\s+(\d{4}-\d{2})", re.IGNORECASE)
_ROUND_PATTERN = re.compile(r"(Jornada\s+\d+)", re.IGNORECASE)
_SCORE_PATTERN = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
_HALFTIME_SCORE_PATTERN = re.compile(r"(\d+)\s*-\s*(\d+)")
_TIME_PATTERN = re.compile(r"^\s*\d{1,2}:\d{2}\s*$")
_MATCH_ID_PATTERN = re.compile(r"/partido/[^/]+/(\d+)")
_MINUTE_PATTERN = re.compile(r"^\s*(\d+)(?:\+(\d+))?\s*$")


@dataclass(slots=True)
class FutbolmePageMetadata:
    competition_name: str | None
    season: str | None


def _text(node: Tag | None) -> str:
    if node is None:
        return ""
    return node.get_text(" ", strip=True)


def _team_text(node: Tag | None) -> str:
    if node is None:
        return ""
    preferred = node.select_one(".d-none.d-sm-inline-block, .d-none.d-sm-block")
    if preferred is not None and _text(preferred):
        return _text(preferred)
    compact = node.select_one(".d-inline-block.d-sm-none, .d-block.d-sm-none")
    if compact is not None and _text(compact):
        return _text(compact)
    return _text(node)


def _strip_duplicate_halves(value: str) -> str:
    cleaned = " ".join(value.split())
    parts = cleaned.split()
    if len(parts) >= 2 and len(parts) % 2 == 0:
        midpoint = len(parts) // 2
        if parts[:midpoint] == parts[midpoint:]:
            return " ".join(parts[:midpoint])
    return cleaned


def _absolute_url(source_url: str, href: str | None) -> str:
    if not href:
        return source_url
    return urljoin(source_url, href)


def _slugify_team_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    lowered = ascii_value.lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered)
    return lowered.strip("-")


def build_detail_url(home_team: str, away_team: str, external_id: str) -> str:
    home_slug = _slugify_team_name(home_team)
    away_slug = _slugify_team_name(away_team)
    return f"https://futbolme.com/resultados-directo/partido/{home_slug}-{away_slug}/{external_id}"


def _extract_match_id(match_card: Tag) -> str | None:
    detail_link = match_card.select_one(selectors.MATCH_DETAIL_LINK_SELECTOR)
    if detail_link and detail_link.get("href"):
        match = _MATCH_ID_PATTERN.search(detail_link["href"])
        if match:
            return match.group(1)

    onclick_target = match_card.find(attrs={"onclick": re.compile(r"mostrarColor\(")})
    if onclick_target:
        onclick = onclick_target.get("onclick", "")
        match = re.search(r"mostrarColor\((\d+)\)", onclick)
        if match:
            return match.group(1)
    return None


def _match_source_url(page_url: str, detail_href: str | None, external_id: str | None) -> str:
    if detail_href:
        return _absolute_url(page_url, detail_href)
    if external_id:
        return f"{page_url}#match-{external_id}"
    return page_url


def _parse_minute_value(value: str | None) -> tuple[int | None, int | None]:
    if not value:
        return None, None
    match = _MINUTE_PATTERN.match(value)
    if match is None:
        return None, None
    minute = int(match.group(1))
    minute_extra = int(match.group(2)) if match.group(2) is not None else None
    return minute, minute_extra


def _parse_halftime_score(soup: BeautifulSoup) -> tuple[int | None, int | None]:
    """Extract half-time score from a match detail page.

    Looks for the ".marcadorDescanso" element whose text contains a "X-Y" pattern
    (e.g. "Descanso 1-0" or "1-0"). Returns (None, None) when the element is absent
    or contains no parseable score — safe for matches without HT data.
    """
    node = soup.select_one(selectors.MATCH_HALFTIME_SCORE_SELECTOR)
    if node is None:
        return None, None
    text = _text(node)
    match = _HALFTIME_SCORE_PATTERN.search(text)
    if match is None:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _parse_page_metadata(soup: BeautifulSoup) -> FutbolmePageMetadata:
    header = soup.select_one(selectors.TOURNAMENT_HEADER_SELECTOR)
    competition_name = _text(header.select_one("h1")) if header else None
    title = _text(soup.title)
    season_match = _SEASON_PATTERN.search(title)
    return FutbolmePageMetadata(
        competition_name=competition_name or None,
        season=season_match.group(1) if season_match else None,
    )


def _parse_round_heading(match_card: Tag) -> tuple[str | None, str | None]:
    heading = match_card.find_previous("div", class_="contenedorTitularTorneoCalendario")
    heading_text = _text(heading)
    if not heading_text:
        return None, None
    if " - " in heading_text:
        round_name, match_date_raw = heading_text.split(" - ", maxsplit=1)
        return round_name.strip(), match_date_raw.strip()
    round_match = _ROUND_PATTERN.search(heading_text)
    if round_match:
        return round_match.group(1), heading_text
    return None, heading_text


def _parse_match_status_and_result(match_card: Tag) -> tuple[MatchStatus, str, int | None, int | None, str | None]:
    score_text = _text(match_card.select_one(selectors.MATCH_SCORE_SELECTOR))
    time_text = _text(match_card.select_one(selectors.MATCH_TIME_SELECTOR))
    planned_time_text = _text(match_card.select_one(selectors.MATCH_PLANNED_TIME_SELECTOR))

    match = _SCORE_PATTERN.match(score_text)
    if match:
        return MatchStatus.FINISHED, "Finalizado", int(match.group(1)), int(match.group(2)), planned_time_text or None

    effective_time = None
    if _TIME_PATTERN.match(time_text):
        effective_time = time_text
    elif _TIME_PATTERN.match(score_text):
        effective_time = score_text
    elif _TIME_PATTERN.match(planned_time_text):
        effective_time = planned_time_text

    if effective_time:
        return MatchStatus.SCHEDULED, "Programado", None, None, effective_time

    return MatchStatus.SCHEDULED, "Programado", None, None, None


class FutbolmeParser:
    def parse_matches(
        self,
        html: str,
        source_url: str,
        competition_code: str | None = None,
    ) -> list[MatchRecord]:
        soup = BeautifulSoup(html, "html.parser")
        container = soup.select_one(selectors.CENTRAL_CONTENT_SELECTOR) or soup
        metadata = _parse_page_metadata(soup)
        cards = container.select(selectors.MATCH_CARD_SELECTOR)
        records: list[MatchRecord] = []

        for match_card in cards:
            home_node = match_card.select_one(selectors.MATCH_HOME_SELECTOR)
            away_node = match_card.select_one(selectors.MATCH_AWAY_SELECTOR)
            if home_node is None or away_node is None:
                continue

            home_team = _strip_duplicate_halves(_team_text(home_node))
            away_team = _strip_duplicate_halves(_team_text(away_node))
            round_name, match_date_raw = _parse_round_heading(match_card)
            status, status_raw, home_score, away_score, match_time_raw = _parse_match_status_and_result(match_card)
            detail_link = match_card.select_one(selectors.MATCH_DETAIL_LINK_SELECTOR)
            external_id = _extract_match_id(match_card)
            team_links = match_card.select("a[href*='/resultados-directo/equipo/']")
            detail_href = detail_link.get("href") if detail_link else None
            detail_url = (
                _absolute_url(source_url, detail_href)
                if detail_href
                else build_detail_url(home_team, away_team, external_id)
                if external_id
                else None
            )

            records.append(
                MatchRecord(
                    source_name=SourceName.FUTBOLME,
                    source_url=_match_source_url(source_url, detail_href, external_id),
                    competition_code=competition_code,
                    competition_name=metadata.competition_name,
                    season=metadata.season,
                    round_name=round_name,
                    external_id=external_id,
                    match_date_raw=match_date_raw,
                    match_time_raw=match_time_raw,
                    home_team=home_team,
                    away_team=away_team,
                    home_score=home_score,
                    away_score=away_score,
                    status_raw=status_raw,
                    status=status,
                    venue=None,
                    scraped_at=utcnow(),
                    raw_payload={
                        "page_url": source_url,
                        "detail_url": detail_url,
                        "home_team_url": _absolute_url(source_url, team_links[0].get("href"))
                        if len(team_links) >= 1
                        else None,
                        "away_team_url": _absolute_url(source_url, team_links[1].get("href"))
                        if len(team_links) >= 2
                        else None,
                    },
                )
            )

        if not records:
            raise SelectorDriftError("No se encontraron partidos en Futbolme")
        return records

    def parse_standings(
        self,
        html: str,
        source_url: str,
        competition_code: str | None = None,
    ) -> list[StandingRecord]:
        soup = BeautifulSoup(html, "html.parser")
        container = soup.select_one(selectors.CENTRAL_CONTENT_SELECTOR) or soup
        metadata = _parse_page_metadata(soup)
        table = container.select_one(selectors.STANDINGS_TABLE_SELECTOR)
        if table is None:
            raise SelectorDriftError("No se encontro clasificacion en Futbolme")

        records: list[StandingRecord] = []
        for row in table.select("tr"):
            cells = row.find_all("td")
            if len(cells) < 10:
                continue
            position_text = _text(cells[0]).rstrip(".")
            position = int(position_text) if position_text.isdigit() else len(records) + 1

            team_anchor = cells[1].find("a")
            team_name = _strip_duplicate_halves(_team_text(team_anchor or cells[1]))
            team_url = _absolute_url(source_url, team_anchor.get("href") if team_anchor else None)

            records.append(
                StandingRecord(
                    source_name=SourceName.FUTBOLME,
                    source_url=source_url,
                    competition_code=competition_code,
                    competition_name=metadata.competition_name,
                    season=metadata.season,
                    position=position,
                    team_name=team_name,
                    points=int(_text(cells[2])),
                    played=int(_text(cells[3])),
                    wins=int(_text(cells[4])),
                    draws=int(_text(cells[5])),
                    losses=int(_text(cells[6])),
                    goals_for=int(_text(cells[7])),
                    goals_against=int(_text(cells[8])),
                    goal_difference=int(_text(cells[9])),
                    scraped_at=utcnow(),
                    raw_payload={"team_url": team_url},
                )
            )

        if not records:
            raise SelectorDriftError("No se encontro clasificacion en Futbolme")
        return records

    def parse_halftime_score(self, html: str) -> tuple[int | None, int | None]:
        """Return (halftime_home_score, halftime_away_score) from a match detail page.

        Returns (None, None) when the page contains no half-time score — this is
        expected for scheduled matches, live matches, and amateur games where the
        data source does not record interval scores.
        """
        soup = BeautifulSoup(html, "html.parser")
        return _parse_halftime_score(soup)

    def parse_match_events(
        self,
        html: str,
        source_url: str,
    ) -> list[MatchEventRecord]:
        soup = BeautifulSoup(html, "html.parser")
        tables = soup.select(selectors.MATCH_EVENT_TABLE_SELECTOR)
        records: list[MatchEventRecord] = []
        seen_keys: set[str] = set()
        sort_order = 0

        for table in tables:
            current_period: str | None = None
            for row in table.select("tr"):
                heading = row.select_one(selectors.MATCH_EVENT_PERIOD_HEADING_SELECTOR)
                if heading is not None:
                    current_period = _text(heading) or current_period
                    continue
                if row.select_one(selectors.MATCH_EVENT_GOAL_ICON_SELECTOR) is None:
                    continue

                cells = row.find_all("td")
                if len(cells) < 2:
                    continue
                team_side = "home" if _text(cells[0]) else "away" if _text(cells[1]) else None
                event_cell = cells[0] if team_side == "home" else cells[1] if team_side == "away" else None
                if team_side is None or event_cell is None:
                    continue

                minute_raw = _text(event_cell.select_one(selectors.MATCH_EVENT_MINUTE_SELECTOR))
                minute, minute_extra = _parse_minute_value(minute_raw)
                player_link = event_cell.select_one(selectors.MATCH_EVENT_PLAYER_LINK_SELECTOR)
                player_raw = _text(player_link) or None
                player_source_url = _absolute_url(source_url, player_link.get("href")) if player_link else None
                source_event_key = (
                    f"{current_period or 'unknown'}:{team_side}:{minute_raw or '-'}:{player_raw or '-'}:"
                    f"{player_source_url or '-'}"
                )
                if source_event_key in seen_keys:
                    continue
                seen_keys.add(source_event_key)
                sort_order += 1
                records.append(
                    MatchEventRecord(
                        team_side=team_side,
                        event_type=MatchEventType.GOAL,
                        period=current_period,
                        minute_raw=minute_raw or None,
                        minute=minute,
                        minute_extra=minute_extra,
                        player_raw=player_raw,
                        player_source_url=player_source_url,
                        sort_order=sort_order,
                        source_event_key=source_event_key,
                        raw_payload={
                            "source_url": source_url,
                            "team_side": team_side,
                            "period": current_period,
                        },
                    )
                )
        return records
