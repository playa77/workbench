"""Workbench FastAPI application factory."""

from __future__ import annotations

import importlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from workbench.core.config import WorkbenchConfig, load_config
from workbench.core.db import close_db, init_db
from workbench.core.encryption import init_encryption
from workbench.core.plugins import get_registry

logger = logging.getLogger(__name__)

_BUILTIN_AGENTS = [
    ("agents.chat.agent", "ChatAgent"),
    ("agents.news.agent", "NewsAgent"),
    ("agents.debate.agent", "DebateAgent"),
    ("agents.research.agent", "ResearchAgent"),
    ("agents.deliberation.agent", "DeliberationAgent"),
    ("agents.planning.agent", "PlanningAgent"),
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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("Workbench %s starting — host=%s port=%s", "0.1.0", config.api_host, config.api_port)
        from workbench.core.db import _engine
        from workbench.core.models import Base
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified/created")
        yield
        logger.info("Workbench shutting down")
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

    app.state.config = config

    static_dir = Path(__file__).resolve().parent.parent / "webui" / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    _register_core_routes(app)

    return app


def _register_core_routes(app: FastAPI) -> None:
    from workbench.api.routes import auth, health
    from workbench.api.routes import config as config_routes
    from workbench.api.routes import plugins as agent_routes

    app.include_router(health.router, tags=["core"])
    app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
    app.include_router(config_routes.router, prefix="/api/v1", tags=["config"])
    app.include_router(agent_routes.router, prefix="/api/v1", tags=["agents"])

    _auto_register_agents(app, get_registry())

    plugin_registry = get_registry()
    plugin_registry.mount_all(app)


def _auto_register_agents(app: FastAPI, registry) -> None:
    """Auto-discover and register built-in agents with lazy importing.

    Agents are imported on first request, not at startup, to reduce memory
    when multiple browser tabs are open. The registry stores agent instances.
    """

    for module_path, class_name in _BUILTIN_AGENTS:
        try:
            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            registry.register(cls())
            logger.info("Registered agent: %s", class_name)
        except Exception as exc:
            logger.debug("Agent %s not available: %s", class_name, exc)

    static_dir = Path(__file__).resolve().parent.parent / "webui" / "static"
    index_html = static_dir / "index.html"

    @app.get("/")
    async def root():
        if index_html.exists():
            return FileResponse(str(index_html))
        return HTMLResponse("<h1>Workbench API</h1><p>Frontend not found.</p>")

    @app.get("/api/v1/tabs")
    async def list_tabs():
        return {"tabs": get_registry().get_tabs()}
