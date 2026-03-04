from alembic import op
import sqlalchemy as sa

revision = "00012914f2d7"
down_revision = "66ba4fbb7646"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE job_runs ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(200)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_job_runs_tenant_jobtype_idem "
        "ON job_runs (tenant_id, job_type, idempotency_key) "
        "WHERE idempotency_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_job_runs_tenant_jobtype_idem")
    op.execute("ALTER TABLE job_runs DROP COLUMN IF EXISTS idempotency_key")