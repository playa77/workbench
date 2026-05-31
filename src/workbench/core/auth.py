"""API key + session cookie authentication."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core import encryption
from workbench.core.db import get_session
from workbench.core.models import User, UserApiKey, UserOpenRouterKey, UserSession

security_scheme = HTTPBearer(auto_error=False)

_SESSION_COOKIE = "workbench_session"


def generate_api_key(prefix: str = "wb", expiry_days: int | None = None) -> tuple[str, str]:
    raw = f"{prefix}-{secrets.token_urlsafe(32)}"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    return raw, hashed


def verify_api_key(raw_key: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw_key.encode(), hashed.encode())


def generate_session_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
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
    result = await session.execute(
        select(UserSession).where(UserSession.expires_at > now)
    )
    for row in result.scalars().all():
        if verify_api_key(token, row.token_hash):
            user = await session.get(User, row.user_id)
            return user
    return None


async def _auth_via_api_key(raw_key: str, session: AsyncSession) -> User | None:
    keys_result = await session.execute(select(UserApiKey))
    for key_row in keys_result.scalars().all():
        if verify_api_key(raw_key, key_row.key_hash):
            if key_row.expires_at is not None and key_row.expires_at < datetime.now(UTC):
                continue
            key_row.last_used_at = datetime.now(UTC)
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
