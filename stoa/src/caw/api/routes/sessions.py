"""Session lifecycle endpoints for the CAW API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from caw.api.deps import get_message_repository, get_session_manager
from caw.api.schemas import (
    APIResponse,
    BranchSessionRequest,
    CreateSessionRequest,
    MessageResponse,
    PaginationInfo,
    SessionResponse,
    UpdateSessionRequest,
)
from caw.models import Message, Session, SessionMode, SessionState
from caw.core.session import SessionManager
from caw.storage.repository import SessionRepository
from caw.storage.repository import MessageRepository

router = APIRouter(prefix="/api/v1", tags=["sessions"])


def _session_response(session: Session) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        state=session.state.value,
        mode=session.mode.value,
        parent_id=session.parent_id,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat(),
        config_overrides=session.config_overrides,
        active_skills=session.active_skills,
        active_skill_pack=session.active_skill_pack,
        metadata=session.metadata,
    )


def _message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        session_id=message.session_id,
        sequence_num=message.sequence_num,
        role=message.role.value,
        content=message.content,
        model=message.model,
        provider=message.provider,
        token_count_in=message.token_count_in,
        token_count_out=message.token_count_out,
        created_at=message.created_at.isoformat(),
        metadata=message.metadata,
    )


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> APIResponse[SessionResponse]:
    session = await session_manager.create(
        mode=SessionMode(request.mode),
        config_overrides=request.config_overrides,
        skills=request.skills,
        skill_pack=request.skill_pack,
    )
    return APIResponse(data=_session_response(session))


@router.get("/sessions")
async def list_sessions(
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
    limit: int = Query(default=50, ge=1, le=200),
    mode: str | None = None,
    state: str | None = None,
) -> APIResponse[list[SessionResponse]]:
    mode_filter = SessionMode(mode) if mode is not None else None
    state_filter = SessionState(state) if state is not None else None
    sessions = await session_manager.list_sessions(
        mode=mode_filter, state=state_filter, limit=limit
    )
    data = [_session_response(session) for session in sessions]
    return APIResponse(data=data, pagination=PaginationInfo(has_more=False, total=len(data)))


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> APIResponse[SessionResponse]:
    session = await session_manager.get(session_id)
    return APIResponse(data=_session_response(session))


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> APIResponse[SessionResponse]:
    if request.state is not None:
        session = await session_manager.transition(session_id, SessionState(request.state))
    else:
        session = await session_manager.get(session_id)
    return APIResponse(data=_session_response(session))


@router.post("/sessions/{session_id}/branch", status_code=status.HTTP_201_CREATED)
async def branch_session(
    session_id: str,
    request: BranchSessionRequest,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> APIResponse[SessionResponse]:
    branched = await session_manager.branch(
        session_id=session_id, branch_point=request.branch_point
    )
    return APIResponse(data=_session_response(branched))


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    session_manager: Annotated[SessionManager, Depends(get_session_manager)],
) -> APIResponse[dict[str, str]]:
    session = await session_manager.get(session_id)
    session_repo = session_manager._repo
    assert isinstance(session_repo, SessionRepository)
    await session_repo.delete(session.id)
    return APIResponse(data={"id": session.id})


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    message_repo: Annotated[MessageRepository, Depends(get_message_repository)],
) -> APIResponse[list[MessageResponse]]:
    messages = await message_repo.list_by_session(session_id)
    return APIResponse(data=[_message_response(message) for message in messages])
