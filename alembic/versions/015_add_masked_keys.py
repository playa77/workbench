"""add masked_key columns

Add api_key_masked to workbench_inference_providers and
masked_key to workbench_brave_keys for displaying key prefixes.

Revision ID: 015
Revises: 014
Create Date: 2026-06-24
"""

from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workbench_inference_providers", sa.Column("api_key_masked", sa.String(20), nullable=True))
    op.add_column("workbench_brave_keys", sa.Column("masked_key", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("workbench_inference_providers", "api_key_masked")
    op.drop_column("workbench_brave_keys", "masked_key")
