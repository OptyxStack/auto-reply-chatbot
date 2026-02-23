"""Drop external_user_id from conversations

Revision ID: 003
Revises: 002
Create Date: 2025-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_conversations_external_user_id", table_name="conversations")
    op.drop_column("conversations", "external_user_id")


def downgrade() -> None:
    op.add_column("conversations", sa.Column("external_user_id", sa.String(256), nullable=True))
    op.create_index("ix_conversations_external_user_id", "conversations", ["external_user_id"])
