"""API key authentication — per-user Bearer token validation."""

import secrets
import time
from datetime import UTC, datetime

import bcrypt
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core import encryption
from workbench.core.config import WorkbenchConfig
from workbench.core.db import get_session
from workbench.core.models import User, UserApiKey, UserOpenRouterKey

security_scheme = HTTPBearer(auto_error=False)


def generate_api_key(prefix: str = "wb") -> tuple[str, str]:
    """Generate a new API key. Returns (raw_key, bcrypt_hash).

    The raw key is displayed once to the user; the hash is stored.
    """
    raw = f"{prefix}-{secrets.token_urlsafe(32)}"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    return raw, hashed


def verify_api_key(raw_key: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw_key.encode(), hashed.encode())


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(security_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="API key required — use Authorization: Bearer <key>")
    raw_key = credentials.credentials

    keys_result = await session.execute(select(UserApiKey))
    for key_row in keys_result.scalars().all():
        if verify_api_key(raw_key, key_row.key_hash):
            key_row.last_used_at = datetime.now(UTC)
            await session.commit()
            user = await session.get(User, key_row.user_id)
            if user is None:
                raise HTTPException(status_code=401, detail="User not found")
            return user

    raise HTTPException(status_code=401, detail="Invalid API key")


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
