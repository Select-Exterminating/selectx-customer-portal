"""gocanvas request processing

Revision ID: c4d9e7a1b2f6
Revises: a8f3c1d27e54
Create Date: 2026-11-03 18:00:00.000000

Risk form deliveries are now processed by the worker. Requests received before this have no
status and stay as they are.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4d9e7a1b2f6"
down_revision: str | None = "a8f3c1d27e54"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("gocanvas_requests", sa.Column("status", sa.String(length=20), nullable=True))
    op.add_column(
        "gocanvas_requests",
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
    )
    op.add_column(
        "gocanvas_requests",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("gocanvas_requests", sa.Column("detail", sa.String(length=1000), nullable=True))
    op.add_column(
        "gocanvas_requests", sa.Column("gocanvas_submission_id", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "gocanvas_requests", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        op.f("ix_gocanvas_requests_status"), "gocanvas_requests", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_gocanvas_requests_status"), table_name="gocanvas_requests")
    op.drop_column("gocanvas_requests", "processed_at")
    op.drop_column("gocanvas_requests", "gocanvas_submission_id")
    op.drop_column("gocanvas_requests", "detail")
    op.drop_column("gocanvas_requests", "next_attempt_at")
    op.drop_column("gocanvas_requests", "attempts")
    op.drop_column("gocanvas_requests", "status")
