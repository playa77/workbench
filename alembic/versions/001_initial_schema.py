"""001_initial_schema

Create core workbench tables: users, api_keys, openrouter_keys, plugin_settings, reports.
"""

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB


def upgrade() -> None:
    op.create_table(
        "workbench_users",
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=op.f("gen_random_uuid()")),
        Column("username", String(100), nullable=False, unique=True),
        Column("created_at", DateTime, nullable=False, server_default=op.f("now()")),
    )
    op.create_table(
        "workbench_api_keys",
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=op.f("gen_random_uuid()")),
        Column("user_id", UUID(as_uuid=True), ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False),
        Column("key_hash", String(120), nullable=False),
        Column("label", String(100), nullable=False, server_default="default"),
        Column("created_at", DateTime, nullable=False, server_default=op.f("now()")),
        Column("last_used_at", DateTime, nullable=True),
    )
    op.create_table(
        "workbench_openrouter_keys",
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=op.f("gen_random_uuid()")),
        Column("user_id", UUID(as_uuid=True), ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False, unique=True),
        Column("encrypted_key", Text, nullable=False),
        Column("created_at", DateTime, nullable=False, server_default=op.f("now()")),
    )
    op.create_table(
        "workbench_plugin_settings",
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=op.f("gen_random_uuid()")),
        Column("user_id", UUID(as_uuid=True), ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False),
        Column("plugin_name", String(100), nullable=False),
        Column("enabled", Boolean, nullable=False, server_default="false"),
        Column("settings", JSONB, nullable=False, server_default=op.f("'{}'::jsonb")),
        Column("updated_at", DateTime, nullable=False, server_default=op.f("now()")),
        UniqueConstraint("user_id", "plugin_name", name="uq_user_plugin"),
        Index("idx_plugin_settings_user", "user_id"),
    )
    op.create_table(
        "workbench_reports",
        Column("id", UUID(as_uuid=True), primary_key=True, server_default=op.f("gen_random_uuid()")),
        Column("user_id", UUID(as_uuid=True), ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False),
        Column("plugin_name", String(100), nullable=False),
        Column("title", String(500), nullable=False),
        Column("content", Text, nullable=False),
        Column("content_format", String(20), nullable=False, server_default="markdown"),
        Column("metadata_json", JSONB, nullable=False, server_default=op.f("'{}'::jsonb")),
        Column("created_at", DateTime, nullable=False, server_default=op.f("now()")),
        Index("idx_reports_user", "user_id"),
        Index("idx_reports_plugin", "plugin_name"),
    )


def downgrade() -> None:
    op.drop_table("workbench_reports")
    op.drop_table("workbench_plugin_settings")
    op.drop_table("workbench_openrouter_keys")
    op.drop_table("workbench_api_keys")
    op.drop_table("workbench_users")
