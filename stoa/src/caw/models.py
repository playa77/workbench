"""Core data models for CAW.

These dataclasses define the shared vocabulary used across all layers.
They are pure data containers with no business logic. Serialization
to/from database rows and API schemas happens in the respective layers.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import uuid6


def _utcnow() -> datetime:
    """Return current UTC time."""
    return datetime.now(UTC)


def _generate_id() -> str:
    """Generate a UUIDv7 string, falling back to UUIDv4 if unavailable."""
    try:
        return str(uuid6.uuid7())
    except Exception:  # pragma: no cover - defensive fallback only
        return str(uuid.uuid4())


class SessionState(str, enum.Enum):
    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    CHECKPOINTED = "checkpointed"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionMode(str, enum.Enum):
    CHAT = "chat"
    RESEARCH = "research"
    DELIBERATION = "deliberation"
    WORKSPACE = "workspace"
    ARENA = "arena"


class MessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ArtifactType(str, enum.Enum):
    REPORT = "report"
    PATCH = "patch"
    FILE = "file"
    EXPORT = "export"
    EVALUATION_RESULT = "evaluation_result"


class PermissionLevel(str, enum.Enum):
    READ = "read"
    SUGGEST = "suggest"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    ADMIN = "admin"


@dataclass
class Session:
    id: str = field(default_factory=_generate_id)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    state: SessionState = SessionState.CREATED
    mode: SessionMode = SessionMode.CHAT
    parent_id: str | None = None
    config_overrides: dict[str, object] = field(default_factory=dict)
    active_skills: list[str] = field(default_factory=list)
    active_skill_pack: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class Message:
    id: str = field(default_factory=_generate_id)
    session_id: str = ""
    sequence_num: int = 0
    role: MessageRole = MessageRole.USER
    content: str = ""
    model: str | None = None
    provider: str | None = None
    token_count_in: int | None = None
    token_count_out: int | None = None
    created_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class Artifact:
    id: str = field(default_factory=_generate_id)
    session_id: str = ""
    type: ArtifactType = ArtifactType.FILE
    name: str = ""
    path: str | None = None
    content: str | None = None
    content_hash: str | None = None
    created_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class Source:
    id: str = field(default_factory=_generate_id)
    session_id: str | None = None
    type: str = ""
    uri: str | None = None
    title: str | None = None
    content: str | None = None
    content_hash: str | None = None
    created_at: datetime = field(default_factory=_utcnow)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class Citation:
    id: str = field(default_factory=_generate_id)
    message_id: str = ""
    source_id: str = ""
    claim: str = ""
    excerpt: str | None = None
    confidence: float | None = None
    location: str | None = None
    created_at: datetime = field(default_factory=_utcnow)


@dataclass
class TraceEvent:
    id: str = field(default_factory=_generate_id)
    trace_id: str = ""
    session_id: str = ""
    timestamp: datetime = field(default_factory=_utcnow)
    event_type: str = ""
    data: dict[str, object] = field(default_factory=dict)
    parent_event_id: str | None = None


@dataclass
class ApprovalRequest:
    id: str = field(default_factory=_generate_id)
    session_id: str = ""
    action: str = ""
    permission_level: PermissionLevel = PermissionLevel.WRITE
    resources: list[str] = field(default_factory=list)
    reversible: bool = False
    preview: str | None = None
    timeout_seconds: int = 300


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass
class ApprovalRecord:
    request: ApprovalRequest
    status: ApprovalStatus = ApprovalStatus.PENDING
    created_at: datetime = field(default_factory=_utcnow)
    resolved_at: datetime | None = None
    resolved_by: str | None = None
    reason: str | None = None


@dataclass
class ApprovalResponse:
    request_id: str = ""
    approved: bool = False
    modifier: str | None = None
    timestamp: datetime = field(default_factory=_utcnow)


@dataclass
class CheckpointRef:
    id: str = field(default_factory=_generate_id)
    session_id: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    message_index: int = 0
    description: str | None = None


@dataclass
class EvalRun:
    id: str = field(default_factory=_generate_id)
    task_id: str = ""
    provider: str = ""
    model: str = ""
    skill_pack: str | None = None
    started_at: datetime = field(default_factory=_utcnow)
    completed_at: datetime | None = None
    status: str = "running"
    scores: dict[str, float] = field(default_factory=dict)
    trace_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
