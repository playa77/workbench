"""News Plugin — PostgreSQL migration.

Tables: news_interests, news_feeds, news_runs, news_articles, news_themes, news_deliverables, news_briefs
"""

from alembic import op
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "002_news_plugin"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_interests",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("user_id", UUID(as_uuid=True), ForeignKey("workbench_users.id", ondelete="CASCADE"), nullable=False),
        Column("name", String(200), nullable=False),
        Column("start_time", String(5), nullable=False, server_default="04:00"),
        Column("interval_hours", Integer, nullable=False, server_default="24"),
        Column("target_summary_words", Integer, nullable=False, server_default="750"),
        Column("target_script_words", Integer, nullable=False, server_default="1250"),
        Column("enable_summary", Boolean, nullable=False, server_default="true"),
        Column("enable_script", Boolean, nullable=False, server_default="true"),
        Column("enable_brief", Boolean, nullable=False, server_default="true"),
        Column("enable_email", Boolean, nullable=False, server_default="true"),
        Column("created_at", DateTime, nullable=False, server_default=op.f("now()")),
    )

    op.create_table(
        "news_feeds",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("interest_id", Integer, ForeignKey("news_interests.id", ondelete="CASCADE"), nullable=False),
        Column("url", Text, nullable=False),
        Column("name", String(200), nullable=False),
        Column("category", String(100), nullable=False, server_default="news"),
        UniqueConstraint("interest_id", "url", name="uq_news_feed_interest_url"),
    )

    op.create_table(
        "news_runs",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("interest_id", Integer, ForeignKey("news_interests.id", ondelete="CASCADE"), nullable=False),
        Column("run_date", String(10), nullable=False),
        Column("started_at", DateTime, nullable=False, server_default=op.f("now()")),
        Column("completed_at", DateTime, nullable=True),
        Column("status", String(20), nullable=False, server_default="running"),
        Column("current_stage", String(50), nullable=True),
        Column("error", Text, nullable=True),
        Index("idx_news_runs_date", "run_date"),
    )

    op.create_table(
        "news_articles",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("run_id", Integer, ForeignKey("news_runs.id", ondelete="CASCADE"), nullable=False),
        Column("feed_id", Integer, ForeignKey("news_feeds.id", ondelete="CASCADE"), nullable=False),
        Column("url", Text, nullable=False, unique=True),
        Column("title", Text, nullable=False),
        Column("author", String(300), nullable=True),
        Column("published_at", DateTime, nullable=False),
        Column("scraped_at", DateTime, nullable=False, server_default=op.f("now()")),
        Column("excerpt", Text, nullable=True),
        Column("content", Text, nullable=True),
        Column("content_status", String(20), nullable=False, server_default="full"),
        Index("idx_news_articles_url", "url"),
    )

    op.create_table(
        "news_themes",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("run_id", Integer, ForeignKey("news_runs.id", ondelete="CASCADE"), nullable=False),
        Column("title", String(300), nullable=False),
        Column("description", Text, nullable=False),
        Column("source_article_ids", Text, nullable=False),
        Column("order_index", Integer, nullable=False),
        Column("created_at", DateTime, nullable=False, server_default=op.f("now()")),
    )

    op.create_table(
        "news_deliverables",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("theme_id", Integer, ForeignKey("news_themes.id", ondelete="CASCADE"), nullable=False),
        Column("deliverable_type", String(50), nullable=False),
        Column("content", Text, nullable=False),
        Column("created_at", DateTime, nullable=False, server_default=op.f("now()")),
    )

    op.create_table(
        "news_briefs",
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("run_id", Integer, ForeignKey("news_runs.id", ondelete="CASCADE"), nullable=False),
        Column("content", Text, nullable=False),
        Column("word_count", Integer, nullable=False),
        Column("created_at", DateTime, nullable=False, server_default=op.f("now()")),
    )


def downgrade() -> None:
    op.drop_table("news_briefs")
    op.drop_table("news_deliverables")
    op.drop_table("news_themes")
    op.drop_table("news_articles")
    op.drop_table("news_runs")
    op.drop_table("news_feeds")
    op.drop_table("news_interests")
