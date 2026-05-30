"""API request and response models for the CAW HTTP surface."""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationInfo(BaseModel):
    """Pagination metadata for list endpoints."""

    cursor: str | None = None
    has_more: bool = False
    total: int | None = None


class APIResponse(BaseModel, Generic[T]):
    """Standard response envelope for all API endpoints."""

    status: str = "ok"
    data: T | None = None
    error_code: str | None = None
    message: str | None = None
    pagination: PaginationInfo | None = None


class CreateSessionRequest(BaseModel):
    """Request payload for creating a session."""

    mode: str = "chat"
    config_overrides: dict[str, object] | None = None
    skills: list[str] | None = None
    skill_pack: str | None = None


class UpdateSessionRequest(BaseModel):
    """Request payload for updating mutable session fields."""

    state: str | None = None
    config_overrides: dict[str, object] | None = None


class BranchSessionRequest(BaseModel):
    """Request payload for branching a session history."""

    branch_point: int = Field(default=0, ge=0)


class SendMessageRequest(BaseModel):
    """Request payload for sending a chat message."""

    content: str
    provider: str | None = None
    model: str | None = None


class SessionResponse(BaseModel):
    """Serialized session payload returned by the API."""

    id: str
    state: str
    mode: str
    parent_id: str | None = None
    created_at: str
    updated_at: str
    config_overrides: dict[str, object]
    active_skills: list[str]
    active_skill_pack: str | None = None
    metadata: dict[str, object]


class MessageResponse(BaseModel):
    """Serialized message payload returned by message endpoints."""

    id: str
    session_id: str
    sequence_num: int
    role: str
    content: str
    model: str | None = None
    provider: str | None = None
    token_count_in: int | None = None
    token_count_out: int | None = None
    created_at: str
    metadata: dict[str, object]


class ExecutionResponse(BaseModel):
    """Serialized execution result for send-message requests."""

    session_id: str
    message_id: str
    content: str
    model: str
    provider: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    trace_id: str


class TraceEventResponse(BaseModel):
    """Serialized trace event payload for trace-read endpoints."""

    id: str
    trace_id: str
    session_id: str
    timestamp: datetime
    event_type: str
    data: dict[str, object]
    parent_event_id: str | None = None


class ProviderHealthResponse(BaseModel):
    """Provider health payload returned by provider endpoints."""

    provider: str
    available: bool
    latency_ms: int | None = None
    error: str | None = None
