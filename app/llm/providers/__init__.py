from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.llm.providers.base import EditorialRewriteProvider
from app.llm.providers.openai import (
    OpenAIEditorialRewriteClient,
    openai_editorial_rewrite_config_presence,
)


def build_editorial_rewrite_provider(settings: Settings) -> EditorialRewriteProvider:
    provider = settings.editorial_rewrite_provider.strip().lower()
    if provider == "openai":
        return OpenAIEditorialRewriteClient(settings)
    raise ConfigurationError(f"Proveedor de reescritura editorial no soportado: {settings.editorial_rewrite_provider}")


def editorial_rewrite_provider_ready(settings: Settings) -> bool:
    provider = settings.editorial_rewrite_provider.strip().lower()
    if provider == "openai":
        return all(openai_editorial_rewrite_config_presence(settings).values())
    return False

