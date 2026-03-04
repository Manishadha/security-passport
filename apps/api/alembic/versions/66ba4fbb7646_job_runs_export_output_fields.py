"""job_runs export output fields

Revision ID: 66ba4fbb7646
Revises: 1a4a954f40d2
Create Date: 2026-02-26 13:50:59.908787
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "66ba4fbb7646"
down_revision: Union[str, Sequence[str], None] = "1a4a954f40d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # output artifact metadata
    op.add_column("job_runs", sa.Column("output_storage_key", sa.String(length=600), nullable=True))
    op.add_column("job_runs", sa.Column("output_filename", sa.String(length=512), nullable=True))
    op.add_column("job_runs", sa.Column("output_content_type", sa.String(length=200), nullable=True))
    op.add_column("job_runs", sa.Column("output_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("job_runs", sa.Column("output_sha256", sa.String(length=128), nullable=True))

    op.create_index("ix_job_runs_output_sha256", "job_runs", ["output_sha256"])


def downgrade() -> None:
    op.drop_index("ix_job_runs_output_sha256", table_name="job_runs")

    op.drop_column("job_runs", "output_sha256")
    op.drop_column("job_runs", "output_size_bytes")
    op.drop_column("job_runs", "output_content_type")
    op.drop_column("job_runs", "output_filename")
    op.drop_column("job_runs", "output_storage_key")