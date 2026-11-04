import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

# Every field is in the response, so the generated client types none of them as optional.
_ALL_REQUIRED = ConfigDict(json_schema_serialization_defaults_required=True)


class StoreRef(BaseModel):
    location_id: uuid.UUID
    store_number: str | None
    name: str | None
    city: str | None
    state: str | None


class Breakdown(BaseModel):
    """How often something was logged, with the stores it appeared at."""

    model_config = _ALL_REQUIRED

    label: str
    mentions: int
    stores: int
    remediated: int = 0


class CohortPoint(BaseModel):
    month: int  # months since the store's first visit; month 1 starts at that visit
    rated: int
    activity_rate: float
    stores: int


class ActivityMonth(BaseModel):
    month: str
    rated: int
    activity_rate: float | None
    heavy_rate: float | None
    captures: int


class RecentActivityStore(StoreRef):
    last_activity: date
    level: str
    zones: list[str]
    risk_index: int | None
    risk_band: str


class SpeciesOutcome(BaseModel):
    """Stores whose findings name one species, and how they stabilize."""

    model_config = _ALL_REQUIRED

    species: str
    stores: int
    stabilized: int
    median_days: float | None


class RodentActivityTab(BaseModel):
    cohort: list[CohortPoint]
    months: list[ActivityMonth]
    zones: list[Breakdown]
    species: list[SpeciesOutcome]
    recent: list[RecentActivityStore]


class StructuralMonth(BaseModel):
    month: str
    logged: int
    remediated: int


class OpenVulnerability(StoreRef):
    category: str
    zone: str
    where: str | None
    issue: str | None
    status: str
    last_reported: date


class StructuralTab(BaseModel):
    categories: list[Breakdown]
    zones: list[Breakdown]
    months: list[StructuralMonth]
    open: list[OpenVulnerability]


class ConcernMonth(BaseModel):
    month: str
    rated: int
    sanitation_share: float | None
    pest_share: float | None


class RecurringSanitationStore(StoreRef):
    visits_with_concerns: int
    visits: int
    share: float
    top_category: str | None


class SanitationTab(BaseModel):
    categories: list[Breakdown]
    zones: list[Breakdown]
    pests: list[Breakdown]
    months: list[ConcernMonth]
    stores: list[RecurringSanitationStore]


class TrackerRow(StoreRef):
    """A store's milestones, as far as worked orders show them. The steps before the work
    (requested, proposed, approved) aren't recorded anywhere we can read."""

    tier: str | None
    first_inspection: date | None
    first_service: date | None
    first_monitoring: date | None
    first_stabilized: date | None
    last_service: date | None
    services: int
    stage: str


class VisitTypeCount(BaseModel):
    label: str
    visits: int


class MonthVisits(BaseModel):
    month: str
    visits: int


class HealthGroup(BaseModel):
    label: str
    treated: int
    stabilized: int
    recurrence: int
    active: int


class PhaseActivity(BaseModel):
    """Activity in active intervention against scheduled monitoring, by the order's code."""

    model_config = _ALL_REQUIRED

    phase: str
    rated: int
    activity_rate: float | None
    heavy_rate: float | None


class CeilingReview(BaseModel):
    stores_assessed: int
    drop_ceilings: int  # assessed stores with a drop ceiling at the latest assessment
    zone_inspected: int
    zone_rodent_rate: float | None
    rodent_zone_stores: int
    activity_visit_share: float | None  # of visits with activity, those naming a ceiling


class FrontLineReview(BaseModel):
    dml_inspected: int
    dml_rodent_rate: float | None
    dml_visit_share: float | None
    front_inspected: int
    front_rodent_rate: float | None
    front_visit_share: float | None


class RecurrenceDrivers(BaseModel):
    active: int  # treated stores not stabilized; the shares below are of these
    structural: float | None
    operational: float | None
    environmental: float | None
    client_reported: int  # stores flagged by a client-reported finding


class SixMonthReview(BaseModel):
    stores: int  # with 6+ months since their first RAMP order
    stabilized: int
    activity_after: int
    gaps_with_activity: int
    activity_stores: list[StoreRef]


class ConditionRow(StoreRef):
    area: str | None
    category: str | None
    severity: str | None
    owner: str
    opened: date | None


class ConditionReview(BaseModel):
    found: int
    assigned: int
    open: int
    resolved: int
    owners: list[VisitTypeCount]
    high_open: list[ConditionRow]


class ExecutiveTab(BaseModel):
    inception: date | None
    through: date | None
    stores_serviced: int
    service_visits: int
    captures: int
    tiers: list[VisitTypeCount]  # stores per RAMP tier
    visit_types: list[VisitTypeCount]
    months: list[MonthVisits]
    treated: int
    stabilized_now: int
    active_now: int
    recurrence: int
    risk_start: float | None  # mean risk index, first 90 days of each treated store
    risk_now: float | None
    by_state: list[HealthGroup]
    by_tier: list[HealthGroup]
    phases: list[PhaseActivity]
    ceilings: CeilingReview
    front_line: FrontLineReview
    drivers: RecurrenceDrivers
    six_month: SixMonthReview
    conditions: ConditionReview
    cadence: list[VisitTypeCount]  # treated stores by the monitoring their record calls for


class ProgramTabs(BaseModel):
    """Everything the dashboard's findings tabs show: one call, since they share their loads."""

    as_of: date
    activity: RodentActivityTab
    structural: StructuralTab
    sanitation: SanitationTab
    tracker: list[TrackerRow]
    executive: ExecutiveTab


class AssessedStore(StoreRef):
    latitude: float | None
    longitude: float | None
    inspection_id: uuid.UUID
    assessed_on: date | None
    assessments: int
    inspector: str | None
    risk_index: float | None  # mean zone overall score / 5 x 100
    sanitation_index: float | None
    structural_index: float | None
    max_zone: int | None
    classification: str | None  # Critical/High/Moderate/Low, from the highest zone
    recommendation: str | None  # RAMP 1/2/3
    high_zones: int  # zones scored 3 or more
    rodent_zones: int
    pest_zones: int
    sweeps_failed: int
    in_program: bool
    first_index: float | None  # the first assessment's index, when there's more than one


class AssessmentZone(BaseModel):
    zone: str
    inspected: int
    rodent_rate: float
    pest_rate: float
    avg_overall: float | None
    avg_sanitation: float | None
    avg_structural: float | None
    tier3: int
    tier4: int
    tier5: int


class AssessmentTargetRow(BaseModel):
    state: str = Field(pattern=r"^[A-Z]{2}$")
    total: int = Field(ge=0, le=100_000)


class AssessmentTargets(BaseModel):
    targets: list[AssessmentTargetRow]


class StateCoverage(BaseModel):
    state: str
    in_program: int
    # The company's target for the state; none when it has none or the view is one bill-to's.
    target: int | None
    assessed: int
    avg_index: float | None
    high_or_critical: int
    with_rodents: int


class SiteCondition(BaseModel):
    attribute: str
    value: str
    stores: int


class RiskAssessmentDashboard(BaseModel):
    assessments: int
    zone_inspections: int
    first: date | None
    last: date | None
    unlinked: int  # submissions we couldn't match to a store
    stores: list[AssessedStore]
    zones: list[AssessmentZone]
    coverage: list[StateCoverage]
    site: list[SiteCondition]


class AssessmentFinding(StoreRef):
    inspection_id: uuid.UUID
    assessed_on: date | None
    zone: str
    kind: str  # Rodent/Pest/Structural/Sanitation/Note
    text: str


class AssessmentFindingPage(BaseModel):
    items: list[AssessmentFinding]
    total: int
    zones: list[str]


class GeneratedReport(StoreRef):
    id: uuid.UUID
    title: str  # the report template's name
    revision: int
    order_number: str | None
    work_date: date | None
    finalized_on: date | None


class ReportLibraryPage(BaseModel):
    items: list[GeneratedReport]
    total: int
