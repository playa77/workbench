"""Planning Agent — AI-powered strategic planning with 9 plan types.

Adapted from PlanExe. Transforms goals into structured plans: project plans,
SWOT analyses, executive summaries, WBS, schedules, RCA, pitches, governance
frameworks, and team compositions. SSE streaming for real-time generation.
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
from workbench.core.models import AgentSession, StoredReport, User
from workbench.shared.llm.router import OpenRouterClient

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 3600

# Simple language detection: count German vs English common words
_DE_WORDS = frozenset({
    "der", "die", "das", "und", "ist", "sind", "ein", "eine", "auf", "für",
    "mit", "von", "zu", "im", "den", "dem", "des", "sich", "nicht", "auch",
    "werden", "hat", "bei", "nach", "aus", "über", "zum", "zur", "unter",
    "vor", "zwischen", "durch", "gegen", "ohne", "um", "bis", "seit",
    "dass", "wenn", "aber", "oder", "weil", "kann", "soll", "wurde",
})
_EN_WORDS = frozenset({
    "the", "a", "an", "and", "is", "are", "was", "were", "for", "with",
    "from", "to", "in", "on", "at", "by", "of", "that", "this", "it",
    "not", "also", "will", "has", "have", "but", "or", "because",
})

def _detect_language(text: str) -> str:
    """Detect whether text is German or English by counting common words."""
    words = text.lower().split()
    de_count = sum(1 for w in words if w in _DE_WORDS)
    en_count = sum(1 for w in words if w in _EN_WORDS)
    if de_count > en_count * 1.5:
        return "de"
    return "en"


class PlanningAgent(AgentBase):
    name = "planning"
    display_name = "Strategic Planning"
    description = (
        "AI-powered strategic planning — 9 plan types including project plans, "
        "SWOT, WBS, RCA, pitches, and governance frameworks"
    )
    version = "0.2.0"
    icon = "target"

    _sessions: ClassVar[dict[str, Any]] = {}
    _session_timestamps: ClassVar[dict[str, float]] = {}

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/types", self.list_plan_types, methods=["GET"])
        router.add_api_route("/runs", self.start_run, methods=["POST"])
        router.add_api_route("/runs/{run_id}", self.get_status, methods=["GET"])
        router.add_api_route("/runs/{run_id}/stop", self.stop_run, methods=["POST"])
        router.add_api_route("/runs/{run_id}/export", self.export_result, methods=["GET"])
        return router

    # ---- plan types ----

    async def list_plan_types(self):
        from workbench.services.planning_service import get_plan_types as types
        return {"plan_types": types()}

    # ---- runs (SSE) ----

    async def start_run(
        self,
        body: PlanRunRequest,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        or_key = await get_user_openrouter_key(user, session)
        if not or_key:
            raise HTTPException(status_code=400, detail="Set your OpenRouter key in Settings")

        from workbench.services.planning_service import (
            PLAN_TYPES,
            PlanningService,
        )

        plan_type = body.plan_type or "project_plan"
        if plan_type not in PLAN_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown plan type: {plan_type}. Available: {', '.join(PLAN_TYPES)}",
            )

        client = OpenRouterClient(api_key=or_key)
        service = PlanningService(client)
        lang = _detect_language(body.goal)

        async def generate_sse():
            task = asyncio.create_task(
                service.run(
                    goal=body.goal,
                    plan_type=plan_type,
                    model=body.model,
                    temperature=body.temperature,
                    language=lang,
                )
            )

            try:
                async for event_str in service.event_stream():
                    if task.done() and event_str.startswith("event: ping"):
                        continue
                    yield event_str

                result = await task
                self._sessions[service.state.run_id] = (result, service.state)
                self._session_timestamps[service.state.run_id] = time.monotonic()

                await self._save_report(
                    user, session, body.goal, plan_type, result.content,
                    service.state.run_id, service.state,
                )
            except asyncio.CancelledError:
                service.stop()
                yield 'event: error\ndata: {"message": "Client disconnected"}\n\n'
            except Exception:
                logger.exception("Planning agent internal error")
                service.stop()
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

    @staticmethod
    async def _save_report(
        user: User,
        session: AsyncSession,
        goal: str,
        plan_type: str,
        content: str,
        run_id: str,
        state: Any,
    ) -> None:
        try:
            from workbench.core.encryption import encrypt_report_content
            from workbench.services.planning_service import PLAN_TYPES
            plan_name = PLAN_TYPES.get(plan_type, {}).get("name", plan_type)
            title_line = content.split("\n")[0] if content else goal
            title = f"[{plan_name}] {title_line[:200]}"
            if len(title) > 500:
                title = title[:497] + "..."

            stored = StoredReport(
                user_id=user.id,
                agent_name="planning",
                title=title,
                content=encrypt_report_content(content),
                content_format="markdown",
                metadata_json={
                    "run_id": run_id,
                    "plan_type": plan_type,
                    "goal": goal[:500],
                },
            )
            session.add(stored)

            agent_session = AgentSession(
                user_id=user.id,
                agent_name="planning",
                session_id=run_id,
                title=title,
                state_json=state.model_dump(),
                content=content,
                content_format="markdown",
                metadata_json={
                    "run_id": run_id,
                    "plan_type": plan_type,
                    "goal": goal[:500],
                },
            )
            session.add(agent_session)
            await session.commit()
        except Exception:
            pass

    # ---- status ----

    async def get_status(
        self,
        run_id: str,
        user: User = Depends(get_current_user),
    ):
        from workbench.services.planning_service import PLAN_TYPES

        entry = self._sessions.get(run_id)
        if not entry:
            result = await self._load_from_db(user, run_id)
            if result:
                return result
            raise HTTPException(status_code=404, detail="Plan not found")

        _, state = entry
        self._session_timestamps[run_id] = time.monotonic()
        plan_info = PLAN_TYPES.get(state.plan_type, {})
        return {
            "run_id": state.run_id,
            "goal": state.goal,
            "plan_type": state.plan_type,
            "plan_name": plan_info.get("name", state.plan_type),
            "status": state.status,
            "model": state.model,
            "content_length": len(state.result),
            "elapsed_seconds": state.elapsed_seconds,
            "error": state.error,
        }

    async def _load_from_db(
        self, user: User, run_id: str,
    ) -> dict | None:
        from sqlalchemy import select
        try:
            from workbench.core.db import get_session_factory
            session_factory = get_session_factory()
            async with session_factory() as sess:
                result = await sess.execute(
                    select(StoredReport).where(
                        StoredReport.metadata_json["run_id"].astext == run_id,
                        StoredReport.user_id == user.id,
                    )
                )
                stored = result.scalars().all()
                if stored:
                    r = stored[0]
                    return {
                        "run_id": run_id,
                        "goal": "",
                        "plan_type": r.metadata_json.get("plan_type", ""),
                        "plan_name": "",
                        "status": "COMPLETED",
                        "model": "",
                        "content_length": len(r.content),
                        "elapsed_seconds": 0,
                        "error": "",
                        "from_db": True,
                    }
        except Exception:
            pass
        return None

    # ---- stop ----

    async def stop_run(
        self,
        run_id: str,
        user: User = Depends(get_current_user),
    ):
        entry = self._sessions.get(run_id)
        if not entry:
            raise HTTPException(status_code=404, detail="Plan run not found")
        _result, state = entry
        self._session_timestamps[run_id] = time.monotonic()
        return {"run_id": run_id, "status": state.status, "stopped": True}

    # ---- export ----

    async def export_result(
        self,
        run_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        entry = self._sessions.get(run_id)
        if entry:
            self._session_timestamps[run_id] = time.monotonic()
            _result, state = entry
            return {
                "run_id": state.run_id,
                "goal": state.goal,
                "plan_type": state.plan_type,
                "content": state.result,
                "format": "markdown",
                "elapsed_seconds": state.elapsed_seconds,
            }

        from sqlalchemy import select
        stored_result = await session.execute(
            select(StoredReport).where(
                StoredReport.metadata_json["run_id"].astext == run_id,
                StoredReport.user_id == user.id,
            )
        )
        stored = stored_result.scalars().all()
        if stored:
            from workbench.core.encryption import decrypt_report_content
            r = stored[0]
            return {
                "run_id": run_id,
                "goal": r.metadata_json.get("goal", ""),
                "plan_type": r.metadata_json.get("plan_type", ""),
                "content": decrypt_report_content(r.content),
                "format": r.content_format,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }

        raise HTTPException(status_code=404, detail="Plan not found")

    @classmethod
    def _cleanup_sessions(cls) -> None:
        now = time.monotonic()
        to_remove = [rid for rid, ts in list(cls._session_timestamps.items()) if now - ts > SESSION_TTL_SECONDS]
        for rid in to_remove:
            cls._sessions.pop(rid, None)
            cls._session_timestamps.pop(rid, None)
            logger.info("Cleaned up expired planning session: %s", rid)

    def get_frontend_tab(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "icon": self.icon,
            "component": f"agent-{self.name}",
            "js": f"/static/js/components/{self.name}-tab.js",
        }


class PlanRunRequest(BaseModel):
    goal: str = Field(..., max_length=10000)
    plan_type: str | None = "project_plan"
    model: str = "deepseek/deepseek-v4-pro"
    temperature: float = Field(default=0.5, ge=0.0, le=2.0)
