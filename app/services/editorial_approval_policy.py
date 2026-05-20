from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.db.models import ContentCandidate

logger = logging.getLogger(__name__)
from app.schemas.editorial_approval import (
    EditorialApprovalCandidateView,
    EditorialApprovalRunResult,
    EditorialApprovalStatusView,
)
from app.services.editorial_candidate_window import EditorialCandidateWindowService
from app.services.editorial_quality_checks import EditorialQualityChecksService
from app.utils.time import utcnow

AUTOAPPROVABLE_CONTENT_TYPES = (
    ContentType.RESULTS_ROUNDUP,
    ContentType.STANDINGS_ROUNDUP,
    ContentType.PREVIEW,
    ContentType.RANKING,
)
MONDAY_AUTOAPPROVABLE_CONTENT_TYPES = (ContentType.TOP_SCORER_UPDATE,)
TUE_WED_AUTOAPPROVABLE_CONTENT_TYPES = (
    ContentType.VIRAL_STORY,
    ContentType.METRIC_NARRATIVE,
    ContentType.STAT_NARRATIVE,
    ContentType.RANKING,
)
THURSDAY_AUTOAPPROVABLE_CONTENT_TYPES = (
    ContentType.TOP_SCORER_UPDATE,
    ContentType.RANKING,
)
FRIDAY_AUTOAPPROVABLE_CONTENT_TYPES = (
    ContentType.FEATURED_MATCH_PREVIEW,
    ContentType.MATCH_IMPACT_SCENARIO,
)
CONDITIONAL_AUTOAPPROVABLE_CONTENT_TYPES = (ContentType.RACE_NARRATIVE,)
MANUAL_REVIEW_CONTENT_TYPES = (
    ContentType.MATCH_RESULT,
    ContentType.STANDINGS,
    ContentType.FORM_RANKING,
    ContentType.FEATURED_MATCH_PREVIEW,
    ContentType.FEATURED_MATCH_EVENT,
    ContentType.STANDINGS_EVENT,
    ContentType.FORM_EVENT,
    ContentType.VIRAL_STORY,
    ContentType.STAT_NARRATIVE,
    ContentType.METRIC_NARRATIVE,
    ContentType.MATCH_IMPACT_SCENARIO,
    ContentType.RACE_NARRATIVE,
    ContentType.MILESTONE_STORY,
    ContentType.TOP_SCORER_UPDATE,
)
_CONDITIONAL_POLICY_PENDING_REASON = "conditional_policy_pending"
_RACE_NARRATIVE_ALLOWED_WEEKDAYS = frozenset({0})
_RACE_NARRATIVE_AUTO_RULES: dict[str, dict[str, int]] = {
    "title_race": {
        "min_priority": 86,
        "min_team_count": 2,
        "max_team_count": 4,
        "max_points_span": 2,
        "max_rounds_remaining": 10,
        "type_rank": 3,
    },
    "playoff_race": {
        "min_priority": 83,
        "min_team_count": 3,
        "max_team_count": 5,
        "max_points_span": 2,
        "max_rounds_remaining": 8,
        "type_rank": 2,
    },
    "relegation_race": {
        "min_priority": 82,
        "min_team_count": 3,
        "max_team_count": 5,
        "max_points_span": 2,
        "max_rounds_remaining": 8,
        "type_rank": 1,
    },
}


def _excerpt(text: str, limit: int = 100) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


class EditorialApprovalPolicyService:
    def __init__(self, session: Session, *, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.window_service = EditorialCandidateWindowService(session, settings=self.settings)
        self.quality_service = EditorialQualityChecksService(session, settings=self.settings)

    def status(
        self,
        *,
        reference_date: date | None = None,
        limit: int = 200,
    ) -> EditorialApprovalStatusView:
        selected_date = reference_date or datetime.now(ZoneInfo(self.settings.timezone)).date()
        rows = self._pending_drafts(reference_date=selected_date, limit=limit)
        quality_snapshot = self._quality_snapshot(rows, reference_date=selected_date)
        views = self._evaluate_rows(
            rows,
            quality_snapshot=quality_snapshot,
            reference_date=selected_date,
        )
        autoapprovable_count = sum(1 for view in views if view.autoapprovable)
        autoapprovable_types = list(self._autoapprovable_types_for_date(selected_date))
        return EditorialApprovalStatusView(
            enabled=True,
            autoapprovable_content_types=autoapprovable_types,
            conditional_autoapprovable_content_types=list(CONDITIONAL_AUTOAPPROVABLE_CONTENT_TYPES),
            manual_review_content_types=[
                content_type for content_type in MANUAL_REVIEW_CONTENT_TYPES if content_type not in autoapprovable_types
            ],
            drafts_found=len(rows),
            autoapprovable_count=autoapprovable_count,
            manual_review_count=len(rows) - autoapprovable_count,
        )

    def autoapprove(
        self,
        *,
        reference_date: date | None = None,
        limit: int = 200,
        dry_run: bool = False,
    ) -> EditorialApprovalRunResult:
        selected_date = reference_date or datetime.now(ZoneInfo(self.settings.timezone)).date()
        rows = self._pending_drafts(reference_date=selected_date, limit=limit)
        quality_snapshot = self._quality_snapshot(rows, reference_date=selected_date)
        evaluated_rows = {
            view.id: view
            for view in self._evaluate_rows(
                rows,
                quality_snapshot=quality_snapshot,
                reference_date=selected_date,
            )
        }
        result_rows: list[EditorialApprovalCandidateView] = []
        autoapprovable_count = 0
        autoapproved_count = 0
        timestamp = utcnow()

        for row in rows:
            view = evaluated_rows[row.id]
            if view.autoapprovable:
                autoapprovable_count += 1
                if not dry_run:
                    row.status = str(ContentCandidateStatus.APPROVED)
                    row.reviewed_at = timestamp
                    row.approved_at = timestamp
                    row.published_at = None
                    row.rejection_reason = None
                    row.autoapproved = True
                    row.autoapproved_at = timestamp
                    row.autoapproval_reason = view.policy_reason
                    self.session.add(row)
                    self.session.flush()
                    view = self._row_to_view(
                        row,
                        autoapprovable=True,
                        policy_reason=view.policy_reason,
                        importance_score=view.importance_score,
                        priority_bucket=view.priority_bucket,
                        importance_reasoning=view.importance_reasoning,
                    )
                autoapproved_count += 1
            result_rows.append(view)

        return EditorialApprovalRunResult(
            dry_run=dry_run,
            reference_date=selected_date,
            drafts_found=len(rows),
            autoapprovable_count=autoapprovable_count,
            autoapproved_count=autoapproved_count,
            manual_review_count=len(rows) - autoapprovable_count,
            rows=result_rows,
        )

    def candidate_ids_for_quality_precheck(
        self,
        *,
        reference_date: date | None = None,
        limit: int = 200,
    ) -> list[int]:
        selected_date = reference_date or datetime.now(ZoneInfo(self.settings.timezone)).date()
        rows = self._pending_drafts(reference_date=selected_date, limit=limit)
        return [row.id for row in rows if self._is_potential_autoapprovable(row, reference_date=selected_date)]

    def _evaluate_rows(
        self,
        candidates: list[ContentCandidate],
        *,
        quality_snapshot: dict[int, tuple[bool, list[str]]] | None = None,
        reference_date: date,
    ) -> list[EditorialApprovalCandidateView]:
        views_by_id: dict[int, EditorialApprovalCandidateView] = {}
        conditional_candidates: list[ContentCandidate] = []
        for candidate in candidates:
            autoapprovable, policy_reason = self._base_policy(
                candidate,
                quality_snapshot=quality_snapshot,
                reference_date=reference_date,
            )
            if policy_reason == _CONDITIONAL_POLICY_PENDING_REASON:
                conditional_candidates.append(candidate)
                continue
            views_by_id[candidate.id] = self._row_to_view(
                candidate,
                autoapprovable=autoapprovable,
                policy_reason=policy_reason,
            )

        decisions = self._evaluate_conditional_candidates(
            conditional_candidates,
            reference_date=reference_date,
        )
        for candidate in conditional_candidates:
            autoapprovable, policy_reason = decisions[candidate.id]
            views_by_id[candidate.id] = self._row_to_view(
                candidate,
                autoapprovable=autoapprovable,
                policy_reason=policy_reason,
            )
        return [views_by_id[candidate.id] for candidate in candidates]

    def _evaluate_conditional_candidates(
        self,
        candidates: list[ContentCandidate],
        *,
        reference_date: date,
    ) -> dict[int, tuple[bool, str]]:
        decisions: dict[int, tuple[bool, str]] = {}
        race_candidates_by_competition: dict[str, list[ContentCandidate]] = {}

        for candidate in candidates:
            content_type = ContentType(candidate.content_type)
            if content_type == ContentType.RACE_NARRATIVE:
                race_candidates_by_competition.setdefault(candidate.competition_slug, []).append(candidate)
                continue
            decisions[candidate.id] = (False, "manual_review_policy")

        for competition_slug in sorted(race_candidates_by_competition):
            rows = race_candidates_by_competition[competition_slug]
            eligible_rows: list[ContentCandidate] = []
            for row in rows:
                allowed, reason = self._race_narrative_eligibility(
                    row,
                    reference_date=reference_date,
                )
                if allowed:
                    eligible_rows.append(row)
                else:
                    decisions[row.id] = (False, reason)
            if not eligible_rows:
                continue
            selected = max(eligible_rows, key=self._race_narrative_selection_key)
            decisions[selected.id] = (True, "policy_autoapprove_race_narrative")
            for row in eligible_rows:
                if row.id != selected.id:
                    decisions[row.id] = (False, "race_narrative_competition_limit")

        return decisions

    def _base_policy(
        self,
        candidate: ContentCandidate,
        *,
        quality_snapshot: dict[int, tuple[bool, list[str]]] | None = None,
        reference_date: date,
    ) -> tuple[bool, str]:
        status = ContentCandidateStatus(candidate.status)
        quality_passed, quality_errors = self._quality_state(
            candidate,
            quality_snapshot=quality_snapshot,
        )
        if status != ContentCandidateStatus.DRAFT:
            return False, f"status_not_draft:{status}"
        elif candidate.reviewed_at is not None:
            return False, "already_reviewed"
        elif not candidate.text_draft.strip():
            return False, "text_draft_empty"
        elif quality_passed is False or quality_errors:
            return False, "quality_errors_present"
        else:
            content_type = ContentType(candidate.content_type)
            if content_type in self._autoapprovable_types_for_date(reference_date):
                return True, "policy_autoapprove_safe_type"
            if content_type in CONDITIONAL_AUTOAPPROVABLE_CONTENT_TYPES:
                return False, _CONDITIONAL_POLICY_PENDING_REASON
            elif content_type in MANUAL_REVIEW_CONTENT_TYPES:
                return False, "manual_review_policy"
            else:
                return False, "content_type_not_configured"

    def _race_narrative_eligibility(
        self,
        candidate: ContentCandidate,
        *,
        reference_date: date,
    ) -> tuple[bool, str]:
        if reference_date.weekday() not in _RACE_NARRATIVE_ALLOWED_WEEKDAYS:
            return False, "race_narrative_day_not_enabled"

        source_payload = self._source_payload(candidate)
        narrative_type = str(source_payload.get("narrative_type") or "")
        if not narrative_type:
            return False, "race_narrative_type_missing"

        rules = _RACE_NARRATIVE_AUTO_RULES.get(narrative_type)
        if rules is None:
            return False, f"race_narrative_manual_only_type:{narrative_type}"

        team_count = source_payload.get("team_count")
        if not isinstance(team_count, int):
            return False, "race_narrative_team_count_invalid"
        if team_count < rules["min_team_count"]:
            return False, f"race_narrative_team_count<{rules['min_team_count']}"
        if team_count > rules["max_team_count"]:
            return False, f"race_narrative_team_count>{rules['max_team_count']}"

        points_span = source_payload.get("points_span")
        if not isinstance(points_span, int):
            return False, "race_narrative_points_span_invalid"
        if points_span > rules["max_points_span"]:
            return False, f"race_narrative_points_span>{rules['max_points_span']}"

        rounds_remaining = source_payload.get("rounds_remaining")
        if not isinstance(rounds_remaining, int) or rounds_remaining < 1:
            return False, "race_narrative_rounds_remaining_invalid"
        if rounds_remaining > rules["max_rounds_remaining"]:
            return False, f"race_narrative_rounds_remaining>{rules['max_rounds_remaining']}"

        target_position = source_payload.get("target_position")
        if narrative_type == "title_race":
            if target_position != 1:
                return False, "race_narrative_target_position_invalid"
        elif not isinstance(target_position, int) or target_position < 2:
            return False, "race_narrative_target_position_invalid"

        if candidate.priority < rules["min_priority"]:
            return False, f"race_narrative_priority<{rules['min_priority']}"

        teams = source_payload.get("teams")
        if not isinstance(teams, list) or not teams:
            return False, "race_narrative_teams_missing"
        team_names = [
            item.get("team")
            for item in teams
            if isinstance(item, dict) and isinstance(item.get("team"), str) and item.get("team").strip()
        ]
        if len(team_names) != len(teams) or len(set(team_names)) != len(team_names):
            return False, "race_narrative_teams_invalid"
        if len(teams) != team_count:
            return False, "race_narrative_team_count_mismatch"

        return True, "race_narrative_policy_ready"

    def _race_narrative_selection_key(self, candidate: ContentCandidate) -> tuple[int, int, int, int, int]:
        source_payload = self._source_payload(candidate)
        narrative_type = str(source_payload.get("narrative_type") or "")
        rules = _RACE_NARRATIVE_AUTO_RULES.get(narrative_type, {})
        points_span = source_payload.get("points_span")
        rounds_remaining = source_payload.get("rounds_remaining")
        team_count = source_payload.get("team_count")
        return (
            candidate.priority,
            int(rules.get("type_rank", 0)),
            -int(points_span) if isinstance(points_span, int) else -99,
            -int(rounds_remaining) if isinstance(rounds_remaining, int) else -99,
            -int(team_count) if isinstance(team_count, int) else -99,
        )

    def _source_payload(self, candidate: ContentCandidate) -> dict[str, object]:
        payload_json = candidate.payload_json or {}
        source_payload = payload_json.get("source_payload", {}) if isinstance(payload_json, dict) else {}
        if isinstance(source_payload, dict):
            return source_payload
        return {}

    def _is_potential_autoapprovable(self, candidate: ContentCandidate, *, reference_date: date) -> bool:
        status = ContentCandidateStatus(candidate.status)
        if status != ContentCandidateStatus.DRAFT:
            return False
        if candidate.reviewed_at is not None:
            return False
        if not candidate.text_draft.strip():
            return False
        content_type = ContentType(candidate.content_type)
        return content_type in self._autoapprovable_types_for_date(
            reference_date
        ) or self._is_conditional_autoapproval_window(candidate, reference_date=reference_date)

    def _is_conditional_autoapproval_window(
        self,
        candidate: ContentCandidate,
        *,
        reference_date: date,
    ) -> bool:
        content_type = ContentType(candidate.content_type)
        if content_type not in CONDITIONAL_AUTOAPPROVABLE_CONTENT_TYPES:
            return False
        if content_type == ContentType.RACE_NARRATIVE:
            return reference_date.weekday() in _RACE_NARRATIVE_ALLOWED_WEEKDAYS
        return False

    def _quality_snapshot(
        self,
        rows: list[ContentCandidate],
        *,
        reference_date: date,
    ) -> dict[int, tuple[bool, list[str]]]:
        candidate_ids = [
            row.id for row in rows if self._is_potential_autoapprovable(row, reference_date=reference_date)
        ]
        if not candidate_ids:
            return {}
        batch = self.quality_service.check_candidates(
            candidate_ids,
            dry_run=True,
            require_published=False,
        )
        return {row.id: (row.passed, list(row.errors)) for row in batch.rows}

    def _autoapprovable_types_for_date(self, target_date: date) -> tuple[ContentType, ...]:
        ordered_unique = dict.fromkeys(
            (
                *AUTOAPPROVABLE_CONTENT_TYPES,
                *self._weekday_autoapprovable_types(target_date),
            )
        )
        return tuple(ordered_unique.keys())

    def _weekday_autoapprovable_types(self, target_date: date) -> tuple[ContentType, ...]:
        if target_date.weekday() == 0:  # Monday
            return MONDAY_AUTOAPPROVABLE_CONTENT_TYPES
        if target_date.weekday() in {1, 2}:  # Tuesday, Wednesday
            return TUE_WED_AUTOAPPROVABLE_CONTENT_TYPES
        if target_date.weekday() == 3:  # Thursday
            return THURSDAY_AUTOAPPROVABLE_CONTENT_TYPES
        if target_date.weekday() == 4:  # Friday
            return FRIDAY_AUTOAPPROVABLE_CONTENT_TYPES
        return ()

    def _quality_state(
        self,
        candidate: ContentCandidate,
        *,
        quality_snapshot: dict[int, tuple[bool, list[str]]] | None,
    ) -> tuple[bool | None, list[str]]:
        if quality_snapshot is not None and candidate.id in quality_snapshot:
            passed, errors = quality_snapshot[candidate.id]
            return passed, list(errors)
        return candidate.quality_check_passed, list(candidate.quality_check_errors or [])

    def _row_to_view(
        self,
        candidate: ContentCandidate,
        *,
        autoapprovable: bool,
        policy_reason: str,
        importance_score: int | None = None,
        priority_bucket: str | None = None,
        importance_reasoning: list[str] | None = None,
    ) -> EditorialApprovalCandidateView:
        return EditorialApprovalCandidateView(
            id=candidate.id,
            competition_slug=candidate.competition_slug,
            content_type=ContentType(candidate.content_type),
            priority=candidate.priority,
            status=ContentCandidateStatus(candidate.status),
            autoapprovable=autoapprovable,
            policy_reason=policy_reason,
            autoapproved=candidate.autoapproved,
            autoapproved_at=candidate.autoapproved_at,
            autoapproval_reason=candidate.autoapproval_reason,
            importance_score=importance_score,
            priority_bucket=priority_bucket,
            importance_reasoning=list(importance_reasoning or []),
            created_at=candidate.created_at,
            excerpt=_excerpt(candidate.text_draft),
        )

    def _pending_drafts(
        self,
        *,
        reference_date: date | None,
        limit: int,
    ) -> list[ContentCandidate]:
        selected_date = reference_date or datetime.now(ZoneInfo(self.settings.timezone)).date()
        query = select(ContentCandidate).where(
            ContentCandidate.status == str(ContentCandidateStatus.DRAFT),
            ContentCandidate.reviewed_at.is_(None),
        )
        if selected_date is not None:
            _, end_utc = self._day_bounds(selected_date)
            query = query.where(
                or_(
                    ContentCandidate.created_at.is_(None),
                    ContentCandidate.created_at < end_utc,
                ),
            )
        query = query.order_by(
            ContentCandidate.priority.desc(),
            case((ContentCandidate.scheduled_at.is_(None), 1), else_=0),
            ContentCandidate.scheduled_at.asc(),
            ContentCandidate.created_at.asc(),
        )
        rows = self.session.execute(query).scalars().all()
        eligible_rows: list[ContentCandidate] = []
        filtered_ids: list[tuple[int, str]] = []
        for row in rows:
            if self.window_service.matches_release_window(row, reference_date=selected_date):
                eligible_rows.append(row)
            else:
                filtered_ids.append((row.id, row.content_type or "unknown"))
        logger.info(
            "editorial_pending_drafts",
            extra={
                "event": "editorial_pending_drafts",
                "reference_date": selected_date.isoformat() if selected_date else None,
                "rows_total": len(rows),
                "rows_eligible": len(eligible_rows),
                "rows_filtered_by_window": len(filtered_ids),
                "filtered_ids": filtered_ids[:50],
                "eligible_ids": [row.id for row in eligible_rows[:50]],
                "limit_applied": limit,
            },
        )
        return eligible_rows[:limit]

    def _day_bounds(self, target_date: date) -> tuple[datetime, datetime]:
        start_local = datetime.combine(target_date, time.min, tzinfo=ZoneInfo(self.settings.timezone))
        end_local = start_local + timedelta(days=1)
        return (
            start_local.astimezone(UTC),
            end_local.astimezone(UTC),
        )
