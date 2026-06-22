"""Tests for workbench.api.routes.sessions."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from workbench.api.routes.sessions import router as sessions_router
from workbench.core.auth import get_current_user
from workbench.core.db import get_session
from workbench.core.models import AgentSession, Base, User as UserModel


@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite database with all tables for session tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def _make_app(db_session, user):
    """Build a FastAPI app with the sessions router and dependency overrides."""
    app = FastAPI()
    app.include_router(sessions_router, prefix="/api/v1")

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_session] = _override_get_session
    return app


def _make_mock_user(user_id=None):
    """Create a mock User with a predictable UUID."""
    if user_id is None:
        user_id = uuid4()
    mock_user = MagicMock(spec=UserModel)
    mock_user.id = user_id
    mock_user.username = "testuser"
    return mock_user


@pytest.mark.asyncio
async def test_list_sessions_empty(db_session):
    """No sessions exist — returns []."""
    user = _make_mock_user()
    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.get("/api/v1/sessions")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_sessions_with_data(db_session):
    """Insert two sessions owned by the user — list returns both."""
    user = _make_mock_user()
    now = datetime.now(timezone.utc)

    s1 = AgentSession(
        id=uuid4(), user_id=user.id, agent_name="agent1", session_id="s1",
        title="Session 1", content="hello world", content_format="text",
        state_json={}, metadata_json={}, created_at=now, updated_at=now,
    )
    s2 = AgentSession(
        id=uuid4(), user_id=user.id, agent_name="agent2", session_id="s2",
        title="Session 2", content="foo bar baz", content_format="text",
        state_json={}, metadata_json={}, created_at=now, updated_at=now,
    )
    db_session.add_all([s1, s2])
    await db_session.commit()

    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.get("/api/v1/sessions")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {d["title"] for d in data} == {"Session 1", "Session 2"}


@pytest.mark.asyncio
async def test_list_sessions_filter_by_agent(db_session):
    """Filter by ?agent=chat returns only matching sessions."""
    user = _make_mock_user()
    now = datetime.now(timezone.utc)

    s_chat = AgentSession(
        id=uuid4(), user_id=user.id, agent_name="chat", session_id="sc1",
        title="Chat Session", content="hi", content_format="text",
        state_json={}, metadata_json={}, created_at=now, updated_at=now,
    )
    s_search = AgentSession(
        id=uuid4(), user_id=user.id, agent_name="search", session_id="ss1",
        title="Search Session", content="result", content_format="text",
        state_json={}, metadata_json={}, created_at=now, updated_at=now,
    )
    db_session.add_all([s_chat, s_search])
    await db_session.commit()

    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.get("/api/v1/sessions?agent=chat")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["agent_name"] == "chat"


@pytest.mark.asyncio
async def test_get_session_found(db_session):
    """GET a session by UUID returns SessionDetail."""
    user = _make_mock_user()
    now = datetime.now(timezone.utc)
    session_id = uuid4()

    s = AgentSession(
        id=session_id, user_id=user.id, agent_name="agent1", session_id="s1",
        title="My Session", content="detail content", content_format="markdown",
        state_json={"key": "val"}, metadata_json={"meta": "data"},
        created_at=now, updated_at=now,
    )
    db_session.add(s)
    await db_session.commit()

    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.get(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(session_id)
    assert data["title"] == "My Session"
    assert data["content"] == "detail content"
    assert data["state"] == {"key": "val"}
    assert data["metadata"] == {"meta": "data"}
    assert data["agent_name"] == "agent1"


@pytest.mark.asyncio
async def test_get_session_not_found(db_session):
    """GET a non-existent UUID returns 404."""
    user = _make_mock_user()
    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.get(f"/api/v1/sessions/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_session_wrong_user(db_session):
    """Session owned by user A is invisible to user B (404)."""
    user_a = _make_mock_user()
    user_b = _make_mock_user()
    now = datetime.now(timezone.utc)
    session_id = uuid4()

    s = AgentSession(
        id=session_id, user_id=user_a.id, agent_name="agent1", session_id="s1",
        title="User A Session", content="secret", content_format="text",
        state_json={}, metadata_json={}, created_at=now, updated_at=now,
    )
    db_session.add(s)
    await db_session.commit()

    app = _make_app(db_session, user_b)
    client = TestClient(app)

    response = client.get(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_session(db_session):
    """DELETE removes the session, subsequent GET returns 404."""
    user = _make_mock_user()
    now = datetime.now(timezone.utc)
    session_id = uuid4()

    s = AgentSession(
        id=session_id, user_id=user.id, agent_name="agent1", session_id="s1",
        title="To Delete", content="gone", content_format="text",
        state_json={}, metadata_json={}, created_at=now, updated_at=now,
    )
    db_session.add(s)
    await db_session.commit()

    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.delete(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # Verify deletion
    get_resp = client.get(f"/api/v1/sessions/{session_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_session_not_found(db_session):
    """DELETE on a non-existent UUID returns 404."""
    user = _make_mock_user()
    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.delete(f"/api/v1/sessions/{uuid4()}")
    assert response.status_code == 404


# ─── Direct handler coverage tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_sessions_direct_empty(db_session):
    """Directly call list_sessions handler for coverage."""
    from workbench.api.routes.sessions import list_sessions

    user = _make_mock_user()
    result = await list_sessions(user, db_session, agent=None)
    assert result == []


@pytest.mark.asyncio
async def test_list_sessions_direct_with_data_and_filter(db_session):
    """Directly call list_sessions with filter."""
    from workbench.api.routes.sessions import list_sessions
    from datetime import datetime, timezone

    user = _make_mock_user()
    now = datetime.now(timezone.utc)
    s = AgentSession(
        id=uuid4(), user_id=user.id, agent_name="chat", session_id="s1",
        title="Chat Session", content="hello world", content_format="text",
        state_json={}, metadata_json={}, created_at=now, updated_at=now,
    )
    db_session.add(s)
    await db_session.commit()

    # Without filter
    result = await list_sessions(user, db_session, agent=None)
    assert len(result) == 1

    # With agent filter
    result = await list_sessions(user, db_session, agent="chat")
    assert len(result) == 1

    # Wrong agent filter
    result = await list_sessions(user, db_session, agent="other")
    assert len(result) == 0


@pytest.mark.asyncio
async def test_get_session_detail_direct_found(db_session):
    """Directly call get_session_detail for coverage."""
    from workbench.api.routes.sessions import get_session_detail
    from datetime import datetime, timezone

    user = _make_mock_user()
    now = datetime.now(timezone.utc)
    session_id = uuid4()
    s = AgentSession(
        id=session_id, user_id=user.id, agent_name="agent1", session_id="s1",
        title="My Session", content="detail", content_format="markdown",
        state_json={"key": "val"}, metadata_json={"meta": "data"},
        created_at=now, updated_at=now,
    )
    db_session.add(s)
    await db_session.commit()

    result = await get_session_detail(str(session_id), user, db_session)
    assert result.id == str(session_id)
    assert result.title == "My Session"

    # Not found
    with pytest.raises(Exception):
        await get_session_detail(str(uuid4()), user, db_session)


@pytest.mark.asyncio
async def test_delete_session_direct(db_session):
    """Directly call delete_session handler for coverage."""
    from workbench.api.routes.sessions import delete_session
    from datetime import datetime, timezone

    user = _make_mock_user()
    now = datetime.now(timezone.utc)
    session_id = uuid4()
    s = AgentSession(
        id=session_id, user_id=user.id, agent_name="agent1", session_id="s1",
        title="To Delete", content="gone", content_format="text",
        state_json={}, metadata_json={}, created_at=now, updated_at=now,
    )
    db_session.add(s)
    await db_session.commit()

    result = await delete_session(str(session_id), user, db_session)
    assert result == {"status": "ok"}

    # Already deleted - not found
    with pytest.raises(Exception):
        await delete_session(str(session_id), user, db_session)
