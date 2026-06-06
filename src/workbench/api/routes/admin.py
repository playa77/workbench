"""Admin routes — invite management (admin-only)."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.auth import generate_token, get_current_user, _hash_token
from workbench.core.db import get_session
from workbench.core.email import send_invite_email
from workbench.core.models import User, UserInvite
from workbench.core.rate_limiter import limiter

router = APIRouter()

_INVITE_TIMEOUT = timedelta(days=7)


class CreateInviteRequest(BaseModel):
    email: str = Field(..., min_length=3)
    username: str = Field(..., min_length=2, max_length=100)


class InviteResponse(BaseModel):
    id: str
    email: str
    username: str
    created_at: str
    expires_at: str
    accepted_at: str | None = None
    is_revoked: bool


async def _require_admin(user: User) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.post("/admin/invites", response_model=InviteResponse)
@limiter.limit("10/minute")
async def create_invite(
    body: CreateInviteRequest,
    request: Request,
    user: User = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
):
    config = request.app.state.config
    email = body.email.strip().lower()
    username = body.username.strip()

    existing = await session.execute(
        select(User).where((User.email == email) | (User.username == username))
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Username or email already in use")

    existing_invite = await session.execute(
        select(UserInvite).where(
            UserInvite.email == email,
            UserInvite.is_revoked == False,
            UserInvite.accepted_at.is_(None),
            UserInvite.expires_at > datetime.now(UTC).replace(tzinfo=None),
        )
    )
    if existing_invite.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="An active invite already exists for this email")

    token, token_hash = generate_token()
    expires = datetime.now(UTC).replace(tzinfo=None) + _INVITE_TIMEOUT
    invite = UserInvite(
        email=email,
        username=username,
        token_hash=token_hash,
        invited_by=user.id,
        expires_at=expires,
    )
    session.add(invite)
    await session.commit()
    await session.refresh(invite)

    origin = str(request.base_url).rstrip("/")
    setup_url = f"{origin}/setup?token={token}"
    await send_invite_email(config, email, username, setup_url)

    return InviteResponse(
        id=str(invite.id),
        email=invite.email,
        username=invite.username,
        created_at=invite.created_at.isoformat() if invite.created_at else "",
        expires_at=invite.expires_at.isoformat() if invite.expires_at else "",
        accepted_at=None,
        is_revoked=False,
    )


@router.get("/admin/invites", response_model=list[InviteResponse])
async def list_invites(
    user: User = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(UserInvite).order_by(UserInvite.created_at.desc())
    )
    invites = result.scalars().all()
    return [
        InviteResponse(
            id=str(i.id),
            email=i.email,
            username=i.username,
            created_at=i.created_at.isoformat() if i.created_at else "",
            expires_at=i.expires_at.isoformat() if i.expires_at else "",
            accepted_at=i.accepted_at.isoformat() if i.accepted_at else None,
            is_revoked=i.is_revoked,
        )
        for i in invites
    ]


@router.delete("/admin/invites/{invite_id}")
async def revoke_invite(
    invite_id: str,
    user: User = Depends(_require_admin),
    session: AsyncSession = Depends(get_session),
):
    from uuid import UUID

    result = await session.execute(
        select(UserInvite).where(UserInvite.id == UUID(invite_id))
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.accepted_at is not None:
        raise HTTPException(status_code=400, detail="Invite already accepted")
    invite.is_revoked = True
    await session.commit()
    return {"status": "ok", "message": "Invite revoked"}
