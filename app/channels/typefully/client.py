from __future__ import annotations

import logging

import requests

from app.channels.typefully.schemas import TypefullyDraftRequest, TypefullyPublishResponse

logger = logging.getLogger(__name__)

_TYPEFULLY_API_URL = "https://api.typefully.com/v1/drafts/"
_DEFAULT_TIMEOUT = 20


class TypefullyApiError(RuntimeError):
    pass


class TypefullyApiClient:
    def __init__(
        self,
        api_key: str,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key
        self.session = session or requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def create_draft(self, request: TypefullyDraftRequest) -> TypefullyPublishResponse:
        response = self.session.post(
            _TYPEFULLY_API_URL,
            json=request.model_dump(by_alias=True, exclude_none=True),
            timeout=_DEFAULT_TIMEOUT,
            headers={"X-API-KEY": f"Bearer {self.api_key}"},
        )
        if response.status_code >= 400:
            raise TypefullyApiError(f"Typefully API devolvio {response.status_code}: {self._error_detail(response)}")
        body = response.json()
        return TypefullyPublishResponse(
            draft_id=str(body.get("id", "")),
            draft_url=body.get("url"),
            scheduled_date=body.get("scheduled_date"),
            text=request.content,
        )

    @staticmethod
    def _error_detail(response: requests.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text.strip() or "sin detalle"
        error = body.get("error")
        if error:
            return str(error)
        return str(body)
