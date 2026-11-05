import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.pestpac import ConnectionStatus


class GoCanvasProcessing(enum.StrEnum):
    """What a stored submission is processed as. Changing the set needs a migration."""

    risk_assessment = "risk_assessment"
    ipm_form = "ipm_form"


class GoCanvasConnection(Base):
    """An operator's GoCanvas API access (OAuth client credentials). The client secret is Fernet
    ciphertext (app.security.secrets) and is never returned by the API."""

    __tablename__ = "gocanvas_connections"

    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    client_id: Mapped[str] = mapped_column(String(255))
    client_secret_enc: Mapped[str] = mapped_column(Text)

    status: Mapped[ConnectionStatus] = mapped_column(
        Enum(ConnectionStatus, name="gocanvas_connection_status"),
        default=ConnectionStatus.unverified,
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))

    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GoCanvasFormProcessing(Base):
    """How an operator's submissions are processed, by the form's `root_version_id`, which every
    version of a form shares. Set on the operator's GoCanvas API tab."""

    __tablename__ = "gocanvas_form_processing"
    __table_args__ = (
        UniqueConstraint(
            "operator_id", "root_version_id", name="uq_gocanvas_form_processing_operator_root"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    root_version_id: Mapped[int] = mapped_column(BigInteger)
    processing: Mapped[GoCanvasProcessing] = mapped_column(
        Enum(GoCanvasProcessing, name="gocanvas_processing")
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class GoCanvasForm(Base):
    """A GoCanvas form version's definition (GET /forms/{id}), fetched the first time one of its
    submissions arrives. It's how a submission, which only has `form_id`, gets its root."""

    __tablename__ = "gocanvas_forms"
    __table_args__ = (
        UniqueConstraint("operator_id", "gocanvas_form_id", name="uq_gocanvas_forms_operator_form"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    gocanvas_form_id: Mapped[int] = mapped_column(BigInteger)
    root_version_id: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(String(300))
    version: Mapped[int | None] = mapped_column(Integer)
    definition: Mapped[dict] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GoCanvasSubmission(Base):
    """The latest copy of every submission a webhook named, whatever its form. An edit keeps its
    submission id, so it replaces the copy. `processed_as` is what last ran on it: null means
    nothing has yet, because its form has no processing or that processing isn't built."""

    __tablename__ = "gocanvas_submissions"
    __table_args__ = (
        UniqueConstraint(
            "operator_id", "gocanvas_submission_id", name="uq_gocanvas_submissions_operator_id"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    gocanvas_submission_id: Mapped[int] = mapped_column(BigInteger)
    gocanvas_form_id: Mapped[int | None] = mapped_column(BigInteger)
    # Null until the form's definition has been fetched.
    root_version_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    payload_sha256: Mapped[str] = mapped_column(String(64))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_as: Mapped[GoCanvasProcessing | None] = mapped_column(
        Enum(GoCanvasProcessing, name="gocanvas_processing")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
