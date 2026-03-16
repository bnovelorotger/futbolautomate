from __future__ import annotations

from datetime import timedelta
from urllib.parse import parse_qs, urlparse
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.channels.x.auth import (
    XAuthError,
    XOAuth2PKCEClient,
    build_authorization_url,
    build_session_expiry,
    generate_pkce_pair,
    generate_state,
)
from app.channels.x.client import XApiClient, XApiError
from app.core.config import Settings, get_settings
from app.db.models import ChannelAuthSession, ChannelUserToken
from app.schemas.x_auth import XAuthorizationStart, XAuthTokenStatus
from app.utils.time import utcnow

X_PROVIDER = "x"


def _aware_datetime(value):
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class XAuthService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        oauth_client: XOAuth2PKCEClient | None = None,
        api_client: XApiClient | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.oauth_client = oauth_client or XOAuth2PKCEClient(self.settings)
        self.api_client = api_client or XApiClient(self.settings)

    def start_authorization(self) -> XAuthorizationStart:
        state = generate_state()
        verifier, challenge = generate_pkce_pair()
        expires_at = build_session_expiry(self.settings)
        authorization_url = build_authorization_url(
            self.settings,
            state=state,
            code_challenge=challenge,
        )
        auth_session = ChannelAuthSession(
            provider=X_PROVIDER,
            state=state,
            code_verifier=verifier,
            redirect_uri=self.settings.x_redirect_uri or "",
            scopes=" ".join(self.settings.x_scope_list),
            expires_at=expires_at,
            used_at=None,
        )
        self.session.add(auth_session)
        self.session.flush()
        return XAuthorizationStart(
            authorization_url=authorization_url,
            state=state,
            expires_at=expires_at,
            scopes=self.settings.x_scope_list,
        )

    def exchange_code(
        self,
        *,
        code: str | None = None,
        state: str | None = None,
        callback_url: str | None = None,
    ) -> XAuthTokenStatus:
        resolved_code, resolved_state = self._resolve_code_and_state(
            code=code,
            state=state,
            callback_url=callback_url,
        )
        auth_session = self._auth_session(resolved_state)
        if auth_session.used_at is not None:
            raise XAuthError("El estado PKCE ya fue utilizado")
        if _aware_datetime(auth_session.expires_at) <= utcnow():
            raise XAuthError("El estado PKCE ha expirado. Ejecuta start-auth de nuevo")

        token_payload = self.oauth_client.exchange_code(
            code=resolved_code,
            code_verifier=auth_session.code_verifier,
        )
        token = self._upsert_token(token_payload)
        auth_session.used_at = utcnow()
        self.session.add(auth_session)
        self._verify_with_api(token)
        self.session.flush()
        return self._token_status(token)

    def verify_user_token(self) -> XAuthTokenStatus:
        token = self._get_valid_token()
        self._verify_with_api(token)
        self.session.flush()
        return self._token_status(token)

    def get_valid_user_access_token(self) -> str:
        token = self._get_valid_token()
        self.session.flush()
        return token.access_token

    def _resolve_code_and_state(
        self,
        *,
        code: str | None,
        state: str | None,
        callback_url: str | None,
    ) -> tuple[str, str]:
        if callback_url:
            parsed = urlparse(callback_url)
            params = parse_qs(parsed.query)
            error = (params.get("error") or [None])[0]
            if error:
                description = (params.get("error_description") or ["sin descripcion"])[0]
                raise XAuthError(f"El callback de X devolvio error={error}: {description}")
            resolved_code = (params.get("code") or [None])[0]
            resolved_state = (params.get("state") or [None])[0]
        else:
            resolved_code = code
            resolved_state = state
        if not resolved_code or not resolved_state:
            raise XAuthError("Necesitas proporcionar code y state, o callback-url completo")
        return resolved_code, resolved_state

    def _auth_session(self, state: str) -> ChannelAuthSession:
        auth_session = self.session.scalar(
            select(ChannelAuthSession).where(
                ChannelAuthSession.provider == X_PROVIDER,
                ChannelAuthSession.state == state,
            )
        )
        if auth_session is None:
            raise XAuthError("No existe una sesion PKCE para ese state")
        return auth_session

    def _token_row(self) -> ChannelUserToken | None:
        return self.session.scalar(
            select(ChannelUserToken).where(ChannelUserToken.provider == X_PROVIDER)
        )

    def _get_valid_token(self) -> ChannelUserToken:
        token = self._token_row()
        if token is None:
            raise XAuthError(
                "No hay token de usuario de X. Ejecuta x_auth start-auth y luego exchange-code"
            )
        if self._needs_refresh(token):
            if not token.refresh_token:
                raise XAuthError(
                    "El token de X ha expirado y no hay refresh_token. Repite el flujo PKCE"
                )
            refreshed = self.oauth_client.refresh_token(refresh_token=token.refresh_token)
            token = self._upsert_token(refreshed, existing=token)
        return token

    def _needs_refresh(self, token: ChannelUserToken) -> bool:
        if token.expires_at is None:
            return False
        refresh_at = utcnow() + timedelta(seconds=self.settings.x_token_refresh_buffer_seconds)
        return _aware_datetime(token.expires_at) <= refresh_at

    def _upsert_token(
        self,
        payload: dict,
        *,
        existing: ChannelUserToken | None = None,
    ) -> ChannelUserToken:
        token = existing or self._token_row()
        if token is None:
            token = ChannelUserToken(provider=X_PROVIDER, access_token="")
        expires_in = payload.get("expires_in")
        expires_at = None
        if isinstance(expires_in, int):
            expires_at = utcnow() + timedelta(seconds=expires_in)
        token.access_token = str(payload.get("access_token") or token.access_token)
        refresh_token = payload.get("refresh_token")
        if refresh_token:
            token.refresh_token = str(refresh_token)
        token.token_type = str(payload.get("token_type") or token.token_type or "Bearer")
        token.scope = str(payload.get("scope") or token.scope or " ".join(self.settings.x_scope_list))
        token.expires_at = expires_at
        self.session.add(token)
        self.session.flush()
        return token

    def _verify_with_api(self, token: ChannelUserToken) -> None:
        user = self.api_client.get_authenticated_user(token.access_token)
        token.subject_id = str(user.get("id"))
        username = user.get("username")
        token.subject_username = str(username) if username is not None else None
        token.last_verified_at = utcnow()
        self.session.add(token)

    def _token_status(self, token: ChannelUserToken) -> XAuthTokenStatus:
        return XAuthTokenStatus(
            ready=True,
            provider=X_PROVIDER,
            subject_id=token.subject_id,
            subject_username=token.subject_username,
            expires_at=token.expires_at,
            has_refresh_token=bool(token.refresh_token),
            scope=token.scope,
            last_verified_at=token.last_verified_at,
        )
