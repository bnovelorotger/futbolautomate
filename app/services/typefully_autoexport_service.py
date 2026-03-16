from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.channels.typefully.client import TypefullyApiError, TypefullyConfigurationError
from app.channels.typefully.publisher import TypefullyPublisherValidationError
from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.core.typefully_autoexport import (
    load_typefully_autoexport_last_run,
    load_typefully_autoexport_policy,
)
from app.db.models import ContentCandidate
from app.schemas.typefully_autoexport import (
    TypefullyAutoexportCandidateView,
    TypefullyAutoexportLastRun,
    TypefullyAutoexportPolicy,
    TypefullyAutoexportRunResult,
    TypefullyAutoexportStatusView,
)
from app.services.editorial_quality_checks import EditorialQualityChecksService
from app.services.typefully_export_service import TypefullyExportService
from app.utils.time import utcnow

_CAPACITY_ERROR_PREFIX = "capacity_deferred:"


class TypefullyAutoexportService:
    def __init__(
        self,
        session: Session,
        *,
        export_service: TypefullyExportService | None = None,
        policy: TypefullyAutoexportPolicy | None = None,
        settings: Settings | None = None,
        quality_service: EditorialQualityChecksService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.export_service = export_service or TypefullyExportService(session, settings=self.settings)
        self.policy = policy or load_typefully_autoexport_policy()
        self.quality_service = quality_service or EditorialQualityChecksService(
            session,
            export_service=self.export_service,
            settings=self.settings,
            policy=self.policy,
        )

    def list_candidates(
        self,
        *,
        reference_date: date | None = None,
        limit: int | None = None,
        prefer_rewrite: bool | None = None,
    ) -> list[TypefullyAutoexportCandidateView]:
        active_limit = limit or self.policy.default_limit
        rewrite_preference = self.policy.use_rewrite_by_default if prefer_rewrite is None else prefer_rewrite
        rows = self._pending_candidates(reference_date=reference_date, limit=active_limit)
        return [self._row_to_view(row, prefer_rewrite=rewrite_preference) for row in rows]

    def run(
        self,
        *,
        dry_run: bool = False,
        reference_date: date | None = None,
        limit: int | None = None,
        prefer_rewrite: bool | None = None,
    ) -> TypefullyAutoexportRunResult:
        active_limit = limit or self.policy.default_limit
        rewrite_preference = self.policy.use_rewrite_by_default if prefer_rewrite is None else prefer_rewrite
        rows = self._pending_candidates(reference_date=reference_date, limit=active_limit)
        return self._run_rows(
            rows,
            dry_run=dry_run,
            reference_date=reference_date,
            prefer_rewrite=rewrite_preference,
        )

    def run_for_candidates(
        self,
        candidate_ids: list[int],
        *,
        dry_run: bool = False,
        prefer_rewrite: bool | None = None,
    ) -> TypefullyAutoexportRunResult:
        rewrite_preference = self.policy.use_rewrite_by_default if prefer_rewrite is None else prefer_rewrite
        rows = self._pending_candidates_by_ids(candidate_ids)
        return self._run_rows(
            rows,
            dry_run=dry_run,
            reference_date=None,
            prefer_rewrite=rewrite_preference,
        )

    def list_pending_capacity(
        self,
        *,
        limit: int | None = None,
        prefer_rewrite: bool | None = None,
    ) -> list[TypefullyAutoexportCandidateView]:
        active_limit = limit or self.policy.default_limit
        rewrite_preference = self.policy.use_rewrite_by_default if prefer_rewrite is None else prefer_rewrite
        rows = self._capacity_deferred_candidates(limit=active_limit)
        views: list[TypefullyAutoexportCandidateView] = []
        for row in rows:
            view = self._row_to_view(row, prefer_rewrite=rewrite_preference)
            view.export_outcome = "capacity_deferred"
            view.policy_reason = row.external_publication_error or "capacity_deferred"
            views.append(view)
        return views

    def _run_rows(
        self,
        rows: list[ContentCandidate],
        *,
        dry_run: bool,
        reference_date: date | None,
        prefer_rewrite: bool,
    ) -> TypefullyAutoexportRunResult:
        result_rows: list[TypefullyAutoexportCandidateView] = []
        eligible_count = 0
        exported_count = 0
        capacity_deferred_count = 0
        failed_count = 0
        capacity_limit_reached = False
        capacity_limit_reason: str | None = None
        remaining_capacity = self._remaining_capacity(reference_date)
        capacity_stop = False

        for row in rows:
            view = self._row_to_view(row, prefer_rewrite=prefer_rewrite)
            if not view.autoexport_allowed:
                self._clear_capacity_deferred_marker(row, persist=not dry_run)
                view.external_publication_error = row.external_publication_error
                view.export_outcome = "blocked_policy"
                result_rows.append(view)
                continue

            quality_detail = self.quality_service._check_candidate(
                row,
                prefer_rewrite=prefer_rewrite,
                persist=not dry_run,
            )
            view.quality_check_passed = quality_detail.passed
            view.quality_check_errors = list(quality_detail.errors)
            if not quality_detail.passed:
                self._clear_capacity_deferred_marker(row, persist=not dry_run)
                view.autoexport_allowed = False
                view.policy_reason = "quality_check_failed"
                view.external_publication_error = row.external_publication_error
                view.export_outcome = "blocked_policy"
                result_rows.append(view)
                continue

            eligible_count += 1
            if capacity_stop or (remaining_capacity is not None and remaining_capacity <= 0):
                defer_reason = capacity_limit_reason or self._capacity_limit_reason(reference_date)
                self._mark_capacity_deferred(row, defer_reason, persist=not dry_run)
                deferred_view = self._row_to_view(row, prefer_rewrite=prefer_rewrite)
                deferred_view.quality_check_passed = True
                deferred_view.quality_check_errors = []
                deferred_view.export_outcome = "capacity_deferred"
                deferred_view.policy_reason = defer_reason
                result_rows.append(deferred_view)
                capacity_deferred_count += 1
                capacity_limit_reached = True
                capacity_limit_reason = defer_reason
                if self.policy.stop_on_capacity_limit:
                    capacity_stop = True
                continue

            if dry_run:
                exported_count += 1
                if remaining_capacity is not None:
                    remaining_capacity -= 1
                    if remaining_capacity <= 0 and self.policy.stop_on_capacity_limit:
                        capacity_stop = True
                view.export_outcome = "dry_run_export"
                result_rows.append(view)
                continue

            try:
                export_result = self.export_service.export_candidate(
                    row.id,
                    dry_run=False,
                    prefer_rewrite=prefer_rewrite,
                )
            except (
                TypefullyApiError,
                TypefullyConfigurationError,
                TypefullyPublisherValidationError,
            ) as exc:
                if self._is_capacity_error(exc):
                    defer_reason = self._capacity_error_reason(exc)
                    self._mark_capacity_deferred(row, defer_reason, persist=True)
                    deferred_view = self._row_to_view(row, prefer_rewrite=prefer_rewrite)
                    deferred_view.quality_check_passed = True
                    deferred_view.quality_check_errors = []
                    deferred_view.export_outcome = "capacity_deferred"
                    deferred_view.policy_reason = defer_reason
                    result_rows.append(deferred_view)
                    capacity_deferred_count += 1
                    capacity_limit_reached = True
                    capacity_limit_reason = defer_reason
                    if self.policy.stop_on_capacity_limit:
                        capacity_stop = True
                    continue
                failed_count += 1
                failure_view = self._row_to_view(row, prefer_rewrite=prefer_rewrite)
                failure_view.export_outcome = "failed_technical"
                failure_view.policy_reason = f"export_failed:{exc}"
                result_rows.append(failure_view)
                continue

            exported_count += 1
            if remaining_capacity is not None:
                remaining_capacity -= 1
                if remaining_capacity <= 0 and self.policy.stop_on_capacity_limit:
                    capacity_stop = True
            result_rows.append(
                TypefullyAutoexportCandidateView(
                    id=export_result.candidate.id,
                    competition_slug=export_result.candidate.competition_slug,
                    content_type=export_result.candidate.content_type,
                    priority=export_result.candidate.priority,
                    status=export_result.candidate.status,
                    autoexport_allowed=True,
                    policy_reason="autoexport_allowed",
                    quality_check_passed=True,
                    quality_check_errors=[],
                    export_outcome="exported",
                    has_rewrite=export_result.candidate.has_rewrite,
                    text_source=export_result.candidate.text_source,
                    external_publication_ref=export_result.candidate.external_publication_ref,
                    external_publication_error=export_result.candidate.external_publication_error,
                    excerpt=export_result.candidate.excerpt,
                )
            )

        return TypefullyAutoexportRunResult(
            executed_at=utcnow(),
            dry_run=dry_run,
            policy_enabled=self.policy.enabled,
            phase=self.policy.phase,
            reference_date=reference_date,
            scanned_count=len(rows),
            eligible_count=eligible_count,
            exported_count=exported_count,
            blocked_count=sum(1 for row in result_rows if not row.autoexport_allowed),
            capacity_deferred_count=capacity_deferred_count,
            failed_count=failed_count,
            capacity_limit_reached=capacity_limit_reached,
            capacity_limit_reason=capacity_limit_reason,
            rows=result_rows,
        )

    def status(self) -> TypefullyAutoexportStatusView:
        last_run = load_typefully_autoexport_last_run()
        return TypefullyAutoexportStatusView(
            enabled=self.policy.enabled,
            phase=self.policy.phase,
            max_exports_per_run=self.policy.max_exports_per_run,
            max_exports_per_day=self.policy.max_exports_per_day,
            stop_on_capacity_limit=self.policy.stop_on_capacity_limit,
            capacity_error_codes=list(self.policy.capacity_error_codes),
            allowed_content_types=self.policy.active_allowed_content_types(),
            validation_required_content_types=self.policy.active_validation_required_content_types(),
            manual_review_content_types=list(self.policy.manual_review_content_types),
            pending_capacity_count=self._pending_capacity_count(),
            pending_normal_count=self._pending_normal_count(),
            last_run=TypefullyAutoexportLastRun.model_validate(last_run.model_dump()) if last_run else None,
        )

    def _row_to_view(
        self,
        row: ContentCandidate,
        *,
        prefer_rewrite: bool,
    ) -> TypefullyAutoexportCandidateView:
        export_view = self.export_service._row_to_view(row, prefer_rewrite=prefer_rewrite)
        content_type = ContentType(row.content_type)
        if not self.policy.enabled:
            policy_reason = "policy_disabled"
            allowed = False
        elif self.policy.allows(content_type):
            policy_reason = (
                "quality_validation_required"
                if self.policy.requires_validation(content_type)
                else "autoexport_allowed"
            )
            allowed = True
        elif content_type in self.policy.manual_review_content_types:
            policy_reason = "manual_review_policy"
            allowed = False
        else:
            policy_reason = f"phase_{self.policy.phase}_not_allowed"
            allowed = False
        return TypefullyAutoexportCandidateView(
            id=export_view.id,
            competition_slug=export_view.competition_slug,
            content_type=export_view.content_type,
            priority=export_view.priority,
            status=export_view.status,
            autoexport_allowed=allowed,
            policy_reason=policy_reason,
            quality_check_passed=row.quality_check_passed,
            quality_check_errors=list(row.quality_check_errors or []),
            export_outcome="blocked_policy" if not allowed else "pending",
            has_rewrite=export_view.has_rewrite,
            text_source=export_view.text_source,
            external_publication_ref=export_view.external_publication_ref,
            external_publication_error=export_view.external_publication_error,
            excerpt=export_view.excerpt,
        )

    def _pending_candidates(
        self,
        *,
        reference_date: date | None,
        limit: int,
    ) -> list[ContentCandidate]:
        query = select(ContentCandidate).where(
            ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
            ContentCandidate.external_publication_ref.is_(None),
            func.length(func.trim(ContentCandidate.text_draft)) > 0,
        )
        if reference_date is not None:
            start_utc, end_utc = self._day_bounds(reference_date)
            query = query.where(
                ContentCandidate.published_at.is_not(None),
                ContentCandidate.published_at >= start_utc,
                ContentCandidate.published_at < end_utc,
            )
        query = query.order_by(
            case((ContentCandidate.published_at.is_(None), 1), else_=0),
            ContentCandidate.published_at.asc(),
            ContentCandidate.priority.desc(),
            ContentCandidate.created_at.asc(),
        ).limit(limit)
        return self.session.execute(query).scalars().all()

    def _pending_candidates_by_ids(self, candidate_ids: list[int]) -> list[ContentCandidate]:
        if not candidate_ids:
            return []
        query = (
            select(ContentCandidate)
            .where(
                ContentCandidate.id.in_(candidate_ids),
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.external_publication_ref.is_(None),
                func.length(func.trim(ContentCandidate.text_draft)) > 0,
            )
            .order_by(
                ContentCandidate.priority.desc(),
                ContentCandidate.created_at.asc(),
            )
        )
        return self.session.execute(query).scalars().all()

    def _capacity_deferred_candidates(self, *, limit: int) -> list[ContentCandidate]:
        capacity_filter = self._capacity_filter_expression()
        query = (
            select(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.external_publication_ref.is_(None),
                capacity_filter,
                func.length(func.trim(ContentCandidate.text_draft)) > 0,
            )
            .order_by(ContentCandidate.priority.desc(), ContentCandidate.created_at.asc())
            .limit(limit)
        )
        return self.session.execute(query).scalars().all()

    def _pending_capacity_count(self) -> int:
        capacity_filter = self._capacity_filter_expression()
        query = select(func.count()).select_from(ContentCandidate).where(
            ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
            ContentCandidate.external_publication_ref.is_(None),
            capacity_filter,
            func.length(func.trim(ContentCandidate.text_draft)) > 0,
        )
        return int(self.session.scalar(query) or 0)

    def _pending_normal_count(self) -> int:
        capacity_filter = self._capacity_filter_expression()
        query = select(func.count()).select_from(ContentCandidate).where(
            ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
            ContentCandidate.external_publication_ref.is_(None),
            func.length(func.trim(ContentCandidate.text_draft)) > 0,
            or_(
                ContentCandidate.external_publication_error.is_(None),
                ~capacity_filter,
            ),
        )
        return int(self.session.scalar(query) or 0)

    def _remaining_capacity(self, reference_date: date | None) -> int | None:
        capacities: list[int] = []
        if self.policy.max_exports_per_run is not None:
            capacities.append(self.policy.max_exports_per_run)
        daily_capacity = self._remaining_daily_capacity(reference_date)
        if daily_capacity is not None:
            capacities.append(daily_capacity)
        if not capacities:
            return None
        return max(0, min(capacities))

    def _remaining_daily_capacity(self, reference_date: date | None) -> int | None:
        if self.policy.max_exports_per_day is None:
            return None
        capacity_date = reference_date or datetime.now(ZoneInfo(self.settings.timezone)).date()
        start_utc, end_utc = self._day_bounds(capacity_date)
        exported_today = int(
            self.session.scalar(
                select(func.count()).select_from(ContentCandidate).where(
                    ContentCandidate.external_channel == "typefully",
                    ContentCandidate.external_publication_ref.is_not(None),
                    ContentCandidate.external_exported_at.is_not(None),
                    ContentCandidate.external_exported_at >= start_utc,
                    ContentCandidate.external_exported_at < end_utc,
                )
            )
            or 0
        )
        return max(0, self.policy.max_exports_per_day - exported_today)

    def _capacity_limit_reason(self, reference_date: date | None) -> str:
        if self.policy.max_exports_per_day is not None:
            remaining_daily = self._remaining_daily_capacity(reference_date)
            if remaining_daily == 0:
                return "capacity_deferred:max_exports_per_day"
        return "capacity_deferred:max_exports_per_run"

    def _mark_capacity_deferred(
        self,
        candidate: ContentCandidate,
        reason: str,
        *,
        persist: bool,
    ) -> None:
        if not persist:
            return
        candidate.external_publication_error = reason
        self.session.add(candidate)
        self.session.flush()

    def _clear_capacity_deferred_marker(self, candidate: ContentCandidate, *, persist: bool) -> None:
        error = candidate.external_publication_error or ""
        if not self._is_capacity_deferred_error_text(error):
            return
        if not persist:
            return
        candidate.external_publication_error = None
        self.session.add(candidate)
        self.session.flush()

    def _is_capacity_error(
        self,
        error: TypefullyApiError | TypefullyConfigurationError | TypefullyPublisherValidationError,
    ) -> bool:
        if not isinstance(error, TypefullyApiError):
            return False
        configured_codes = {code.strip().upper() for code in self.policy.capacity_error_codes if code.strip()}
        if error.error_code and error.error_code.strip().upper() in configured_codes:
            return True
        message = str(error).upper()
        return any(code in message for code in configured_codes)

    def _capacity_error_reason(self, error: TypefullyApiError) -> str:
        code = (error.error_code or "").strip().upper()
        if code:
            return f"{_CAPACITY_ERROR_PREFIX}{code}"
        return f"{_CAPACITY_ERROR_PREFIX}channel_limit"

    def _capacity_filter_expression(self):
        clauses = [ContentCandidate.external_publication_error.like(f"{_CAPACITY_ERROR_PREFIX}%")]
        for code in self.policy.capacity_error_codes:
            normalized = code.strip()
            if normalized:
                clauses.append(ContentCandidate.external_publication_error.like(f"%{normalized}%"))
        return or_(*clauses)

    def _is_capacity_deferred_error_text(self, error: str) -> bool:
        normalized = error.strip().upper()
        if normalized.startswith(_CAPACITY_ERROR_PREFIX.upper()):
            return True
        return any(code.strip().upper() in normalized for code in self.policy.capacity_error_codes if code.strip())

    def _day_bounds(self, target_date: date) -> tuple[datetime, datetime]:
        timezone_name = self.settings.timezone
        start_local = datetime.combine(target_date, time.min, tzinfo=ZoneInfo(timezone_name))
        end_local = start_local + timedelta(days=1)
        return (
            start_local.astimezone(timezone.utc),
            end_local.astimezone(timezone.utc),
        )
