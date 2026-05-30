"""Custom OpenAI-compatible provider — any endpoint with an API key and base URL."""

from __future__ import annotations

from openai import AsyncOpenAI, DefaultAsyncHttpxClient

from presearch.config import PResearchConfig
from presearch.providers.openai.provider import OpenaiProvider

DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
FAST_MODEL = "deepseek/deepseek-v4-pro"


class CustomProvider(OpenaiProvider):
    """Thin wrapper over OpenaiProvider that uses a custom base_url and api_key."""

    def __init__(self, config: PResearchConfig) -> None:
        if not config.custom_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY is required. "
                "Set it via environment variable or PRESEARCH_CUSTOM_API_KEY."
            )
        if not config.custom_api_base:
            raise ValueError(
                "PRESEARCH_CUSTOM_API_BASE is required for the custom provider."
            )
        proxy = config.get_proxy("custom")
        http_client = DefaultAsyncHttpxClient(proxy=proxy) if proxy else None
        self._client = AsyncOpenAI(
            api_key=config.custom_api_key,
            base_url=config.custom_api_base,
            http_client=http_client,
        )
        self._model = config.model
