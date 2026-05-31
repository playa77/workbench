"""Workbench FastAPI application factory."""

from __future__ import annotations

import asyncio
import importlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.agents import get_registry, get_user_agent_settings
from workbench.core.auth import get_current_user
from workbench.core.config import WorkbenchConfig, load_config
from workbench.core.db import close_db, get_session, init_db
from workbench.core.encryption import init_encryption
from workbench.core.models import User
from workbench.core.rate_limiter import limiter

logger = logging.getLogger(__name__)

SESSION_CLEANUP_INTERVAL = 300

_BUILTIN_AGENTS = [
    ("agents.chat.agent", "ChatAgent"),
    ("agents.news.agent", "NewsAgent"),
    ("agents.debate.agent", "DebateAgent"),
    ("agents.research.agent", "ResearchAgent"),
    ("agents.deliberation.agent", "DeliberationAgent"),
    ("agents.planning.agent", "PlanningAgent"),
    ("agents.math_tutor.agent", "MathTutorAgent"),
    ("agents.knowledge.agent", "KnowledgeBaseAgent"),
]


def create_app(config: WorkbenchConfig | None = None) -> FastAPI:
    if config is None:
        config = load_config()

    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    init_db(config)
    init_encryption(config)
    from workbench.core.encryption import set_encrypt_reports
    set_encrypt_reports(config.encryption_encrypt_reports)

    # Run migrations before starting the server (not inside lifespan)
    # to avoid nested event loop conflicts with asyncio.run()
    _run_alembic_upgrade()
    logger.info("Database migrations applied")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info(
            "Workbench %s starting — host=%s port=%s",
            "0.1.0", config.api_host, config.api_port,
        )

        # Start the background news scheduler (non-blocking)
        scheduler_task = _start_news_scheduler_if_agent_enabled(app)

        # Start periodic session cleanup
        cleanup_task = asyncio.create_task(_run_periodic_session_cleanup())

        yield

        logger.info("Workbench shutting down")
        if scheduler_task:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except Exception:
                pass
        if cleanup_task:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except Exception:
                pass
        await close_db()

    app = FastAPI(
        title="Workbench",
        description="Unified BYOK AI Workbench — agent-driven infrastructure for LLM-powered tools",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.api_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers_middleware(request, call_next):
        response = await call_next(request)
        if config.api_csp_header:
            response.headers["Content-Security-Policy"] = config.api_csp_header
        if config.api_strict_transport_security:
            response.headers["Strict-Transport-Security"] = config.api_strict_transport_security
        return response

    if config.rate_limit_enabled:
        limiter._default_limits = [config.rate_limit_general]
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.state.config = config

    static_dir = Path(__file__).resolve().parent.parent / "webui" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    _register_core_routes(app)

    return app


def _register_core_routes(app: FastAPI) -> None:
    from workbench.api.routes import agents as agent_routes
    from workbench.api.routes import auth, health
    from workbench.api.routes import config as config_routes

    app.include_router(health.router, tags=["core"])
    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    app.include_router(config_routes.router, prefix="/api/v1", tags=["config"])
    app.include_router(agent_routes.router, prefix="/api/v1", tags=["agents"])

    _auto_register_agents(app, get_registry())

    agent_registry = get_registry()
    agent_registry.mount_all(app)


def _run_alembic_upgrade() -> None:
    from alembic.config import Config as AlembicConfig

    from alembic import command

    # Primary: relative to the source tree (editable installs)
    root = Path(__file__).resolve().parents[3]
    # Fallback: relative to the current working directory (Docker / pip install)
    if not (root / "alembic.ini").exists():
        root = Path.cwd()
    alembic_cfg = AlembicConfig(str(root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(alembic_cfg, "head")


def _auto_register_agents(app: FastAPI, registry) -> None:
    for module_path, class_name in _BUILTIN_AGENTS:
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            registry.register(cls())
            logger.info("Registered agent: %s", class_name)
        except Exception as exc:
            logger.debug("Agent %s not available: %s", class_name, exc)

    for agent in registry.list_all():
        static_dir = agent.get_static_dir()
        if static_dir and static_dir.exists():
            mount_path = f"/static/plugins/{agent.name}"
            app.mount(
                mount_path,
                StaticFiles(directory=str(static_dir)),
                name=f"static-plugin-{agent.name}",
            )
            logger.info(
                "Mounted plugin static dir for '%s': %s -> %s",
                agent.name, static_dir, mount_path,
            )

    static_dir = Path(__file__).resolve().parent.parent / "webui" / "static"
    index_html = static_dir / "index.html"

    @app.get("/")
    async def root():
        if index_html.exists():
            return FileResponse(str(index_html))
        return HTMLResponse("<h1>Workbench API</h1><p>Frontend not found.</p>")

    @app.get("/api/v1/tabs")
    async def list_tabs(
        user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ):
        user_settings = await get_user_agent_settings(str(user.id), session)
        tabs = []
        for agent in get_registry().list_all():
            agent_config = user_settings.get(agent.name, {})
            if agent_config.get("enabled", False):
                tabs.append(agent.get_frontend_tab())
        return {"tabs": tabs}


def _start_news_scheduler_if_agent_enabled(app: FastAPI):
    """Start the background news scheduler if the news agent is registered."""
    try:
        from workbench.core.db import get_session_factory
        from workbench.services.news_scheduler import NewsScheduler
        from workbench.services.news_store import NewsStore

        session_factory = get_session_factory()

        async def get_interests():
            async with session_factory() as sess:
                store = NewsStore(sess)
                return await store.list_all_interests_global()

        async def is_running(interest_id: int) -> bool:
            async with session_factory() as sess:
                store = NewsStore(sess)
                return await store.is_interest_running(interest_id)

        async def run_interest(user_id: str, interest_id: int) -> None:

            from workbench.services.news_pipeline import NewsPipeline

            async with session_factory() as sess:
                store = NewsStore(sess)
                interest = await store.get_interest(user_id, interest_id)
                if not interest:
                    return

                # Get user's OpenRouter key
                from sqlalchemy import select

                from workbench.core import encryption
                from workbench.core.models import UserOpenRouterKey

                result = await sess.execute(
                    select(UserOpenRouterKey).where(
                        UserOpenRouterKey.user_id == user_id
                    )
                )
                or_key_row = result.scalar_one_or_none()
                if not or_key_row:
                    logger.warning(
                        "Skipping scheduled run for interest %d: user %s has no OpenRouter key",
                        interest_id, user_id,
                    )
                    return

                api_key = encryption.decrypt(or_key_row.encrypted_key)
                pipeline = NewsPipeline(store, sess)
                await pipeline.run(user_id, interest, api_key)

        scheduler = NewsScheduler(
            get_interests=get_interests,
            is_running=is_running,
            run_interest=run_interest,
            timezone="Europe/Berlin",
        )

        task = asyncio.create_task(scheduler.start())

        # Store scheduler reference for agent endpoints
        try:
            from agents.news.agent import set_scheduler
            set_scheduler(scheduler)
        except Exception:
            pass

        logger.info("News scheduler started in background")
        return task
    except Exception as exc:
        logger.debug("News scheduler not started: %s", exc)
        return None


async def _run_periodic_session_cleanup() -> None:
    """Periodically call _cleanup_sessions on all registered agents."""
    while True:
        try:
            await asyncio.sleep(SESSION_CLEANUP_INTERVAL)
            registry = get_registry()
            for agent in registry.list_all():
                if hasattr(agent, "_cleanup_sessions"):
                    agent._cleanup_sessions()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Session cleanup failed")
