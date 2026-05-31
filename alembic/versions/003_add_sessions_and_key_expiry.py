"""003_add_sessions_and_key_expiry

Add workbench_sessions table for cookie-based auth,
and expires_at column to workbench_api_keys.
"""

from alembic import op
from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workbench_sessions",
        Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=op.f("gen_random_uuid()"),
        ),
        Column(
            "user_id",
            UUID(as_uuid=True),
            ForeignKey("workbench_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("token_hash", String(120), nullable=False),
        Column(
            "created_at",
            DateTime,
            nullable=False,
            server_default=op.f("now()"),
        ),
        Column("expires_at", DateTime, nullable=False),
    )

    op.add_column(
        "workbench_api_keys",
        Column("expires_at", DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workbench_api_keys", "expires_at")
    op.drop_table("workbench_sessions")
