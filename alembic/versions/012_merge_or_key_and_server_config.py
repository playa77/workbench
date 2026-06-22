"""012_merge_or_key_and_server_config

1. Drop workbench_openrouter_keys table (merged into inference_config.api_key).
2. Add workbench_server_config table for SMTP + Google token.
3. Update quick_model default in workbench_inference_config.
4. Drop medium_model column from workbench_inference_config.
"""

from alembic import op
from sqlalchemy import Column, DateTime, Integer, String, Text, Uuid, func

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop the redundant openrouter_keys table
    op.drop_table("workbench_openrouter_keys")

    # 2. Create server_config table for admin-editable server settings
    op.create_table(
        "workbench_server_config",
        Column("id", Uuid, primary_key=True),
        Column("key", String(100), unique=True, nullable=False),
        Column("value", Text, nullable=False),
        Column("updated_at", DateTime, nullable=False, server_default=func.now()),
    )

    # 3. Update quick_model default value
    with op.batch_alter_table("workbench_inference_config") as batch_op:
        batch_op.alter_column(
            "quick_model",
            existing_type=String(200),
            server_default="deepseek/deepseek-v4-flash",
            existing_nullable=False,
        )

    # 4. Drop medium_model column (batch mode for SQLite compat)
    with op.batch_alter_table("workbench_inference_config") as batch_op:
        batch_op.drop_column("medium_model")


def downgrade() -> None:
    # Re-add medium_model column
    with op.batch_alter_table("workbench_inference_config") as batch_op:
        batch_op.add_column(
            Column("medium_model", String(200), nullable=False, server_default="anthropic/claude-sonnet-4-20250514")
        )

    # Revert quick_model default
    with op.batch_alter_table("workbench_inference_config") as batch_op:
        batch_op.alter_column(
            "quick_model",
            existing_type=String(200),
            server_default="google/gemini-2.0-flash-001",
            existing_nullable=False,
        )

    # Re-create openrouter_keys table
    op.create_table(
        "workbench_openrouter_keys",
        Column("id", Uuid, primary_key=True),
        Column("user_id", Uuid, nullable=False),
        Column("encrypted_key", Text, nullable=False),
        Column("created_at", DateTime, nullable=False, server_default=func.now()),
    )

    # Drop server_config table
    op.drop_table("workbench_server_config")
