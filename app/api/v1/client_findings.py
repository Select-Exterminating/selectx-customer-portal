import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import ClientFinding, Location
from app.schemas.client_findings import ClientFindingRead, ClientFindingWrite
from app.security.access import AccessScope, get_scope
from app.security.permissions import Perm
from app.services import area_mapping, client_findings

router = APIRouter(tags=["client-findings"])


def _read(db: Session, finding: ClientFinding) -> ClientFindingRead:
    zones = area_mapping.zone_names(db, finding.operator_id)
    return client_findings.read(finding, {z.value: name for z, name in zones.items()})


@router.post(
    "/locations/{location_id}/client-findings",
    response_model=ClientFindingRead,
    status_code=status.HTTP_201_CREATED,
)
def log_client_finding(
    location_id: uuid.UUID,
    body: ClientFindingWrite,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    """Log what the customer's own people found at this store. Reading is on the store profile."""
    location = db.get(Location, location_id)
    if location is None or location.removed_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    scope.require(Perm.bill_tos_write, location.operator_id, read_perm=Perm.bill_tos_read)
    finding = client_findings.create(
        db, location.operator_id, location.id, body, scope.user_id, date.today()
    )
    db.commit()
    return _read(db, finding)


@router.put("/client-findings/{finding_id}", response_model=ClientFindingRead)
def update_client_finding(
    finding_id: uuid.UUID,
    body: ClientFindingWrite,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    """Edit a finding, or close it. Findings are never deleted."""
    finding = db.get(ClientFinding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    scope.require(Perm.bill_tos_write, finding.operator_id, read_perm=Perm.bill_tos_read)
    client_findings.apply(finding, body)
    db.commit()
    return _read(db, finding)
