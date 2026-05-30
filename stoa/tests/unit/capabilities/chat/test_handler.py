import pytest

from caw.capabilities.chat.handler import ChatHandler
from caw.capabilities.chat.history import ConversationHistory
from caw.core.config import CAWConfig
from caw.core.engine import Engine
from caw.core.permissions import PermissionGate
from caw.core.router import Router
from caw.core.session import SessionManager
from caw.models import Message, MessageRole, SessionMode
from caw.protocols.mock import MockProvider
from caw.protocols.registry import ProviderRegistry
from caw.skills.loader import SkillDocument
from caw.skills.registry import SkillRegistry
from caw.storage.database import Database
from caw.storage.repository import MessageRepository, SessionRepository, TraceEventRepository
from caw.traces.collector import TraceCollector


async def _build_chat_handler(
    db: Database,
) -> tuple[ChatHandler, SessionManager, MessageRepository]:
    config = CAWConfig.model_validate(
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
            "skills": {
                "builtin_dir": "missing",
                "user_dir": "missing",
                "packs_dir": "missing",
            },
        }
    )

    session_repo = SessionRepository(db)
    message_repo = MessageRepository(db)
    trace_repo = TraceEventRepository(db)
    session_manager = SessionManager(session_repo, message_repo)
    collector = TraceCollector(trace_repo, flush_threshold=1)

    provider_registry = ProviderRegistry(config)
    provider_registry._providers["primary"] = MockProvider(
        provider_id="primary",
        response_text="hello from chat",
        token_count_in=5,
        token_count_out=7,
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
            body="Respond helpfully.",
        )
    }

    engine = Engine(
        config=config,
        session_manager=session_manager,
        router=Router(config, provider_registry),
        permission_gate=PermissionGate(config.workspace, collector),
        skill_registry=skill_registry,
        trace_collector=collector,
        provider_registry=provider_registry,
        message_repo=message_repo,
    )
    return ChatHandler(engine), session_manager, message_repo


async def _collect_chunks(handler: ChatHandler, session_id: str, message: str) -> list[object]:
    chunks = []
    async for chunk in handler.handle_message(session_id=session_id, message=message):
        chunks.append(chunk)
    return chunks


@pytest.mark.asyncio
async def test_handle_message_yields_chunks(db: Database) -> None:
    handler, session_manager, _ = await _build_chat_handler(db)
    session = await session_manager.create(mode=SessionMode.CHAT, skills=["skill.chat"])

    chunks = await _collect_chunks(handler, session.id, "hi")

    assert [chunk.type for chunk in chunks] == ["text", "done"]
    assert chunks[0].content == "hello from chat"


@pytest.mark.asyncio
async def test_done_chunk_has_metadata(db: Database) -> None:
    handler, session_manager, _ = await _build_chat_handler(db)
    session = await session_manager.create(mode=SessionMode.CHAT, skills=["skill.chat"])

    chunks = await _collect_chunks(handler, session.id, "hi")
    done_chunk = chunks[-1]

    assert done_chunk.type == "done"
    assert done_chunk.data is not None
    assert done_chunk.data["ok"] is True
    assert done_chunk.data["session_id"] == session.id
    assert isinstance(done_chunk.data["message_id"], str)
    assert done_chunk.data["tokens"] == {"input": 5, "output": 7}


@pytest.mark.asyncio
async def test_collect_response_non_streaming(db: Database) -> None:
    handler, session_manager, _ = await _build_chat_handler(db)
    session = await session_manager.create(mode=SessionMode.CHAT, skills=["skill.chat"])

    text, metadata = await handler.collect_response(session.id, "hello")

    assert text == "hello from chat"
    assert metadata["ok"] is True
    assert isinstance(metadata["message_id"], str)


@pytest.mark.asyncio
async def test_history_builds_context(db: Database) -> None:
    _, session_manager, message_repo = await _build_chat_handler(db)
    session = await session_manager.create(mode=SessionMode.CHAT)

    await message_repo.create(
        Message(session_id=session.id, sequence_num=1, role=MessageRole.USER, content="u1")
    )
    await message_repo.create(
        Message(session_id=session.id, sequence_num=2, role=MessageRole.ASSISTANT, content="a1")
    )
    await message_repo.create(
        Message(session_id=session.id, sequence_num=3, role=MessageRole.USER, content="u2")
    )

    history = ConversationHistory(message_repo)
    context = await history.build_context(session.id, max_messages=2)

    assert [message.role for message in context] == ["assistant", "user"]
    assert [message.content for message in context] == ["a1", "u2"]
