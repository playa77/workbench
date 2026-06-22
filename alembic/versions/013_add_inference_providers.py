"""013_add_inference_providers

Replace the single-row workbench_inference_config table with
workbench_inference_providers — allowing multiple providers per user.

1. Create workbench_inference_providers table with is_default column.
2. Migrate existing data from workbench_inference_config (one row per user
   becomes one provider with is_default=True, name='Default').
3. Drop workbench_inference_config table.
"""

from alembic import op
from sqlalchemy import Column, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid, func, text

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create the new providers table
    op.create_table(
        "workbench_inference_providers",
        Column("id", Uuid, primary_key=True, server_default=text("gen_random_uuid()")),
        Column("user_id", Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False, index=True),
        Column("name", String(100), nullable=False, server_default="Default"),
        Column("api_key", Text, nullable=True),
        Column("provider_url", String(500), nullable=False, server_default="https://openrouter.ai/api/v1"),
        Column("strong_model", String(200), nullable=False, server_default="deepseek/deepseek-v4-pro"),
        Column("quick_model", String(200), nullable=False, server_default="deepseek/deepseek-v4-flash"),
        Column("requests_per_minute", Integer, nullable=False, server_default="0"),
        Column("is_default", Boolean, nullable=False, server_default="0"),
        Column("created_at", DateTime, nullable=False, server_default=func.now()),
        Column("updated_at", DateTime, nullable=False, server_default=func.now()),
    )

    # 2. Migrate existing inference config rows into providers
    connection = op.get_bind()
    existing = connection.execute(
        text(
            "SELECT user_id, api_key, provider_url, strong_model, quick_model, "
            "requests_per_minute FROM workbench_inference_config"
        )
    ).fetchall()

    if existing:
        insert_sql = text(
            "INSERT INTO workbench_inference_providers "
            "(user_id, name, api_key, provider_url, strong_model, quick_model, "
            "requests_per_minute, is_default) "
            "VALUES (:uid, 'Default', :api_key, :provider_url, :strong_model, "
            ":quick_model, :rpm, TRUE)"
        )
        for row in existing:
            connection.execute(
                insert_sql,
                {
                    "uid": row[0],
                    "api_key": row[1],
                    "provider_url": row[2],
                    "strong_model": row[3],
                    "quick_model": row[4],
                    "rpm": row[5],
                },
            )

    # 3. Drop the old table
    op.drop_table("workbench_inference_config")


def downgrade() -> None:
    # Re-create the old single-config table
    op.create_table(
        "workbench_inference_config",
        Column("id", Uuid, primary_key=True),
        Column("user_id", Uuid, ForeignKey("workbench_users.id", ondelete="CASCADE"), unique=True, nullable=False),
        Column("api_key", Text, nullable=True),
        Column("provider_url", String(500), nullable=False, server_default="https://openrouter.ai/api/v1"),
        Column("strong_model", String(200), nullable=False, server_default="deepseek/deepseek-v4-pro"),
        Column("quick_model", String(200), nullable=False, server_default="deepseek/deepseek-v4-flash"),
        Column("requests_per_minute", Integer, nullable=False, server_default="0"),
        Column("created_at", DateTime, nullable=False, server_default=func.now()),
        Column("updated_at", DateTime, nullable=False, server_default=func.now()),
    )

    # Migrate default providers back to single config (first provider per user)
    connection = op.get_bind()
    providers = connection.execute(
        text(
            "SELECT DISTINCT user_id, api_key, provider_url, strong_model, "
            "quick_model, requests_per_minute "
            "FROM workbench_inference_providers "
            "WHERE is_default = 1 OR user_id IN ("
            "  SELECT user_id FROM workbench_inference_providers GROUP BY user_id HAVING COUNT(*) = 1"
            ") "
            "ORDER BY user_id, is_default DESC, created_at ASC"
        )
    ).fetchall()

    if providers:
        insert_sql = text(
            "INSERT INTO workbench_inference_config "
            "(user_id, api_key, provider_url, strong_model, quick_model, requests_per_minute) "
            "VALUES (:uid, :api_key, :provider_url, :strong_model, :quick_model, :rpm)"
        )
        for row in providers:
            connection.execute(
                insert_sql,
                {
                    "uid": row[0],
                    "api_key": row[1],
                    "provider_url": row[2],
                    "strong_model": row[3],
                    "quick_model": row[4],
                    "rpm": row[5],
                },
            )

    op.drop_table("workbench_inference_providers")
