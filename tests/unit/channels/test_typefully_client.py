from __future__ import annotations

from app.channels.typefully.client import (
    TypefullyApiClient,
    missing_typefully_config,
    validate_typefully_config,
)
from app.channels.typefully.schemas import TypefullyDraftRequest
from app.core.config import Settings


class DummyResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


class DummySession:
    def __init__(self) -> None:
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        if url.endswith("/v2/me"):
            return DummyResponse({"id": "me-1", "username": "ufutbolbalear"})
        return DummyResponse(
            {
                "data": [
                    {
                        "id": "social-set-1",
                        "name": "Cuenta principal",
                    }
                ]
            }
        )

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return DummyResponse({"id": "draft-1", "share_url": "https://typefully.com/share/draft-1"})


def build_settings(**overrides) -> Settings:
    payload = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "typefully_api_key": "typefully-api-key",
        "typefully_api_url": "https://api.typefully.com",
    }
    payload.update(overrides)
    return Settings(**payload)


def test_typefully_reports_missing_required_config() -> None:
    settings = build_settings(typefully_api_key=" ", typefully_api_url="")
    assert missing_typefully_config(settings) == ["TYPEFULLY_API_KEY", "TYPEFULLY_API_URL"]
    try:
        validate_typefully_config(settings)
    except Exception as exc:
        assert str(exc) == "Missing Typefully configuration:\nTYPEFULLY_API_KEY\nTYPEFULLY_API_URL"
    else:
        raise AssertionError("Expected Typefully config error")


def test_typefully_client_uses_v2_endpoints_for_profile_and_social_sets() -> None:
    session = DummySession()
    client = TypefullyApiClient(build_settings(), session=session)

    me = client.verify_credentials()
    social_sets = client.list_social_sets()

    assert me["username"] == "ufutbolbalear"
    assert social_sets[0].id == "social-set-1"
    first_method, first_url, first_kwargs = session.calls[0]
    assert first_method == "get"
    assert first_url == "https://api.typefully.com/v2/me"
    assert first_kwargs["headers"]["Authorization"] == "Bearer typefully-api-key"
    second_method, second_url, second_kwargs = session.calls[1]
    assert second_method == "get"
    assert second_url == "https://api.typefully.com/v2/social-sets"
    assert second_kwargs["headers"]["Authorization"] == "Bearer typefully-api-key"


def test_typefully_client_creates_drafts_under_social_set_v2_endpoint() -> None:
    session = DummySession()
    client = TypefullyApiClient(build_settings(), session=session)

    response = client.create_draft(
        TypefullyDraftRequest(
            social_set_id="social-set-1",
            text="Hola uFutbolBalear",
            dry_run=False,
        )
    )

    assert response["id"] == "draft-1"
    method, url, kwargs = session.calls[0]
    assert method == "post"
    assert url == "https://api.typefully.com/v2/social-sets/social-set-1/drafts"
    assert kwargs["headers"]["Authorization"] == "Bearer typefully-api-key"
    assert kwargs["json"] == {
        "platforms": {
            "x": {
                "enabled": True,
                "posts": [{"text": "Hola uFutbolBalear"}],
            }
        },
    }
