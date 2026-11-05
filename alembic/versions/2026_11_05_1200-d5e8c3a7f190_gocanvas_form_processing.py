"""gocanvas form processing

Revision ID: d5e8c3a7f190
Revises: b3d7f1a94c28
Create Date: 2026-11-05 12:00:00.000000

Every submission a GoCanvas webhook names is stored, and a form's root id decides what processes
it. What's already held is copied in: risk forms, their submissions, and each root's processing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d5e8c3a7f190"
down_revision: str | None = "b3d7f1a94c28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

processing = postgresql.ENUM(
    "risk_assessment", "ipm_form", name="gocanvas_processing", create_type=False
)


def upgrade() -> None:
    processing.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "gocanvas_form_processing",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("root_version_id", sa.BigInteger(), nullable=False),
        sa.Column("processing", processing, nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["tenants.id"],
            name=op.f("fk_gocanvas_form_processing_operator_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_gocanvas_form_processing_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gocanvas_form_processing")),
        sa.UniqueConstraint(
            "operator_id", "root_version_id", name="uq_gocanvas_form_processing_operator_root"
        ),
    )
    op.create_index(
        op.f("ix_gocanvas_form_processing_operator_id"),
        "gocanvas_form_processing",
        ["operator_id"],
    )
    op.create_table(
        "gocanvas_forms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("gocanvas_form_id", sa.BigInteger(), nullable=False),
        sa.Column("root_version_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("definition", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["tenants.id"],
            name=op.f("fk_gocanvas_forms_operator_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gocanvas_forms")),
        sa.UniqueConstraint(
            "operator_id", "gocanvas_form_id", name="uq_gocanvas_forms_operator_form"
        ),
    )
    op.create_index(op.f("ix_gocanvas_forms_operator_id"), "gocanvas_forms", ["operator_id"])
    op.create_index(
        op.f("ix_gocanvas_forms_root_version_id"), "gocanvas_forms", ["root_version_id"]
    )
    op.create_table(
        "gocanvas_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("operator_id", sa.Uuid(), nullable=False),
        sa.Column("gocanvas_submission_id", sa.BigInteger(), nullable=False),
        sa.Column("gocanvas_form_id", sa.BigInteger(), nullable=True),
        sa.Column("root_version_id", sa.BigInteger(), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_as", processing, nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["tenants.id"],
            name=op.f("fk_gocanvas_submissions_operator_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gocanvas_submissions")),
        sa.UniqueConstraint(
            "operator_id", "gocanvas_submission_id", name="uq_gocanvas_submissions_operator_id"
        ),
    )
    op.create_index(
        op.f("ix_gocanvas_submissions_operator_id"), "gocanvas_submissions", ["operator_id"]
    )
    op.create_index(
        op.f("ix_gocanvas_submissions_root_version_id"),
        "gocanvas_submissions",
        ["root_version_id"],
    )

    # A form's first version is its own root.
    op.execute(
        """
        INSERT INTO gocanvas_forms
            (id, operator_id, gocanvas_form_id, root_version_id, name, version, definition,
             fetched_at)
        SELECT gen_random_uuid(), operator_id, gocanvas_form_id,
               COALESCE(gocanvas_root_version_id, gocanvas_form_id), name, version, definition,
               imported_at
        FROM inspection_forms
        """
    )
    op.execute(
        """
        INSERT INTO gocanvas_form_processing (id, operator_id, root_version_id, processing)
        SELECT gen_random_uuid(), operator_id, root_version_id, 'risk_assessment'
        FROM (
            SELECT DISTINCT operator_id,
                   COALESCE(gocanvas_root_version_id, gocanvas_form_id) AS root_version_id
            FROM inspection_forms
            WHERE kind = 'risk'
        ) AS roots
        """
    )
    op.execute(
        """
        INSERT INTO gocanvas_submissions
            (id, operator_id, gocanvas_submission_id, gocanvas_form_id, root_version_id, payload,
             payload_sha256, fetched_at, processed_as, processed_at)
        SELECT gen_random_uuid(), s.operator_id, s.gocanvas_submission_id, s.gocanvas_form_id,
               COALESCE(f.gocanvas_root_version_id, f.gocanvas_form_id), s.raw_payload,
               s.payload_sha256, now(), 'risk_assessment', now()
        FROM inspection_submissions s
        JOIN inspection_forms f ON f.id = s.form_id
        WHERE f.kind = 'risk'
        """
    )


def downgrade() -> None:
    op.drop_table("gocanvas_submissions")
    op.drop_table("gocanvas_forms")
    op.drop_table("gocanvas_form_processing")
    processing.drop(op.get_bind(), checkfirst=True)
