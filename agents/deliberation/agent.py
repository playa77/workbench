"""Deliberation Agent — multi-frame deliberation engine.

Adapted from stoa's capabilities/deliberation.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import AgentBase
from workbench.core.auth import get_current_user, get_user_openrouter_key
from workbench.core.db import get_session
from workbench.core.models import User
from workbench.core.router import OpenRouterClient


class DeliberationAgent(AgentBase):
    name = "deliberation"
    display_name = "Deliberation"
    description = "Multi-frame AI deliberation engine — explore topics from multiple perspectives"
    version = "0.1.0"
    icon = "scale"

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/analyze", self.analyze, methods=["POST"])
        router.add_api_route("/frames", self.get_frames, methods=["GET"])
        return router

    async def get_frames(self):
        return {
            "frames": [
                {"id": "pro_con", "name": "Pro / Con"},
                {"id": "swot", "name": "SWOT Analysis"},
                {"id": "forces", "name": "Driving Forces"},
                {"id": "stakeholder", "name": "Stakeholder Perspectives"},
            ]
        }

    async def analyze(
        self,
        body: "DeliberationRequest",
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        or_key = await get_user_openrouter_key(user, session)
        if not or_key:
            raise HTTPException(status_code=400, detail="Set your OpenRouter key in Settings")

        frame = body.frame or "pro_con"
        client = OpenRouterClient(api_key=or_key)
        try:
            if frame == "pro_con":
                prompt = f"Analyze this topic from both pro and con perspectives. First the PRO case, then the CON case, then a balanced synthesis:\n\n{body.question}"
            elif frame == "swot":
                prompt = f"Perform a SWOT analysis of this topic. Cover Strengths, Weaknesses, Opportunities, and Threats:\n\n{body.question}"
            else:
                prompt = f"Analyze this topic from multiple perspectives, providing a structured, balanced analysis:\n\n{body.question}"

            response = await client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are an expert analyst. Provide thorough, balanced, structured analysis."},
                    {"role": "user", "content": prompt},
                ],
                model="deepseek/deepseek-v4-flash",
                temperature=0.5,
                max_tokens=3000,
            )
            return {"frame": frame, "analysis": response}
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


class DeliberationRequest(BaseModel):
    question: str
    frame: str | None = "pro_con"
