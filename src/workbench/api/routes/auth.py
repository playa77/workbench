"""Authentication routes — login, logout, password management, API key management."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.auth import (
    consume_token,
    create_session,
    generate_api_key,
    generate_token,
    get_current_user,
    get_user_brave_key,
    get_user_inference_config,
    get_user_openrouter_key,
    hash_password,
    set_user_brave_key,
    set_user_inference_config,
    set_user_openrouter_key,
    verify_api_key,
    verify_password,
    _hash_token,
)
from workbench.core.db import get_session
from workbench.core.email import (
    send_invite_accepted_email,
    send_password_changed_email,
    send_reset_email,
    send_welcome_email,
)
from workbench.core.models import User, UserApiKey, UserBraveKey, UserInferenceConfig, UserInvite, UserOpenRouterKey, UserSession
from workbench.core.rate_limiter import limiter

router = APIRouter()

_REQUEST_TIMEOUT = timedelta(hours=1)
_INVITE_TIMEOUT = timedelta(days=7)


class PasswordLoginRequest(BaseModel):
    email_or_username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class ApiKeyLoginRequest(BaseModel):
    api_key: str = Field(..., min_length=1)


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=1)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)


class AcceptInviteRequest(BaseModel):
    token: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8)


class SetupRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class ApiKeyLabel(BaseModel):
    label: str = "default"


class ApiKeyResponse(BaseModel):
    id: str
    label: str
    key_fingerprint: str | None = None
    created_at: str
    last_used_at: str | None
    expires_at: str | None = None
    api_key: str | None = None


class OpenRouterKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=1)


class BraveKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=1)


class InferenceConfigRequest(BaseModel):
    model_config = {"extra": "forbid"}
    api_key: str | None = None
    provider_url: str | None = None
    strong_model: str | None = None
    quick_model: str | None = None
    medium_model: str | None = None
    requests_per_minute: int | None = None


class InferenceConfigResponse(BaseModel):
    provider_url: str
    strong_model: str
    quick_model: str
    medium_model: str
    requests_per_minute: int
    has_api_key: bool


class UserProfile(BaseModel):
    id: str
    username: str
    email: str | None = None
    is_admin: bool = False
    has_password: bool = False
    created_at: str
    has_openrouter_key: bool
    has_brave_key: bool = False
    inference_config: InferenceConfigResponse


def _set_session_cookie(request: Request, response: Response, token: str, hours: int = 24) -> None:
    is_https = request.headers.get("X-Forwarded-Proto", "") == "https" or request.url.scheme == "https"
    response.set_cookie(
        key="workbench_session",
        value=token,
        max_age=hours * 3600,
        httponly=True,
        secure=is_https,
        samesite="strict",
        path="/",
    )


def _login_response(user: User) -> dict:
    return {
        "user_id": str(user.id),
        "username": user.username,
        "email": user.email,
        "is_admin": user.is_admin,
        "message": "Login successful",
    }


@router.get("/auth/setup-status")
async def setup_status(
    session: Annotated[AsyncSession, Depends(get_session)],
):
    result = await session.execute(select(func.count(User.id)))
    count = result.scalar() or 0
    return {"needs_setup": count == 0}


@router.post("/auth/setup")
@limiter.limit("3/minute")
async def setup(
    body: SetupRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    result = await session.execute(select(func.count(User.id)))
    count = result.scalar() or 0
    if count > 0:
        raise HTTPException(status_code=403, detail="Setup already completed")

    user = User(
        username=body.username.strip(),
        email=body.email.strip().lower(),
        password_hash=hash_password(body.password),
        is_admin=True,
    )
    session.add(user)
    await session.commit()

    token = await create_session(user, session, hours=24)
    _set_session_cookie(request, response, token)
    return _login_response(user)


@router.post("/auth/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    content_type = request.headers.get("content-type", "")
    body = await request.json()

    if "api_key" in body:
        return await _api_key_login(body["api_key"], request, response, session)

    return await _password_login(body, request, response, session)


async def _password_login(body: dict, request: Request, response: Response, session: AsyncSession):
    identifier = (body.get("email_or_username") or "").strip()
    password = (body.get("password") or "").strip()
    if not identifier or not password:
        raise HTTPException(status_code=400, detail="email_or_username and password are required")

    result = await session.execute(
        select(User).where(
            (User.email == identifier) | (User.username == identifier)
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = await create_session(user, session, hours=24)
    _set_session_cookie(request, response, token)
    return _login_response(user)


async def _api_key_login(raw_key: str, request: Request, response: Response, session: AsyncSession):
    import hashlib

    lookup = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await session.execute(
        select(UserApiKey).where(UserApiKey.key_lookup == lookup)
    )
    key_row = result.scalar_one_or_none()
    if key_row is not None and verify_api_key(raw_key, key_row.key_hash):
        user = await session.get(User, key_row.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")
        token = await create_session(user, session, hours=24)
        _set_session_cookie(request, response, token)
        return _login_response(user)

    keys_result = await session.execute(select(UserApiKey))
    for key_row in keys_result.scalars().all():
        if verify_api_key(raw_key, key_row.key_hash):
            user = await session.get(User, key_row.user_id)
            if user is None:
                raise HTTPException(status_code=401, detail="User not found")
            token = await create_session(user, session, hours=24)
            _set_session_cookie(request, response, token)
            return _login_response(user)
    raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/auth/logout")
async def logout(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    cookie_token = request.cookies.get("workbench_session")
    if cookie_token:
        token_hash = _hash_token(cookie_token)
        result = await session.execute(
            select(UserSession).where(UserSession.token_hash == token_hash)
        )
        row = result.scalar_one_or_none()
        if row is not None:
            await session.delete(row)
            await session.commit()
        else:
            result = await session.execute(select(UserSession))
            for row in result.scalars().all():
                if verify_api_key(cookie_token, row.token_hash):
                    await session.delete(row)
                    await session.commit()
                    break
    response.delete_cookie("workbench_session", path="/")
    return {"status": "ok", "message": "Logged out"}


@router.post("/auth/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    config = request.app.state.config
    email = body.email.strip().lower()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None and user.password_hash:
        token, token_hash = generate_token()
        expires = datetime.now(UTC).replace(tzinfo=None) + _REQUEST_TIMEOUT
        invite = UserInvite(
            email=email,
            username=user.username,
            token_hash=token_hash,
            invited_by=None,
            expires_at=expires,
        )
        session.add(invite)
        await session.commit()
        origin = str(request.base_url).rstrip("/")
        reset_url = f"{origin}/reset-password?token={token}"
        await send_reset_email(config, email, reset_url)
    return {"status": "ok", "message": "If an account with that email exists, a reset link has been sent."}


@router.post("/auth/reset-password")
@limiter.limit("5/minute")
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    config = request.app.state.config
    token_hash = _hash_token(body.token)
    row = await consume_token(token_hash, session, UserInvite, token_field="token_hash", expiry_field="expires_at")
    if row is None or row.is_revoked:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    result = await session.execute(select(User).where(User.username == row.username))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=400, detail="User not found")

    user.password_hash = hash_password(body.password)
    await session.delete(row)
    await session.commit()

    token = await create_session(user, session, hours=24)
    _set_session_cookie(request, response, token)
    await send_password_changed_email(config, user.email or row.email, user.username)
    return _login_response(user)


@router.post("/auth/accept-invite")
@limiter.limit("5/minute")
async def accept_invite(
    body: AcceptInviteRequest,
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    config = request.app.state.config
    token_hash = _hash_token(body.token)
    row = await consume_token(token_hash, session, UserInvite, token_field="token_hash", expiry_field="expires_at")
    if row is None or row.is_revoked or row.accepted_at is not None:
        raise HTTPException(status_code=400, detail="Invalid or expired invite token")

    existing = await session.execute(
        select(User).where((User.email == row.email) | (User.username == row.username))
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Username or email already taken")

    user = User(
        username=row.username,
        email=row.email,
        password_hash=hash_password(body.password),
        is_admin=False,
    )
    session.add(user)
    await session.flush()

    row.accepted_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()

    origin = str(request.base_url).rstrip("/")
    await send_welcome_email(config, row.email, user.username, origin)
    if row.invited_by:
        admin_result = await session.execute(select(User).where(User.id == row.invited_by))
        admin = admin_result.scalar_one_or_none()
        if admin and admin.email:
            await send_invite_accepted_email(config, admin.email, admin.username, user.username, user.email or "")

    token = await create_session(user, session, hours=24)
    _set_session_cookie(request, response, token)
    return _login_response(user)


@router.get("/me", response_model=UserProfile)
async def get_profile(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    has_key = await get_user_openrouter_key(user, session)
    has_brave = await get_user_brave_key(user, session)
    inf_cfg = await get_user_inference_config(user, session, request.app.state.config)
    return UserProfile(
        id=str(user.id),
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        has_password=user.password_hash is not None,
        created_at=user.created_at.isoformat() if user.created_at else "",
        has_openrouter_key=has_key is not None,
        has_brave_key=has_brave is not None,
        inference_config=InferenceConfigResponse(**inf_cfg),
    )


@router.post("/me/change-password")
@limiter.limit("5/minute")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    await session.commit()
    config = request.app.state.config
    if user.email:
        await send_password_changed_email(config, user.email, user.username)
    return {"status": "ok", "message": "Password changed"}


@router.post("/me/openrouter-key")
@limiter.limit("10/minute")
async def set_openrouter_key(
    body: OpenRouterKeyRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if not body.api_key.startswith("sk-or-v1-"):
        raise HTTPException(
            status_code=400,
            detail="Invalid OpenRouter key format. Must begin with 'sk-or-v1-'.",
        )
    if len(body.api_key) < 20:
        raise HTTPException(status_code=400, detail="OpenRouter key too short.")
    await set_user_openrouter_key(user, body.api_key, session)
    return {"status": "ok", "message": "OpenRouter key saved"}


@router.delete("/me/openrouter-key")
async def delete_openrouter_key(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    result = await session.execute(
        select(UserOpenRouterKey).where(UserOpenRouterKey.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()
    return {"status": "ok", "message": "OpenRouter key removed"}


@router.post("/me/brave-key")
@limiter.limit("10/minute")
async def set_brave_key(
    body: BraveKeyRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if len(body.api_key) < 8:
        raise HTTPException(status_code=400, detail="Brave Search API key too short.")
    await set_user_brave_key(user, body.api_key, session)
    return {"status": "ok", "message": "Brave Search API key saved"}


@router.delete("/me/brave-key")
async def delete_brave_key(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    result = await session.execute(
        select(UserBraveKey).where(UserBraveKey.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()
    return {"status": "ok", "message": "Brave Search API key removed"}


@router.get("/me/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    result = await session.execute(select(UserApiKey).where(UserApiKey.user_id == user.id))
    keys = result.scalars().all()
    return [
        ApiKeyResponse(
            id=str(k.id),
            label=k.label,
            key_fingerprint=k.key_lookup[:8] if k.key_lookup else None,
            created_at=k.created_at.isoformat() if k.created_at else "",
            last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
            expires_at=k.expires_at.isoformat() if k.expires_at else None,
        )
        for k in keys
    ]


@router.post("/me/api-keys", response_model=ApiKeyResponse)
@limiter.limit("10/minute")
async def create_api_key(
    body: ApiKeyLabel,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    count_result = await session.execute(
        select(func.count(UserApiKey.id)).where(UserApiKey.user_id == user.id)
    )
    current_count = count_result.scalar() or 0
    config = request.app.state.config
    max_keys = config.auth_max_keys_per_user
    if current_count >= max_keys:
        raise HTTPException(status_code=400, detail=f"Maximum of {max_keys} API keys reached")

    raw_key, hashed, lookup = generate_api_key()
    key = UserApiKey(user_id=user.id, key_hash=hashed, key_lookup=lookup, label=body.label)
    session.add(key)
    await session.commit()
    await session.refresh(key)

    return ApiKeyResponse(
        id=str(key.id),
        label=key.label,
        key_fingerprint=lookup[:8],
        created_at=key.created_at.isoformat() if key.created_at else "",
        last_used_at=None,
        api_key=raw_key,
    )


@router.delete("/me/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    from uuid import UUID

    try:
        key_uuid = UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid API key ID format")

    result = await session.execute(
        select(UserApiKey).where(
            UserApiKey.id == key_uuid,
            UserApiKey.user_id == user.id,
        )
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    await session.delete(key)
    await session.commit()
    return {"status": "ok"}


# ── Inference provider config ───────────────────────────────────────

@router.get("/me/inference-config", response_model=InferenceConfigResponse)
async def get_inference_config(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    inf_cfg = await get_user_inference_config(user, session, request.app.state.config)
    return InferenceConfigResponse(**inf_cfg)


@router.put("/me/inference-config", response_model=InferenceConfigResponse)
@limiter.limit("10/minute")
async def update_inference_config(
    body: InferenceConfigRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    await set_user_inference_config(
        user, session,
        api_key=body.api_key,
        provider_url=body.provider_url,
        strong_model=body.strong_model,
        quick_model=body.quick_model,
        medium_model=body.medium_model,
        requests_per_minute=body.requests_per_minute,
    )
    inf_cfg = await get_user_inference_config(user, session, request.app.state.config)
    return InferenceConfigResponse(**inf_cfg)


@router.delete("/me/inference-config")
async def delete_inference_config(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    result = await session.execute(
        select(UserInferenceConfig).where(UserInferenceConfig.user_id == user.id)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await session.delete(row)
        await session.commit()
    return {"status": "ok", "message": "Inference config reset to defaults"}
