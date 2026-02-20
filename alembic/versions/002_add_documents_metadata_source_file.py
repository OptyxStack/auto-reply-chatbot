"""Add documents metadata and source_file

Revision ID: 002
Revises: 001
Create Date: 2025-02-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("metadata", postgresql.JSONB(), nullable=True))
    op.add_column("documents", sa.Column("source_file", sa.String(256), nullable=True))
    op.create_index("ix_documents_source_file", "documents", ["source_file"])


def downgrade() -> None:
    op.drop_index("ix_documents_source_file", table_name="documents")
    op.drop_column("documents", "source_file")
    op.drop_column("documents", "metadata")
