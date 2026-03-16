from __future__ import annotations

import logging

import requests

from app.channels.x.schemas import XPublishRequest, XPublishResponse
from app.core.config import Settings
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


class XClientConfigurationError(RuntimeError):
    pass


class XApiError(RuntimeError):
    pass


class XApiClient:
    def __init__(
        self,
        settings: Settings,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": settings.user_agent,
                "Content-Type": "application/json",
            }
        )

    def publish_text(self, access_token: str, request: XPublishRequest) -> XPublishResponse:
        published_at = utcnow()
        if request.dry_run:
            logger.info("X dry-run publish", extra={"length": len(request.text)})
            return XPublishResponse(
                post_id="dry-run",
                text=request.text,
                published_at=published_at,
                raw_response={"dry_run": True},
                dry_run=True,
            )
        response = self.session.post(
            f"{self.settings.x_api_base_url.rstrip('/')}/2/tweets",
            json={"text": request.text},
            timeout=self.settings.request_timeout_seconds,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise XApiError(f"X API devolvio {response.status_code}: {self._error_detail(response)}")
        body = response.json()
        post_id = str(body.get("data", {}).get("id") or "")
        if not post_id:
            raise XApiError(f"Respuesta de X sin id de publicacion: {body}")
        return XPublishResponse(
            post_id=post_id,
            text=request.text,
            published_at=published_at,
            raw_response=body,
            dry_run=False,
        )

    def get_authenticated_user(self, access_token: str) -> dict:
        response = self.session.get(
            f"{self.settings.x_api_base_url.rstrip('/')}/2/users/me",
            timeout=self.settings.request_timeout_seconds,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code >= 400:
            raise XApiError(f"X API devolvio {response.status_code}: {self._error_detail(response)}")
        body = response.json()
        data = body.get("data")
        if not isinstance(data, dict) or not data.get("id"):
            raise XApiError(f"Respuesta de X sin usuario autenticado: {body}")
        return data

    @staticmethod
    def _error_detail(response: requests.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text.strip() or "sin detalle"
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            return "; ".join(str(error) for error in errors)
        detail = body.get("detail")
        if detail:
            return str(detail)
        return str(body)
