"""client findings

Revision ID: b3d7f1a94c28
Revises: a1c6e8f02b57
Create Date: 2026-11-05 10:00:00.000000

Findings a customer's own people report to Select, logged by hand beside Select's reports.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models.zone import zone_check

revision: str = "b3d7f1a94c28"
down_revision: str | None = "a1c6e8f02b57"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=False),
        sa.Column("reported_on", sa.Date(), nullable=True),
        sa.Column("logged_on", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("finding", sa.Text(), nullable=False),
        sa.Column("zone", sa.String(length=40), nullable=True),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("select_response", sa.Text(), nullable=True),
        sa.Column("logged_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "zone IS NULL OR " + zone_check("zone"),
            name=op.f("ck_client_findings_client_finding_zone_value"),
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high')",
            name=op.f("ck_client_findings_client_finding_severity"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'closed')", name=op.f("ck_client_findings_client_finding_status")
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_client_findings_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["logged_by_user_id"],
            ["users.id"],
            name=op.f("fk_client_findings_logged_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["tenants.id"],
            name=op.f("fk_client_findings_operator_id_tenants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_client_findings")),
    )
    op.create_index(op.f("ix_client_findings_location_id"), "client_findings", ["location_id"])
    op.create_index(op.f("ix_client_findings_operator_id"), "client_findings", ["operator_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_client_findings_operator_id"), table_name="client_findings")
    op.drop_index(op.f("ix_client_findings_location_id"), table_name="client_findings")
    op.drop_table("client_findings")
