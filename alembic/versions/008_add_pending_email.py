"""008_add_pending_email

Add pending_email and pending_email_token_hash to workbench_users for email change verification.
"""

from alembic import op
from sqlalchemy import Column, String

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workbench_users", Column("pending_email", String(254), nullable=True))
    op.add_column("workbench_users", Column("pending_email_token_hash", String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("workbench_users", "pending_email_token_hash")
    op.drop_column("workbench_users", "pending_email")
