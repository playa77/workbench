from datetime import UTC, datetime

import pytest

from caw.core.session import SessionManager
from caw.errors import ValidationError_
from caw.models import Message, SessionMode, SessionState
from caw.storage.database import Database
from caw.storage.repository import MessageRepository, SessionRepository


@pytest.mark.asyncio
async def test_create_session(db: Database) -> None:
    manager = SessionManager(SessionRepository(db), MessageRepository(db))
    session = await manager.create(mode=SessionMode.CHAT, skills=["s1"], skill_pack="pack")
    assert session.id
    assert session.state is SessionState.CREATED
    assert session.active_skills == ["s1"]


@pytest.mark.asyncio
async def test_valid_transitions(db: Database) -> None:
    manager = SessionManager(SessionRepository(db), MessageRepository(db))
    session = await manager.create(mode=SessionMode.CHAT)

    session = await manager.transition(session.id, SessionState.ACTIVE)
    assert session.state is SessionState.ACTIVE

    session = await manager.transition(session.id, SessionState.PAUSED)
    assert session.state is SessionState.PAUSED

    session = await manager.transition(session.id, SessionState.ACTIVE)
    assert session.state is SessionState.ACTIVE

    session = await manager.transition(session.id, SessionState.CHECKPOINTED)
    assert session.state is SessionState.CHECKPOINTED

    session = await manager.transition(session.id, SessionState.ACTIVE)
    session = await manager.transition(session.id, SessionState.COMPLETED)
    assert session.state is SessionState.COMPLETED


@pytest.mark.asyncio
async def test_invalid_transition(db: Database) -> None:
    manager = SessionManager(SessionRepository(db), MessageRepository(db))
    session = await manager.create(mode=SessionMode.CHAT)
    active = await manager.transition(session.id, SessionState.ACTIVE)
    done = await manager.transition(active.id, SessionState.COMPLETED)
    with pytest.raises(ValidationError_):
        await manager.transition(done.id, SessionState.ACTIVE)


@pytest.mark.asyncio
async def test_branch_copies_parent_id(db: Database) -> None:
    session_repo = SessionRepository(db)
    message_repo = MessageRepository(db)
    manager = SessionManager(session_repo, message_repo)

    parent = await manager.create(mode=SessionMode.CHAT)
    await message_repo.create(Message(session_id=parent.id, sequence_num=1, content="one"))
    await message_repo.create(Message(session_id=parent.id, sequence_num=2, content="two"))

    child = await manager.branch(parent.id, branch_point=1)
    copied = await message_repo.list_by_session(child.id)

    assert child.parent_id == parent.id
    assert [message.content for message in copied] == ["one", "two"]


@pytest.mark.asyncio
async def test_transition_updates_timestamp(db: Database) -> None:
    manager = SessionManager(SessionRepository(db), MessageRepository(db))
    session = await manager.create(mode=SessionMode.CHAT)
    original = session.updated_at

    updated = await manager.transition(session.id, SessionState.ACTIVE)
    assert updated.updated_at >= original
    assert updated.updated_at <= datetime.now(UTC)
