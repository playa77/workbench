"""009_add_agent_sessions

Add workbench_agent_sessions table for storing complete agent run history.
"""

from alembic import op
from sqlalchemy import Column, DateTime, ForeignKey, Index, JSON, String, Text, Uuid, func

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workbench_agent_sessions",
        Column("id", Uuid, primary_key=True),
        Column("user_id", Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False),
        Column("agent_name", String(100), nullable=False),
        Column("session_id", String(64), nullable=False),
        Column("title", String(500), nullable=False),
        Column("state_json", JSON, nullable=False, server_default="{}"),
        Column("content", Text, nullable=True),
        Column("content_format", String(20), nullable=False, server_default="markdown"),
        Column("metadata_json", JSON, nullable=False, server_default="{}"),
        Column("created_at", DateTime, nullable=False, server_default=func.now()),
        Column("updated_at", DateTime, nullable=False, server_default=func.now()),
    )
    op.create_index("idx_agent_sessions_user", "workbench_agent_sessions", ["user_id"])
    op.create_index("idx_agent_sessions_agent", "workbench_agent_sessions", ["agent_name"])
    op.create_index("idx_agent_sessions_session", "workbench_agent_sessions", ["session_id"])


def downgrade() -> None:
    op.drop_table("workbench_agent_sessions")
