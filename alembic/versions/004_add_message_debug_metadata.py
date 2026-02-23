"""Add debug_metadata to messages for flow inspection

Revision ID: 004
Revises: 003
Create Date: 2025-02-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("debug_metadata", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "debug_metadata")
