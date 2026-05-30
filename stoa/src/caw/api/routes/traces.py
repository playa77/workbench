"""Trace read endpoints for replay and diagnostics."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from caw.api.deps import get_replay_engine, get_trace_collector
from caw.api.schemas import APIResponse, TraceEventResponse
from caw.traces.collector import TraceCollector
from caw.traces.replay import ReplayEngine

router = APIRouter(prefix="/api/v1", tags=["traces"])


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    collector: Annotated[TraceCollector, Depends(get_trace_collector)],
) -> APIResponse[list[TraceEventResponse]]:
    events = await collector.get_trace(trace_id)
    data = [
        TraceEventResponse(
            id=event.id,
            trace_id=event.trace_id,
            session_id=event.session_id,
            timestamp=event.timestamp,
            event_type=event.event_type,
            data=event.data,
            parent_event_id=event.parent_event_id,
        )
        for event in events
    ]
    return APIResponse(data=data)


@router.get("/traces/{trace_id}/summary")
async def get_trace_summary(
    trace_id: str,
    replay_engine: Annotated[ReplayEngine, Depends(get_replay_engine)],
) -> APIResponse[dict[str, object]]:
    summary = await replay_engine.summary(trace_id)
    return APIResponse(
        data={
            "trace_id": summary.trace_id,
            "session_id": summary.session_id,
            "mode": summary.mode,
            "started_at": summary.started_at.isoformat(),
            "completed_at": summary.completed_at.isoformat() if summary.completed_at else None,
            "duration_ms": summary.duration_ms,
            "event_count": summary.event_count,
            "provider_calls": summary.provider_calls,
            "tool_calls": summary.tool_calls,
            "errors": summary.errors,
        }
    )
