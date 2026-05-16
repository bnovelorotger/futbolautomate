from __future__ import annotations

from datetime import datetime

from app.channels.typefully.client import TypefullyApiClient
from app.channels.typefully.schemas import TypefullyDraftRequest, TypefullyPublishResponse

MAX_POST_LENGTH = 280


class TypefullyPublisherValidationError(RuntimeError):
    pass


class TypefullyPublisher:
    def __init__(self, client: TypefullyApiClient) -> None:
        self.client = client

    def publish_text(
        self,
        text: str,
        *,
        schedule_date: datetime | None = None,
        dry_run: bool = False,
    ) -> TypefullyPublishResponse:
        normalized_text = text.strip()
        if not normalized_text:
            raise TypefullyPublisherValidationError("El texto para Typefully no puede estar vacio")
        if len(normalized_text) > MAX_POST_LENGTH:
            raise TypefullyPublisherValidationError(
                f"El texto excede el maximo de {MAX_POST_LENGTH} caracteres permitido por Typefully"
            )
        if dry_run:
            return TypefullyPublishResponse(draft_id="dry-run", text=normalized_text, dry_run=True)
        return self.client.create_draft(
            TypefullyDraftRequest(content=normalized_text, schedule_date=schedule_date)
        )
