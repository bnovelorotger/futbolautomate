from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import ContentCandidate


class EditorialRewriteMetricsService:
    def __init__(self, session: Session, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.timezone = ZoneInfo(self.settings.timezone)

    def daily_outcome_report(
        self,
        *,
        start_date: date,
        end_date: date,
        competition_slug: str | None = None,
    ) -> dict:
        start_utc, end_utc = self._day_bounds(start_date, end_date)
        query = select(ContentCandidate).where(
            ContentCandidate.rewrite_timestamp.is_not(None),
            ContentCandidate.rewrite_timestamp >= start_utc,
            ContentCandidate.rewrite_timestamp < end_utc,
        )
        if competition_slug:
            query = query.where(ContentCandidate.competition_slug == competition_slug)
        rows = self.session.execute(query.order_by(ContentCandidate.rewrite_timestamp.asc())).scalars().all()

        by_date: dict[str, dict] = {}
        overall_outcomes: Counter[str] = Counter()
        overall_by_type: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            rewrite_date = self._local_date(row.rewrite_timestamp)
            if rewrite_date is None:
                continue
            key = rewrite_date.isoformat()
            day_payload = by_date.setdefault(
                key,
                {
                    "date": key,
                    "total": 0,
                    "real_count": 0,
                    "fallback_count": 0,
                    "failed_count": 0,
                    "other_count": 0,
                    "by_content_type": defaultdict(Counter),
                },
            )
            outcome = self._rewrite_outcome(row.rewrite_status)
            day_payload["total"] += 1
            overall_outcomes[outcome] += 1
            day_payload["by_content_type"][row.content_type][outcome] += 1
            overall_by_type[row.content_type][outcome] += 1
            if outcome == "real":
                day_payload["real_count"] += 1
            elif outcome == "fallback_base_text":
                day_payload["fallback_count"] += 1
            elif outcome == "failed":
                day_payload["failed_count"] += 1
            else:
                day_payload["other_count"] += 1

        days = []
        for payload in sorted(by_date.values(), key=lambda item: item["date"]):
            total = payload["total"] or 1
            payload["real_ratio"] = round(payload["real_count"] / total, 4)
            payload["fallback_ratio"] = round(payload["fallback_count"] / total, 4)
            payload["failed_ratio"] = round(payload["failed_count"] / total, 4)
            payload["other_ratio"] = round(payload["other_count"] / total, 4)
            payload["by_content_type"] = {
                content_type: dict(counter)
                for content_type, counter in sorted(payload["by_content_type"].items())
            }
            days.append(payload)

        total = sum(day["total"] for day in days)
        return {
            "timezone": self.settings.timezone,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "competition_slug": competition_slug,
            "total_rewrites": total,
            "real_count": overall_outcomes["real"],
            "fallback_count": overall_outcomes["fallback_base_text"],
            "failed_count": overall_outcomes["failed"],
            "other_count": overall_outcomes["other"],
            "real_ratio": round(overall_outcomes["real"] / total, 4) if total else 0.0,
            "fallback_ratio": round(overall_outcomes["fallback_base_text"] / total, 4) if total else 0.0,
            "failed_ratio": round(overall_outcomes["failed"] / total, 4) if total else 0.0,
            "other_ratio": round(overall_outcomes["other"] / total, 4) if total else 0.0,
            "by_content_type": {content_type: dict(counter) for content_type, counter in sorted(overall_by_type.items())},
            "days": days,
        }

    def _rewrite_outcome(self, rewrite_status: str | None) -> str:
        if rewrite_status in {"rewritten", "dry_run"}:
            return "real"
        if rewrite_status in {"rewritten_fallback_base_text", "dry_run_fallback_base_text"}:
            return "fallback_base_text"
        if rewrite_status == "failed":
            return "failed"
        return "other"

    def _local_date(self, value: datetime | None) -> date | None:
        if value is None:
            return None
        normalized = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return normalized.astimezone(self.timezone).date()

    def _day_bounds(self, start_date: date, end_date: date) -> tuple[datetime, datetime]:
        start_local = datetime.combine(start_date, time.min, tzinfo=self.timezone)
        end_local = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=self.timezone)
        return start_local.astimezone(UTC), end_local.astimezone(UTC)
