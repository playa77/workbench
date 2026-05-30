"""Mock model provider for tests and local development."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from caw.errors import ProviderError
from caw.protocols.provider import ModelProvider
from caw.protocols.types import ProviderHealth, ProviderResponse, ProviderStreamChunk

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from caw.protocols.types import ProviderMessage, ToolDefinition


class MockProvider(ModelProvider):
    """Mock model provider for testing."""

    def __init__(
        self,
        provider_id: str = "mock",
        response_text: str = "Mock response.",
        latency_ms: int = 0,
        fail: bool = False,
        fail_message: str = "Simulated provider failure",
        token_count_in: int = 10,
        token_count_out: int = 20,
    ) -> None:
        self._provider_id = provider_id
        self._response_text = response_text
        self._latency_ms = latency_ms
        self._fail = fail
        self._fail_message = fail_message
        self._token_count_in = token_count_in
        self._token_count_out = token_count_out

    @property
    def provider_id(self) -> str:
        return self._provider_id

    async def complete(
        self,
        messages: list[ProviderMessage],
        model: str,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        stream: bool = False,
    ) -> ProviderResponse | AsyncIterator[ProviderStreamChunk]:
        del messages, tools, max_tokens, temperature
        await self._simulate_latency()
        self._maybe_raise_failure()
        if stream:
            return self._stream_response(model)
        return ProviderResponse(
            content=self._response_text,
            model=model,
            input_tokens=self._token_count_in,
            output_tokens=self._token_count_out,
            latency_ms=self._latency_ms,
        )

    async def health_check(self) -> ProviderHealth:
        await self._simulate_latency()
        if self._fail:
            return ProviderHealth(
                available=False, latency_ms=self._latency_ms, error=self._fail_message
            )
        return ProviderHealth(available=True, latency_ms=self._latency_ms)

    def supports_tool_use(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True

    def max_context_window(self, model: str) -> int:
        del model
        return 200_000

    async def _simulate_latency(self) -> None:
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000)

    def _maybe_raise_failure(self) -> None:
        if self._fail:
            raise ProviderError(message=self._fail_message, code="provider_mock_failure")

    async def _stream_response(self, model: str) -> AsyncIterator[ProviderStreamChunk]:
        del model
        for token in self._response_text.split(" "):
            yield ProviderStreamChunk(delta_text=f"{token} ")
        yield ProviderStreamChunk(done=True)
