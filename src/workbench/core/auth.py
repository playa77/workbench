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
    UserInferenceConfig,
    UserInvite,
    UserOpenRouterKey,
    UserSession,
)

if TYPE_CHECKING:
    from workbench.core.config import WorkbenchConfig
    from workbench.shared.llm.router import OpenRouterClient

_T = TypeVar("_T")

security_scheme = HTTPBearer(auto_error=False)

_SESSION_COOKIE = "workbench_session"


def generate_api_key(prefix: str = "wb", expiry_days: int | None = None) -> tuple[str, str, str]:
    raw = f"{prefix}-{secrets.token_urlsafe(32)}"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    lookup = _hash_token(raw)
    return raw, hashed, lookup


def verify_api_key(raw_key: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw_key.encode(), hashed.encode())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


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


async def get_user_openrouter_key(user: User, session: AsyncSession) -> str | None:
    result = await session.execute(
        select(UserOpenRouterKey).where(UserOpenRouterKey.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return encryption.decrypt(row.encrypted_key)


async def set_user_openrouter_key(user: User, api_key: str, session: AsyncSession) -> None:
    encrypted = encryption.encrypt(api_key)
    result = await session.execute(
        select(UserOpenRouterKey).where(UserOpenRouterKey.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        row.encrypted_key = encrypted
    else:
        session.add(UserOpenRouterKey(user_id=user.id, encrypted_key=encrypted))
    await session.commit()


async def get_user_brave_key(user: User, session: AsyncSession) -> str | None:
    result = await session.execute(
        select(UserBraveKey).where(UserBraveKey.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return encryption.decrypt(row.encrypted_key)


async def set_user_brave_key(user: User, api_key: str, session: AsyncSession) -> None:
    encrypted = encryption.encrypt(api_key)
    result = await session.execute(
        select(UserBraveKey).where(UserBraveKey.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        row.encrypted_key = encrypted
    else:
        session.add(UserBraveKey(user_id=user.id, encrypted_key=encrypted))
    await session.commit()


async def get_user_inference_config(
    user: User, session: AsyncSession, config: "WorkbenchConfig | None" = None
) -> dict:
    """Get inference config for user. Falls back to system defaults."""
    result = await session.execute(
        select(UserInferenceConfig).where(UserInferenceConfig.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        if config is None:
            from workbench.core.config import load_config
            config = load_config()
        return {
            "provider_url": config.inference_provider_url,
            "strong_model": config.inference_strong_model,
            "quick_model": config.inference_quick_model,
            "medium_model": config.inference_medium_model,
            "requests_per_minute": config.inference_requests_per_minute,
            "has_api_key": False,
        }
    return {
        "provider_url": row.provider_url,
        "strong_model": row.strong_model,
        "quick_model": row.quick_model,
        "medium_model": row.medium_model,
        "requests_per_minute": row.requests_per_minute,
        "has_api_key": row.api_key is not None,
    }


async def get_user_inference_api_key(user: User, session: AsyncSession) -> str | None:
    """Get the decrypted inference API key, or fall back to OpenRouter key."""
    result = await session.execute(
        select(UserInferenceConfig).where(UserInferenceConfig.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is not None and row.api_key:
        return encryption.decrypt(row.api_key)
    return await get_user_openrouter_key(user, session)


async def set_user_inference_config(
    user: User,
    session: AsyncSession,
    *,
    api_key: str | None = None,
    provider_url: str | None = None,
    strong_model: str | None = None,
    quick_model: str | None = None,
    medium_model: str | None = None,
    requests_per_minute: int | None = None,
) -> None:
    """Create or update per-user inference config. api_key=None means don't change; empty string means clear."""
    result = await session.execute(
        select(UserInferenceConfig).where(UserInferenceConfig.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = UserInferenceConfig(user_id=user.id)
        session.add(row)

    if api_key is not None:
        row.api_key = encryption.encrypt(api_key) if len(api_key) > 0 else None

    if provider_url is not None:
        row.provider_url = provider_url
    if strong_model is not None:
        row.strong_model = strong_model
    if quick_model is not None:
        row.quick_model = quick_model
    if medium_model is not None:
        row.medium_model = medium_model
    if requests_per_minute is not None:
        row.requests_per_minute = requests_per_minute

    await session.commit()


async def get_user_llm_client(
    user: User,
    session: AsyncSession,
    config: "WorkbenchConfig | None" = None,
    *,
    model: str | None = None,
) -> "OpenRouterClient":
    """Build an LLM client for *user* from their inference config (falling back to system defaults).

    If *model* is provided, it overrides the strong model in the fallback chain.
    """
    from workbench.shared.llm.router import OpenRouterClient

    cfg = await get_user_inference_config(user, session, config)
    api_key = await get_user_inference_api_key(user, session)
    if not api_key:
        raise RuntimeError("No inference API key configured for this user")

    return OpenRouterClient(
        api_key=api_key,
        base_url=cfg["provider_url"],
        default_model=model or cfg["strong_model"],
        rate_limit_user_id=str(user.id),
        rate_limit_rpm=cfg["requests_per_minute"],
    )
