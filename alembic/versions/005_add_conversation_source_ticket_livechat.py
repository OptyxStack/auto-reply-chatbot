"""Add source_type and source_id (ticket/livechat) to conversations

Revision ID: 005
Revises: 004
Create Date: 2025-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("source_type", sa.String(32), nullable=True))
    op.add_column("conversations", sa.Column("source_id", sa.String(256), nullable=True))
    # Backfill existing rows: treat as ticket with id as source_id
    op.execute(
        "UPDATE conversations SET source_type = 'ticket', source_id = id::text WHERE source_id IS NULL"
    )
    op.alter_column(
        "conversations",
        "source_type",
        existing_type=sa.String(32),
        nullable=False,
    )
    op.alter_column(
        "conversations",
        "source_id",
        existing_type=sa.String(256),
        nullable=False,
    )
    op.create_index("ix_conversations_source_type", "conversations", ["source_type"])
    op.create_index("ix_conversations_source_id", "conversations", ["source_id"])
    op.create_index("ix_conversations_source", "conversations", ["source_type", "source_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_source", table_name="conversations")
    op.drop_index("ix_conversations_source_id", table_name="conversations")
    op.drop_index("ix_conversations_source_type", table_name="conversations")
    op.drop_column("conversations", "source_id")
    op.drop_column("conversations", "source_type")
