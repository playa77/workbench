"""Provider registry implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from caw.errors import ProviderError
from caw.protocols.anthropic_provider import AnthropicProvider
from caw.protocols.openai_provider import OpenAIProvider

if TYPE_CHECKING:
    from caw.core.config import CAWConfig
    from caw.protocols.provider import ModelProvider
    from caw.protocols.types import ProviderHealth


class ProviderRegistry:
    """Registry of available model providers."""

    def __init__(self, config: CAWConfig) -> None:
        self._providers: dict[str, ModelProvider] = {}
        for key, provider_config in config.providers.items():
            if provider_config.type == "anthropic":
                self._providers[key] = AnthropicProvider(provider_config)
            elif provider_config.type in {"openai", "openai_compatible"}:
                self._providers[key] = OpenAIProvider(provider_key=key, config=provider_config)

    def get(self, provider_key: str) -> ModelProvider:
        if provider_key not in self._providers:
            raise ProviderError(
                message=f"Provider not found: {provider_key}",
                code="provider_not_found",
                details={"provider_key": provider_key},
            )
        return self._providers[provider_key]

    def list_providers(self) -> list[str]:
        return list(self._providers.keys())

    async def health_check_all(self) -> dict[str, ProviderHealth]:
        return {key: await provider.health_check() for key, provider in self._providers.items()}
