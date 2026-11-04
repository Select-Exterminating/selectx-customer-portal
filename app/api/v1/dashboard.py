import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import BillTo, Company, Location
from app.schemas.dashboard import CompanyDashboard
from app.schemas.program_dashboard import ProgramDashboard
from app.schemas.program_tabs import (
    AssessmentFindingPage,
    AssessmentTargets,
    ProgramTabs,
    ReportLibraryPage,
    RiskAssessmentDashboard,
)
from app.schemas.store_profile import StoreProfile
from app.security.access import AccessScope, get_scope
from app.security.permissions import Perm
from app.services import dashboard, program_metrics, program_tabs, store_profile

router = APIRouter(tags=["dashboard"])


@router.get("/companies/{company_id}/dashboard", response_model=CompanyDashboard)
def get_company_dashboard(
    company_id: uuid.UUID,
    bill_to_id: uuid.UUID | None = Query(default=None, description="Limit to one bill-to"),
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    # Open to the company's own users (company_manager).
    scope.require(
        Perm.dashboards_read,
        company.operator_id,
        read_perm=Perm.companies_read,
        company_id=company.id,
    )
    if bill_to_id is not None:
        bill_to = db.get(BillTo, bill_to_id)
        if bill_to is None or bill_to.company_id != company.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return dashboard.company_dashboard(db, company.id, bill_to_id)


@router.get("/companies/{company_id}/program-dashboard", response_model=ProgramDashboard)
def get_program_dashboard(
    company_id: uuid.UUID,
    bill_to_id: uuid.UUID | None = Query(default=None, description="Limit to one bill-to"),
    state: str | None = Query(default=None, max_length=2, description="Limit to one state"),
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    """Program results, Store Watch, and the risk index, from findings."""
    company = _scoped_company(db, scope, company_id, bill_to_id, company_users=True)
    return program_metrics.program_dashboard(
        db, company.id, bill_to_id=bill_to_id, state=state, today=date.today()
    )


def _scoped_company(
    db: Session,
    scope: AccessScope,
    company_id: uuid.UUID,
    bill_to_id: uuid.UUID | None,
    *,
    company_users: bool,
) -> Company:
    """The company, for a dashboard route. `company_users` lets the company's own users in."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    scope.require(
        Perm.dashboards_read,
        company.operator_id,
        read_perm=Perm.companies_read,
        company_id=company.id if company_users else None,
    )
    if bill_to_id is not None:
        bill_to = db.get(BillTo, bill_to_id)
        if bill_to is None or bill_to.company_id != company.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return company


@router.get("/companies/{company_id}/program-tabs", response_model=ProgramTabs)
def get_program_tabs(
    company_id: uuid.UUID,
    bill_to_id: uuid.UUID | None = Query(default=None, description="Limit to one bill-to"),
    state: str | None = Query(default=None, max_length=2, description="Limit to one state"),
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    """Rodent activity, structural, sanitation and pests, tracker, and executive review."""
    company = _scoped_company(db, scope, company_id, bill_to_id, company_users=True)
    return program_tabs.program_tabs(
        db,
        company.id,
        company.operator_id,
        bill_to_id=bill_to_id,
        state=state,
        today=date.today(),
    )


@router.get(
    "/companies/{company_id}/risk-assessment-dashboard",
    response_model=RiskAssessmentDashboard,
)
def get_risk_assessment_dashboard(
    company_id: uuid.UUID,
    bill_to_id: uuid.UUID | None = Query(default=None, description="Limit to one bill-to"),
    state: str | None = Query(default=None, max_length=2, description="Limit to one state"),
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    company = _scoped_company(db, scope, company_id, bill_to_id, company_users=True)
    return program_tabs.risk_assessment_dashboard(
        db, company.id, bill_to_id=bill_to_id, state=state
    )


@router.get(
    "/companies/{company_id}/risk-assessment-findings",
    response_model=AssessmentFindingPage,
)
def get_risk_assessment_findings(
    company_id: uuid.UUID,
    bill_to_id: uuid.UUID | None = Query(default=None, description="Limit to one bill-to"),
    state: str | None = Query(default=None, max_length=2, description="Limit to one state"),
    q: str | None = Query(default=None, max_length=200),
    kind: str | None = Query(default=None, max_length=20),
    zone: str | None = Query(default=None, max_length=300),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    company = _scoped_company(db, scope, company_id, bill_to_id, company_users=True)
    return program_tabs.assessment_findings(
        db,
        company.id,
        bill_to_id=bill_to_id,
        state=state,
        q=q,
        kind=kind,
        zone=zone,
        limit=limit,
        offset=offset,
    )


@router.get("/companies/{company_id}/stores/{location_id}/profile", response_model=StoreProfile)
def get_store_profile(
    company_id: uuid.UUID,
    location_id: uuid.UUID,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    """One store's flyover. Reports are listed only for callers who can open them."""
    company = _scoped_company(db, scope, company_id, None, company_users=True)
    location = db.get(Location, location_id)
    if (
        location is None
        or location.removed_at is not None
        or db.scalar(select(BillTo.company_id).where(BillTo.id == location.bill_to_id))
        != company.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return store_profile.store_profile(
        db,
        company,
        location,
        include_reports=scope.can(Perm.reports_read, company.operator_id),
        today=date.today(),
    )


@router.get("/companies/{company_id}/report-library", response_model=ReportLibraryPage)
def get_report_library(
    company_id: uuid.UUID,
    bill_to_id: uuid.UUID | None = Query(default=None, description="Limit to one bill-to"),
    state: str | None = Query(default=None, max_length=2, description="Limit to one state"),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    # Staff only: company users can't open report PDFs yet.
    company = _scoped_company(db, scope, company_id, bill_to_id, company_users=False)
    return program_tabs.report_library(
        db, company.id, bill_to_id=bill_to_id, state=state, q=q, limit=limit, offset=offset
    )


@router.get("/companies/{company_id}/assessment-targets", response_model=AssessmentTargets)
def get_assessment_targets(
    company_id: uuid.UUID, db: Session = Depends(get_db), scope: AccessScope = Depends(get_scope)
):
    """How many of the company's restaurants in each state its risk assessments cover."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    scope.require(Perm.companies_read, company.operator_id, read_perm=Perm.companies_read)
    return AssessmentTargets(targets=program_tabs.assessment_targets(db, company.id))


@router.put("/companies/{company_id}/assessment-targets", response_model=AssessmentTargets)
def put_assessment_targets(
    company_id: uuid.UUID,
    body: AssessmentTargets,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    """Replace the company's targets. A state left out has no target."""
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    scope.require(Perm.companies_write, company.operator_id, read_perm=Perm.companies_read)
    states = [row.state for row in body.targets]
    if len(set(states)) != len(states):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="A state is listed twice"
        )
    program_tabs.set_assessment_targets(db, company, body.targets)
    db.commit()
    return AssessmentTargets(targets=program_tabs.assessment_targets(db, company.id))
