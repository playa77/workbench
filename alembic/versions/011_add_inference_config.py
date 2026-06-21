"""011_add_inference_config

Add workbench_inference_config table for per-user inference provider settings.
"""

from alembic import op
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Uuid, func

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workbench_inference_config",
        Column("id", Uuid, primary_key=True),
        Column("user_id", Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), unique=True, nullable=False),
        Column("api_key", Text, nullable=True),
        Column("provider_url", String(500), nullable=False, server_default="https://openrouter.ai/api/v1"),
        Column("strong_model", String(200), nullable=False, server_default="deepseek/deepseek-v4-pro"),
        Column("quick_model", String(200), nullable=False, server_default="google/gemini-2.0-flash-001"),
        Column("medium_model", String(200), nullable=False, server_default="anthropic/claude-sonnet-4-20250514"),
        Column("requests_per_minute", Integer, nullable=False, server_default="0"),
        Column("created_at", DateTime, nullable=False, server_default=func.now()),
        Column("updated_at", DateTime, nullable=False, server_default=func.now()),
    )


def downgrade() -> None:
    op.drop_table("workbench_inference_config")
