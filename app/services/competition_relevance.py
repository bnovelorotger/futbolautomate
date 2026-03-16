from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

from app.core.catalog import load_competition_catalog, load_team_alias_catalog
from app.core.exceptions import ConfigurationError
from app.normalizers.text import normalize_token
from app.schemas.reporting import CompetitionMatchView


@dataclass(frozen=True, slots=True)
class CompetitionTrackingConfig:
    tracked_teams: tuple[str, ...]
    alias_to_canonical: dict[str, str]


@lru_cache(maxsize=None)
def _tracking_config(competition_code: str) -> CompetitionTrackingConfig:
    competition = load_competition_catalog().get(competition_code)
    if competition is None:
        raise ConfigurationError(f"Competicion desconocida: {competition_code}")

    tracked_teams = tuple(competition.tracked_teams)
    alias_to_canonical: dict[str, str] = {}
    canonical_by_normalized = {normalize_token(team): team for team in tracked_teams if normalize_token(team)}

    for team in tracked_teams:
        normalized = normalize_token(team)
        if normalized:
            alias_to_canonical[normalized] = team

    for alias, canonical in load_team_alias_catalog().aliases.items():
        normalized_canonical = normalize_token(canonical)
        tracked_canonical = canonical_by_normalized.get(normalized_canonical)
        if tracked_canonical is None:
            continue
        normalized_alias = normalize_token(alias)
        if normalized_alias:
            alias_to_canonical[normalized_alias] = tracked_canonical

    return CompetitionTrackingConfig(
        tracked_teams=tracked_teams,
        alias_to_canonical=alias_to_canonical,
    )


class CompetitionRelevanceService:
    def tracked_teams(self, competition_code: str) -> list[str]:
        return list(_tracking_config(competition_code).tracked_teams)

    def has_tracked_teams(self, competition_code: str) -> bool:
        return bool(_tracking_config(competition_code).tracked_teams)

    def canonical_team(self, competition_code: str, team_name: str | None) -> str | None:
        if not team_name:
            return None
        return _tracking_config(competition_code).alias_to_canonical.get(normalize_token(team_name))

    def is_tracked_team(self, competition_code: str, team_name: str | None) -> bool:
        return self.canonical_team(competition_code, team_name) is not None

    def is_relevant_match(
        self,
        competition_code: str,
        home_team: str | None,
        away_team: str | None,
    ) -> bool:
        if not self.has_tracked_teams(competition_code):
            return True
        return self.is_tracked_team(competition_code, home_team) or self.is_tracked_team(
            competition_code,
            away_team,
        )

    def filter_match_views(
        self,
        competition_code: str,
        matches: Iterable[CompetitionMatchView],
    ) -> list[CompetitionMatchView]:
        rows = list(matches)
        if not self.has_tracked_teams(competition_code):
            return rows
        return [
            match
            for match in rows
            if self.is_relevant_match(competition_code, match.home_team, match.away_team)
        ]

    def tracked_teams_present(self, competition_code: str, team_names: Iterable[str]) -> list[str]:
        if not self.has_tracked_teams(competition_code):
            return []
        present: list[str] = []
        seen: set[str] = set()
        for team_name in team_names:
            canonical = self.canonical_team(competition_code, team_name)
            if canonical and canonical not in seen:
                seen.add(canonical)
                present.append(canonical)
        return present
