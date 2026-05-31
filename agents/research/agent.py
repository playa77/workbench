"""Research Agent — autonomous deep research agent with SSE streaming.

Adapted from PResearch/orchestrator.py. Takes research questions, conducts
multi-source web research via function-calling, and produces cited reports.
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
from workbench.core.models import StoredReport, User
from workbench.shared.llm.router import OpenRouterClient

logger = logging.getLogger(__name__)

SESSION_TTL_SECONDS = 3600


class ResearchAgent(AgentBase):
    name = "research"
    display_name = "Deep Research"
    description = "Autonomous web research agent — produce cited, publication-quality reports"
    version = "0.2.0"
    icon = "search"

    _sessions: ClassVar[dict[str, Any]] = {}
    _session_timestamps: ClassVar[dict[str, float]] = {}

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        router.add_api_route("/query", self.start_query, methods=["POST"])
        router.add_api_route("/query/{run_id}/stop", self.stop_query, methods=["POST"])
        router.add_api_route("/query/{run_id}/status", self.get_status, methods=["GET"])
        router.add_api_route("/reports/{run_id}/export", self.export_report, methods=["GET"])
        return router

    @staticmethod
    def _parse_query_params(body: ResearchRequest) -> tuple[str, int, str | None]:
        """Extract research parameters from the request."""
        max_iter = body.max_iterations or 20
        brave_key = body.brave_api_key or None
        return body.question, max_iter, brave_key

    # ---- SSE: start research query ----

    async def start_query(
        self,
        body: ResearchRequest,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        or_key = await get_user_openrouter_key(user, session)
        if not or_key:
            raise HTTPException(status_code=400, detail="Set your OpenRouter key in Settings")

        question, max_iter, brave_key = self._parse_query_params(body)

        from workbench.services.research_orchestrator import (
            ResearchOrchestrator,
            ResearchState,
        )

        state = ResearchState.create(question, max_iterations=max_iter)
        run_id = state.run_id

        client = OpenRouterClient(api_key=or_key)
        orchestrator = ResearchOrchestrator(
            client=client,
            state=state,
            brave_api_key=brave_key,
        )
        self._sessions[run_id] = {"orchestrator": orchestrator, "user_id": str(user.id)}
        self._session_timestamps[run_id] = time.monotonic()

        async def generate_sse():
            try:
                task = asyncio.create_task(orchestrator.run(question))

                async for event_str in orchestrator.event_stream():
                    if task.done() and event_str.startswith("event: ping"):
                        continue
                    yield event_str

                await task
                report = task.result()
                await self._save_report(user, session, question, report, run_id, state)
            except asyncio.CancelledError:
                orchestrator.stop()
                yield 'event: error\ndata: {"message": "Client disconnected"}\n\n'
            except Exception:
                logger.exception("Research agent internal error")
                orchestrator.stop()
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
        question: str,
        report: str,
        run_id: str,
        state: Any,
    ) -> None:
        try:
            from workbench.core.encryption import encrypt_report_content
            title = question[:200] if len(question) <= 200 else question[:197] + "..."
            stored = StoredReport(
                user_id=user.id,
                agent_name="research",
                title=title,
                content=encrypt_report_content(report),
                content_format="markdown",
                metadata_json={
                    "run_id": run_id,
                    "iterations": state.iteration,
                    "sources": state.mind_map.source_count(),
                    "input_tokens": state.token_usage.input_tokens,
                    "output_tokens": state.token_usage.output_tokens,
                },
            )
            session.add(stored)
            await session.commit()
        except Exception:
            pass

    # ---- stop ----

    def _get_research(self, run_id: str, user_id: str):
        entry = self._sessions.get(run_id)
        if not entry or entry.get("user_id") != str(user_id):
            raise HTTPException(status_code=404, detail="Research session not found")
        return entry["orchestrator"]

    async def stop_query(
        self,
        run_id: str,
        user: User = Depends(get_current_user),
    ):
        orchestrator = self._get_research(run_id, str(user.id))
        self._session_timestamps[run_id] = time.monotonic()
        orchestrator.stop()
        return {"status": "STOPPED", "run_id": run_id}

    # ---- status ----

    async def get_status(
        self,
        run_id: str,
        user: User = Depends(get_current_user),
    ):
        orchestrator = self._get_research(run_id, str(user.id))
        self._session_timestamps[run_id] = time.monotonic()
        state = orchestrator.state
        return {
            "run_id": run_id,
            "query": state.query,
            "status": state.status,
            "iteration": state.iteration,
            "max_iterations": state.max_iterations,
            "sources": state.mind_map.source_count(),
            "input_tokens": state.token_usage.input_tokens,
            "output_tokens": state.token_usage.output_tokens,
            "actions": [
                {"tool": a.tool, "summary": a.result_summary, "time": a.timestamp}
                for a in state.actions_log
            ],
            "mind_map_summary": state.mind_map.get_summary(),
            "error": state.error,
        }

    # ---- export ----

    async def export_report(
        self,
        run_id: str,
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        from sqlalchemy import select

        result = await session.execute(
            select(StoredReport).where(
                StoredReport.metadata_json["run_id"].astext == run_id,
                StoredReport.user_id == user.id,
            )
        )
        stored = result.scalars().all()

        if stored:
            from workbench.core.encryption import decrypt_report_content
            report = stored[0]
            return {
                "run_id": run_id,
                "title": report.title,
                "content": decrypt_report_content(report.content),
                "format": report.content_format,
                "created_at": report.created_at.isoformat() if report.created_at else "",
            }

        orchestrator = self._sessions.get(run_id)
        if orchestrator and orchestrator.get("user_id") == str(user.id):
            state = orchestrator["orchestrator"].state
            return {
                "run_id": run_id,
                "title": state.query,
                "content": state.report or state.mind_map.get_summary(),
                "format": "markdown",
                "created_at": "",
            }

        raise HTTPException(status_code=404, detail="Report not found")

    @classmethod
    def _cleanup_sessions(cls) -> None:
        now = time.monotonic()
        to_remove = [rid for rid, ts in list(cls._session_timestamps.items()) if now - ts > SESSION_TTL_SECONDS]
        for rid in to_remove:
            cls._sessions.pop(rid, None)
            cls._session_timestamps.pop(rid, None)
            logger.info("Cleaned up expired research session: %s", rid)

    def get_frontend_tab(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "icon": self.icon,
            "component": f"agent-{self.name}",
            "js": f"/static/js/components/{self.name}-tab.js",
        }


class ResearchRequest(BaseModel):
    question: str = Field(..., max_length=10000)
    max_iterations: int | None = None
    brave_api_key: str | None = None
