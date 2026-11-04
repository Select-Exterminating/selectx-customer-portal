"""One store's flyover: the RAMP portal's store profile (`../select-ramp-portal/public/js/watch.js`,
`drawProfile`), worked out from the same visits as `program_metrics`, so a store reads the same
here as in Store Watch. What only the portal's tracker, Drive, or customer lists hold isn't shown
(`docs/dashboard-gaps.md`)."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    BillTo,
    Company,
    Contact,
    ContactLink,
    ContactRole,
    InspectionFinding,
    InspectionFindingItem,
    Location,
    Report,
    ReportStatus,
    ReportTemplate,
    ServiceOrder,
)
from app.schemas.store_profile import (
    ActivityGrid,
    AssessmentZoneScore,
    ProfileAssessment,
    ProfileFinding,
    ProfileJourney,
    ProfileNumbers,
    ProfileReport,
    ProfileVisit,
    RiskPoints,
    StoreProfile,
    TrendPoint,
    ZoneMonths,
)
from app.services import area_mapping, client_findings
from app.services.dashboard import store_name, store_number
from app.services.program_metrics import (
    ACTIVITY_LEVEL,
    NON_VISIT_CODES,
    band_of,
    load_tiers,
    load_visits,
    risk_index_at,
    risk_points,
    store_metrics,
    watch_flags,
)
from app.services.program_tabs import (
    _cadence,
    _classification,
    _index,
    _order_dates,
    _risk_rows,
    _stage,
    _zones_by_submission,
)

CADENCE_WHY = {
    "Full Reassessment": "Persistent activity",
    "Maintain Weekly": "Basement or high-risk zone activity",
    "Four-Week Weekly Escalation": "Emerging activity in the last 30 days",
    "Elevated Permanent Cadence": "High-risk structural environment",
    "Monthly Validation": "Standard stabilized store",
    "Program Cadence": "Active stabilization underway",
}
START_DAYS = 14  # "Start" is the two weeks from a store's first rated visit
RECENT_CONCERNS = 12


def _as_of(db: Session, company: Company, today: date) -> date:
    """The latest visit across the company, as in Store Watch, so day counts and flags match."""
    latest = db.scalar(
        select(func.max(ServiceOrder.work_date))
        .join(Location, Location.id == ServiceOrder.location_id)
        .join(BillTo, BillTo.id == Location.bill_to_id)
        .where(
            BillTo.company_id == company.id,
            Location.removed_at.is_(None),
            ServiceOrder.posted.is_(True),
            func.upper(func.trim(func.coalesce(ServiceOrder.service_code, ""))).not_in(
                NON_VISIT_CODES
            ),
        )
    )
    return min(latest.date(), today) if latest else today


def _directors(db: Session, location: Location) -> dict[ContactRole, str]:
    names: dict[ContactRole, str] = {}
    for role, name in db.execute(
        select(ContactLink.role, Contact.name)
        .join(Contact, Contact.id == ContactLink.contact_id)
        .where(
            ContactLink.location_id == location.id,
            ContactLink.removed_at.is_(None),
            ContactLink.role.in_([ContactRole.team_director, ContactRole.executive_team_director]),
        )
    ):
        if name:
            names.setdefault(role, name)
    return names


def _visit_details(db: Session, location: Location, *, include_reports: bool) -> dict[date, dict]:
    """The details of each visit: what its merged orders' findings say."""
    rows = db.execute(
        select(ServiceOrder, InspectionFinding)
        .outerjoin(InspectionFinding, InspectionFinding.service_order_id == ServiceOrder.id)
        .options(joinedload(ServiceOrder.technician))
        .where(
            ServiceOrder.location_id == location.id,
            ServiceOrder.posted.is_(True),
            ServiceOrder.work_date.is_not(None),
        )
        .order_by(ServiceOrder.work_date)
    ).all()
    reports: dict = {}
    if include_reports:
        reports = dict(
            db.execute(
                select(Report.service_order_id, Report.id).where(
                    Report.location_id == location.id, Report.status == ReportStatus.final
                )
            ).all()
        )
    details: dict[date, dict] = defaultdict(
        lambda: {"technicians": [], "evidence": [], "summaries": [], "report_id": None}
    )
    for order, finding in rows:
        if (order.service_code or "").strip().upper() in NON_VISIT_CODES:
            continue
        d = details[order.work_date.date()]
        tech = order.technician_name
        if tech and tech not in d["technicians"]:
            d["technicians"].append(tech)
        d["report_id"] = d["report_id"] or reports.get(order.id)
        if finding is not None:
            d["evidence"].extend(e for e in finding.rodent_evidence if e not in d["evidence"])
            if finding.summary:
                d["summaries"].append(finding.summary)
    return details


def _findings(db: Session, location: Location, zone_names: dict[str, str]) -> list[ProfileFinding]:
    """Every structural, sanitation, and pest finding at the store, oldest first."""
    return [
        ProfileFinding(
            day=worked.date(),
            kind=item.kind,
            category=item.category,
            zone=zone_names.get(item.zone, item.zone) if item.zone else None,
            where=item.location,
            issue=item.issue,
            status=item.status,
            severity=item.severity,
        )
        for item, worked in db.execute(
            select(InspectionFindingItem, ServiceOrder.work_date)
            .join(InspectionFinding, InspectionFinding.id == InspectionFindingItem.finding_id)
            .join(ServiceOrder, ServiceOrder.id == InspectionFinding.service_order_id)
            .where(
                ServiceOrder.location_id == location.id,
                ServiceOrder.posted.is_(True),
                ServiceOrder.work_date.is_not(None),
            )
            .order_by(ServiceOrder.work_date, InspectionFindingItem.position)
        )
    ]


def _open_structural(findings: list[ProfileFinding]) -> list[ProfileFinding]:
    """The latest report of each distinct structural finding still open, newest first."""
    latest = {(f.category, f.zone): f for f in findings if f.kind == "structural"}
    return sorted(
        (f for f in latest.values() if f.status != "repaired"), key=lambda f: f.day, reverse=True
    )


def _activity_grid(rated: list, zone_names: dict[str, str]) -> ActivityGrid:
    months = sorted({v.day.strftime("%Y-%m") for v in rated})
    position = {m: i for i, m in enumerate(months)}
    counts = [0] * len(months)
    levels: dict[str, list[int]] = {}
    totals: dict[str, int] = defaultdict(int)
    for visit in rated:
        i = position[visit.day.strftime("%Y-%m")]
        counts[i] += 1
        if visit.activity == 0:
            continue
        names = [zone_names.get(z, z) for z in visit.zones] or ["Area not stated"]
        for name in names:
            row = levels.setdefault(name, [0] * len(months))
            row[i] = max(row[i], visit.activity)
            totals[name] += 1
    return ActivityGrid(
        months=months,
        rated=counts,
        zones=[
            ZoneMonths(zone=z, total=totals[z], levels=levels[z])
            for z in sorted(levels, key=lambda z: -totals[z])
        ],
    )


def _assessments(db: Session, company: Company, location: Location) -> list[ProfileAssessment]:
    rows = _risk_rows(db, company.id, [location.id])
    zones = _zones_by_submission(db, [sub.id for sub, _ in rows])
    out = []
    for sub, recommendation in reversed(rows):
        rows_z = zones[sub.id]
        overall = [z.overall_risk for z in rows_z if z.overall_risk is not None]
        highest = max(overall, default=None)
        out.append(
            ProfileAssessment(
                inspection_id=sub.id,
                day=sub.inspected_at.date() if sub.inspected_at else None,
                inspector=sub.inspector_name,
                classification=_classification(highest),
                risk_index=_index(overall),
                sanitation_index=_index(
                    [z.sanitation_risk for z in rows_z if z.sanitation_risk is not None]
                ),
                structural_index=_index(
                    [z.structural_risk for z in rows_z if z.structural_risk is not None]
                ),
                max_zone=highest,
                recommendation=f"RAMP {recommendation}" if recommendation else None,
                rodent_zones=sum(1 for z in rows_z if z.rodent_activity),
                pest_zones=sum(1 for z in rows_z if z.pest_activity),
                zones=[
                    AssessmentZoneScore(
                        zone=z.name,
                        areas=z.areas or [],
                        sanitation=z.sanitation_risk,
                        structural=z.structural_risk,
                        overall=z.overall_risk,
                        rodent=z.rodent_activity,
                        pest=z.pest_activity,
                        pest_types=z.pest_types or [],
                        notes=[
                            f"{label}: {note}"
                            for label, note in (
                                ("Sanitation", z.sanitation_notes),
                                ("Structural", z.structural_notes),
                                ("Pest", z.pest_notes),
                                ("Note", z.additional_notes),
                            )
                            if note
                        ],
                    )
                    for z in rows_z
                ],
            )
        )
    return out


def _reports(db: Session, location: Location) -> list[ProfileReport]:
    return [
        ProfileReport(
            id=report.id,
            title=title,
            revision=report.revision,
            work_date=worked.date() if worked else None,
            finalized_on=report.finalized_at.date() if report.finalized_at else None,
        )
        for report, title, worked in db.execute(
            select(Report, ReportTemplate.name, ServiceOrder.work_date)
            .join(ReportTemplate, ReportTemplate.id == Report.template_id)
            .join(ServiceOrder, ServiceOrder.id == Report.service_order_id)
            .where(Report.location_id == location.id, Report.status == ReportStatus.final)
            .order_by(Report.finalized_at.desc().nulls_last(), Report.id)
        )
    ]


def store_profile(
    db: Session, company: Company, location: Location, *, include_reports: bool, today: date
) -> StoreProfile:
    as_of = _as_of(db, company, today)
    visits = load_visits(db, [location.id]).get(location.id, [])
    tier = load_tiers(db, [location.id]).get(location.id)
    reported = client_findings.load(db, [location.id]).get(location.id, [])
    m = store_metrics(location.id, visits, tier, as_of, reported)
    first_monitoring = _order_dates(db, [location.id])[0].get(location.id)
    zone_names = {z.value: n for z, n in area_mapping.zone_names(db, company.operator_id).items()}
    rated = [v for v in visits if v.activity is not None]
    recent = [v for v in rated if (as_of - v.day).days < 30]

    # Start is measured from the first rated visit: an earlier visit with no findings says nothing.
    start_index = start_activity = None
    if rated:
        start = rated[0].day + timedelta(days=START_DAYS)
        start_index = risk_index_at(visits, min(as_of, start))
        start_activity = ACTIVITY_LEVEL[max(v.activity for v in rated if v.day <= start)]

    trend = []
    for visit in rated:
        # The last point is the index Store Watch shows.
        index = m.risk_index if visit is rated[-1] else risk_index_at(visits, visit.day)
        if index is not None:
            trend.append((visit, index))
    details = _visit_details(db, location, include_reports=include_reports)
    findings = _findings(db, location, zone_names)
    concerns = [f for f in findings if f.kind in ("sanitation", "pest")]
    cadence = _cadence(m, as_of)
    points = risk_points(visits, rated[-1].day) if rated else {}
    directors = _directors(db, location)

    def detail(day: date) -> dict:
        return details.get(day, {"technicians": [], "evidence": [], "summaries": []})

    return StoreProfile(
        location_id=location.id,
        store_number=store_number(location.pestpac_company),
        name=store_name(location),
        address=location.address,
        city=location.city,
        state=location.state,
        as_of=as_of,
        tier=tier,
        stage=_stage(m, first_monitoring),
        attention=m.attention,
        flags=watch_flags(m, zone_names),
        client_findings=[client_findings.read(f, zone_names) for f in reported],
        team_director=directors.get(ContactRole.team_director),
        executive_team_director=directors.get(ContactRole.executive_team_director),
        numbers=ProfileNumbers(
            services=m.services,
            inspections=m.inspections,
            captures=m.captures,
            activity_rate=m.activity_visits / m.rated_visits if m.rated_visits else None,
            activity_30d=sum(1 for v in recent if v.activity > 0),
            rated_30d=len(recent),
            structural_open=m.structural_open,
            days_since_service=(as_of - m.last_service).days if m.last_service else None,
        ),
        journey=ProfileJourney(
            first_visit=m.first_visit,
            first_service=m.first_service,
            first_rated=rated[0].day if rated else None,
            start_index=start_index,
            start_band=band_of(start_index),
            start_activity=start_activity,
            last_rated=rated[-1].day if rated else None,
            now_index=m.risk_index,
            now_band=m.risk_band,
            now_activity=m.current_activity,
            index_change=(
                m.risk_index - start_index
                if m.risk_index is not None and start_index is not None
                else None
            ),
            outcome=(
                ("Stabilized" if m.stabilized_now else "Active stabilization")
                if len(rated) >= 2 and m.services
                else None
            ),
            stabilized_since=m.stabilized_since,
            first_stabilized=m.first_stabilized,
            days_to_stabilized=m.days_to_stabilized,
            recurrences=m.recurrences,
            clean_from_start=len(rated) >= 2 and not m.activity_visits,
            cadence=cadence,
            cadence_why=CADENCE_WHY.get(cadence),
            last_activity=m.last_activity,
            days_since_activity=(as_of - m.last_activity).days if m.last_activity else None,
            first_monitoring=first_monitoring,
        ),
        risk_points=RiskPoints(**{k: round(v) for k, v in points.items()}) if points else None,
        trend=[
            TrendPoint(
                day=v.day,
                index=index,
                band=band_of(index),
                activity=ACTIVITY_LEVEL[v.activity],
                visit_type=v.visit_type,
                summary=" ".join(detail(v.day)["summaries"]) or None,
            )
            for v, index in trend
        ],
        activity_grid=_activity_grid(rated, zone_names),
        visits=[
            ProfileVisit(
                day=v.day,
                visit_type=v.visit_type,
                service=v.service,
                activity=ACTIVITY_LEVEL[v.activity] if v.activity is not None else None,
                technicians=detail(v.day)["technicians"],
                captures=v.captures,
                zones=[zone_names.get(z, z) for z in sorted(v.zones)],
                evidence=detail(v.day)["evidence"],
                summaries=detail(v.day)["summaries"],
                report_id=detail(v.day).get("report_id"),
            )
            for v in reversed(visits)
        ],
        open_structural=_open_structural(findings),
        recent_concerns=concerns[::-1][:RECENT_CONCERNS],
        assessments=_assessments(db, company, location),
        reports=_reports(db, location) if include_reports else [],
    )
