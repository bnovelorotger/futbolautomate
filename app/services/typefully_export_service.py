from __future__ import annotations

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.channels.typefully.client import (
    TypefullyApiClient,
    TypefullyApiError,
    TypefullyConfigurationError,
    typefully_config_presence,
)
from app.channels.typefully.publisher import (
    TypefullyPublisher,
    TypefullyPublisherValidationError,
)
from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.models import ContentCandidate
from app.schemas.typefully_export import (
    TypefullyBatchExportResult,
    TypefullyConfigStatus,
    TypefullyExportCandidateView,
    TypefullyExportResult,
)
from app.services.editorial_formatter import EditorialFormatterService
from app.utils.time import utcnow


def _excerpt(text: str, limit: int = 90) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _usable_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = text.strip()
    return normalized or None


def is_candidate_eligible_for_typefully(candidate: ContentCandidate) -> bool:
    return (
        candidate.status == str(ContentCandidateStatus.PUBLISHED)
        and candidate.external_publication_ref is None
        and bool(candidate.text_draft.strip())
    )


class TypefullyExportService:
    def __init__(
        self,
        session: Session,
        *,
        publisher: TypefullyPublisher | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.publisher = publisher or TypefullyPublisher(
            TypefullyApiClient(self.settings),
            default_social_set_id=self.settings.typefully_social_set_id,
        )
        self.formatter = EditorialFormatterService(session)

    @staticmethod
    def config_status(settings: Settings | None = None) -> TypefullyConfigStatus:
        active_settings = settings or get_settings()
        presence = typefully_config_presence(active_settings)
        return TypefullyConfigStatus(
            ready=all(presence.values()),
            has_api_key=presence["TYPEFULLY_API_KEY"],
            has_api_url=presence["TYPEFULLY_API_URL"],
            api_url=active_settings.typefully_api_url,
            social_set_id=active_settings.typefully_social_set_id,
            social_set_strategy="env" if active_settings.typefully_social_set_id else "auto_discovery",
        )

    def _candidate(self, candidate_id: int) -> ContentCandidate:
        candidate = self.session.get(ContentCandidate, candidate_id)
        if candidate is None:
            raise ConfigurationError(f"Content candidate desconocido: {candidate_id}")
        return candidate

    def _validate_candidate(self, candidate: ContentCandidate) -> None:
        if candidate.status != str(ContentCandidateStatus.PUBLISHED):
            raise InvalidStateTransitionError(
                "Solo se pueden exportar a Typefully piezas con estado interno published. "
                f"Estado actual: {candidate.status}"
            )
        if candidate.external_publication_ref:
            raise InvalidStateTransitionError(
                f"El candidato {candidate.id} ya tiene external_publication_ref={candidate.external_publication_ref}"
            )
        if not candidate.text_draft.strip():
            raise InvalidStateTransitionError(f"El candidato {candidate.id} no tiene text_draft utilizable")

    def _selected_text(
        self,
        candidate: ContentCandidate,
        *,
        prefer_rewrite: bool = True,
    ) -> tuple[str, str, bool, bool]:
        rewrite_text = _usable_text(candidate.rewritten_text)
        draft_text = _usable_text(candidate.text_draft)
        if draft_text is None:
            raise InvalidStateTransitionError(f"El candidato {candidate.id} no tiene text_draft utilizable")
        formatted_text = _usable_text(candidate.formatted_text) or _usable_text(
            self.formatter.format_candidate(candidate)
        )
        enriched_text = _usable_text(
            self.formatter.enrich_text(
                competition_slug=candidate.competition_slug,
                content_type=ContentType(candidate.content_type),
                text=formatted_text or draft_text,
                payload_json=candidate.payload_json or {},
            )
        )
        if prefer_rewrite and rewrite_text is not None:
            return rewrite_text, "rewritten_text", True, formatted_text is not None
        if not prefer_rewrite:
            return draft_text, "text_draft", rewrite_text is not None, formatted_text is not None
        if enriched_text is not None and enriched_text != (formatted_text or draft_text):
            return enriched_text, "enriched_text", rewrite_text is not None, formatted_text is not None
        if formatted_text is not None:
            return formatted_text, "formatted_text", rewrite_text is not None, True
        return draft_text, "text_draft", rewrite_text is not None, False

    def _row_to_view(
        self,
        row: ContentCandidate,
        *,
        prefer_rewrite: bool = True,
    ) -> TypefullyExportCandidateView:
        selected_text, text_source, has_rewrite, has_formatted = self._selected_text(
            row,
            prefer_rewrite=prefer_rewrite,
        )
        return TypefullyExportCandidateView(
            id=row.id,
            competition_slug=row.competition_slug,
            content_type=ContentType(row.content_type),
            priority=row.priority,
            status=ContentCandidateStatus(row.status),
            has_rewrite=has_rewrite,
            has_formatted=has_formatted,
            text_source=text_source,
            external_publication_ref=row.external_publication_ref,
            external_channel=row.external_channel,
            external_exported_at=row.external_exported_at,
            external_publication_attempted_at=row.external_publication_attempted_at,
            external_publication_error=row.external_publication_error,
            excerpt=_excerpt(selected_text),
        )

    def list_pending(
        self,
        *,
        limit: int = 50,
        prefer_rewrite: bool = True,
    ) -> list[TypefullyExportCandidateView]:
        query = (
            select(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.external_publication_ref.is_(None),
                func.length(func.trim(ContentCandidate.text_draft)) > 0,
            )
            .order_by(
                case((ContentCandidate.published_at.is_(None), 1), else_=0),
                ContentCandidate.published_at.asc(),
                ContentCandidate.priority.desc(),
                ContentCandidate.created_at.asc(),
            )
            .limit(limit)
        )
        rows = self.session.execute(query).scalars().all()
        return [self._row_to_view(row, prefer_rewrite=prefer_rewrite) for row in rows]

    def export_candidate(
        self,
        candidate_id: int,
        *,
        dry_run: bool = False,
        prefer_rewrite: bool = True,
    ) -> TypefullyExportResult:
        candidate = self._candidate(candidate_id)
        self._validate_candidate(candidate)
        selected_text, _, _, _ = self._selected_text(candidate, prefer_rewrite=prefer_rewrite)
        if dry_run:
            self.publisher.export_text(selected_text, dry_run=True)
            return TypefullyExportResult(
                dry_run=True,
                candidate=self._row_to_view(candidate, prefer_rewrite=prefer_rewrite),
            )

        attempted_at = utcnow()
        try:
            response = self.publisher.export_text(selected_text, dry_run=False)
        except (
            TypefullyApiError,
            TypefullyConfigurationError,
            TypefullyPublisherValidationError,
        ) as exc:
            candidate.external_publication_attempted_at = attempted_at
            candidate.external_publication_error = str(exc)
            self.session.add(candidate)
            self.session.flush()
            raise

        candidate.external_publication_ref = response.draft_id
        candidate.external_channel = "typefully"
        candidate.external_exported_at = response.exported_at
        candidate.external_publication_attempted_at = attempted_at
        candidate.external_publication_error = None
        self.session.add(candidate)
        self.session.flush()
        return TypefullyExportResult(
            dry_run=False,
            candidate=self._row_to_view(candidate, prefer_rewrite=prefer_rewrite),
        )

    def export_ready(
        self,
        *,
        limit: int = 20,
        dry_run: bool = False,
        prefer_rewrite: bool = True,
    ) -> TypefullyBatchExportResult:
        query = (
            select(ContentCandidate)
            .where(
                ContentCandidate.status == str(ContentCandidateStatus.PUBLISHED),
                ContentCandidate.external_publication_ref.is_(None),
                func.length(func.trim(ContentCandidate.text_draft)) > 0,
            )
            .order_by(
                case((ContentCandidate.published_at.is_(None), 1), else_=0),
                ContentCandidate.published_at.asc(),
                ContentCandidate.priority.desc(),
                ContentCandidate.created_at.asc(),
            )
            .limit(limit)
        )
        rows = self.session.execute(query).scalars().all()
        result_rows: list[TypefullyExportCandidateView] = []
        for row in rows:
            try:
                result = self.export_candidate(
                    row.id,
                    dry_run=dry_run,
                    prefer_rewrite=prefer_rewrite,
                )
            except (
                TypefullyApiError,
                TypefullyConfigurationError,
                TypefullyPublisherValidationError,
            ):
                result_rows.append(self._row_to_view(row, prefer_rewrite=prefer_rewrite))
                continue
            result_rows.append(result.candidate)
        exported_count = sum(1 for row in result_rows if row.external_publication_ref)
        if dry_run:
            exported_count = len(result_rows)
        return TypefullyBatchExportResult(
            dry_run=dry_run,
            exported_count=exported_count,
            rows=result_rows,
        )
