"""Chat capability handler with streaming-friendly chunk output."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from caw.core.engine import Engine, ExecutionRequest
from caw.errors import CAWError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass(slots=True)
class StreamChunk:
    """A normalized chunk emitted while a chat message is being handled."""

    type: str
    content: str | None = None
    data: dict[str, object] | None = None


class ChatHandler:
    """Handle chat messages by delegating orchestration to the engine."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    async def handle_message(
        self,
        session_id: str,
        message: str,
        attachments: list[object] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Process a message and yield stream chunks.

        The current orchestration engine returns a complete response payload.
        This handler normalizes that payload into stream chunks so API clients
        can consume a single streaming interface now and remain forward-compatible
        with true token streaming later.
        """
        try:
            result = await self._engine.execute(
                ExecutionRequest(
                    session_id=session_id,
                    content=message,
                    attachments=attachments,
                )
            )
        except CAWError as exc:
            yield StreamChunk(type="error", content=exc.message, data={"code": exc.code})
            yield StreamChunk(type="done", data={"ok": False, "error": exc.code})
            return

        if result.content:
            yield StreamChunk(type="text", content=result.content)

        yield StreamChunk(
            type="done",
            data={
                "ok": True,
                "session_id": result.session_id,
                "message_id": result.message_id,
                "provider": result.provider,
                "model": result.model,
                "tokens": {"input": result.tokens_in, "output": result.tokens_out},
                "latency_ms": result.latency_ms,
                "trace_id": result.trace_id,
            },
        )

    async def collect_response(
        self,
        session_id: str,
        message: str,
        attachments: list[object] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Collect streamed chunks into a complete non-streaming response."""
        text_parts: list[str] = []
        done_data: dict[str, Any] = {}

        async for chunk in self.handle_message(session_id, message, attachments):
            if chunk.type == "text" and chunk.content is not None:
                text_parts.append(chunk.content)
            if chunk.type == "done" and chunk.data is not None:
                done_data = dict(chunk.data)

        return "".join(text_parts), done_data
