import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.models.zone import Zone


class ClientFindingWrite(BaseModel):
    reported_on: date | None = None
    source: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    finding: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    zone: Zone | None = None
    severity: Literal["low", "medium", "high"]
    status: Literal["open", "closed"] = "open"
    select_response: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] | None
    ) = None


class ClientFindingRead(BaseModel):
    id: uuid.UUID
    reported_on: date | None
    logged_on: date
    source: str
    finding: str
    zone: str | None  # the zone's value
    zone_name: str | None  # as the operator names it
    severity: str
    status: str
    select_response: str | None
