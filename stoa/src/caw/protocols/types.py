"""Normalized provider-layer data structures.

These dataclasses represent the stable protocol boundary between higher-level orchestration
logic and concrete model provider SDKs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ContentBlock:
    """A structured content block in a provider message."""

    type: str
    text: str | None = None
    media_type: str | None = None
    data: str | None = None
    source_uri: str | None = None


@dataclass(slots=True)
class ToolCall:
    """A model-initiated request to invoke a tool."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolResult:
    """The result of a tool invocation."""

    tool_name: str
    success: bool
    output: str | dict[str, Any] | list[Any]
    error: str | None = None
    duration_ms: int = 0
    tool_call_id: str | None = None


@dataclass(slots=True)
class ToolDefinition:
    """A tool declaration supplied to model providers."""

    name: str
    description: str
    parameters: dict[str, Any]
    permission_level: str
    server_id: str


@dataclass(slots=True)
class ProviderMessage:
    """A normalized message in a provider request/response conversation."""

    role: str
    content: str | list[ContentBlock]
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass(slots=True)
class ProviderResponse:
    """A full non-streaming provider response payload."""

    content: str | list[ContentBlock]
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    stop_reason: str | None = None
    tool_calls: list[ToolCall] | None = None
    raw_response: dict[str, Any] | None = None


@dataclass(slots=True)
class ProviderStreamChunk:
    """A partial streaming event emitted during completion."""

    delta_text: str = ""
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    done: bool = False


@dataclass(slots=True)
class ProviderHealth:
    """Provider health status and optional diagnostics."""

    available: bool
    latency_ms: int | None = None
    error: str | None = None
