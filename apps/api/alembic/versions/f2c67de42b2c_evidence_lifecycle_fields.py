"""Evidence lifecycle fields

Revision ID: 89dd75d00851
Revises: ae3852e415da
Create Date: 2026-02-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "89dd75d00851"
down_revision: Union[str, Sequence[str], None] = "ae3852e415da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns (all nullable / safe defaults)
    op.add_column("evidence_items", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence_items", sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("evidence_items", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence_items", sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("evidence_items", sa.Column("category", sa.String(length=120), nullable=True))

    # tags as text[]
    op.add_column(
        "evidence_items",
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::text[]"),
        ),
    )

    # Backfill updated_at for existing rows: use created_at
    op.execute("UPDATE evidence_items SET updated_at = created_at WHERE updated_at IS NULL")

    # Now that backfill is done, drop server default for tags if you prefer app-level control
    op.alter_column("evidence_items", "tags", server_default=None)

    # Indexes for soft-delete listing patterns
    op.create_index("ix_evidence_items_tenant_deleted", "evidence_items", ["tenant_id", "deleted_at"])
    op.create_index("ix_evidence_items_tenant_updated", "evidence_items", ["tenant_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_evidence_items_tenant_updated", table_name="evidence_items")
    op.drop_index("ix_evidence_items_tenant_deleted", table_name="evidence_items")

    op.drop_column("evidence_items", "tags")
    op.drop_column("evidence_items", "category")
    op.drop_column("evidence_items", "deleted_by")
    op.drop_column("evidence_items", "deleted_at")
    op.drop_column("evidence_items", "updated_by")
    op.drop_column("evidence_items", "updated_at")