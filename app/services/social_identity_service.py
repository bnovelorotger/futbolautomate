from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TeamMention, TeamSocial
from app.normalizers.text import normalize_token

_ACTIVITY_RANK = {
    "muy_alta": 5,
    "alta": 4,
    "media": 3,
    "baja_media": 2,
    "baja": 1,
}
_CLUB_PREFIXES = {
    "cd",
    "cf",
    "ce",
    "ue",
    "ud",
    "rcd",
    "scr",
    "atletico",
    "atl",
    "fc",
}


def _normalize_handle(handle: str | None) -> str | None:
    if handle is None:
        return None
    normalized = handle.strip()
    if not normalized:
        return None
    if not normalized.startswith("@"):
        normalized = f"@{normalized}"
    return normalized


def _normalized_identity(team_name: str) -> str:
    normalized = normalize_token(team_name)
    tokens = [token for token in normalized.split() if token and token not in _CLUB_PREFIXES]
    return " ".join(tokens) or normalized


class SocialIdentityService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_team_handle(
        self,
        team_name: str,
        competition_slug: str | None,
    ) -> str | None:
        social_info = self.get_team_social_info(team_name, competition_slug=competition_slug)
        handle = social_info.get("x_handle")
        if not isinstance(handle, str) or not handle.strip():
            return None
        return handle

    def get_team_social_info(
        self,
        team_name: str,
        competition_slug: str | None = None,
    ) -> dict[str, Any]:
        normalized_name = team_name.strip()
        if not normalized_name:
            return {}

        if competition_slug is not None:
            row = self.session.execute(
                select(TeamSocial).where(
                    TeamSocial.team_name == normalized_name,
                    TeamSocial.competition_slug == competition_slug,
                    TeamSocial.is_active.is_(True),
                )
            ).scalars().first()
            if row is not None and _normalize_handle(row.x_handle) is not None:
                return self._team_social_payload(row)

        rows = self.session.execute(
            select(TeamSocial).where(
                TeamSocial.team_name == normalized_name,
                TeamSocial.is_active.is_(True),
            )
        ).scalars().all()
        rows = [row for row in rows if _normalize_handle(row.x_handle) is not None]
        if rows:
            rows.sort(
                key=lambda row: (
                    -_ACTIVITY_RANK.get(row.activity_level, 0),
                    -(row.followers_approx or 0),
                    row.team_name,
                    row.id,
                )
            )
            return self._team_social_payload(rows[0])

        identity_match = self._identity_match_team_social(normalized_name, competition_slug)
        if identity_match is not None:
            return identity_match

        legacy = self._legacy_team_mention(normalized_name, competition_slug)
        if legacy is not None:
            return legacy
        return {}

    def _legacy_team_mention(
        self,
        team_name: str,
        competition_slug: str | None,
    ) -> dict[str, Any] | None:
        if competition_slug is not None:
            row = self.session.execute(
                select(TeamMention).where(
                    TeamMention.team_name == team_name,
                    TeamMention.competition_slug == competition_slug,
                )
            ).scalars().first()
            if row is not None and _normalize_handle(row.twitter_handle) is not None:
                return {
                    "team_name": row.team_name,
                    "competition_slug": row.competition_slug,
                    "x_handle": _normalize_handle(row.twitter_handle),
                    "followers_approx": None,
                    "activity_level": "media",
                    "is_shared_handle": False,
                    "is_active": True,
                    "source": "team_mentions",
                }

        row = self.session.execute(
            select(TeamMention).where(TeamMention.team_name == team_name)
        ).scalars().first()
        if row is None or _normalize_handle(row.twitter_handle) is None:
            return self._legacy_identity_match(team_name, competition_slug)
        return {
            "team_name": row.team_name,
            "competition_slug": row.competition_slug,
            "x_handle": _normalize_handle(row.twitter_handle),
            "followers_approx": None,
            "activity_level": "media",
            "is_shared_handle": False,
            "is_active": True,
            "source": "team_mentions",
        }

    def _identity_match_team_social(
        self,
        team_name: str,
        competition_slug: str | None,
    ) -> dict[str, Any] | None:
        identity = _normalized_identity(team_name)
        rows = self.session.execute(
            select(TeamSocial).where(TeamSocial.is_active.is_(True))
        ).scalars().all()
        matches = [
            row
            for row in rows
            if _normalize_handle(row.x_handle) is not None
            and (competition_slug is None or row.competition_slug in {competition_slug, None})
            and _normalized_identity(row.team_name) == identity
        ]
        if not matches:
            return None
        matches.sort(
            key=lambda row: (
                row.competition_slug not in {competition_slug, None},
                -_ACTIVITY_RANK.get(row.activity_level, 0),
                -(row.followers_approx or 0),
                row.team_name,
                row.id,
            )
        )
        return self._team_social_payload(matches[0])

    def _legacy_identity_match(
        self,
        team_name: str,
        competition_slug: str | None,
    ) -> dict[str, Any] | None:
        identity = _normalized_identity(team_name)
        rows = self.session.execute(select(TeamMention)).scalars().all()
        matches = [
            row
            for row in rows
            if _normalize_handle(row.twitter_handle) is not None
            and (competition_slug is None or row.competition_slug in {competition_slug, None})
            and _normalized_identity(row.team_name) == identity
        ]
        if not matches:
            return None
        matches.sort(
            key=lambda row: (
                row.competition_slug not in {competition_slug, None},
                row.team_name,
                row.id,
            )
        )
        row = matches[0]
        return {
            "team_name": row.team_name,
            "competition_slug": row.competition_slug,
            "x_handle": _normalize_handle(row.twitter_handle),
            "followers_approx": None,
            "activity_level": "media",
            "is_shared_handle": False,
            "is_active": True,
            "source": "team_mentions",
        }

    def _team_social_payload(self, row: TeamSocial) -> dict[str, Any]:
        return {
            "team_name": row.team_name,
            "competition_slug": row.competition_slug,
            "x_handle": _normalize_handle(row.x_handle),
            "followers_approx": row.followers_approx,
            "activity_level": row.activity_level,
            "is_shared_handle": row.is_shared_handle,
            "is_active": row.is_active,
            "source": "team_socials",
        }
