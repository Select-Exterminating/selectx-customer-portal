"""Client-reported findings: logged by staff, read on the store profile, flagged in Store Watch."""

from datetime import date, timedelta

from app.db.session import SessionLocal
from app.models import ClientFinding
from app.services.program_metrics import CLIENT_FINDING_DAYS, store_metrics
from tests.conftest import headers_for
from tests.test_program_metrics import _visit

AS_OF = date(2026, 6, 30)


def _finding(status: str = "open", days_ago: int = 3) -> ClientFinding:
    return ClientFinding(
        source="Food safety walk",
        finding="Droppings in the basement",
        severity="high",
        status=status,
        logged_on=AS_OF - timedelta(days=days_ago),
    )


def _flags(metrics) -> list[str]:
    return [code for code, _, _ in metrics.flags]


def test_an_open_recent_finding_escalates_a_store_with_no_other_flags():
    visits = [_visit(i, 0) for i in range(0, 28, 7)]
    calm = store_metrics(None, visits, None, AS_OF)
    assert calm.attention != "Escalated" and "client" not in _flags(calm)
    flagged = store_metrics(None, visits, None, AS_OF, [_finding()])
    assert flagged.attention == "Escalated"
    code, weight, detail = flagged.flags[0]
    assert (code, weight) == ("client", 4)
    assert detail == "Food safety walk: Droppings in the basement"


def test_it_escalates_a_store_never_serviced():
    assert store_metrics(None, [], None, AS_OF).attention == "Not Yet Serviced"
    assert store_metrics(None, [], None, AS_OF, [_finding()]).attention == "Escalated"


def test_closed_or_old_findings_flag_nothing():
    visits = [_visit(i, 0) for i in range(0, 28, 7)]
    for finding in (_finding(status="closed"), _finding(days_ago=CLIENT_FINDING_DAYS + 1)):
        assert "client" not in _flags(store_metrics(None, visits, None, AS_OF, [finding]))
    on_the_day = store_metrics(None, visits, None, AS_OF, [_finding(days_ago=CLIENT_FINDING_DAYS)])
    assert "client" in _flags(on_the_day)


def test_logging_and_closing_reach_the_flyover_and_store_watch(client, world):
    admin = headers_for(client, world.emails["admin_a"])
    manager = headers_for(client, world.emails["manager_a"])
    profile = f"/v1/companies/{world.company_a}/stores/{world.location_a}/profile"
    watch = f"/v1/companies/{world.company_a}/program-dashboard"
    body = {
        "reported_on": "2026-10-26",
        "source": "  Food safety walk ",
        "finding": "Droppings in the basement",
        "zone": "basement",
        "severity": "high",
        "select_response": "Escalated.",
    }
    created = client.post(
        f"/v1/locations/{world.location_a}/client-findings", json=body, headers=admin
    )
    assert created.status_code == 201
    finding = created.json()
    assert (finding["source"], finding["status"], finding["logged_on"]) == (
        "Food safety walk",
        "open",
        date.today().isoformat(),
    )
    assert finding["zone"] == "basement" and finding["zone_name"]

    # The customer's users read it, newest first, and it flags the store for them too.
    seen = client.get(profile, headers=manager).json()
    assert seen["client_findings"][0]["id"] == finding["id"]
    assert seen["attention"] == "Escalated"
    assert seen["flags"][0]["code"] == "client"
    row = next(
        s
        for s in client.get(watch, headers=manager).json()["stores"]
        if s["location_id"] == str(world.location_a)
    )
    assert row["attention"] == "Escalated"

    closed = client.put(
        f"/v1/client-findings/{finding['id']}", json={**body, "status": "closed"}, headers=admin
    )
    assert closed.status_code == 200 and closed.json()["status"] == "closed"
    after = client.get(profile, headers=admin).json()
    assert "client" not in [f["code"] for f in after["flags"]]
    assert len(after["client_findings"]) == 2  # kept, beside the world's closed one


def test_customer_users_cant_log_findings_and_bad_values_are_refused(client, world):
    path = f"/v1/locations/{world.location_a}/client-findings"
    good = {"source": "Store team", "finding": "Droppings", "severity": "high"}
    manager = headers_for(client, world.emails["manager_a"])
    assert client.post(path, json=good, headers=manager).status_code == 404
    admin = headers_for(client, world.emails["admin_a"])
    for bad in ({"source": "  "}, {"finding": ""}, {"severity": "extreme"}, {"zone": "attic"}):
        assert client.post(path, json={**good, **bad}, headers=admin).status_code == 422
    other_op = headers_for(client, world.emails["admin_b"])
    assert client.post(path, json=good, headers=other_op).status_code == 404
    with SessionLocal() as db:
        assert db.query(ClientFinding).count() == 1  # only the world's
