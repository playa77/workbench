"""Agent session history routes — list, view, delete stored agent sessions."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from workbench.core.auth import get_current_user
from workbench.core.db import get_session
from workbench.core.models import AgentSession, User

router = APIRouter()


class SessionSummary(BaseModel):
    id: str
    agent_name: str
    session_id: str
    title: str
    content_length: int
    word_count: int
    created_at: str
    updated_at: str
    metadata: dict


class SessionDetail(BaseModel):
    id: str
    agent_name: str
    session_id: str
    title: str
    state: dict
    content: str | None
    content_format: str
    created_at: str
    updated_at: str
    metadata: dict


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    agent: str | None = Query(None, description="Filter by agent name"),
):
    """List all saved agent sessions for the current user, optionally filtered by agent."""
    query = (
        select(AgentSession)
        .where(AgentSession.user_id == user.id)
        .order_by(AgentSession.created_at.desc())
        .limit(200)
    )
    if agent:
        query = query.where(AgentSession.agent_name == agent)

    result = await session.execute(query)
    sessions = result.scalars().all()
    return [
        SessionSummary(
            id=str(s.id),
            agent_name=s.agent_name,
            session_id=s.session_id,
            title=s.title,
            content_length=len(s.content) if s.content else 0,
            word_count=len(s.content.split()) if s.content else 0,
            created_at=s.created_at.isoformat() if s.created_at else "",
            updated_at=s.updated_at.isoformat() if s.updated_at else "",
            metadata=s.metadata_json or {},
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get a single session by its UUID."""
    result = await session.execute(
        select(AgentSession).where(
            AgentSession.id == UUID(session_id),
            AgentSession.user_id == user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetail(
        id=str(entry.id),
        agent_name=entry.agent_name,
        session_id=entry.session_id,
        title=entry.title,
        state=entry.state_json or {},
        content=entry.content,
        content_format=entry.content_format,
        created_at=entry.created_at.isoformat() if entry.created_at else "",
        updated_at=entry.updated_at.isoformat() if entry.updated_at else "",
        metadata=entry.metadata_json or {},
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Delete a session by its UUID."""
    result = await session.execute(
        select(AgentSession).where(
            AgentSession.id == UUID(session_id),
            AgentSession.user_id == user.id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Session not found")
    await session.delete(entry)
    await session.commit()
    return {"status": "ok"}
