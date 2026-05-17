from __future__ import annotations

from app.core.config import Settings
from app.core.exceptions import ConfigurationError
from app.llm.providers.base import EditorialRewriteProvider
from app.llm.providers.groq import (
    GroqEditorialRewriteClient,
    missing_groq_editorial_rewrite_config,
    groq_editorial_rewrite_config_presence,
)
from app.llm.providers.openai import (
    OpenAIEditorialRewriteClient,
    missing_openai_editorial_rewrite_config,
    openai_editorial_rewrite_config_presence,
)


def build_editorial_rewrite_provider(settings: Settings) -> EditorialRewriteProvider:
    provider = settings.editorial_rewrite_provider.strip().lower()
    if provider == "openai":
        return OpenAIEditorialRewriteClient(settings)
    if provider == "groq":
        return GroqEditorialRewriteClient(settings)
    raise ConfigurationError(f"Proveedor de reescritura editorial no soportado: {settings.editorial_rewrite_provider}")


def editorial_rewrite_provider_ready(settings: Settings) -> bool:
    provider = settings.editorial_rewrite_provider.strip().lower()
    if provider == "openai":
        return all(openai_editorial_rewrite_config_presence(settings).values())
    if provider == "groq":
        return all(groq_editorial_rewrite_config_presence(settings).values())
    return False


def missing_editorial_rewrite_config(settings: Settings) -> list[str]:
    provider = settings.editorial_rewrite_provider.strip().lower()
    if provider == "openai":
        return missing_openai_editorial_rewrite_config(settings)
    if provider == "groq":
        return missing_groq_editorial_rewrite_config(settings)
    raise ConfigurationError(f"Proveedor de reescritura editorial no soportado: {settings.editorial_rewrite_provider}")
