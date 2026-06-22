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
    create_inference_provider,
    delete_inference_provider,
    delete_user_sessions,
    generate_api_key,
    generate_session_token,
    generate_token,
    get_current_user,
    get_user_brave_key,
    get_user_inference_api_key,
    get_user_inference_providers,
    get_user_llm_client,
    hash_password,
    set_user_brave_key,
    update_inference_provider,
    verify_api_key,
    verify_password,
)
from workbench.core.models import (
    User,
    UserApiKey,
    UserBraveKey,
    UserInferenceProvider,
    UserInvite,
    UserSession,
)


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


# ---- _auth_via_cookie bcrypt fallback (lines 129-131) ----


@pytest.mark.asyncio
async def test_auth_via_cookie_bcrypt_fallback(db_session, setup_encryption):
    """Cookie auth falls back to bcrypt-verify scan when SHA-256 lookup fails."""
    user = User(id=uuid4(), username="cookiebcrypt")
    db_session.add(user)
    await db_session.commit()

    # Build a raw token + bcrypt hash (like generate_api_key does), store it as a session
    raw_key, bcrypt_hashed, _ = generate_api_key()
    expires = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=24)
    session_row = UserSession(user_id=user.id, token_hash=bcrypt_hashed, expires_at=expires)
    db_session.add(session_row)
    await db_session.commit()

    result = await _auth_via_cookie(raw_key, db_session)
    assert result is not None
    assert result.id == user.id


# ---- _auth_via_api_key: user not found after lookup (line 149) ----


@pytest.mark.asyncio
async def test_auth_via_api_key_user_not_found(db_session, setup_encryption):
    """Direct lookup finds a UserApiKey whose user_id doesn't match any User -> 401."""
    raw_key, hashed, lookup = generate_api_key()
    api_key = UserApiKey(
        user_id=uuid4(),  # non-existent user
        key_hash=hashed,
        key_lookup=lookup,
        label="orphan",
    )
    db_session.add(api_key)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await _auth_via_api_key(raw_key, db_session)
    assert exc_info.value.status_code == 401


# ---- _auth_via_api_key: full-scan fallback (lines 154-162) ----


@pytest.mark.asyncio
async def test_auth_via_api_key_full_scan_fallback(db_session, setup_encryption):
    """API key with no key_lookup triggers full-scan bcrypt fallback."""
    user = User(id=uuid4(), username="fullscan")
    db_session.add(user)
    await db_session.flush()

    raw_key, hashed, _ = generate_api_key()
    api_key = UserApiKey(
        user_id=user.id, key_hash=hashed, key_lookup=None, label="fullscan",
    )
    db_session.add(api_key)
    await db_session.commit()

    result = await _auth_via_api_key(raw_key, db_session)
    assert result is not None
    assert result.id == user.id


@pytest.mark.asyncio
async def test_auth_via_api_key_full_scan_expired_skip(db_session, setup_encryption):
    """Full-scan skips expired keys and authenticates against a valid one."""
    user = User(id=uuid4(), username="fullscanexp")
    db_session.add(user)
    await db_session.flush()

    raw_key, hashed, _ = generate_api_key()
    non_matching_lookup = _hash_token("some-other-token")
    expired = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)

    # Expired key — will be skipped
    key1 = UserApiKey(
        user_id=user.id, key_hash=hashed, key_lookup=non_matching_lookup,
        label="expired", expires_at=expired,
    )
    db_session.add(key1)
    # Valid key
    key2 = UserApiKey(
        user_id=user.id, key_hash=hashed, key_lookup=non_matching_lookup,
        label="valid",
    )
    db_session.add(key2)
    await db_session.commit()

    result = await _auth_via_api_key(raw_key, db_session)
    assert result is not None
    assert result.id == user.id


@pytest.mark.asyncio
async def test_auth_via_api_key_full_scan_user_not_found(db_session, setup_encryption):
    """Full-scan finds a key whose user_id does not exist -> 401."""
    raw_key, hashed, _ = generate_api_key()
    non_matching_lookup = _hash_token("some-other-token")
    api_key = UserApiKey(
        user_id=uuid4(), key_hash=hashed, key_lookup=non_matching_lookup,
        label="orphan",
    )
    db_session.add(api_key)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await _auth_via_api_key(raw_key, db_session)
    assert exc_info.value.status_code == 401


# ---- get_user_inference_providers ----


@pytest.mark.asyncio
async def test_get_user_inference_providers_no_rows(db_session, setup_encryption):
    """No UserInferenceProvider rows -> system defaults returned as single-item list."""
    from workbench.core.config import WorkbenchConfig

    user = User(id=uuid4(), username="infodefault")
    db_session.add(user)
    await db_session.commit()

    config = WorkbenchConfig()
    result = await get_user_inference_providers(user, db_session, config)
    assert len(result) == 1
    assert result[0]["id"] is None
    assert result[0]["is_default"] is True
    assert result[0]["provider_url"] == config.inference_provider_url
    assert result[0]["strong_model"] == config.inference_strong_model
    assert result[0]["quick_model"] == config.inference_quick_model
    assert result[0]["requests_per_minute"] == config.inference_requests_per_minute
    assert result[0]["has_api_key"] is False


@pytest.mark.asyncio
async def test_get_user_inference_providers_no_config_arg(db_session, setup_encryption):
    """No config arg and no DB row -> calls load_config() internally."""
    from unittest.mock import patch
    from workbench.core.config import WorkbenchConfig

    user = User(id=uuid4(), username="infoconfigfallback")
    db_session.add(user)
    await db_session.commit()

    dummy_config = WorkbenchConfig(inference_provider_url="https://fallback.test")
    with patch("workbench.core.config.load_config", return_value=dummy_config):
        result = await get_user_inference_providers(user, db_session)

    assert len(result) == 1
    assert result[0]["provider_url"] == "https://fallback.test"
    assert result[0]["has_api_key"] is False


@pytest.mark.asyncio
async def test_get_user_inference_providers_with_rows(db_session, setup_encryption):
    """UserInferenceProvider rows exist -> row values returned."""
    from workbench.core import encryption

    user = User(id=uuid4(), username="infocustom")
    db_session.add(user)
    await db_session.flush()

    provider = UserInferenceProvider(
        user_id=user.id,
        name="Test",
        provider_url="https://custom.example.com",
        strong_model="custom-model",
        quick_model="custom-quick",
        requests_per_minute=15,
        api_key=encryption.encrypt("sk-test-key"),
        is_default=True,
    )
    db_session.add(provider)
    await db_session.commit()

    result = await get_user_inference_providers(user, db_session)
    assert len(result) == 1
    assert result[0]["id"] == str(provider.id)
    assert result[0]["name"] == "Test"
    assert result[0]["provider_url"] == "https://custom.example.com"
    assert result[0]["strong_model"] == "custom-model"
    assert result[0]["quick_model"] == "custom-quick"
    assert result[0]["requests_per_minute"] == 15
    assert result[0]["is_default"] is True
    assert result[0]["has_api_key"] is True


# ---- get_user_inference_api_key ----


@pytest.mark.asyncio
async def test_get_user_inference_api_key_from_provider(db_session, setup_encryption):
    """UserInferenceProvider with api_key -> decrypts and returns it."""
    from workbench.core import encryption

    user = User(id=uuid4(), username="infokeycfg")
    db_session.add(user)
    await db_session.flush()

    encrypted = encryption.encrypt("sk-inference-key")
    provider = UserInferenceProvider(
        user_id=user.id,
        name="Test",
        api_key=encrypted,
        is_default=True,
    )
    db_session.add(provider)
    await db_session.commit()

    result = await get_user_inference_api_key(user, db_session)
    assert result == "sk-inference-key"


# ---- create_inference_provider ----


@pytest.mark.asyncio
async def test_create_inference_provider(db_session, setup_encryption):
    """Creates a new UserInferenceProvider row."""
    user = User(id=uuid4(), username="createprov")
    db_session.add(user)
    await db_session.commit()

    provider = await create_inference_provider(
        user, db_session, name="Test", provider_url="https://test.example.com",
    )

    assert provider.name == "Test"
    assert provider.provider_url == "https://test.example.com"

    result = await db_session.execute(
        select(UserInferenceProvider).where(UserInferenceProvider.user_id == user.id)
    )
    row = result.scalar_one()
    assert row.name == "Test"
    assert row.provider_url == "https://test.example.com"


# ---- update_inference_provider ----


@pytest.mark.asyncio
async def test_update_inference_provider(db_session, setup_encryption):
    """Update specific fields on an existing provider."""
    user = User(id=uuid4(), username="updateprov")
    db_session.add(user)
    await db_session.flush()

    provider = UserInferenceProvider(
        user_id=user.id,
        name="Old",
        provider_url="https://old.example.com",
    )
    db_session.add(provider)
    await db_session.commit()

    updated = await update_inference_provider(
        user, db_session, str(provider.id), provider_url="https://updated.example.com",
    )
    assert updated is not None
    assert updated.provider_url == "https://updated.example.com"
    # Unchanged fields stay intact
    assert updated.name == "Old"


@pytest.mark.asyncio
async def test_update_inference_provider_partial(db_session, setup_encryption):
    """Only provider_url passed -> other fields unchanged."""
    user = User(id=uuid4(), username="updatepart")
    db_session.add(user)
    await db_session.flush()

    from workbench.core import encryption

    provider = UserInferenceProvider(
        user_id=user.id,
        name="Original",
        api_key=encryption.encrypt("sk-original"),
        provider_url="https://original.example.com",
        strong_model="original-model",
        quick_model="quick-model",
        requests_per_minute=10,
    )
    db_session.add(provider)
    await db_session.commit()

    updated = await update_inference_provider(
        user, db_session, str(provider.id), provider_url="https://updated.example.com",
    )
    assert updated is not None
    assert updated.provider_url == "https://updated.example.com"
    assert updated.name == "Original"  # unchanged
    assert updated.strong_model == "original-model"  # unchanged
    assert updated.quick_model == "quick-model"  # unchanged
    assert updated.requests_per_minute == 10  # unchanged
    assert updated.api_key is not None  # unchanged


# ---- delete_inference_provider ----


@pytest.mark.asyncio
async def test_delete_inference_provider(db_session, setup_encryption):
    """Delete an existing provider row."""
    user = User(id=uuid4(), username="delprov")
    db_session.add(user)
    await db_session.flush()

    provider = UserInferenceProvider(
        user_id=user.id,
        name="ToDelete",
        provider_url="https://delete.example.com",
    )
    db_session.add(provider)
    await db_session.commit()

    result = await delete_inference_provider(user, db_session, str(provider.id))
    assert result is True

    db_row = await db_session.execute(
        select(UserInferenceProvider).where(UserInferenceProvider.id == provider.id)
    )
    assert db_row.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_delete_inference_provider_not_found(db_session, setup_encryption):
    """Delete a non-existent provider returns False."""
    user = User(id=uuid4(), username="delprovnf")
    db_session.add(user)
    await db_session.commit()

    result = await delete_inference_provider(user, db_session, str(uuid4()))
    assert result is False


# ---- get_user_llm_client (lines 318-331) ----


@pytest.mark.asyncio
async def test_get_user_llm_client_success(db_session, setup_encryption):
    """Mocked OpenRouterClient is constructed with correct arguments."""
    from unittest.mock import MagicMock, patch

    user = User(id=uuid4(), username="llmclient")
    db_session.add(user)
    await db_session.flush()

    from workbench.core import encryption

    provider = UserInferenceProvider(
        user_id=user.id,
        name="Test",
        provider_url="https://api.example.com",
        strong_model="strong-model",
        requests_per_minute=30,
        api_key=encryption.encrypt("sk-llm-key"),
        is_default=True,
    )
    db_session.add(provider)
    await db_session.commit()

    with patch("workbench.shared.llm.router.OpenRouterClient") as MockClient:
        mock_instance = MagicMock()
        MockClient.return_value = mock_instance
        result = await get_user_llm_client(user, db_session)
        assert result is mock_instance
        MockClient.assert_called_once_with(
            api_key="sk-llm-key",
            base_url="https://api.example.com",
            default_model="strong-model",
            rate_limit_user_id=str(user.id),
            rate_limit_rpm=30,
        )


@pytest.mark.asyncio
async def test_get_user_llm_client_no_key_raises(db_session, setup_encryption):
    """No inference API key available -> RuntimeError."""
    user = User(id=uuid4(), username="llmnokey")
    db_session.add(user)
    await db_session.commit()

    from workbench.core.config import WorkbenchConfig

    config = WorkbenchConfig()
    with pytest.raises(RuntimeError, match="No inference API key configured"):
        await get_user_llm_client(user, db_session, config)
