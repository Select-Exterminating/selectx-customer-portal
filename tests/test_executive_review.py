"""The Executive Review's sections drawn from assessments, findings, and conditions."""

import uuid
from datetime import UTC, date, datetime, timedelta

from app.db.session import SessionLocal
from app.models import Condition, Location, ServiceOrder
from app.services.program_metrics import store_metrics
from app.services.program_tabs import (
    _drivers,
    _share_naming,
    _six_month,
)
from tests.conftest import headers_for
from tests.test_program_metrics import _findings, _visit

AS_OF = date(2026, 12, 31)


def _stores(*visits_by_store):
    return [store_metrics(uuid.uuid4(), visits, None, AS_OF) for visits in visits_by_store]


def test_share_naming_counts_visits_with_those_words():
    visits = ["serving line and dml", "basement", "ceiling tiles over the dml"]
    assert _share_naming(visits, "ceiling|overhead") == 1 / 3
    assert _share_naming(visits, r"\bdml\b") == 2 / 3
    assert _share_naming([], "dml") is None


def test_six_months_counts_from_the_first_ramp_order():
    day0 = date(2026, 6, 1)
    # Day 0 is DAY0: 6+ months before AS_OF. Activity on day 200 after a 30-day gap.
    late = _stores([_visit(0, 2), _visit(170, 0), _visit(200, 1)])[0]
    stable = _stores([_visit(0, 2), _visit(190, 0), _visit(195, 0)])[0]
    recent = _stores([_visit(0, 2), _visit(14, 0)])[0]
    by_id = {
        s.location_id: Location(id=s.location_id, pestpac_company=f"STORE #{i}")
        for i, s in enumerate((late, stable, recent))
    }
    review = _six_month(
        [late, stable, recent],
        by_id,
        {
            late.location_id: day0,
            stable.location_id: day0,
            recent.location_id: AS_OF - timedelta(days=30),
        },
        AS_OF,
    )
    assert review.stores == 2
    assert review.activity_after == 1
    assert [s.location_id for s in review.activity_stores] == [late.location_id]


def test_drivers_share_the_stores_still_stabilizing():
    recent_day = (AS_OF - date(2026, 6, 1)).days - 10
    environmental = _stores(
        [_visit(recent_day, 1, zones={"dumpster_waste"})],
    )[0]
    plain = _stores([_visit(recent_day, 1, sanitation=1)])[0]
    mall = _stores([_visit(recent_day, 1)])[0]
    drivers = _drivers(
        [environmental, plain, mall],
        [environmental, plain, mall],
        {mall.location_id},
        AS_OF,
    )
    assert drivers.active == 3
    assert drivers.environmental == 2 / 3
    assert drivers.operational == 1 / 3
    assert drivers.structural == 0
    assert drivers.client_reported == 0


def test_the_tab_returns_conditions_and_activity_words_for_the_customer(client, world):
    with SessionLocal() as db:
        order = db.get(ServiceOrder, world.service_order_a)
        order.posted = True
        _findings(
            db,
            world,
            order,
            "low",
            activity_locations=[{"location": "DML ceiling", "zone": "ceiling_voids"}],
        )
        for issue, status, responsibility, severity in (
            (1, "Open", "Customer", "High"),
            (2, "Resolved", "PestManagement", "Low"),
            (3, "Open", "ToBeDetermined", "Medium"),
            (4, "Void", "Customer", "High"),
        ):
            db.add(
                Condition(
                    operator_id=world.op_a,
                    pestpac_issue_id=issue,
                    location_id=world.location_a,
                    status=status,
                    responsibility=responsibility,
                    severity=severity,
                    area="Basement",
                    pestpac_fetched_at=datetime.now(UTC),
                )
            )
        db.commit()
    response = client.get(
        f"/v1/companies/{world.company_a}/program-tabs",
        headers=headers_for(client, world.emails["manager_a"]),
    )
    assert response.status_code == 200
    e = response.json()["executive"]
    c = e["conditions"]
    assert (c["found"], c["assigned"], c["open"], c["resolved"]) == (3, 2, 2, 1)
    assert {o["label"]: o["visits"] for o in c["owners"]} == {
        "Customer": 1,
        "Select": 1,
        "To be determined": 1,
    }
    assert [r["owner"] for r in c["high_open"]] == ["Customer"]
    assert e["ceilings"]["activity_visit_share"] == 1
    assert e["front_line"]["dml_visit_share"] == 1
    assert e["front_line"]["front_visit_share"] == 0
