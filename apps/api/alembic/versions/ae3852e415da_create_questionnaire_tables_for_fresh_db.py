"""Create questionnaire tables for fresh DB

Revision ID: ae3852e415da
Revises: 14a3f725d795
Create Date: 2026-02-16 20:01:45.976413

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "ae3852e415da"
down_revision: Union[str, Sequence[str], None] = "14a3f725d795"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(conn, name: str) -> bool:
    insp = sa.inspect(conn)
    return name in insp.get_table_names()


def upgrade() -> None:
    conn = op.get_bind()

    # questionnaire_templates
    if not _has_table(conn, "questionnaire_templates"):
        op.create_table(
            "questionnaire_templates",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("code", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("language", sa.Text(), nullable=False),
            sa.Column("version", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        op.create_index("ix_questionnaire_templates_code", "questionnaire_templates", ["code"], unique=True)

    # questionnaire_questions
    if not _has_table(conn, "questionnaire_questions"):
        op.create_table(
            "questionnaire_questions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("key", sa.Text(), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["template_id"], ["questionnaire_templates.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_questionnaire_questions_template_id", "questionnaire_questions", ["template_id"])
        op.create_index(
            "ux_questionnaire_questions_template_key",
            "questionnaire_questions",
            ["template_id", "key"],
            unique=True,
        )

    # tenant_answers
    if not _has_table(conn, "tenant_answers"):
        op.create_table(
            "tenant_answers",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("answer_text", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["question_id"], ["questionnaire_questions.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_tenant_answers_tenant_id", "tenant_answers", ["tenant_id"])
        op.create_index("ix_tenant_answers_question_id", "tenant_answers", ["question_id"])
        op.create_index(
            "ux_tenant_answers_tenant_question",
            "tenant_answers",
            ["tenant_id", "question_id"],
            unique=True,
        )

    # tenant_answer_evidence
    if not _has_table(conn, "tenant_answer_evidence"):
        op.create_table(
            "tenant_answer_evidence",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("answer_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["answer_id"], ["tenant_answers.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["evidence_id"], ["evidence_items.id"], ondelete="CASCADE"),
        )
        op.create_index("ix_tenant_answer_evidence_tenant_id", "tenant_answer_evidence", ["tenant_id"])
        op.create_index("ix_tenant_answer_evidence_answer_id", "tenant_answer_evidence", ["answer_id"])
        op.create_index("ix_tenant_answer_evidence_evidence_id", "tenant_answer_evidence", ["evidence_id"])
        op.create_index(
            "ux_tenant_answer_evidence_triplet",
            "tenant_answer_evidence",
            ["tenant_id", "answer_id", "evidence_id"],
            unique=True,
        )


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    tables = set(insp.get_table_names())

    # Drop in reverse order
    if "tenant_answer_evidence" in tables:
        op.drop_index("ux_tenant_answer_evidence_triplet", table_name="tenant_answer_evidence")
        op.drop_index("ix_tenant_answer_evidence_evidence_id", table_name="tenant_answer_evidence")
        op.drop_index("ix_tenant_answer_evidence_answer_id", table_name="tenant_answer_evidence")
        op.drop_index("ix_tenant_answer_evidence_tenant_id", table_name="tenant_answer_evidence")
        op.drop_table("tenant_answer_evidence")

    if "tenant_answers" in tables:
        op.drop_index("ux_tenant_answers_tenant_question", table_name="tenant_answers")
        op.drop_index("ix_tenant_answers_question_id", table_name="tenant_answers")
        op.drop_index("ix_tenant_answers_tenant_id", table_name="tenant_answers")
        op.drop_table("tenant_answers")

    if "questionnaire_questions" in tables:
        op.drop_index("ux_questionnaire_questions_template_key", table_name="questionnaire_questions")
        op.drop_index("ix_questionnaire_questions_template_id", table_name="questionnaire_questions")
        op.drop_table("questionnaire_questions")

    if "questionnaire_templates" in tables:
        op.drop_index("ix_questionnaire_templates_code", table_name="questionnaire_templates")
        op.drop_table("questionnaire_templates")
