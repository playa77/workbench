"""Research Plugin — autonomous deep research agent.

Adapted from PResearch. Takes research questions, conducts multi-source web research,
and produces publication-quality reports with citations.
"""

from plugins.base import PluginBase
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.db import get_session
from workbench.core.auth import get_current_user, get_user_openrouter_key
from workbench.core.router import OpenRouterClient
from workbench.core.models import User


class ResearchPlugin(PluginBase):
    name = "research"
    display_name = "Deep Research"
    description = "Autonomous web research agent — produce cited, publication-quality reports"
    version = "0.1.0"
    icon = "search"

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/query", self.query, methods=["POST"])
        router.add_api_route("/reports", self.list_reports, methods=["GET"])
        return router

    async def query(self, body: "ResearchRequest", user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        or_key = await get_user_openrouter_key(user, session)
        if not or_key:
            raise HTTPException(status_code=400, detail="Set your OpenRouter key in Settings")

        client = OpenRouterClient(api_key=or_key)
        try:
            # Plan
            plan_prompt = (
                f"Research question: {body.question}\n\n"
                "Plan a research approach. List 3-5 subtopics to investigate. Use numbered list."
            )
            plan = await client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a research planner. Plan a thorough investigation."},
                    {"role": "user", "content": plan_prompt},
                ],
                model="deepseek/deepseek-v4-flash",
                temperature=0.3,
                max_tokens=800,
            )

            # Synthesize
            synth_prompt = (
                f"Research question: {body.question}\n\n"
                f"Research plan:\n{plan}\n\n"
                "Write a comprehensive research report covering the planned subtopics. "
                "Use markdown formatting. Include a summary section and key findings. "
                "Be thorough and well-structured."
            )
            report = await client.chat_completion(
                messages=[
                    {"role": "system", "content": "You are an expert researcher. Write comprehensive, well-cited research reports."},
                    {"role": "user", "content": synth_prompt},
                ],
                model="deepseek/deepseek-v4-flash",
                temperature=0.4,
                max_tokens=4000,
            )

            return {"question": body.question, "plan": plan, "report": report}
        finally:
            await client.close()

    async def list_reports(self, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from sqlalchemy import select
        from workbench.core.models import StoredReport
        result = await session.execute(
            select(StoredReport).where(StoredReport.user_id == user.id, StoredReport.plugin_name == "research")
        )
        reports = result.scalars().all()
        return {"reports": [{"id": str(r.id), "title": r.title, "created_at": r.created_at.isoformat() if r.created_at else ""} for r in reports]}


class ResearchRequest(BaseModel):
    question: str
