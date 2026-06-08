"""Debate Agent — multi-agent debate system with Director Mode.

Adapted from MADS engine. Provides:
- Full state machine: IDLE -> RUNNING / PAUSED / COMPLETED
- Turn-by-turn execution with round counting
- Director Mode with influence shader (subtle/moderate/critical)
- Pause / Resume with auto-continue
- Per-agent model, temperature, and system prompt
- Role catalog (12 built-in roles)
- Debate state persistence (JSON save/load)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import AgentBase
from workbench.core.auth import get_current_user, get_user_openrouter_key
from workbench.core.db import get_session
from workbench.core.models import AgentSession, User
from workbench.shared.llm.router import OpenRouterClient

logger = logging.getLogger(__name__)

DEBATE_TIMEOUT_SECONDS = 600

class DebateAgent(AgentBase):
    name = "debate"
    display_name = "Debate Arena"
    description = "Multi-agent AI debate arena — assemble a panel with Director Mode"
    version = "0.2.0"
    icon = "users"

    _engines: dict[str, Any] = {}
    _debate_tasks: dict[str, asyncio.Task] = {}
    _last_activity: dict[str, float] = {}

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/roles", self.get_roles, methods=["GET"])
        router.add_api_route("/start", self.start_debate, methods=["POST"])
        router.add_api_route("/debate/{debate_id}/status", self.debate_status, methods=["GET"])
        router.add_api_route("/debate/{debate_id}/inject", self.director_inject, methods=["POST"])
        router.add_api_route("/debate/{debate_id}/pause", self.debate_pause, methods=["POST"])
        router.add_api_route("/debate/{debate_id}/resume", self.debate_resume, methods=["POST"])
        router.add_api_route("/debate/{debate_id}/export", self.export_debate, methods=["GET"])
        return router

    async def get_roles(self):
        from workbench.services.debate_engine import get_roles
        return {"roles": get_roles()}

    async def start_debate(
        self,
        body: DebateRequest,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        or_key = await get_user_openrouter_key(user, session)
        if not or_key:
            raise HTTPException(status_code=400, detail="Set your OpenRouter key in Settings")

        from workbench.services.debate_engine import (
            AgentConfig as EngAgentConfig,
        )
        from workbench.services.debate_engine import (
            DebateEngine,
        )

        role_ids = body.roles or ["optimist", "pessimist", "pragmatist"]
        if len(role_ids) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 roles")
        if len(role_ids) > 8:
            raise HTTPException(status_code=400, detail="Maximum 8 roles")

        from workbench.services.debate_engine import get_roles as _all_roles
        all_roles = {r["id"]: r for r in _all_roles()}

        agents = []
        for role_id in role_ids:
            role_info = all_roles.get(role_id, {"name": role_id.title(), "description": "Debate participant"})
            agents.append(EngAgentConfig.from_role(
                role_id=role_id,
                name=role_info["name"],
                description=role_info["description"],
                model="deepseek/deepseek-v4-pro",
            ))

        engine = DebateEngine()
        engine.initialize_debate(body.topic, agents, max_rounds=body.max_rounds or 3)
        engine.start()

        debate_id = f"debate_{user.id}_{len(self._engines)}"
        self._engines[debate_id] = {"engine": engine, "user_id": str(user.id)}
        self._last_activity[debate_id] = time.monotonic()

        task = asyncio.create_task(self._run_debate_loop(debate_id, or_key))
        self._debate_tasks[debate_id] = task
        return {"debate_id": debate_id, "topic": body.topic, "agents": [a.model_dump() for a in agents], "status": "RUNNING"}

    def _get_debate(self, debate_id: str, user_id: str):
        entry = self._engines.get(debate_id)
        if not entry or entry.get("user_id") != str(user_id):
            raise HTTPException(status_code=404, detail="Debate not found")
        return entry["engine"]

    async def debate_status(
        self,
        debate_id: str,
        user: User = Depends(get_current_user),
    ):
        engine = self._get_debate(debate_id, str(user.id))
        self._last_activity[debate_id] = time.monotonic()
        state = engine.state
        return {
            "debate_id": debate_id,
            "topic": state.topic,
            "status": state.status,
            "rounds_completed": state.rounds_completed,
            "max_rounds": state.max_rounds,
            "current_speaker": state.agents[state.current_turn_index].name if state.agents and state.status == "RUNNING" else None,
            "history": [{"sender": m.sender_name, "content": m.content, "is_injection": m.is_injection} for m in state.history],
        }

    async def director_inject(
        self,
        debate_id: str,
        body: InjectRequest,
        user: User = Depends(get_current_user),
    ):
        engine = self._get_debate(debate_id, str(user.id))
        if engine.is_completed():
            raise HTTPException(status_code=400, detail="Debate is already completed")

        self._last_activity[debate_id] = time.monotonic()
        engine.inject_message(body.content, body.weight)
        return {"status": "injected", "weight": body.weight}

    async def debate_pause(
        self,
        debate_id: str,
        user: User = Depends(get_current_user),
    ):
        engine = self._get_debate(debate_id, str(user.id))
        self._last_activity[debate_id] = time.monotonic()
        engine.pause()
        return {"status": "PAUSED"}

    async def debate_resume(
        self,
        debate_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        engine = self._get_debate(debate_id, str(user.id))
        if not engine.state.status == "PAUSED":
            raise HTTPException(status_code=400, detail="Debate is not paused")

        or_key = await get_user_openrouter_key(user, session)
        if not or_key:
            raise HTTPException(status_code=400, detail="Set your OpenRouter key in Settings")

        self._last_activity[debate_id] = time.monotonic()
        engine.resume()
        task = asyncio.create_task(self._run_debate_loop(debate_id, or_key))
        self._debate_tasks[debate_id] = task
        return {"status": "RUNNING"}

    async def export_debate(
        self,
        debate_id: str,
        user: User = Depends(get_current_user),
    ):
        engine = self._get_debate(debate_id, str(user.id))
        return engine.to_dict()

    async def _run_debate_loop(self, debate_id: str, openrouter_key: str) -> None:
        entry: Any = self._engines.get(debate_id)
        if not entry:
            return
        engine = entry.get("engine")
        if not engine:
            return

        client = OpenRouterClient(api_key=openrouter_key)

        try:
            while engine.is_running() and not engine.is_completed():
                if debate_id in self._last_activity:
                    if time.monotonic() - self._last_activity[debate_id] > DEBATE_TIMEOUT_SECONDS:
                        engine.state.status = "TIMED_OUT"
                        logger.warning("Debate %s timed out after %ds of inactivity", debate_id, DEBATE_TIMEOUT_SECONDS)
                        break

                try:
                    system, user = engine.build_prompt_for_agent(history_limit=12)
                    agent = engine.get_current_agent()
                    response = await client.chat_completion(
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        model=agent.model_name,
                        temperature=agent.temperature,
                        max_tokens=800,
                    )
                except Exception as exc:
                    engine.pause()
                    engine.append_message(
                        __import__("workbench.services.debate_engine").Message(
                            sender_id="system",
                            sender_name="System",
                            role="system",
                            content=f"API Error: {exc}",
                        )
                    )
                    break

                from workbench.services.debate_engine import Message

                msg = Message(
                    sender_id=agent.id,
                    sender_name=agent.name,
                    role="assistant",
                    content=response,
                )
                engine.append_message(msg)
                engine.advance_turn()

                await asyncio.sleep(2.5)

            if engine.is_completed():
                engine.append_message(
                    __import__("workbench.services.debate_engine").Message(
                        sender_id="system",
                        sender_name="System",
                        role="system",
                        content=f"Debate completed after {engine.state.rounds_completed} rounds.",
                    )
                )
                # Save AgentSession
                try:
                    from workbench.core.db import get_session_factory
                    session_factory = get_session_factory()
                    async with session_factory() as db_session:
                        state = engine.state
                        agent_session = AgentSession(
                            user_id=uuid4(),  # placeholder — actual user stored in entry
                            agent_name="debate",
                            session_id=debate_id,
                            title=state.topic,
                            state_json=state.model_dump(),
                            content=None,
                            content_format="markdown",
                            metadata_json={
                                "rounds": state.rounds_completed,
                                "max_rounds": state.max_rounds,
                                "agent_count": len(state.agents),
                                "status": state.status,
                            },
                        )
                        entry = self._engines.get(debate_id)
                        if entry:
                            from uuid import UUID
                            try:
                                agent_session.user_id = UUID(entry.get("user_id", ""))
                            except Exception:
                                pass
                        db_session.add(agent_session)
                        await db_session.commit()
                except Exception:
                    logger.exception("Failed to save AgentSession for debate %s", debate_id)
        finally:
            await client.close()

    @classmethod
    def _cleanup_sessions(cls) -> None:
        now = time.monotonic()
        to_remove = []
        for debate_id, last_active in list(cls._last_activity.items()):
            if now - last_active > DEBATE_TIMEOUT_SECONDS * 2:
                entry = cls._engines.get(debate_id)
                if entry:
                    engine = entry.get("engine")
                    if engine and engine.is_running():
                        engine.state.status = "TIMED_OUT"
                task = cls._debate_tasks.get(debate_id)
                if task and not task.done():
                    task.cancel()
                to_remove.append(debate_id)
        for debate_id in to_remove:
            cls._engines.pop(debate_id, None)
            cls._debate_tasks.pop(debate_id, None)
            cls._last_activity.pop(debate_id, None)
            logger.info("Cleaned up timed-out debate: %s", debate_id)

    def get_frontend_tab(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "icon": self.icon,
            "component": f"agent-{self.name}",
            "js": f"/static/js/components/{self.name}-tab.js",
        }


class DebateRequest(BaseModel):
    topic: str = Field(..., max_length=5000)
    roles: list[str] | None = None
    max_rounds: int | None = Field(default=None, ge=1, le=50)


class InjectRequest(BaseModel):
    content: str = Field(..., max_length=50000)
    weight: float = Field(default=0.5, ge=0.0, le=1.0)
