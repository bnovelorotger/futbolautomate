from __future__ import annotations

import requests

from app.channels.typefully.schemas import TypefullyDraftRequest, TypefullySocialSet
from app.core.config import Settings

REQUIRED_TYPEFULLY_CONFIG: tuple[str, ...] = (
    "TYPEFULLY_API_KEY",
    "TYPEFULLY_API_URL",
)


class TypefullyConfigurationError(RuntimeError):
    pass


class TypefullyApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        detail: str | None = None,
        body: object | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
        self.body = body


def typefully_config_presence(settings: Settings) -> dict[str, bool]:
    values = {
        "TYPEFULLY_API_KEY": settings.typefully_api_key,
        "TYPEFULLY_API_URL": settings.typefully_api_url,
    }
    return {
        key: isinstance(value, str) and value.strip() != ""
        for key, value in values.items()
    }


def missing_typefully_config(settings: Settings) -> list[str]:
    presence = typefully_config_presence(settings)
    return [key for key in REQUIRED_TYPEFULLY_CONFIG if not presence[key]]


def validate_typefully_config(settings: Settings) -> None:
    missing = missing_typefully_config(settings)
    if missing:
        raise TypefullyConfigurationError(
            "Missing Typefully configuration:\n" + "\n".join(missing)
        )


class TypefullyApiClient:
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

    def verify_credentials(self) -> dict:
        validate_typefully_config(self.settings)
        response = self.session.get(
            f"{self._base_url()}/v2/me",
            timeout=self.settings.request_timeout_seconds,
            headers=self._auth_headers(),
        )
        self._raise_for_error(response, "Typefully verify credentials")
        return response.json()

    def list_social_sets(self) -> list[TypefullySocialSet]:
        validate_typefully_config(self.settings)
        response = self.session.get(
            f"{self._base_url()}/v2/social-sets",
            timeout=self.settings.request_timeout_seconds,
            headers=self._auth_headers(),
        )
        self._raise_for_error(response, "Typefully list social sets")
        body = response.json()
        items = self._extract_items(body)
        social_sets: list[TypefullySocialSet] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            social_set_id = str(item.get("id") or item.get("social_set_id") or "").strip()
            if not social_set_id:
                continue
            name = item.get("name") or item.get("title") or item.get("label")
            social_sets.append(
                TypefullySocialSet(
                    id=social_set_id,
                    name=str(name) if name is not None else None,
                    raw=item,
                )
            )
        if not social_sets:
            raise TypefullyApiError(f"Respuesta de Typefully sin social sets utilizables: {body}")
        return social_sets

    def create_draft(self, request: TypefullyDraftRequest) -> dict:
        validate_typefully_config(self.settings)
        response = self.session.post(
            f"{self._base_url()}/v2/social-sets/{request.social_set_id}/drafts",
            json={
                "platforms": {
                    "x": {
                        "enabled": True,
                        "posts": [{"text": request.text}],
                    }
                },
            },
            timeout=self.settings.request_timeout_seconds,
            headers=self._auth_headers(),
        )
        self._raise_for_error(response, "Typefully create draft")
        return response.json()

    def _base_url(self) -> str:
        return str(self.settings.typefully_api_url or "").rstrip("/")

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.typefully_api_key or ''}"}

    @staticmethod
    def _extract_items(body) -> list:
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            for key in ("data", "results", "social_sets"):
                value = body.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _raise_for_error(response: requests.Response, prefix: str) -> None:
        if response.status_code < 400:
            return
        body = TypefullyApiClient._response_body(response)
        detail = TypefullyApiClient._error_detail(response, body=body)
        raise TypefullyApiError(
            f"{prefix} failed with {response.status_code}: {detail}",
            status_code=response.status_code,
            error_code=TypefullyApiClient._error_code(body),
            detail=detail,
            body=body,
        )

    @staticmethod
    def _response_body(response: requests.Response):
        try:
            return response.json()
        except ValueError:
            return None

    @staticmethod
    def _error_detail(response: requests.Response, *, body=None) -> str:
        if body is None:
            body = TypefullyApiClient._response_body(response)
        if body is None:
            return response.text.strip() or "sin detalle"
        if isinstance(body, dict):
            for key in ("error", "message", "detail"):
                value = body.get(key)
                if value:
                    return str(value)
            errors = body.get("errors")
            if isinstance(errors, list) and errors:
                return "; ".join(str(error) for error in errors)
        return str(body)

    @staticmethod
    def _error_code(body) -> str | None:
        if not isinstance(body, dict):
            return None
        candidates = [
            body.get("code"),
            body.get("error_code"),
        ]
        error = body.get("error")
        if isinstance(error, dict):
            candidates.extend([error.get("code"), error.get("error_code")])
        for candidate in candidates:
            value = str(candidate or "").strip()
            if value:
                return value
        return None
