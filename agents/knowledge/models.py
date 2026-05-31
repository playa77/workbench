from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from workbench.shared.db.base import Base


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    chunk_overlap: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    embedding_model: Mapped[str] = mapped_column(
        String(100), nullable=False, default="openai/text-embedding-3-small"
    )
    document_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    __table_args__ = (Index("idx_kb_user", "user_id"),)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    knowledge_base_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=func.now())

    __table_args__ = (Index("idx_kd_kb", "knowledge_base_id"),)
