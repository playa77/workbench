"""API key + session cookie authentication."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, TypeVar

import bcrypt
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core import encryption
from workbench.core.db import get_session
from workbench.core.models import (
    User,
    UserApiKey,
    UserBraveKey,
    UserInferenceProvider,
    UserInvite,
    UserSession,
    ServerConfig,
)

if TYPE_CHECKING:
    from workbench.core.config import WorkbenchConfig
    from workbench.shared.llm.router import OpenRouterClient

_T = TypeVar("_T")

security_scheme = HTTPBearer(auto_error=False)

_SESSION_COOKIE = "workbench_session"


def generate_api_key(prefix: str = "wb", expiry_days: int | None = None) -> tuple[str, str, str, str]:
    raw = f"{prefix}-{secrets.token_urlsafe(32)}"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    lookup = _hash_token(raw)
    masked = mask_api_key(raw)
    return raw, hashed, lookup, masked


def mask_api_key(raw: str) -> str:
    """Mask an API key for display: show first 6 chars (incl. prefix) and last 3 chars."""
    if len(raw) <= 9:
        return raw
    return raw[:6] + "..." + raw[-3:]


def _bcrypt_verify(raw: str, hashed: str) -> bool:
    """Compare a raw value against a bcrypt hash.

    Returns False (instead of raising) when the hash is not a valid bcrypt
    digest (e.g. a SHA-256 token stored prior to the bcrypt 5.0.0 upgrade).
    """
    try:
        return bcrypt.checkpw(raw.encode(), hashed.encode())
    except ValueError:
        return False


def verify_api_key(raw_key: str, hashed: str) -> bool:
    """Compare a raw API token against its stored hash."""
    return _bcrypt_verify(raw_key, hashed)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return _bcrypt_verify(password, hashed)


def generate_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    hashed = _hash_token(raw)
    return raw, hashed


async def consume_token(
    token_hash: str,
    session: AsyncSession,
    model_cls: type[_T],
    token_field: str = "token_hash",
    expiry_field: str | None = "expires_at",
) -> _T | None:
    now = datetime.now(UTC).replace(tzinfo=None)
    conditions = [getattr(model_cls, token_field) == token_hash]
    if expiry_field and hasattr(model_cls, expiry_field):
        conditions.append(getattr(model_cls, expiry_field) > now)
    result = await session.execute(select(model_cls).where(*conditions))
    return result.scalar_one_or_none()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_session_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    hashed = _hash_token(raw)
    return raw, hashed


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    cookie_token = request.cookies.get(_SESSION_COOKIE)
    if cookie_token:
        user = await _auth_via_cookie(cookie_token, session)
        if user is not None:
            return user

    if credentials is not None and credentials.credentials.startswith("wb-"):
        user = await _auth_via_api_key(credentials.credentials, session)
        if user is not None:
            return user

    raise HTTPException(
        status_code=401,
        detail="Authentication required — provide a valid API key or session cookie",
    )


async def _auth_via_cookie(token: str, session: AsyncSession) -> User | None:
    now = datetime.now(UTC).replace(tzinfo=None)
    token_hash = _hash_token(token)
    result = await session.execute(
        select(UserSession).where(
            UserSession.token_hash == token_hash,
            UserSession.expires_at > now,
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        user = await session.get(User, row.user_id)
        return user

    result = await session.execute(
        select(UserSession).where(UserSession.expires_at > now)
    )
    for row in result.scalars().all():
        if verify_api_key(token, row.token_hash):
            user = await session.get(User, row.user_id)
            return user
    return None


async def _auth_via_api_key(raw_key: str, session: AsyncSession) -> User | None:
    lookup = _hash_token(raw_key)
    result = await session.execute(
        select(UserApiKey).where(UserApiKey.key_lookup == lookup)
    )
    key_row = result.scalar_one_or_none()
    if key_row is not None:
        if verify_api_key(raw_key, key_row.key_hash):
            if key_row.expires_at is not None and key_row.expires_at < datetime.now(UTC).replace(tzinfo=None):
                return None
            key_row.last_used_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()
            user = await session.get(User, key_row.user_id)
            if user is None:
                raise HTTPException(status_code=401, detail="User not found")
            return user

    keys_result = await session.execute(select(UserApiKey))
    for key_row in keys_result.scalars().all():
        if verify_api_key(raw_key, key_row.key_hash):
            if key_row.expires_at is not None and key_row.expires_at < datetime.now(UTC).replace(tzinfo=None):
                continue
            key_row.last_used_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()
            user = await session.get(User, key_row.user_id)
            if user is None:
                raise HTTPException(status_code=401, detail="User not found")
            return user
    return None


async def create_session(user: User, session: AsyncSession, hours: int = 24) -> str:
    raw, hashed = generate_session_token()
    expires = (datetime.now(UTC) + timedelta(hours=hours)).replace(tzinfo=None)
    session.add(UserSession(user_id=user.id, token_hash=hashed, expires_at=expires))
    await session.commit()
    return raw


async def delete_user_sessions(user: User, session: AsyncSession) -> None:
    result = await session.execute(
        select(UserSession).where(UserSession.user_id == user.id)
    )
    for row in result.scalars().all():
        await session.delete(row)
    await session.commit()


async def get_user_brave_key(user: User, session: AsyncSession) -> str | None:
    result = await session.execute(
        select(UserBraveKey).where(UserBraveKey.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return encryption.decrypt(row.encrypted_key)


async def get_user_brave_key_info(user: User, session: AsyncSession) -> tuple[bool, str | None]:
    """Returns (has_key, masked_key) for the user's Brave Search API key."""
    result = await session.execute(
        select(UserBraveKey).where(UserBraveKey.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return False, None
    return True, row.masked_key


async def set_user_brave_key(user: User, api_key: str, session: AsyncSession) -> None:
    encrypted = encryption.encrypt(api_key)
    masked = mask_api_key(api_key)
    result = await session.execute(
        select(UserBraveKey).where(UserBraveKey.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        row.encrypted_key = encrypted
        row.masked_key = masked
    else:
        session.add(UserBraveKey(user_id=user.id, encrypted_key=encrypted, masked_key=masked))
    await session.commit()


async def get_user_inference_providers(
    user: User, session: AsyncSession, config: "WorkbenchConfig | None" = None
) -> list[dict]:
    """Get all inference providers for user, with system defaults if none configured."""
    result = await session.execute(
        select(UserInferenceProvider).where(UserInferenceProvider.user_id == user.id)
        .order_by(UserInferenceProvider.is_default.desc(), UserInferenceProvider.created_at.asc())
    )
    rows = result.scalars().all()
    if not rows:
        if config is None:
            from workbench.core.config import load_config
            config = load_config()
        import os
        return [{
            "id": None,
            "name": "Default",
            "provider_url": config.inference_provider_url,
            "strong_model": config.inference_strong_model,
            "quick_model": config.inference_quick_model,
            "requests_per_minute": config.inference_requests_per_minute,
            "is_default": True,
            "has_api_key": bool(os.environ.get("OPENROUTER_API_KEY")),
            "masked_key": None,
        }]
    return [
        {
            "id": str(row.id),
            "name": row.name,
            "provider_url": row.provider_url,
            "strong_model": row.strong_model,
            "quick_model": row.quick_model,
            "requests_per_minute": row.requests_per_minute,
            "is_default": row.is_default,
            "has_api_key": row.api_key is not None,
            "masked_key": row.api_key_masked,
        }
        for row in rows
    ]


async def get_user_inference_api_key(
    user: User, session: AsyncSession, provider_id: str | None = None
) -> str | None:
    """Get the decrypted inference API key from the user's inference provider.
    
    If provider_id is given, use that specific provider.
    Otherwise, use the user's default provider (is_default=True, first by created_at).
    """
    from uuid import UUID

    if provider_id:
        result = await session.execute(
            select(UserInferenceProvider).where(
                UserInferenceProvider.id == UUID(provider_id),
                UserInferenceProvider.user_id == user.id,
            )
        )
    else:
        result = await session.execute(
            select(UserInferenceProvider).where(
                UserInferenceProvider.user_id == user.id,
                UserInferenceProvider.is_default == True,
            ).order_by(UserInferenceProvider.created_at.asc()).limit(1)
        )
    row = result.scalar_one_or_none()
    if row is not None and row.api_key:
        return encryption.decrypt(row.api_key)
    return None


async def create_inference_provider(
    user: User,
    session: AsyncSession,
    *,
    name: str = "Default",
    api_key: str | None = None,
    provider_url: str = "https://openrouter.ai/api/v1",
    strong_model: str = "deepseek/deepseek-v4-pro",
    quick_model: str = "deepseek/deepseek-v4-flash",
    requests_per_minute: int = 0,
    is_default: bool = False,
) -> UserInferenceProvider:
    """Create a new inference provider for the user."""
    provider = UserInferenceProvider(
        user_id=user.id,
        name=name,
        api_key=encryption.encrypt(api_key) if api_key else None,
        api_key_masked=mask_api_key(api_key) if api_key else None,
        provider_url=provider_url,
        strong_model=strong_model,
        quick_model=quick_model,
        requests_per_minute=requests_per_minute,
        is_default=is_default,
    )
    session.add(provider)
    await session.commit()
    await session.refresh(provider)
    return provider


async def update_inference_provider(
    user: User,
    session: AsyncSession,
    provider_id: str,
    *,
    name: str | None = None,
    api_key: str | None = None,
    provider_url: str | None = None,
    strong_model: str | None = None,
    quick_model: str | None = None,
    requests_per_minute: int | None = None,
    is_default: bool | None = None,
) -> UserInferenceProvider | None:
    """Update an existing inference provider. api_key=None means don't change; empty string means clear."""
    from uuid import UUID
    result = await session.execute(
        select(UserInferenceProvider).where(
            UserInferenceProvider.id == UUID(provider_id),
            UserInferenceProvider.user_id == user.id,
        )
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        return None

    if name is not None:
        provider.name = name
    if api_key is not None:
        provider.api_key = encryption.encrypt(api_key) if len(api_key) > 0 else None
        provider.api_key_masked = mask_api_key(api_key) if len(api_key) > 0 else None
    if provider_url is not None:
        provider.provider_url = provider_url
    if strong_model is not None:
        provider.strong_model = strong_model
    if quick_model is not None:
        provider.quick_model = quick_model
    if requests_per_minute is not None:
        provider.requests_per_minute = requests_per_minute
    if is_default is not None:
        provider.is_default = is_default

    await session.commit()
    await session.refresh(provider)
    return provider


async def delete_inference_provider(
    user: User, session: AsyncSession, provider_id: str
) -> bool:
    """Delete a user's inference provider. Returns True if deleted, False if not found."""
    from uuid import UUID
    result = await session.execute(
        select(UserInferenceProvider).where(
            UserInferenceProvider.id == UUID(provider_id),
            UserInferenceProvider.user_id == user.id,
        )
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        return False
    await session.delete(provider)
    await session.commit()
    return True


async def set_default_inference_provider(
    user: User, session: AsyncSession, provider_id: str
) -> UserInferenceProvider | None:
    """Set a provider as the user's default (clears default on others)."""
    from uuid import UUID

    # Unset all current defaults
    result = await session.execute(
        select(UserInferenceProvider).where(
            UserInferenceProvider.user_id == user.id,
            UserInferenceProvider.is_default == True,
        )
    )
    for p in result.scalars().all():
        p.is_default = False

    # Set new default
    result = await session.execute(
        select(UserInferenceProvider).where(
            UserInferenceProvider.id == UUID(provider_id),
            UserInferenceProvider.user_id == user.id,
        )
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        await session.rollback()
        return None
    provider.is_default = True
    await session.commit()
    await session.refresh(provider)
    return provider


async def get_user_llm_client(
    user: User,
    session: AsyncSession,
    config: "WorkbenchConfig | None" = None,
    *,
    model: str | None = None,
    provider_id: str | None = None,
) -> "OpenRouterClient":
    """Build an LLM client for *user* from their inference provider.

    If *provider_id* is given, use that specific provider.
    Otherwise, use the user's default provider.
    If *model* is provided, it overrides the strong model in the fallback chain.
    """
    from workbench.shared.llm.router import OpenRouterClient

    providers = await get_user_inference_providers(user, session, config)
    if not providers:
        raise RuntimeError("No inference provider configured for this user")

    # Find the target provider
    if provider_id:
        provider = next((p for p in providers if p["id"] == provider_id), None)
        if provider is None:
            raise RuntimeError(f"Inference provider {provider_id} not found")
    else:
        provider = next((p for p in providers if p["is_default"]), providers[0])

    api_key = await get_user_inference_api_key(user, session, provider.get("id"))
    if not api_key:
        import os
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="No API key configured. Set OPENROUTER_API_KEY in your environment "
                   "or add an inference provider in Settings.",
        )

    return OpenRouterClient(
        api_key=api_key,
        base_url=provider["provider_url"],
        default_model=model or provider["strong_model"],
        rate_limit_user_id=str(user.id),
        rate_limit_rpm=provider["requests_per_minute"],
    )


# ── Server-wide configuration (admin-editable in Settings) ─────────────

async def get_server_config(session: AsyncSession) -> dict:
    """Get all server config key-value pairs."""
    result = await session.execute(select(ServerConfig))
    rows = result.scalars().all()
    return {row.key: row.value for row in rows}


async def get_server_config_value(session: AsyncSession, key: str, default: str = "") -> str:
    """Get a single server config value."""
    result = await session.execute(
        select(ServerConfig).where(ServerConfig.key == key)
    )
    row = result.scalar_one_or_none()
    return row.value if row is not None else default


async def set_server_config_value(session: AsyncSession, key: str, value: str) -> None:
    """Set (upsert) a server config value."""
    result = await session.execute(
        select(ServerConfig).where(ServerConfig.key == key)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        row.value = value
    else:
        session.add(ServerConfig(key=key, value=value))
    await session.commit()
