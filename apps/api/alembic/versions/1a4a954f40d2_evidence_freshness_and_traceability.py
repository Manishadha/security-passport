from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1a4a954f40d2"
down_revision: Union[str, Sequence[str], None] = "2c1e5575bdcb"  # your current head
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable columns only => backward compatible
    op.add_column("evidence_items", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence_items", sa.Column("evidence_period_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence_items", sa.Column("evidence_period_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence_items", sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("evidence_items", sa.Column("source_system", sa.String(length=50), nullable=True))
    op.add_column("evidence_items", sa.Column("source_ref", sa.String(length=500), nullable=True))

    # Indexes useful for dashboards + filtering
    op.create_index("ix_evidence_items_tenant_expires", "evidence_items", ["tenant_id", "expires_at"])
    op.create_index("ix_evidence_items_tenant_verified", "evidence_items", ["tenant_id", "last_verified_at"])
    op.create_index("ix_evidence_items_source_system", "evidence_items", ["source_system"])


def downgrade() -> None:
    op.drop_index("ix_evidence_items_source_system", table_name="evidence_items")
    op.drop_index("ix_evidence_items_tenant_verified", table_name="evidence_items")
    op.drop_index("ix_evidence_items_tenant_expires", table_name="evidence_items")

    op.drop_column("evidence_items", "source_ref")
    op.drop_column("evidence_items", "source_system")
    op.drop_column("evidence_items", "last_verified_at")
    op.drop_column("evidence_items", "evidence_period_end")
    op.drop_column("evidence_items", "evidence_period_start")
    op.drop_column("evidence_items", "expires_at")