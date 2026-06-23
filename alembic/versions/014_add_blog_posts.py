"""add blog posts table

Revision ID: 014
Revises: 013
Create Date: 2026-06-23
"""
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workbench_blog_posts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workbench_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("slug", sa.String(300), nullable=False),
        sa.Column("filename", sa.String(300), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("format", sa.String(20), nullable=False, server_default="markdown"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "slug", name="uq_blog_user_slug"),
        sa.Index("idx_blog_posts_user", "user_id"),
        sa.Index("idx_blog_posts_published", "is_published"),
    )


def downgrade() -> None:
    op.drop_table("workbench_blog_posts")
