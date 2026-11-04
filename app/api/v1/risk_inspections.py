import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import BillTo, Company, Location, Tenant, TenantKind
from app.schemas.inspections import (
    RiskInspectionDetail,
    RiskInspectionListItem,
    RiskInspectionLocationUpdate,
    StoreCandidate,
)
from app.security.access import AccessScope, get_scope
from app.security.permissions import Perm
from app.services import inspections, risk_inspections

router = APIRouter(tags=["risk-inspections"])


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


@router.get(
    "/operators/{operator_id}/risk-inspections", response_model=list[RiskInspectionListItem]
)
def list_operator_risk_inspections(
    operator_id: uuid.UUID, db: Session = Depends(get_db), scope: AccessScope = Depends(get_scope)
):
    """All the operator's risk inspections, those without a store first, then newest first."""
    operator = db.get(Tenant, operator_id)
    if operator is None or operator.kind is not TenantKind.operator:
        raise _not_found()
    scope.require(Perm.bill_tos_read, operator.id, read_perm=Perm.bill_tos_read)
    return [
        risk_inspections.list_item(s) for s in risk_inspections.list_for_operator(db, operator.id)
    ]


@router.get("/companies/{company_id}/risk-inspections", response_model=list[RiskInspectionListItem])
def list_company_risk_inspections(
    company_id: uuid.UUID, db: Session = Depends(get_db), scope: AccessScope = Depends(get_scope)
):
    """Risk inspections of every location under the company's bill-tos, newest first."""
    company = db.get(Company, company_id)
    if company is None:
        raise _not_found()
    scope.require(Perm.bill_tos_read, company.operator_id, read_perm=Perm.companies_read)
    return [
        risk_inspections.list_item(s) for s in risk_inspections.list_for_company(db, company.id)
    ]


@router.get("/bill-tos/{bill_to_id}/risk-inspections", response_model=list[RiskInspectionListItem])
def list_bill_to_risk_inspections(
    bill_to_id: uuid.UUID, db: Session = Depends(get_db), scope: AccessScope = Depends(get_scope)
):
    """Risk inspections of the bill-to's locations, newest first."""
    bill_to = db.get(BillTo, bill_to_id)
    if bill_to is None:
        raise _not_found()
    scope.require(Perm.bill_tos_read, bill_to.operator_id, read_perm=Perm.bill_tos_read)
    return [
        risk_inspections.list_item(s) for s in risk_inspections.list_for_bill_to(db, bill_to.id)
    ]


@router.get(
    "/locations/{location_id}/risk-inspections", response_model=list[RiskInspectionListItem]
)
def list_location_risk_inspections(
    location_id: uuid.UUID, db: Session = Depends(get_db), scope: AccessScope = Depends(get_scope)
):
    """The location's risk inspections, newest first."""
    location = db.get(Location, location_id)
    if location is None:
        raise _not_found()
    scope.require(Perm.bill_tos_read, location.operator_id, read_perm=Perm.bill_tos_read)
    return [
        risk_inspections.list_item(s) for s in risk_inspections.list_for_location(db, location.id)
    ]


@router.get("/risk-inspections/{inspection_id}", response_model=RiskInspectionDetail)
def get_risk_inspection(
    inspection_id: uuid.UUID, db: Session = Depends(get_db), scope: AccessScope = Depends(get_scope)
):
    """One risk inspection with its zones, notes, photos (as stored file ids), and materials:
    what the RiskGate PDF report shows."""
    submission = risk_inspections.get(db, inspection_id)
    if submission is None:
        raise _not_found()
    scope.require(Perm.bill_tos_read, submission.operator_id, read_perm=Perm.bill_tos_read)
    return risk_inspections.detail(db, submission)


@router.get(
    "/risk-inspections/{inspection_id}/store-candidates", response_model=list[StoreCandidate]
)
def search_risk_inspection_stores(
    inspection_id: uuid.UUID,
    q: str = Query(min_length=1, max_length=200),
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    """Stores of the inspection's operator to link it to, searched by customer, name, address,
    or city."""
    submission = risk_inspections.get(db, inspection_id)
    if submission is None:
        raise _not_found()
    scope.require(Perm.bill_tos_read, submission.operator_id, read_perm=Perm.bill_tos_read)
    return risk_inspections.search_stores(db, submission.operator_id, q)


@router.put("/risk-inspections/{inspection_id}/location", response_model=RiskInspectionDetail)
def set_risk_inspection_location(
    inspection_id: uuid.UUID,
    body: RiskInspectionLocationUpdate,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    """Choose the inspection's store by hand. Automatic linking leaves it alone from then on, and
    its photos move to the store's company."""
    submission = risk_inspections.get(db, inspection_id)
    if submission is None:
        raise _not_found()
    scope.require(Perm.bill_tos_write, submission.operator_id, read_perm=Perm.bill_tos_read)
    location = db.get(Location, body.location_id)
    if (
        location is None
        or location.operator_id != submission.operator_id
        or location.removed_at is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Store not found"
        )
    inspections.choose_location(db, submission, location.id, scope.user_id)
    db.commit()
    db.expire(submission)
    return risk_inspections.detail(db, submission)
