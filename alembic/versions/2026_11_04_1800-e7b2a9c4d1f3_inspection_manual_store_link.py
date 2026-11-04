"""inspection manual store link

Revision ID: e7b2a9c4d1f3
Revises: c4d9e7a1b2f6
Create Date: 2026-11-04 18:00:00.000000

Records who chose an inspection's store by hand, so automatic linking leaves that store alone.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7b2a9c4d1f3"
down_revision: str | None = "c4d9e7a1b2f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inspection_submissions",
        sa.Column("location_linked_by_user_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "inspection_submissions",
        sa.Column("location_linked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_inspection_submissions_location_linked_by_user_id_users"),
        "inspection_submissions",
        "users",
        ["location_linked_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_inspection_submissions_location_linked_by_user_id_users"),
        "inspection_submissions",
        type_="foreignkey",
    )
    op.drop_column("inspection_submissions", "location_linked_at")
    op.drop_column("inspection_submissions", "location_linked_by_user_id")
