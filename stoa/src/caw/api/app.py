"""FastAPI application factory for the CAW API surface."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from caw.api.deps import AppServices, build_services, shutdown_services
from caw.api.routes.approvals import router as approvals_router
from caw.api.routes.chat import router as chat_router
from caw.api.routes.deliberation import router as deliberation_router
from caw.api.routes.evaluation import router as evaluation_router
from caw.api.routes.research import router as research_router
from caw.api.routes.sessions import router as sessions_router
from caw.api.routes.skills import router as skills_router
from caw.api.routes.traces import router as traces_router
from caw.api.routes.workspace import router as workspace_router
from caw.api.schemas import APIResponse
from caw.api.websocket import handle_session_stream
from caw.errors import (
    CAWError,
    ConfigError,
    ProviderError,
    SkillError,
    StorageError,
    TraceError,
    ValidationError_,
)

if TYPE_CHECKING:
    from caw.core.config import CAWConfig


def _status_for_error(error: CAWError) -> int:
    if isinstance(error, ValidationError_):
        return 400
    if isinstance(error, SkillError):
        return 400
    if isinstance(error, ProviderError):
        return 502
    if isinstance(error, (ConfigError, StorageError, TraceError)):
        return 500
    return 500


def create_app(config: CAWConfig | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        services = await build_services(config)
        app.state.services = services
        try:
            yield
        finally:
            await shutdown_services(services)

    app = FastAPI(title="Canonical Agent Workbench API", version="v1", lifespan=lifespan)

    @app.exception_handler(CAWError)
    async def handle_caw_error(_: Request, exc: CAWError) -> JSONResponse:
        response = APIResponse[object](
            status="error",
            data=None,
            error_code=exc.code,
            message=exc.message,
        )
        return JSONResponse(status_code=_status_for_error(exc), content=response.model_dump())

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        response = APIResponse[object](
            status="error",
            error_code="internal_server_error",
            message=str(exc),
        )
        return JSONResponse(status_code=500, content=response.model_dump())

    origins = config.api.cors_origins if config is not None else ["http://localhost:3000"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health")
    async def health() -> APIResponse[dict[str, str]]:
        return APIResponse(data={"status": "healthy"})

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/docs", status_code=307)

    @app.websocket("/api/v1/sessions/{session_id}/stream")
    async def session_stream(websocket: WebSocket, session_id: str) -> None:
        services: AppServices = app.state.services
        await handle_session_stream(websocket, session_id, services)

    app.include_router(sessions_router)
    app.include_router(chat_router)
    app.include_router(traces_router)
    app.include_router(skills_router)
    app.include_router(research_router)
    app.include_router(deliberation_router)
    app.include_router(workspace_router)
    app.include_router(approvals_router)
    app.include_router(evaluation_router)

    return app
