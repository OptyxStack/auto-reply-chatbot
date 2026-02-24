"""Add tickets table for WHMCS ticket storage

Revision ID: 007
Revises: 006
Create Date: 2025-02-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tickets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.String(128), nullable=False),
        sa.Column("subject", sa.String(512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(64), nullable=False),
        sa.Column("priority", sa.String(32), nullable=True),
        sa.Column("client_id", sa.String(128), nullable=True),
        sa.Column("email", sa.String(256), nullable=True),
        sa.Column("name", sa.String(256), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("source_file", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tickets_external_id", "tickets", ["external_id"], unique=True)
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_client_id", "tickets", ["client_id"])
    op.create_index("ix_tickets_email", "tickets", ["email"])
    op.create_index("ix_tickets_source_file", "tickets", ["source_file"])


def downgrade() -> None:
    op.drop_index("ix_tickets_source_file", table_name="tickets")
    op.drop_index("ix_tickets_email", table_name="tickets")
    op.drop_index("ix_tickets_client_id", table_name="tickets")
    op.drop_index("ix_tickets_status", table_name="tickets")
    op.drop_index("ix_tickets_external_id", table_name="tickets")
    op.drop_table("tickets")
