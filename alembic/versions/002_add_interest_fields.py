"""002_add_interest_fields

Add expanded interest configuration fields to news_interests.
"""

from alembic import op
from sqlalchemy import Boolean, Column, Integer, String

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_interests",
        Column("target_script_de_words", Integer, nullable=False, server_default="1250"),
    )
    op.add_column(
        "news_interests",
        Column("target_brief_words", Integer, nullable=False, server_default="600"),
    )
    op.add_column(
        "news_interests",
        Column("enable_script_de", Boolean, nullable=False, server_default="false"),
    )
    op.add_column(
        "news_interests",
        Column("input_data_length_mode", String(20), nullable=False, server_default="'full_article'"),
    )
    op.add_column(
        "news_interests",
        Column("input_word_count", Integer, nullable=False, server_default="256"),
    )


def downgrade() -> None:
    op.drop_column("news_interests", "input_word_count")
    op.drop_column("news_interests", "input_data_length_mode")
    op.drop_column("news_interests", "enable_script_de")
    op.drop_column("news_interests", "target_brief_words")
    op.drop_column("news_interests", "target_script_de_words")
