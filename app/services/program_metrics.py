"""Program metrics: per-store results, Store Watch, and the RAMP risk index, worked out from
worked orders and their findings, the way the Chipotle RAMP Intelligence Portal
(`../select-ramp-portal/public/js/core.js` and `watch.js`) works them out from its extracts.

A *visit* is a location's worked orders on one work date, merged (night services often post as
several orders). It's *rated* when one of them has findings with a rodent activity level. It's an
*inspection* rather than a service when its findings call it a risk assessment, entomology walk,
or QC inspection (a QC visit months before a store's program isn't its day one), or, without
findings, its service code is an inspection code; a program order (RAMP) is always a service. Codes
that aren't visits at all (travel, credits) are left out.

Everything is calculated on read from the scope's rows; the API returns summaries.
"""

import statistics
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillTo, InspectionFinding, InspectionFindingItem, Location, ServiceOrder
from app.schemas.program_dashboard import (
    CurvePoint,
    LabelCount,
    MonthTrend,
    Portfolio,
    ProgramDashboard,
    ProgramResults,
    StoreWatchRow,
    WatchFlag,
)
from app.services.dashboard import store_number

ACTIVITY_SCORE = {"none": 0, "low": 1, "moderate": 2, "heavy": 3}
ACTIVITY_LEVEL = {v: k for k, v in ACTIVITY_SCORE.items()}
INSPECTION_VISIT_TYPES = {"risk_assessment", "entomology_walk", "qc_inspection"}
INSPECTION_CODES = {"SPINSPCHG", "SPINSPNOCHG", "INSP-CHARGE", "INSP-NO CHARGE"}
# Program orders are services, whatever their notes read like.
PROGRAM_CODES = {"RAMP 1", "RAMP 2", "RAMP 3", "RAMP MONITOR"}
NON_VISIT_CODES = {"INTTRAVEL", "INTEXTRATECH", "BCREDIT", "CM"}
# The RAMP risk index (0-100) over the 90 days up to a store's latest rated visit.
RISK_WINDOW_DAYS = 90
RISK_POINTS = {"activity": 40, "structural": 25, "sanitation": 20, "pests": 15}
STRUCTURAL_CAP = 6
BANDS = ["Critical", "High", "Elevated", "Controlled", "No Service Data"]
# Stabilized (the portfolio standard): 28+ days since the last activity, every rated visit since
# clean, at least two of them.
STABILIZED_DAYS = 28
STABILIZED_VISITS = 2
ATTENTION = ["Escalated", "Watch", "Stable", "Not Yet Serviced"]
FLAG_LABELS = {
    "regress": ("Recurrence After Stabilization", "Recurrence"),
    "active": ("Active at Last Visit", "Active Now"),
    "repeat": ("Repeat Activity in Same Zone", "Repeat Zone"),
    "notclear": ("Not Yet Stabilized", "Not Yet Stable"),
    "rising": ("Rising Activity Trend", "Rising"),
    "exclusion": ("Exclusion Compromised", "Exclusion"),
    "structural": ("Open Structural Backlog", "Structural"),
    "sanitation": ("Recurring Sanitation Concerns", "Sanitation"),
}
TIME_TO_STABILIZED_BUCKETS = [
    (0, 35, "Within 5 Weeks"),
    (35, 49, "5–7 Weeks"),
    (49, 63, "7–9 Weeks"),
    (63, 91, "9–13 Weeks"),
    (91, 122, "3–4 Months"),
    (122, None, "4+ Months"),
]
SERVICE_BUCKETS = [
    (1, 6, "1–5 Services"),
    (6, 11, "6–10 Services"),
    (11, 21, "11–20 Services"),
    (21, 31, "21–30 Services"),
    (31, None, "31+ Services"),
]
CURVE_MIN_VISITS = 10  # two-week periods with fewer rated visits are left off the curve
CURVE_LAST_PERIOD = 12  # "Wk 24+"


@dataclass
class Visit:
    day: date
    service: bool = False
    activity: int | None = None  # 0-3; None when no order that day has an activity level
    captures: int = 0
    zones: set[str] = field(default_factory=set)
    structural: list[tuple[str, str, str]] = field(default_factory=list)  # category, zone, status
    sanitation: int = 0
    pests: set[str] = field(default_factory=set)
    exclusion: str | None = None
    visit_type: str | None = None


@dataclass
class StoreMetrics:
    location_id: uuid.UUID
    visits: list[Visit]
    tier: str | None  # the first RAMP 1/2/3 order's code
    services: int = 0
    inspections: int = 0
    captures: int = 0
    first_visit: date | None = None
    first_service: date | None = None
    last_service: date | None = None
    rated_visits: int = 0
    activity_visits: int = 0
    last_activity: date | None = None
    last_activity_level: str | None = None
    current_activity: str | None = None  # the latest rated visit's level
    stabilized_now: bool = False
    stabilized_since: date | None = None
    first_stabilized: date | None = None
    days_to_stabilized: int | None = None
    recurrences: int = 0
    structural_open: int = 0
    structural_remediated: int = 0
    risk_index: int | None = None
    risk_band: str = "No Service Data"
    flags: list[tuple[str, int, str]] = field(default_factory=list)  # code, weight, detail
    attention: str = "Not Yet Serviced"
    top_zone: str | None = None


# --- Loading -----------------------------------------------------------------------------------


def load_visits(db: Session, location_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[Visit]]:
    """Each location's visits, oldest first."""
    if not location_ids:
        return {}
    rows = db.execute(
        select(
            ServiceOrder.location_id,
            ServiceOrder.work_date,
            ServiceOrder.service_code,
            InspectionFinding.id,
            InspectionFinding.visit_type,
            InspectionFinding.rodent_activity,
            InspectionFinding.rodents_captured,
            InspectionFinding.activity_zones,
            InspectionFinding.exclusion_status,
        )
        .outerjoin(InspectionFinding, InspectionFinding.service_order_id == ServiceOrder.id)
        .where(
            ServiceOrder.location_id.in_(location_ids),
            ServiceOrder.posted.is_(True),
            ServiceOrder.work_date.is_not(None),
        )
    ).all()
    finding_ids = [r[3] for r in rows if r[3] is not None]
    items: dict[uuid.UUID, list] = defaultdict(list)
    for finding_id, kind, category, zone, status in db.execute(
        select(
            InspectionFindingItem.finding_id,
            InspectionFindingItem.kind,
            InspectionFindingItem.category,
            InspectionFindingItem.zone,
            InspectionFindingItem.status,
        ).where(InspectionFindingItem.finding_id.in_(finding_ids))
    ):
        items[finding_id].append((kind, category, zone, status))

    by_day: dict[tuple[uuid.UUID, date], Visit] = {}
    for (
        location_id,
        work_date,
        code,
        finding_id,
        visit_type,
        activity,
        captured,
        zones,
        excl,
    ) in rows:
        code = (code or "").strip().upper()
        if code in NON_VISIT_CODES:
            continue
        key = (location_id, work_date.date())
        visit = by_day.setdefault(key, Visit(day=key[1]))
        inspection = code not in PROGRAM_CODES and (
            visit_type in INSPECTION_VISIT_TYPES
            if finding_id is not None
            else code in INSPECTION_CODES
        )
        visit.service = visit.service or not inspection
        if visit_type and (visit.visit_type is None or not inspection):
            visit.visit_type = visit_type
        if activity is not None:
            visit.activity = max(visit.activity or 0, ACTIVITY_SCORE[activity])
        visit.captures += captured or 0
        visit.zones.update(zones or [])
        if excl == "compromised" or (excl and visit.exclusion is None):
            visit.exclusion = excl
        for kind, category, zone, status in items.get(finding_id, []):
            if kind == "structural":
                visit.structural.append((category, zone or "other", status or "open"))
            elif kind == "sanitation":
                visit.sanitation += 1
            elif kind == "pest":
                visit.pests.add(category)

    visits: dict[uuid.UUID, list[Visit]] = defaultdict(list)
    for (location_id, _), visit in sorted(by_day.items(), key=lambda kv: kv[0][1]):
        visits[location_id].append(visit)
    return visits


def load_tiers(db: Session, location_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Each location's RAMP tier: the code of its first RAMP 1/2/3 order."""
    tiers: dict[uuid.UUID, str] = {}
    for location_id, code in db.execute(
        select(ServiceOrder.location_id, ServiceOrder.service_code)
        .where(
            ServiceOrder.location_id.in_(location_ids),
            ServiceOrder.service_code.in_(["RAMP 1", "RAMP 2", "RAMP 3"]),
        )
        .order_by(ServiceOrder.work_date)
    ):
        tiers.setdefault(location_id, code)
    return tiers


# --- Per store -----------------------------------------------------------------------------------


def stabilization(rated: list[Visit]) -> tuple[bool, date | None, int, list[date]]:
    """(stabilized now, since when, index of the first stabilizing visit or -1, recurrence dates)
    over rated visits, oldest first."""
    anchor = rated[0].day if rated else None
    clean, now, since, first = 0, False, None, -1
    recurrences: list[date] = []
    for i, visit in enumerate(rated):
        if visit.activity > 0:
            if now:
                recurrences.append(visit.day)
            now, since, clean, anchor = False, None, 0, visit.day
            continue
        clean += 1
        if not now and clean >= STABILIZED_VISITS and (visit.day - anchor).days >= STABILIZED_DAYS:
            now, since = True, visit.day
            if first < 0:
                first = i
    return now, since, first, recurrences


def band_of(index: int | None) -> str:
    if index is None:
        return "No Service Data"
    if index >= 55:
        return "Critical"
    if index >= 35:
        return "High"
    if index >= 20:
        return "Elevated"
    return "Controlled"


def _structural_status(visits: list[Visit], since: date | None = None) -> dict[tuple, tuple]:
    """The latest status of each distinct structural finding (category and zone), with the date
    it was last logged."""
    latest: dict[tuple, tuple] = {}
    for visit in visits:
        for category, zone, status in visit.structural:
            if since is None or visit.day > since:
                latest[(category, zone)] = (status, visit.day)
    return latest


def store_metrics(
    location_id: uuid.UUID, visits: list[Visit], tier: str | None, as_of: date
) -> StoreMetrics:
    m = StoreMetrics(location_id=location_id, visits=visits, tier=tier)
    services = [v for v in visits if v.service]
    rated = [v for v in visits if v.activity is not None]
    m.services, m.inspections = len(services), len(visits) - len(services)
    m.captures = sum(v.captures for v in visits)
    m.first_visit = visits[0].day if visits else None
    m.first_service = services[0].day if services else None
    m.last_service = services[-1].day if services else (visits[-1].day if visits else None)
    m.rated_visits = len(rated)
    active = [v for v in rated if v.activity > 0]
    m.activity_visits = len(active)
    if active:
        m.last_activity = active[-1].day
        m.last_activity_level = ACTIVITY_LEVEL[active[-1].activity]
    m.current_activity = ACTIVITY_LEVEL[rated[-1].activity] if rated else None

    now, since, first, recurrences = stabilization(rated)
    m.stabilized_now, m.stabilized_since, m.recurrences = now, since, len(recurrences)
    if first >= 0:
        m.first_stabilized = rated[first].day
        if m.first_service:
            m.days_to_stabilized = max(0, (m.first_stabilized - m.first_service).days)

    statuses = _structural_status(visits)
    m.structural_remediated = sum(1 for s, _ in statuses.values() if s == "repaired")
    m.structural_open = len(statuses) - m.structural_remediated

    if rated:
        end = rated[-1].day
        window = [v for v in visits if (end - v.day).days < RISK_WINDOW_DAYS]
        window_rated = [v for v in window if v.activity is not None]
        open_recent = sum(
            1
            for s, logged in statuses.values()
            if s != "repaired" and (end - logged).days < RISK_WINDOW_DAYS
        )
        points = (
            (sum(v.activity for v in window_rated) / len(window_rated) / 3 if window_rated else 0)
            * RISK_POINTS["activity"]
            + min(open_recent, STRUCTURAL_CAP) / STRUCTURAL_CAP * RISK_POINTS["structural"]
            + sum(1 for v in window if v.sanitation) / len(window) * RISK_POINTS["sanitation"]
            + sum(1 for v in window if v.pests) / len(window) * RISK_POINTS["pests"]
        )
        m.risk_index = round(points)
    m.risk_band = band_of(m.risk_index)
    _watch(m, rated, services, recurrences, as_of)
    return m


def _watch(
    m: StoreMetrics, rated: list[Visit], services: list[Visit], recurrences: list[date], as_of
) -> None:
    """Store Watch flags and attention level (watch.js, without client-reported findings)."""

    def ago(d: date) -> int:
        return (as_of - d).days

    def add(code: str, weight: int, detail: str) -> None:
        m.flags.append((code, weight, detail))

    def fmt(d: date) -> str:
        return f"{d:%b} {d.day}, {d.year}"

    if not rated:
        m.attention = "Not Yet Serviced"
        return
    after = (
        [v for v in rated if v.day > m.first_stabilized and v.activity > 0]
        if m.first_stabilized
        else []
    )
    if after and ago(after[-1].day) <= 45:
        n = len(after)
        add(
            "regress",
            3,
            f"Stabilized {fmt(m.first_stabilized)}; activity on {n} "
            f"{'visit' if n == 1 else 'visits'} since, most recently {fmt(after[-1].day)}.",
        )
    last = rated[-1]
    if last.activity > 0 and ago(last.day) <= 45:
        where = f" in {', '.join(sorted(last.zones))}" if last.zones else ""
        add(
            "active",
            3 if last.activity >= 2 else 2,
            f"{ACTIVITY_LEVEL[last.activity].capitalize()} activity on {fmt(last.day)}{where}.",
        )
    zones = Counter(
        z for v in rated if ago(v.day) < 90 and v.activity > 0 for z in v.zones if z != "other"
    )
    if zones:
        m.top_zone, top = zones.most_common(1)[0]
        if top >= 3:
            add("repeat", 2, f"{m.top_zone}: activity on {top} visits in the last 90 days.")
    clean_from_start = len(rated) >= 2 and not any(v.activity > 0 for v in rated)
    if (
        not m.first_stabilized
        and not clean_from_start
        and m.first_service
        and ago(m.first_service) >= 60
        and m.last_activity
        and ago(m.last_activity) <= 60
    ):
        add("notclear", 2, f"{ago(m.first_service)} days since first service without stabilizing.")
    r30 = [v for v in rated if ago(v.day) < 30]
    r60 = [v for v in rated if 30 <= ago(v.day) < 90]
    if len(r30) >= 2 and len(r60) >= 2:
        rate30 = sum(v.activity > 0 for v in r30) / len(r30)
        rate60 = sum(v.activity > 0 for v in r60) / len(r60)
        if rate30 > 0 and rate30 - rate60 >= 0.25:
            add(
                "rising",
                1,
                f"{rate30:.0%} of visits in the last 30 days found activity, up from {rate60:.0%}.",
            )
    last_exclusion = next((v for v in reversed(m.visits) if v.exclusion), None)
    if (
        last_exclusion
        and last_exclusion.exclusion == "compromised"
        and ago(last_exclusion.day) <= 60
    ):
        add("exclusion", 1, f"Exclusion recorded as compromised on {fmt(last_exclusion.day)}.")
    if m.structural_open >= 5:
        add("structural", 1, f"{m.structural_open} distinct structural vulnerabilities still open.")
    last5 = m.visits[-5:]
    bad = sum(1 for v in last5 if v.sanitation)
    if len(last5) >= 3 and bad >= 3:
        add("sanitation", 1, f"Sanitation concerns on {bad} of the last {len(last5)} visits.")

    score = sum(w for _, w, _ in m.flags)
    codes = {c for c, _, _ in m.flags}
    heavy_now = any(c == "active" and w >= 3 for c, w, _ in m.flags)
    if score >= 7 or ("regress" in codes and (heavy_now or "repeat" in codes)):
        m.attention = "Escalated"
    elif score >= 2:
        m.attention = "Watch"
    else:
        m.attention = "Stable"


# --- Portfolio -----------------------------------------------------------------------------------


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _rate(visits: list[Visit], test) -> float | None:
    return sum(1 for v in visits if test(v)) / len(visits) if visits else None


def _bucket(value: int, buckets) -> str | None:
    for lo, hi, label in buckets:
        if value >= lo and (hi is None or value < hi):
            return label
    return None


def results(stores: list[StoreMetrics]) -> dict:
    """How fast stores stabilize, measured from each store's first service (a baseline risk
    assessment weeks earlier isn't day one)."""
    rows = []
    for s in stores:
        rated = [v for v in s.visits if v.activity is not None]
        first_service = next((i for i, v in enumerate(rated) if v.service), None)
        r = rated[first_service:] if first_service is not None else []
        if len(r) < 2:
            continue
        start = r[0].day
        intake = any(v.activity > 0 and (v.day - start).days <= 14 for v in r)
        _, _, first, _ = stabilization(r)
        after = r[first + 1 :] if first >= 0 else []
        rows.append(
            {
                "intake": intake,
                "cleared": intake and first >= 0,
                "days": (r[first].day - start).days if first >= 0 else None,
                "services_to_clear": sum(1 for v in r[: first + 1] if v.service)
                if first >= 0
                else None,
                "clean_after": _rate(after, lambda v: v.activity == 0),
                "current_clear": stabilization(r)[0],
                "services": s.services,
                "early": [v for v in r if (v.day - start).days < 15],
                "late": [v for v in r if (v.day - start).days >= 90],
            }
        )
    intake = [x for x in rows if x["intake"]]
    cleared = [x for x in intake if x["cleared"]]
    early = [v for x in rows for v in x["early"]]
    late = [v for x in rows for v in x["late"]]
    return {
        "stores_measured": len(rows),
        "intake_active": len(intake),
        "stabilized": len(cleared),
        "stabilized_share": len(cleared) / len(intake) if intake else None,
        "median_days": _median([x["days"] for x in cleared]),
        "median_services": _median([x["services_to_clear"] for x in cleared]),
        "clean_after": _median([x["clean_after"] for x in cleared if x["clean_after"] is not None]),
        "stabilized_now": sum(1 for x in intake if x["current_clear"]),
        "services_per_store": _median([x["services"] for x in rows]),
        "early_rate": _rate(early, lambda v: v.activity > 0),
        "late_rate": _rate(late, lambda v: v.activity > 0),
        "early_heavy": _rate(early, lambda v: v.activity == 3),
        "late_heavy": _rate(late, lambda v: v.activity == 3),
        "early_visits": len(early),
        "late_visits": len(late),
        "time_to_stabilized": [
            (label, sum(1 for x in cleared if _bucket(x["days"], [(lo, hi, label)])))
            for lo, hi, label in TIME_TO_STABILIZED_BUCKETS
        ],
        "services_per_ramp": [
            (label, sum(1 for x in rows if _bucket(x["services"], [(lo, hi, label)])))
            for lo, hi, label in SERVICE_BUCKETS
        ],
    }


def curve(stores: list[StoreMetrics]) -> list[dict]:
    """Share of rated visits finding activity by two-week period since each store's first
    visit."""
    cells: dict[int, list] = defaultdict(lambda: [0, 0, 0, set()])
    for s in stores:
        if not s.visits:
            continue
        first = s.visits[0].day
        for v in s.visits:
            if v.activity is None:
                continue
            k = min((v.day - first).days // 14, CURVE_LAST_PERIOD)
            c = cells[k]
            c[0] += 1
            c[1] += v.activity > 0
            c[2] += v.activity == 3
            c[3].add(s.location_id)
    out = []
    for k in sorted(cells):
        rated, active, heavy, stores_ = cells[k]
        if rated < CURVE_MIN_VISITS:
            continue
        label = "Wk 24+" if k == CURVE_LAST_PERIOD else f"Wk {k * 2}–{k * 2 + 2}"
        out.append(
            {
                "period": k,
                "label": label,
                "rated": rated,
                "activity_rate": active / rated,
                "heavy_rate": heavy / rated,
                "stores": len(stores_),
            }
        )
    return out


def monthly(stores: list[StoreMetrics]) -> list[dict]:
    cells: dict[str, list] = defaultdict(lambda: [0, 0, 0, 0])
    for s in stores:
        for v in s.visits:
            c = cells[f"{v.day:%Y-%m}"]
            c[0] += v.service
            if v.activity is not None:
                c[1] += 1
                c[2] += v.activity > 0
            c[3] += v.captures
    return [
        {
            "month": month,
            "services": c[0],
            "rated": c[1],
            "activity_visits": c[2],
            "activity_rate": c[2] / c[1] if c[1] else None,
            "captures": c[3],
        }
        for month, c in sorted(cells.items())
    ]


def portfolio(stores: list[StoreMetrics], as_of: date) -> dict:
    """Headline figures (core.js kpis)."""
    visits = [v for s in stores for v in s.visits if v.activity is not None]

    def window(lo: int, hi: int) -> list[Visit]:
        return [v for v in visits if lo <= (as_of - v.day).days < hi]

    last30, prev30 = window(0, 30), window(30, 60)
    free30 = _rate(last30, lambda v: v.activity == 0)
    free_prev = _rate(prev30, lambda v: v.activity == 0)
    logged = sum(s.structural_open + s.structural_remediated for s in stores)
    remediated = sum(s.structural_remediated for s in stores)
    return {
        "stores": len(stores),
        "stores_serviced": sum(1 for s in stores if s.services),
        "services": sum(s.services for s in stores),
        "inspections": sum(s.inspections for s in stores),
        "rated_30d": len(last30),
        "rodent_free_30d": free30,
        "rodent_free_change": free30 - free_prev
        if free30 is not None and free_prev is not None
        else None,
        "captures": sum(s.captures for s in stores),
        "structural_logged": logged,
        "structural_remediated": remediated,
        "remediation_rate": remediated / logged if logged else None,
        "stores_active_now": sum(1 for s in stores if s.current_activity not in (None, "none")),
        "bands": {b: sum(1 for s in stores if s.risk_band == b) for b in BANDS},
        "attention": {a: sum(1 for s in stores if s.attention == a) for a in ATTENTION},
        "recurrences": sum(1 for s in stores if any(c == "regress" for c, _, _ in s.flags)),
    }


def as_of_date(visits: dict[uuid.UUID, list[Visit]], today: date) -> date:
    """The latest visit on file, so day counts stay right as new reports land."""
    latest = max((vs[-1].day for vs in visits.values() if vs), default=None)
    return min(latest, today) if latest else today


def compute(db: Session, locations: list[Location], today: date) -> tuple[date, list[StoreMetrics]]:
    ids = [loc.id for loc in locations]
    visits = load_visits(db, ids)
    tiers = load_tiers(db, ids)
    as_of = as_of_date(visits, today)
    stores = [
        store_metrics(loc.id, visits.get(loc.id, []), tiers.get(loc.id), as_of) for loc in locations
    ]
    return as_of, stores


def flag_label(code: str) -> tuple[str, str]:
    """(label, short label)"""
    return FLAG_LABELS[code]


def program_dashboard(
    db: Session,
    company_id: uuid.UUID,
    *,
    bill_to_id: uuid.UUID | None = None,
    state: str | None = None,
    today: date,
) -> ProgramDashboard:
    bill_tos = select(BillTo.id).where(BillTo.company_id == company_id)
    if bill_to_id is not None:
        bill_tos = bill_tos.where(BillTo.id == bill_to_id)
    all_locations = list(
        db.scalars(
            select(Location).where(Location.bill_to_id.in_(bill_tos), Location.removed_at.is_(None))
        )
    )
    states = sorted({loc.state for loc in all_locations if loc.state})
    locations = [loc for loc in all_locations if state is None or loc.state == state]
    as_of, stores = compute(db, locations, today)
    by_id = {loc.id: loc for loc in locations}

    def row(s: StoreMetrics) -> StoreWatchRow:
        loc = by_id[s.location_id]
        rated = [v.activity for v in s.visits if v.activity is not None]
        return StoreWatchRow(
            location_id=loc.id,
            store_number=store_number(loc.pestpac_company),
            name=loc.description or loc.pestpac_company,
            city=loc.city,
            state=loc.state,
            latitude=loc.latitude,
            longitude=loc.longitude,
            tier=s.tier,
            attention=s.attention,
            flags=[
                WatchFlag(
                    code=code,
                    label=FLAG_LABELS[code][0],
                    short=FLAG_LABELS[code][1],
                    weight=weight,
                    detail=detail,
                )
                for code, weight, detail in sorted(s.flags, key=lambda f: -f[1])
            ],
            risk_index=s.risk_index,
            risk_band=s.risk_band,
            services=s.services,
            current_activity=s.current_activity,
            last_activity=s.last_activity,
            days_since_activity=(as_of - s.last_activity).days if s.last_activity else None,
            last_service=s.last_service,
            stabilized_now=s.stabilized_now,
            stabilized_since=s.stabilized_since,
            days_to_stabilized=s.days_to_stabilized,
            structural_open=s.structural_open,
            spark=rated[-12:],
        )

    def urgency(s: StoreMetrics):
        return (ATTENTION.index(s.attention), -sum(w for _, w, _ in s.flags), -(s.risk_index or 0))

    r = results(stores)
    p = portfolio(stores, as_of)
    return ProgramDashboard(
        company_id=company_id,
        bill_to_id=bill_to_id,
        state=state,
        states=states,
        as_of=as_of,
        results=ProgramResults(
            **{k: v for k, v in r.items() if k not in ("time_to_stabilized", "services_per_ramp")},
            time_to_stabilized=[LabelCount(label=a, stores=n) for a, n in r["time_to_stabilized"]],
            services_per_ramp=[LabelCount(label=a, stores=n) for a, n in r["services_per_ramp"]],
        ),
        portfolio=Portfolio(
            **{k: v for k, v in p.items() if k not in ("bands", "attention")},
            bands=[LabelCount(label=b, stores=n) for b, n in p["bands"].items()],
            attention=[LabelCount(label=a, stores=n) for a, n in p["attention"].items()],
        ),
        curve=[CurvePoint(**c) for c in curve(stores)],
        monthly=[MonthTrend(**m) for m in monthly(stores)],
        stores=[row(s) for s in sorted(stores, key=urgency) if s.visits],
    )
