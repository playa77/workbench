"""Deliberation capability API endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from caw.api.deps import AppServices, get_services
from caw.api.schemas import APIResponse
from caw.capabilities.deliberation.engine import DeliberationEngine, DeliberationResult
from caw.capabilities.deliberation.frames import FrameConfig

router = APIRouter(prefix="/api/v1/deliberation", tags=["deliberation"])

_DELIBERATIONS: dict[str, DeliberationResult] = {}


class DeliberationFrameRequest(BaseModel):
    frame_id: str
    skill_id: str
    label: str
    provider: str | None = None
    model: str | None = None
    initial_context: str | None = None


class DeliberationRunRequest(BaseModel):
    question: str
    session_id: str = "deliberation"
    rounds: int = Field(default=2, ge=0)
    include_rhetoric_analysis: bool = True
    include_synthesis: bool = True
    frames: list[DeliberationFrameRequest]


@router.post("/run")
async def run_deliberation(
    request: DeliberationRunRequest,
    services: Annotated[AppServices, Depends(get_services)],
) -> APIResponse[dict[str, object]]:
    engine = DeliberationEngine(
        provider_registry=services.provider_registry,
        skill_registry=services.skill_registry,
        trace_collector=services.trace_collector,
    )
    frame_configs = [FrameConfig(**frame.model_dump()) for frame in request.frames]
    result = await engine.deliberate(
        question=request.question,
        frames=frame_configs,
        rounds=request.rounds,
        include_rhetoric_analysis=request.include_rhetoric_analysis,
        include_synthesis=request.include_synthesis,
        session_id=request.session_id,
    )
    deliberation_id = result.trace_id
    _DELIBERATIONS[deliberation_id] = result
    return APIResponse(data={"id": deliberation_id, "result": asdict(result)})


@router.get("/{deliberation_id}")
async def get_deliberation(deliberation_id: str) -> APIResponse[dict[str, object]]:
    result = _DELIBERATIONS[deliberation_id]
    return APIResponse(data={"id": deliberation_id, "result": asdict(result)})


@router.get("/{deliberation_id}/surface")
async def get_deliberation_surface(deliberation_id: str) -> APIResponse[dict[str, object]]:
    result = _DELIBERATIONS[deliberation_id]
    return APIResponse(data={"id": deliberation_id, "surface": asdict(result.disagreement_surface)})
