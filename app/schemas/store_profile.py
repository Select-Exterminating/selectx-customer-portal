import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.schemas.client_findings import ClientFindingRead
from app.schemas.program_dashboard import WatchFlag

# Every field is in the response, so the generated client types none of them as optional.
_ALL_REQUIRED = ConfigDict(json_schema_serialization_defaults_required=True)


class ProfileNumbers(BaseModel):
    services: int
    inspections: int
    captures: int
    activity_rate: float | None
    activity_30d: int
    rated_30d: int
    structural_open: int
    days_since_service: int | None


class ProfileJourney(BaseModel):
    """Where a store started against where it is now. Dates that only the program tracker holds
    (requested, approved, abatement started) aren't known; first monitoring comes from orders."""

    model_config = _ALL_REQUIRED

    first_visit: date | None
    first_service: date | None
    first_rated: date | None
    start_index: int | None
    start_band: str
    start_activity: str | None
    last_rated: date | None
    now_index: int | None
    now_band: str
    now_activity: str | None
    index_change: int | None
    outcome: str | None
    stabilized_since: date | None
    first_stabilized: date | None
    days_to_stabilized: int | None
    recurrences: int
    clean_from_start: bool
    cadence: str | None
    cadence_why: str | None
    last_activity: date | None
    days_since_activity: int | None
    first_monitoring: date | None


class RiskPoints(BaseModel):
    activity: int
    structural: int
    sanitation: int
    pests: int


class TrendPoint(BaseModel):
    day: date
    index: int
    band: str
    activity: str
    visit_type: str | None
    summary: str | None


class ZoneMonths(BaseModel):
    zone: str
    total: int  # rated visits that found activity in this zone
    levels: list[int]  # the heaviest activity (0-3) in each of `ActivityGrid.months`


class ActivityGrid(BaseModel):
    months: list[str]  # YYYY-MM
    rated: list[int]  # rated visits in each month
    zones: list[ZoneMonths]


class ProfileVisit(BaseModel):
    """A visit: a location's worked orders on one date, merged."""

    day: date
    visit_type: str | None
    service: bool
    activity: str | None
    technicians: list[str]
    captures: int
    zones: list[str]
    evidence: list[str]
    summaries: list[str]
    report_id: uuid.UUID | None  # null unless the caller can open reports


class ProfileFinding(BaseModel):
    day: date
    kind: str
    category: str
    zone: str | None
    where: str | None
    issue: str | None
    status: str | None
    severity: str | None


class AssessmentZoneScore(BaseModel):
    zone: str
    areas: list[str]
    sanitation: int | None
    structural: int | None
    overall: int | None
    rodent: bool | None
    pest: bool | None
    pest_types: list[str]
    notes: list[str]


class ProfileAssessment(BaseModel):
    inspection_id: uuid.UUID
    day: date | None
    inspector: str | None
    classification: str | None
    risk_index: float | None
    sanitation_index: float | None
    structural_index: float | None
    max_zone: int | None
    recommendation: str | None
    rodent_zones: int
    pest_zones: int
    zones: list[AssessmentZoneScore]


class ProfileReport(BaseModel):
    id: uuid.UUID
    title: str
    revision: int
    work_date: date | None
    finalized_on: date | None


class StoreProfile(BaseModel):
    """Everything one store's flyover shows, in the RAMP portal's layout."""

    model_config = _ALL_REQUIRED

    location_id: uuid.UUID
    store_number: str | None
    name: str | None
    address: str | None
    city: str | None
    state: str | None
    as_of: date
    tier: str | None
    stage: str
    attention: str
    flags: list[WatchFlag]
    client_findings: list[ClientFindingRead]  # newest logged first
    team_director: str | None
    executive_team_director: str | None
    numbers: ProfileNumbers
    journey: ProfileJourney
    risk_points: RiskPoints | None
    trend: list[TrendPoint]
    activity_grid: ActivityGrid
    visits: list[ProfileVisit]  # newest first
    open_structural: list[ProfileFinding]
    recent_concerns: list[ProfileFinding]  # the latest 12 sanitation and pest findings
    assessments: list[ProfileAssessment]  # newest first
    reports: list[ProfileReport]  # empty unless the caller can open reports
