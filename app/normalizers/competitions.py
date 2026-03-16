from __future__ import annotations

from dataclasses import dataclass

from app.core.catalog import load_competition_catalog
from app.normalizers.text import normalize_token


@dataclass(slots=True)
class CompetitionMatch:
    code: str
    name: str
    normalized_name: str


class CompetitionNormalizer:
    def __init__(self) -> None:
        self._catalog = load_competition_catalog()
        self._lookup: dict[str, CompetitionMatch] = {}
        for code, competition in self._catalog.items():
            candidates = [
                competition.name,
                competition.editorial_name,
                *competition.aliases,
                *competition.historical_backlog_names,
            ]
            for candidate in candidates:
                if not candidate:
                    continue
                self._lookup[normalize_token(candidate)] = CompetitionMatch(
                    code=code,
                    name=competition.name,
                    normalized_name=normalize_token(competition.name),
                )

    def resolve(self, raw_name: str | None, fallback_code: str | None = None) -> CompetitionMatch | None:
        if fallback_code:
            competition = self._catalog.get(fallback_code)
            if competition:
                return CompetitionMatch(
                    code=competition.code,
                    name=competition.name,
                    normalized_name=normalize_token(competition.name),
                )
        if not raw_name:
            return None
        return self._lookup.get(normalize_token(raw_name))
