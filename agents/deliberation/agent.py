"""Deliberation Agent — multi-frame reasoning with critique and synthesis.

Adapted from stoa's capabilities/deliberation/engine.py. Provides:
- Multi-frame deliberation with 8 built-in skill frames
- Multi-round critique (pair-wise frame evaluation)
- Rhetoric analysis (devices, biases, inconsistencies, cross-frame contradictions)
- Disagreement surface mapping (agreements, disagreements, open questions)
- Synthesis with uncertainty awareness
- SSE streaming for real-time progress
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, ClassVar

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import AgentBase
from workbench.core.auth import get_current_user, get_user_openrouter_key
from workbench.core.db import get_session
from workbench.core.models import AgentSession, User
from workbench.shared.llm.router import OpenRouterClient

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 3600


class DeliberationAgent(AgentBase):
    name = "deliberation"
    display_name = "Deliberation"
    description = (
        "Multi-frame AI deliberation engine — explore topics from "
        "multiple perspectives with rigorous critique"
    )
    version = "0.2.0"
    icon = "scale"

    _sessions: ClassVar[dict[str, Any]] = {}
    _session_timestamps: ClassVar[dict[str, float]] = {}

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/frames", self.list_frames, methods=["GET"])
        router.add_api_route("/run", self.run_deliberation, methods=["POST"])
        router.add_api_route("/{deliberation_id}", self.get_deliberation, methods=["GET"])
        router.add_api_route("/{deliberation_id}/surface", self.get_surface, methods=["GET"])
        router.add_api_route("/{deliberation_id}/export", self.export_deliberation, methods=["GET"])
        return router

    # ---- frames ----

    async def list_frames(self):
        from workbench.services.deliberation_service import get_available_frames as frames
        return {"frames": frames()}

    # ---- run (SSE) ----

    async def run_deliberation(
        self,
        body: DeliberationRunRequest,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        or_key = await get_user_openrouter_key(user, session)
        if not or_key:
            raise HTTPException(status_code=400, detail="Set your OpenRouter key in Settings")

        frame_ids = body.frames or ["pro_con", "swot"]
        if len(frame_ids) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 frames")
        if len(frame_ids) > 6:
            raise HTTPException(status_code=400, detail="Maximum 6 frames")

        from workbench.services.deliberation_service import (
            DeliberationService,
            FrameConfig,
            get_available_frames,
        )

        known_frames = {f["frame_id"] for f in get_available_frames()}
        invalid = [fid for fid in frame_ids if fid not in known_frames]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Unknown frames: {', '.join(invalid)}")

        frame_names = {f["frame_id"]: f["label"] for f in get_available_frames()}
        frame_configs = [
            FrameConfig(
                frame_id=fid,
                label=frame_names.get(fid, fid),
                temperature=body.temperature,
            )
            for fid in frame_ids
        ]

        client = OpenRouterClient(api_key=or_key)
        service = DeliberationService(client)

        async def generate_sse():
            task = asyncio.create_task(
                service.deliberate(
                    question=body.question,
                    frame_configs=frame_configs,
                    rounds=body.rounds,
                    include_rhetoric_analysis=body.include_rhetoric_analysis,
                    include_synthesis=body.include_synthesis,
                )
            )

            try:
                async for event_str in service.event_stream():
                    if task.done() and event_str.startswith("event: ping"):
                        continue
                    yield event_str

                result = await task
                self._sessions[result.deliberation_id] = {
                    "result": result, "service": service, "user_id": str(user.id),
                }
                self._session_timestamps[result.deliberation_id] = time.monotonic()

                # Save AgentSession
                try:
                    agent_session = AgentSession(
                        user_id=user.id,
                        agent_name="deliberation",
                        session_id=result.deliberation_id,
                        title=result.question,
                        state_json=result.model_dump(),
                        content=result.synthesis,
                        content_format="markdown",
                        metadata_json={
                            "frame_count": len(result.frames),
                            "rhetoric_analysis": result.rhetoric_analysis is not None,
                            "synthesis_available": result.synthesis is not None,
                            "elapsed_seconds": result.elapsed_seconds,
                            "status": result.status,
                        },
                    )
                    session.add(agent_session)
                    await session.commit()
                except Exception:
                    logger.exception("Failed to save AgentSession for deliberation %s", result.deliberation_id)
            except asyncio.CancelledError:
                yield 'event: error\ndata: {"message": "Client disconnected"}\n\n'
            except Exception:
                logger.exception("Deliberation agent internal error")
                yield 'event: error\ndata: {"message": "An internal error occurred. Check server logs."}\n\n'
            finally:
                await client.close()

        return StreamingResponse(
            generate_sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ---- get ----

    def _get_deliberation(self, deliberation_id: str, user_id: str):
        entry = self._sessions.get(deliberation_id)
        if not entry or entry.get("user_id") != str(user_id):
            raise HTTPException(status_code=404, detail="Deliberation not found")
        return entry["result"]

    async def get_deliberation(
        self,
        deliberation_id: str,
        user: User = Depends(get_current_user),
    ):
        result = self._get_deliberation(deliberation_id, str(user.id))
        self._session_timestamps[deliberation_id] = time.monotonic()
        return {
            "deliberation_id": result.deliberation_id,
            "question": result.question,
            "status": result.status,
            "elapsed_seconds": result.elapsed_seconds,
            "frames": [
                {
                    "frame_id": f.frame_id,
                    "label": f.label,
                    "position": f.position,
                    "critique_count": len(f.critiques),
                }
                for f in result.frames
            ],
            "rhetoric_summary": (
                {
                    "devices": len(result.rhetoric_analysis.devices),
                    "biases": len(result.rhetoric_analysis.biases),
                    "inconsistencies": len(
                        result.rhetoric_analysis.inconsistencies
                    ),
                    "cross_frame_contradictions": len(
                        result.rhetoric_analysis.cross_frame_contradictions
                    ),
                }
                if result.rhetoric_analysis
                else None
            ),
            "surface_summary": {
                "agreements": len(result.disagreement_surface.agreements),
                "disagreements": len(result.disagreement_surface.disagreements),
                "open_questions": len(result.disagreement_surface.open_questions),
            },
            "synthesis_available": result.synthesis is not None,
            "error": result.error,
        }

    # ---- surface ----

    async def get_surface(
        self,
        deliberation_id: str,
        user: User = Depends(get_current_user),
    ):
        result = self._get_deliberation(deliberation_id, str(user.id))
        self._session_timestamps[deliberation_id] = time.monotonic()
        return {
            "deliberation_id": result.deliberation_id,
            "question": result.question,
            "surface": result.disagreement_surface.model_dump(),
        }

    # ---- export ----

    async def export_deliberation(
        self,
        deliberation_id: str,
        user: User = Depends(get_current_user),
    ):
        result = self._get_deliberation(deliberation_id, str(user.id))
        self._session_timestamps[deliberation_id] = time.monotonic()
        return result.model_dump()

    @classmethod
    def _cleanup_sessions(cls) -> None:
        now = time.monotonic()
        to_remove = [did for did, ts in list(cls._session_timestamps.items()) if now - ts > SESSION_TTL_SECONDS]
        for did in to_remove:
            cls._sessions.pop(did, None)
            cls._session_timestamps.pop(did, None)
            logger.info("Cleaned up expired deliberation session: %s", did)

    def get_frontend_tab(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "icon": self.icon,
            "component": f"agent-{self.name}",
            "js": f"/static/js/components/{self.name}-tab.js",
        }


class DeliberationRunRequest(BaseModel):
    question: str = Field(..., max_length=10000)
    frames: list[str] | None = None
    rounds: int = Field(default=2, ge=0, le=5)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    include_rhetoric_analysis: bool = True
    include_synthesis: bool = True
