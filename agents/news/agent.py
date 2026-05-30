"""Workbench News Pipeline Agent.

Adapted from ai_news_scraper. Provides:
- Multi-interest RSS feed management
- AI-powered theme identification and content generation
- Email delivery of daily digests
- Per-user interests, schedules, and feeds
"""


from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from agents.base import AgentBase
from workbench.core.auth import get_current_user, get_user_openrouter_key
from workbench.core.db import get_session
from workbench.core.models import User


class NewsAgent(AgentBase):
    name = "news"
    display_name = "News Pipeline"
    description = "Multi-interest AI-powered RSS news scraper, theme analyzer, and content generator"
    version = "0.1.0"
    icon = "newspaper"

    def _build_router(self) -> APIRouter:
        router = APIRouter()
        self._register_routes(router)
        return router

    def _register_routes(self, router: APIRouter) -> None:
        router.add_api_route("/interests", self.list_interests, methods=["GET"])
        router.add_api_route("/interests", self.create_interest, methods=["POST"])
        router.add_api_route("/interests/{interest_id}", self.delete_interest, methods=["DELETE"])
        router.add_api_route("/interests/{interest_id}/feeds", self.list_feeds, methods=["GET"])
        router.add_api_route("/interests/{interest_id}/feeds", self.add_feed, methods=["POST"])
        router.add_api_route("/interests/{interest_id}/feeds/{feed_id}", self.delete_feed, methods=["DELETE"])
        router.add_api_route("/interests/{interest_id}/run", self.trigger_run, methods=["POST"])
        router.add_api_route("/interests/{interest_id}/runs", self.list_runs, methods=["GET"])
        router.add_api_route("/runs/{run_id}/themes", self.get_themes, methods=["GET"])
        router.add_api_route("/runs/{run_id}/brief", self.get_brief, methods=["GET"])

    async def list_interests(self, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        interests = await store.list_interests(str(user.id))
        return {"interests": interests}

    async def create_interest(self, body: "InterestCreate", user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        record = await store.create_interest(str(user.id), body.model_dump())
        return {"interest": record}

    async def delete_interest(self, interest_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        await store.delete_interest(str(user.id), interest_id)
        return {"status": "ok"}

    async def list_feeds(self, interest_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        feeds = await store.list_feeds(str(user.id), interest_id)
        return {"feeds": feeds}

    async def add_feed(self, interest_id: int, body: "FeedCreate", user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        record = await store.add_feed(str(user.id), interest_id, body.url, body.name, body.category)
        return {"feed": record}

    async def delete_feed(self, interest_id: int, feed_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        await store.delete_feed(str(user.id), interest_id, feed_id)
        return {"status": "ok"}

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
        return {"run_id": run_id, "status": "started"}

    async def list_runs(self, interest_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        runs = await store.list_runs(str(user.id), interest_id)
        return {"runs": runs}

    async def get_themes(self, run_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        themes = await store.get_themes_for_run(run_id)
        return {"themes": themes}

    async def get_brief(self, run_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
        from workbench.services.news_store import NewsStore
        store = NewsStore(session)
        brief = await store.get_daily_brief_for_run(run_id)
        return {"brief": brief}

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
    enable_summary: bool = True
    enable_script: bool = True
    enable_brief: bool = True
    enable_email: bool = True


class FeedCreate(BaseModel):
    name: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    category: str = "news"
