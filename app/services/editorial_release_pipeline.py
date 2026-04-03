from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import ContentCandidate
from app.schemas.editorial_release import EditorialReleaseResult
from app.services.editorial_approval_policy import EditorialApprovalPolicyService
from app.services.editorial_formatter import EditorialFormatterService
from app.services.editorial_quality_checks import EditorialQualityChecksService
from app.services.export_base_service import ExportBaseService
from app.services.export_json_service import ExportJsonService
from app.services.publication_dispatcher import PublicationDispatcherService


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
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.approval_service = approval_service or EditorialApprovalPolicyService(session, settings=self.settings)
        self.formatter_service = EditorialFormatterService(session, settings=self.settings)
        self.quality_service = quality_service or EditorialQualityChecksService(session, settings=self.settings)
        self.dispatch_service = dispatch_service or PublicationDispatcherService(session)
        self.export_base_service = export_base_service or ExportBaseService(session, settings=self.settings)
        self.legacy_export_service = legacy_export_service
        if self.legacy_export_service is None and self.settings.legacy_export_json_enabled:
            self.legacy_export_service = ExportJsonService(session, settings=self.settings)

    def run(
        self,
        *,
        reference_date: date | None = None,
        limit: int = 200,
        dry_run: bool = False,
        prefer_rewrite: bool | None = None,
    ) -> EditorialReleaseResult:
        if dry_run:
            with self.session.begin_nested() as nested:
                result = self._run_internal(
                    reference_date=reference_date,
                    limit=limit,
                    prefer_rewrite=prefer_rewrite,
                    export_dry_run=True,
                )
                nested.rollback()
            self.session.expire_all()
            return result.model_copy(update={"dry_run": True})
        return self._run_internal(
            reference_date=reference_date,
            limit=limit,
            prefer_rewrite=prefer_rewrite,
            export_dry_run=False,
        )

    def _run_internal(
        self,
        *,
        reference_date: date | None,
        limit: int,
        prefer_rewrite: bool | None,
        export_dry_run: bool,
    ) -> EditorialReleaseResult:
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
        ready_approved_ids = [
            row.id
            for row in self.dispatch_service.list_ready(
                include_unscheduled=True,
                limit=limit,
            )
        ]
        candidate_ids_to_dispatch = list(dict.fromkeys([*autoapproved_ids, *ready_approved_ids]))
        dispatch_result = self.dispatch_service.dispatch_candidates(
            candidate_ids_to_dispatch,
            dry_run=False,
            only_ready=True,
            include_unscheduled=True,
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
            legacy_export_json_count=legacy_export_count,
            legacy_export_json_path=legacy_export_path,
            legacy_export_blocked_series_count=legacy_export_blocked_series_count,
            legacy_export_blocked_series=legacy_export_blocked_series,
            approval_rows=approval_result.rows,
            dispatched_rows=dispatch_result.rows,
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
