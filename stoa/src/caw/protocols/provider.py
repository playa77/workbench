"""Model provider protocol definition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from caw.protocols.types import (
        ProviderHealth,
        ProviderMessage,
        ProviderResponse,
        ProviderStreamChunk,
        ToolDefinition,
    )


@runtime_checkable
class ModelProvider(Protocol):
    """Interface contract for all model providers."""

    @property
    def provider_id(self) -> str:
        """Return the provider identifier."""

    async def complete(
        self,
        messages: list[ProviderMessage],
        model: str,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        stream: bool = False,
    ) -> ProviderResponse | AsyncIterator[ProviderStreamChunk]:
        """Submit a completion request to the provider."""

    async def health_check(self) -> ProviderHealth:
        """Return health information about provider availability."""

    def supports_tool_use(self) -> bool:
        """Whether this provider supports tool use / function calling."""

    def supports_streaming(self) -> bool:
        """Whether this provider supports streaming completions."""

    def max_context_window(self, model: str) -> int:
        """Return supported context window for a model in tokens."""
