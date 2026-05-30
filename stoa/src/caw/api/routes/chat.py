"""Chat message endpoints for the CAW API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from caw.api.deps import get_engine
from caw.api.schemas import APIResponse, ExecutionResponse, SendMessageRequest
from caw.core.engine import Engine, ExecutionRequest

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    engine: Annotated[Engine, Depends(get_engine)],
) -> APIResponse[ExecutionResponse]:
    result = await engine.execute(
        ExecutionRequest(
            session_id=session_id,
            content=request.content,
            provider=request.provider,
            model=request.model,
        )
    )
    return APIResponse(
        data=ExecutionResponse(
            session_id=result.session_id,
            message_id=result.message_id,
            content=result.content,
            model=result.model,
            provider=result.provider,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            latency_ms=result.latency_ms,
            trace_id=result.trace_id,
        )
    )
