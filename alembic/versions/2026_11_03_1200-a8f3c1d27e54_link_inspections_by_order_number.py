"""link inspections by order number

Revision ID: a8f3c1d27e54
Revises: 7c41d9e2a6b3
Create Date: 2026-11-03 12:00:00.000000

An inspection's order field holds the OrderID or, on some, the order's number, and only the first
was linked. Links the stored inspections either way; an order stored after its inspection is
linked too. The links stay on downgrade: nothing reads them differently.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8f3c1d27e54"
down_revision: str | Sequence[str] | None = "7c41d9e2a6b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        UPDATE condition_inspections i SET service_order_id = o.id
        FROM conditions c, service_orders o
        WHERE c.id = i.condition_id
          AND i.service_order_id IS NULL
          AND i.pestpac_order_id > 0
          AND o.operator_id = c.operator_id
          AND o.pestpac_order_id = i.pestpac_order_id
        """
    )
    op.execute(
        """
        UPDATE condition_inspections i SET service_order_id = o.id
        FROM conditions c, service_orders o
        WHERE c.id = i.condition_id
          AND i.service_order_id IS NULL
          AND i.pestpac_order_id > 0
          AND o.operator_id = c.operator_id
          AND o.location_id = c.location_id
          AND o.order_number = i.pestpac_order_id::text
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
