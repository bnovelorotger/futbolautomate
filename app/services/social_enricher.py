from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import ContentType
from app.services.social_identity_service import SocialIdentityService

_HANDLE_PATTERN = re.compile(r"(?<!\w)@[A-Za-z0-9_]{1,15}")
_ACTIVITY_RANK = {
    "muy_alta": 5,
    "alta": 4,
    "media": 3,
    "baja_media": 2,
    "baja": 1,
}
_MAX_ENRICHED_CHARACTERS = 280


class SocialEnricherService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        identity_service: SocialIdentityService | None = None,
        max_characters: int = _MAX_ENRICHED_CHARACTERS,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.identity_service = identity_service or SocialIdentityService(session)
        self.max_characters = max_characters

    def enrich_text_with_mentions(
        self,
        text: str,
        payload_json: dict[str, Any],
        content_type: str,
        *,
        competition_slug: str | None = None,
    ) -> str:
        if not self.settings.enable_team_mentions:
            return text
        if not text.strip():
            return text

        try:
            resolved_content_type = ContentType(content_type)
        except ValueError:
            return text

        source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
        team_names = self._extract_team_names(source_payload, resolved_content_type)
        if not team_names:
            return text

        existing_handles = {
            handle.lower()
            for handle in _HANDLE_PATTERN.findall(text)
        }
        mention_budget = max(0, self.settings.max_mentions_per_post - len(existing_handles))
        if mention_budget <= 0:
            return text

        candidates = self._prioritized_candidates(team_names, competition_slug)
        enriched_text = text
        for team_name, handle in candidates:
            if mention_budget <= 0:
                break
            if handle.lower() in existing_handles:
                continue
            replacement = f"{team_name} {handle}"
            updated_text, replaced = self._replace_first(enriched_text, team_name, replacement)
            if not replaced:
                continue
            if len(updated_text) > self.max_characters:
                continue
            enriched_text = updated_text
            existing_handles.add(handle.lower())
            mention_budget -= 1

        return enriched_text

    def _prioritized_candidates(
        self,
        team_names: list[str],
        competition_slug: str | None,
    ) -> list[tuple[str, str]]:
        rows: list[tuple[str, str, int, int, int]] = []
        for index, team_name in enumerate(team_names):
            social_info = self.identity_service.get_team_social_info(team_name, competition_slug=competition_slug)
            handle = social_info.get("x_handle")
            if not isinstance(handle, str) or not handle.strip():
                continue
            activity_level = str(social_info.get("activity_level") or "media")
            rows.append(
                (
                    team_name,
                    handle,
                    index,
                    -_ACTIVITY_RANK.get(activity_level, 0),
                    -(int(social_info.get("followers_approx") or 0)),
                )
            )
        rows.sort(key=lambda item: (item[2], item[3], item[4], item[0]))

        selected: list[tuple[str, str]] = []
        seen_handles: set[str] = set()
        seen_teams: set[str] = set()
        for team_name, handle, _, _, _ in rows:
            normalized_handle = handle.lower()
            if normalized_handle in seen_handles or team_name in seen_teams:
                continue
            selected.append((team_name, handle))
            seen_handles.add(normalized_handle)
            seen_teams.add(team_name)
        return selected

    def _extract_team_names(
        self,
        source_payload: dict[str, Any],
        content_type: ContentType,
    ) -> list[str]:
        if not isinstance(source_payload, dict):
            return []
        if content_type == ContentType.RESULTS_ROUNDUP:
            matches = source_payload.get("matches")
            if isinstance(matches, list):
                return self._unique(
                    team_name
                    for match in matches
                    for team_name in (
                        self._string(match.get("home_team")),
                        self._string(match.get("away_team")),
                    )
                    if team_name
                )
        if content_type in {ContentType.STANDINGS, ContentType.STANDINGS_ROUNDUP}:
            rows = source_payload.get("rows")
            if isinstance(rows, list):
                ordered_rows = sorted(rows, key=lambda row: int(row.get("position") or 999))
                return self._unique(
                    self._string(row.get("team"))
                    for row in ordered_rows[:3]
                    if self._string(row.get("team"))
                )
        if content_type == ContentType.PREVIEW:
            featured = source_payload.get("featured_match")
            names: list[str] = []
            if isinstance(featured, dict):
                names.extend(
                    team_name
                    for team_name in (
                        self._string(featured.get("home_team")),
                        self._string(featured.get("away_team")),
                    )
                    if team_name
                )
            matches = source_payload.get("matches")
            if isinstance(matches, list):
                for match in matches:
                    for team_name in (
                        self._string(match.get("home_team")),
                        self._string(match.get("away_team")),
                    ):
                        if team_name:
                            names.append(team_name)
            return self._unique(names)
        if content_type == ContentType.RANKING:
            names: list[str] = []
            for key in ("best_attack", "best_defense", "most_wins"):
                value = source_payload.get(key)
                if isinstance(value, dict):
                    team_name = self._string(value.get("team"))
                    if team_name:
                        names.append(team_name)
            return self._unique(names)
        return self._unique(self._walk_team_names(source_payload))

    def _walk_team_names(self, value: Any) -> list[str]:
        names: list[str] = []
        if isinstance(value, dict):
            for key, inner_value in value.items():
                if key in {"team", "home_team", "away_team"}:
                    team_name = self._string(inner_value)
                    if team_name:
                        names.append(team_name)
                elif key == "teams" and isinstance(inner_value, list):
                    for item in inner_value:
                        team_name = self._string(item)
                        if team_name:
                            names.append(team_name)
                else:
                    names.extend(self._walk_team_names(inner_value))
        elif isinstance(value, list):
            for item in value:
                names.extend(self._walk_team_names(item))
        return names

    def _replace_first(self, text: str, needle: str, replacement: str) -> tuple[str, bool]:
        position = text.find(needle)
        if position < 0:
            return text, False
        return f"{text[:position]}{replacement}{text[position + len(needle):]}", True

    def _unique(self, values) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            ordered.append(value)
        return ordered

    def _string(self, value: Any) -> str | None:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return None
