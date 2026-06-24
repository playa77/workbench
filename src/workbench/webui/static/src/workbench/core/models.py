"""Core database models for Workbench.

Uses generic SQLAlchemy types that work with both PostgreSQL and SQLite.
All models inherit from the shared declarative Base.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from workbench.shared.db.base import Base


class User(Base):
    __tablename__ = "workbench_users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pending_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    pending_email_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    api_keys: Mapped[list["UserApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    brave_key: Mapped["UserBraveKey | None"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    inference_providers: Mapped[list["UserInferenceProvider"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    agent_settings: Mapped[list["UserAgentSettings"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    agent_sessions: Mapped[list["AgentSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserApiKey(Base):
    __tablename__ = "workbench_api_keys"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    key_lookup: Mapped[str | None] = mapped_column(String(64), nullable=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="api_keys")


class UserSession(Base):
    __tablename__ = "workbench_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    user: Mapped["User"] = relationship(back_populates="sessions")


class UserBraveKey(Base):
    __tablename__ = "workbench_brave_keys"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), unique=True, nullable=False)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    masked_key: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    user: Mapped["User"] = relationship(back_populates="brave_key")


class UserInferenceProvider(Base):
    """Per-user inference provider configuration — multiple providers per user.
    
    Each provider has its own endpoint URL, API key, model list, and rate limit.
    One provider per user is marked as default (is_default=True).
    API key is encrypted at rest via AES-256-GCM.
    """

    __tablename__ = "workbench_inference_providers"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="Default")
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_masked: Mapped[str | None] = mapped_column(String(20), nullable=True)
    provider_url: Mapped[str] = mapped_column(String(500), nullable=False, default="https://openrouter.ai/api/v1")
    strong_model: Mapped[str] = mapped_column(String(200), nullable=False, default="deepseek/deepseek-v4-pro")
    quick_model: Mapped[str] = mapped_column(String(200), nullable=False, default="deepseek/deepseek-v4-flash")
    requests_per_minute: Mapped[int] = mapped_column(default=0, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="inference_providers")


class UserAgentSettings(Base):
    __tablename__ = "workbench_agent_settings"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="agent_settings")

    __table_args__ = (
        UniqueConstraint("user_id", "agent_name", name="uq_user_agent"),
        Index("idx_agent_settings_user", "user_id"),
    )


class UserInvite(Base):
    __tablename__ = "workbench_invites"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invited_by: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("workbench_users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class StoredReport(Base):
    __tablename__ = "workbench_reports"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_format: Mapped[str] = mapped_column(String(20), nullable=False, default="markdown")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    __table_args__ = (
        Index("idx_reports_user", "user_id"),
        Index("idx_reports_agent", "agent_name"),
    )


class ServerConfig(Base):
    """Server-wide runtime configuration — SMTP settings, Google API token, etc."""

    __tablename__ = "workbench_server_config"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())


class AgentSession(Base):
    """Stores the complete state of any agent run for history/replay."""
    __tablename__ = "workbench_agent_sessions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    state_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_format: Mapped[str] = mapped_column(String(20), nullable=False, default="markdown")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship(back_populates="agent_sessions")

    __table_args__ = (
        Index("idx_agent_sessions_user", "user_id"),
        Index("idx_agent_sessions_agent", "agent_name"),
        Index("idx_agent_sessions_session", "session_id"),
    )


class BlogPost(Base):
    """A published document in the user's minimal blog/publishing hub.
    
    Files live on disk under data/blog/{user_id}/ in a per-user git repo.
    Metadata lives in the database. Git versions files transparently.
    """
    __tablename__ = "workbench_blog_posts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(300), nullable=False)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    format: Mapped[str] = mapped_column(String(20), nullable=False, default="markdown")
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "slug", name="uq_blog_user_slug"),
        Index("idx_blog_posts_user", "user_id"),
        Index("idx_blog_posts_published", "is_published"),
    )
