"""Assessment targets: how many restaurants in each state the risk assessments cover."""

from app.db.session import SessionLocal
from app.models import Location
from tests.conftest import headers_for


def _coverage(client, world, headers, **params) -> dict:
    response = client.get(
        f"/v1/companies/{world.company_a}/risk-assessment-dashboard",
        params=params,
        headers=headers,
    )
    assert response.status_code == 200
    return {c["state"]: c for c in response.json()["coverage"]}


def test_targets_replace_and_reach_the_coverage(client, world):
    headers = headers_for(client, world.emails["admin_a"])
    path = f"/v1/companies/{world.company_a}/assessment-targets"
    with SessionLocal() as db:
        db.get(Location, world.location_a).state = "NY"
        db.commit()

    assert client.get(path, headers=headers).json() == {"targets": []}
    assert _coverage(client, world, headers)["NY"]["target"] is None

    targets = [{"state": "MD", "total": 125}, {"state": "NY", "total": 249}]
    assert client.put(path, json={"targets": targets}, headers=headers).status_code == 200
    assert client.get(path, headers=headers).json() == {"targets": targets}

    coverage = _coverage(client, world, headers)
    assert (coverage["NY"]["target"], coverage["NY"]["assessed"]) == (249, 1)
    # A state with a target and no locations of ours still shows.
    assert (coverage["MD"]["target"], coverage["MD"]["in_program"]) == (125, 0)

    assert set(_coverage(client, world, headers, state="NY")) == {"NY"}
    # Targets cover the company, so one bill-to's view has none.
    one_bill_to = _coverage(client, world, headers, bill_to_id=str(world.bill_to_a))
    assert set(one_bill_to) == {"NY"}
    assert one_bill_to["NY"]["target"] is None

    # Replacing drops what's left out.
    assert client.put(path, json={"targets": targets[:1]}, headers=headers).status_code == 200
    assert _coverage(client, world, headers)["NY"]["target"] is None


def test_bad_targets_are_refused(client, world):
    headers = headers_for(client, world.emails["admin_a"])
    path = f"/v1/companies/{world.company_a}/assessment-targets"
    for targets in (
        [{"state": "NY", "total": 1}, {"state": "NY", "total": 2}],
        [{"state": "ny", "total": 1}],
        [{"state": "NY", "total": -1}],
    ):
        assert client.put(path, json={"targets": targets}, headers=headers).status_code == 422


def test_customer_users_see_targets_only_through_the_dashboard(client, world):
    admin = headers_for(client, world.emails["admin_a"])
    path = f"/v1/companies/{world.company_a}/assessment-targets"
    with SessionLocal() as db:
        db.get(Location, world.location_a).state = "NY"
        db.commit()
    targets = [{"state": "NY", "total": 249}]
    assert client.put(path, json={"targets": targets}, headers=admin).status_code == 200

    manager = headers_for(client, world.emails["manager_a"])
    assert client.get(path, headers=manager).status_code == 404
    assert _coverage(client, world, manager)["NY"]["target"] == 249
