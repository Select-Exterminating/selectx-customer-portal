import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.zone import zone_check


class ClientFinding(Base):
    """Something a customer's own people found at a store (a food safety walk, EcoLab, the store
    team) and told Select, logged beside Select's reports. Closed, never deleted."""

    __tablename__ = "client_findings"
    __table_args__ = (
        CheckConstraint("zone IS NULL OR " + zone_check("zone"), name="client_finding_zone_value"),
        CheckConstraint("severity IN ('low', 'medium', 'high')", name="client_finding_severity"),
        CheckConstraint("status IN ('open', 'closed')", name="client_finding_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="RESTRICT"), index=True
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"), index=True
    )
    # When it was found, if known; `logged_on` is when Select heard, and starts the flag's window.
    reported_on: Mapped[date | None] = mapped_column(Date)
    logged_on: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(100))
    finding: Mapped[str] = mapped_column(Text)
    zone: Mapped[str | None] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10))
    select_response: Mapped[str | None] = mapped_column(Text)
    logged_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
