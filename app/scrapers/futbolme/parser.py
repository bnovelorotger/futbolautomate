from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.core.enums import MatchStatus, SourceName
from app.core.exceptions import SelectorDriftError
from app.schemas.match import MatchRecord
from app.schemas.standing import StandingRecord
from app.scrapers.futbolme import selectors
from app.utils.time import utcnow

_SEASON_PATTERN = re.compile(r"Temporada\s+(\d{4}-\d{2})", re.IGNORECASE)
_ROUND_PATTERN = re.compile(r"(Jornada\s+\d+)", re.IGNORECASE)
_SCORE_PATTERN = re.compile(r"^\s*(\d+)\s*-\s*(\d+)\s*$")
_TIME_PATTERN = re.compile(r"^\s*\d{1,2}:\d{2}\s*$")
_MATCH_ID_PATTERN = re.compile(r"/partido/[^/]+/(\d+)")


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

            round_name, match_date_raw = _parse_round_heading(match_card)
            status, status_raw, home_score, away_score, match_time_raw = _parse_match_status_and_result(match_card)
            detail_link = match_card.select_one(selectors.MATCH_DETAIL_LINK_SELECTOR)
            external_id = _extract_match_id(match_card)
            team_links = match_card.select("a[href*='/resultados-directo/equipo/']")
            detail_href = detail_link.get("href") if detail_link else None

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
                    home_team=_strip_duplicate_halves(_team_text(home_node)),
                    away_team=_strip_duplicate_halves(_team_text(away_node)),
                    home_score=home_score,
                    away_score=away_score,
                    status_raw=status_raw,
                    status=status,
                    venue=None,
                    scraped_at=utcnow(),
                    raw_payload={
                        "page_url": source_url,
                        "detail_url": _absolute_url(source_url, detail_href) if detail_href else None,
                        "home_team_url": _absolute_url(source_url, team_links[0].get("href")) if len(team_links) >= 1 else None,
                        "away_team_url": _absolute_url(source_url, team_links[1].get("href")) if len(team_links) >= 2 else None,
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
