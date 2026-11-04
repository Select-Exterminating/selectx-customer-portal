"""assessment targets

Revision ID: a1c6e8f02b57
Revises: e7b2a9c4d1f3
Create Date: 2026-11-05 09:00:00.000000

How many of a company's restaurants in each state its risk assessment program covers.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1c6e8f02b57"
down_revision: str | None = "e7b2a9c4d1f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assessment_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=2), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "operator_id"],
            ["companies.id", "companies.operator_id"],
            name="fk_assessment_targets_company_operator",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assessment_targets")),
        sa.UniqueConstraint("company_id", "state", name="uq_assessment_targets_company_state"),
    )
    op.create_index(
        op.f("ix_assessment_targets_operator_id"), "assessment_targets", ["operator_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_assessment_targets_operator_id"), table_name="assessment_targets")
    op.drop_table("assessment_targets")
