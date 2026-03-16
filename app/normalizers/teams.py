from __future__ import annotations

from dataclasses import dataclass

from app.core.catalog import load_team_alias_catalog
from app.normalizers.text import normalize_spaces, normalize_token


@dataclass(slots=True)
class TeamNameResult:
    raw: str
    canonical: str
    normalized: str


class TeamNameNormalizer:
    def __init__(self) -> None:
        self._aliases = load_team_alias_catalog().aliases

    def normalize(self, raw_name: str) -> TeamNameResult:
        cleaned = normalize_spaces(raw_name)
        normalized = normalize_token(cleaned)
        canonical = self._aliases.get(normalized, cleaned)
        return TeamNameResult(
            raw=cleaned,
            canonical=canonical,
            normalized=normalize_token(canonical),
        )

