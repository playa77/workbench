"""add email_recipient and email_sender to news_interests

Support per-interest email recipient and sender configuration.

Revision ID: 017
Revises: 016
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("news_interests", sa.Column("email_sender", sa.String(255), nullable=True))
    op.add_column("news_interests", sa.Column("email_recipient", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("news_interests", "email_recipient")
    op.drop_column("news_interests", "email_sender")