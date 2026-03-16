from __future__ import annotations

import json

from app.core.config import Settings
from app.llm.providers.base import LLMConfigurationError
from app.llm.providers.openai import (
    OpenAIEditorialRewriteClient,
    missing_openai_editorial_rewrite_config,
    validate_openai_editorial_rewrite_config,
)
from app.llm.schemas import EditorialRewriteLLMRequest


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

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return DummyResponse(
            {
                "id": "resp_1",
                "model": "gpt-4.1-mini",
                "output_text": json.dumps({"rewritten_text": "Texto reescrito limpio"}),
            }
        )


def build_settings(**overrides) -> Settings:
    payload = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "editorial_rewrite_provider": "openai",
        "editorial_rewrite_api_key": "openai-api-key",
        "editorial_rewrite_api_url": "https://api.openai.com/v1/responses",
        "editorial_rewrite_model": "gpt-4.1-mini",
        "editorial_rewrite_max_chars": 280,
    }
    payload.update(overrides)
    return Settings(**payload)


def test_openai_rewrite_reports_missing_required_config() -> None:
    settings = build_settings(editorial_rewrite_api_key=" ", editorial_rewrite_model=None, editorial_rewrite_api_url="")
    assert missing_openai_editorial_rewrite_config(settings) == [
        "EDITORIAL_REWRITE_API_KEY",
        "EDITORIAL_REWRITE_MODEL",
        "EDITORIAL_REWRITE_API_URL",
    ]
    try:
        validate_openai_editorial_rewrite_config(settings)
    except LLMConfigurationError as exc:
        assert str(exc) == (
            "Missing editorial rewrite configuration:\n"
            "EDITORIAL_REWRITE_API_KEY\n"
            "EDITORIAL_REWRITE_MODEL\n"
            "EDITORIAL_REWRITE_API_URL"
        )
    else:
        raise AssertionError("Expected rewrite config error")


def test_openai_rewrite_client_posts_to_responses_api_with_json_schema() -> None:
    session = DummySession()
    client = OpenAIEditorialRewriteClient(build_settings(), session=session)

    response = client.rewrite(
        EditorialRewriteLLMRequest(
            prompt="Reescribe este texto",
            max_chars=280,
        )
    )

    assert response.rewritten_text == "Texto reescrito limpio"
    method, url, kwargs = session.calls[0]
    assert method == "post"
    assert url == "https://api.openai.com/v1/responses"
    assert kwargs["headers"]["Authorization"] == "Bearer openai-api-key"
    assert kwargs["json"]["model"] == "gpt-4.1-mini"
    assert kwargs["json"]["input"] == "Reescribe este texto"
    assert kwargs["json"]["store"] is False
    assert kwargs["json"]["text"]["format"]["type"] == "json_schema"
    assert kwargs["json"]["text"]["format"]["schema"]["properties"]["rewritten_text"]["maxLength"] == 280
