"""add key_masked to workbench_api_keys

Add key_masked column for displaying masked API key prefixes.

Revision ID: 016
Revises: 015
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workbench_api_keys", sa.Column("key_masked", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("workbench_api_keys", "key_masked")
