import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

# Every field is in the response, so the generated client types none of them as optional.
_ALL_REQUIRED = ConfigDict(json_schema_serialization_defaults_required=True)


class LabelCount(BaseModel):
    label: str
    stores: int


class ProgramResults(BaseModel):
    """How fast stores stabilize, measured from each store's first service."""

    model_config = _ALL_REQUIRED

    stores_measured: int  # stores with two or more rated visits from their first service
    intake_active: int  # with rodent activity in their first two weeks
    stabilized: int  # of those, how many reached Stabilized
    stabilized_share: float | None
    median_days: float | None  # first service to Stabilized
    median_services: float | None
    clean_after: float | None  # median share of clean visits after stabilizing
    stabilized_now: int
    services_per_store: float | None
    early_rate: float | None  # share of rated visits with activity, first two weeks
    late_rate: float | None  # day 90 onward
    early_heavy: float | None
    late_heavy: float | None
    early_visits: int
    late_visits: int
    time_to_stabilized: list[LabelCount]
    services_per_ramp: list[LabelCount]


class CurvePoint(BaseModel):
    period: int  # two-week periods since the store's first visit; the last is "24 weeks on"
    label: str
    rated: int
    activity_rate: float
    heavy_rate: float
    stores: int


class MonthTrend(BaseModel):
    model_config = _ALL_REQUIRED

    month: str  # YYYY-MM
    services: int
    rated: int
    activity_visits: int
    activity_rate: float | None
    captures: int


class Portfolio(BaseModel):
    model_config = _ALL_REQUIRED

    stores: int
    stores_serviced: int
    services: int
    inspections: int
    rated_30d: int
    rodent_free_30d: float | None
    rodent_free_change: float | None  # vs. the 30 days before
    captures: int
    structural_logged: int
    structural_remediated: int
    remediation_rate: float | None
    stores_active_now: int
    recurrences: int  # stores flagged for recurrence after stabilization
    bands: list[LabelCount]  # Critical, High, Elevated, Controlled, No Service Data
    attention: list[LabelCount]  # Escalated, Watch, Stable, Not Yet Serviced


class WatchFlag(BaseModel):
    code: str
    label: str
    short: str
    weight: int
    detail: str


class StoreWatchRow(BaseModel):
    model_config = _ALL_REQUIRED

    location_id: uuid.UUID
    store_number: str | None
    name: str | None  # our store name (description), else PestPac's
    city: str | None
    state: str | None
    latitude: float | None
    longitude: float | None
    tier: str | None  # first RAMP 1/2/3 order
    attention: str
    flags: list[WatchFlag]
    risk_index: int | None
    risk_band: str
    services: int
    current_activity: str | None
    last_activity: date | None
    days_since_activity: int | None
    last_service: date | None
    stabilized_now: bool
    stabilized_since: date | None
    days_to_stabilized: int | None
    structural_open: int
    spark: list[int]  # activity score (0-3) of the last 12 rated visits, oldest first


class ProgramDashboard(BaseModel):
    """Program results, worked out from worked orders and their findings."""

    model_config = _ALL_REQUIRED

    company_id: uuid.UUID
    bill_to_id: uuid.UUID | None
    state: str | None
    states: list[str]  # the scope's states, for the market filter
    as_of: date  # the latest visit on file
    results: ProgramResults
    portfolio: Portfolio
    curve: list[CurvePoint]
    monthly: list[MonthTrend]
    stores: list[StoreWatchRow]  # stores with any visit, most urgent first
