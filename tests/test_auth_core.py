"""Tests for core.auth — password hashing, token management, session auth, brave keys."""

import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.auth import (
    _hash_token,
    _auth_via_api_key,
    _auth_via_cookie,
    consume_token,
    create_session,
    delete_user_sessions,
    generate_api_key,
    generate_session_token,
    generate_token,
    get_current_user,
    get_user_brave_key,
    hash_password,
    set_user_brave_key,
    verify_password,
)
from workbench.core.models import User, UserApiKey, UserBraveKey, UserInvite, UserSession


# ---- hash_password / verify_password ----


def test_hash_password_returns_bcrypt_hash():
    result = hash_password("secret123")
    assert isinstance(result, str)
    assert result.startswith("$2b$")


def test_verify_password_correct():
    hashed = hash_password("mypassword")
    assert verify_password("mypassword", hashed) is True


def test_verify_password_wrong():
    hashed = hash_password("mypassword")
    assert verify_password("wrongpassword", hashed) is False


# ---- generate_token / generate_session_token ----


def test_generate_token_returns_tuple():
    raw, hashed = generate_token()
    assert isinstance(raw, str)
    assert isinstance(hashed, str)
    assert len(raw) > 10
    assert hashed == hashlib.sha256(raw.encode()).hexdigest()


def test_generate_session_token_returns_tuple():
    raw, hashed = generate_session_token()
    assert isinstance(raw, str)
    assert isinstance(hashed, str)
    assert hashed == _hash_token(raw)


def test_hash_token_deterministic():
    result = _hash_token("test-token")
    assert result == hashlib.sha256(b"test-token").hexdigest()


# ---- consume_token ----


@pytest.mark.asyncio
async def test_consume_token_valid(db_session, setup_encryption):
    user = User(id=uuid4(), username="tokenuser")
    db_session.add(user)
    await db_session.flush()

    raw, token_hash = generate_token()
    expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
    invite = UserInvite(
        email="test@example.com",
        username="tokenuser",
        token_hash=token_hash,
        invited_by=user.id,
        expires_at=expires,
    )
    db_session.add(invite)
    await db_session.commit()

    result = await consume_token(token_hash, db_session, UserInvite)
    assert result is not None
    assert result.token_hash == token_hash


@pytest.mark.asyncio
async def test_consume_token_expired(db_session, setup_encryption):
    user = User(id=uuid4(), username="expireduser")
    db_session.add(user)
    await db_session.flush()

    raw, token_hash = generate_token()
    expires = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    invite = UserInvite(
        email="expired@example.com",
        username="expireduser",
        token_hash=token_hash,
        invited_by=user.id,
        expires_at=expires,
    )
    db_session.add(invite)
    await db_session.commit()

    result = await consume_token(token_hash, db_session, UserInvite)
    assert result is None


@pytest.mark.asyncio
async def test_consume_token_not_found(db_session, setup_encryption):
    result = await consume_token("nonexistent", db_session, UserInvite)
    assert result is None


# ---- create_session / delete_user_sessions ----


@pytest.mark.asyncio
async def test_create_session(db_session, setup_encryption):
    user = User(id=uuid4(), username="sessionuser")
    db_session.add(user)
    await db_session.commit()

    raw_token = await create_session(user, db_session, hours=24)
    assert isinstance(raw_token, str)
    assert len(raw_token) > 10

    # Verify session exists in DB
    token_hash = _hash_token(raw_token)
    result = await db_session.execute(
        select(UserSession).where(UserSession.token_hash == token_hash)
    )
    session_row = result.scalar_one_or_none()
    assert session_row is not None
    assert session_row.user_id == user.id


@pytest.mark.asyncio
async def test_create_session_custom_hours(db_session, setup_encryption):
    user = User(id=uuid4(), username="houruser")
    db_session.add(user)
    await db_session.commit()

    raw_token = await create_session(user, db_session, hours=48)
    token_hash = _hash_token(raw_token)
    result = await db_session.execute(
        select(UserSession).where(UserSession.token_hash == token_hash)
    )
    session_row = result.scalar_one()
    assert session_row is not None


@pytest.mark.asyncio
async def test_delete_user_sessions(db_session, setup_encryption):
    user = User(id=uuid4(), username="deluser")
    db_session.add(user)
    await db_session.commit()

    await create_session(user, db_session, hours=24)
    await create_session(user, db_session, hours=24)

    await delete_user_sessions(user, db_session)

    result = await db_session.execute(
        select(UserSession).where(UserSession.user_id == user.id)
    )
    assert result.scalars().all() == []


# ---- get_user_brave_key / set_user_brave_key ----


@pytest.mark.asyncio
async def test_set_and_get_brave_key(db_session, setup_encryption):
    user = User(id=uuid4(), username="braveuser")
    db_session.add(user)
    await db_session.commit()

    await set_user_brave_key(user, "bsk-test123", db_session)
    result = await get_user_brave_key(user, db_session)
    assert result == "bsk-test123"


@pytest.mark.asyncio
async def test_get_brave_key_none(db_session, setup_encryption):
    user = User(id=uuid4(), username="nobraveuser")
    db_session.add(user)
    await db_session.commit()

    result = await get_user_brave_key(user, db_session)
    assert result is None


@pytest.mark.asyncio
async def test_set_brave_key_updates_existing(db_session, setup_encryption):
    user = User(id=uuid4(), username="braveupdateuser")
    db_session.add(user)
    await db_session.commit()

    await set_user_brave_key(user, "bsk-old", db_session)
    await set_user_brave_key(user, "bsk-new", db_session)
    result = await get_user_brave_key(user, db_session)
    assert result == "bsk-new"


# ---- _auth_via_cookie ----


@pytest.mark.asyncio
async def test_auth_via_cookie_valid(db_session, setup_encryption):
    user = User(id=uuid4(), username="cookieuser")
    db_session.add(user)
    await db_session.commit()

    raw_token = await create_session(user, db_session, hours=24)
    result = await _auth_via_cookie(raw_token, db_session)
    assert result is not None
    assert result.id == user.id


@pytest.mark.asyncio
async def test_auth_via_cookie_invalid(db_session, setup_encryption):
    result = await _auth_via_cookie("invalid-token", db_session)
    assert result is None


# ---- _auth_via_api_key ----


@pytest.mark.asyncio
async def test_auth_via_api_key_valid(db_session, setup_encryption):
    user = User(id=uuid4(), username="apikeyuser")
    db_session.add(user)
    await db_session.flush()

    raw_key, hashed, lookup = generate_api_key()
    api_key = UserApiKey(user_id=user.id, key_hash=hashed, key_lookup=lookup, label="test")
    db_session.add(api_key)
    await db_session.commit()

    result = await _auth_via_api_key(raw_key, db_session)
    assert result is not None
    assert result.id == user.id


@pytest.mark.asyncio
async def test_auth_via_api_key_invalid(db_session, setup_encryption):
    result = await _auth_via_api_key("wb-invalid-key", db_session)
    assert result is None


@pytest.mark.asyncio
async def test_auth_via_api_key_expired(db_session, setup_encryption):
    user = User(id=uuid4(), username="expiredkeyuser")
    db_session.add(user)
    await db_session.flush()

    raw_key, hashed, lookup = generate_api_key()
    expired = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    api_key = UserApiKey(
        user_id=user.id, key_hash=hashed, key_lookup=lookup,
        label="expired", expires_at=expired,
    )
    db_session.add(api_key)
    await db_session.commit()

    result = await _auth_via_api_key(raw_key, db_session)
    assert result is None


# ---- get_current_user ----


@pytest.mark.asyncio
async def test_get_current_user_via_cookie(db_session, setup_encryption):
    user = User(id=uuid4(), username="gcuser")
    db_session.add(user)
    await db_session.commit()

    raw_token = await create_session(user, db_session, hours=24)

    request = MagicMock()
    request.cookies.get.return_value = raw_token

    result = await get_current_user(request, None, db_session)
    assert result.id == user.id


@pytest.mark.asyncio
async def test_get_current_user_via_api_key(db_session, setup_encryption):
    user = User(id=uuid4(), username="gcapiuser")
    db_session.add(user)
    await db_session.flush()

    raw_key, hashed, lookup = generate_api_key()
    api_key = UserApiKey(user_id=user.id, key_hash=hashed, key_lookup=lookup, label="test")
    db_session.add(api_key)
    await db_session.commit()

    request = MagicMock()
    request.cookies.get.return_value = None

    credentials = MagicMock()
    credentials.credentials = raw_key

    result = await get_current_user(request, credentials, db_session)
    assert result.id == user.id


@pytest.mark.asyncio
async def test_get_current_user_no_auth_raises(db_session, setup_encryption):
    request = MagicMock()
    request.cookies.get.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(request, None, db_session)
    assert exc_info.value.status_code == 401
