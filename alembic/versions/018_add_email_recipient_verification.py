"""add email_recipient_verified and pending_email_recipient_token to news_interests

Support email recipient verification with 24-hour token expiry.
Public verification endpoint — no login required.

Revision ID: 018
Revises: 017
Create Date: 2026-06-27
"""

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("news_interests", sa.Column("email_recipient_verified", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("news_interests", sa.Column("pending_email_recipient_token_hash", sa.String(64), nullable=True))
    op.add_column("news_interests", sa.Column("pending_email_recipient_token_expires", sa.DateTime, nullable=True))


def downgrade() -> None:
    op.drop_column("news_interests", "pending_email_recipient_token_expires")
    op.drop_column("news_interests", "pending_email_recipient_token_hash")
    op.drop_column("news_interests", "email_recipient_verified")
