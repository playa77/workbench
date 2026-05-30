"""Session lifecycle management.

This module implements the orchestration-layer session state machine,
including creation, transitions, branching, and retrieval operations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from caw.errors import ValidationError_
from caw.models import Message, Session, SessionMode, SessionState, _utcnow

if TYPE_CHECKING:
    from caw.storage.repository import MessageRepository, SessionRepository


class SessionManager:
    """Manages session lifecycle transitions and branching."""

    VALID_TRANSITIONS: ClassVar[dict[SessionState, set[SessionState]]] = {
        SessionState.CREATED: {SessionState.ACTIVE, SessionState.FAILED},
        SessionState.ACTIVE: {
            SessionState.PAUSED,
            SessionState.COMPLETED,
            SessionState.FAILED,
            SessionState.CHECKPOINTED,
        },
        SessionState.PAUSED: {SessionState.ACTIVE},
        SessionState.CHECKPOINTED: {SessionState.ACTIVE},
        SessionState.COMPLETED: set(),
        SessionState.FAILED: set(),
    }

    def __init__(
        self,
        repo: SessionRepository,
        message_repo: MessageRepository | None = None,
    ) -> None:
        self._repo = repo
        self._message_repo = message_repo

    async def create(
        self,
        mode: SessionMode,
        config_overrides: dict[str, object] | None = None,
        skills: list[str] | None = None,
        skill_pack: str | None = None,
    ) -> Session:
        """Create a new session in CREATED state."""
        session = Session(
            mode=mode,
            state=SessionState.CREATED,
            config_overrides=dict(config_overrides or {}),
            active_skills=list(skills or []),
            active_skill_pack=skill_pack,
        )
        return await self._repo.create(session)

    async def get(self, session_id: str) -> Session:
        """Fetch a session by ID."""
        session = await self._repo.get(session_id)
        if session is None:
            raise ValidationError_(
                message=f"Session not found: {session_id}",
                code="session_not_found",
                details={"session_id": session_id},
            )
        return session

    async def transition(self, session_id: str, new_state: SessionState) -> Session:
        """Transition a session to a new state if allowed."""
        session = await self.get(session_id)
        allowed = self.VALID_TRANSITIONS[session.state]
        if new_state not in allowed:
            raise ValidationError_(
                message=(
                    f"Invalid session transition from {session.state.value} to {new_state.value}"
                ),
                code="invalid_session_transition",
                details={
                    "session_id": session_id,
                    "from_state": session.state.value,
                    "to_state": new_state.value,
                },
            )

        session.state = new_state
        session.updated_at = _utcnow()
        return await self._repo.update(session)

    async def branch(self, session_id: str, branch_point: int) -> Session:
        """Branch a session by cloning message history up to a branch point."""
        parent = await self.get(session_id)
        if self._message_repo is None:
            raise ValidationError_(
                message="SessionManager.branch requires a MessageRepository",
                code="branch_message_repo_missing",
            )

        if branch_point < 0:
            raise ValidationError_(
                message="branch_point must be >= 0",
                code="invalid_branch_point",
                details={"branch_point": branch_point},
            )

        parent_messages = await self._message_repo.list_by_session(parent.id)
        if parent_messages and branch_point >= len(parent_messages):
            raise ValidationError_(
                message="branch_point exceeds message history length",
                code="invalid_branch_point",
                details={"branch_point": branch_point, "history_length": len(parent_messages)},
            )

        branched = Session(
            mode=parent.mode,
            parent_id=parent.id,
            state=SessionState.CREATED,
            config_overrides=dict(parent.config_overrides),
            active_skills=list(parent.active_skills),
            active_skill_pack=parent.active_skill_pack,
            metadata=dict(parent.metadata),
        )
        created = await self._repo.create(branched)

        # branch_point is inclusive per technical specification.
        copied = parent_messages[: branch_point + 1]
        for index, message in enumerate(copied, start=1):
            await self._message_repo.create(
                Message(
                    session_id=created.id,
                    sequence_num=index,
                    role=message.role,
                    content=message.content,
                    model=message.model,
                    provider=message.provider,
                    token_count_in=message.token_count_in,
                    token_count_out=message.token_count_out,
                    metadata=dict(message.metadata),
                )
            )

        return created

    async def list_sessions(
        self,
        state: SessionState | None = None,
        mode: SessionMode | None = None,
        limit: int = 50,
    ) -> list[Session]:
        """List sessions by optional state or mode filter."""
        if state is not None:
            return await self._repo.list_by_state(state=state, limit=limit)
        if mode is not None:
            return await self._repo.list_by_mode(mode=mode, limit=limit)
        return await self._repo.list_recent(limit=limit)
