"""FastAPI application factory and entry point for presearch-web."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from starlette.applications import Starlette
from starlette.routing import WebSocketRoute

from presearch.config import PResearchConfig
from presearch.web import db as report_db
from presearch.web.routes import routes
from presearch.web.session import SessionManager
from presearch.web.ws import ws_endpoint


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    cfg = PResearchConfig()
    app.state.db = await report_db.init_db(cfg.web_db_path)
    app.state.session_manager = SessionManager()
    yield
    await app.state.db.close()


def create_app() -> Starlette:
    """Build the Starlette ASGI application."""
    return Starlette(
        routes=[*routes, WebSocketRoute("/ws", ws_endpoint)],
        lifespan=lifespan,
    )


def main() -> None:
    """Entry point for the ``presearch-web`` console script."""
    import uvicorn
    cfg = PResearchConfig()
    app = create_app()
    uvicorn.run(app, host=cfg.web_host, port=cfg.web_port)


if __name__ == "__main__":
    main()
