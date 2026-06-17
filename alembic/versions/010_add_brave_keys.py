"""010_add_brave_keys

Add workbench_brave_keys table for per-user encrypted Brave Search API keys.
"""

from alembic import op
from sqlalchemy import Column, DateTime, ForeignKey, Text, Uuid, func

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workbench_brave_keys",
        Column("id", Uuid, primary_key=True),
        Column("user_id", Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), unique=True, nullable=False),
        Column("encrypted_key", Text, nullable=False),
        Column("created_at", DateTime, nullable=False, server_default=func.now()),
    )


def downgrade() -> None:
    op.drop_table("workbench_brave_keys")
