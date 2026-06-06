"""006_add_user_email_password

Add email, password_hash, is_admin columns to workbench_users for invite-only auth.
"""

from alembic import op
from sqlalchemy import Boolean, Column, String

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workbench_users", Column("email", String(254), nullable=True))
    op.create_unique_constraint("uq_users_email", "workbench_users", ["email"])
    op.add_column("workbench_users", Column("password_hash", String(120), nullable=True))
    op.add_column("workbench_users", Column("is_admin", Boolean, nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("workbench_users", "is_admin")
    op.drop_column("workbench_users", "password_hash")
    op.drop_constraint("uq_users_email", "workbench_users", type_="unique")
    op.drop_column("workbench_users", "email")
