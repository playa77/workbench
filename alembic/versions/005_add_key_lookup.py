"""005_add_key_lookup

Add key_lookup (SHA256) column to workbench_api_keys for O(1) login lookup.
"""

from alembic import op
from sqlalchemy import Column, String

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workbench_api_keys",
        Column("key_lookup", String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workbench_api_keys", "key_lookup")
