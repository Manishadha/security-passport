"""Default UUID for tenant_overrides.id

Revision ID: 14a3f725d795
Revises: f16f92d60d86
Create Date: 2026-02-16 18:34:15.946254

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "14a3f725d795"
down_revision: Union[str, Sequence[str], None] = "f16f92d60d86"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.alter_column(
        "tenant_overrides",
        "id",
        server_default=sa.text("gen_random_uuid()"),
        existing_type=sa.UUID(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "tenant_overrides",
        "id",
        server_default=None,
        existing_type=sa.UUID(),
        existing_nullable=False,
    )
