"""Add doc_types table for user-managed document types

Revision ID: 010
Revises: 009
Create Date: 2025-03-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_DOC_TYPES = [
    ("policy", "Policy", "Privacy policy, data policy, general policies", 0),
    ("tos", "Terms of Service", "Terms of service, terms of use, legal terms", 1),
    ("faq", "FAQ", "Frequently asked questions, Q&A format", 2),
    ("howto", "How-to", "Tutorials, setup guides, documentation", 3),
    ("pricing", "Pricing", "Plans, prices, product offerings, billing", 4),
    ("other", "Other", "Blog, about, news, general content", 5),
]


def upgrade() -> None:
    op.create_table(
        "doc_types",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_doc_types_key", "doc_types", ["key"], unique=True)

    for key, label, description, sort_order in DEFAULT_DOC_TYPES:
        op.execute(
            sa.text(
                "INSERT INTO doc_types (id, key, label, description, sort_order) "
                "SELECT gen_random_uuid(), :k, :lbl, :desc, :ord "
                "WHERE NOT EXISTS (SELECT 1 FROM doc_types WHERE key = :k)"
            ).bindparams(k=key, lbl=label, desc=description, ord=sort_order)
        )


def downgrade() -> None:
    op.drop_index("ix_doc_types_key", table_name="doc_types")
    op.drop_table("doc_types")
