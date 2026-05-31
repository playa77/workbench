"""004_add_knowledge_tables

Create knowledge_bases and knowledge_documents tables for the Knowledge agent.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("chunk_size", sa.Integer, nullable=False, server_default="1000"),
        sa.Column("chunk_overlap", sa.Integer, nullable=False, server_default="200"),
        sa.Column("embedding_model", sa.String(100), nullable=False,
                  server_default="openai/text-embedding-3-small"),
        sa.Column("document_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False,
                  server_default=sa.text("now()")),
        sa.Index("idx_kb_user", "user_id"),
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("knowledge_base_id", UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False,
                  server_default=sa.text("now()")),
        sa.Index("idx_kd_kb", "knowledge_base_id"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_documents")
    op.drop_table("knowledge_bases")
