"""Debate Agent — multi-agent debate system.

Adapted from MADS engine. Web-based debate arena with director mode.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import AgentBase
from workbench.core.auth import get_current_user, get_user_openrouter_key
from workbench.core.db import get_session
from workbench.core.models import User


class DebateAgent(AgentBase):
    name = "debate"
    display_name = "Debate Arena"
    description = "Multi-agent AI debate arena — assemble a panel and watch them debate topics"
    version = "0.1.0"
    icon = "users"

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/roles", self.get_roles, methods=["GET"])
        router.add_api_route("/start", self.start_debate, methods=["POST"])
        return router

    async def get_roles(self):
        return {
            "roles": [
                {"id": "optimist", "name": "Optimist", "description": "Positive, opportunity-focused perspective"},
                {"id": "pessimist", "name": "Pessimist", "description": "Risk-focused, downside analysis"},
                {"id": "pragmatist", "name": "Pragmatist", "description": "Practical, solutions-oriented"},
                {"id": "strategist", "name": "Strategist", "description": "Game-theoretic, long-term planning"},
                {"id": "contrarian", "name": "Contrarian", "description": "Devil's advocate — challenges assumptions"},
                {"id": "historian", "name": "Historian", "description": "Historical precedent and context"},
                {"id": "futurist", "name": "Futurist", "description": "Future-oriented, technological"},
                {"id": "capitalist", "name": "Capitalist", "description": "Free-market economic perspective"},
                {"id": "stoic", "name": "Stoic", "description": "Philosophical, acceptance, virtue"},
            ]
        }

    async def start_debate(
        self,
        body: "DebateRequest",
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        or_key = await get_user_openrouter_key(user, session)
        if not or_key:
            raise HTTPException(status_code=400, detail="Set your OpenRouter key in Settings")

        from workbench.core.router import OpenRouterClient

        roles = body.roles or ["optimist", "pessimist", "pragmatist"]
        client = OpenRouterClient(api_key=or_key)
        messages = []

        try:
            for i, role_id in enumerate(roles[:5]):
                prompt = (
                    f"You are the {role_id.upper()} perspective in a debate.\n"
                    f"Debate topic: {body.topic}\n\n"
                    f"{'Opening statement — make your case.' if i == 0 else 'Respond to the debate so far. Argue from your perspective.'}\n"
                    f"\nDebate history: {chr(10).join(messages[-3:]) if messages else '(none yet)'}"
                )
                response = await client.chat_completion(
                    messages=[
                        {"role": "system", "content": f"You are a {role_id}. Debate the topic from your assigned perspective. Be concise (2-3 paragraphs). Do not break character."},
                        {"role": "user", "content": prompt},
                    ],
                    model="deepseek/deepseek-v4-pro",
                    temperature=0.7,
                    max_tokens=800,
                )
                messages.append(f"[{role_id.upper()}]: {response}")

            return {"topic": body.topic, "roles": roles[:5], "messages": messages}
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
