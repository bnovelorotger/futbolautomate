from __future__ import annotations

from app.channels.x.client import XApiClient
from app.channels.x.schemas import XPublishRequest, XPublishResponse

MAX_X_POST_LENGTH = 280


class XPublisherValidationError(RuntimeError):
    pass


class XPublisher:
    def __init__(self, client: XApiClient) -> None:
        self.client = client

    def publish_text(
        self,
        text: str,
        *,
        access_token: str | None = None,
        dry_run: bool = False,
    ) -> XPublishResponse:
        normalized_text = text.strip()
        if not normalized_text:
            raise XPublisherValidationError("El texto para X no puede estar vacio")
        if len(normalized_text) > MAX_X_POST_LENGTH:
            raise XPublisherValidationError(
                f"El texto excede el maximo de {MAX_X_POST_LENGTH} caracteres permitido por X"
            )
        if dry_run:
            return self.client.publish_text("", XPublishRequest(text=normalized_text, dry_run=True))
        if not access_token:
            raise XPublisherValidationError("Falta access token de usuario para publicar en X")
        return self.client.publish_text(access_token, XPublishRequest(text=normalized_text, dry_run=False))
