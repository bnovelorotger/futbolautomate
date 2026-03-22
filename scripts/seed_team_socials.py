from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.db.models import TeamMention, TeamSocial
from app.db.session import init_db, session_scope

DATASET_PATH = Path(__file__).resolve().with_name("team_socials_dataset.json")
_ALLOWED_ACTIVITY_LEVELS = {"muy_alta", "alta", "media", "baja_media", "baja"}
_ACTIVITY_ALIASES = {
    "media_baja": "baja_media",
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


def _dataset_rows() -> list[dict]:
    if not DATASET_PATH.exists():
        return []
    with DATASET_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError(f"Dataset invalido en {DATASET_PATH}")
    return [row for row in payload if isinstance(row, dict)]


def _normalize_activity_level(value: str | None) -> str:
    normalized = str(value or "media").strip().lower()
    normalized = _ACTIVITY_ALIASES.get(normalized, normalized)
    if normalized not in _ALLOWED_ACTIVITY_LEVELS:
        return "media"
    return normalized


def _legacy_rows(session) -> list[dict]:
    rows = session.execute(select(TeamMention)).scalars().all()
    payload: list[dict] = []
    for row in rows:
        handle = _normalize_handle(row.twitter_handle)
        if handle is None:
            continue
        payload.append(
            {
                "team_name": row.team_name,
                "competition_slug": row.competition_slug,
                "x_handle": handle,
                "followers_approx": None,
                "activity_level": "media",
                "is_shared_handle": False,
                "is_active": True,
            }
        )
    return payload


def _upsert_row(session, payload: dict) -> tuple[bool, bool]:
    team_name = str(payload.get("team_name") or "").strip()
    competition_slug = payload.get("competition_slug")
    handle = _normalize_handle(payload.get("x_handle"))
    if not team_name or handle is None:
        return False, False

    row = session.execute(
        select(TeamSocial).where(
            TeamSocial.team_name == team_name,
            TeamSocial.competition_slug == competition_slug,
        )
    ).scalars().first()
    created = False
    updated = False
    if row is None:
        row = TeamSocial(
            team_name=team_name,
            competition_slug=competition_slug,
            x_handle=handle,
            followers_approx=payload.get("followers_approx"),
            activity_level=_normalize_activity_level(payload.get("activity_level")),
            is_shared_handle=bool(payload.get("is_shared_handle", False)),
            is_active=bool(payload.get("is_active", True)),
        )
        session.add(row)
        session.flush()
        return True, False

    if row.x_handle != handle:
        row.x_handle = handle
        updated = True
    new_followers = payload.get("followers_approx")
    if row.followers_approx != new_followers:
        row.followers_approx = new_followers
        updated = True
    new_activity = _normalize_activity_level(payload.get("activity_level"))
    if row.activity_level != new_activity:
        row.activity_level = new_activity
        updated = True
    new_shared = bool(payload.get("is_shared_handle", False))
    if row.is_shared_handle != new_shared:
        row.is_shared_handle = new_shared
        updated = True
    new_active = bool(payload.get("is_active", True))
    if row.is_active != new_active:
        row.is_active = new_active
        updated = True
    session.add(row)
    session.flush()
    return created, updated


def main() -> None:
    init_db()
    with session_scope() as session:
        dataset_rows = _dataset_rows()
        bootstrap_rows = _legacy_rows(session)
        created = 0
        updated = 0
        skipped = 0
        for payload in [*bootstrap_rows, *dataset_rows]:
            inserted, changed = _upsert_row(session, payload)
            if inserted:
                created += 1
            elif changed:
                updated += 1
            else:
                skipped += 1
    print(
        f"team_socials seeded created={created} updated={updated} skipped={skipped} "
        f"dataset_rows={len(dataset_rows)} bootstrap_rows={len(bootstrap_rows)}"
    )


if __name__ == "__main__":
    main()
