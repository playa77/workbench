"""Workbench News Pipeline Agent.

Adapted from ai_news_scraper. Provides:
- Multi-interest RSS feed management with full CRUD + editing
- AI-powered theme identification and content generation
- German script support (script_de)
- Background scheduler with catch-up
- Email delivery via SMTP
- Per-user interests, schedules, feeds, and pipeline runs
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import AgentBase
from workbench.core.auth import get_current_user, get_user_openrouter_key
from workbench.core.db import get_session
from workbench.core.models import AgentSession, User

_news_scheduler: Any = None


def get_scheduler():
    return _news_scheduler


def set_scheduler(scheduler: Any) -> None:
    global _news_scheduler
    _news_scheduler = scheduler


class NewsAgent(AgentBase):
    name = "news"
    display_name = "News Pipeline"
    description = "Multi-interest AI-powered RSS news scraper, theme analyzer, and content generator"
    version = "0.2.0"
    icon = "newspaper"

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        self._register_routes(router)
        return router

    def _register_routes(self, router: APIRouter) -> None:
        # Interest CRUD
        router.add_api_route("/interests", self.list_interests, methods=["GET"])
        router.add_api_route("/interests", self.create_interest, methods=["POST"])
        router.add_api_route("/interests/{interest_id}", self.update_interest, methods=["PATCH"])
        router.add_api_route("/interests/{interest_id}", self.delete_interest, methods=["DELETE"])
        # Feed CRUD
        router.add_api_route("/interests/{interest_id}/feeds", self.list_feeds, methods=["GET"])
        router.add_api_route("/interests/{interest_id}/feeds", self.add_feed, methods=["POST"])
        router.add_api_route("/interests/{interest_id}/feeds/{feed_id}", self.update_feed, methods=["PATCH"])
        router.add_api_route("/interests/{interest_id}/feeds/{feed_id}", self.delete_feed, methods=["DELETE"])
        # Pipeline
        router.add_api_route("/interests/{interest_id}/run", self.trigger_run, methods=["POST"])
        router.add_api_route("/interests/{interest_id}/runs", self.list_runs, methods=["GET"])
        router.add_api_route("/runs/{run_id}/themes", self.get_themes, methods=["GET"])
        router.add_api_route("/runs/{run_id}/brief", self.get_brief, methods=["GET"])
        router.add_api_route("/runs/{run_id}/deliverables", self.get_deliverables, methods=["GET"])
        # Scheduler
        router.add_api_route("/interests/{interest_id}/next-run", self.get_next_run, methods=["GET"])
        router.add_api_route("/scheduler/status", self.scheduler_status, methods=["GET"])

    # ---- Interests ----
    async def list_interests(self, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        interests = await store.list_interests(str(user.id))
        return {"interests": interests}

    async def create_interest(self, body: InterestCreate, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        record = await store.create_interest(str(user.id), body.model_dump())
        return {"interest": record}

    async def update_interest(self, interest_id: int, body: InterestUpdate, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        existing = await store.get_interest(str(user.id), interest_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Interest not found")
        updated = await store.update_interest(str(user.id), interest_id, body.model_dump(exclude_none=True))
        return {"interest": updated}

    async def delete_interest(self, interest_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        existing = await store.get_interest(str(user.id), interest_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Interest not found")
        await store.delete_interest(str(user.id), interest_id)
        return {"status": "ok"}

    # ---- Feeds ----
    async def list_feeds(self, interest_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        feeds = await store.list_feeds(str(user.id), interest_id)
        return {"feeds": feeds}

    async def add_feed(self, interest_id: int, body: FeedCreate, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        record = await store.add_feed(str(user.id), interest_id, body.url, body.name, body.category)
        return {"feed": record}

    async def update_feed(self, interest_id: int, feed_id: int, body: FeedUpdate, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        updated = await store.update_feed(str(user.id), interest_id, feed_id, body.model_dump(exclude_none=True))
        if not updated:
            raise HTTPException(status_code=404, detail="Feed not found")
        return {"feed": updated}

    async def delete_feed(self, interest_id: int, feed_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        await store.delete_feed(str(user.id), interest_id, feed_id)
        return {"status": "ok"}

    # ---- Pipeline ----
    async def trigger_run(self, interest_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        interest = await store.get_interest(str(user.id), interest_id)
        if not interest:
            raise HTTPException(status_code=404, detail="Interest not found")

        or_key = await get_user_openrouter_key(user, session)
        if not or_key:
            raise HTTPException(status_code=400, detail="OpenRouter API key not configured — set it in Settings")

        from workbench.services.news_pipeline import NewsPipeline
        pipeline = NewsPipeline(store, session)
        run_id = await pipeline.run(str(user.id), interest, or_key)

        # Save AgentSession
        try:
            title = interest.get("name", f"News Run {run_id}")
            agent_session = AgentSession(
                user_id=user.id,
                agent_name="news",
                session_id=str(run_id),
                title=title,
                state_json={
                    "interest": interest,
                    "run_id": run_id,
                    "pipeline_stage": "completed",
                },
                content=None,
                content_format="markdown",
                metadata_json={
                    "interest_id": interest.get("id"),
                    "interest_name": interest.get("name"),
                    "enable_summary": interest.get("enable_summary"),
                    "enable_script": interest.get("enable_script"),
                    "enable_brief": interest.get("enable_brief"),
                    "interval_hours": interest.get("interval_hours"),
                },
            )
            session.add(agent_session)
            await session.commit()
        except Exception:
            logger = __import__("logging").getLogger(__name__)
            logger.exception("Failed to save AgentSession for news run %d", run_id)

        # Send email if configured
        if interest.get("enable_email") and interest.get("email_smtp_host"):
            try:
                from workbench.services.news_emailer import send_pipeline_results
                await send_pipeline_results(
                    run_id=run_id,
                    store=store,
                    interest=interest,
                    smtp_config={
                        "host": interest.get("email_smtp_host", ""),
                        "port": interest.get("email_smtp_port", 587),
                        "user": interest.get("email_smtp_user", ""),
                        "password_env": interest.get("email_smtp_password_env", ""),
                        "sender": interest.get("email_sender", ""),
                        "recipient": interest.get("email_recipient", ""),
                    },
                )
            except Exception as exc:
                logger = __import__("logging").getLogger(__name__)
                logger.warning("Email dispatch failed: %s", exc)

        return {"run_id": run_id, "status": "started"}

    async def list_runs(self, interest_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        runs = await store.list_runs(str(user.id), interest_id)
        return {"runs": runs}

    async def get_themes(self, run_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        run = await store.get_run_for_user(str(user.id), run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        themes = await store.get_themes_for_run(run_id)
        return {"themes": themes}

    async def get_brief(self, run_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        run = await store.get_run_for_user(str(user.id), run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        brief = await store.get_daily_brief_for_run(run_id)
        return {"brief": brief}

    async def get_deliverables(self, run_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        run = await store.get_run_for_user(str(user.id), run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        themes = await store.get_themes_for_run(run_id)
        result = []
        for theme in themes:
            dels = await store.get_deliverables_for_theme(theme.get("id", 0))
            result.append({
                "theme_id": theme.get("id"),
                "theme_title": theme.get("title"),
                "deliverables": dels,
            })
        return {"deliverables": result}

    # ---- Scheduler ----
    async def get_next_run(self, interest_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from workbench.services.news_scheduler import _compute_next_run_seconds
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        interest = await store.get_interest(str(user.id), interest_id)
        if not interest:
            raise HTTPException(status_code=404, detail="Interest not found")

        now = datetime.now(ZoneInfo("Europe/Berlin"))
        seconds = _compute_next_run_seconds(
            interest.get("start_time", "04:00"),
            interest.get("interval_hours", 24),
            now,
        )
        next_at = now.timestamp() + seconds
        return {
            "next_run_seconds": seconds,
            "next_run_iso": datetime.fromtimestamp(next_at, tz=ZoneInfo("Europe/Berlin")).isoformat(),
        }

    async def scheduler_status(self, user: User = Depends(get_current_user)):
        sched = _news_scheduler
        return {
            "running": bool(sched) and sched._started,
        }

    def get_frontend_tab(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "icon": self.icon,
            "component": f"agent-{self.name}",
            "js": f"/static/js/components/{self.name}-tab.js",
        }


class InterestCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    start_time: str = "04:00"
    interval_hours: int = Field(default=24, ge=1, le=168)
    target_summary_words: int = Field(default=750, ge=50)
    target_script_words: int = Field(default=1250, ge=50)
    target_script_de_words: int = Field(default=1250, ge=50)
    target_brief_words: int = Field(default=600, ge=50)
    enable_summary: bool = True
    enable_script: bool = True
    enable_script_de: bool = False
    enable_brief: bool = True
    enable_email: bool = False
    input_data_length_mode: str = "full_article"
    input_word_count: int = Field(default=256, ge=1)
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_smtp_user: str = ""
    email_sender: str = ""
    email_recipient: str = ""


class InterestUpdate(BaseModel):
    name: str | None = None
    start_time: str | None = None
    interval_hours: int | None = None
    target_summary_words: int | None = None
    target_script_words: int | None = None
    target_script_de_words: int | None = None
    target_brief_words: int | None = None
    enable_summary: bool | None = None
    enable_script: bool | None = None
    enable_script_de: bool | None = None
    enable_brief: bool | None = None
    enable_email: bool | None = None
    input_data_length_mode: str | None = None
    input_word_count: int | None = None
    email_smtp_host: str | None = None
    email_smtp_port: int | None = None
    email_smtp_user: str | None = None
    email_sender: str | None = None
    email_recipient: str | None = None


class FeedCreate(BaseModel):
    name: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    category: str = "news"


class FeedUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    category: str | None = None
