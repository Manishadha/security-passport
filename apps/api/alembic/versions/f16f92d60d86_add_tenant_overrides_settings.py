from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f16f92d60d86"
down_revision = "1af399055691"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_tenant_overrides_tenant_id", "tenant_overrides", ["tenant_id"], unique=True)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_overrides CASCADE")
