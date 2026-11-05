import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models import ConnectionStatus, GoCanvasProcessing


class GoCanvasConnectionWrite(BaseModel):
    """The client secret is write-only. Omit it to keep the stored value (required on first
    setup)."""

    client_id: str = Field(min_length=1, max_length=255)
    client_secret: str | None = Field(default=None, min_length=1, max_length=1024)


class GoCanvasConnectionRead(BaseModel):
    operator_id: uuid.UUID
    configured: bool
    client_id: str | None = None
    has_client_secret: bool = False
    status: ConnectionStatus | None = None
    last_verified_at: datetime | None = None
    last_error: str | None = None
    updated_at: datetime | None = None


class GoCanvasFormProcessingWrite(BaseModel):
    processing: GoCanvasProcessing


class GoCanvasFormProcessingRead(BaseModel):
    """A form's root id, whether it has processing set or has only been seen in a submission."""

    root_version_id: int
    # The newest version we hold; null for a root set by hand that nothing has arrived for.
    form_name: str | None = None
    processing: GoCanvasProcessing | None = None
    submission_count: int
    # Stored submissions nothing has run on yet.
    unprocessed_count: int


class GoCanvasFormProcessingList(BaseModel):
    items: list[GoCanvasFormProcessingRead]
