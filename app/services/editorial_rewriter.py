from __future__ import annotations

import json

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import ContentCandidateStatus, ContentType
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.models import ContentCandidate
from app.llm.providers import build_editorial_rewrite_provider, editorial_rewrite_provider_ready
from app.llm.providers.base import LLMConfigurationError, LLMProviderError
from app.llm.schemas import EditorialRewriteLLMRequest
from app.schemas.editorial_rewrite import (
    EditorialRewriteBatchResult,
    EditorialRewriteCandidateDetail,
    EditorialRewriteCandidateView,
    EditorialRewriteResult,
)
from app.utils.time import utcnow

ALLOWED_REWRITE_STATUSES = {
    ContentCandidateStatus.DRAFT,
    ContentCandidateStatus.APPROVED,
    ContentCandidateStatus.PUBLISHED,
}

COMMON_POLICY = """Eres el editor de estilo de uFutbolBalear.
Tu trabajo es reescribir un borrador breve ya calculado por el sistema.

Reglas obligatorias:
- Mantener exactos todos los datos del borrador y de los hechos estructurados.
- No inventar datos, contexto, lesiones, rachas, valoraciones ni antecedentes.
- No recalcular datos ni corregirlos con conocimiento externo.
- No anadir opinion, hype, clickbait, ironia, emojis ni hashtags.
- Tono directo, periodistico, limpio y breve.
- Texto apto para Typefully/X.
- Maximo {max_chars} caracteres.
- Si el borrador ya esta bien, haz solo una mejora ligera.
- Devuelve solo JSON con la clave rewritten_text.
"""

TYPE_SPECIFIC_GUIDANCE = {
    ContentType.MATCH_RESULT: (
        "Abre con el resultado final y deja muy claro el partido y la competicion. "
        "No cambies marcadores, equipos, jornada ni estado."
    ),
    ContentType.STANDINGS: (
        "Prioriza claridad y lectura rapida de posiciones y puntos. "
        "No alteres ranking, orden, equipos ni puntos."
    ),
    ContentType.STANDINGS_EVENT: (
        "Escribe el cambio de tabla de forma directa y verificable. "
        "No alteres posiciones, equipos ni el tipo de evento detectado."
    ),
    ContentType.FORM_RANKING: (
        "Prioriza lectura rapida de secuencias y puntos recientes. "
        "No alteres el orden, las rachas ni los puntos del ranking."
    ),
    ContentType.FORM_EVENT: (
        "Resume la dinamica reciente del equipo con claridad y sin exageracion. "
        "No alteres secuencias, puntos ni la ventana temporal analizada."
    ),
    ContentType.FEATURED_MATCH_PREVIEW: (
        "Presenta el partido destacado con tono de previa breve y editorial. "
        "No inventes contexto ni cambies posiciones, equipos o etiquetas del analisis."
    ),
    ContentType.FEATURED_MATCH_EVENT: (
        "Resume el angulo principal del partido destacado de forma limpia y concreta. "
        "No anadas hype ni razones no soportadas por el scoring."
    ),
    ContentType.PREVIEW: (
        "Escribe en tono de previa, ordenado y concreto. "
        "No inventes claves del partido ni contexto adicional."
    ),
    ContentType.RANKING: (
        "Resume rankings de forma compacta y clara. "
        "No cambies categorias, equipos ni valores."
    ),
    ContentType.STAT_NARRATIVE: (
        "Manten una narrativa de dato corto y limpia. "
        "No cambies cifras agregadas ni conclusiones implicitas."
    ),
    ContentType.METRIC_NARRATIVE: (
        "Escribe como una narrativa social breve y fiable. "
        "No exageres la metrica ni anadas contexto no medido por el sistema."
    ),
    ContentType.VIRAL_STORY: (
        "Refuerza la claridad y el ritmo de lectura sin convertirlo en clickbait. "
        "No exageres, no dramatices y no anadas causas que el sistema no haya medido."
    ),
}


def _excerpt(text: str | None, limit: int = 90) -> str | None:
    if text is None:
        return None
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def is_candidate_eligible_for_rewrite(
    candidate: ContentCandidate,
    *,
    overwrite: bool = False,
) -> bool:
    return (
        ContentCandidateStatus(candidate.status) in ALLOWED_REWRITE_STATUSES
        and bool(candidate.text_draft.strip())
        and (overwrite or not candidate.rewritten_text)
    )


class EditorialRewriterService:
    def __init__(
        self,
        session: Session,
        *,
        provider=None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.provider = provider or build_editorial_rewrite_provider(self.settings)

    def _candidate(self, candidate_id: int) -> ContentCandidate:
        candidate = self.session.get(ContentCandidate, candidate_id)
        if candidate is None:
            raise ConfigurationError(f"Content candidate desconocido: {candidate_id}")
        return candidate

    def _validate_candidate(
        self,
        candidate: ContentCandidate,
        *,
        overwrite: bool,
    ) -> None:
        status = ContentCandidateStatus(candidate.status)
        if status not in ALLOWED_REWRITE_STATUSES:
            raise InvalidStateTransitionError(
                f"Solo se pueden reescribir candidatos en estados draft, approved o published. Estado actual: {status}"
            )
        if not candidate.text_draft.strip():
            raise InvalidStateTransitionError(f"El candidato {candidate.id} no tiene text_draft utilizable")
        if candidate.rewritten_text and not overwrite:
            raise InvalidStateTransitionError(
                f"El candidato {candidate.id} ya tiene rewritten_text. Usa overwrite para reemplazarlo"
            )

    def _row_to_view(self, row: ContentCandidate) -> EditorialRewriteCandidateView:
        return EditorialRewriteCandidateView(
            id=row.id,
            competition_slug=row.competition_slug,
            content_type=ContentType(row.content_type),
            priority=row.priority,
            status=ContentCandidateStatus(row.status),
            rewrite_status=row.rewrite_status,
            rewrite_model=row.rewrite_model,
            rewrite_timestamp=row.rewrite_timestamp,
            rewrite_error=row.rewrite_error,
            excerpt=_excerpt(row.text_draft) or "",
            rewritten_excerpt=_excerpt(row.rewritten_text),
        )

    def _row_to_detail(self, row: ContentCandidate) -> EditorialRewriteCandidateDetail:
        return EditorialRewriteCandidateDetail(
            id=row.id,
            competition_slug=row.competition_slug,
            content_type=ContentType(row.content_type),
            priority=row.priority,
            status=ContentCandidateStatus(row.status),
            text_draft=row.text_draft,
            rewritten_text=row.rewritten_text,
            payload_json=row.payload_json or {},
            rewrite_status=row.rewrite_status,
            rewrite_model=row.rewrite_model,
            rewrite_timestamp=row.rewrite_timestamp,
            rewrite_error=row.rewrite_error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _prompt(self, candidate: ContentCandidate) -> str:
        content_type = ContentType(candidate.content_type)
        payload_json = json.dumps(candidate.payload_json or {}, ensure_ascii=False, indent=2, default=str)
        return "\n\n".join(
            [
                COMMON_POLICY.format(max_chars=self.settings.editorial_rewrite_max_chars),
                f"Guia por tipo:\n{TYPE_SPECIFIC_GUIDANCE[content_type]}",
                "Contexto del candidato:",
                f"- competition_slug: {candidate.competition_slug}",
                f"- content_type: {content_type}",
                f"- max_chars: {self.settings.editorial_rewrite_max_chars}",
                "",
                "Borrador base:",
                candidate.text_draft,
                "",
                "Hechos estructurados disponibles:",
                payload_json,
            ]
        )

    def list_pending(
        self,
        *,
        limit: int = 50,
        overwrite: bool = False,
    ) -> list[EditorialRewriteCandidateView]:
        query = select(ContentCandidate).where(
            ContentCandidate.status.in_([str(status) for status in ALLOWED_REWRITE_STATUSES]),
            func.length(func.trim(ContentCandidate.text_draft)) > 0,
        )
        if not overwrite:
            query = query.where(ContentCandidate.rewritten_text.is_(None))
        query = query.order_by(
            case((ContentCandidate.rewrite_timestamp.is_(None), 0), else_=1),
            ContentCandidate.priority.desc(),
            ContentCandidate.created_at.asc(),
        ).limit(limit)
        rows = self.session.execute(query).scalars().all()
        return [self._row_to_view(row) for row in rows]

    def show_candidate(self, candidate_id: int) -> EditorialRewriteCandidateDetail:
        return self._row_to_detail(self._candidate(candidate_id))

    def rewrite_candidate(
        self,
        candidate_id: int,
        *,
        dry_run: bool = False,
        overwrite: bool = False,
    ) -> EditorialRewriteResult:
        candidate = self._candidate(candidate_id)
        self._validate_candidate(candidate, overwrite=overwrite)
        had_rewritten_text = bool(candidate.rewritten_text)

        if dry_run and not editorial_rewrite_provider_ready(self.settings):
            preview = self._row_to_detail(candidate)
            preview.rewritten_text = candidate.text_draft
            preview.rewrite_status = "dry_run_unconfigured"
            preview.rewrite_model = self.settings.editorial_rewrite_model
            preview.rewrite_timestamp = utcnow()
            preview.rewrite_error = "Proveedor no configurado; dry-run sin llamada externa"
            return EditorialRewriteResult(
                dry_run=True,
                overwritten=bool(had_rewritten_text and overwrite),
                candidate=preview,
            )

        attempted_at = utcnow()
        try:
            response = self.provider.rewrite(
                EditorialRewriteLLMRequest(
                    prompt=self._prompt(candidate),
                    max_chars=self.settings.editorial_rewrite_max_chars,
                )
            )
        except (LLMConfigurationError, LLMProviderError) as exc:
            if not dry_run:
                candidate.rewrite_status = "failed"
                candidate.rewrite_model = self.settings.editorial_rewrite_model
                candidate.rewrite_timestamp = attempted_at
                candidate.rewrite_error = str(exc)
                self.session.add(candidate)
                self.session.flush()
            raise

        rewritten_text = response.rewritten_text.strip()
        if len(rewritten_text) > self.settings.editorial_rewrite_max_chars:
            exc = InvalidStateTransitionError(
                f"La reescritura excede el maximo configurado de {self.settings.editorial_rewrite_max_chars} caracteres"
            )
            if not dry_run:
                candidate.rewrite_status = "failed"
                candidate.rewrite_model = response.model
                candidate.rewrite_timestamp = attempted_at
                candidate.rewrite_error = str(exc)
                self.session.add(candidate)
                self.session.flush()
            raise exc

        if dry_run:
            preview = self._row_to_detail(candidate)
            preview.rewritten_text = rewritten_text
            preview.rewrite_status = "dry_run"
            preview.rewrite_model = response.model
            preview.rewrite_timestamp = response.rewritten_at
            preview.rewrite_error = None
            return EditorialRewriteResult(
                dry_run=True,
                overwritten=bool(had_rewritten_text and overwrite),
                candidate=preview,
            )

        candidate.rewritten_text = rewritten_text
        candidate.rewrite_status = "rewritten"
        candidate.rewrite_model = response.model
        candidate.rewrite_timestamp = response.rewritten_at
        candidate.rewrite_error = None
        self.session.add(candidate)
        self.session.flush()
        return EditorialRewriteResult(
            dry_run=False,
            overwritten=bool(had_rewritten_text and overwrite),
            candidate=self._row_to_detail(candidate),
        )

    def rewrite_pending(
        self,
        *,
        limit: int = 10,
        dry_run: bool = False,
        overwrite: bool = False,
    ) -> EditorialRewriteBatchResult:
        query = select(ContentCandidate).where(
            ContentCandidate.status.in_([str(status) for status in ALLOWED_REWRITE_STATUSES]),
            func.length(func.trim(ContentCandidate.text_draft)) > 0,
        )
        if not overwrite:
            query = query.where(ContentCandidate.rewritten_text.is_(None))
        query = query.order_by(
            case((ContentCandidate.rewrite_timestamp.is_(None), 0), else_=1),
            ContentCandidate.priority.desc(),
            ContentCandidate.created_at.asc(),
        ).limit(limit)
        rows = self.session.execute(query).scalars().all()

        result_rows: list[EditorialRewriteCandidateView] = []
        rewritten_count = 0
        for row in rows:
            try:
                result = self.rewrite_candidate(row.id, dry_run=dry_run, overwrite=overwrite)
            except (LLMConfigurationError, LLMProviderError, InvalidStateTransitionError):
                result_rows.append(self._row_to_view(row))
                continue
            result_rows.append(
                EditorialRewriteCandidateView(
                    id=result.candidate.id,
                    competition_slug=result.candidate.competition_slug,
                    content_type=result.candidate.content_type,
                    priority=result.candidate.priority,
                    status=result.candidate.status,
                    rewrite_status=result.candidate.rewrite_status,
                    rewrite_model=result.candidate.rewrite_model,
                    rewrite_timestamp=result.candidate.rewrite_timestamp,
                    rewrite_error=result.candidate.rewrite_error,
                    excerpt=_excerpt(result.candidate.text_draft) or "",
                    rewritten_excerpt=_excerpt(result.candidate.rewritten_text),
                )
            )
            rewritten_count += 1

        return EditorialRewriteBatchResult(
            dry_run=dry_run,
            rewritten_count=rewritten_count,
            rows=result_rows,
        )
