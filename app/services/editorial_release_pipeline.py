from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import ContentCandidate
from app.schemas.editorial_release import EditorialReleaseResult
from app.services.editorial_approval_policy import EditorialApprovalPolicyService
from app.services.editorial_formatter import EditorialFormatterService
from app.services.editorial_phase import EditorialPhaseService
from app.services.editorial_quality_checks import EditorialQualityChecksService
from app.services.export_base_service import ExportBaseService
from app.services.export_json_service import ExportJsonService
from app.services.publication_dispatcher import PublicationDispatcherService, is_candidate_ready_for_dispatch
from app.services.typefully_publication_service import TypefullyPublicationService
from app.services.x_browser_publication_service import XBrowserPublicationService
from app.services.x_publication_scheduler import PublicationSlot, load_publication_schedule
from app.services.x_publication_service import XPublicationService

logger = logging.getLogger(__name__)

_PUBLICATION_DAY_KEYS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")


class EditorialReleasePipelineService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        approval_service: EditorialApprovalPolicyService | None = None,
        quality_service: EditorialQualityChecksService | None = None,
        dispatch_service: PublicationDispatcherService | None = None,
        export_base_service: ExportBaseService | None = None,
        legacy_export_service: ExportJsonService | None = None,
        x_publication_service: XPublicationService | None = None,
        typefully_publication_service: TypefullyPublicationService | None = None,
        x_browser_publication_service: XBrowserPublicationService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.approval_service = approval_service or EditorialApprovalPolicyService(session, settings=self.settings)
        self.phase_service = EditorialPhaseService(session, settings=self.settings)
        self.formatter_service = EditorialFormatterService(session, settings=self.settings)
        self.quality_service = quality_service or EditorialQualityChecksService(session, settings=self.settings)
        self.dispatch_service = dispatch_service or PublicationDispatcherService(session)
        self.export_base_service = export_base_service or ExportBaseService(session, settings=self.settings)
        self.legacy_export_service = legacy_export_service
        # The API publisher remains injectable for manual compatibility flows,
        # but release no longer uses it as an operational path.
        self.x_publication_service = x_publication_service
        if typefully_publication_service is not None:
            self.typefully_publication_service: TypefullyPublicationService | None = typefully_publication_service
        elif self.settings.typefully_api_key:
            self.typefully_publication_service = TypefullyPublicationService(session)
        else:
            self.typefully_publication_service = None
        self.x_browser_publication_service: XBrowserPublicationService | None = (
            x_browser_publication_service or XBrowserPublicationService(session, settings=self.settings)
        )
        if self.legacy_export_service is None and self.settings.legacy_export_json_enabled:
            self.legacy_export_service = ExportJsonService(session, settings=self.settings)

    def run(
        self,
        *,
        reference_date: date | None = None,
        limit: int = 200,
        dry_run: bool = False,
        prefer_rewrite: bool | None = None,
        publish_to_x: bool = False,
        publish_via_typefully: bool = False,
        publish_via_browser: bool = False,
        publish_limit: int | None = None,
    ) -> EditorialReleaseResult:
        # publish_limit caps the browser publish batch only (per-slot quota from the
        # Task Scheduler). limit caps the evaluation/approval pool. They must stay
        # independent — collapsing them caused approval to ignore wed candidates
        # whenever the scheduler imposed a low publish quota (e.g. -Limit 4).
        if dry_run:
            with self.session.begin_nested() as nested:
                result = self._run_internal(
                    reference_date=reference_date,
                    limit=limit,
                    prefer_rewrite=prefer_rewrite,
                    export_dry_run=True,
                    publish_to_x=publish_to_x,
                    publish_via_typefully=publish_via_typefully,
                    publish_via_browser=publish_via_browser,
                    publish_limit=publish_limit,
                )
                nested.rollback()
            self.session.expire_all()
            return result.model_copy(update={"dry_run": True})
        return self._run_internal(
            reference_date=reference_date,
            limit=limit,
            prefer_rewrite=prefer_rewrite,
            export_dry_run=False,
            publish_to_x=publish_to_x,
            publish_via_typefully=publish_via_typefully,
            publish_via_browser=publish_via_browser,
            publish_limit=publish_limit,
        )

    def _run_internal(
        self,
        *,
        reference_date: date | None,
        limit: int,
        prefer_rewrite: bool | None,
        export_dry_run: bool,
        publish_to_x: bool,
        publish_via_typefully: bool = False,
        publish_via_browser: bool = False,
        publish_limit: int | None = None,
    ) -> EditorialReleaseResult:
        browser_publish_enabled = publish_to_x or publish_via_browser
        schedule_publish_limit = self._browser_slot_publish_limit(reference_date) if browser_publish_enabled else None
        release_action_limit = self._release_action_limit(
            limit=limit,
            publish_limit=publish_limit,
            schedule_publish_limit=schedule_publish_limit,
        )
        quality_candidate_ids = self.approval_service.candidate_ids_for_quality_precheck(
            reference_date=reference_date,
            limit=limit,
        )
        if quality_candidate_ids:
            self.quality_service.check_candidates(
                quality_candidate_ids,
                dry_run=False,
                prefer_rewrite=prefer_rewrite,
                require_published=False,
            )
        approval_result = self.approval_service.autoapprove(
            reference_date=reference_date,
            limit=limit,
            dry_run=False,
        )
        autoapproved_ids = [row.id for row in approval_result.rows if row.autoapprovable]
        # Rescue path for orphaned APPROVED candidates: any candidate that was
        # approved in a previous run but never reached PUBLISHED (e.g. the prior
        # release crashed between dispatch and commit) is picked up here.
        ready_approved_ids = [
            row.id
            for row in self.dispatch_service.list_ready(
                include_unscheduled=True,
                limit=limit,
            )
        ]
        rescue_only_ids = [cid for cid in ready_approved_ids if cid not in autoapproved_ids]
        if rescue_only_ids:
            logger.warning(
                "editorial_release_rescue",
                extra={
                    "event": "editorial_release_rescue",
                    "rescued_approved_ids": rescue_only_ids,
                    "note": "approved candidates from a previous run reached dispatch only now",
                },
            )
        candidate_ids_to_dispatch = list(dict.fromkeys([*autoapproved_ids, *ready_approved_ids]))
        deferred_approved_ids: list[int] = []
        if browser_publish_enabled:
            dispatch_selection = self._select_browser_slot_dispatch_ids(
                candidate_ids_to_dispatch,
                reference_date=reference_date,
                dispatch_limit=release_action_limit,
            )
            candidate_ids_to_dispatch = dispatch_selection["selected_ids"]
            deferred_approved_ids = dispatch_selection["deferred_ids"]
        dispatch_result = self.dispatch_service.dispatch_candidates(
            candidate_ids_to_dispatch,
            dry_run=False,
            only_ready=True,
            include_unscheduled=True,
        )
        logger.info(
            "editorial_release_phase",
            extra={
                "event": "editorial_release_phase",
                "reference_date": reference_date.isoformat() if reference_date else None,
                "limit": limit,
                "dry_run": export_dry_run,
                "quality_precheck_ids": quality_candidate_ids,
                "drafts_found": approval_result.drafts_found,
                "autoapprovable_count": approval_result.autoapprovable_count,
                "autoapproved_ids": autoapproved_ids,
                "ready_approved_rescue_ids": ready_approved_ids,
                "slot_dispatch_cap": release_action_limit if browser_publish_enabled else None,
                "slot_dispatch_selected_ids": candidate_ids_to_dispatch,
                "approved_deferred_ids": deferred_approved_ids,
                "quality_blocked_ids": [
                    row.id for row in approval_result.rows if row.policy_reason == "quality_errors_present"
                ],
                "ids_to_dispatch": candidate_ids_to_dispatch,
                "dispatched_count": dispatch_result.dispatched_count,
                "dispatched_ids": [row.id for row in dispatch_result.rows],
            },
        )
        self._hydrate_formatted_text(published_ids=[row.id for row in dispatch_result.rows])
        export_base_result = self.export_base_service.generate_export_file(
            reference_date=reference_date,
            dry_run=export_dry_run,
        )
        legacy_export_count = 0
        legacy_export_path: str | None = None
        legacy_export_blocked_series_count = 0
        legacy_export_blocked_series = []
        legacy_export_rows = []
        if self.legacy_export_service is not None:
            legacy_export_result = self.legacy_export_service.generate_export_file(
                reference_date=reference_date,
                dry_run=export_dry_run,
                prefer_rewrite=prefer_rewrite,
            )
            legacy_export_count = legacy_export_result.generated_count
            legacy_export_path = legacy_export_result.path
            legacy_export_blocked_series_count = legacy_export_result.blocked_series_count
            legacy_export_blocked_series = legacy_export_result.blocked_series
            legacy_export_rows = legacy_export_result.rows
        browser_publish_enabled = publish_to_x or publish_via_browser
        browser_publish_result = None
        browser_publication_rows = []
        if browser_publish_enabled and self.x_browser_publication_service is not None:
            # Release should publish the current scheduled batch, not rescue old stranded items.
            # Rescue flows belong to the dedicated browser retry path.
            browser_publish_result = self.x_browser_publication_service.publish_selected_pending(
                candidate_ids_to_dispatch,
                limit=release_action_limit,
                dry_run=export_dry_run,
                bypass_schedule=False,
            )
            browser_publication_rows = self.x_browser_publication_service.build_views_from_batch_result(
                browser_publish_result
            )
        typefully_result = None
        if publish_via_typefully and self.typefully_publication_service is not None and dispatch_result.rows:
            typefully_result = self.typefully_publication_service.publish_pending(
                dry_run=export_dry_run,
            )
        return EditorialReleaseResult(
            dry_run=export_dry_run,
            reference_date=reference_date,
            drafts_found=approval_result.drafts_found,
            autoapprovable_count=approval_result.autoapprovable_count,
            autoapproved_count=approval_result.autoapproved_count,
            manual_review_count=approval_result.manual_review_count,
            dispatched_count=dispatch_result.dispatched_count,
            export_base_total_items=export_base_result.total_items,
            export_base_path=export_base_result.path,
            x_publish_enabled=browser_publish_enabled,
            x_published_count=browser_publish_result.published_count if browser_publish_result is not None else 0,
            typefully_publish_enabled=publish_via_typefully,
            typefully_published_count=typefully_result.published_count if typefully_result is not None else 0,
            legacy_export_json_count=legacy_export_count,
            legacy_export_json_path=legacy_export_path,
            legacy_export_blocked_series_count=legacy_export_blocked_series_count,
            legacy_export_blocked_series=legacy_export_blocked_series,
            approval_rows=approval_result.rows,
            dispatched_rows=dispatch_result.rows,
            x_publication_rows=browser_publication_rows,
            legacy_export_json_rows=legacy_export_rows,
        )

    def _hydrate_formatted_text(self, *, published_ids: list[int]) -> None:
        for candidate_id in published_ids:
            candidate = self.session.get(ContentCandidate, candidate_id)
            if candidate is None:
                continue
            if (candidate.formatted_text or "").strip():
                continue
            layers = self.formatter_service.build_text_layers_for_candidate(candidate)
            formatted_text = (layers.formatted_text or "").strip()
            if not formatted_text:
                continue
            candidate.formatted_text = layers.formatted_text
            self.session.add(candidate)
        if published_ids:
            self.session.flush()

    def _release_action_limit(
        self,
        *,
        limit: int,
        publish_limit: int | None,
        schedule_publish_limit: int | None,
    ) -> int:
        if publish_limit is not None:
            effective_publish_limit = max(int(publish_limit), 1)
        elif schedule_publish_limit is not None:
            effective_publish_limit = max(int(schedule_publish_limit), 1)
        else:
            effective_publish_limit = max(int(limit), 1)
        return min(max(int(self.settings.x_browser_release_action_limit), 1), effective_publish_limit)

    def _select_browser_slot_dispatch_ids(
        self,
        candidate_ids: list[int],
        *,
        reference_date: date | None,
        dispatch_limit: int,
    ) -> dict[str, list[int]]:
        if not candidate_ids:
            return {"selected_ids": [], "deferred_ids": []}

        selected_date, slot_now, allowed_types = self._browser_slot_context(reference_date)
        rows = self._candidate_rows_for_dispatch(candidate_ids)
        eligible_rows: list[ContentCandidate] = []
        deferred_ids: list[int] = []
        deferred_reasons: list[tuple[int, str]] = []
        for row in rows:
            if row.content_type not in allowed_types:
                deferred_ids.append(row.id)
                deferred_reasons.append((row.id, "not_in_publication_schedule"))
                continue
            if not self.phase_service.is_candidate_allowed(row, reference_date=selected_date):
                deferred_ids.append(row.id)
                deferred_reasons.append((row.id, "phase_content_type_blocked"))
                continue
            if not self.approval_service.window_service.matches_release_window(row, reference_date=selected_date):
                deferred_ids.append(row.id)
                deferred_reasons.append((row.id, "outside_release_window"))
                continue
            if not is_candidate_ready_for_dispatch(row, slot_now, include_unscheduled=True):
                deferred_ids.append(row.id)
                deferred_reasons.append((row.id, "not_ready_for_dispatch"))
                continue
            eligible_rows.append(row)

        selected_rows = eligible_rows[:dispatch_limit]
        selected_ids = [row.id for row in selected_rows]
        overflow_ids = [row.id for row in eligible_rows[dispatch_limit:]]
        deferred_ids.extend(overflow_ids)
        deferred_reasons.extend((candidate_id, "slot_publish_limit") for candidate_id in overflow_ids)
        logger.info(
            "editorial_release_slot_selection",
            extra={
                "event": "editorial_release_slot_selection",
                "reference_date": selected_date.isoformat(),
                "slot_now": slot_now.isoformat(),
                "dispatch_limit": dispatch_limit,
                "candidate_ids": candidate_ids,
                "allowed_types": sorted(allowed_types),
                "eligible_ids": [row.id for row in eligible_rows],
                "selected_ids": selected_ids,
                "deferred_ids": deferred_ids,
                "deferred_reasons": deferred_reasons,
            },
        )
        return {"selected_ids": selected_ids, "deferred_ids": deferred_ids}

    def _browser_slot_context(self, reference_date: date | None) -> tuple[date, datetime, set[str]]:
        selected_date, slot_now, active_slot = self._browser_active_slot(reference_date)
        if active_slot is None:
            return selected_date, slot_now, set()
        return selected_date, slot_now, set(active_slot.types)

    def _browser_slot_publish_limit(self, reference_date: date | None) -> int | None:
        _, _, active_slot = self._browser_active_slot(reference_date)
        if active_slot is None:
            return None
        return active_slot.publish_limit

    def _browser_active_slot(self, reference_date: date | None) -> tuple[date, datetime, PublicationSlot | None]:
        timezone = ZoneInfo(self.settings.timezone)
        schedule = load_publication_schedule()
        if reference_date is None:
            current = datetime.now(timezone)
            selected_date = current.date()
            slot_now = current
        else:
            selected_date = reference_date
            day_key = _PUBLICATION_DAY_KEYS[selected_date.weekday()]
            day_schedule = schedule.day(day_key)
            if day_schedule is None:
                slot_now = datetime.combine(selected_date, datetime.min.time(), tzinfo=timezone)
            else:
                slot_now = datetime.combine(selected_date, day_schedule.last_slot().publish_after, tzinfo=timezone)

        day_key = _PUBLICATION_DAY_KEYS[selected_date.weekday()]
        day_schedule = schedule.day(day_key)
        if day_schedule is None:
            return selected_date, slot_now, None
        active_slot = day_schedule.active_slot_at(slot_now.time())
        return selected_date, slot_now, active_slot

    def _candidate_rows_for_dispatch(self, candidate_ids: list[int]) -> list[ContentCandidate]:
        rows = list(
            self.session.execute(select(ContentCandidate).where(ContentCandidate.id.in_(candidate_ids))).scalars().all()
        )
        candidate_id_set = set(candidate_ids)
        rows = [row for row in rows if row.id in candidate_id_set]
        return sorted(
            rows,
            key=lambda row: (
                -int(row.priority or 0),
                self._sort_datetime(row.created_at),
                row.id,
            ),
        )

    def _sort_datetime(self, value: datetime | None) -> datetime:
        if value is None:
            return datetime.min.replace(tzinfo=UTC)
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
