"""007_add_invites

Create workbench_invites table for invite-only registration flow.
"""

from alembic import op
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Uuid

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workbench_invites",
        Column("id", Uuid, primary_key=True),
        Column("email", String(254), nullable=False),
        Column("username", String(100), nullable=False),
        Column("token_hash", String(64), nullable=False, unique=True),
        Column("invited_by", Uuid, ForeignKey("workbench_users.id", ondelete="SET NULL"), nullable=True),
        Column("created_at", DateTime, nullable=False),
        Column("expires_at", DateTime, nullable=False),
        Column("accepted_at", DateTime, nullable=True),
        Column("is_revoked", Boolean, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("workbench_invites")
