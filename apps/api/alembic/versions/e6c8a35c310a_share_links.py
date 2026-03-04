from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "5e4ff79e5cb6"
down_revision: Union[str, Sequence[str], None] = "ae3852e415da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "share_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("policy_version", sa.String(length=50), nullable=False, server_default=sa.text("'v1'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_share_links_tenant_id", "share_links", ["tenant_id"])
    op.create_index("ix_share_links_token_hash", "share_links", ["token_hash"], unique=True)

    op.create_table(
        "share_link_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("share_link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["share_link_id"], ["share_links.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_share_link_items_tenant_id", "share_link_items", ["tenant_id"])
    op.create_index("ix_share_link_items_link_id", "share_link_items", ["share_link_id"])
    op.create_index("ux_share_link_items_unique", "share_link_items", ["share_link_id", "evidence_id"], unique=True)

    op.create_table(
        "share_link_access_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("share_link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["share_link_id"], ["share_links.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_share_link_access_tenant_created", "share_link_access_logs", ["tenant_id", "created_at"])
    op.create_index("ix_share_link_access_link_created", "share_link_access_logs", ["share_link_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_share_link_access_link_created", table_name="share_link_access_logs")
    op.drop_index("ix_share_link_access_tenant_created", table_name="share_link_access_logs")
    op.drop_table("share_link_access_logs")

    op.drop_index("ux_share_link_items_unique", table_name="share_link_items")
    op.drop_index("ix_share_link_items_link_id", table_name="share_link_items")
    op.drop_index("ix_share_link_items_tenant_id", table_name="share_link_items")
    op.drop_table("share_link_items")

    op.drop_index("ix_share_links_token_hash", table_name="share_links")
    op.drop_index("ix_share_links_tenant_id", table_name="share_links")
    op.drop_table("share_links")