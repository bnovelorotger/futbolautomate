from __future__ import annotations

from app.channels.x.auth import (
    XOAuth2PKCEClient,
    build_authorization_url,
    generate_pkce_pair,
    missing_x_auth_config,
    validate_x_auth_config,
)
from app.channels.x.client import XApiClient
from app.channels.x.schemas import XPublishRequest
from app.core.config import Settings


class DummyResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


class DummySession:
    def __init__(self) -> None:
        self.headers = {}
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        if url.endswith("/oauth2/token"):
            return DummyResponse(
                {
                    "token_type": "bearer",
                    "access_token": "user-access-token",
                    "refresh_token": "refresh-token",
                    "expires_in": 7200,
                    "scope": "tweet.read tweet.write users.read offline.access",
                }
            )
        return DummyResponse({"data": {"id": "tweet-123"}})

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        return DummyResponse({"data": {"id": "user-1", "username": "ufutbolbalear"}})


def build_settings(**overrides) -> Settings:
    payload = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "x_client_id": "client-id",
        "x_redirect_uri": "http://127.0.0.1:8000/callback",
        "x_scopes": "tweet.read tweet.write users.read offline.access",
    }
    payload.update(overrides)
    return Settings(**payload)


def test_x_auth_reports_missing_required_pkce_config() -> None:
    settings = build_settings(x_client_id=" ", x_redirect_uri="")
    assert missing_x_auth_config(settings) == ["X_CLIENT_ID", "X_REDIRECT_URI"]
    try:
        validate_x_auth_config(settings)
    except Exception as exc:
        assert str(exc) == "Missing X auth configuration:\nX_CLIENT_ID\nX_REDIRECT_URI"
    else:
        raise AssertionError("Expected auth config error")


def test_x_auth_builds_authorization_url_with_pkce_parameters() -> None:
    verifier, challenge = generate_pkce_pair()
    settings = build_settings()

    url = build_authorization_url(settings, state="state-123", code_challenge=challenge)

    assert verifier
    assert "https://x.com/i/oauth2/authorize?" in url
    assert "response_type=code" in url
    assert "client_id=client-id" in url
    assert "state=state-123" in url
    assert "code_challenge_method=S256" in url


def test_x_oauth_pkce_client_uses_official_token_endpoint() -> None:
    session = DummySession()
    client = XOAuth2PKCEClient(build_settings(), session=session)

    payload = client.exchange_code(code="auth-code", code_verifier="verifier-123")

    assert payload["access_token"] == "user-access-token"
    method, url, kwargs = session.calls[0]
    assert method == "post"
    assert url == "https://api.x.com/2/oauth2/token"
    assert kwargs["data"]["grant_type"] == "authorization_code"
    assert kwargs["data"]["client_id"] == "client-id"
    assert kwargs["data"]["code_verifier"] == "verifier-123"


def test_x_api_client_posts_to_v2_tweets_with_user_bearer_token() -> None:
    session = DummySession()
    client = XApiClient(build_settings(), session=session)

    response = client.publish_text("user-access-token", XPublishRequest(text="hola", dry_run=False))

    assert response.post_id == "tweet-123"
    method, url, kwargs = session.calls[0]
    assert method == "post"
    assert url == "https://api.x.com/2/tweets"
    assert kwargs["headers"]["Authorization"] == "Bearer user-access-token"
    assert kwargs["json"] == {"text": "hola"}
