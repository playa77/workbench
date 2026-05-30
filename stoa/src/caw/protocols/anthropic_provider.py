"""Anthropic model provider implementation."""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING, Any

from caw.errors import ProviderError
from caw.protocols.provider import ModelProvider
from caw.protocols.types import (
    ProviderHealth,
    ProviderMessage,
    ProviderResponse,
    ProviderStreamChunk,
    ToolCall,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from caw.core.config import ProviderConfig
    from caw.protocols.types import ToolDefinition

_CONTEXT_WINDOWS: dict[str, int] = {
    "claude-sonnet-4-20250514": 200_000,
    "claude-3-7-sonnet-latest": 200_000,
    "claude-3-5-sonnet-latest": 200_000,
    "claude-3-5-haiku-latest": 200_000,
}


class AnthropicProvider(ModelProvider):
    """Provider implementation for Anthropic models."""

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._api_key_env = config.api_key_env or "ANTHROPIC_API_KEY"
        self._client: Any | None = None

    @property
    def provider_id(self) -> str:
        return "anthropic"

    async def complete(
        self,
        messages: list[ProviderMessage],
        model: str,
        tools: list[ToolDefinition] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        stream: bool = False,
    ) -> ProviderResponse | AsyncIterator[ProviderStreamChunk]:
        client = self._get_client()
        system_prompt, chat_messages = self._split_system_messages(messages)
        payload_tools = [self._map_tool(tool) for tool in tools or []]
        try:
            if stream:
                return self._stream_complete(
                    client=client,
                    model=model,
                    system_prompt=system_prompt,
                    chat_messages=chat_messages,
                    payload_tools=payload_tools,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
            started = time.perf_counter()
            response = await client.messages.create(
                model=model,
                system=system_prompt,
                messages=chat_messages,
                tools=payload_tools or None,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            return self._map_response(response=response, model=model, latency_ms=latency_ms)
        except Exception as exc:
            raise self._map_error(exc) from exc

    async def health_check(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            await self.complete(
                messages=[ProviderMessage(role="user", content="ping")],
                model=self._config.default_model,
                max_tokens=4,
            )
        except ProviderError as exc:
            return ProviderHealth(
                available=False,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=f"{exc.code}: {exc.message}",
            )
        return ProviderHealth(
            available=True, latency_ms=int((time.perf_counter() - started) * 1000)
        )

    def supports_tool_use(self) -> bool:
        return True

    def supports_streaming(self) -> bool:
        return True

    def max_context_window(self, model: str) -> int:
        return _CONTEXT_WINDOWS.get(model, 200_000)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        api_key = os.getenv(self._api_key_env)
        if not api_key:
            raise ProviderError(
                message=f"Missing API key env var: {self._api_key_env}", code="provider_auth"
            )
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                message="anthropic package is not installed", code="provider_not_installed"
            ) from exc
        self._client = AsyncAnthropic(api_key=api_key, timeout=self._config.timeout_seconds)
        return self._client

    def _split_system_messages(
        self, messages: list[ProviderMessage]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts: list[str] = []
        chat_messages: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "system":
                system_parts.append(self._coerce_to_text(message.content))
            else:
                chat_messages.append(
                    {"role": message.role, "content": self._coerce_to_text(message.content)}
                )
        return ("\n\n".join(system_parts) if system_parts else None, chat_messages)

    def _coerce_to_text(self, content: str | list[Any]) -> str:
        return (
            content
            if isinstance(content, str)
            else "\n".join(block.text or "" for block in content)
        )

    def _map_tool(self, tool: ToolDefinition) -> dict[str, Any]:
        return {"name": tool.name, "description": tool.description, "input_schema": tool.parameters}

    def _map_response(self, response: Any, model: str, latency_ms: int) -> ProviderResponse:
        content_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in getattr(response, "content", []):
            if getattr(block, "type", None) == "text":
                content_parts.append(getattr(block, "text", ""))
            elif getattr(block, "type", None) == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=getattr(block, "id", ""),
                        name=getattr(block, "name", ""),
                        arguments=getattr(block, "input", {}),
                    )
                )
        usage = getattr(response, "usage", None)
        return ProviderResponse(
            content="".join(content_parts),
            model=getattr(response, "model", model),
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            latency_ms=latency_ms,
            stop_reason=getattr(response, "stop_reason", None),
            tool_calls=tool_calls or None,
        )

    async def _stream_complete(
        self,
        client: Any,
        model: str,
        system_prompt: str | None,
        chat_messages: list[dict[str, Any]],
        payload_tools: list[dict[str, Any]],
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[ProviderStreamChunk]:
        stream = await client.messages.create(
            model=model,
            system=system_prompt,
            messages=chat_messages,
            tools=payload_tools or None,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for event in stream:
            if getattr(event, "type", "") == "content_block_delta":
                delta = getattr(event, "delta", None)
                if getattr(delta, "type", "") == "text_delta":
                    yield ProviderStreamChunk(delta_text=getattr(delta, "text", ""))
            elif getattr(event, "type", "") == "message_stop":
                yield ProviderStreamChunk(done=True)

    def _map_error(self, error: Exception) -> ProviderError:
        status_code = getattr(error, "status_code", None)
        if status_code == 401:
            return ProviderError(message=str(error), code="provider_auth")
        if status_code == 429:
            return ProviderError(message=str(error), code="provider_rate_limit")
        if isinstance(error, TimeoutError | asyncio.TimeoutError):
            return ProviderError(message=str(error), code="provider_timeout")
        if isinstance(status_code, int) and status_code >= 500:
            return ProviderError(message=str(error), code="provider_server_error")
        return ProviderError(message=str(error), code="provider_request_failed")
