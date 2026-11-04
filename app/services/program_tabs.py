"""The program dashboard's other tabs: rodent activity, structural, sanitation and pests, the store
tracker, the executive review, risk assessments, and the generated reports, laid out like the RAMP
portal's. Findings tabs read the same visits as `program_metrics`; risk assessments read the
GoCanvas submissions (`risk_inspections`), scored like the portal's `build_assessments.py`.

Everything is calculated on read and scoped to one company.
"""

import re
import statistics
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import (
    AssessmentTarget,
    BillTo,
    Company,
    Condition,
    InspectionFinding,
    InspectionFindingItem,
    InspectionForm,
    InspectionKind,
    InspectionSubmission,
    Location,
    Report,
    ReportStatus,
    ReportTemplate,
    RiskInspectionSummary,
    RiskInspectionZone,
    ServiceOrder,
)
from app.schemas.program_tabs import (
    ActivityMonth,
    AssessedStore,
    AssessmentFinding,
    AssessmentFindingPage,
    AssessmentTargetRow,
    AssessmentZone,
    Breakdown,
    CeilingReview,
    CohortPoint,
    ConcernMonth,
    ConditionReview,
    ConditionRow,
    ExecutiveTab,
    FrontLineReview,
    GeneratedReport,
    HealthGroup,
    MonthVisits,
    OpenVulnerability,
    PhaseActivity,
    ProgramTabs,
    RecentActivityStore,
    RecurrenceDrivers,
    RecurringSanitationStore,
    ReportLibraryPage,
    RiskAssessmentDashboard,
    RodentActivityTab,
    SanitationTab,
    SiteCondition,
    SixMonthReview,
    SpeciesOutcome,
    StateCoverage,
    StoreRef,
    StructuralMonth,
    StructuralTab,
    TrackerRow,
    VisitTypeCount,
)
from app.services import area_mapping
from app.services.dashboard import store_name, store_number
from app.services.program_metrics import (
    ACTIVITY_LEVEL,
    INSPECTION_CODES,
    NON_VISIT_CODES,
    PROGRAM_CODES,
    RISK_WINDOW_DAYS,
    StoreMetrics,
    Visit,
    compute,
    store_metrics,
)

COHORT_MONTHS = 11
RECENT_STORES = 50
MONITOR_CODE = "RAMP MONITOR"
RAMP_CODES = PROGRAM_CODES - {MONITOR_CODE}
# Sanitation concerns on this many visits make a store "recurring".
RECURRING_VISITS = 3


def _locations(
    db: Session, company_id: uuid.UUID, bill_to_id: uuid.UUID | None, state: str | None
) -> list[Location]:
    bill_tos = select(BillTo.id).where(BillTo.company_id == company_id)
    if bill_to_id is not None:
        bill_tos = bill_tos.where(BillTo.id == bill_to_id)
    query = select(Location).where(Location.bill_to_id.in_(bill_tos), Location.removed_at.is_(None))
    if state is not None:
        query = query.where(Location.state == state)
    return list(db.scalars(query))


def _ref(loc: Location) -> dict:
    return {
        "location_id": loc.id,
        "store_number": store_number(loc.pestpac_company),
        "name": store_name(loc),
        "city": loc.city,
        "state": loc.state,
    }


def _rate(hits: int, total: int) -> float | None:
    return hits / total if total else None


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


@dataclass
class Item:
    location_id: uuid.UUID
    day: date
    kind: str
    category: str
    zone: str
    status: str | None
    where: str | None
    issue: str | None


def _load_items(db: Session, location_ids: list[uuid.UUID]) -> list[Item]:
    """Every finding item of the locations' worked orders, oldest first."""
    if not location_ids:
        return []
    rows = db.execute(
        select(
            ServiceOrder.location_id,
            ServiceOrder.work_date,
            InspectionFindingItem.kind,
            InspectionFindingItem.category,
            InspectionFindingItem.zone,
            InspectionFindingItem.status,
            InspectionFindingItem.location,
            InspectionFindingItem.issue,
        )
        .join(InspectionFinding, InspectionFinding.id == InspectionFindingItem.finding_id)
        .join(ServiceOrder, ServiceOrder.id == InspectionFinding.service_order_id)
        .where(
            ServiceOrder.location_id.in_(location_ids),
            ServiceOrder.posted.is_(True),
            ServiceOrder.work_date.is_not(None),
            ServiceOrder.service_code.not_in(NON_VISIT_CODES),
        )
        .order_by(ServiceOrder.work_date)
    ).all()
    return [
        Item(loc, worked.date(), kind, category, zone or "other", status, where, issue)
        for loc, worked, kind, category, zone, status, where, issue in rows
    ]


def _breakdown(items: list[Item], key) -> list[Breakdown]:
    groups: dict[str, list[Item]] = defaultdict(list)
    for item in items:
        groups[key(item)].append(item)
    out = [
        Breakdown(
            label=label,
            mentions=len(group),
            stores=len({i.location_id for i in group}),
            remediated=sum(1 for i in group if i.status == "repaired"),
        )
        for label, group in groups.items()
    ]
    return sorted(out, key=lambda b: (-b.mentions, b.label))


def _activity(
    stores: list[StoreMetrics],
    by_id: dict[uuid.UUID, Location],
    names: dict,
    species: dict[uuid.UUID, set[str]],
) -> RodentActivityTab:
    cohort: dict[int, list] = defaultdict(lambda: [0, 0, set()])
    months: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # rated, active, heavy, caught
    zones: dict[str, list] = defaultdict(lambda: [0, set()])
    for s in stores:
        for v in s.visits:
            month = v.day.strftime("%Y-%m")
            months[month][3] += v.captures
            if v.activity is None:
                continue
            program_month = (v.day - s.visits[0].day).days // 30 + 1
            if program_month <= COHORT_MONTHS:
                cell = cohort[program_month]
                cell[0] += 1
                cell[1] += v.activity > 0
                cell[2].add(s.location_id)
            months[month][0] += 1
            months[month][1] += v.activity > 0
            months[month][2] += v.activity == 3
            if v.activity > 0:
                for zone in v.zones:
                    zones[zone][0] += 1
                    zones[zone][1].add(s.location_id)

    recent = []
    for s in sorted(stores, key=lambda s: s.last_activity or date.min, reverse=True):
        rated = [v for v in s.visits if v.activity is not None]
        if not rated or rated[-1].activity == 0:
            continue
        last = rated[-1]
        recent.append(
            RecentActivityStore(
                **_ref(by_id[s.location_id]),
                last_activity=last.day,
                level=ACTIVITY_LEVEL[last.activity],
                zones=sorted(names.get(z, z) for z in last.zones),
                risk_index=s.risk_index,
                risk_band=s.risk_band,
            )
        )

    outcomes = []
    for kind, label in (("rat", "Rats"), ("mouse", "Mice")):
        group = [
            s
            for s in stores
            if s.services
            and kind in species.get(s.location_id, set())
            and len(species[s.location_id]) == 1
        ]
        days = [s.days_to_stabilized for s in group if s.days_to_stabilized is not None]
        outcomes.append(
            SpeciesOutcome(
                species=label,
                stores=len(group),
                stabilized=sum(1 for s in group if s.stabilized_now),
                median_days=_median(days),
            )
        )

    return RodentActivityTab(
        cohort=[
            CohortPoint(month=m, rated=c[0], activity_rate=c[1] / c[0], stores=len(c[2]))
            for m, c in sorted(cohort.items())
        ],
        months=[
            ActivityMonth(
                month=m,
                rated=c[0],
                activity_rate=_rate(c[1], c[0]),
                heavy_rate=_rate(c[2], c[0]),
                captures=c[3],
            )
            for m, c in sorted(months.items())
        ],
        zones=sorted(
            (
                Breakdown(label=names.get(z, z), mentions=c[0], stores=len(c[1]))
                for z, c in zones.items()
            ),
            key=lambda b: -b.mentions,
        ),
        species=outcomes,
        recent=recent[:RECENT_STORES],
    )


def _structural(items: list[Item], by_id: dict[uuid.UUID, Location], names: dict) -> StructuralTab:
    structural = [i for i in items if i.kind == "structural"]
    months: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    latest: dict[tuple, Item] = {}
    for item in structural:  # oldest first, so the latest report of each wins
        month = item.day.strftime("%Y-%m")
        months[month][0] += 1
        months[month][1] += item.status == "repaired"
        latest[(item.location_id, item.category, item.zone)] = item
    still_open = sorted(
        (i for i in latest.values() if i.status != "repaired"),
        key=lambda i: i.day,
        reverse=True,
    )
    return StructuralTab(
        categories=_breakdown(structural, lambda i: i.category),
        zones=_breakdown(structural, lambda i: names.get(i.zone, i.zone)),
        months=[
            StructuralMonth(month=m, logged=c[0], remediated=c[1])
            for m, c in sorted(months.items())
        ],
        open=[
            OpenVulnerability(
                **_ref(by_id[i.location_id]),
                category=i.category,
                zone=names.get(i.zone, i.zone),
                where=i.where,
                issue=i.issue,
                status=i.status or "open",
                last_reported=i.day,
            )
            for i in still_open
        ],
    )


def _sanitation(
    stores: list[StoreMetrics],
    items: list[Item],
    by_id: dict[uuid.UUID, Location],
    names: dict,
) -> SanitationTab:
    sanitation = [i for i in items if i.kind == "sanitation"]
    pests = [i for i in items if i.kind == "pest"]
    months: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    recurring = []
    tops: dict[uuid.UUID, Counter] = defaultdict(Counter)
    for item in sanitation:
        tops[item.location_id][item.category] += 1
    for s in stores:
        with_concerns = 0
        for v in s.visits:
            month = v.day.strftime("%Y-%m")
            months[month][0] += 1
            months[month][1] += v.sanitation > 0
            months[month][2] += bool(v.pests)
            with_concerns += v.sanitation > 0
        if with_concerns >= RECURRING_VISITS:
            top = tops[s.location_id].most_common(1)
            recurring.append(
                RecurringSanitationStore(
                    **_ref(by_id[s.location_id]),
                    visits_with_concerns=with_concerns,
                    visits=len(s.visits),
                    share=with_concerns / len(s.visits),
                    top_category=top[0][0] if top else None,
                )
            )
    return SanitationTab(
        categories=_breakdown(sanitation, lambda i: i.category),
        zones=_breakdown(sanitation, lambda i: names.get(i.zone, i.zone)),
        pests=_breakdown(pests, lambda i: i.category),
        months=[
            ConcernMonth(
                month=m,
                rated=c[0],
                sanitation_share=_rate(c[1], c[0]),
                pest_share=_rate(c[2], c[0]),
            )
            for m, c in sorted(months.items())
        ],
        stores=sorted(recurring, key=lambda r: -r.visits_with_concerns),
    )


def _stage(s: StoreMetrics, first_monitoring: date | None) -> str:
    if not s.services:
        return "Inspected only" if s.visits else "Not started"
    if s.stabilized_now:
        return "Stabilized"
    return "Monitoring" if first_monitoring else "Active intervention"


def _order_dates(
    db: Session, location_ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, date], Counter, Counter, dict[str, list[int]]]:
    """Each location's first monitoring order; distinct visits by code and by month; activity by
    program phase (rated orders: count, with activity, heavy)."""
    first_monitoring: dict[uuid.UUID, date] = {}
    by_code: Counter = Counter()
    by_month: Counter = Counter()
    phases: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    seen: set[tuple] = set()
    if not location_ids:
        return first_monitoring, by_code, by_month, phases
    rows = db.execute(
        select(
            ServiceOrder.location_id,
            ServiceOrder.work_date,
            ServiceOrder.service_code,
            InspectionFinding.rodent_activity,
        )
        .outerjoin(InspectionFinding, InspectionFinding.service_order_id == ServiceOrder.id)
        .where(
            ServiceOrder.location_id.in_(location_ids),
            ServiceOrder.posted.is_(True),
            ServiceOrder.work_date.is_not(None),
        )
        .order_by(ServiceOrder.work_date)
    )
    for location_id, worked, code, activity in rows:
        code = (code or "").strip().upper()
        if code in NON_VISIT_CODES:
            continue
        day = worked.date()
        if code == MONITOR_CODE:
            first_monitoring.setdefault(location_id, day)
        label = (
            code
            if code in RAMP_CODES
            else "RAMP Monitoring"
            if code == MONITOR_CODE
            else "Risk assessments and inspections"
            if code in INSPECTION_CODES
            else "Other services"
        )
        if (location_id, day, label) not in seen:
            seen.add((location_id, day, label))
            by_code[label] += 1
        if (location_id, day) not in seen:
            seen.add((location_id, day))
            by_month[day.strftime("%Y-%m")] += 1
        if activity is not None and (code in RAMP_CODES or code == MONITOR_CODE):
            phase = phases["Monitoring" if code == MONITOR_CODE else "RAMP"]
            phase[0] += 1
            phase[1] += activity != "none"
            phase[2] += activity == "heavy"
    return first_monitoring, by_code, by_month, phases


def _cadence(s: StoreMetrics, as_of: date) -> str | None:
    """The monitoring a store's condition calls for: the portal's risk-based cadence (`watch.js`).
    None until a store has a service and two rated visits."""
    rated = [v for v in s.visits if v.activity is not None]
    if len(rated) < 2 or not s.services:
        return None

    def ago(v: Visit) -> int:
        return (as_of - v.day).days

    codes = {code for code, _, _ in s.flags}
    last4 = [v for v in rated if ago(v) <= 90][-4:]
    if (len(last4) >= 3 and sum(v.activity > 0 for v in last4) >= 3) or "notclear" in codes:
        return "Full Reassessment"
    if any(v.activity > 0 and "basement" in v.zones for v in rated if ago(v) <= 90):
        return "Maintain Weekly"
    if any(v.activity > 0 and ago(v) <= 30 for v in rated):
        return "Four-Week Weekly Escalation"
    if s.structural_open >= 5 or "exclusion" in codes:
        return "Elevated Permanent Cadence"
    return "Monthly Validation" if s.stabilized_now else "Program Cadence"


def _health(groups: dict[str, list[StoreMetrics]]) -> list[HealthGroup]:
    return [
        HealthGroup(
            label=label,
            treated=len(group),
            stabilized=sum(1 for s in group if s.stabilized_now),
            recurrence=sum(1 for s in group if s.recurrences),
            active=sum(1 for s in group if not s.stabilized_now),
        )
        for label, group in sorted(groups.items(), key=lambda kv: -len(kv[1]))
    ]


DRIVER_DAYS = 90
SIX_MONTHS_DAYS = 183
SERVICE_GAP_DAYS = 21
ENVIRONMENTAL_ZONES = {"exterior_perimeter", "dumpster_waste", "shared_structures"}
CONDITION_OWNERS = {"Customer": "Customer", "PestManagement": "Select"}


def _activity_locations(db: Session, ids: list[uuid.UUID]) -> list[str]:
    """Each visit with activity: the words of where it was found, a location's orders on one date
    merged, for measures that need the technician's words rather than the zones."""
    visits: dict[tuple, list[str]] = defaultdict(list)
    for location_id, work_date, places in db.execute(
        select(
            ServiceOrder.location_id, ServiceOrder.work_date, InspectionFinding.activity_locations
        )
        .join(InspectionFinding, InspectionFinding.service_order_id == ServiceOrder.id)
        .where(
            ServiceOrder.location_id.in_(ids),
            ServiceOrder.posted.is_(True),
            ServiceOrder.work_date.is_not(None),
            InspectionFinding.rodent_activity.is_not(None),
            InspectionFinding.rodent_activity != "none",
        )
    ):
        visits[(location_id, work_date.date())].extend(places or [])
    return [" ".join(places).lower() for places in visits.values()]


def _share_naming(visits: list[str], words: str) -> float | None:
    return _rate(sum(1 for v in visits if re.search(words, v)), len(visits)) if visits else None


def _assessment_reviews(
    db: Session, ids: list[uuid.UUID], assessments: RiskAssessmentDashboard
) -> tuple[CeilingReview, FrontLineReview]:
    """Ceilings and the front line, from assessment zones and where visits found activity. A
    zone's name is the form's: the DML is measured through Service Line / Food Preparation."""
    zones = {z.zone: z for z in assessments.zones}
    ceiling = next((z for z in assessments.zones if z.zone.startswith("Ceiling")), None)
    dml = next((z for z in assessments.zones if z.zone.startswith("Service Line")), None)
    front = zones.get("Front of House")
    visits = _activity_locations(db, ids)
    return (
        CeilingReview(
            stores_assessed=len(assessments.stores),
            drop_ceilings=next(
                (
                    c.stores
                    for c in assessments.site
                    if c.attribute == "Ceiling" and c.value == "Drop Ceiling"
                ),
                0,
            ),
            zone_inspected=ceiling.inspected if ceiling else 0,
            zone_rodent_rate=ceiling.rodent_rate if ceiling else None,
            rodent_zone_stores=sum(1 for s in assessments.stores if s.rodent_zones),
            activity_visit_share=_share_naming(visits, "ceiling|overhead"),
        ),
        FrontLineReview(
            dml_inspected=dml.inspected if dml else 0,
            dml_rodent_rate=dml.rodent_rate if dml else None,
            dml_visit_share=_share_naming(visits, r"\bdml\b|make ?line|digital|service line"),
            front_inspected=front.inspected if front else 0,
            front_rodent_rate=front.rodent_rate if front else None,
            front_visit_share=_share_naming(
                visits, "dining|front of house|front line|serving line"
            ),
        ),
    )


def _mall_locations(db: Session, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Locations an assessment recorded as being in a mall."""
    return set(
        db.scalars(
            select(InspectionSubmission.location_id)
            .join(RiskInspectionZone, RiskInspectionZone.submission_id == InspectionSubmission.id)
            .where(
                InspectionSubmission.location_id.in_(ids),
                RiskInspectionZone.attributes["in_mall"].astext == "true",
            )
        )
    )


def _drivers(
    treated: list[StoreMetrics], stores: list[StoreMetrics], malls: set[uuid.UUID], as_of: date
) -> RecurrenceDrivers:
    """What's behind the stores still stabilizing, over the last 90 days. A store can show more
    than one."""
    active = [s for s in treated if not s.stabilized_now]

    def share(test) -> float | None:
        return _rate(sum(1 for s in active if test(s)), len(active)) if active else None

    def recent(s: StoreMetrics) -> list[Visit]:
        return [v for v in s.visits if (as_of - v.day).days <= DRIVER_DAYS]

    return RecurrenceDrivers(
        active=len(active),
        structural=share(
            lambda s: any(
                v.exclusion == "compromised" or any(i[2] == "open" for i in v.structural)
                for v in recent(s)
            )
        ),
        operational=share(lambda s: any(v.sanitation > 0 for v in recent(s))),
        environmental=share(
            lambda s: (
                s.location_id in malls or any(v.zones & ENVIRONMENTAL_ZONES for v in recent(s))
            )
        ),
        client_reported=sum(1 for s in stores if any(f[0] == "client" for f in s.flags)),
    )


def _first_ramp_orders(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, date]:
    """Each location's first worked RAMP 1/2/3 order. PestPac's RAMP Monitoring code only began in
    June 2026, so it can't date a store's program yet; the tracker's phase dates aren't held."""
    if not ids:
        return {}
    return {
        location_id: first.date()
        for location_id, first in db.execute(
            select(ServiceOrder.location_id, func.min(ServiceOrder.work_date))
            .where(
                ServiceOrder.location_id.in_(ids),
                ServiceOrder.posted.is_(True),
                func.upper(func.trim(ServiceOrder.service_code)).in_(RAMP_CODES),
            )
            .group_by(ServiceOrder.location_id)
        )
        if first is not None
    }


def _six_month(
    treated: list[StoreMetrics],
    by_id: dict[uuid.UUID, Location],
    first_ramp: dict[uuid.UUID, date],
    as_of: date,
) -> SixMonthReview:
    """Stores six months past their first RAMP order: is the program still holding them?"""
    after: dict[uuid.UUID, list[Visit]] = {}
    for s in treated:
        began = first_ramp.get(s.location_id)
        if began and (as_of - began).days >= SIX_MONTHS_DAYS:
            cutoff = began + timedelta(days=SIX_MONTHS_DAYS)
            after[s.location_id] = [v for v in s.visits if v.day > cutoff]

    def gap_with_activity(visits: list[Visit]) -> bool:
        services = [v for v in visits if v.service]
        return any(
            (b.day - a.day).days > SERVICE_GAP_DAYS and (b.activity or 0) > 0
            for a, b in zip(services, services[1:], strict=False)
        )

    with_activity = [
        location_id
        for location_id, visits in after.items()
        if any((v.activity or 0) > 0 for v in visits)
    ]
    return SixMonthReview(
        stores=len(after),
        stabilized=sum(1 for s in treated if s.location_id in after and s.stabilized_now),
        activity_after=len(with_activity),
        gaps_with_activity=sum(1 for visits in after.values() if gap_with_activity(visits)),
        activity_stores=[StoreRef(**_ref(by_id[location_id])) for location_id in with_activity],
    )


def _conditions(
    db: Session, ids: list[uuid.UUID], by_id: dict[uuid.UUID, Location]
) -> ConditionReview:
    """PestPac conditions at these stores and who owns them. Voided ones don't count."""
    rows = [
        c
        for c in db.scalars(
            select(Condition).where(Condition.location_id.in_(ids), Condition.removed_at.is_(None))
        )
        if c.status != "Void"
    ]

    def owner(c: Condition) -> str:
        return CONDITION_OWNERS.get(c.responsibility or "", "To be determined")

    high_open = sorted(
        (c for c in rows if c.status == "Open" and c.severity == "High"),
        key=lambda c: c.date_opened or datetime.min,
        reverse=True,
    )
    return ConditionReview(
        found=len(rows),
        assigned=sum(1 for c in rows if owner(c) != "To be determined"),
        open=sum(1 for c in rows if c.status == "Open"),
        resolved=sum(1 for c in rows if c.status == "Resolved"),
        owners=[
            VisitTypeCount(label=label, visits=n)
            for label, n in Counter(owner(c) for c in rows).most_common()
        ],
        high_open=[
            ConditionRow(
                **_ref(by_id[c.location_id]),
                area=c.area,
                category=c.category,
                severity=c.severity,
                owner=owner(c),
                opened=c.date_opened.date() if c.date_opened else None,
            )
            for c in high_open
        ],
    )


def _executive(
    db: Session,
    company_id: uuid.UUID,
    bill_to_id: uuid.UUID | None,
    state: str | None,
    stores: list[StoreMetrics],
    by_id: dict[uuid.UUID, Location],
    by_code: Counter,
    by_month: Counter,
    phases: dict[str, list[int]],
    as_of: date,
) -> ExecutiveTab:
    treated = [s for s in stores if s.services]
    days = [v.day for s in treated for v in s.visits]
    starts, nows = [], []
    for s in treated:
        if s.risk_index is None or s.first_service is None:
            continue
        cutoff = s.first_service + timedelta(days=RISK_WINDOW_DAYS)
        early: list[Visit] = [v for v in s.visits if v.day <= cutoff]
        start = store_metrics(s.location_id, early, s.tier, as_of).risk_index
        if start is not None:
            starts.append(start)
            nows.append(s.risk_index)
    by_state: dict[str, list[StoreMetrics]] = defaultdict(list)
    by_tier: dict[str, list[StoreMetrics]] = defaultdict(list)
    for s in treated:
        by_state[by_id[s.location_id].state or "—"].append(s)
        by_tier[s.tier or "Not tiered"].append(s)
    tiers = Counter(s.tier for s in treated if s.tier)
    cadence = Counter(c for s in treated if (c := _cadence(s, as_of)))
    ids = list(by_id)
    assessments = risk_assessment_dashboard(db, company_id, bill_to_id=bill_to_id, state=state)
    ceilings, front_line = _assessment_reviews(db, ids, assessments)
    return ExecutiveTab(
        inception=min(days, default=None),
        through=max(days, default=None),
        stores_serviced=len(treated),
        service_visits=sum(s.services for s in treated),
        captures=sum(s.captures for s in treated),
        tiers=[VisitTypeCount(label=t, visits=n) for t, n in sorted(tiers.items())],
        visit_types=[VisitTypeCount(label=t, visits=n) for t, n in by_code.most_common()],
        months=[MonthVisits(month=m, visits=n) for m, n in sorted(by_month.items())],
        treated=len(treated),
        stabilized_now=sum(1 for s in treated if s.stabilized_now),
        active_now=sum(1 for s in treated if not s.stabilized_now),
        recurrence=sum(1 for s in treated if s.recurrences),
        risk_start=statistics.fmean(starts) if starts else None,
        risk_now=statistics.fmean(nows) if nows else None,
        by_state=_health(by_state),
        by_tier=_health(by_tier),
        phases=[
            PhaseActivity(
                phase=phase,
                rated=phases[phase][0],
                activity_rate=_rate(phases[phase][1], phases[phase][0]),
                heavy_rate=_rate(phases[phase][2], phases[phase][0]),
            )
            for phase in ("RAMP", "Monitoring")
        ],
        ceilings=ceilings,
        front_line=front_line,
        drivers=_drivers(treated, stores, _mall_locations(db, ids), as_of),
        six_month=_six_month(treated, by_id, _first_ramp_orders(db, ids), as_of),
        conditions=_conditions(db, ids, by_id),
        cadence=[VisitTypeCount(label=c, visits=n) for c, n in cadence.most_common()],
    )


def program_tabs(
    db: Session,
    company_id: uuid.UUID,
    operator_id: uuid.UUID,
    *,
    bill_to_id: uuid.UUID | None = None,
    state: str | None = None,
    today: date,
) -> ProgramTabs:
    locations = _locations(db, company_id, bill_to_id, state)
    by_id = {loc.id: loc for loc in locations}
    ids = list(by_id)
    as_of, stores = compute(db, locations, today)
    items = _load_items(db, ids)
    names = {zone.value: name for zone, name in area_mapping.zone_names(db, operator_id).items()}
    species: dict[uuid.UUID, set[str]] = defaultdict(set)
    if ids:
        for location_id, named in db.execute(
            select(ServiceOrder.location_id, InspectionFinding.rodent_species)
            .join(InspectionFinding, InspectionFinding.service_order_id == ServiceOrder.id)
            .where(ServiceOrder.location_id.in_(ids))
        ):
            species[location_id].update(named or [])
    first_monitoring, by_code, by_month, phases = _order_dates(db, ids)

    def tracker_row(s: StoreMetrics) -> TrackerRow:
        inspections = [v.day for v in s.visits if not v.service]
        return TrackerRow(
            **_ref(by_id[s.location_id]),
            tier=s.tier,
            first_inspection=inspections[0] if inspections else None,
            first_service=s.first_service,
            first_monitoring=first_monitoring.get(s.location_id),
            first_stabilized=s.first_stabilized,
            last_service=s.last_service,
            services=s.services,
            stage=_stage(s, first_monitoring.get(s.location_id)),
        )

    tracked = [s for s in stores if s.tier or s.location_id in first_monitoring]
    return ProgramTabs(
        as_of=as_of,
        activity=_activity(stores, by_id, names, species),
        structural=_structural(items, by_id, names),
        sanitation=_sanitation(stores, items, by_id, names),
        tracker=[
            tracker_row(s)
            for s in sorted(tracked, key=lambda s: s.first_service or date.max, reverse=True)
        ],
        executive=_executive(
            db,
            company_id,
            bill_to_id,
            state,
            stores,
            by_id,
            by_code,
            by_month,
            phases,
            as_of,
        ),
    )


# --- Risk assessments ------------------------------------------------------------------------


def _risk_rows(db: Session, company_id: uuid.UUID, location_ids: list[uuid.UUID]) -> list:
    """Risk submissions linked to the locations, oldest first, with their recommendation."""
    if not location_ids:
        return []
    return list(
        db.execute(
            select(InspectionSubmission, RiskInspectionSummary.ramp_recommendation)
            .join(InspectionForm, InspectionForm.id == InspectionSubmission.form_id)
            .outerjoin(
                RiskInspectionSummary,
                RiskInspectionSummary.submission_id == InspectionSubmission.id,
            )
            .where(
                InspectionForm.kind == InspectionKind.risk,
                InspectionSubmission.location_id.in_(location_ids),
            )
            .order_by(InspectionSubmission.inspected_at.asc().nulls_first())
        )
    )


def _zones_by_submission(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, list]:
    zones: dict[uuid.UUID, list[RiskInspectionZone]] = defaultdict(list)
    if ids:
        for zone in db.scalars(
            select(RiskInspectionZone)
            .where(RiskInspectionZone.submission_id.in_(ids))
            .order_by(RiskInspectionZone.position)
        ):
            zones[zone.submission_id].append(zone)
    return zones


def _index(scores: list[int]) -> float | None:
    return round(sum(scores) / len(scores) / 5 * 100, 1) if scores else None


def _classification(highest: int | None) -> str | None:
    if highest is None:
        return None
    return (
        "Critical"
        if highest >= 5
        else "High"
        if highest >= 4
        else "Moderate"
        if highest >= 3
        else "Low"
    )


def _mean(values: list[int]) -> float | None:
    return round(statistics.fmean(values), 2) if values else None


def assessment_targets(db: Session, company_id: uuid.UUID) -> list[AssessmentTargetRow]:
    return [
        AssessmentTargetRow(state=t.state, total=t.total)
        for t in db.scalars(
            select(AssessmentTarget)
            .where(AssessmentTarget.company_id == company_id)
            .order_by(AssessmentTarget.state)
        )
    ]


def set_assessment_targets(db: Session, company: Company, rows: list[AssessmentTargetRow]) -> None:
    """Replace the company's targets."""
    db.execute(delete(AssessmentTarget).where(AssessmentTarget.company_id == company.id))
    db.add_all(
        AssessmentTarget(
            operator_id=company.operator_id, company_id=company.id, state=r.state, total=r.total
        )
        for r in rows
    )


def risk_assessment_dashboard(
    db: Session,
    company_id: uuid.UUID,
    *,
    bill_to_id: uuid.UUID | None = None,
    state: str | None = None,
) -> RiskAssessmentDashboard:
    locations = _locations(db, company_id, bill_to_id, state)
    by_id = {loc.id: loc for loc in locations}
    rows = _risk_rows(db, company_id, list(by_id))
    zones = _zones_by_submission(db, [sub.id for sub, _ in rows])
    tiered = set(
        db.scalars(
            select(ServiceOrder.location_id).where(
                ServiceOrder.location_id.in_(by_id),
                ServiceOrder.service_code.in_(PROGRAM_CODES),
            )
        )
    )

    by_location: dict[uuid.UUID, list] = defaultdict(list)
    for sub, recommendation in rows:
        by_location[sub.location_id].append((sub, recommendation))

    def overall(sub) -> list[int]:
        return [z.overall_risk for z in zones[sub.id] if z.overall_risk is not None]

    stores: list[AssessedStore] = []
    latest_zones: list[RiskInspectionZone] = []
    site: Counter = Counter()
    for location_id, subs in by_location.items():
        sub, recommendation = subs[-1]
        loc = by_id[location_id]
        rows_z = zones[sub.id]
        latest_zones.extend(z for z in rows_z if z.overall_risk is not None)
        scores = overall(sub)
        highest = max(scores, default=None)
        stores.append(
            AssessedStore(
                **_ref(loc),
                latitude=loc.latitude,
                longitude=loc.longitude,
                inspection_id=sub.id,
                assessed_on=sub.inspected_at.date() if sub.inspected_at else None,
                assessments=len(subs),
                inspector=sub.inspector_name,
                risk_index=_index(scores),
                sanitation_index=_index(
                    [z.sanitation_risk for z in rows_z if z.sanitation_risk is not None]
                ),
                structural_index=_index(
                    [z.structural_risk for z in rows_z if z.structural_risk is not None]
                ),
                max_zone=highest,
                classification=_classification(highest),
                recommendation=f"RAMP {recommendation}" if recommendation else None,
                high_zones=sum(1 for s in scores if s >= 3),
                rodent_zones=sum(1 for z in rows_z if z.rodent_activity),
                pest_zones=sum(1 for z in rows_z if z.pest_activity),
                sweeps_failed=sum(1 for z in rows_z if z.door_sweeps_ok is False),
                in_program=location_id in tiered,
                first_index=_index(overall(subs[0][0])) if len(subs) > 1 else None,
            )
        )
        seen: set[tuple] = set()
        for z in rows_z:
            for attribute, value in (z.attributes or {}).items():
                for v in value if isinstance(value, list) else [value]:
                    seen.add((attribute.replace("_", " ").capitalize(), str(v)))
        site.update(seen)

    grouped: dict[str, list[RiskInspectionZone]] = defaultdict(list)
    for z in latest_zones:
        grouped[z.name].append(z)
    zone_rows = [
        AssessmentZone(
            zone=name,
            inspected=len(group),
            rodent_rate=sum(1 for z in group if z.rodent_activity) / len(group),
            pest_rate=sum(1 for z in group if z.pest_activity) / len(group),
            avg_overall=_mean([z.overall_risk for z in group]),
            avg_sanitation=_mean(
                [z.sanitation_risk for z in group if z.sanitation_risk is not None]
            ),
            avg_structural=_mean(
                [z.structural_risk for z in group if z.structural_risk is not None]
            ),
            tier3=sum(1 for z in group if z.overall_risk == 3),
            tier4=sum(1 for z in group if z.overall_risk == 4),
            tier5=sum(1 for z in group if z.overall_risk >= 5),
        )
        for name, group in grouped.items()
    ]
    zone_rows.sort(key=lambda z: (-z.rodent_rate, -(z.avg_overall or 0)))

    in_state = Counter(loc.state or "—" for loc in locations)
    # Targets cover the whole company, so one bill-to's view has none.
    targets = (
        {}
        if bill_to_id
        else {
            t.state: t.total
            for t in db.scalars(
                select(AssessmentTarget).where(AssessmentTarget.company_id == company_id)
            )
            if not state or t.state == state
        }
    )
    by_state: dict[str, list[AssessedStore]] = defaultdict(list)
    for s in stores:
        by_state[s.state or "—"].append(s)
    coverage = [
        StateCoverage(
            state=st,
            in_program=total,
            target=targets.get(st),
            assessed=len(by_state[st]),
            avg_index=_mean([s.risk_index for s in by_state[st] if s.risk_index is not None]),
            high_or_critical=sum(
                1 for s in by_state[st] if s.classification in ("High", "Critical")
            ),
            with_rodents=sum(1 for s in by_state[st] if s.rodent_zones),
        )
        for st, total in [
            *in_state.most_common(),
            *((st, 0) for st in sorted(targets) if st not in in_state),
        ]
    ]
    dates = [sub.inspected_at.date() for sub, _ in rows if sub.inspected_at]
    unlinked = (
        db.scalar(
            select(func.count())
            .select_from(InspectionSubmission)
            .join(InspectionForm, InspectionForm.id == InspectionSubmission.form_id)
            .where(
                InspectionForm.kind == InspectionKind.risk,
                InspectionSubmission.location_id.is_(None),
                InspectionForm.operator_id == locations[0].operator_id,
            )
        )
        if locations
        else 0
    )
    stores.sort(key=lambda s: -(s.risk_index or 0))
    return RiskAssessmentDashboard(
        assessments=len(rows),
        zone_inspections=sum(len(overall(sub)) for sub, _ in rows),
        first=min(dates, default=None),
        last=max(dates, default=None),
        unlinked=unlinked or 0,
        stores=stores,
        zones=zone_rows,
        coverage=coverage,
        site=[
            SiteCondition(attribute=a, value=v, stores=n)
            for (a, v), n in sorted(site.items(), key=lambda kv: (kv[0][0], -kv[1]))
        ],
    )


def assessment_findings(
    db: Session,
    company_id: uuid.UUID,
    *,
    bill_to_id: uuid.UUID | None = None,
    state: str | None = None,
    q: str | None = None,
    kind: str | None = None,
    zone: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> AssessmentFindingPage:
    """Every written finding from the assessments, zone by zone, newest first."""
    locations = _locations(db, company_id, bill_to_id, state)
    by_id = {loc.id: loc for loc in locations}
    rows = _risk_rows(db, company_id, list(by_id))
    zones = _zones_by_submission(db, [sub.id for sub, _ in rows])
    needle = (q or "").strip().lower()
    found: list[AssessmentFinding] = []
    zone_names: set[str] = set()
    for sub, _ in reversed(rows):
        for z in zones[sub.id]:
            for label, text in (
                ("Pest", z.pest_notes),
                ("Structural", z.structural_notes),
                ("Sanitation", z.sanitation_notes),
                ("Note", z.additional_notes),
            ):
                text = (text or "").strip()
                if not text:
                    continue
                zone_names.add(z.name)
                if (kind and kind != label) or (zone and zone != z.name):
                    continue
                if needle and needle not in text.lower():
                    continue
                found.append(
                    AssessmentFinding(
                        **_ref(by_id[sub.location_id]),
                        inspection_id=sub.id,
                        assessed_on=sub.inspected_at.date() if sub.inspected_at else None,
                        zone=z.name,
                        kind=label,
                        text=text,
                    )
                )
    return AssessmentFindingPage(
        items=found[offset : offset + limit], total=len(found), zones=sorted(zone_names)
    )


# --- Report library --------------------------------------------------------------------------


def report_library(
    db: Session,
    company_id: uuid.UUID,
    *,
    bill_to_id: uuid.UUID | None = None,
    state: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> ReportLibraryPage:
    """The service reports we generated (their current, final versions), newest first."""
    locations = _locations(db, company_id, bill_to_id, state)
    by_id = {loc.id: loc for loc in locations}
    query = (
        select(Report, ReportTemplate.name, ServiceOrder.order_number, ServiceOrder.work_date)
        .join(ReportTemplate, ReportTemplate.id == Report.template_id)
        .join(ServiceOrder, ServiceOrder.id == Report.service_order_id)
        .where(Report.location_id.in_(by_id), Report.status == ReportStatus.final)
        .order_by(Report.finalized_at.desc().nulls_last(), Report.id)
    )
    needle = (q or "").strip().lower()
    rows = [
        GeneratedReport(
            **_ref(by_id[report.location_id]),
            id=report.id,
            title=title,
            revision=report.revision,
            order_number=order_number,
            work_date=worked.date() if worked else None,
            finalized_on=report.finalized_at.date() if report.finalized_at else None,
        )
        for report, title, order_number, worked in db.execute(query)
    ]
    rows = [
        r
        for r in rows
        if not needle
        or needle in r.title.lower()
        or needle == (r.store_number or "").lower()
        or needle in (r.name or "").lower()
    ]
    return ReportLibraryPage(items=rows[offset : offset + limit], total=len(rows))
