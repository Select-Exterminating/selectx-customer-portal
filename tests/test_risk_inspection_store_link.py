"""Choosing an inspection's store by hand: the operator's list, the search, and the link."""

from app.db.session import SessionLocal
from app.models import (
    InspectionKind,
    InspectionPhoto,
    InspectionPhotoValue,
    InspectionSubmission,
    Location,
    StoredFile,
)
from app.services.inspections import import_form, store_submission
from tests.conftest import headers_for
from tests.test_inspections import FORM, submission


def _unlink(world) -> None:
    with SessionLocal() as db:
        db.get(InspectionSubmission, world.risk_inspection_a).location_id = None
        db.commit()


def test_operator_list_puts_inspections_without_a_store_first(client, world):
    path = f"/v1/operators/{world.op_a}/risk-inspections"
    headers = headers_for(client, world.emails["admin_a"])
    assert client.get(path, headers=headers).json()[0]["location_id"] is not None
    _unlink(world)
    first = client.get(path, headers=headers).json()[0]
    assert (first["id"], first["location_id"], first["company_name"]) == (
        str(world.risk_inspection_a),
        None,
        None,
    )


def test_store_search_matches_every_word_within_the_operator(client, world):
    headers = headers_for(client, world.emails["admin_a"])
    path = f"/v1/risk-inspections/{world.risk_inspection_a}/store-candidates"
    with SessionLocal() as db:
        name = db.get(Location, world.location_a).pestpac_company
        company = db.get(Location, world.location_a).company_name
    found = client.get(path, params={"q": name}, headers=headers).json()
    assert [c["id"] for c in found] == [str(world.location_a)]
    assert found[0]["company_name"] == company
    assert client.get(path, params={"q": f"{name} nosuchword"}, headers=headers).json() == []
    assert client.get(path, params={"q": "   "}, headers=headers).json() == []
    # A wildcard is a plain character.
    assert client.get(path, params={"q": "%"}, headers=headers).json() == []
    assert client.get(path, params={"q": ""}, headers=headers).status_code == 422


def test_choosing_a_store_links_it_and_records_who(client, world):
    _unlink(world)
    headers = headers_for(client, world.emails["admin_a"])
    response = client.put(
        f"/v1/risk-inspections/{world.risk_inspection_a}/location",
        json={"location_id": str(world.location_a)},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["location_id"] == str(world.location_a)
    assert body["location_linked_by"] == world.emails["admin_a"]
    assert body["location_linked_at"] is not None
    listed = client.get(f"/v1/locations/{world.location_a}/risk-inspections", headers=headers)
    assert str(world.risk_inspection_a) in [i["id"] for i in listed.json()]


def test_a_store_of_another_operator_or_removed_is_refused(client, world):
    with SessionLocal() as db:
        import_form(db, world.op_b, FORM, InspectionKind.risk)
        theirs = store_submission(db, world.op_b, submission("pdf_sample")).submission.id
        db.commit()
    other = client.put(
        f"/v1/risk-inspections/{theirs}/location",
        json={"location_id": str(world.location_a)},
        headers=headers_for(client, world.emails["admin_b"]),
    )
    assert other.status_code == 422

    with SessionLocal() as db:
        location = db.get(Location, world.location_a)
        location.removed_at = location.pestpac_fetched_at
        db.commit()
    removed = client.put(
        f"/v1/risk-inspections/{world.risk_inspection_a}/location",
        json={"location_id": str(world.location_a)},
        headers=headers_for(client, world.emails["admin_a"]),
    )
    assert removed.status_code == 422


def test_photos_move_to_the_chosen_stores_company(client, world):
    _unlink(world)
    with SessionLocal() as db:
        value = InspectionPhotoValue(
            submission_id=world.risk_inspection_a, gocanvas_value_id=1, entry_id=1
        )
        value.photos.append(InspectionPhoto(position=1, file_name="a.jpeg", file_id=world.file_a))
        db.add(value)
        db.get(StoredFile, world.file_a).company_id = None
        db.commit()
    response = client.put(
        f"/v1/risk-inspections/{world.risk_inspection_a}/location",
        json={"location_id": str(world.location_a)},
        headers=headers_for(client, world.emails["admin_a"]),
    )
    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.get(StoredFile, world.file_a).company_id == world.company_a
