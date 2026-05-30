import pytest

from caw.core.config import CAWConfig
from caw.core.engine import Engine, ExecutionRequest
from caw.core.permissions import PermissionGate
from caw.core.router import Router
from caw.core.session import SessionManager
from caw.models import SessionMode, SessionState
from caw.protocols.mock import MockProvider
from caw.protocols.registry import ProviderRegistry
from caw.skills.loader import SkillDocument
from caw.skills.registry import SkillRegistry
from caw.storage.database import Database
from caw.storage.repository import MessageRepository, SessionRepository, TraceEventRepository
from caw.traces.collector import TraceCollector


def _config() -> CAWConfig:
    return CAWConfig.model_validate(
        {
            "providers": {
                "primary": {
                    "type": "openai",
                    "api_key_env": "OPENAI_API_KEY",
                    "default_model": "gpt-4o-mini",
                    "max_tokens": 500,
                }
            },
            "routing": {"strategy": "config", "fallback_chain": []},
            "skills": {"builtin_dir": "missing", "user_dir": "missing", "packs_dir": "missing"},
        }
    )


async def _build_engine(
    db: Database,
) -> tuple[Engine, SessionManager, MessageRepository, TraceEventRepository]:
    config = _config()
    session_repo = SessionRepository(db)
    message_repo = MessageRepository(db)
    trace_repo = TraceEventRepository(db)
    session_manager = SessionManager(session_repo, message_repo)
    collector = TraceCollector(trace_repo, flush_threshold=1)
    registry = ProviderRegistry(config)
    registry._providers["primary"] = MockProvider(
        provider_id="primary",
        response_text="Hello from mock.",
        token_count_in=13,
        token_count_out=21,
    )

    skill_registry = SkillRegistry(config.skills)
    skill_registry._skills = {
        "skill.chat": SkillDocument(
            skill_id="skill.chat",
            version="1.0.0",
            name="Chat Skill",
            description="test",
            author="test",
            provider_preference="primary",
            body="Use concise responses.",
        )
    }

    engine = Engine(
        config=config,
        session_manager=session_manager,
        router=Router(config, registry),
        permission_gate=PermissionGate(config.workspace, collector),
        skill_registry=skill_registry,
        trace_collector=collector,
        provider_registry=registry,
        message_repo=message_repo,
    )
    return engine, session_manager, message_repo, trace_repo


@pytest.mark.asyncio
async def test_execute_chat_basic(db: Database) -> None:
    engine, session_manager, _, _ = await _build_engine(db)
    session = await session_manager.create(mode=SessionMode.CHAT, skills=["skill.chat"])

    result = await engine.execute(ExecutionRequest(session_id=session.id, content="Hello"))

    assert result.session_id == session.id
    assert result.content == "Hello from mock."
    assert result.provider == "primary"


@pytest.mark.asyncio
async def test_execute_stores_messages(db: Database) -> None:
    engine, session_manager, message_repo, _ = await _build_engine(db)
    session = await session_manager.create(mode=SessionMode.CHAT, skills=["skill.chat"])

    await engine.execute(ExecutionRequest(session_id=session.id, content="Ping"))

    messages = await message_repo.list_by_session(session.id)
    assert len(messages) == 2
    assert messages[0].content == "Ping"
    assert messages[1].content == "Hello from mock."


@pytest.mark.asyncio
async def test_execute_activates_session(db: Database) -> None:
    engine, session_manager, _, _ = await _build_engine(db)
    session = await session_manager.create(mode=SessionMode.CHAT)
    assert session.state is SessionState.CREATED

    await engine.execute(ExecutionRequest(session_id=session.id, content="Ping"))
    refreshed = await session_manager.get(session.id)
    assert refreshed.state is SessionState.ACTIVE


@pytest.mark.asyncio
async def test_execute_resolves_skills(db: Database) -> None:
    engine, session_manager, _, trace_repo = await _build_engine(db)
    session = await session_manager.create(mode=SessionMode.CHAT, skills=["skill.chat"])

    result = await engine.execute(ExecutionRequest(session_id=session.id, content="Hello"))
    events = await trace_repo.get_by_trace_id(result.trace_id)

    assert any(event.event_type == "skill:resolved" for event in events)


@pytest.mark.asyncio
async def test_execute_routes_provider(db: Database) -> None:
    engine, session_manager, _, trace_repo = await _build_engine(db)
    session = await session_manager.create(mode=SessionMode.CHAT)

    result = await engine.execute(ExecutionRequest(session_id=session.id, content="Hello"))
    events = await trace_repo.get_by_trace_id(result.trace_id)

    assert any(event.event_type == "routing:decision" for event in events)


@pytest.mark.asyncio
async def test_execute_records_tokens(db: Database) -> None:
    engine, session_manager, _, _ = await _build_engine(db)
    session = await session_manager.create(mode=SessionMode.CHAT)

    result = await engine.execute(ExecutionRequest(session_id=session.id, content="Hello"))

    assert result.tokens_in == 13
    assert result.tokens_out == 21
