from alembic import op

revision = '42d3982ba451'
down_revision = '4c42a8852573'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ux_job_runs_tenant_type_idem",
        "job_runs",
        ["tenant_id", "job_type", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ux_job_runs_tenant_type_idem", table_name="job_runs")