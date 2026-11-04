import uuid
from datetime import UTC, date, datetime, timedelta

from app.db.session import SessionLocal
from app.integrations.openrouter import Usage
from app.models import Location, Report, ServiceOrder
from app.services import inspection_findings
from app.services.program_metrics import (
    Visit,
    band_of,
    results,
    risk_index_at,
    stabilization,
    store_metrics,
    watch_flags,
)
from tests.conftest import headers_for
from tests.test_service_reports import DRAFT

DAY0 = date(2026, 6, 1)


def _visit(day: int, activity: int | None, **extra) -> Visit:
    return Visit(day=DAY0 + timedelta(days=day), service=True, activity=activity, **extra)


def test_stabilized_after_28_days_and_two_clean_visits_then_a_recurrence():
    rated = [_visit(0, 2), _visit(14, 0), _visit(27, 0), _visit(28, 0), _visit(40, 1)]
    now, since, first, recurrences = stabilization(rated)
    # Day 27 is the second clean visit but only 27 days on; day 28 stabilizes.
    assert first == 3 and since is None and not now
    assert recurrences == [DAY0 + timedelta(days=40)]

    now, since, first, _ = stabilization(rated[:4])
    assert (now, since) == (True, DAY0 + timedelta(days=28))


def test_risk_index_and_band():
    visits = [
        _visit(0, 3, structural=[("wall/floor gap", "basement", "open")], sanitation=1),
        _visit(30, 0, pests={"German cockroach"}),
        _visit(60, 0),
        _visit(80, 0),
    ]
    m = store_metrics("loc", visits, "RAMP 1", as_of=DAY0 + timedelta(days=80))
    # Activity 3/4 visits avg 0.75 of 3 -> 10; one open finding -> 25/6; sanitation 1/4 -> 5;
    # pests 1/4 -> 3.75.
    assert m.risk_index == round(10 + 25 / 6 + 5 + 3.75)
    assert m.risk_band == band_of(m.risk_index) == "Elevated"
    assert (m.structural_open, m.structural_remediated) == (1, 0)
    assert (m.days_to_stabilized, m.stabilized_now) == (60, True)


def test_recurrence_with_heavy_activity_now_is_escalated():
    visits = [
        _visit(0, 2),
        _visit(10, 0),
        _visit(30, 0),  # stabilized
        _visit(60, 3, zones={"basement"}),
    ]
    m = store_metrics("loc", visits, None, as_of=DAY0 + timedelta(days=62))
    assert {c for c, _, _ in m.flags} == {"regress", "active"}
    assert m.attention == "Escalated"

    quiet = store_metrics("loc", visits[:3], None, as_of=DAY0 + timedelta(days=32))
    assert quiet.flags == [] and quiet.attention == "Stable"
    assert store_metrics("loc", [], None, as_of=DAY0).attention == "Not Yet Serviced"


def test_results_measure_from_the_first_service():
    baseline = Visit(day=DAY0 - timedelta(days=30), service=False, activity=3)
    stores = [
        store_metrics("a", [baseline, _visit(0, 2), _visit(10, 0), _visit(35, 0)], None, DAY0),
        store_metrics("b", [_visit(0, 0), _visit(20, 0)], None, DAY0),
    ]
    r = results(stores)
    assert (r["stores_measured"], r["intake_active"], r["stabilized"]) == (2, 1, 1)
    assert r["median_days"] == 35  # from the first service, not the baseline inspection


# --- API ---


def _order(world, order_id: int, day: int, code: str) -> ServiceOrder:
    return ServiceOrder(
        operator_id=world.op_a,
        bill_to_id=world.bill_to_a,
        location_id=world.location_a,
        pestpac_order_id=order_id,
        pestpac_location_id=800001,
        service_code=code,
        work_date=datetime(2026, 6, 1, 23, 0) + timedelta(days=day),
        posted=True,
        pestpac_fetched_at=datetime.now(UTC),
    )


def _findings(db, world, order: ServiceOrder, activity: str, **overrides) -> None:
    data = {
        **DRAFT["findings"],
        "visit_type": "mass_trapping",
        "rodent_activity": activity,
        "exclusion_status": None,
        "structural_findings": [],
        "other_pests": [],
        **overrides,
    }
    inspection_findings.save(
        db,
        operator_id=world.op_a,
        service_order_id=order.id,
        location_id=world.location_a,
        report_id=None,
        source="extraction",
        findings=inspection_findings.FindingsOut.model_validate(data),
        model="test/model",
        usage=Usage(),
    )


def test_program_dashboard_merges_a_nights_orders_and_skips_non_visits(client, world):
    with SessionLocal() as db:
        night = [_order(world, 9101, 0, "RAMP 1"), _order(world, 9102, 0, "SPRODENTPICKUP")]
        later = [_order(world, 9103, 14, "RAMP MONITOR"), _order(world, 9104, 40, "RAMP MONITOR")]
        inspection = _order(world, 9105, -20, "SPINSPCHG")  # no findings: an inspection by code
        travel = _order(world, 9106, 40, "INTTRAVEL")  # not a visit
        db.add_all([*night, *later, inspection, travel])
        db.flush()
        _findings(db, world, night[0], "moderate", rodents_captured=2)
        _findings(db, world, night[1], "none", rodents_captured=1)
        _findings(db, world, later[0], "none")
        _findings(db, world, later[1], "none")
        db.commit()

    admin = headers_for(client, world.emails["admin_a"])
    resp = client.get(f"/v1/companies/{world.company_a}/program-dashboard", headers=admin)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    [store] = [s for s in body["stores"] if s["location_id"] == str(world.location_a)]
    assert store["services"] == 3  # the night's two orders are one visit; travel isn't one
    assert store["tier"] == "RAMP 1"
    assert store["spark"] == [2, 0, 0]  # the night is moderate: the stronger of its orders
    assert store["stabilized_now"] and store["days_to_stabilized"] == 40
    assert body["portfolio"]["inspections"] == 1 and body["portfolio"]["captures"] == 3
    assert body["results"]["intake_active"] == 1 and body["results"]["stabilized"] == 1
    assert body["as_of"] == "2026-07-11"

    other = client.get(
        f"/v1/companies/{world.company_a}/program-dashboard?state=ZZ", headers=admin
    ).json()
    assert other["stores"] == [] and other["state"] == "ZZ"


def test_a_qc_inspection_months_before_the_program_is_not_day_one(client, world):
    with SessionLocal() as db:
        qc = _order(world, 9201, -70, "INSP-NO CHARGE")
        ramp = [_order(world, 9202, 0, "RAMP 2"), _order(world, 9203, 14, "RAMP MONITOR")]
        later = _order(world, 9204, 28, "RAMP MONITOR")
        db.add_all([qc, *ramp, later])
        db.flush()
        _findings(db, world, qc, "moderate", visit_type="qc_inspection")
        _findings(db, world, ramp[0], "low")
        _findings(db, world, ramp[1], "none")
        # A program order stays a service even when its notes read like a QC visit.
        _findings(db, world, later, "none", visit_type="qc_inspection")
        db.commit()

    admin = headers_for(client, world.emails["admin_a"])
    body = client.get(f"/v1/companies/{world.company_a}/program-dashboard", headers=admin).json()
    [store] = [s for s in body["stores"] if s["location_id"] == str(world.location_a)]
    assert store["services"] == 3 and store["spark"] == [2, 1, 0, 0]  # still rated, not a service
    assert store["days_to_stabilized"] == 28
    assert body["portfolio"]["inspections"] == 1
    assert body["results"]["median_days"] == 28


def test_program_tabs_group_findings_and_list_what_is_still_open(client, world):
    item = {
        "location": "basement wall",
        "zone": "basement",
        "issue": "gap at the wall",
        "category": "wall/floor gap",
    }
    with SessionLocal() as db:
        first = _order(world, 9301, 0, "RAMP 2")
        second = _order(world, 9302, 14, "RAMP MONITOR")
        third = _order(world, 9303, 28, "RAMP MONITOR")
        db.add_all([first, second, third])
        db.flush()
        _findings(
            db,
            world,
            first,
            "moderate",
            rodent_species=["mouse"],
            activity_locations=[{"location": "basement", "zone": "basement"}],
            structural_findings=[
                {**item, "status": "open"},
                {**item, "category": "door/door sweep", "status": "open"},
            ],
        )
        # The gap is repaired by the next visit; the door sweep isn't mentioned again.
        _findings(db, world, second, "none", structural_findings=[{**item, "status": "repaired"}])
        _findings(db, world, third, "none")
        db.commit()

    admin = headers_for(client, world.emails["admin_a"])
    body = client.get(f"/v1/companies/{world.company_a}/program-tabs", headers=admin).json()
    assert [z["stores"] for z in body["activity"]["zones"]] == [1]
    assert body["activity"]["cohort"][0]["activity_rate"] == 1 / 3
    assert body["activity"]["recent"] == []  # the latest rated visit was clean
    assert [o["category"] for o in body["structural"]["open"]] == ["door/door sweep"]
    assert {b["label"]: b["remediated"] for b in body["structural"]["categories"]} == {
        "wall/floor gap": 1,
        "door/door sweep": 0,
    }
    [row] = [r for r in body["tracker"] if r["location_id"] == str(world.location_a)]
    assert row["tier"] == "RAMP 2" and row["first_monitoring"] == "2026-06-15"
    assert row["stage"] == "Stabilized"
    assert body["executive"]["stabilized_now"] == 1
    assert {p["phase"]: p["rated"] for p in body["executive"]["phases"]} == {
        "RAMP": 1,
        "Monitoring": 2,
    }

    other = client.get(f"/v1/companies/{world.company_a}/program-tabs?state=ZZ", headers=admin)
    assert other.json()["tracker"] == []


def test_risk_index_at_only_counts_what_was_known_then():
    visits = [_visit(0, 3), _visit(30, 0), _visit(120, 1)]
    # Day 0 alone: all heavy, 40 points.
    assert risk_index_at(visits, DAY0) == 40
    # Day 30: heavy and clean, half the activity points; the later visit doesn't count yet.
    assert risk_index_at(visits, DAY0 + timedelta(days=30)) == 20
    # Day 300: nothing rated in the 90 days before it.
    assert risk_index_at(visits, DAY0 + timedelta(days=300)) is None


def _profile_visits(client, world):
    """A heavy start, then clean visits, one with a structural finding and a generated summary."""
    with SessionLocal() as db:
        first = _order(world, 9401, 0, "RAMP 1")
        night = _order(world, 9402, 0, "RAMP 1")
        travel = _order(world, 9403, 0, "INTTRAVEL")
        second = _order(world, 9404, 14, "RAMP MONITOR")
        third = _order(world, 9405, 40, "RAMP MONITOR")
        db.add_all([first, night, travel, second, third])
        db.flush()
        _findings(
            db,
            world,
            first,
            "heavy",
            activity_locations=[{"location": "basement wall", "zone": "basement"}],
            structural_findings=[
                {
                    "location": "basement wall",
                    "zone": "basement",
                    "issue": "gap at the wall",
                    "category": "wall/floor gap",
                    "status": "open",
                }
            ],
        )
        _findings(
            db,
            world,
            night,
            "low",
            activity_locations=[{"location": "basement wall", "zone": "basement"}],
        )
        _findings(db, world, second, "none")
        _findings(db, world, third, "none")
        db.commit()


def test_store_profile_reads_like_store_watch(client, world):
    _profile_visits(client, world)
    staff = headers_for(client, world.emails["staff_a"])
    resp = client.get(
        f"/v1/companies/{world.company_a}/stores/{world.location_a}/profile", headers=staff
    )
    assert resp.status_code == 200
    p = resp.json()
    watch = client.get(f"/v1/companies/{world.company_a}/program-dashboard", headers=staff).json()
    row = next(s for s in watch["stores"] if s["location_id"] == str(world.location_a))
    # The same store reads the same in Store Watch and its flyover.
    assert p["attention"] == row["attention"] and p["flags"] == row["flags"]
    assert p["journey"]["now_index"] == row["risk_index"] == p["trend"][-1]["index"]
    assert p["as_of"] == watch["as_of"]
    # The night's two orders merge into one visit, and travel isn't one.
    assert [v["day"] for v in p["visits"]] == ["2026-07-11", "2026-06-15", "2026-06-01"]
    assert p["visits"][-1]["activity"] == "heavy"
    assert p["numbers"]["services"] == 3
    # Start is the two weeks from the first rated visit: heavy, then clean on day 14.
    assert p["journey"]["first_rated"] == "2026-06-01"
    assert p["journey"]["start_activity"] == "heavy"
    assert p["journey"]["start_index"] is not None
    assert p["journey"]["index_change"] == p["journey"]["now_index"] - p["journey"]["start_index"]
    assert [f["category"] for f in p["open_structural"]] == ["wall/floor gap"]
    grid = p["activity_grid"]
    assert grid["months"] == ["2026-06", "2026-07"] and grid["rated"] == [2, 1]
    assert [(z["total"], z["levels"]) for z in grid["zones"]] == [(1, [3, 0])]


def test_store_profile_lists_reports_only_for_those_who_can_open_them(client, world):
    with SessionLocal() as db:
        report = db.get(Report, world.report_final_a)
        db.get(ServiceOrder, report.service_order_id).posted = True
        db.commit()
    path = f"/v1/companies/{world.company_a}/stores/{world.location_a}/profile"
    manager = client.get(path, headers=headers_for(client, world.emails["manager_a"])).json()
    staff = client.get(path, headers=headers_for(client, world.emails["staff_a"])).json()
    assert staff["reports"], "the world has a final report at location A"
    assert manager["reports"] == []
    assert any(v["report_id"] for v in staff["visits"])
    assert not any(v["report_id"] for v in manager["visits"])


def test_store_profile_is_scoped_to_the_company(client, world):
    admin = headers_for(client, world.emails["admin_a"])
    sibling = client.post(
        f"/v1/operators/{world.op_a}/companies", json={"name": "Sibling Co"}, headers=admin
    ).json()["id"]
    # Another company's id with this store, and a store that doesn't exist.
    assert (
        client.get(f"/v1/companies/{sibling}/stores/{world.location_a}/profile", headers=admin)
    ).status_code == 404
    assert (
        client.get(f"/v1/companies/{world.company_a}/stores/{uuid.uuid4()}/profile", headers=admin)
    ).status_code == 404


def test_flags_name_zones_as_the_operator_does():
    m = store_metrics(
        "loc",
        [_visit(0, 2, zones={"bar_beverage"})],
        None,
        as_of=DAY0 + timedelta(days=1),
    )
    [flag] = [f for f in watch_flags(m, {"bar_beverage": "Bar & Beverage"}) if f.code == "active"]
    assert "in Bar & Beverage." in flag.detail and "bar_beverage" not in flag.detail


def test_a_store_that_only_repeats_the_customers_name_is_named_by_address(client, world):
    staff = headers_for(client, world.emails["staff_a"])
    path = f"/v1/companies/{world.company_a}/stores/{world.location_a}/profile"
    with SessionLocal() as db:
        location = db.get(Location, world.location_a)
        location.pestpac_company, location.address = "ACME RESTAURANTS", "10 HUDSON YARDS"
        location.description = None
        db.commit()
    assert client.get(path, headers=staff).json()["name"] == "10 HUDSON YARDS"

    with SessionLocal() as db:
        db.get(Location, world.location_a).pestpac_company = "ACME BOSTON"
        db.commit()
    assert client.get(path, headers=staff).json()["name"] == "ACME BOSTON"
