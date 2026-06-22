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
    get_user_inference_api_key,
    get_user_inference_config,
    get_user_llm_client,
    get_user_openrouter_key,
    hash_password,
    set_user_brave_key,
    set_user_inference_config,
    set_user_openrouter_key,
    verify_api_key,
    verify_password,
)
from workbench.core.models import (
    User,
    UserApiKey,
    UserBraveKey,
    UserInferenceConfig,
    UserInvite,
    UserOpenRouterKey,
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


# ---- get_user_openrouter_key / set_user_openrouter_key (lines 183-204) ----


@pytest.mark.asyncio
async def test_set_and_get_openrouter_key(db_session, setup_encryption):
    user = User(id=uuid4(), username="orkeyuser")
    db_session.add(user)
    await db_session.commit()

    await set_user_openrouter_key(user, "sk-or-test", db_session)
    result = await get_user_openrouter_key(user, db_session)
    assert result == "sk-or-test"


@pytest.mark.asyncio
async def test_get_openrouter_key_none(db_session, setup_encryption):
    user = User(id=uuid4(), username="noorkeyuser")
    db_session.add(user)
    await db_session.commit()

    result = await get_user_openrouter_key(user, db_session)
    assert result is None


@pytest.mark.asyncio
async def test_set_openrouter_key_updates_existing(db_session, setup_encryption):
    user = User(id=uuid4(), username="orkeyupdateuser")
    db_session.add(user)
    await db_session.commit()

    await set_user_openrouter_key(user, "sk-old", db_session)
    await set_user_openrouter_key(user, "sk-new", db_session)
    result = await get_user_openrouter_key(user, db_session)
    assert result == "sk-new"


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


# ---- get_user_inference_config (lines 237-256) ----


@pytest.mark.asyncio
async def test_get_user_inference_config_no_row(db_session, setup_encryption):
    """No UserInferenceConfig row -> system defaults returned."""
    from workbench.core.config import WorkbenchConfig

    user = User(id=uuid4(), username="infodefault")
    db_session.add(user)
    await db_session.commit()

    config = WorkbenchConfig()
    result = await get_user_inference_config(user, db_session, config)
    assert result["provider_url"] == config.inference_provider_url
    assert result["strong_model"] == config.inference_strong_model
    assert result["quick_model"] == config.inference_quick_model
    assert result["medium_model"] == config.inference_medium_model
    assert result["requests_per_minute"] == config.inference_requests_per_minute
    assert result["has_api_key"] is False


@pytest.mark.asyncio
async def test_get_user_inference_config_no_config_arg_loads_config(db_session, setup_encryption, monkeypatch):
    """No config arg and no DB row -> calls load_config() internally (lines 239-240)."""
    from unittest.mock import patch
    from workbench.core.config import WorkbenchConfig

    user = User(id=uuid4(), username="infoconfigfallback")
    db_session.add(user)
    await db_session.commit()

    dummy_config = WorkbenchConfig(inference_provider_url="https://fallback.test")
    with patch("workbench.core.config.load_config", return_value=dummy_config):
        result = await get_user_inference_config(user, db_session)

    assert result["provider_url"] == "https://fallback.test"
    assert result["has_api_key"] is False


@pytest.mark.asyncio
async def test_get_user_inference_config_with_row(db_session, setup_encryption):
    """UserInferenceConfig row exists -> row values returned and has_api_key reflects api_key."""
    from workbench.core import encryption

    user = User(id=uuid4(), username="infocustom")
    db_session.add(user)
    await db_session.flush()

    cfg_row = UserInferenceConfig(
        user_id=user.id,
        provider_url="https://custom.example.com",
        strong_model="custom-model",
        quick_model="custom-quick",
        medium_model="custom-medium",
        requests_per_minute=15,
        api_key=encryption.encrypt("sk-test-key"),
    )
    db_session.add(cfg_row)
    await db_session.commit()

    result = await get_user_inference_config(user, db_session)
    assert result["provider_url"] == "https://custom.example.com"
    assert result["strong_model"] == "custom-model"
    assert result["quick_model"] == "custom-quick"
    assert result["medium_model"] == "custom-medium"
    assert result["requests_per_minute"] == 15
    assert result["has_api_key"] is True


# ---- get_user_inference_api_key (lines 261-267) ----


@pytest.mark.asyncio
async def test_get_user_inference_api_key_from_config(db_session, setup_encryption):
    """UserInferenceConfig with api_key -> decrypts and returns it."""
    from workbench.core import encryption

    user = User(id=uuid4(), username="infokeycfg")
    db_session.add(user)
    await db_session.flush()

    encrypted = encryption.encrypt("sk-inference-key")
    cfg_row = UserInferenceConfig(user_id=user.id, api_key=encrypted)
    db_session.add(cfg_row)
    await db_session.commit()

    result = await get_user_inference_api_key(user, db_session)
    assert result == "sk-inference-key"


@pytest.mark.asyncio
async def test_get_user_inference_api_key_fallback(db_session, setup_encryption):
    """No UserInferenceConfig -> falls back to UserOpenRouterKey."""
    from workbench.core import encryption

    user = User(id=uuid4(), username="infofallback")
    db_session.add(user)
    await db_session.flush()

    or_key = UserOpenRouterKey(
        user_id=user.id, encrypted_key=encryption.encrypt("sk-or-key")
    )
    db_session.add(or_key)
    await db_session.commit()

    result = await get_user_inference_api_key(user, db_session)
    assert result == "sk-or-key"


# ---- set_user_inference_config (lines 282-304) ----


@pytest.mark.asyncio
async def test_set_user_inference_config_create(db_session, setup_encryption):
    """No existing row -> creates one."""
    user = User(id=uuid4(), username="setcreate")
    db_session.add(user)
    await db_session.commit()

    await set_user_inference_config(
        user, db_session, api_key="sk-new", provider_url="https://test.example.com",
    )

    result = await db_session.execute(
        select(UserInferenceConfig).where(UserInferenceConfig.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    assert row is not None
    assert row.provider_url == "https://test.example.com"


@pytest.mark.asyncio
async def test_set_user_inference_config_update(db_session, setup_encryption):
    """Existing row -> updates specified fields."""
    from workbench.core import encryption

    user = User(id=uuid4(), username="setupd")
    db_session.add(user)
    await db_session.flush()

    cfg_row = UserInferenceConfig(
        user_id=user.id,
        provider_url="https://old.example.com",
        api_key=encryption.encrypt("sk-old"),
    )
    db_session.add(cfg_row)
    await db_session.commit()

    await set_user_inference_config(
        user, db_session, provider_url="https://new.example.com", strong_model="new-model",
    )

    await db_session.refresh(cfg_row)
    assert cfg_row.provider_url == "https://new.example.com"
    assert cfg_row.strong_model == "new-model"
    # Unchanged fields stay intact
    assert cfg_row.api_key is not None


@pytest.mark.asyncio
async def test_set_user_inference_config_clear_api_key(db_session, setup_encryption):
    """Passing api_key='' clears the encrypted api_key."""
    from workbench.core import encryption

    user = User(id=uuid4(), username="setclear")
    db_session.add(user)
    await db_session.flush()

    cfg_row = UserInferenceConfig(
        user_id=user.id,
        api_key=encryption.encrypt("sk-old"),
        provider_url="https://test.example.com",
        strong_model="m",
    )
    db_session.add(cfg_row)
    await db_session.commit()

    await set_user_inference_config(user, db_session, api_key="")

    await db_session.refresh(cfg_row)
    assert cfg_row.api_key is None
    assert cfg_row.provider_url == "https://test.example.com"  # unchanged


@pytest.mark.asyncio
async def test_set_user_inference_config_partial_update(db_session, setup_encryption):
    """Only provider_url passed -> other fields unchanged."""
    from workbench.core import encryption

    user = User(id=uuid4(), username="setpartial")
    db_session.add(user)
    await db_session.flush()

    cfg_row = UserInferenceConfig(
        user_id=user.id,
        api_key=encryption.encrypt("sk-original"),
        provider_url="https://original.example.com",
        strong_model="original-model",
        quick_model="quick-model",
        medium_model="medium-model",
        requests_per_minute=10,
    )
    db_session.add(cfg_row)
    await db_session.commit()

    await set_user_inference_config(user, db_session, provider_url="https://updated.example.com")

    await db_session.refresh(cfg_row)
    assert cfg_row.provider_url == "https://updated.example.com"
    assert cfg_row.strong_model == "original-model"  # unchanged
    assert cfg_row.quick_model == "quick-model"  # unchanged
    assert cfg_row.medium_model == "medium-model"  # unchanged
    assert cfg_row.requests_per_minute == 10  # unchanged
    assert cfg_row.api_key is not None  # unchanged (api_key=None means skip)


@pytest.mark.asyncio
async def test_set_user_inference_config_all_fields(db_session, setup_encryption):
    """Set quick_model, medium_model, and requests_per_minute explicitly (lines 298, 300, 302)."""
    user = User(id=uuid4(), username="setallfields")
    db_session.add(user)
    await db_session.commit()

    await set_user_inference_config(
        user, db_session,
        quick_model="q-model",
        medium_model="m-model",
        requests_per_minute=20,
    )

    result = await db_session.execute(
        select(UserInferenceConfig).where(UserInferenceConfig.user_id == user.id)
    )
    row = result.scalar_one()
    assert row.quick_model == "q-model"
    assert row.medium_model == "m-model"
    assert row.requests_per_minute == 20


# ---- get_user_llm_client (lines 318-331) ----


@pytest.mark.asyncio
async def test_get_user_llm_client_success(db_session, setup_encryption):
    """Mocked OpenRouterClient is constructed with correct arguments."""
    from unittest.mock import MagicMock, patch

    user = User(id=uuid4(), username="llmclient")
    db_session.add(user)
    await db_session.flush()

    from workbench.core import encryption

    cfg_row = UserInferenceConfig(
        user_id=user.id,
        provider_url="https://api.example.com",
        strong_model="strong-model",
        requests_per_minute=30,
        api_key=encryption.encrypt("sk-llm-key"),
    )
    db_session.add(cfg_row)
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
