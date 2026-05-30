"""Authentication routes — user registration, API key management."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.auth import (
    generate_api_key,
    get_current_user,
    get_user_openrouter_key,
    set_user_openrouter_key,
)
from workbench.core.db import get_session
from workbench.core.encryption import encrypt
from workbench.core.models import User, UserApiKey, UserOpenRouterKey

router = APIRouter()


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=100)


class RegisterResponse(BaseModel):
    user_id: str
    username: str
    api_key: str
    message: str


class ApiKeyLabel(BaseModel):
    label: str = "default"


class ApiKeyResponse(BaseModel):
    id: str
    label: str
    created_at: str
    last_used_at: str | None
    api_key: str | None = None


class OpenRouterKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=1)


class UserProfile(BaseModel):
    id: str
    username: str
    created_at: str
    has_openrouter_key: bool


@router.post("/register", response_model=RegisterResponse)
async def register_user(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    existing = await session.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(username=body.username)
    session.add(user)
    await session.flush()

    raw_key, hashed = generate_api_key()
    session.add(UserApiKey(user_id=user.id, key_hash=hashed, label="default"))
    await session.commit()

    return RegisterResponse(
        user_id=str(user.id),
        username=user.username,
        api_key=raw_key,
        message="Save this API key — it will not be shown again.",
    )


@router.get("/me", response_model=UserProfile)
async def get_profile(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    has_key = await get_user_openrouter_key(user, session)
    return UserProfile(
        id=str(user.id),
        username=user.username,
        created_at=user.created_at.isoformat() if user.created_at else "",
        has_openrouter_key=has_key is not None,
    )


@router.post("/me/openrouter-key")
async def set_openrouter_key(body: OpenRouterKeyRequest, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await set_user_openrouter_key(user, body.api_key, session)
    return {"status": "ok", "message": "OpenRouter key saved"}


@router.delete("/me/openrouter-key")
async def delete_openrouter_key(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(UserOpenRouterKey).where(UserOpenRouterKey.user_id == user.id))
    row = result.scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()
    return {"status": "ok", "message": "OpenRouter key removed"}


@router.get("/me/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(UserApiKey).where(UserApiKey.user_id == user.id))
    keys = result.scalars().all()
    return [
        ApiKeyResponse(
            id=str(k.id),
            label=k.label,
            created_at=k.created_at.isoformat() if k.created_at else "",
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
        )
        for k in keys
    ]


@router.post("/me/api-keys", response_model=ApiKeyResponse)
async def create_api_key(body: ApiKeyLabel, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    count_result = await session.execute(
        select(func.count(UserApiKey.id)).where(UserApiKey.user_id == user.id)
    )
    current_count = count_result.scalar() or 0
    if current_count >= 5:
        raise HTTPException(status_code=400, detail="Maximum of 5 API keys reached")

    raw_key, hashed = generate_api_key()
    key = UserApiKey(user_id=user.id, key_hash=hashed, label=body.label)
    session.add(key)
    await session.commit()
    await session.refresh(key)

    return ApiKeyResponse(
        id=str(key.id),
        label=key.label,
        created_at=key.created_at.isoformat() if key.created_at else "",
        last_used_at=None,
        api_key=raw_key,
    )


@router.delete("/me/api-keys/{key_id}")
async def delete_api_key(key_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    from uuid import UUID
    result = await session.execute(select(UserApiKey).where(UserApiKey.id == UUID(key_id), UserApiKey.user_id == user.id))
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    await session.delete(key)
    await session.commit()
    return {"status": "ok"}
