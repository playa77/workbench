"""Planning Plugin — AI-powered strategic planning.

Adapted from PlanExe. Turns plain-English goals into structured plans.
"""

from plugins.base import PluginBase
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.db import get_session
from workbench.core.auth import get_current_user, get_user_openrouter_key
from workbench.core.router import OpenRouterClient
from workbench.core.models import User


class PlanningPlugin(PluginBase):
    name = "planning"
    display_name = "Strategic Planning"
    description = "AI-powered strategic planning — turn goals into actionable plans with SWOT, WBS, and Gantt charts"
    version = "0.1.0"
    icon = "target"

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/create", self.create_plan, methods=["POST"])
        router.add_api_route("/plans", self.list_plans, methods=["GET"])
        return router

    async def create_plan(self, body: "PlanRequest", user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        or_key = await get_user_openrouter_key(user, session)
        if not or_key:
            raise HTTPException(status_code=400, detail="Set your OpenRouter key in Settings")

        client = OpenRouterClient(api_key=or_key)
        try:
            prompt = (
                f"Goal: {body.goal}\n\n"
                "Create a comprehensive strategic plan. Include:\n"
                "1. Executive Summary\n"
                "2. SWOT Analysis\n"
                "3. Key Objectives (3-5)\n"
                "4. Action Plan with timeline\n"
                "5. Resource Requirements\n"
                "6. Risk Assessment\n"
                "7. Success Metrics\n\n"
                "Use markdown formatting. Be thorough and actionable."
            )
            plan = await client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a senior strategic planner. Create comprehensive, actionable plans."},
                    {"role": "user", "content": prompt},
                ],
                model="deepseek/deepseek-v4-pro",
                temperature=0.5,
                max_tokens=4000,
            )
            return {"goal": body.goal, "plan": plan}
        finally:
            await client.close()

    async def list_plans(self, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from sqlalchemy import select
        from workbench.core.models import StoredReport
        result = await session.execute(
            select(StoredReport).where(StoredReport.user_id == user.id, StoredReport.plugin_name == "planning")
        )
        reports = result.scalars().all()
        return {"plans": [{"id": str(r.id), "title": r.title, "created_at": r.created_at.isoformat() if r.created_at else ""} for r in reports]}


class PlanRequest(BaseModel):
    goal: str
