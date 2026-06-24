"""Tests for workbench.api.routes.reports."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from workbench.api.routes.reports import router as reports_router
from workbench.core.auth import get_current_user
from workbench.core.db import get_session
from workbench.core.models import Base, StoredReport, User as UserModel


@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite database with all tables for report tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


def _make_app(db_session, user):
    """Build a FastAPI app with the reports router and dependency overrides."""
    app = FastAPI()
    app.include_router(reports_router, prefix="/api/v1")

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
async def test_list_reports_empty(db_session):
    """No reports exist — returns []."""
    user = _make_mock_user()
    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.get("/api/v1/reports")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_reports_with_data(db_session):
    """Insert two reports owned by the user — list returns both."""
    user = _make_mock_user()
    now = datetime.now(timezone.utc)

    r1 = StoredReport(
        id=uuid4(), user_id=user.id, agent_name="agent1",
        title="Report 1", content="Hello world",
        content_format="markdown", metadata_json={}, created_at=now,
    )
    r2 = StoredReport(
        id=uuid4(), user_id=user.id, agent_name="agent2",
        title="Report 2", content="Foo bar baz",
        content_format="markdown", metadata_json={}, created_at=now,
    )
    db_session.add_all([r1, r2])
    await db_session.commit()

    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.get("/api/v1/reports")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {d["title"] for d in data} == {"Report 1", "Report 2"}


@pytest.mark.asyncio
async def test_get_report_found(db_session):
    """GET a report by UUID returns decrypted ReportDetail."""
    user = _make_mock_user()
    now = datetime.now(timezone.utc)
    report_id = uuid4()

    r = StoredReport(
        id=report_id, user_id=user.id, agent_name="agent1",
        title="My Report", content="Detailed report content",
        content_format="markdown", metadata_json={"key": "value"},
        created_at=now,
    )
    db_session.add(r)
    await db_session.commit()

    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.get(f"/api/v1/reports/{report_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(report_id)
    assert data["title"] == "My Report"
    assert data["content"] == "Detailed report content"
    assert data["content_format"] == "markdown"
    assert data["metadata"] == {"key": "value"}


@pytest.mark.asyncio
async def test_get_report_not_found(db_session):
    """GET a non-existent UUID returns 404."""
    user = _make_mock_user()
    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.get(f"/api/v1/reports/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_report_wrong_user(db_session):
    """Report owned by user A is invisible to user B (404)."""
    user_a = _make_mock_user()
    user_b = _make_mock_user()
    now = datetime.now(timezone.utc)
    report_id = uuid4()

    r = StoredReport(
        id=report_id, user_id=user_a.id, agent_name="agent1",
        title="User A Report", content="secret",
        content_format="text", metadata_json={}, created_at=now,
    )
    db_session.add(r)
    await db_session.commit()

    app = _make_app(db_session, user_b)
    client = TestClient(app)

    response = client.get(f"/api/v1/reports/{report_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_report(db_session):
    """DELETE removes the report, subsequent GET returns 404."""
    user = _make_mock_user()
    now = datetime.now(timezone.utc)
    report_id = uuid4()

    r = StoredReport(
        id=report_id, user_id=user.id, agent_name="agent1",
        title="To Delete", content="gone",
        content_format="text", metadata_json={}, created_at=now,
    )
    db_session.add(r)
    await db_session.commit()

    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.delete(f"/api/v1/reports/{report_id}")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # Verify deletion
    get_resp = client.get(f"/api/v1/reports/{report_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_report_not_found(db_session):
    """DELETE on a non-existent UUID returns 404."""
    user = _make_mock_user()
    app = _make_app(db_session, user)
    client = TestClient(app)

    response = client.delete(f"/api/v1/reports/{uuid4()}")
    assert response.status_code == 404


# ─── Direct handler coverage tests ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_reports_direct_empty(db_session):
    """Directly call list_reports handler for coverage."""
    from workbench.api.routes.reports import list_reports

    user = _make_mock_user()
    result = await list_reports(user, db_session)
    assert result == []


@pytest.mark.asyncio
async def test_list_reports_direct_with_data(db_session):
    """Directly call list_reports with data."""
    from workbench.api.routes.reports import list_reports
    from datetime import datetime, timezone

    user = _make_mock_user()
    now = datetime.now(timezone.utc)
    r = StoredReport(
        id=uuid4(), user_id=user.id, agent_name="agent1",
        title="Report 1", content="Hello world",
        content_format="markdown", metadata_json={}, created_at=now,
    )
    db_session.add(r)
    await db_session.commit()

    result = await list_reports(user, db_session)
    assert len(result) == 1
    assert result[0].title == "Report 1"


@pytest.mark.asyncio
async def test_get_report_direct_found_and_not_found(db_session):
    """Directly call get_report handler for coverage."""
    from workbench.api.routes.reports import get_report
    from datetime import datetime, timezone

    user = _make_mock_user()
    now = datetime.now(timezone.utc)
    report_id = uuid4()
    r = StoredReport(
        id=report_id, user_id=user.id, agent_name="agent1",
        title="My Report", content="Detailed content",
        content_format="markdown", metadata_json={}, created_at=now,
    )
    db_session.add(r)
    await db_session.commit()

    result = await get_report(str(report_id), user, db_session)
    assert result.id == str(report_id)
    assert result.title == "My Report"

    # Not found
    with pytest.raises(Exception):
        await get_report(str(uuid4()), user, db_session)


@pytest.mark.asyncio
async def test_delete_report_direct(db_session):
    """Directly call delete_report handler for coverage."""
    from workbench.api.routes.reports import delete_report
    from datetime import datetime, timezone

    user = _make_mock_user()
    now = datetime.now(timezone.utc)
    report_id = uuid4()
    r = StoredReport(
        id=report_id, user_id=user.id, agent_name="agent1",
        title="To Delete", content="gone",
        content_format="text", metadata_json={}, created_at=now,
    )
    db_session.add(r)
    await db_session.commit()

    result = await delete_report(str(report_id), user, db_session)
    assert result == {"status": "ok"}

    # Already deleted - not found
    with pytest.raises(Exception):
        await delete_report(str(report_id), user, db_session)
