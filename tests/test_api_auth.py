"""Tests for workbench.api.routes.auth — full coverage for all auth endpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from unittest.mock import patch

from workbench.api.routes.auth import router as auth_router
from workbench.core.auth import (
    _hash_token,
    generate_api_key,
    generate_token,
    get_current_user,
    hash_password,
    verify_password,
)
from workbench.core.db import get_session
from workbench.core.models import (
    Base,
    User,
    UserApiKey,
    UserBraveKey,
    UserInferenceConfig,
    UserInvite,
    UserOpenRouterKey,
    UserSession,
)
from workbench.core.rate_limiter import limiter as rate_limiter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite database with all tables for auth tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class ConfigStub:
    """Stub config object that can be attached to app.state.config."""
    def __init__(self):
        self.auth_max_keys_per_user = 5
        self.inference_provider_url = "https://openrouter.ai/api/v1"
        self.inference_strong_model = "deepseek/deepseek-v4-pro"
        self.inference_quick_model = "google/gemini-2.0-flash-001"
        self.inference_medium_model = "anthropic/claude-sonnet-4-20250514"
        self.inference_requests_per_minute = 0
        self.auth_api_key_prefix = "wb"
        self.encryption_key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def _make_app(db_session, user_override=None):
    """Build a FastAPI app with the auth router and dependency overrides."""
    rate_limiter.reset()

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1")

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session

    if user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: user_override

    # Set up state needed by routes
    app.state.config = ConfigStub()

    return app


async def _make_real_user(db_session, **kwargs):
    """Create and return a real User persisted in db_session."""
    user = User(
        id=kwargs.get("id", uuid4()),
        username=kwargs.get("username", "testuser"),
        email=kwargs.get("email", "test@example.com"),
        password_hash=kwargs.get("password_hash", hash_password("secret123")),
        is_admin=kwargs.get("is_admin", False),
        created_at=kwargs.get("created_at", datetime.now(UTC).replace(tzinfo=None)),
    )
    db_session.add(user)
    await db_session.commit()
    return user


# ===================================================================
# GET /api/v1/auth/setup-status
# ===================================================================

class TestSetupStatus:
    @pytest.mark.asyncio
    async def test_needs_setup_when_no_users(self, db_session):
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.get("/api/v1/auth/setup-status")
        assert resp.status_code == 200
        assert resp.json() == {"needs_setup": True}

    @pytest.mark.asyncio
    async def test_no_setup_when_users_exist(self, db_session):
        await _make_real_user(db_session)
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.get("/api/v1/auth/setup-status")
        assert resp.status_code == 200
        assert resp.json() == {"needs_setup": False}

    @pytest.mark.asyncio
    async def test_no_setup_with_committed_user(self, db_session):
        await _make_real_user(db_session)
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.get("/api/v1/auth/setup-status")
        assert resp.status_code == 200
        assert resp.json() == {"needs_setup": False}


# ===================================================================
# POST /api/v1/auth/setup
# ===================================================================

class TestSetup:
    @pytest.mark.asyncio
    async def test_setup_creates_first_admin_user(self, db_session):
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/setup",
            json={"username": "admin", "email": "admin@test.com", "password": "strongpass123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert data["email"] == "admin@test.com"
        assert data["is_admin"] is True
        assert "user_id" in data
        assert data["message"] == "Login successful"
        # A session cookie should be set
        assert "workbench_session" in resp.cookies

        # Verify user was actually saved
        result = await db_session.execute(select(User).where(User.username == "admin"))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.is_admin is True

    @pytest.mark.asyncio
    async def test_setup_fails_when_users_exist(self, db_session):
        await _make_real_user(db_session)
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/setup",
            json={"username": "admin2", "email": "admin2@test.com", "password": "strongpass123"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Setup already completed"

    @pytest.mark.asyncio
    async def test_setup_trims_and_lowercases(self, db_session):
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/setup",
            json={"username": "  AdminUser  ", "email": "  ADMIN@TEST.COM  ", "password": "strongpass123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "AdminUser"  # trimmed but case preserved
        assert data["email"] == "admin@test.com"  # trimmed and lowered

    @pytest.mark.asyncio
    async def test_setup_validation_errors(self, db_session):
        app = _make_app(db_session)
        client = TestClient(app)
        # Missing fields
        resp = client.post("/api/v1/auth/setup", json={})
        assert resp.status_code == 422

        # Password too short
        resp = client.post(
            "/api/v1/auth/setup",
            json={"username": "u", "email": "e@e.com", "password": "short"},
        )
        assert resp.status_code == 422

        # Username too short
        resp = client.post(
            "/api/v1/auth/setup",
            json={"username": "u", "email": "e@e.com", "password": "longenough123"},
        )
        assert resp.status_code == 422


# ===================================================================
# POST /api/v1/auth/login  (password login)
# ===================================================================

class TestPasswordLogin:
    @pytest.mark.asyncio
    async def test_login_with_email(self, db_session):
        await _make_real_user(db_session, username="logintest", email="login@test.com")
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email_or_username": "login@test.com", "password": "secret123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "logintest"
        assert data["email"] == "login@test.com"
        assert data["message"] == "Login successful"
        assert "workbench_session" in resp.cookies

    @pytest.mark.asyncio
    async def test_login_with_username(self, db_session):
        await _make_real_user(db_session, username="usernamelogin", email="ul@test.com")
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email_or_username": "usernamelogin", "password": "secret123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "usernamelogin"

    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, db_session):
        await _make_real_user(db_session, username="badlogin")
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email_or_username": "badlogin", "password": "wrongpassword"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, db_session):
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email_or_username": "nobody", "password": "secret123"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, db_session):
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 400
        assert "required" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_login_user_without_password_hash(self, db_session):
        user = User(
            id=uuid4(), username="nopwuser", email="nopw@test.com",
            password_hash=None,
        )
        db_session.add(user)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email_or_username": "nopwuser", "password": "any"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_and_session_cookie_is_httponly(self, db_session):
        await _make_real_user(db_session, username="cookiecheck")
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/login",
            json={"email_or_username": "cookiecheck", "password": "secret123"},
        )
        assert resp.status_code == 200
        set_cookie = resp.headers.get("set-cookie", "")
        assert "workbench_session=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=strict" in set_cookie


# ===================================================================
# POST /api/v1/auth/login  (API key login)
# ===================================================================

class TestApiKeyLogin:
    @pytest.mark.asyncio
    async def test_api_key_login_success(self, db_session):
        user = await _make_real_user(db_session, username="apikeylogin")
        raw_key, hashed, lookup = generate_api_key()
        api_key = UserApiKey(
            user_id=user.id, key_hash=hashed, key_lookup=lookup, label="test",
        )
        db_session.add(api_key)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": raw_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "apikeylogin"
        assert "workbench_session" in resp.cookies

    @pytest.mark.asyncio
    async def test_api_key_login_invalid(self, db_session):
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": "wb-invalid-key"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid API key"

    @pytest.mark.asyncio
    async def test_api_key_login_user_deleted(self, db_session):
        """API key exists but user is gone — should raise 401."""
        user = await _make_real_user(db_session, username="deleteduser")
        raw_key, hashed, lookup = generate_api_key()
        api_key = UserApiKey(
            user_id=user.id, key_hash=hashed, key_lookup=lookup, label="test",
        )
        db_session.add(api_key)
        await db_session.commit()
        # Delete the user (cascade should handle the key too)
        await db_session.delete(user)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": raw_key},
        )
        assert resp.status_code == 401
        # Cascade delete removes the key with the user, so "Invalid API key"

    @pytest.mark.asyncio
    async def test_api_key_login_no_lookup_match_fallback_scan(self, db_session):
        """API key whose lookup hash doesn't match but key_hash does (fallback scan)."""
        user = await _make_real_user(db_session, username="fallbackuser")
        raw_key, hashed, lookup = generate_api_key()
        # Store with a different lookup so direct lookup misses
        api_key = UserApiKey(
            user_id=user.id, key_hash=hashed, key_lookup="different_lookup", label="fallback",
        )
        db_session.add(api_key)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": raw_key},
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "fallbackuser"

    @pytest.mark.asyncio
    async def test_api_key_login_fallback_scan_user_deleted(self, db_session):
        """Fallback scan finds key but user is deleted."""
        user = await _make_real_user(db_session, username="fallbackdel")
        raw_key, hashed, lookup = generate_api_key()
        api_key = UserApiKey(
            user_id=user.id, key_hash=hashed, key_lookup="different_lookup", label="fb2",
        )
        db_session.add(api_key)
        await db_session.commit()
        await db_session.delete(user)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/login",
            json={"api_key": raw_key},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_login_empty_body(self, db_session):
        """An empty body without fields — test error handling."""
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 400


# ===================================================================
# POST /api/v1/auth/logout
# ===================================================================

class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_with_valid_session(self, db_session):
        user = await _make_real_user(db_session, username="logoutuser")
        # Create a session manually
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=24)
        sess = UserSession(user_id=user.id, token_hash=token_hash, expires_at=expires)
        db_session.add(sess)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        client.cookies.set("workbench_session", raw_token)
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "message": "Logged out"}
        # Cookie should be cleared
        assert "workbench_session=" in resp.headers.get("set-cookie", "")
        # Session should be deleted
        result = await db_session.execute(select(UserSession).where(UserSession.id == sess.id))
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_logout_without_cookie(self, db_session):
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "message": "Logged out"}

    @pytest.mark.asyncio
    async def test_logout_with_invalid_cookie(self, db_session):
        app = _make_app(db_session)
        client = TestClient(app)
        client.cookies.set("workbench_session", "invalid-token")
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_logout_fallback_scan(self, db_session):
        """Cookie token doesn't match via SHA256 hash but matches via bcrypt verify."""
        user = await _make_real_user(db_session, username="fallbacklogout")
        # Create a session with a bcrypt-compatible hash (simulating legacy format)
        raw_token = "legacy-format-token-abc123"
        fake_hash = hash_password(raw_token)  # This is a bcrypt hash
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=24)
        sess = UserSession(user_id=user.id, token_hash=fake_hash, expires_at=expires)
        db_session.add(sess)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        client.cookies.set("workbench_session", raw_token)
        resp = client.post("/api/v1/auth/logout")
        assert resp.status_code == 200
        # Session should be deleted
        result = await db_session.execute(select(UserSession).where(UserSession.id == sess.id))
        assert result.scalar_one_or_none() is None


# ===================================================================
# POST /api/v1/auth/forgot-password
# ===================================================================

class TestForgotPassword:
    @patch("workbench.api.routes.auth.send_reset_email", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_forgot_password_existing_user(self, mock_send, db_session):
        await _make_real_user(db_session, username="forgotuser", email="forgot@test.com")
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "forgot@test.com"},
        )
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"]
        # Verify invite was created
        result = await db_session.execute(select(UserInvite).where(UserInvite.email == "forgot@test.com"))
        invite = result.scalar_one_or_none()
        assert invite is not None
        assert invite.username == "forgotuser"
        mock_send.assert_awaited_once()

    @patch("workbench.api.routes.auth.send_reset_email", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_forgot_password_nonexistent_email(self, mock_send, db_session):
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nobody@test.com"},
        )
        assert resp.status_code == 200
        # Should say same message to avoid leaking info
        assert "reset link" in resp.json()["message"]
        mock_send.assert_not_called()

    @patch("workbench.api.routes.auth.send_reset_email", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_forgot_password_user_without_password_hash(self, mock_send, db_session):
        user = User(
            id=uuid4(), username="nopwuser", email="nopw@test.com",
            password_hash=None,
        )
        db_session.add(user)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nopw@test.com"},
        )
        assert resp.status_code == 200
        mock_send.assert_not_called()

    @patch("workbench.api.routes.auth.send_reset_email", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_forgot_password_trims_and_lowercases(self, mock_send, db_session):
        await _make_real_user(db_session, username="caseuser", email="casemix@test.com")
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "  CASEMIX@TEST.COM  "},
        )
        assert resp.status_code == 200
        mock_send.assert_awaited_once()


# ===================================================================
# POST /api/v1/auth/reset-password
# ===================================================================

class TestResetPassword:
    @patch("workbench.api.routes.auth.send_password_changed_email", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_reset_password_success(self, mock_send, db_session):
        user = await _make_real_user(db_session, username="resetuser", email="reset@test.com")
        # Create a valid invite
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
        invite = UserInvite(
            email="reset@test.com",
            username="resetuser",
            token_hash=token_hash,
            invited_by=None,
            expires_at=expires,
        )
        db_session.add(invite)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        new_pw = "newpassword123"
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw_token, "password": new_pw},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "resetuser"
        assert "workbench_session" in resp.cookies
        mock_send.assert_awaited_once()

        # Verify password was updated
        await db_session.refresh(user)
        assert verify_password(new_pw, user.password_hash)

        # Verify invite was consumed
        result = await db_session.execute(select(UserInvite).where(UserInvite.token_hash == token_hash))
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, db_session):
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": "invalidtoken", "password": "newpassword123"},
        )
        assert resp.status_code == 400
        assert "Invalid or expired" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_reset_password_expired_token(self, db_session):
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)  # expired
        invite = UserInvite(
            email="expired@test.com",
            username="expireduser",
            token_hash=token_hash,
            invited_by=None,
            expires_at=expires,
        )
        db_session.add(invite)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw_token, "password": "newpassword123"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_revoked_token(self, db_session):
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
        invite = UserInvite(
            email="revoked@test.com",
            username="revokeduser",
            token_hash=token_hash,
            invited_by=None,
            expires_at=expires,
            is_revoked=True,
        )
        db_session.add(invite)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw_token, "password": "newpassword123"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_user_not_found(self, db_session):
        """Token valid but user referenced in invite doesn't exist."""
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
        invite = UserInvite(
            email="ghost@test.com",
            username="ghostuser",  # No User with this username
            token_hash=token_hash,
            invited_by=None,
            expires_at=expires,
        )
        db_session.add(invite)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/reset-password",
            json={"token": raw_token, "password": "newpassword123"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "User not found"


# ===================================================================
# POST /api/v1/auth/accept-invite
# ===================================================================

class TestAcceptInvite:
    @patch("workbench.api.routes.auth.send_welcome_email", new_callable=AsyncMock)
    @patch("workbench.api.routes.auth.send_invite_accepted_email", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_accept_invite_no_inviter(self, mock_invite_accepted, mock_welcome, db_session):
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
        invite = UserInvite(
            email="invited@test.com",
            username="inviteduser",
            token_hash=token_hash,
            invited_by=None,
            expires_at=expires,
        )
        db_session.add(invite)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/accept-invite",
            json={"token": raw_token, "password": "newpassword123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "inviteduser"
        assert data["email"] == "invited@test.com"
        assert data["is_admin"] is False
        assert "workbench_session" in resp.cookies
        mock_welcome.assert_awaited_once()
        mock_invite_accepted.assert_not_called()

        # Verify user was created
        result = await db_session.execute(select(User).where(User.username == "inviteduser"))
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.email == "invited@test.com"

        # Verify invite was accepted
        await db_session.refresh(invite)
        assert invite.accepted_at is not None

    @patch("workbench.api.routes.auth.send_welcome_email", new_callable=AsyncMock)
    @patch("workbench.api.routes.auth.send_invite_accepted_email", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_accept_invite_with_inviter(self, mock_invite_accepted, mock_welcome, db_session):
        admin_user = await _make_real_user(
            db_session, username="adminuser", email="admin@test.com",
        )
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
        invite = UserInvite(
            email="invited2@test.com",
            username="inviteduser2",
            token_hash=token_hash,
            invited_by=admin_user.id,
            expires_at=expires,
        )
        db_session.add(invite)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/accept-invite",
            json={"token": raw_token, "password": "newpassword123"},
        )
        assert resp.status_code == 200
        mock_welcome.assert_awaited_once()
        mock_invite_accepted.assert_awaited_once()

    @patch("workbench.api.routes.auth.send_welcome_email", new_callable=AsyncMock)
    @patch("workbench.api.routes.auth.send_invite_accepted_email", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_accept_invite_inviter_without_email(self, mock_invite_accepted, mock_welcome, db_session):
        """Inviter exists but has no email — no accepted email sent."""
        admin_user = await _make_real_user(
            db_session, username="noemailadmin", email=None,
        )
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
        invite = UserInvite(
            email="invited3@test.com",
            username="inviteduser3",
            token_hash=token_hash,
            invited_by=admin_user.id,
            expires_at=expires,
        )
        db_session.add(invite)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/accept-invite",
            json={"token": raw_token, "password": "newpassword123"},
        )
        assert resp.status_code == 200
        mock_welcome.assert_awaited_once()
        mock_invite_accepted.assert_not_called()

    @pytest.mark.asyncio
    async def test_accept_invite_invalid_token(self, db_session):
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/accept-invite",
            json={"token": "invalidtoken", "password": "newpassword123"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_invite_revoked(self, db_session):
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
        invite = UserInvite(
            email="revoked@test.com",
            username="revokeduser",
            token_hash=token_hash,
            invited_by=None,
            expires_at=expires,
            is_revoked=True,
        )
        db_session.add(invite)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/accept-invite",
            json={"token": raw_token, "password": "newpassword123"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_invite_already_accepted(self, db_session):
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
        invite = UserInvite(
            email="already@test.com",
            username="alreadyuser",
            token_hash=token_hash,
            invited_by=None,
            expires_at=expires,
            accepted_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db_session.add(invite)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/accept-invite",
            json={"token": raw_token, "password": "newpassword123"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_invite_username_or_email_taken(self, db_session):
        await _make_real_user(db_session, username="existinguser", email="existing@test.com")
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
        invite = UserInvite(
            email="existing@test.com",  # same email as existing user
            username="inviteduser4",
            token_hash=token_hash,
            invited_by=None,
            expires_at=expires,
        )
        db_session.add(invite)
        await db_session.commit()
        app = _make_app(db_session)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/auth/accept-invite",
            json={"token": raw_token, "password": "newpassword123"},
        )
        assert resp.status_code == 400
        assert "already taken" in resp.json()["detail"]


# ===================================================================
# GET /api/v1/me
# ===================================================================

class TestGetProfile:
    @pytest.mark.asyncio
    async def test_get_profile(self, db_session):
        user = await _make_real_user(
            db_session, username="profileuser", email="profile@test.com",
            password_hash=hash_password("test123"),
        )
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.get("/api/v1/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(user.id)
        assert data["username"] == "profileuser"
        assert data["email"] == "profile@test.com"
        assert data["is_admin"] is False
        assert data["has_password"] is True
        assert data["has_openrouter_key"] is False
        assert data["has_brave_key"] is False
        assert "inference_config" in data
        assert data["inference_config"]["has_api_key"] is False

    @pytest.mark.asyncio
    async def test_get_profile_with_keys(self, db_session):
        user = await _make_real_user(db_session, username="keyuser", email="key@test.com")
        # Add openrouter key
        from workbench.core.encryption import init_encryption, encrypt
        init_encryption(ConfigStub())
        or_key = UserOpenRouterKey(user_id=user.id, encrypted_key=encrypt("sk-or-v1-testkey123"))
        db_session.add(or_key)
        # Add brave key
        brave_key = UserBraveKey(user_id=user.id, encrypted_key=encrypt("bsk-testkey123"))
        db_session.add(brave_key)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.get("/api/v1/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_openrouter_key"] is True
        assert data["has_brave_key"] is True

    @pytest.mark.asyncio
    async def test_get_profile_no_password(self, db_session):
        user = User(
            id=uuid4(), username="nopw", email="nopw@test.com",
            password_hash=None,
        )
        db_session.add(user)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.get("/api/v1/me")
        assert resp.status_code == 200
        assert resp.json()["has_password"] is False

    @pytest.mark.asyncio
    async def test_get_profile_requires_auth(self, db_session):
        app = _make_app(db_session)  # no user override
        client = TestClient(app)
        resp = client.get("/api/v1/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_profile_admin(self, db_session):
        user = await _make_real_user(
            db_session, username="adminprofile", email="adminp@test.com",
            is_admin=True,
        )
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.get("/api/v1/me")
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is True

    @pytest.mark.asyncio
    async def test_get_profile_created_at_always_set(self, db_session):
        """Edge case: user has created_at set (nullable=False with default)."""
        user = await _make_real_user(
            db_session, username="hascreated", email="has@test.com",
            password_hash=None,
        )
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.get("/api/v1/me")
        assert resp.status_code == 200
        assert resp.json()["created_at"] != ""


# ===================================================================
# POST /api/v1/me/change-password
# ===================================================================

class TestChangePassword:
    @patch("workbench.api.routes.auth.send_password_changed_email", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_change_password_success(self, mock_send, db_session):
        user = await _make_real_user(
            db_session, username="changepw", email="changepw@test.com",
        )
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        new_pw = "newpassword456"
        resp = client.post(
            "/api/v1/me/change-password",
            json={"current_password": "secret123", "new_password": new_pw},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "message": "Password changed"}
        mock_send.assert_awaited_once()

        # Verify password was changed
        await db_session.refresh(user)
        assert verify_password(new_pw, user.password_hash)

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, db_session):
        user = await _make_real_user(db_session, username="wrongpwuser")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/me/change-password",
            json={"current_password": "wrongpassword", "new_password": "newpassword456"},
        )
        assert resp.status_code == 400
        assert "incorrect" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_change_password_no_password_hash(self, db_session):
        user = User(
            id=uuid4(), username="nopwchange", password_hash=None,
        )
        db_session.add(user)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/me/change-password",
            json={"current_password": "any", "new_password": "newpassword456"},
        )
        assert resp.status_code == 400

    @patch("workbench.api.routes.auth.send_password_changed_email", new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_change_password_no_email(self, mock_send, db_session):
        """User has no email — no email sent but password still changed."""
        user = await _make_real_user(db_session, username="noemailchange", email=None)
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/me/change-password",
            json={"current_password": "secret123", "new_password": "newpassword456"},
        )
        assert resp.status_code == 200
        mock_send.assert_not_called()


# ===================================================================
# POST /api/v1/me/openrouter-key
# ===================================================================

class TestSetOpenRouterKey:
    @pytest.mark.asyncio
    async def test_set_openrouter_key_success(self, db_session):
        user = await _make_real_user(db_session, username="orkeyuser")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/me/openrouter-key",
            json={"api_key": "sk-or-v1-testkey1234567890"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "message": "OpenRouter key saved"}

        # Verify it was saved
        result = await db_session.execute(
            select(UserOpenRouterKey).where(UserOpenRouterKey.user_id == user.id)
        )
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_set_openrouter_key_invalid_prefix(self, db_session):
        user = await _make_real_user(db_session, username="orkeyfail")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/me/openrouter-key",
            json={"api_key": "invalid-key-123"},
        )
        assert resp.status_code == 400
        assert "sk-or-v1-" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_set_openrouter_key_too_short(self, db_session):
        user = await _make_real_user(db_session, username="orkshort")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        # Valid prefix but too short
        resp = client.post(
            "/api/v1/me/openrouter-key",
            json={"api_key": "sk-or-v1-short"},
        )
        assert resp.status_code == 400
        assert "too short" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_set_openrouter_key_updates_existing(self, db_session):
        user = await _make_real_user(db_session, username="orkeyupdate")
        from workbench.core.encryption import init_encryption, encrypt
        init_encryption(ConfigStub())
        existing = UserOpenRouterKey(user_id=user.id, encrypted_key=encrypt("sk-or-v1-oldkey1234567890"))
        db_session.add(existing)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/me/openrouter-key",
            json={"api_key": "sk-or-v1-newkey1234567890"},
        )
        assert resp.status_code == 200


# ===================================================================
# DELETE /api/v1/me/openrouter-key
# ===================================================================

class TestDeleteOpenRouterKey:
    @pytest.mark.asyncio
    async def test_delete_openrouter_key_existing(self, db_session):
        user = await _make_real_user(db_session, username="delorkey")
        from workbench.core.encryption import init_encryption, encrypt
        init_encryption(ConfigStub())
        key_row = UserOpenRouterKey(user_id=user.id, encrypted_key=encrypt("sk-or-v1-test1234567890"))
        db_session.add(key_row)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.delete("/api/v1/me/openrouter-key")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "message": "OpenRouter key removed"}

        # Verify deletion
        result = await db_session.execute(
            select(UserOpenRouterKey).where(UserOpenRouterKey.user_id == user.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_openrouter_key_nonexistent(self, db_session):
        user = await _make_real_user(db_session, username="nodelorkey")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.delete("/api/v1/me/openrouter-key")
        assert resp.status_code == 200


# ===================================================================
# POST /api/v1/me/brave-key
# ===================================================================

class TestSetBraveKey:
    @pytest.mark.asyncio
    async def test_set_brave_key_success(self, db_session):
        user = await _make_real_user(db_session, username="braveuser")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/me/brave-key",
            json={"api_key": "bsk-testkey12345678"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "message": "Brave Search API key saved"}

        # Verify it was saved
        result = await db_session.execute(
            select(UserBraveKey).where(UserBraveKey.user_id == user.id)
        )
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_set_brave_key_too_short(self, db_session):
        user = await _make_real_user(db_session, username="braveshort")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/me/brave-key",
            json={"api_key": "short"},
        )
        assert resp.status_code == 400
        assert "too short" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_set_brave_key_updates_existing(self, db_session):
        user = await _make_real_user(db_session, username="braveupdate")
        from workbench.core.encryption import init_encryption, encrypt
        init_encryption(ConfigStub())
        existing = UserBraveKey(user_id=user.id, encrypted_key=encrypt("bsk-oldkey12345678"))
        db_session.add(existing)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/me/brave-key",
            json={"api_key": "bsk-newkey12345678"},
        )
        assert resp.status_code == 200


# ===================================================================
# DELETE /api/v1/me/brave-key
# ===================================================================

class TestDeleteBraveKey:
    @pytest.mark.asyncio
    async def test_delete_brave_key_existing(self, db_session):
        user = await _make_real_user(db_session, username="delbrave")
        from workbench.core.encryption import init_encryption, encrypt
        init_encryption(ConfigStub())
        key_row = UserBraveKey(user_id=user.id, encrypted_key=encrypt("bsk-test12345678"))
        db_session.add(key_row)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.delete("/api/v1/me/brave-key")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "message": "Brave Search API key removed"}

        # Verify deletion
        result = await db_session.execute(
            select(UserBraveKey).where(UserBraveKey.user_id == user.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_brave_key_nonexistent(self, db_session):
        user = await _make_real_user(db_session, username="nodelbrave")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.delete("/api/v1/me/brave-key")
        assert resp.status_code == 200


# ===================================================================
# GET /api/v1/me/api-keys
# ===================================================================

class TestListApiKeys:
    @pytest.mark.asyncio
    async def test_list_api_keys_empty(self, db_session):
        user = await _make_real_user(db_session, username="nolistkeys")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.get("/api/v1/me/api-keys")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_api_keys_with_data(self, db_session):
        user = await _make_real_user(db_session, username="listkeys")
        raw_key, hashed, lookup = generate_api_key()
        created = datetime.now(UTC).replace(tzinfo=None)
        api_key = UserApiKey(
            user_id=user.id, key_hash=hashed, key_lookup=lookup,
            label="mykey", created_at=created,
        )
        db_session.add(api_key)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.get("/api/v1/me/api-keys")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["label"] == "mykey"
        assert data[0]["key_fingerprint"] == lookup[:8]
        assert data[0]["id"] == str(api_key.id)
        assert data[0]["last_used_at"] is None
        assert data[0]["expires_at"] is None

    @pytest.mark.asyncio
    async def test_list_api_keys_with_optional_fields(self, db_session):
        user = await _make_real_user(db_session, username="listkeysfull")
        raw_key, hashed, lookup = generate_api_key()
        created = datetime.now(UTC).replace(tzinfo=None)
        last_used = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=30)
        api_key = UserApiKey(
            user_id=user.id, key_hash=hashed, key_lookup=lookup,
            label="fullkey", created_at=created,
            last_used_at=last_used, expires_at=expires,
        )
        db_session.add(api_key)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.get("/api/v1/me/api-keys")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["last_used_at"] is not None
        assert data[0]["expires_at"] is not None

    @pytest.mark.asyncio
    async def test_list_api_keys_other_user_not_visible(self, db_session):
        user = await _make_real_user(db_session, username="listuser")
        other = await _make_real_user(db_session, username="otheruser", email="other@test.com")
        raw_key, hashed, lookup = generate_api_key()
        api_key = UserApiKey(
            user_id=other.id, key_hash=hashed, key_lookup=lookup, label="otherkey",
        )
        db_session.add(api_key)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.get("/api/v1/me/api-keys")
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_api_keys_no_lookup_fingerprint(self, db_session):
        """key_lookup can be None — ensures no crash."""
        user = await _make_real_user(db_session, username="nolookup")
        raw_key, hashed, _ = generate_api_key()
        api_key = UserApiKey(
            user_id=user.id, key_hash=hashed, key_lookup=None, label="nolookup",
        )
        db_session.add(api_key)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.get("/api/v1/me/api-keys")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["key_fingerprint"] is None


# ===================================================================
# POST /api/v1/me/api-keys
# ===================================================================

class TestCreateApiKey:
    @pytest.mark.asyncio
    async def test_create_api_key_success(self, db_session):
        user = await _make_real_user(db_session, username="createapikey")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/me/api-keys",
            json={"label": "my-new-key"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "my-new-key"
        assert data["api_key"] is not None
        assert data["api_key"].startswith("wb-")
        assert data["key_fingerprint"] is not None

        # Verify it was saved
        result = await db_session.execute(
            select(UserApiKey).where(UserApiKey.user_id == user.id)
        )
        keys = result.scalars().all()
        assert len(keys) == 1
        assert keys[0].label == "my-new-key"

    @pytest.mark.asyncio
    async def test_create_api_key_max_limit(self, db_session):
        user = await _make_real_user(db_session, username="maxkeysuser")
        # Create 5 keys (the max per user from ConfigStub)
        for i in range(5):
            raw, hashed, lookup = generate_api_key()
            db_session.add(UserApiKey(
                user_id=user.id, key_hash=hashed, key_lookup=lookup,
                label=f"key{i}",
            ))
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/me/api-keys",
            json={"label": "should-fail"},
        )
        assert resp.status_code == 400
        assert "Maximum" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_api_key_default_label(self, db_session):
        user = await _make_real_user(db_session, username="defaultlabel")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/me/api-keys",
            json={},
        )
        assert resp.status_code == 200
        assert resp.json()["label"] == "default"


# ===================================================================
# DELETE /api/v1/me/api-keys/{key_id}
# ===================================================================

class TestDeleteApiKey:
    @pytest.mark.asyncio
    async def test_delete_api_key_success(self, db_session):
        user = await _make_real_user(db_session, username="delapikey")
        raw_key, hashed, lookup = generate_api_key()
        api_key = UserApiKey(
            user_id=user.id, key_hash=hashed, key_lookup=lookup, label="todelete",
        )
        db_session.add(api_key)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.delete(f"/api/v1/me/api-keys/{api_key.id}")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

        # Verify deletion
        result = await db_session.execute(
            select(UserApiKey).where(UserApiKey.id == api_key.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_api_key_not_found(self, db_session):
        user = await _make_real_user(db_session, username="delnotexist")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.delete(f"/api/v1/me/api-keys/{uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "API key not found"

    @pytest.mark.asyncio
    async def test_delete_api_key_other_users_key(self, db_session):
        user = await _make_real_user(db_session, username="ownerdel")
        other = await _make_real_user(db_session, username="otherdel", email="otherdel@test.com")
        raw_key, hashed, lookup = generate_api_key()
        api_key = UserApiKey(
            user_id=other.id, key_hash=hashed, key_lookup=lookup, label="otherskey",
        )
        db_session.add(api_key)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.delete(f"/api/v1/me/api-keys/{api_key.id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_api_key_invalid_uuid(self, db_session):
        user = await _make_real_user(db_session, username="invaliddel")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.delete("/api/v1/me/api-keys/not-a-uuid")
        assert resp.status_code == 422  # FastAPI UUID validation


# ===================================================================
# GET /api/v1/me/inference-config
# ===================================================================

class TestGetInferenceConfig:
    @pytest.mark.asyncio
    async def test_get_inference_config_defaults(self, db_session):
        user = await _make_real_user(db_session, username="infodefault")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.get("/api/v1/me/inference-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_url"] == "https://openrouter.ai/api/v1"
        assert data["strong_model"] == "deepseek/deepseek-v4-pro"
        assert data["quick_model"] == "google/gemini-2.0-flash-001"
        assert data["medium_model"] == "anthropic/claude-sonnet-4-20250514"
        assert data["requests_per_minute"] == 0
        assert data["has_api_key"] is False

    @pytest.mark.asyncio
    async def test_get_inference_config_custom(self, db_session):
        user = await _make_real_user(db_session, username="infocustom")
        from workbench.core.encryption import init_encryption, encrypt
        init_encryption(ConfigStub())
        cfg = UserInferenceConfig(
            user_id=user.id,
            provider_url="https://custom.api/v1",
            strong_model="custom-model",
            quick_model="custom-quick",
            medium_model="custom-medium",
            requests_per_minute=10,
            api_key=encrypt("test-api-key"),
        )
        db_session.add(cfg)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.get("/api/v1/me/inference-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_url"] == "https://custom.api/v1"
        assert data["strong_model"] == "custom-model"
        assert data["quick_model"] == "custom-quick"
        assert data["medium_model"] == "custom-medium"
        assert data["requests_per_minute"] == 10
        assert data["has_api_key"] is True


# ===================================================================
# PUT /api/v1/me/inference-config
# ===================================================================

class TestUpdateInferenceConfig:
    @pytest.mark.asyncio
    async def test_update_full_config(self, db_session):
        user = await _make_real_user(db_session, username="updateinfofull")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.put(
            "/api/v1/me/inference-config",
            json={
                "api_key": "new-api-key",
                "provider_url": "https://custom.api/v1",
                "strong_model": "strong-model",
                "quick_model": "quick-model",
                "medium_model": "medium-model",
                "requests_per_minute": 20,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_url"] == "https://custom.api/v1"
        assert data["strong_model"] == "strong-model"
        assert data["quick_model"] == "quick-model"
        assert data["medium_model"] == "medium-model"
        assert data["requests_per_minute"] == 20
        assert data["has_api_key"] is True

    @pytest.mark.asyncio
    async def test_update_partial_config(self, db_session):
        user = await _make_real_user(db_session, username="updateinfopart")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.put(
            "/api/v1/me/inference-config",
            json={"provider_url": "https://partial.api/v1", "strong_model": "partial-model"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider_url"] == "https://partial.api/v1"
        assert data["strong_model"] == "partial-model"
        # Other fields should be defaults
        assert data["quick_model"] == "google/gemini-2.0-flash-001"
        assert data["has_api_key"] is False

    @pytest.mark.asyncio
    async def test_update_forbids_extra_fields(self, db_session):
        user = await _make_real_user(db_session, username="updateextra")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.put(
            "/api/v1/me/inference-config",
            json={"provider_url": "https://x.api/v1", "unknown_field": "should_fail"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_update_clear_api_key(self, db_session):
        """Setting api_key to '' should clear it."""
        user = await _make_real_user(db_session, username="clearkey")
        from workbench.core.encryption import init_encryption, encrypt
        init_encryption(ConfigStub())
        cfg = UserInferenceConfig(
            user_id=user.id,
            provider_url="https://original.api/v1",
            api_key=encrypt("existing-key"),
        )
        db_session.add(cfg)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.put(
            "/api/v1/me/inference-config",
            json={"api_key": ""},
        )
        assert resp.status_code == 200
        assert resp.json()["has_api_key"] is False


# ===================================================================
# DELETE /api/v1/me/inference-config
# ===================================================================

class TestDeleteInferenceConfig:
    @pytest.mark.asyncio
    async def test_delete_inference_config_existing(self, db_session):
        user = await _make_real_user(db_session, username="delinfocfg")
        cfg = UserInferenceConfig(
            user_id=user.id,
            provider_url="https://custom.api/v1",
            strong_model="custom-model",
        )
        db_session.add(cfg)
        await db_session.commit()
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.delete("/api/v1/me/inference-config")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "message": "Inference config reset to defaults"}

        # Verify deletion
        result = await db_session.execute(
            select(UserInferenceConfig).where(UserInferenceConfig.user_id == user.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_inference_config_nonexistent(self, db_session):
        user = await _make_real_user(db_session, username="nodelinfocfg")
        app = _make_app(db_session, user_override=user)
        client = TestClient(app)
        resp = client.delete("/api/v1/me/inference-config")
        assert resp.status_code == 200


# ===================================================================
# Direct-call coverage tests — call route handler functions directly
# to ensure coverage.py can track async handler body lines.
# ===================================================================


def _mock_request(**kwargs):
    """Build a real starlette Request for direct handler calls."""
    from starlette.requests import Request as StarletteRequest

    cfg = kwargs.get("config", ConfigStub())
    cookie_val = kwargs.get("cookie")

    class AppState:
        config = cfg

    class MockApp:
        state = AppState()

    headers = []
    if "content_type" in kwargs:
        headers.append((b"content-type", kwargs["content_type"].encode()))
    if cookie_val:
        headers.append((b"cookie", f"workbench_session={cookie_val}".encode()))

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "scheme": "http",
        "server": ("test", 80),
        "query_string": b"",
        "root_path": "",
        "app": MockApp(),
    }
    req = StarletteRequest(scope)
    # For direct endpoint calls, we need the json method to work
    if "json_body" in kwargs:
        import json as _json
        async def _json_body():
            return kwargs["json_body"]
        req.json = _json_body
    return req


def _mock_response() -> MagicMock:
    """Build a minimal mock Response for direct handler calls."""
    resp = MagicMock()
    resp.set_cookie = MagicMock()
    resp.delete_cookie = MagicMock()
    return resp


class TestDirectCoverage:
    """Call route handler functions directly to exercise all uncovered lines.

    These tests bypass the ASGI transport so that coverage.py can track
    individual statement lines inside async handler bodies.  Each test
    explicitly reloads the auth module *after* coverage has started so that
    function definitions are registered with the C tracer.
    """

    @pytest_asyncio.fixture(autouse=True)
    async def _auto_reset(self):
        """Disable rate limiting entirely for these direct-call tests."""
        from workbench.core.rate_limiter import limiter as _rl
        _orig = _rl.limiter.hit
        _rl.limiter.hit = lambda *a, **kw: True
        yield
        _rl.limiter.hit = _orig

    @pytest.mark.asyncio
    async def test_setup_status_empty(self, db_session):
        """Line 160: scalar() or 0; line 161: return."""
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        result = await _auth.setup_status(session=db_session)
        assert result == {"needs_setup": True}

    @pytest.mark.asyncio
    async def test_setup_status_with_user(self, db_session):
        """Line 160: scalar() returns a count; line 161: return."""
        await _make_real_user(db_session)
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        result = await _auth.setup_status(session=db_session)
        assert result == {"needs_setup": False}

    @pytest.mark.asyncio
    async def test_setup_creates_user(self, db_session):
        """Lines 173–188: full setup flow."""
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import SetupRequest
        body = SetupRequest(username="directadm", email="direct@test.com", password="strongpass123")
        req = _mock_request()
        resp = _mock_response()
        result = await _auth.setup(body=body, request=req, response=resp, session=db_session)
        assert result["username"] == "directadm"
        assert result["email"] == "direct@test.com"
        assert result["is_admin"] is True
        resp.set_cookie.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_already_completed(self, db_session):
        """Lines 173–175: count > 0 raises."""
        await _make_real_user(db_session)
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import SetupRequest
        body = SetupRequest(username="admin2", email="a2@t.com", password="strongpass123")
        req = _mock_request()
        resp = _mock_response()
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await _auth.setup(body=body, request=req, response=resp, session=db_session)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_password_login_success(self, db_session):
        """Lines 218, 219, 221, 224–226: login via password."""
        await _make_real_user(db_session, username="directpw", email="dpw@t.com")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(content_type="application/json")
        resp = _mock_response()
        # Call _password_login directly with parsed body
        body = {"email_or_username": "directpw", "password": "secret123"}
        result = await _auth._password_login(body, req, resp, db_session)
        assert result["username"] == "directpw"
        resp.set_cookie.assert_called_once()

    @pytest.mark.asyncio
    async def test_password_login_user_none(self, db_session):
        """Line 219: user is None raises."""
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(content_type="application/json")
        resp = _mock_response()
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await _auth._password_login(
                {"email_or_username": "nobody", "password": "x"}, req, resp, db_session
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_password_login_no_hash(self, db_session):
        """Line 219: user.password_hash is None raises."""
        from workbench.core.models import User
        user = User(id=uuid4(), username="nohash", email="nh@t.com", password_hash=None)
        db_session.add(user)
        await db_session.commit()
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(content_type="application/json")
        resp = _mock_response()
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await _auth._password_login(
                {"email_or_username": "nohash", "password": "x"}, req, resp, db_session
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_password_login_wrong_password(self, db_session):
        """Line 221–222: wrong password raises."""
        await _make_real_user(db_session, username="wrongpw")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(content_type="application/json")
        resp = _mock_response()
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await _auth._password_login(
                {"email_or_username": "wrongpw", "password": "bad"}, req, resp, db_session
            )
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_login_direct_match(self, db_session):
        """Lines 236–243: direct key lookup success."""
        user = await _make_real_user(db_session, username="apikdirect")
        from workbench.core.auth import generate_api_key
        raw_key, hashed, lookup = generate_api_key()
        db_session.add(UserApiKey(user_id=user.id, key_hash=hashed, key_lookup=lookup, label="t"))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(content_type="application/json")
        resp = _mock_response()
        result = await _auth._api_key_login(raw_key, req, resp, db_session)
        assert result["username"] == "apikdirect"

    @pytest.mark.asyncio
    async def test_api_key_login_direct_user_gone(self, db_session):
        """Lines 238–240: key found but user deleted."""
        user = await _make_real_user(db_session, username="apikdeluser")
        from workbench.core.auth import generate_api_key
        raw_key, hashed, lookup = generate_api_key()
        db_session.add(UserApiKey(user_id=user.id, key_hash=hashed, key_lookup=lookup, label="t"))
        await db_session.commit()
        await db_session.delete(user)
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(content_type="application/json")
        resp = _mock_response()
        from fastapi import HTTPException
        # Direct lookup finds the key row but user is gone -> falls through to fallback scan
        # Fallback also fails -> 401
        with pytest.raises(HTTPException) as exc:
            await _auth._api_key_login(raw_key, req, resp, db_session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_login_fallback_match(self, db_session):
        """Lines 245–253: fallback scan success."""
        user = await _make_real_user(db_session, username="apikfallback")
        from workbench.core.auth import generate_api_key
        raw_key, hashed, lookup = generate_api_key()
        db_session.add(UserApiKey(user_id=user.id, key_hash=hashed, key_lookup="diff_lkup", label="t"))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(content_type="application/json")
        resp = _mock_response()
        result = await _auth._api_key_login(raw_key, req, resp, db_session)
        assert result["username"] == "apikfallback"

    @pytest.mark.asyncio
    async def test_api_key_login_fallback_user_gone(self, db_session):
        """Lines 248–250: fallback finds key but user deleted."""
        user = await _make_real_user(db_session, username="apikfbdel")
        from workbench.core.auth import generate_api_key
        raw_key, hashed, lookup = generate_api_key()
        db_session.add(UserApiKey(user_id=user.id, key_hash=hashed, key_lookup="diff_lkup", label="t"))
        await db_session.commit()
        await db_session.delete(user)
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(content_type="application/json")
        resp = _mock_response()
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await _auth._api_key_login(raw_key, req, resp, db_session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_login_invalid(self, db_session):
        """Line 254: no match raises."""
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(content_type="application/json")
        resp = _mock_response()
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await _auth._api_key_login("wb-invalid", req, resp, db_session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_logout_with_valid_session(self, db_session):
        """Lines 269–272: delete session row."""
        user = await _make_real_user(db_session)
        from workbench.core.auth import generate_token, _hash_token
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=24)
        db_session.add(UserSession(user_id=user.id, token_hash=token_hash, expires_at=expires))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(cookie=raw_token)
        resp = _mock_response()
        result = await _auth.logout(request=req, response=resp, session=db_session)
        assert result["status"] == "ok"
        # Verify session deleted
        row = await db_session.execute(select(UserSession).where(UserSession.token_hash == token_hash))
        assert row.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_logout_fallback_scan(self, db_session):
        """Lines 274–279: fallback scan deletes session."""
        user = await _make_real_user(db_session)
        raw_token = "legacy-format-token-xyz"
        from workbench.core.auth import hash_password
        bcrypt_hash = hash_password(raw_token)  # This is a bcrypt hash
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=24)
        db_session.add(UserSession(user_id=user.id, token_hash=bcrypt_hash, expires_at=expires))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(cookie=raw_token)
        resp = _mock_response()
        result = await _auth.logout(request=req, response=resp, session=db_session)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_logout_no_cookie(self, db_session):
        """Line 280–281: no cookie just returns ok."""
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request()
        resp = _mock_response()
        result = await _auth.logout(request=req, response=resp, session=db_session)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_forgot_password_sends_email(self, db_session):
        """Lines 294–310: user found with password_hash."""
        await _make_real_user(db_session, username="fpwuser", email="fpw@t.com")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import ForgotPasswordRequest
        with patch.object(_auth, "send_reset_email", new_callable=AsyncMock) as mock_send:
            body = ForgotPasswordRequest(email="fpw@t.com")
            req = _mock_request()
            result = await _auth.forgot_password(body=body, request=req, session=db_session)
            assert "reset link" in result["message"]
            mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_forgot_password_no_user(self, db_session):
        """Line 294: user not found, skips email."""
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import ForgotPasswordRequest
        with patch.object(_auth, "send_reset_email", new_callable=AsyncMock) as mock_send:
            body = ForgotPasswordRequest(email="nouser@t.com")
            req = _mock_request()
            result = await _auth.forgot_password(body=body, request=req, session=db_session)
            assert "reset link" in result["message"]
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_forgot_password_no_password_hash(self, db_session):
        """Line 295: user has no password_hash."""
        user = User(id=uuid4(), username="npw", email="npw@t.com", password_hash=None)
        db_session.add(user)
        await db_session.commit()
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import ForgotPasswordRequest
        with patch.object(_auth, "send_reset_email", new_callable=AsyncMock) as mock_send:
            body = ForgotPasswordRequest(email="npw@t.com")
            req = _mock_request()
            result = await _auth.forgot_password(body=body, request=req, session=db_session)
            assert "reset link" in result["message"]
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_reset_password_success(self, db_session):
        """Lines 324–339: full reset flow."""
        user = await _make_real_user(db_session, username="rpwuser", email="rpw@t.com")
        from workbench.core.auth import generate_token
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
        db_session.add(UserInvite(email="rpw@t.com", username="rpwuser", token_hash=token_hash, invited_by=None, expires_at=expires))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import ResetPasswordRequest
        with patch.object(_auth, "send_password_changed_email", new_callable=AsyncMock) as mock_send:
            body = ResetPasswordRequest(token=raw_token, password="newpw1234")
            req = _mock_request()
            resp = _mock_response()
            result = await _auth.reset_password(body=body, request=req, response=resp, session=db_session)
            assert result["username"] == "rpwuser"
            resp.set_cookie.assert_called_once()
            mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reset_password_none_row(self, db_session):
        """Line 324: consume_token returns None."""
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import ResetPasswordRequest
        from fastapi import HTTPException
        body = ResetPasswordRequest(token="invalid", password="newpw1234")
        req = _mock_request()
        resp = _mock_response()
        with pytest.raises(HTTPException) as exc:
            await _auth.reset_password(body=body, request=req, response=resp, session=db_session)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_revoked(self, db_session):
        """Line 324: row.is_revoked is True."""
        from workbench.core.auth import generate_token
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
        db_session.add(UserInvite(email="rev@t.com", username="revuser", token_hash=token_hash, invited_by=None, expires_at=expires, is_revoked=True))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import ResetPasswordRequest
        from fastapi import HTTPException
        body = ResetPasswordRequest(token=raw_token, password="newpw1234")
        req = _mock_request()
        resp = _mock_response()
        with pytest.raises(HTTPException) as exc:
            await _auth.reset_password(body=body, request=req, response=resp, session=db_session)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_user_not_found(self, db_session):
        """Lines 327–330: user referenced in invite doesn't exist."""
        from workbench.core.auth import generate_token
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
        db_session.add(UserInvite(email="ghost@t.com", username="ghostuser", token_hash=token_hash, invited_by=None, expires_at=expires))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import ResetPasswordRequest
        from fastapi import HTTPException
        body = ResetPasswordRequest(token=raw_token, password="newpw1234")
        req = _mock_request()
        resp = _mock_response()
        with pytest.raises(HTTPException) as exc:
            await _auth.reset_password(body=body, request=req, response=resp, session=db_session)
        assert exc.value.status_code == 400
        assert exc.value.detail == "User not found"

    @pytest.mark.asyncio
    async def test_accept_invite_no_inviter(self, db_session):
        """Lines 353–384: successful invite acceptance without inviter."""
        from workbench.core.auth import generate_token
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
        db_session.add(UserInvite(email="ainv@t.com", username="ainvuser", token_hash=token_hash, invited_by=None, expires_at=expires))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import AcceptInviteRequest
        with patch.object(_auth, "send_welcome_email", new_callable=AsyncMock) as mock_welcome:
            with patch.object(_auth, "send_invite_accepted_email", new_callable=AsyncMock) as mock_inv:
                body = AcceptInviteRequest(token=raw_token, password="newpw1234")
                req = _mock_request()
                resp = _mock_response()
                result = await _auth.accept_invite(body=body, request=req, response=resp, session=db_session)
                assert result["username"] == "ainvuser"
                mock_welcome.assert_awaited_once()
                mock_inv.assert_not_called()

    @pytest.mark.asyncio
    async def test_accept_invite_with_inviter(self, db_session):
        """Lines 376–380: send invite-accepted email to inviter."""
        admin = await _make_real_user(db_session, username="admininv", email="admininv@t.com")
        from workbench.core.auth import generate_token
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
        db_session.add(UserInvite(email="ainv2@t.com", username="ainvuser2", token_hash=token_hash, invited_by=admin.id, expires_at=expires))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import AcceptInviteRequest
        with patch.object(_auth, "send_welcome_email", new_callable=AsyncMock) as mock_welcome:
            with patch.object(_auth, "send_invite_accepted_email", new_callable=AsyncMock) as mock_inv:
                body = AcceptInviteRequest(token=raw_token, password="newpw1234")
                req = _mock_request()
                resp = _mock_response()
                result = await _auth.accept_invite(body=body, request=req, response=resp, session=db_session)
                assert result["username"] == "ainvuser2"
                mock_welcome.assert_awaited_once()
                mock_inv.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_accept_invite_inviter_no_email(self, db_session):
        """Lines 377–379: inviter exists but has no email."""
        admin = await _make_real_user(db_session, username="adminnoemail", email=None)
        from workbench.core.auth import generate_token
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
        db_session.add(UserInvite(email="ainv3@t.com", username="ainvuser3", token_hash=token_hash, invited_by=admin.id, expires_at=expires))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import AcceptInviteRequest
        with patch.object(_auth, "send_welcome_email", new_callable=AsyncMock) as mock_welcome:
            with patch.object(_auth, "send_invite_accepted_email", new_callable=AsyncMock) as mock_inv:
                body = AcceptInviteRequest(token=raw_token, password="newpw1234")
                req = _mock_request()
                resp = _mock_response()
                result = await _auth.accept_invite(body=body, request=req, response=resp, session=db_session)
                assert result["username"] == "ainvuser3"
                mock_welcome.assert_awaited_once()
                mock_inv.assert_not_called()

    @pytest.mark.asyncio
    async def test_accept_invite_invalid(self, db_session):
        """Line 353: row is None."""
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import AcceptInviteRequest
        from fastapi import HTTPException
        body = AcceptInviteRequest(token="invalid", password="newpw1234")
        req = _mock_request()
        resp = _mock_response()
        with pytest.raises(HTTPException) as exc:
            await _auth.accept_invite(body=body, request=req, response=resp, session=db_session)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_invite_revoked(self, db_session):
        """Line 353: row.is_revoked."""
        from workbench.core.auth import generate_token
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
        db_session.add(UserInvite(email="rev@t.com", username="revuser", token_hash=token_hash, invited_by=None, expires_at=expires, is_revoked=True))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import AcceptInviteRequest
        from fastapi import HTTPException
        body = AcceptInviteRequest(token=raw_token, password="newpw1234")
        req = _mock_request()
        resp = _mock_response()
        with pytest.raises(HTTPException) as exc:
            await _auth.accept_invite(body=body, request=req, response=resp, session=db_session)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_invite_already_accepted(self, db_session):
        """Line 353: row.accepted_at is not None."""
        from workbench.core.auth import generate_token
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
        db_session.add(UserInvite(email="acc@t.com", username="accuser", token_hash=token_hash, invited_by=None, expires_at=expires, accepted_at=datetime.now(UTC).replace(tzinfo=None)))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import AcceptInviteRequest
        from fastapi import HTTPException
        body = AcceptInviteRequest(token=raw_token, password="newpw1234")
        req = _mock_request()
        resp = _mock_response()
        with pytest.raises(HTTPException) as exc:
            await _auth.accept_invite(body=body, request=req, response=resp, session=db_session)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_get_profile_no_keys(self, db_session):
        """Lines 394–406: profile without keys."""
        user = await _make_real_user(db_session, username="dprofile", email="dp@t.com")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request()
        result = await _auth.get_profile(request=req, user=user, session=db_session)
        assert result.username == "dprofile"
        assert result.has_openrouter_key is False
        assert result.has_brave_key is False

    @pytest.mark.asyncio
    async def test_get_profile_with_keys(self, db_session):
        """Lines 394–406: profile with keys."""
        user = await _make_real_user(db_session, username="dprofilek", email="dpk@t.com")
        from workbench.core.encryption import init_encryption, encrypt
        init_encryption(ConfigStub())
        db_session.add(UserOpenRouterKey(user_id=user.id, encrypted_key=encrypt("sk-or-v1-test1234567890")))
        db_session.add(UserBraveKey(user_id=user.id, encrypted_key=encrypt("bsk-test12345678")))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request()
        result = await _auth.get_profile(request=req, user=user, session=db_session)
        assert result.has_openrouter_key is True
        assert result.has_brave_key is True

    @pytest.mark.asyncio
    async def test_change_password_with_email(self, db_session):
        """Lines 421–424: password changed, email sent."""
        user = await _make_real_user(db_session, username="dcpwe", email="dcpw@t.com")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import ChangePasswordRequest
        with patch.object(_auth, "send_password_changed_email", new_callable=AsyncMock) as mock_send:
            body = ChangePasswordRequest(current_password="secret123", new_password="newpw1234")
            req = _mock_request()
            result = await _auth.change_password(body=body, request=req, user=user, session=db_session)
            assert result["status"] == "ok"
            mock_send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_change_password_no_email(self, db_session):
        """Lines 421–424: no email, no send."""
        user = await _make_real_user(db_session, username="dcpwnoem", email=None)
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import ChangePasswordRequest
        with patch.object(_auth, "send_password_changed_email", new_callable=AsyncMock) as mock_send:
            body = ChangePasswordRequest(current_password="secret123", new_password="newpw1234")
            req = _mock_request()
            result = await _auth.change_password(body=body, request=req, user=user, session=db_session)
            assert result["status"] == "ok"
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_openrouter_key_success(self, db_session):
        """Line 443: return."""
        user = await _make_real_user(db_session, username="dorset")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import OpenRouterKeyRequest
        req = _mock_request()
        body = OpenRouterKeyRequest(api_key="sk-or-v1-testkey1234567890")
        result = await _auth.set_openrouter_key(body=body, request=req, user=user, session=db_session)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_delete_openrouter_key_exists(self, db_session):
        """Lines 454–458: key exists, delete it."""
        user = await _make_real_user(db_session, username="ddorke")
        from workbench.core.encryption import init_encryption, encrypt
        init_encryption(ConfigStub())
        db_session.add(UserOpenRouterKey(user_id=user.id, encrypted_key=encrypt("sk-or-v1-test1234567890")))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        result = await _auth.delete_openrouter_key(user=user, session=db_session)
        assert result["status"] == "ok"
        row = await db_session.execute(select(UserOpenRouterKey).where(UserOpenRouterKey.user_id == user.id))
        assert row.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_openrouter_key_nonexistent(self, db_session):
        """Lines 454, 458: no key exists."""
        user = await _make_real_user(db_session, username="ddorkeno")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        result = await _auth.delete_openrouter_key(user=user, session=db_session)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_set_brave_key_success(self, db_session):
        """Line 472: return."""
        user = await _make_real_user(db_session, username="dbraveset")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import BraveKeyRequest
        req = _mock_request()
        body = BraveKeyRequest(api_key="bsk-testkey12345678")
        result = await _auth.set_brave_key(body=body, request=req, user=user, session=db_session)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_delete_brave_key_exists(self, db_session):
        """Lines 483–487: key exists."""
        user = await _make_real_user(db_session, username="ddbrave")
        from workbench.core.encryption import init_encryption, encrypt
        init_encryption(ConfigStub())
        db_session.add(UserBraveKey(user_id=user.id, encrypted_key=encrypt("bsk-test12345678")))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        result = await _auth.delete_brave_key(user=user, session=db_session)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_delete_brave_key_nonexistent(self, db_session):
        """Lines 483, 487: no key."""
        user = await _make_real_user(db_session, username="ddbraveno")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        result = await _auth.delete_brave_key(user=user, session=db_session)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_list_api_keys_empty(self, db_session):
        """Lines 496–497: empty list."""
        user = await _make_real_user(db_session, username="dlkempty")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        result = await _auth.list_api_keys(user=user, session=db_session)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_api_keys_with_data(self, db_session):
        """Lines 496–507: with keys."""
        user = await _make_real_user(db_session, username="dlkdata")
        from workbench.core.auth import generate_api_key
        raw_key, hashed, lookup = generate_api_key()
        db_session.add(UserApiKey(user_id=user.id, key_hash=hashed, key_lookup=lookup, label="k1"))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        result = await _auth.list_api_keys(user=user, session=db_session)
        assert len(result) == 1
        assert result[0].label == "k1"

    @pytest.mark.asyncio
    async def test_create_api_key_success(self, db_session):
        """Lines 521–540: create a new key."""
        user = await _make_real_user(db_session, username="dcak")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import ApiKeyLabel
        req = _mock_request()
        body = ApiKeyLabel(label="newkey")
        result = await _auth.create_api_key(body=body, request=req, user=user, session=db_session)
        assert result.label == "newkey"
        assert result.api_key is not None

    @pytest.mark.asyncio
    async def test_create_api_key_max_reached(self, db_session):
        """Lines 521–525: max keys reached."""
        user = await _make_real_user(db_session, username="dcakmax")
        from workbench.core.auth import generate_api_key
        for i in range(5):
            raw, h, lk = generate_api_key()
            db_session.add(UserApiKey(user_id=user.id, key_hash=h, key_lookup=lk, label=f"k{i}"))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import ApiKeyLabel
        from fastapi import HTTPException
        req = _mock_request()
        body = ApiKeyLabel(label="toomany")
        with pytest.raises(HTTPException) as exc:
            await _auth.create_api_key(body=body, request=req, user=user, session=db_session)
        assert exc.value.status_code == 400
        assert "Maximum" in exc.value.detail

    @pytest.mark.asyncio
    async def test_delete_api_key_success(self, db_session):
        """Lines 562–567: delete existing key."""
        user = await _make_real_user(db_session, username="ddak")
        from workbench.core.auth import generate_api_key
        raw, h, lk = generate_api_key()
        key = UserApiKey(user_id=user.id, key_hash=h, key_lookup=lk, label="delme")
        db_session.add(key)
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        result = await _auth.delete_api_key(key_id=str(key.id), user=user, session=db_session)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_delete_api_key_not_found(self, db_session):
        """Lines 562–564: key not found."""
        user = await _make_real_user(db_session, username="ddaknf")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from fastapi import HTTPException
        from uuid import uuid4
        with pytest.raises(HTTPException) as exc:
            await _auth.delete_api_key(key_id=str(uuid4()), user=user, session=db_session)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_inference_config(self, db_session):
        """Line 579: return inference config."""
        user = await _make_real_user(db_session, username="dinfcfg")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request()
        result = await _auth.get_inference_config(request=req, user=user, session=db_session)
        assert result.provider_url is not None
        assert result.has_api_key is False

    @pytest.mark.asyncio
    async def test_update_inference_config(self, db_session):
        """Lines 599–600: update and return."""
        user = await _make_real_user(db_session, username="duinfcfg")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import InferenceConfigRequest
        req = _mock_request()
        body = InferenceConfigRequest(provider_url="https://custom.api/v1", strong_model="sm")
        result = await _auth.update_inference_config(body=body, request=req, user=user, session=db_session)
        assert result.provider_url == "https://custom.api/v1"

    @pytest.mark.asyncio
    async def test_delete_inference_config_exists(self, db_session):
        """Lines 611–615: delete existing config."""
        user = await _make_real_user(db_session, username="ddinfcfg")
        db_session.add(UserInferenceConfig(user_id=user.id, provider_url="https://x.api/v1"))
        await db_session.commit()
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        result = await _auth.delete_inference_config(user=user, session=db_session)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_delete_inference_config_nonexistent(self, db_session):
        """Lines 611, 615: no config to delete."""
        user = await _make_real_user(db_session, username="ddinfcfgn")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        result = await _auth.delete_inference_config(user=user, session=db_session)
        assert result["status"] == "ok"

    # ── Remaining uncovered lines ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_login_endpoint_dispatches_password(self, db_session):
        """Lines 198–204: login() reads content-type and dispatches to password login."""
        await _make_real_user(db_session, username="logindispatch", email="ld@t.com")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(content_type="application/json", json_body={"email_or_username": "logindispatch", "password": "secret123"})
        resp = _mock_response()
        result = await _auth.login(request=req, response=resp, session=db_session)
        assert result["username"] == "logindispatch"

    @pytest.mark.asyncio
    async def test_login_endpoint_dispatches_api_key(self, db_session):
        """Lines 198–204: login() dispatches to api_key login."""
        user = await _make_real_user(db_session, username="logindispapik")
        from workbench.core.auth import generate_api_key
        raw_key, hashed, lookup = generate_api_key()
        db_session.add(UserApiKey(user_id=user.id, key_hash=hashed, key_lookup=lookup, label="t"))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        req = _mock_request(content_type="application/json", json_body={"api_key": raw_key})
        resp = _mock_response()
        result = await _auth.login(request=req, response=resp, session=db_session)
        assert result["username"] == "logindispapik"

    @pytest.mark.asyncio
    async def test_password_login_missing_fields(self, db_session):
        """Line 211: empty identifier or password."""
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from fastapi import HTTPException
        req = _mock_request()
        resp = _mock_response()
        with pytest.raises(HTTPException) as exc:
            await _auth._password_login({"email_or_username": "", "password": "x"}, req, resp, db_session)
        assert exc.value.status_code == 400
        with pytest.raises(HTTPException) as exc:
            await _auth._password_login({"email_or_username": "u", "password": ""}, req, resp, db_session)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_api_key_login_direct_user_not_found(self, db_session):
        """Line 240: direct lookup finds key but user is gone."""
        from workbench.core.auth import generate_api_key
        raw_key, hashed, lookup = generate_api_key()
        # Create the key with a fake user_id that doesn't exist
        fake_user_id = uuid4()
        db_session.add(UserApiKey(user_id=fake_user_id, key_hash=hashed, key_lookup=lookup, label="t"))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from fastapi import HTTPException
        req = _mock_request()
        resp = _mock_response()
        with pytest.raises(HTTPException) as exc:
            await _auth._api_key_login(raw_key, req, resp, db_session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_api_key_login_fallback_user_not_found(self, db_session):
        """Line 250: fallback finds key but user is gone."""
        from workbench.core.auth import generate_api_key
        raw_key, hashed, lookup = generate_api_key()
        fake_user_id = uuid4()
        db_session.add(UserApiKey(user_id=fake_user_id, key_hash=hashed, key_lookup="diff", label="t"))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from fastapi import HTTPException
        req = _mock_request()
        resp = _mock_response()
        with pytest.raises(HTTPException) as exc:
            await _auth._api_key_login(raw_key, req, resp, db_session)
        assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_accept_invite_existing_user(self, db_session):
        """Line 360: username or email already taken."""
        await _make_real_user(db_session, username="existingai", email="existingai@t.com")
        from workbench.core.auth import generate_token
        raw_token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7)
        db_session.add(UserInvite(email="existingai@t.com", username="newuser", token_hash=token_hash, invited_by=None, expires_at=expires))
        await db_session.commit()

        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import AcceptInviteRequest
        from fastapi import HTTPException
        body = AcceptInviteRequest(token=raw_token, password="newpw1234")
        req = _mock_request()
        resp = _mock_response()
        with pytest.raises(HTTPException) as exc:
            await _auth.accept_invite(body=body, request=req, response=resp, session=db_session)
        assert exc.value.status_code == 400
        assert "already taken" in exc.value.detail

    @pytest.mark.asyncio
    async def test_change_password_incorrect(self, db_session):
        """Line 418: current password is incorrect."""
        user = await _make_real_user(db_session, username="dcpwinc", email="dcpwinc@t.com")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import ChangePasswordRequest
        from fastapi import HTTPException
        body = ChangePasswordRequest(current_password="wrongpassword", new_password="newpw1234")
        req = _mock_request()
        with pytest.raises(HTTPException) as exc:
            await _auth.change_password(body=body, request=req, user=user, session=db_session)
        assert exc.value.status_code == 400
        assert "incorrect" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_set_openrouter_key_validation(self, db_session):
        """Lines 436, 441: validation errors."""
        user = await _make_real_user(db_session, username="dorkeyinv")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import OpenRouterKeyRequest
        from fastapi import HTTPException

        body = OpenRouterKeyRequest(api_key="invalid-prefix-key")
        req = _mock_request()
        with pytest.raises(HTTPException) as exc:
            await _auth.set_openrouter_key(body=body, request=req, user=user, session=db_session)
        assert exc.value.status_code == 400
        assert "sk-or-v1-" in exc.value.detail

        body = OpenRouterKeyRequest(api_key="sk-or-v1-short")
        req = _mock_request()
        with pytest.raises(HTTPException) as exc:
            await _auth.set_openrouter_key(body=body, request=req, user=user, session=db_session)
        assert exc.value.status_code == 400
        assert "too short" in exc.value.detail.lower()

    @pytest.mark.asyncio
    async def test_set_brave_key_too_short(self, db_session):
        """Line 470: brave key too short."""
        user = await _make_real_user(db_session, username="dbraveshort")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from workbench.api.routes.auth import BraveKeyRequest
        from fastapi import HTTPException
        body = BraveKeyRequest(api_key="short")
        req = _mock_request()
        with pytest.raises(HTTPException) as exc:
            await _auth.set_brave_key(body=body, request=req, user=user, session=db_session)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_api_key_invalid_uuid(self, db_session):
        """Lines 553–554: invalid UUID format."""
        user = await _make_real_user(db_session, username="ddakuuid")
        import importlib
        import workbench.api.routes.auth as _auth
        _auth = importlib.reload(_auth)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await _auth.delete_api_key(key_id="not-a-uuid", user=user, session=db_session)
        assert exc.value.status_code == 422
