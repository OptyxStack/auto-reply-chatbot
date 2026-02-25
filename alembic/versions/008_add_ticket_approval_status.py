"""Add approval_status to tickets table

Revision ID: 008
Revises: 007
Create Date: 2025-02-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("approval_status", sa.String(32), nullable=False, server_default="pending"),
    )
    op.create_index("ix_tickets_approval_status", "tickets", ["approval_status"])


def downgrade() -> None:
    op.drop_index("ix_tickets_approval_status", table_name="tickets")
    op.drop_column("tickets", "approval_status")
