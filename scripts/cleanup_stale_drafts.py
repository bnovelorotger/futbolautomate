"""Mark stale draft candidates as rejected so they don't block the pipeline."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from app.db.session import session_scope
from app.db.models import ContentCandidate
from sqlalchemy import select, update

CUTOFF_UTC = datetime(2026, 5, 14, 0, 0, 0, tzinfo=timezone.utc)
DRY_RUN = "--dry-run" in sys.argv


def main() -> None:
    with session_scope() as session:
        rows = session.execute(
            select(ContentCandidate).where(
                ContentCandidate.status == "draft",
                ContentCandidate.created_at < CUTOFF_UTC,
            )
        ).scalars().all()

        print(f"Stale drafts found (created before {CUTOFF_UTC.date()}): {len(rows)}")
        if DRY_RUN:
            for r in rows:
                print(f"  [{r.id}] {r.content_type:<30} {r.competition_slug:<35} created={str(r.created_at)[:10]}")
            print("\n[dry-run] No changes made.")
            return

        now = datetime.now(timezone.utc)
        ids = [r.id for r in rows]
        session.execute(
            update(ContentCandidate)
            .where(ContentCandidate.id.in_(ids))
            .values(
                status="rejected",
                reviewed_at=now,
                rejection_reason="stale_window: content expired before release could run",
            )
        )
        print(f"Marked {len(ids)} drafts as rejected.")

        remaining = session.execute(
            select(ContentCandidate).where(ContentCandidate.status == "draft")
        ).scalars().all()
        print(f"\nDrafts remaining after cleanup: {len(remaining)}")
        for r in remaining:
            print(f"  [{r.id}] {r.content_type:<30} {r.competition_slug:<35} created={str(r.created_at)[:10]}")


if __name__ == "__main__":
    main()
