from __future__ import annotations

from typing import Protocol

from app.llm.schemas import EditorialRewriteLLMRequest, EditorialRewriteLLMResponse


class LLMConfigurationError(RuntimeError):
    pass


class LLMProviderError(RuntimeError):
    pass


class EditorialRewriteProvider(Protocol):
    def rewrite(self, request: EditorialRewriteLLMRequest) -> EditorialRewriteLLMResponse:
        ...
