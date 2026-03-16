from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta
from urllib.parse import urlencode

import requests
from requests.auth import HTTPBasicAuth

from app.core.config import Settings
from app.utils.time import utcnow

REQUIRED_X_AUTH_CONFIG: tuple[str, ...] = (
    "X_CLIENT_ID",
    "X_REDIRECT_URI",
)


class XAuthError(RuntimeError):
    pass


def x_auth_config_presence(settings: Settings) -> dict[str, bool]:
    values = {
        "X_CLIENT_ID": settings.x_client_id,
        "X_REDIRECT_URI": settings.x_redirect_uri,
    }
    return {
        key: isinstance(value, str) and value.strip() != ""
        for key, value in values.items()
    }


def missing_x_auth_config(settings: Settings) -> list[str]:
    presence = x_auth_config_presence(settings)
    return [key for key in REQUIRED_X_AUTH_CONFIG if not presence[key]]


def validate_x_auth_config(settings: Settings) -> None:
    missing = missing_x_auth_config(settings)
    if missing:
        raise XAuthError("Missing X auth configuration:\n" + "\n".join(missing))


def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


def generate_state() -> str:
    return secrets.token_urlsafe(32)


def build_authorization_url(
    settings: Settings,
    *,
    state: str,
    code_challenge: str,
) -> str:
    validate_x_auth_config(settings)
    params = {
        "response_type": "code",
        "client_id": settings.x_client_id,
        "redirect_uri": settings.x_redirect_uri,
        "scope": " ".join(settings.x_scope_list),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{settings.x_authorize_url.rstrip('/')}?{urlencode(params)}"


def build_session_expiry(settings: Settings) -> datetime:
    return utcnow() + timedelta(minutes=settings.x_auth_state_ttl_minutes)


class XOAuth2PKCEClient:
    def __init__(
        self,
        settings: Settings,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": settings.user_agent})

    def exchange_code(self, *, code: str, code_verifier: str) -> dict:
        validate_x_auth_config(self.settings)
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.settings.x_redirect_uri,
            "code_verifier": code_verifier,
            "client_id": self.settings.x_client_id,
        }
        response = self.session.post(
            self.settings.x_token_url,
            data=payload,
            timeout=self.settings.request_timeout_seconds,
            auth=self._client_auth(),
        )
        if response.status_code >= 400:
            raise XAuthError(f"X token exchange fallo con {response.status_code}: {self._error_detail(response)}")
        return response.json()

    def refresh_token(self, *, refresh_token: str) -> dict:
        validate_x_auth_config(self.settings)
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.settings.x_client_id,
        }
        response = self.session.post(
            self.settings.x_token_url,
            data=payload,
            timeout=self.settings.request_timeout_seconds,
            auth=self._client_auth(),
        )
        if response.status_code >= 400:
            raise XAuthError(f"X refresh token fallo con {response.status_code}: {self._error_detail(response)}")
        return response.json()

    def _client_auth(self):
        if self.settings.x_client_secret:
            return HTTPBasicAuth(self.settings.x_client_id or "", self.settings.x_client_secret)
        return None

    @staticmethod
    def _error_detail(response: requests.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text.strip() or "sin detalle"
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            return "; ".join(str(error) for error in errors)
        if "error_description" in body:
            return str(body["error_description"])
        if "detail" in body:
            return str(body["detail"])
        return str(body)
