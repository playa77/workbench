"""FastAPI dependency providers for shared CAW services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from caw.core.approvals import ApprovalManager
from caw.core.config import CAWConfig, load_config
from caw.core.engine import Engine
from caw.core.permissions import PermissionGate
from caw.core.router import Router
from caw.core.session import SessionManager
from caw.protocols.registry import ProviderRegistry
from caw.skills.registry import SkillRegistry
from caw.storage.database import Database
from caw.storage.approvals import ApprovalRepository
from caw.storage.repository import MessageRepository, SessionRepository, TraceEventRepository
from caw.traces.collector import TraceCollector
from caw.traces.replay import ReplayEngine

@dataclass(slots=True)
class AppServices:
    """Container for long-lived application service singletons."""

    config: CAWConfig
    database: Database
    session_manager: SessionManager
    message_repository: MessageRepository
    trace_collector: TraceCollector
    replay_engine: ReplayEngine
    provider_registry: ProviderRegistry
    skill_registry: SkillRegistry
    engine: Engine
    permission_gate: PermissionGate
    approval_manager: ApprovalManager


async def build_services(config: CAWConfig | None = None) -> AppServices:
    """Build and initialize all service objects needed by the API."""
    resolved_config = config or load_config()

    database = Database(resolved_config.storage)
    await database.connect()
    await database.run_migrations()

    session_repo = SessionRepository(database)
    message_repo = MessageRepository(database)
    trace_repo = TraceEventRepository(database)

    trace_collector = TraceCollector(trace_repo, flush_threshold=1)
    await trace_collector.start()

    provider_registry = ProviderRegistry(resolved_config)

    skill_registry = SkillRegistry(resolved_config.skills)
    skill_registry.load()

    session_manager = SessionManager(session_repo, message_repo)
    permission_gate = PermissionGate(resolved_config.workspace, trace_collector)
    approval_manager = ApprovalManager(ApprovalRepository(database), trace_collector)

    engine = Engine(
        config=resolved_config,
        session_manager=session_manager,
        router=Router(resolved_config, provider_registry),
        permission_gate=permission_gate,
        skill_registry=skill_registry,
        trace_collector=trace_collector,
        provider_registry=provider_registry,
        message_repo=message_repo,
    )

    replay_engine = ReplayEngine(trace_collector)

    return AppServices(
        config=resolved_config,
        database=database,
        session_manager=session_manager,
        message_repository=message_repo,
        trace_collector=trace_collector,
        replay_engine=replay_engine,
        provider_registry=provider_registry,
        skill_registry=skill_registry,
        engine=engine,
        permission_gate=permission_gate,
        approval_manager=approval_manager,
    )


async def shutdown_services(services: AppServices) -> None:
    """Flush and close all stateful services during app shutdown."""
    await services.trace_collector.stop()
    await services.database.close()


def get_services(request: Request) -> AppServices:
    """Return app services stored on the ASGI app state container."""
    return request.app.state.services


async def get_config(request: Request) -> CAWConfig:
    """Resolve active app configuration for route handlers."""
    return get_services(request).config


async def get_engine(request: Request) -> Engine:
    """Resolve orchestration engine instance for route handlers."""
    return get_services(request).engine


async def get_session_manager(request: Request) -> SessionManager:
    """Resolve session manager instance for route handlers."""
    return get_services(request).session_manager


async def get_message_repository(request: Request) -> MessageRepository:
    """Resolve message repository instance for route handlers."""
    return get_services(request).message_repository


async def get_trace_collector(request: Request) -> TraceCollector:
    """Resolve trace collector instance for route handlers."""
    return get_services(request).trace_collector


async def get_replay_engine(request: Request) -> ReplayEngine:
    """Resolve replay engine instance for trace summary endpoints."""
    return get_services(request).replay_engine


async def get_provider_registry(request: Request) -> ProviderRegistry:
    """Resolve provider registry instance for provider endpoints."""
    return get_services(request).provider_registry


async def get_skill_registry(request: Request) -> SkillRegistry:
    """Resolve skill registry instance for skill endpoints."""
    return get_services(request).skill_registry


def redact_config_for_display(config: CAWConfig) -> dict[str, object]:
    """Return config dict with potentially sensitive values redacted."""
    redacted = config.model_dump(mode="python")

    providers = redacted.get("providers")
    if isinstance(providers, dict):
        for provider in providers.values():
            if isinstance(provider, dict):
                api_env = provider.get("api_key_env")
                if isinstance(api_env, str) and api_env:
                    provider["api_key_env"] = "***"

    return redacted


def ensure_data_dir(config: CAWConfig) -> Path:
    """Create configured data directory if it does not already exist."""
    data_dir = Path(config.general.data_dir).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir
