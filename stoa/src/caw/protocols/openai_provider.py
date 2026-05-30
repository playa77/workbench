"""OpenAI and OpenAI-compatible model provider implementation."""

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


class OpenAIProvider(ModelProvider):
    """Provider implementation for OpenAI and OpenAI-compatible APIs."""

    def __init__(self, provider_key: str, config: ProviderConfig) -> None:
        self._provider_key = provider_key
        self._config = config
        self._api_key_env = config.api_key_env or "OPENAI_API_KEY"
        self._client: Any | None = None

    @property
    def provider_id(self) -> str:
        return "openai" if self._config.type == "openai" else self._provider_key

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
        payload_messages = [self._map_message(message) for message in messages]
        payload_tools = [self._map_tool(tool) for tool in tools or []]
        try:
            if stream:
                return self._stream_complete(
                    client, payload_messages, payload_tools, model, max_tokens, temperature
                )
            started = time.perf_counter()
            response = await client.chat.completions.create(
                model=model,
                messages=payload_messages,
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
        del model
        return 128_000

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        api_key = os.getenv(self._api_key_env)
        if not api_key:
            raise ProviderError(
                message=f"Missing API key env var: {self._api_key_env}", code="provider_auth"
            )
        kwargs: dict[str, Any] = {"api_key": api_key, "timeout": self._config.timeout_seconds}
        if self._config.type == "openai_compatible" and self._config.base_url is not None:
            kwargs["base_url"] = self._config.base_url
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:  # pragma: no cover
            raise ProviderError(
                message="openai package is not installed", code="provider_not_installed"
            ) from exc
        self._client = AsyncOpenAI(**kwargs)
        return self._client

    def _map_message(self, message: ProviderMessage) -> dict[str, Any]:
        mapped: dict[str, Any] = {
            "role": message.role,
            "content": message.content
            if isinstance(message.content, str)
            else self._join_content(message),
        }
        if message.name is not None:
            mapped["name"] = message.name
        if message.tool_call_id is not None:
            mapped["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            mapped["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": str(call.arguments)},
                }
                for call in message.tool_calls
            ]
        return mapped

    def _join_content(self, message: ProviderMessage) -> str:
        assert not isinstance(message.content, str)
        return "\n".join(block.text or "" for block in message.content)

    def _map_tool(self, tool: ToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    def _map_response(self, response: Any, model: str, latency_ms: int) -> ProviderResponse:
        choice = response.choices[0]
        message = choice.message
        tool_calls: list[ToolCall] = []
        for tool_call in getattr(message, "tool_calls", []) or []:
            tool_calls.append(
                ToolCall(
                    id=getattr(tool_call, "id", ""),
                    name=getattr(tool_call.function, "name", ""),
                    arguments={},
                )
            )
        usage = getattr(response, "usage", None)
        return ProviderResponse(
            content=getattr(message, "content", "") or "",
            model=getattr(response, "model", model),
            input_tokens=getattr(usage, "prompt_tokens", 0),
            output_tokens=getattr(usage, "completion_tokens", 0),
            latency_ms=latency_ms,
            stop_reason=getattr(choice, "finish_reason", None),
            tool_calls=tool_calls or None,
        )

    async def _stream_complete(
        self,
        client: Any,
        payload_messages: list[dict[str, Any]],
        payload_tools: list[dict[str, Any]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[ProviderStreamChunk]:
        stream = await client.chat.completions.create(
            model=model,
            messages=payload_messages,
            tools=payload_tools or None,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                yield ProviderStreamChunk(delta_text=delta.content)
            if getattr(chunk.choices[0], "finish_reason", None) is not None:
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
