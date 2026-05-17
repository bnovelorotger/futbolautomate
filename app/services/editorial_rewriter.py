from __future__ import annotations

import json
import logging
from enum import StrEnum

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.editorial_rollout import EditorialPhase3Decision, with_phase3_editorial_voice
from app.core.enums import ContentCandidateStatus, ContentType
from app.core.exceptions import ConfigurationError, InvalidStateTransitionError
from app.db.models import ContentCandidate
from app.llm.providers import build_editorial_rewrite_provider, editorial_rewrite_provider_ready
from app.llm.providers.base import LLMConfigurationError, LLMProviderError
from app.llm.schemas import EditorialRewriteLLMRequest
from app.schemas.editorial_content import ContentCandidateDraft
from app.schemas.editorial_rewrite import (
    EditorialRewriteBatchResult,
    EditorialRewriteCandidateDetail,
    EditorialRewriteCandidateView,
    EditorialRewriteResult,
)
from app.services.editorial_formatter import EditorialFormatterService
from app.utils.time import utcnow

ALLOWED_REWRITE_STATUSES = {
    ContentCandidateStatus.DRAFT,
    ContentCandidateStatus.APPROVED,
    ContentCandidateStatus.PUBLISHED,
}

logger = logging.getLogger(__name__)


class EditorialRewriteMode(StrEnum):
    STRICT_DATA = "strict_data"
    HUMANIZED_LOCAL = "humanized_local"


HARD_INVARIANTS = """Eres el editor de estilo de uFutbolBalear.
Tu trabajo es reescribir un borrador breve ya calculado por el sistema.

Invariantes duras:
- No alterar ningun dato del borrador ni de los hechos estructurados.
- No inventar datos, contexto, lesiones, rachas, valoraciones ni antecedentes.
- No recalcular datos ni corregirlos con conocimiento externo.
- No inventar hashtags ni handles.
- Conservar intactos los hashtags y handles ya presentes en el borrador base.
- Conservar literalmente las lineas ancla estructurales que se indiquen mas abajo.
- No traducir ni sustituir titulos, etiquetas editoriales ni hashtags ya presentes en el borrador base.
- No anadir opinion, hype, clickbait, ironia ni emojis.
- Respetar el maximo real de {max_chars} caracteres en el texto final.
- Si el borrador ya esta bien, haz solo una mejora ligera.
- Devuelve solo JSON con la clave rewritten_text.
"""

STRICT_DATA_TONE_GUIDANCE = (
    "Tono sobrio, periodistico, limpio y breve. Prioriza claridad verificable, lectura rapida y compresion editorial."
)
LEGACY_TONE_GUIDANCE = "Tono directo, periodistico, limpio y breve. Texto apto para X y para exportacion local."
HUMANIZED_LOCAL_TONE_GUIDANCE = (
    "Tono cercano y natural, con una capa ligera de calidez local solo cuando encaje con el tipo. "
    "Mantener voz periodistica, breve y apta para X, sin folklore forzado."
)

STRICT_DATA_CONTENT_TYPES = (
    ContentType.MATCH_RESULT,
    ContentType.RESULTS_ROUNDUP,
    ContentType.STANDINGS,
    ContentType.STANDINGS_ROUNDUP,
    ContentType.STANDINGS_EVENT,
    ContentType.RANKING,
    ContentType.FORM_RANKING,
    ContentType.FORM_EVENT,
    ContentType.FEATURED_MATCH_EVENT,
    ContentType.MATCH_IMPACT_SCENARIO,
    ContentType.STAT_NARRATIVE,
    ContentType.TOP_SCORER_UPDATE,
)
HUMANIZED_LOCAL_CONTENT_TYPES = (
    ContentType.PREVIEW,
    ContentType.FEATURED_MATCH_PREVIEW,
    ContentType.VIRAL_STORY,
    ContentType.METRIC_NARRATIVE,
    ContentType.RACE_NARRATIVE,
    ContentType.MILESTONE_STORY,
)
CONTENT_TYPE_REWRITE_MODE = {
    content_type: EditorialRewriteMode.STRICT_DATA for content_type in STRICT_DATA_CONTENT_TYPES
} | {content_type: EditorialRewriteMode.HUMANIZED_LOCAL for content_type in HUMANIZED_LOCAL_CONTENT_TYPES}
UNCONFIGURED_REWRITE_MODE_TYPES = tuple(
    content_type for content_type in ContentType if content_type not in CONTENT_TYPE_REWRITE_MODE
)
if UNCONFIGURED_REWRITE_MODE_TYPES:
    missing = ", ".join(str(content_type) for content_type in UNCONFIGURED_REWRITE_MODE_TYPES)
    raise RuntimeError(f"ContentType sin editorial rewrite mode configurado: {missing}")

TYPE_SPECIFIC_GUIDANCE = {
    ContentType.MATCH_RESULT: (
        "Abre con el resultado final y deja muy claro el partido y la competicion. "
        "No cambies marcadores, equipos, jornada ni estado."
    ),
    ContentType.RESULTS_ROUNDUP: (
        "Resume una tanda de resultados con lectura rapida y limpia. "
        "No cambies marcadores, orden ni competicion, y evita anadir analisis."
    ),
    ContentType.STANDINGS: (
        "Prioriza claridad y lectura rapida de posiciones y puntos. No alteres ranking, orden, equipos ni puntos."
    ),
    ContentType.STANDINGS_ROUNDUP: (
        "Resume la clasificacion en formato compacto y editorial. "
        "No alteres posiciones, puntos, equipos ni etiquetas de zona incluidas en el borrador."
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
        "Escribe en tono de previa, ordenado y concreto. No inventes claves del partido ni contexto adicional."
    ),
    ContentType.RANKING: ("Resume rankings de forma compacta y clara. No cambies categorias, equipos ni valores."),
    ContentType.STAT_NARRATIVE: (
        "Manten una narrativa de dato corto y limpia. No cambies cifras agregadas ni conclusiones implicitas."
    ),
    ContentType.METRIC_NARRATIVE: (
        "Escribe como una narrativa social breve y fiable. "
        "No exageres la metrica ni anadas contexto no medido por el sistema."
    ),
    ContentType.RACE_NARRATIVE: (
        "Resume una carrera de clasificacion con tension clara y verificable. "
        "No inventes probabilidades ni anadas equipos fuera del payload."
    ),
    ContentType.MILESTONE_STORY: (
        "Presenta el hito de forma concreta y compartible, sin adornos. "
        "No exageres la racha ni anadas contexto que no este medido."
    ),
    ContentType.TOP_SCORER_UPDATE: (
        "Resume la pelea de goleadores con lectura rapida y verificable. "
        "No cambies nombres, equipos, goles ni posiciones del ranking."
    ),
    ContentType.VIRAL_STORY: (
        "Refuerza la claridad y el ritmo de lectura sin convertirlo en clickbait. "
        "No exageres, no dramatices y no anadas causas que el sistema no haya medido."
    ),
    ContentType.MATCH_IMPACT_SCENARIO: (
        "Explica escenarios de clasificacion en formato breve y util. "
        "No inventes desempates, porcentajes ni consecuencias fuera de la simulacion."
    ),
}


def _excerpt(text: str | None, limit: int = 90) -> str | None:
    if text is None:
        return None
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _usable_text(text: str | None) -> str | None:
    if text is None:
        return None
    normalized = text.strip()
    return normalized or None


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
        self.formatter = EditorialFormatterService(session)

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
            formatted_text=row.formatted_text,
            rewritten_text=row.rewritten_text,
            payload_json=row.payload_json or {},
            rewrite_status=row.rewrite_status,
            rewrite_model=row.rewrite_model,
            rewrite_timestamp=row.rewrite_timestamp,
            rewrite_error=row.rewrite_error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _base_text(self, candidate: ContentCandidate) -> str:
        effective_payload_json = self._effective_payload_json(candidate)
        stored_formatted_text = _usable_text(candidate.formatted_text)
        if stored_formatted_text is not None and effective_payload_json == (candidate.payload_json or {}):
            return stored_formatted_text
        draft = ContentCandidateDraft(
            competition_slug=candidate.competition_slug,
            content_type=ContentType(candidate.content_type),
            priority=candidate.priority,
            text_draft=candidate.text_draft,
            formatted_text=candidate.formatted_text,
            payload_json=effective_payload_json,
            source_summary_hash=candidate.source_summary_hash,
            scheduled_at=candidate.scheduled_at,
            status=ContentCandidateStatus(candidate.status),
        )
        layers = self.formatter.build_text_layers_for_draft(draft)
        formatted_text = _usable_text(layers.enriched_text) or _usable_text(layers.formatted_text)
        if formatted_text is not None:
            return formatted_text
        return candidate.text_draft

    def _effective_payload_json(self, candidate: ContentCandidate) -> dict:
        payload_json, _ = with_phase3_editorial_voice(
            candidate.payload_json or {},
            ContentType(candidate.content_type),
            priority=candidate.priority,
            competition_slug=candidate.competition_slug,
            humanized_local_enabled=self.settings.editorial_rewrite_humanized_local_enabled,
            phase3_rollout_enabled=self.settings.editorial_phase3_rollout_enabled,
        )
        return payload_json

    def _phase3_decision(self, candidate: ContentCandidate) -> EditorialPhase3Decision:
        _, decision = with_phase3_editorial_voice(
            candidate.payload_json or {},
            ContentType(candidate.content_type),
            priority=candidate.priority,
            competition_slug=candidate.competition_slug,
            humanized_local_enabled=self.settings.editorial_rewrite_humanized_local_enabled,
            phase3_rollout_enabled=self.settings.editorial_phase3_rollout_enabled,
        )
        return decision

    def _rewrite_mode(self, content_type: ContentType) -> EditorialRewriteMode:
        return CONTENT_TYPE_REWRITE_MODE[content_type]

    def _tone_guidance(self, mode: EditorialRewriteMode, *, phase3_decision: EditorialPhase3Decision) -> str:
        if mode == EditorialRewriteMode.STRICT_DATA:
            return STRICT_DATA_TONE_GUIDANCE
        if phase3_decision.eligible:
            return HUMANIZED_LOCAL_TONE_GUIDANCE
        return LEGACY_TONE_GUIDANCE

    def _applied_tone(self, mode: EditorialRewriteMode, *, phase3_decision: EditorialPhase3Decision) -> str:
        if mode == EditorialRewriteMode.STRICT_DATA:
            return "strict_data"
        if phase3_decision.eligible:
            return "humanized_local"
        return "legacy"

    def _structural_anchor_lines(self, candidate: ContentCandidate, *, base_text: str) -> list[str]:
        content_type = ContentType(candidate.content_type)
        lines = [line.strip() for line in base_text.splitlines() if line.strip()]
        if not lines:
            return []

        anchors: list[str] = []
        if content_type in {
            ContentType.MATCH_RESULT,
            ContentType.RESULTS_ROUNDUP,
            ContentType.STANDINGS,
            ContentType.STANDINGS_ROUNDUP,
            ContentType.PREVIEW,
            ContentType.FEATURED_MATCH_PREVIEW,
            ContentType.RANKING,
            ContentType.FORM_RANKING,
        }:
            anchors.append(f"- title_line_exact: {lines[0]}")

        hashtag_line = next((line for line in reversed(lines) if "#" in line), None)
        if hashtag_line:
            anchors.append(f"- hashtag_line_exact: {hashtag_line}")

        if content_type in {ContentType.PREVIEW, ContentType.FEATURED_MATCH_PREVIEW}:
            for prefix in ("Partidos:", "Partido clave:"):
                matching_line = next((line for line in lines if line.startswith(prefix)), None)
                if matching_line:
                    anchors.append(f"- preserve_line_exact: {matching_line}")
            if len(lines) > 1 and not lines[1].startswith(("Partidos:", "Partido clave:", "#")):
                anchors.append(f"- preserve_line_exact: {lines[1]}")

        return anchors

    def _prompt_layers(self, candidate: ContentCandidate) -> list[str]:
        content_type = ContentType(candidate.content_type)
        mode = self._rewrite_mode(content_type)
        phase3_decision = self._phase3_decision(candidate)
        applied_tone = self._applied_tone(mode, phase3_decision=phase3_decision)
        editorial_voice_request = phase3_decision.editorial_voice_request or {}
        return [
            HARD_INVARIANTS.format(max_chars=self.settings.editorial_rewrite_max_chars),
            "Modo editorial:",
            f"- assigned_mode: {mode}",
            f"- applied_tone: {applied_tone}",
            f"- phase3_rollout_eligible: {str(phase3_decision.eligible).lower()}",
            f"- phase3_rollout_reason: {phase3_decision.reason}",
            (
                f"- editorial_voice_mode: {editorial_voice_request.get('mode')}"
                if editorial_voice_request.get("mode")
                else "- editorial_voice_mode: none"
            ),
            (
                f"- editorial_voice_resource_id: {editorial_voice_request.get('resource_id')}"
                if editorial_voice_request.get("resource_id")
                else "- editorial_voice_resource_id: none"
            ),
            "Guia de tono:",
            self._tone_guidance(mode, phase3_decision=phase3_decision),
            "Guia por tipo:",
            TYPE_SPECIFIC_GUIDANCE[content_type],
        ]

    def _prompt(self, candidate: ContentCandidate) -> str:
        content_type = ContentType(candidate.content_type)
        payload_json = json.dumps(self._effective_payload_json(candidate), ensure_ascii=False, indent=2, default=str)
        base_text = self._base_text(candidate)
        structural_anchors = self._structural_anchor_lines(candidate, base_text=base_text)
        return "\n\n".join(
            [
                *self._prompt_layers(candidate),
                *(
                    [
                        "Anclajes estructurales obligatorios:",
                        *structural_anchors,
                        "Si una mejora rompe alguna linea ancla, devuelve el borrador base exacto.",
                    ]
                    if structural_anchors
                    else []
                ),
                "Contexto del candidato:",
                f"- competition_slug: {candidate.competition_slug}",
                f"- content_type: {content_type}",
                f"- max_chars: {self.settings.editorial_rewrite_max_chars}",
                "",
                "Borrador base:",
                base_text,
                "",
                "Hechos estructurados disponibles:",
                payload_json,
            ]
        )

    def _supports_base_text_fallback(self, exc: Exception) -> bool:
        if not isinstance(exc, LLMProviderError):
            return False
        normalized = str(exc).lower()
        return (
            "failed to validate json" in normalized
            or "failed to generate json" in normalized
            or "rate limit reached" in normalized
        )

    def _rewrite_outcome(self, rewrite_status: str | None) -> str:
        if rewrite_status in {"rewritten", "dry_run"}:
            return "real"
        if rewrite_status in {"rewritten_fallback_base_text", "dry_run_fallback_base_text"}:
            return "fallback_base_text"
        if rewrite_status == "dry_run_unconfigured":
            return "unconfigured"
        if rewrite_status == "failed":
            return "failed"
        return "unknown"

    def _fallback_to_base_text_result(
        self,
        candidate: ContentCandidate,
        *,
        had_rewritten_text: bool,
        overwrite: bool,
        dry_run: bool,
        attempted_at,
        error_message: str,
        content_type: ContentType,
        rewrite_mode: EditorialRewriteMode,
        applied_tone: str,
        phase3_decision: EditorialPhase3Decision,
    ) -> EditorialRewriteResult:
        base_text = self._base_text(candidate)
        status = "dry_run_fallback_base_text" if dry_run else "rewritten_fallback_base_text"
        logger.warning(
            "editorial_rewrite_provider_fallback",
            extra={
                "event": "editorial_rewrite_provider_fallback",
                "candidate_id": candidate.id,
                "competition_slug": candidate.competition_slug,
                "content_type": str(content_type),
                "rewrite_mode": str(rewrite_mode),
                "applied_tone": applied_tone,
                "phase3_rollout_eligible": phase3_decision.eligible,
                "phase3_rollout_reason": phase3_decision.reason,
                "rewrite_status": status,
                "rewrite_outcome": self._rewrite_outcome(status),
                "fallback_status": status,
                "fallback_reason": error_message,
                "dry_run": dry_run,
            },
        )
        if dry_run:
            preview = self._row_to_detail(candidate)
            preview.rewritten_text = base_text
            preview.rewrite_status = status
            preview.rewrite_model = self.settings.editorial_rewrite_model
            preview.rewrite_timestamp = attempted_at
            preview.rewrite_error = error_message
            return EditorialRewriteResult(
                dry_run=True,
                overwritten=bool(had_rewritten_text and overwrite),
                candidate=preview,
            )

        candidate.rewritten_text = base_text
        candidate.rewrite_status = status
        candidate.rewrite_model = self.settings.editorial_rewrite_model
        candidate.rewrite_timestamp = attempted_at
        candidate.rewrite_error = error_message
        self.session.add(candidate)
        self.session.flush()
        return EditorialRewriteResult(
            dry_run=False,
            overwritten=bool(had_rewritten_text and overwrite),
            candidate=self._row_to_detail(candidate),
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
        content_type = ContentType(candidate.content_type)
        rewrite_mode = self._rewrite_mode(content_type)
        phase3_decision = self._phase3_decision(candidate)
        applied_tone = self._applied_tone(rewrite_mode, phase3_decision=phase3_decision)
        editorial_voice_request = phase3_decision.editorial_voice_request or {}
        logger.info(
            "editorial_rewrite_started",
            extra={
                "event": "editorial_rewrite_started",
                "candidate_id": candidate.id,
                "competition_slug": candidate.competition_slug,
                "content_type": str(content_type),
                "rewrite_mode": str(rewrite_mode),
                "applied_tone": applied_tone,
                "phase3_rollout_eligible": phase3_decision.eligible,
                "phase3_rollout_reason": phase3_decision.reason,
                "editorial_voice_mode": editorial_voice_request.get("mode"),
                "editorial_voice_resource_id": editorial_voice_request.get("resource_id"),
                "dry_run": dry_run,
                "overwrite": overwrite,
            },
        )

        if dry_run and not editorial_rewrite_provider_ready(self.settings):
            preview = self._row_to_detail(candidate)
            preview.rewritten_text = self._base_text(candidate)
            preview.rewrite_status = "dry_run_unconfigured"
            preview.rewrite_model = self.settings.editorial_rewrite_model
            preview.rewrite_timestamp = utcnow()
            preview.rewrite_error = "Proveedor no configurado; dry-run sin llamada externa"
            logger.info(
                "editorial_rewrite_dry_run_unconfigured",
                extra={
                    "event": "editorial_rewrite_dry_run_unconfigured",
                    "candidate_id": candidate.id,
                    "competition_slug": candidate.competition_slug,
                    "content_type": str(content_type),
                    "rewrite_mode": str(rewrite_mode),
                    "applied_tone": applied_tone,
                    "phase3_rollout_eligible": phase3_decision.eligible,
                    "phase3_rollout_reason": phase3_decision.reason,
                    "rewrite_status": preview.rewrite_status,
                    "rewrite_outcome": self._rewrite_outcome(preview.rewrite_status),
                },
            )
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
            if self._supports_base_text_fallback(exc):
                return self._fallback_to_base_text_result(
                    candidate,
                    had_rewritten_text=had_rewritten_text,
                    overwrite=overwrite,
                    dry_run=dry_run,
                    attempted_at=attempted_at,
                    error_message=str(exc),
                    content_type=content_type,
                    rewrite_mode=rewrite_mode,
                    applied_tone=applied_tone,
                    phase3_decision=phase3_decision,
                )
            if not dry_run:
                candidate.rewrite_status = "failed"
                candidate.rewrite_model = self.settings.editorial_rewrite_model
                candidate.rewrite_timestamp = attempted_at
                candidate.rewrite_error = str(exc)
                self.session.add(candidate)
                self.session.flush()
            logger.warning(
                "editorial_rewrite_failed",
                extra={
                    "event": "editorial_rewrite_failed",
                    "candidate_id": candidate.id,
                    "competition_slug": candidate.competition_slug,
                    "content_type": str(content_type),
                    "rewrite_mode": str(rewrite_mode),
                    "applied_tone": applied_tone,
                    "phase3_rollout_eligible": phase3_decision.eligible,
                    "phase3_rollout_reason": phase3_decision.reason,
                    "rewrite_status": "failed",
                    "rewrite_outcome": self._rewrite_outcome("failed"),
                    "error": str(exc),
                    "dry_run": dry_run,
                },
            )
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
            logger.warning(
                "editorial_rewrite_failed_length",
                extra={
                    "event": "editorial_rewrite_failed_length",
                    "candidate_id": candidate.id,
                    "competition_slug": candidate.competition_slug,
                    "content_type": str(content_type),
                    "rewrite_mode": str(rewrite_mode),
                    "applied_tone": applied_tone,
                    "phase3_rollout_eligible": phase3_decision.eligible,
                    "phase3_rollout_reason": phase3_decision.reason,
                    "rewrite_status": "failed",
                    "rewrite_outcome": self._rewrite_outcome("failed"),
                    "rewritten_length": len(rewritten_text),
                    "max_chars": self.settings.editorial_rewrite_max_chars,
                    "dry_run": dry_run,
                },
            )
            raise exc

        if dry_run:
            preview = self._row_to_detail(candidate)
            preview.rewritten_text = rewritten_text
            preview.rewrite_status = "dry_run"
            preview.rewrite_model = response.model
            preview.rewrite_timestamp = response.rewritten_at
            preview.rewrite_error = None
            logger.info(
                "editorial_rewrite_completed",
                extra={
                    "event": "editorial_rewrite_completed",
                    "candidate_id": candidate.id,
                    "competition_slug": candidate.competition_slug,
                    "content_type": str(content_type),
                    "rewrite_mode": str(rewrite_mode),
                    "applied_tone": applied_tone,
                    "phase3_rollout_eligible": phase3_decision.eligible,
                    "phase3_rollout_reason": phase3_decision.reason,
                    "rewrite_status": preview.rewrite_status,
                    "rewrite_outcome": self._rewrite_outcome(preview.rewrite_status),
                    "rewritten_length": len(rewritten_text),
                    "dry_run": True,
                },
            )
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
        logger.info(
            "editorial_rewrite_completed",
            extra={
                "event": "editorial_rewrite_completed",
                "candidate_id": candidate.id,
                "competition_slug": candidate.competition_slug,
                "content_type": str(content_type),
                "rewrite_mode": str(rewrite_mode),
                "applied_tone": applied_tone,
                "phase3_rollout_eligible": phase3_decision.eligible,
                "phase3_rollout_reason": phase3_decision.reason,
                "rewrite_status": candidate.rewrite_status,
                "rewrite_outcome": self._rewrite_outcome(candidate.rewrite_status),
                "rewritten_length": len(rewritten_text),
                "dry_run": False,
            },
        )
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
