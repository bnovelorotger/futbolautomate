from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.catalog import load_competition_catalog, load_team_alias_catalog
from app.core.editorial import EditorialRules, load_editorial_rules
from app.db.models import News, Team
from app.db.repositories.news_enrichments import NewsEnrichmentRepository
from app.normalizers.text import normalize_token
from app.schemas.common import IngestStats
from app.schemas.editorial import NewsEditorialRecord
from app.utils.time import utcnow

@dataclass(slots=True)
class AliasMap:
    aliases: dict[str, str]
    ordered_aliases: list[str]


class NewsEditorialAnalyzer:
    def __init__(self, session: Session, rules: EditorialRules | None = None) -> None:
        self.session = session
        self.rules = rules or load_editorial_rules()
        self.club_aliases = self._build_club_aliases()
        self.competition_aliases = self._build_competition_aliases()

    def _build_club_aliases(self) -> AliasMap:
        alias_map: dict[str, str] = {}

        def add(alias: str, canonical: str) -> None:
            normalized_alias = normalize_token(alias)
            if normalized_alias:
                alias_map[normalized_alias] = canonical

        for canonical, aliases in self.rules.target_clubs.items():
            add(canonical, canonical)
            for alias in aliases:
                add(alias, canonical)

        for alias, canonical in load_team_alias_catalog().aliases.items():
            add(alias, canonical)
            add(canonical, canonical)

        team_names = self.session.execute(select(Team.name)).scalars().all()
        for team_name in team_names:
            add(team_name, team_name)

        ordered_aliases = sorted(alias_map.keys(), key=lambda value: (-len(value.split()), -len(value), value))
        return AliasMap(aliases=alias_map, ordered_aliases=ordered_aliases)

    def _build_competition_aliases(self) -> AliasMap:
        alias_map: dict[str, str] = {}

        def add(alias: str, canonical: str) -> None:
            normalized_alias = normalize_token(alias)
            if normalized_alias:
                alias_map[normalized_alias] = canonical

        for canonical, aliases in self.rules.target_competitions.items():
            add(canonical, canonical)
            for alias in aliases:
                add(alias, canonical)

        for competition in load_competition_catalog().values():
            add(competition.name, competition.name)
            for alias in competition.aliases:
                add(alias, competition.name)

        ordered_aliases = sorted(alias_map.keys(), key=lambda value: (-len(value.split()), -len(value), value))
        return AliasMap(aliases=alias_map, ordered_aliases=ordered_aliases)

    def _news_text(self, news: News) -> str:
        parts = [news.title, news.subtitle, news.summary, news.body_text, news.raw_category]
        return normalize_token(" ".join(part for part in parts if part))

    def _match_aliases(self, text: str, mapping: AliasMap) -> list[str]:
        padded_text = f" {text} "
        matched: list[str] = []
        seen: set[str] = set()
        for alias in mapping.ordered_aliases:
            if f" {alias} " not in padded_text:
                continue
            canonical = mapping.aliases[alias]
            if canonical not in seen:
                seen.add(canonical)
                matched.append(canonical)
        return matched

    def _term_hits(self, text: str, terms: list[str]) -> list[str]:
        padded_text = f" {text} "
        hits: list[str] = []
        for term in terms:
            normalized_term = normalize_token(term)
            if normalized_term and f" {normalized_term} " in padded_text:
                hits.append(term)
        return hits

    def analyze(self, news: News) -> NewsEditorialRecord:
        text = self._news_text(news)
        clubs = self._match_aliases(text, self.club_aliases)
        competitions = self._match_aliases(text, self.competition_aliases)

        if news.clubs_detected:
            for club in news.clubs_detected:
                if club not in clubs:
                    clubs.append(club)

        competition_detected = competitions[0] if competitions else news.competition_detected

        football_hits = self._term_hits(text, self.rules.football_terms)
        balearic_hits = self._term_hits(text, self.rules.balearic_terms)
        penalty_hits = self._term_hits(text, self.rules.non_football_penalty_terms)

        sport_hits: dict[str, int] = {}
        for sport, terms in self.rules.sport_terms.items():
            sport_hits[sport] = len(self._term_hits(text, terms))

        best_other_sport = "unknown"
        best_other_score = 0
        for sport, hits in sport_hits.items():
            if sport == "football":
                continue
            if hits > best_other_score:
                best_other_sport = sport
                best_other_score = hits

        football_signal_strength = sport_hits.get("football", 0) + len(football_hits) + len(clubs) + int(
            competition_detected is not None
        )
        hard_football_signal = bool(clubs or competition_detected)
        if hard_football_signal:
            is_football = football_signal_strength > 0 and football_signal_strength >= best_other_score
        else:
            is_football = football_signal_strength > 0 and football_signal_strength > best_other_score

        if is_football:
            sport_detected = "football"
        elif best_other_score > 0:
            sport_detected = best_other_sport
        else:
            sport_detected = "unknown"

        is_balearic_related = bool(clubs or competition_detected or balearic_hits)

        weights = defaultdict(int, self.rules.score_weights)
        score = 0
        if is_football:
            score += weights["football_detected"]
        if football_hits:
            score += weights["football_terms"]
        if clubs:
            score += weights["club_detected"] + max(0, len(clubs) - 1) * 2
        if competition_detected:
            score += weights["competition_detected"]
        if balearic_hits:
            score += weights["balearic_terms"]
        if sport_detected not in {"football", "unknown"}:
            score += weights["non_football_sport"]
        if penalty_hits and not is_football:
            score += weights["non_football_terms"]
        if not is_balearic_related:
            score += weights["no_balearic_signal"]

        signals = {
            "football_hits": football_hits,
            "balearic_hits": balearic_hits,
            "penalty_hits": penalty_hits,
            "sport_hits": sport_hits,
            "clubs_detected": clubs,
            "competition_detected": competition_detected or "",
        }

        return NewsEditorialRecord(
            news_id=news.id,
            sport_detected=sport_detected,
            is_football=is_football,
            is_balearic_related=is_balearic_related,
            clubs_detected=clubs,
            competition_detected=competition_detected,
            editorial_relevance_score=score,
            signals=signals,
            analyzed_at=utcnow(),
        )


def enrich_news_editorial(
    session: Session,
    limit: int | None = None,
    source_name: str | None = None,
) -> IngestStats:
    stats = IngestStats()
    query = select(News).order_by(News.published_at.desc().nullslast(), News.id.desc())
    if source_name:
        query = query.where(News.source_name == source_name)
    if limit is not None:
        query = query.limit(limit)

    news_items = session.execute(query).scalars().all()
    stats.found = len(news_items)

    repository = NewsEnrichmentRepository(session)
    analyzer = NewsEditorialAnalyzer(session)
    for news in news_items:
        record = analyzer.analyze(news)
        _, inserted, updated = repository.upsert(record.model_dump())
        stats.inserted += int(inserted)
        stats.updated += int(updated)
    return stats
