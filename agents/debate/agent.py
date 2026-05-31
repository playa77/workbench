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
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import AgentBase
from workbench.core.auth import get_current_user, get_user_openrouter_key
from workbench.core.db import get_session
from workbench.core.models import User
from workbench.shared.llm.router import OpenRouterClient


class DebateAgent(AgentBase):
    name = "debate"
    display_name = "Debate Arena"
    description = "Multi-agent AI debate arena — assemble a panel with Director Mode"
    version = "0.2.0"
    icon = "users"

    _engines: dict[str, Any] = {}

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
        self._engines[debate_id] = engine

        # Run debate turns asynchronously
        asyncio.create_task(self._run_debate_loop(debate_id, or_key))
        return {"debate_id": debate_id, "topic": body.topic, "agents": [a.model_dump() for a in agents], "status": "RUNNING"}

    async def debate_status(
        self,
        debate_id: str,
        user: User = Depends(get_current_user),
    ):
        engine = self._engines.get(debate_id)
        if not engine:
            raise HTTPException(status_code=404, detail="Debate not found")
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
        engine = self._engines.get(debate_id)
        if not engine:
            raise HTTPException(status_code=404, detail="Debate not found")
        if engine.is_completed():
            raise HTTPException(status_code=400, detail="Debate is already completed")

        engine.inject_message(body.content, body.weight)
        return {"status": "injected", "weight": body.weight}

    async def debate_pause(
        self,
        debate_id: str,
        user: User = Depends(get_current_user),
    ):
        engine = self._engines.get(debate_id)
        if not engine:
            raise HTTPException(status_code=404, detail="Debate not found")
        engine.pause()
        return {"status": "PAUSED"}

    async def debate_resume(
        self,
        debate_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        engine = self._engines.get(debate_id)
        if not engine:
            raise HTTPException(status_code=404, detail="Debate not found")
        if not engine.state.status == "PAUSED":
            raise HTTPException(status_code=400, detail="Debate is not paused")

        or_key = await get_user_openrouter_key(user, session)
        if not or_key:
            raise HTTPException(status_code=400, detail="Set your OpenRouter key in Settings")

        engine.resume()
        asyncio.create_task(self._run_debate_loop(debate_id, or_key))
        return {"status": "RUNNING"}

    async def export_debate(
        self,
        debate_id: str,
        user: User = Depends(get_current_user),
    ):
        engine = self._engines.get(debate_id)
        if not engine:
            raise HTTPException(status_code=404, detail="Debate not found")
        return engine.to_dict()

    async def _run_debate_loop(self, debate_id: str, openrouter_key: str) -> None:
        engine: Any = self._engines.get(debate_id)
        if not engine:
            return

        client = OpenRouterClient(api_key=openrouter_key)

        try:
            while engine.is_running() and not engine.is_completed():
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
        finally:
            await client.close()

    def get_frontend_tab(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "icon": self.icon,
            "component": f"agent-{self.name}",
            "js": f"/static/js/components/{self.name}-tab.js",
        }


class DebateRequest(BaseModel):
    topic: str
    roles: list[str] | None = None
    max_rounds: int | None = None


class InjectRequest(BaseModel):
    content: str
    weight: float = 0.5
