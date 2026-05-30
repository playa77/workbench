import pytest

from caw.core.config import CAWConfig, StorageConfig
from caw.core.engine import Engine, ExecutionRequest
from caw.core.permissions import PermissionGate
from caw.core.router import Router
from caw.core.session import SessionManager
from caw.models import SessionMode
from caw.protocols.mock import MockProvider
from caw.protocols.registry import ProviderRegistry
from caw.skills.registry import SkillRegistry
from caw.storage.database import Database
from caw.storage.repository import MessageRepository, SessionRepository, TraceEventRepository
from caw.traces.collector import TraceCollector


@pytest.mark.asyncio
async def test_full_chat_roundtrip(tmp_path) -> None:
    storage = StorageConfig(
        db_path=str(tmp_path / "caw.db"),
        trace_dir=str(tmp_path / "traces"),
        artifact_dir=str(tmp_path / "artifacts"),
    )
    database = Database(storage)
    await database.connect()
    await database.run_migrations()

    try:
        config = CAWConfig.model_validate(
            {
                "storage": storage.model_dump(),
                "providers": {
                    "primary": {
                        "type": "openai",
                        "api_key_env": "OPENAI_API_KEY",
                        "default_model": "gpt-4o-mini",
                    }
                },
                "skills": {
                    "builtin_dir": str(tmp_path / "skills" / "builtin"),
                    "user_dir": str(tmp_path / "skills" / "user"),
                    "packs_dir": str(tmp_path / "skills" / "packs"),
                },
            }
        )

        session_repo = SessionRepository(database)
        message_repo = MessageRepository(database)
        trace_repo = TraceEventRepository(database)
        session_manager = SessionManager(session_repo, message_repo)
        collector = TraceCollector(trace_repo, flush_threshold=1)
        providers = ProviderRegistry(config)
        providers._providers["primary"] = MockProvider(
            provider_id="primary", response_text="Integrated mock response."
        )

        engine = Engine(
            config=config,
            session_manager=session_manager,
            router=Router(config, providers),
            permission_gate=PermissionGate(config.workspace, collector),
            skill_registry=SkillRegistry(config.skills),
            trace_collector=collector,
            provider_registry=providers,
            message_repo=message_repo,
        )

        session = await session_manager.create(mode=SessionMode.CHAT)
        result = await engine.execute(
            ExecutionRequest(session_id=session.id, content="Hello integration")
        )

        history = await message_repo.list_by_session(session.id)
        events = await trace_repo.get_by_trace_id(result.trace_id)

        assert result.content == "Integrated mock response."
        assert len(history) == 2
        assert history[0].content == "Hello integration"
        assert history[1].content == "Integrated mock response."
        assert {event.event_type for event in events} >= {
            "skill:resolved",
            "routing:decision",
            "provider:request",
            "provider:response",
        }
    finally:
        await database.close()
