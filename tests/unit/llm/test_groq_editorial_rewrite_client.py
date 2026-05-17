from __future__ import annotations

import json

from app.core.config import Settings
from app.llm.providers.base import LLMConfigurationError
from app.llm.providers.groq import (
    GroqEditorialRewriteClient,
    groq_editorial_rewrite_config_presence,
    missing_groq_editorial_rewrite_config,
    validate_groq_editorial_rewrite_config,
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
                "id": "chatcmpl-1",
                "model": "openai/gpt-oss-20b",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps({"rewritten_text": "Texto reescrito por Groq"})
                        }
                    }
                ],
            }
        )


def build_settings(**overrides) -> Settings:
    payload = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "editorial_rewrite_provider": "groq",
        "editorial_rewrite_api_key": "groq-api-key",
        "editorial_rewrite_api_url": "https://api.groq.com/openai/v1/chat/completions",
        "editorial_rewrite_model": "openai/gpt-oss-20b",
        "editorial_rewrite_max_chars": 280,
    }
    payload.update(overrides)
    return Settings(**payload)


def test_groq_rewrite_reports_missing_required_config() -> None:
    settings = build_settings(editorial_rewrite_api_key=" ", editorial_rewrite_model=None, editorial_rewrite_api_url="")
    assert groq_editorial_rewrite_config_presence(settings) == {
        "EDITORIAL_REWRITE_API_KEY": False,
        "EDITORIAL_REWRITE_MODEL": False,
        "EDITORIAL_REWRITE_API_URL": False,
    }
    assert missing_groq_editorial_rewrite_config(settings) == [
        "EDITORIAL_REWRITE_API_KEY",
        "EDITORIAL_REWRITE_MODEL",
        "EDITORIAL_REWRITE_API_URL",
    ]
    try:
        validate_groq_editorial_rewrite_config(settings)
    except LLMConfigurationError as exc:
        assert str(exc) == (
            "Missing editorial rewrite configuration:\n"
            "EDITORIAL_REWRITE_API_KEY\n"
            "EDITORIAL_REWRITE_MODEL\n"
            "EDITORIAL_REWRITE_API_URL"
        )
    else:
        raise AssertionError("Expected rewrite config error")


def test_groq_rewrite_client_posts_chat_completion_with_json_schema() -> None:
    session = DummySession()
    client = GroqEditorialRewriteClient(build_settings(), session=session)

    response = client.rewrite(
        EditorialRewriteLLMRequest(
            prompt="Reescribe este texto",
            max_chars=280,
        )
    )

    assert response.rewritten_text == "Texto reescrito por Groq"
    method, url, kwargs = session.calls[0]
    assert method == "post"
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer groq-api-key"
    assert kwargs["json"]["model"] == "openai/gpt-oss-20b"
    assert kwargs["json"]["messages"][1]["content"] == "Reescribe este texto"
    assert kwargs["json"]["response_format"]["type"] == "json_schema"
    assert kwargs["json"]["response_format"]["json_schema"]["strict"] is True
    assert (
        kwargs["json"]["response_format"]["json_schema"]["schema"]["properties"]["rewritten_text"]["maxLength"] == 280
    )
