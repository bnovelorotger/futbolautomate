from __future__ import annotations

import json

import requests

from app.core.config import Settings
from app.llm.providers.base import LLMConfigurationError, LLMProviderError
from app.llm.schemas import EditorialRewriteLLMRequest, EditorialRewriteLLMResponse
from app.utils.time import utcnow

REQUIRED_OPENAI_REWRITE_CONFIG: tuple[str, ...] = (
    "EDITORIAL_REWRITE_API_KEY",
    "EDITORIAL_REWRITE_MODEL",
    "EDITORIAL_REWRITE_API_URL",
)


def openai_editorial_rewrite_config_presence(settings: Settings) -> dict[str, bool]:
    values = {
        "EDITORIAL_REWRITE_API_KEY": settings.editorial_rewrite_api_key,
        "EDITORIAL_REWRITE_MODEL": settings.editorial_rewrite_model,
        "EDITORIAL_REWRITE_API_URL": settings.editorial_rewrite_api_url,
    }
    return {
        key: isinstance(value, str) and value.strip() != ""
        for key, value in values.items()
    }


def missing_openai_editorial_rewrite_config(settings: Settings) -> list[str]:
    presence = openai_editorial_rewrite_config_presence(settings)
    return [key for key in REQUIRED_OPENAI_REWRITE_CONFIG if not presence[key]]


def validate_openai_editorial_rewrite_config(settings: Settings) -> None:
    missing = missing_openai_editorial_rewrite_config(settings)
    if missing:
        raise LLMConfigurationError(
            "Missing editorial rewrite configuration:\n" + "\n".join(missing)
        )


class OpenAIEditorialRewriteClient:
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

    def rewrite(self, request: EditorialRewriteLLMRequest) -> EditorialRewriteLLMResponse:
        validate_openai_editorial_rewrite_config(self.settings)
        response = self.session.post(
            str(self.settings.editorial_rewrite_api_url or "").rstrip("/"),
            json={
                "model": self.settings.editorial_rewrite_model,
                "input": request.prompt,
                "store": False,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "editorial_rewrite_result",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "rewritten_text": {
                                    "type": "string",
                                    "minLength": 1,
                                    "maxLength": request.max_chars,
                                }
                            },
                            "required": ["rewritten_text"],
                            "additionalProperties": False,
                        },
                    }
                },
            },
            timeout=self.settings.request_timeout_seconds,
            headers={"Authorization": f"Bearer {self.settings.editorial_rewrite_api_key or ''}"},
        )
        if response.status_code >= 400:
            raise LLMProviderError(
                f"OpenAI editorial rewrite failed with {response.status_code}: {self._error_detail(response)}"
            )
        body = response.json()
        rewritten_payload = self._output_payload(body)
        rewritten_text = str(rewritten_payload.get("rewritten_text") or "").strip()
        if not rewritten_text:
            raise LLMProviderError(f"Respuesta de OpenAI sin rewritten_text utilizable: {body}")
        return EditorialRewriteLLMResponse(
            rewritten_text=rewritten_text,
            model=str(body.get("model") or self.settings.editorial_rewrite_model or "openai"),
            rewritten_at=utcnow(),
            raw_response=body,
        )

    def _output_payload(self, body: dict) -> dict:
        candidates: list[str] = []
        output_text = body.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            candidates.append(output_text)
        output = body.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for chunk in content:
                    if not isinstance(chunk, dict):
                        continue
                    text = chunk.get("text") or chunk.get("output_text")
                    if isinstance(text, str) and text.strip():
                        candidates.append(text)
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise LLMProviderError(f"Respuesta de OpenAI sin JSON valido de reescritura: {body}")

    @staticmethod
    def _error_detail(response: requests.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            return response.text.strip() or "sin detalle"
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if message:
                    return str(message)
            for key in ("message", "detail"):
                value = body.get(key)
                if value:
                    return str(value)
        return str(body)
