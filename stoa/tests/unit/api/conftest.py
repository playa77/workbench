import pytest
from fastapi.testclient import TestClient

from caw.api.app import create_app
from caw.api.deps import AppServices
from caw.core.approvals import ApprovalManager
from caw.core.config import CAWConfig
from caw.core.engine import Engine
from caw.core.permissions import PermissionGate
from caw.core.router import Router
from caw.core.session import SessionManager
from caw.protocols.mock import MockProvider
from caw.protocols.registry import ProviderRegistry
from caw.skills.registry import SkillRegistry
from caw.storage.approvals import ApprovalRepository
from caw.storage.database import Database
from caw.storage.repository import MessageRepository, SessionRepository, TraceEventRepository
from caw.traces.collector import TraceCollector
from caw.traces.replay import ReplayEngine


async def build_test_services() -> AppServices:
    config = CAWConfig.model_validate(
        {
            "providers": {
                "primary": {
                    "type": "openai",
                    "api_key_env": "OPENAI_API_KEY",
                    "default_model": "gpt-4o-mini",
                }
            },
            "skills": {"builtin_dir": "missing", "user_dir": "missing", "packs_dir": "missing"},
            "storage": {"db_path": ":memory:"},
        }
    )
    db = Database(config.storage)
    await db.connect()
    await db.run_migrations()

    trace_repo = TraceEventRepository(db)
    collector = TraceCollector(trace_repo, flush_threshold=1)
    await collector.start()

    provider_registry = ProviderRegistry(config)
    provider_registry._providers["primary"] = MockProvider(
        provider_id="primary", response_text="Mock"
    )

    session_manager = SessionManager(SessionRepository(db), MessageRepository(db))
    message_repository = MessageRepository(db)
    skill_registry = SkillRegistry(config.skills)

    permission_gate = PermissionGate(config.workspace, collector)

    engine = Engine(
        config=config,
        session_manager=session_manager,
        router=Router(config, provider_registry),
        permission_gate=permission_gate,
        skill_registry=skill_registry,
        trace_collector=collector,
        provider_registry=provider_registry,
        message_repo=message_repository,
    )

    return AppServices(
        config=config,
        database=db,
        session_manager=session_manager,
        message_repository=message_repository,
        trace_collector=collector,
        replay_engine=ReplayEngine(collector),
        provider_registry=provider_registry,
        skill_registry=skill_registry,
        engine=engine,
        permission_gate=permission_gate,
        approval_manager=ApprovalManager(ApprovalRepository(db), collector),
    )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def fake_build_services(config: CAWConfig | None = None) -> AppServices:
        del config
        return await build_test_services()

    async def fake_shutdown(built: AppServices) -> None:
        await built.trace_collector.stop()
        await built.database.close()

    monkeypatch.setattr("caw.api.app.build_services", fake_build_services)
    monkeypatch.setattr("caw.api.app.shutdown_services", fake_shutdown)

    app = create_app(CAWConfig())
    with TestClient(app) as test_client:
        yield test_client
