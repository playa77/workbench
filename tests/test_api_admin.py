"""Tests for workbench.api.routes.admin."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import select

from uuid import UUID, uuid4

from workbench.api.routes.admin import (
    InviteResponse,
    create_invite,
    list_invites,
    revoke_invite,
    router,
    _require_admin,
)
from workbench.core.auth import generate_token, get_current_user
from workbench.core.db import get_session as get_db_session
from workbench.core.models import User, UserInvite


@pytest.fixture
def admin_user():
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.is_admin = True
    return user


@pytest.fixture
def non_admin_user():
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.is_admin = False
    return user


@pytest.fixture
def test_config():
    """Minimal config object so request.app.state.config works."""
    config = MagicMock()
    config.smtp_host = ""
    config.smtp_port = 587
    config.smtp_user = None
    config.smtp_password = None
    config.smtp_from_address = "noreply@workbench.local"
    config.smtp_use_tls = True
    return config


@pytest.fixture
def override_get_session(db_session):
    async def _override():
        yield db_session
    return _override


@pytest.fixture
def admin_client(admin_user, override_get_session, test_config):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db_session] = override_get_session
    app.state.config = test_config
    return TestClient(app)


@pytest.fixture
def non_admin_client(non_admin_user, override_get_session, test_config):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: non_admin_user
    app.dependency_overrides[get_db_session] = override_get_session
    app.state.config = test_config
    return TestClient(app)


# ─── create_invite ───────────────────────────────────────────────────────────


@patch("workbench.api.routes.admin.send_invite_email", new_callable=AsyncMock)
def test_create_invite_non_admin(mock_send_email, non_admin_client):
    """Non-admin user gets 403 when creating an invite."""
    response = non_admin_client.post(
        "/admin/invites",
        json={"email": "newuser@example.com", "username": "newuser"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"
    mock_send_email.assert_not_called()


@patch("workbench.api.routes.admin.send_invite_email", new_callable=AsyncMock)
def test_create_invite_admin(mock_send_email, admin_client):
    """Admin user can create an invite successfully."""
    response = admin_client.post(
        "/admin/invites",
        json={"email": "newuser@example.com", "username": "newuser"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["username"] == "newuser"
    assert data["is_revoked"] is False
    assert data["accepted_at"] is None
    assert UUID(data["id"])
    mock_send_email.assert_called_once()


@patch("workbench.api.routes.admin.send_invite_email", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_create_invite_existing_user(
    mock_send_email, admin_client, override_get_session, db_session,
):
    """Creating an invite for an existing username/email returns 400."""
    # Pre-create a user with this email
    user = User(id=uuid4(), username="existing_user", email="used@example.com")
    async with db_session as session:
        session.add(user)
        await session.commit()

    response = admin_client.post(
        "/admin/invites",
        json={"email": "used@example.com", "username": "newuser"},
    )
    assert response.status_code == 400
    assert "already in use" in response.json()["detail"]
    mock_send_email.assert_not_called()


@patch("workbench.api.routes.admin.send_invite_email", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_create_invite_duplicate_invite(
    mock_send_email, admin_client, override_get_session, db_session,
):
    """Creating an invite when an active invite exists for the email returns 400."""
    from datetime import UTC, datetime, timedelta

    token_raw, token_hash = generate_token()
    invite = UserInvite(
        email="dup@example.com",
        username="dupuser",
        token_hash=token_hash,
        invited_by=uuid4(),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    async with db_session as session:
        session.add(invite)
        await session.commit()

    response = admin_client.post(
        "/admin/invites",
        json={"email": "dup@example.com", "username": "anotheruser"},
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]
    mock_send_email.assert_not_called()


# ─── list_invites ────────────────────────────────────────────────────────────


@patch("workbench.api.routes.admin.send_invite_email", new_callable=AsyncMock)
def test_list_invites_non_admin(mock_send_email, non_admin_client):
    """Non-admin user gets 403 when listing invites."""
    response = non_admin_client.get("/admin/invites")
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


@patch("workbench.api.routes.admin.send_invite_email", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_list_invites_admin(mock_send_email, admin_client, override_get_session, db_session):
    """Admin user can list invites."""
    from datetime import UTC, datetime, timedelta

    # Create a couple of invites directly
    token_raw1, token_hash1 = generate_token()
    token_raw2, token_hash2 = generate_token()
    now = datetime.now(UTC).replace(tzinfo=None)
    invites = [
        UserInvite(
            email="alice@example.com", username="alice",
            token_hash=token_hash1, invited_by=uuid4(),
            expires_at=now + timedelta(days=7),
        ),
        UserInvite(
            email="bob@example.com", username="bob",
            token_hash=token_hash2, invited_by=uuid4(),
            expires_at=now + timedelta(days=7),
        ),
    ]
    async with db_session as session:
        session.add_all(invites)
        await session.commit()

    response = admin_client.get("/admin/invites")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 2
    emails = {i["email"] for i in data}
    assert "alice@example.com" in emails
    assert "bob@example.com" in emails


# ─── revoke_invite ───────────────────────────────────────────────────────────


@patch("workbench.api.routes.admin.send_invite_email", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_revoke_invite(mock_send_email, admin_client, override_get_session, db_session):
    """Admin can revoke an active invite."""
    from datetime import UTC, datetime, timedelta

    token_raw, token_hash = generate_token()
    invite = UserInvite(
        email="revoke_me@example.com", username="revokeme",
        token_hash=token_hash, invited_by=uuid4(),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    async with db_session as session:
        session.add(invite)
        await session.commit()
        invite_id = str(invite.id)

    response = admin_client.delete(f"/admin/invites/{invite_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # Verify it's revoked in DB
    async with db_session as session:
        result = await session.execute(
            select(UserInvite).where(UserInvite.id == UUID(invite_id))
        )
        revoked = result.scalar_one_or_none()
        assert revoked is not None
        assert revoked.is_revoked is True


@patch("workbench.api.routes.admin.send_invite_email", new_callable=AsyncMock)
def test_revoke_invite_not_found(mock_send_email, admin_client):
    """Revoking a nonexistent invite returns 404."""
    fake_id = uuid4()
    response = admin_client.delete(f"/admin/invites/{fake_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "Invite not found"


@patch("workbench.api.routes.admin.send_invite_email", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_revoke_invite_already_accepted(
    mock_send_email, admin_client, override_get_session, db_session,
):
    """Revoking an already accepted invite returns 400."""
    from datetime import UTC, datetime, timedelta

    token_raw, token_hash = generate_token()
    now = datetime.now(UTC).replace(tzinfo=None)
    invite = UserInvite(
        email="accepted@example.com", username="accepted",
        token_hash=token_hash, invited_by=uuid4(),
        expires_at=now + timedelta(days=7),
        accepted_at=now,
    )
    async with db_session as session:
        session.add(invite)
        await session.commit()
        invite_id = str(invite.id)

    response = admin_client.delete(f"/admin/invites/{invite_id}")
    assert response.status_code == 400
    assert response.json()["detail"] == "Invite already accepted"


# ─── Direct handler coverage tests ──────────────────────────────────────────
# These call the handler functions directly to ensure coverage is tracked
# through the slowapi wrapper that TestClient can't always trace.


@pytest.mark.asyncio
async def test_list_invites_direct(db_session, admin_user):
    """Directly call list_invites handler for coverage."""
    from datetime import UTC, datetime, timedelta

    token_raw, token_hash = generate_token()
    now = datetime.now(UTC).replace(tzinfo=None)
    invite = UserInvite(
        email="direct_list@test.com", username="directlist",
        token_hash=token_hash, invited_by=uuid4(),
        expires_at=now + timedelta(days=7),
    )
    db_session.add(invite)
    await db_session.commit()

    result = await list_invites(admin_user, db_session)
    assert isinstance(result, list)
    emails = {i.email for i in result}
    assert "direct_list@test.com" in emails


@pytest.mark.asyncio
async def test_revoke_invite_not_found_direct(db_session, admin_user):
    """Directly call revoke_invite for not-found coverage."""
    from uuid import UUID

    fake_id = str(uuid4())
    with pytest.raises(Exception):
        await revoke_invite(fake_id, admin_user, db_session)


@pytest.mark.asyncio
async def test_revoke_invite_already_accepted_direct(db_session, admin_user):
    """Directly call revoke_invite for already-accepted coverage."""
    from datetime import UTC, datetime, timedelta
    from uuid import UUID

    token_raw, token_hash = generate_token()
    now = datetime.now(UTC).replace(tzinfo=None)
    invite = UserInvite(
        email="direct_accepted@test.com", username="directaccepted",
        token_hash=token_hash, invited_by=uuid4(),
        expires_at=now + timedelta(days=7),
        accepted_at=now,
    )
    db_session.add(invite)
    await db_session.commit()
    invite_id = str(invite.id)

    with pytest.raises(Exception):
        await revoke_invite(invite_id, admin_user, db_session)


@pytest.mark.asyncio
async def test_create_invite_direct(
    db_session, admin_user, override_get_session, test_config,
):
    """Directly call create_invite handler for coverage of lines 58-89."""
    from workbench.api.routes.admin import CreateInviteRequest

    body = CreateInviteRequest(email="direct_invite@test.com", username="directuser")
    request = MagicMock(spec=Request)
    request.app.state.config = test_config
    request.base_url = "http://testserver/"

    with patch("workbench.api.routes.admin.send_invite_email", new_callable=AsyncMock):
        result = await create_invite(body, request, admin_user, db_session)
        assert isinstance(result, InviteResponse)
        assert result.email == "direct_invite@test.com"
        assert result.username == "directuser"


@pytest.mark.asyncio
async def test_revoke_invite_success_direct(db_session, admin_user):
    """Directly call revoke_invite for success coverage."""
    from datetime import UTC, datetime, timedelta

    token_raw, token_hash = generate_token()
    now = datetime.now(UTC).replace(tzinfo=None)
    invite = UserInvite(
        email="direct_revoke@test.com", username="directrevoke",
        token_hash=token_hash, invited_by=uuid4(),
        expires_at=now + timedelta(days=7),
    )
    db_session.add(invite)
    await db_session.commit()
    invite_id = str(invite.id)

    result = await revoke_invite(invite_id, admin_user, db_session)
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_create_invite_existing_user_direct(
    db_session, admin_user, test_config,
):
    """Directly call create_invite with existing username/email (line 59)."""
    from workbench.api.routes.admin import CreateInviteRequest
    from workbench.core.models import User

    # Create a user with the same email
    user = User(id=uuid4(), username="existing_user", email="existing@test.com")
    db_session.add(user)
    await db_session.commit()

    body = CreateInviteRequest(email="existing@test.com", username="newuser")
    request = MagicMock(spec=Request)
    request.app.state.config = test_config
    request.base_url = "http://testserver/"

    with (
        patch("workbench.api.routes.admin.send_invite_email", new_callable=AsyncMock),
        pytest.raises(Exception),
    ):
        await create_invite(body, request, admin_user, db_session)


@pytest.mark.asyncio
async def test_create_invite_duplicate_invite_direct(
    db_session, admin_user, test_config,
):
    """Directly call create_invite with duplicate invite (line 70)."""
    from datetime import UTC, datetime, timedelta
    from workbench.api.routes.admin import CreateInviteRequest

    token_raw, token_hash = generate_token()
    invite = UserInvite(
        email="dup_direct@test.com", username="dupdirect",
        token_hash=token_hash, invited_by=uuid4(),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    db_session.add(invite)
    await db_session.commit()

    body = CreateInviteRequest(email="dup_direct@test.com", username="anotheruser")
    request = MagicMock(spec=Request)
    request.app.state.config = test_config
    request.base_url = "http://testserver/"

    with (
        patch("workbench.api.routes.admin.send_invite_email", new_callable=AsyncMock),
        pytest.raises(Exception),
    ):
        await create_invite(body, request, admin_user, db_session)
