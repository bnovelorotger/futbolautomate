from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.typefully_autoexport import store_typefully_autoexport_last_run
from app.schemas.editorial_release import EditorialReleaseResult
from app.services.editorial_approval_policy import EditorialApprovalPolicyService
from app.services.editorial_quality_checks import EditorialQualityChecksService
from app.services.publication_dispatcher import PublicationDispatcherService
from app.services.typefully_autoexport_service import TypefullyAutoexportService


class EditorialReleasePipelineService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        approval_service: EditorialApprovalPolicyService | None = None,
        quality_service: EditorialQualityChecksService | None = None,
        dispatch_service: PublicationDispatcherService | None = None,
        autoexport_service: TypefullyAutoexportService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.approval_service = approval_service or EditorialApprovalPolicyService(session, settings=self.settings)
        self.quality_service = quality_service or EditorialQualityChecksService(session, settings=self.settings)
        self.dispatch_service = dispatch_service or PublicationDispatcherService(session)
        self.autoexport_service = autoexport_service or TypefullyAutoexportService(session, settings=self.settings)

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
                    autoexport_dry_run=True,
                )
                nested.rollback()
            self.session.expire_all()
            return result.model_copy(update={"dry_run": True})
        return self._run_internal(
            reference_date=reference_date,
            limit=limit,
            prefer_rewrite=prefer_rewrite,
            autoexport_dry_run=False,
        )

    def _run_internal(
        self,
        *,
        reference_date: date | None,
        limit: int,
        prefer_rewrite: bool | None,
        autoexport_dry_run: bool,
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
        dispatch_result = self.dispatch_service.dispatch_candidates(
            autoapproved_ids,
            dry_run=False,
        )
        published_ids = [row.id for row in dispatch_result.rows]
        autoexport_result = self.autoexport_service.run_for_candidates(
            published_ids,
            dry_run=autoexport_dry_run,
            prefer_rewrite=prefer_rewrite,
        )
        store_typefully_autoexport_last_run(autoexport_result)
        return EditorialReleaseResult(
            dry_run=autoexport_dry_run,
            reference_date=reference_date,
            drafts_found=approval_result.drafts_found,
            autoapprovable_count=approval_result.autoapprovable_count,
            autoapproved_count=approval_result.autoapproved_count,
            manual_review_count=approval_result.manual_review_count,
            dispatched_count=dispatch_result.dispatched_count,
            autoexport_scanned_count=autoexport_result.scanned_count,
            autoexport_eligible_count=autoexport_result.eligible_count,
            autoexport_exported_count=autoexport_result.exported_count,
            autoexport_blocked_count=autoexport_result.blocked_count,
            autoexport_failed_count=autoexport_result.failed_count,
            approval_rows=approval_result.rows,
            dispatched_rows=dispatch_result.rows,
            autoexport_rows=autoexport_result.rows,
        )
