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
    create_inference_provider,
    create_session,
    delete_inference_provider,
    generate_api_key,
    generate_token,
    get_current_user,
    get_user_brave_key_info,
    get_user_inference_api_key,
    get_user_inference_providers,
    get_server_config,
    set_default_inference_provider,
    set_server_config_value,
    hash_password,
    set_user_brave_key,
    update_inference_provider,
    verify_api_key,
    verify_password,
    _hash_token,
)
from workbench.core.db import get_session
from workbench.core.email import (
    get_smtp_overrides_from_db,
    send_invite_accepted_email,
    send_password_changed_email,
    send_reset_email,
    send_welcome_email,
)
from workbench.core.models import User, UserApiKey, UserBraveKey, UserInferenceProvider, UserInvite, UserSession
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
    key_masked: str | None = None
    created_at: str
    last_used_at: str | None
    expires_at: str | None = None
    api_key: str | None = None


class BraveKeyRequest(BaseModel):
    api_key: str = Field(..., min_length=1)


class InferenceProviderRequest(BaseModel):
    """Request to create or update an inference provider."""
    model_config = {"extra": "forbid"}
    name: str | None = None
    api_key: str | None = None
    provider_url: str | None = None
    strong_model: str | None = None
    quick_model: str | None = None
    requests_per_minute: int | None = None
    is_default: bool | None = None


class InferenceProviderResponse(BaseModel):
    id: str | None = None
    name: str
    provider_url: str
    strong_model: str
    quick_model: str
    requests_per_minute: int
    is_default: bool
    has_api_key: bool
    masked_key: str | None = None


class UserProfile(BaseModel):
    id: str
    username: str
    email: str | None = None
    is_admin: bool = False
    has_password: bool = False
    created_at: str
    has_brave_key: bool = False
    brave_key_masked: str | None = None
    inference_providers: list[InferenceProviderResponse] = []


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
        smtp_overrides = await get_smtp_overrides_from_db(session)
        await send_reset_email(config, email, reset_url, smtp_overrides)
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
    smtp_overrides = await get_smtp_overrides_from_db(session)
    await send_password_changed_email(config, user.email or row.email, user.username, smtp_overrides)
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
    smtp_overrides = await get_smtp_overrides_from_db(session)
    await send_welcome_email(config, row.email, user.username, origin, smtp_overrides)
    if row.invited_by:
        admin_result = await session.execute(select(User).where(User.id == row.invited_by))
        admin = admin_result.scalar_one_or_none()
        if admin and admin.email:
            await send_invite_accepted_email(config, admin.email, admin.username, user.username, user.email or "", smtp_overrides)

    token = await create_session(user, session, hours=24)
    _set_session_cookie(request, response, token)
    return _login_response(user)


@router.get("/me", response_model=UserProfile)
async def get_profile(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    has_brave, brave_masked = await get_user_brave_key_info(user, session)
    providers = await get_user_inference_providers(user, session, request.app.state.config)
    return UserProfile(
        id=str(user.id),
        username=user.username,
        email=user.email,
        is_admin=user.is_admin,
        has_password=user.password_hash is not None,
        created_at=user.created_at.isoformat() if user.created_at else "",
        has_brave_key=has_brave,
        brave_key_masked=brave_masked,
        inference_providers=[InferenceProviderResponse(**p) for p in providers],
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
        smtp_overrides = await get_smtp_overrides_from_db(session)
        await send_password_changed_email(config, user.email, user.username, smtp_overrides)
    return {"status": "ok", "message": "Password changed"}


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
            key_masked=k.key_masked,
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

    raw_key, hashed, lookup, masked_key = generate_api_key()
    key = UserApiKey(user_id=user.id, key_hash=hashed, key_lookup=lookup, key_masked=masked_key, label=body.label)
    session.add(key)
    await session.commit()
    await session.refresh(key)

    return ApiKeyResponse(
        id=str(key.id),
        label=key.label,
        key_fingerprint=lookup[:8],
        key_masked=key.key_masked,
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


# ── Inference providers (multi-provider) ───────────────────────────

@router.get("/me/inference-providers", response_model=list[InferenceProviderResponse])
async def list_inference_providers(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    providers = await get_user_inference_providers(user, session, request.app.state.config)
    return [InferenceProviderResponse(**p) for p in providers]


@router.post("/me/inference-providers", response_model=InferenceProviderResponse, status_code=201)
@limiter.limit("10/minute")
async def add_inference_provider(
    body: InferenceProviderRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    provider = await create_inference_provider(
        user, session,
        name=body.name or "Default",
        api_key=body.api_key,
        provider_url=body.provider_url or "https://openrouter.ai/api/v1",
        strong_model=body.strong_model or "deepseek/deepseek-v4-pro",
        quick_model=body.quick_model or "deepseek/deepseek-v4-flash",
        requests_per_minute=body.requests_per_minute or 0,
        is_default=body.is_default or False,
    )
    return InferenceProviderResponse(
        id=str(provider.id),
        name=provider.name,
        provider_url=provider.provider_url,
        strong_model=provider.strong_model,
        quick_model=provider.quick_model,
        requests_per_minute=provider.requests_per_minute,
        is_default=provider.is_default,
        has_api_key=provider.api_key is not None,
        masked_key=provider.api_key_masked,
    )



@router.put("/me/inference-providers/{provider_id}", response_model=InferenceProviderResponse)
@limiter.limit("10/minute")
async def edit_inference_provider(
    provider_id: str,
    body: InferenceProviderRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    provider = await update_inference_provider(
        user, session, provider_id,
        name=body.name,
        api_key=body.api_key,
        provider_url=body.provider_url,
        strong_model=body.strong_model,
        quick_model=body.quick_model,
        requests_per_minute=body.requests_per_minute,
        is_default=body.is_default,
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return InferenceProviderResponse(
        id=str(provider.id),
        name=provider.name,
        provider_url=provider.provider_url,
        strong_model=provider.strong_model,
        quick_model=provider.quick_model,
        requests_per_minute=provider.requests_per_minute,
        is_default=provider.is_default,
        has_api_key=provider.api_key is not None,
        masked_key=provider.api_key_masked,
    )

@router.delete("/me/inference-providers/{provider_id}")
async def remove_inference_provider(
    provider_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    deleted = await delete_inference_provider(user, session, provider_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Provider not found")
    return {"status": "ok", "message": "Provider removed"}


@router.post("/me/inference-providers/{provider_id}/default", response_model=InferenceProviderResponse)
async def set_provider_default(
    provider_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    provider = await set_default_inference_provider(user, session, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return InferenceProviderResponse(
        id=str(provider.id),
        name=provider.name,
        provider_url=provider.provider_url,
        strong_model=provider.strong_model,
        quick_model=provider.quick_model,
        requests_per_minute=provider.requests_per_minute,
        is_default=provider.is_default,
        has_api_key=provider.api_key is not None,
        masked_key=provider.api_key_masked,
    )


@router.get("/me/inference/models")
async def get_inference_models(
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    provider_id: str | None = None,
):
    """Return available models for the user's inference provider.

    Tries to fetch from the provider's /v1/models endpoint. Falls back
    to the provider's configured strong_model and quick_model.
    """
    providers = await get_user_inference_providers(user, session, request.app.state.config)
    if not providers:
        # Return OpenRouter defaults as last resort
        return {"models": ["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"], "default_model": "deepseek/deepseek-v4-pro"}

    # Find target provider
    if provider_id:
        provider = next((p for p in providers if p["id"] == provider_id), None)
        if provider is None:
            raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")
    else:
        provider = next((p for p in providers if p["is_default"]), providers[0])

    api_key = await get_user_inference_api_key(user, session, provider.get("id"))
    if not api_key:
        import os
        api_key = os.environ.get("OPENROUTER_API_KEY", "")

    models = [provider["strong_model"]]
    if provider.get("quick_model") and provider["quick_model"] != provider["strong_model"]:
        models.append(provider["quick_model"])

    # Try to fetch models from the provider's /v1/models endpoint
    if api_key:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{provider['provider_url'].rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {api_key}"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict) and "data" in data:
                        fetched = [m["id"] for m in data["data"] if "id" in m]
                        if fetched:
                            models = fetched
        except Exception:
            pass  # Fall back to configured models

    return {"models": models, "default_model": provider["strong_model"]}


# ── Server configuration (admin-only) ─────────────────────────────────

class ServerConfigResponse(BaseModel):
    config: dict


class ServerConfigUpdateRequest(BaseModel):
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from_address: str | None = None
    smtp_use_tls: bool | None = None
    google_token: str | None = None


@router.get("/admin/server-config", response_model=ServerConfigResponse)
async def admin_get_server_config(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    config = await get_server_config(session)
    return ServerConfigResponse(config=config)


@router.put("/admin/server-config")
async def admin_update_server_config(
    body: ServerConfigUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    updates = body.model_dump(exclude_none=True)
    for key, value in updates.items():
        await set_server_config_value(session, key, str(value) if not isinstance(value, bool) else "true" if value else "false")
    return {"status": "ok", "message": "Server config updated"}
