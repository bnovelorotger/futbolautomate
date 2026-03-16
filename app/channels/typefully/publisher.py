from __future__ import annotations

from app.channels.typefully.client import TypefullyApiClient
from app.channels.typefully.schemas import (
    TypefullyDraftRequest,
    TypefullyDraftResponse,
    TypefullySocialSet,
)
from app.utils.time import utcnow


class TypefullyPublisherValidationError(RuntimeError):
    pass


class TypefullyPublisher:
    def __init__(
        self,
        client: TypefullyApiClient,
        *,
        default_social_set_id: str | None = None,
    ) -> None:
        self.client = client
        self.default_social_set_id = default_social_set_id.strip() if default_social_set_id else None
        self._resolved_social_set_id = self.default_social_set_id

    def export_text(
        self,
        text: str,
        *,
        dry_run: bool = False,
        social_set_id: str | None = None,
    ) -> TypefullyDraftResponse:
        normalized_text = text.strip()
        if not normalized_text:
            raise TypefullyPublisherValidationError("El texto para Typefully no puede estar vacio")
        if dry_run:
            return TypefullyDraftResponse(
                draft_id="dry-run",
                social_set_id=(social_set_id or self.default_social_set_id or "dry-run"),
                exported_at=utcnow(),
                raw_response={"dry_run": True},
                dry_run=True,
            )

        resolved_social_set_id = self._resolve_social_set_id(social_set_id)
        response = self.client.create_draft(
            TypefullyDraftRequest(
                social_set_id=resolved_social_set_id,
                text=normalized_text,
                dry_run=False,
            )
        )
        return TypefullyDraftResponse(
            draft_id=self._draft_id(response),
            social_set_id=resolved_social_set_id,
            exported_at=utcnow(),
            raw_response=response,
            dry_run=False,
        )

    def _resolve_social_set_id(self, social_set_id: str | None) -> str:
        if social_set_id and social_set_id.strip():
            return social_set_id.strip()
        if self._resolved_social_set_id:
            return self._resolved_social_set_id
        social_sets = self.client.list_social_sets()
        if len(social_sets) == 1:
            self._resolved_social_set_id = social_sets[0].id
            return self._resolved_social_set_id
        raise TypefullyPublisherValidationError(
            self._multiple_social_sets_error(social_sets)
        )

    @staticmethod
    def _draft_id(body: dict) -> str:
        candidates = [
            body.get("id"),
            body.get("draft_id"),
            body.get("draft", {}).get("id") if isinstance(body.get("draft"), dict) else None,
            body.get("data", {}).get("id") if isinstance(body.get("data"), dict) else None,
        ]
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value:
                return value
        raise TypefullyPublisherValidationError(f"Respuesta de Typefully sin draft id: {body}")

    @staticmethod
    def _multiple_social_sets_error(social_sets: list[TypefullySocialSet]) -> str:
        labels = ", ".join(
            social_set.name or social_set.id
            for social_set in social_sets[:5]
        )
        return (
            "Typefully devolvio multiples social sets. "
            "Configura TYPEFULLY_SOCIAL_SET_ID para fijar cual usar"
            + (f". Disponibles: {labels}" if labels else "")
        )
