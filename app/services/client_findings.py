"""What a customer's own people found at a store and told Select."""

import uuid
from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClientFinding
from app.schemas.client_findings import ClientFindingRead, ClientFindingWrite


def load(db: Session, location_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[ClientFinding]]:
    """Each location's findings, newest logged first."""
    found: dict[uuid.UUID, list[ClientFinding]] = defaultdict(list)
    if location_ids:
        for finding in db.scalars(
            select(ClientFinding)
            .where(ClientFinding.location_id.in_(location_ids))
            .order_by(ClientFinding.logged_on.desc(), ClientFinding.created_at.desc())
        ):
            found[finding.location_id].append(finding)
    return found


def apply(finding: ClientFinding, body: ClientFindingWrite) -> None:
    finding.reported_on = body.reported_on
    finding.source = body.source
    finding.finding = body.finding
    finding.zone = body.zone.value if body.zone else None
    finding.severity = body.severity
    finding.status = body.status
    finding.select_response = body.select_response or None


def create(
    db: Session,
    operator_id: uuid.UUID,
    location_id: uuid.UUID,
    body: ClientFindingWrite,
    user_id: uuid.UUID,
    today: date,
) -> ClientFinding:
    finding = ClientFinding(
        operator_id=operator_id,
        location_id=location_id,
        logged_on=today,
        logged_by_user_id=user_id,
    )
    apply(finding, body)
    db.add(finding)
    return finding


def read(finding: ClientFinding, zone_names: dict[str, str]) -> ClientFindingRead:
    return ClientFindingRead(
        id=finding.id,
        reported_on=finding.reported_on,
        logged_on=finding.logged_on,
        source=finding.source,
        finding=finding.finding,
        zone=finding.zone,
        zone_name=zone_names.get(finding.zone) if finding.zone else None,
        severity=finding.severity,
        status=finding.status,
        select_response=finding.select_response,
    )
