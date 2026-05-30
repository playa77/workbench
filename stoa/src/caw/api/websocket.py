"""WebSocket endpoint for streaming chat-style responses."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import WebSocket, WebSocketDisconnect

from caw.core.engine import ExecutionRequest
from caw.errors import CAWError, ValidationError_

if TYPE_CHECKING:
    from caw.api.deps import AppServices


async def handle_session_stream(
    websocket: WebSocket, session_id: str, services: AppServices
) -> None:
    """Accept a websocket stream and emit chunked JSON events."""
    await websocket.accept()

    try:
        await services.session_manager.get(session_id)
    except ValidationError_:
        await websocket.send_json(
            {
                "type": "error",
                "error_code": "session_not_found",
                "message": "Session does not exist",
            }
        )
        await websocket.close(code=4404)
        return

    while True:
        try:
            payload = await websocket.receive_json()
        except WebSocketDisconnect:
            return

        if payload.get("type") != "message":
            await websocket.send_json(
                {
                    "type": "error",
                    "error_code": "invalid_message_type",
                    "message": "Expected payload with type='message'",
                }
            )
            continue

        content = payload.get("content", "")
        if not isinstance(content, str) or not content.strip():
            await websocket.send_json(
                {
                    "type": "error",
                    "error_code": "invalid_content",
                    "message": "Message content must be a non-empty string",
                }
            )
            continue

        try:
            result = await services.engine.execute(
                ExecutionRequest(
                    session_id=session_id,
                    content=content,
                    provider=payload.get("provider"),
                    model=payload.get("model"),
                )
            )
            for token in result.content.split(" "):
                if token:
                    await websocket.send_json({"type": "text", "content": f"{token} "})
            await websocket.send_json(
                {
                    "type": "done",
                    "message_id": result.message_id,
                    "tokens_in": result.tokens_in,
                    "tokens_out": result.tokens_out,
                }
            )
        except CAWError as exc:
            await websocket.send_json(
                {"type": "error", "error_code": exc.code, "message": exc.message}
            )
