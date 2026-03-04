from alembic import op
import sqlalchemy as sa
revision: str = '4c42a8852573'
down_revision = "00012914f2d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_runs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_job_runs_tenant_started", "job_runs", ["tenant_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_job_runs_tenant_started", table_name="job_runs")
    op.drop_column("job_runs", "started_at")