"""bill to extract findings

Revision ID: 7c41d9e2a6b3
Revises: 140240b074ee
Create Date: 2026-11-02 16:00:00.000000

Moves the opt-in for findings extraction from the company to each of its bill-tos, which keep the
company's setting.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c41d9e2a6b3"
down_revision: str | Sequence[str] | None = "140240b074ee"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "bill_tos",
        sa.Column(
            "extract_findings", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.execute(
        """
        UPDATE bill_tos SET extract_findings = companies.extract_findings
        FROM companies WHERE companies.id = bill_tos.company_id
        """
    )
    op.drop_column("companies", "extract_findings")


def downgrade() -> None:
    """Downgrade schema. A company comes back on if any of its bill-tos was."""
    op.add_column(
        "companies",
        sa.Column(
            "extract_findings", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.execute(
        """
        UPDATE companies SET extract_findings = true
        WHERE id IN (SELECT company_id FROM bill_tos WHERE extract_findings)
        """
    )
    op.drop_column("bill_tos", "extract_findings")
