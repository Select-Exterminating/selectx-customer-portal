"""GoCanvas deliveries: every submission fetched and stored by the worker, routed by its form's
root id, anything else ignored, and GoCanvas failures retried."""

import json
from datetime import UTC, datetime, timedelta

import pytest
import responses
from sqlalchemy import delete, func, select, update

from app import worker
from app.db.session import SessionLocal
from app.models import (
    GoCanvasForm,
    GoCanvasFormProcessing,
    GoCanvasProcessing,
    GoCanvasRequest,
    GoCanvasSubmission,
    InspectionForm,
    InspectionPhoto,
    InspectionSubmission,
)
from app.services import gocanvas_processing
from tests.conftest import GOCANVAS_BASE, GOCANVAS_TOKEN_URL, headers_for
from tests.test_inspection_photos import PEST_VALUE, VALUE_URL, photo_zip
from tests.test_inspections import FORM, submission

SUBMISSION = submission("pdf_sample")
SUBMISSION_URL = f"{GOCANVAS_BASE}/submissions/{SUBMISSION['id']}"
FORM_URL = f"{GOCANVAS_BASE}/forms/{FORM['id']}"
ROOT = FORM["root_version_id"]


def _notice(event="submission_create", form_id=FORM["id"], submission_id=SUBMISSION["id"]) -> dict:
    return {
        "type": event,
        "form": {"id": form_id, "name": "A form", "guid": "abc", "tag": ""},
        "submission": {"id": submission_id, "guid": "def"},
    }


@pytest.fixture
def gocanvas():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.post(GOCANVAS_TOKEN_URL, json={"access_token": "gocanvas-token", "expires_in": 7200})
        rsps.get(SUBMISSION_URL, json=SUBMISSION)
        rsps.get(FORM_URL, json=FORM)
        rsps.add_callback(
            responses.GET,
            VALUE_URL,
            lambda request: (
                200,
                {"Content-Type": "application/zip"},
                photo_zip(int(request.url.rsplit("/", 1)[1])),
            ),
        )
        yield rsps


@pytest.fixture(autouse=True)
def risk_processing(world):
    """The fixture form's root is processed as risk assessments, unless a test clears it."""
    _set_processing(world, ROOT, GoCanvasProcessing.risk_assessment)


def _set_processing(world, root, processing) -> None:
    with SessionLocal() as db:
        db.add(
            GoCanvasFormProcessing(
                operator_id=world.op_a, root_version_id=root, processing=processing
            )
        )
        db.commit()


def _clear_processing() -> None:
    with SessionLocal() as db:
        db.execute(delete(GoCanvasFormProcessing))
        db.commit()


def _risk_copies(db) -> int:
    return db.scalar(
        select(func.count())
        .select_from(InspectionSubmission)
        .where(InspectionSubmission.gocanvas_submission_id == SUBMISSION["id"])
    )


def _stored(db) -> GoCanvasSubmission:
    return db.scalar(
        select(GoCanvasSubmission).where(
            GoCanvasSubmission.gocanvas_submission_id == SUBMISSION["id"]
        )
    )


def _deliver(client, world, body) -> None:
    raw = body if isinstance(body, str) else json.dumps(body)
    assert client.post(f"/v1/webhooks/gocanvas/{world.op_a}", content=raw).status_code == 200


def _latest(db) -> GoCanvasRequest:
    return db.scalar(
        select(GoCanvasRequest)
        .where(GoCanvasRequest.status.is_not(None))
        .order_by(GoCanvasRequest.received_at.desc())
        .limit(1)
    )


def _calls(rsps, url: str) -> int:
    return sum(1 for call in rsps.calls if call.request.url == url)


def test_a_risk_form_submission_is_fetched_and_stored_with_its_photos(client, world, gocanvas):
    _deliver(client, world, _notice())
    assert worker.run_pending_gocanvas() == 1
    with SessionLocal() as db:
        request = _latest(db)
        assert (request.status, request.gocanvas_submission_id) == ("processed", SUBMISSION["id"])
        assert request.detail == "Submission created"
        stored = db.scalar(
            select(InspectionSubmission).where(
                InspectionSubmission.gocanvas_submission_id == SUBMISSION["id"]
            )
        )
        assert stored.gocanvas_request_id == request.id
        assert stored.risk_zones
        # The form's definition was imported on first sight.
        assert db.scalar(
            select(InspectionForm).where(InspectionForm.gocanvas_form_id == FORM["id"])
        )
        assert db.scalar(select(func.count()).select_from(InspectionPhoto)) > 0
    assert any(str(PEST_VALUE) in call.request.url for call in gocanvas.calls)


def test_a_redelivery_and_an_edit_are_safe_and_the_form_is_imported_once(client, world, gocanvas):
    _deliver(client, world, _notice())
    _deliver(client, world, _notice())
    _deliver(client, world, _notice("submission_edit"))
    assert worker.run_pending_gocanvas() == 3
    with SessionLocal() as db:
        statuses = db.scalars(
            select(GoCanvasRequest.detail)
            .where(GoCanvasRequest.status == "processed")
            .order_by(GoCanvasRequest.received_at)
        ).all()
        assert statuses == ["Submission created", "Submission unchanged", "Submission unchanged"]
        stored = db.scalar(
            select(func.count())
            .select_from(InspectionSubmission)
            .where(InspectionSubmission.gocanvas_submission_id == SUBMISSION["id"])
        )
        assert stored == 1
    assert _calls(gocanvas, FORM_URL) == 1


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        (_notice(event="form_update"), "Not a submission event"),
        ({"type": "submission_create", "form": {"id": FORM["id"]}}, "Not a submission event"),
        ("<xml>not json</xml>", "Not a submission event"),
    ],
)
def test_other_deliveries_are_ignored_without_calling_gocanvas(client, world, body, detail):
    # No GoCanvas mock: a call would fail the test.
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        _deliver(client, world, body)
        assert worker.run_pending_gocanvas() == 1
        assert len(rsps.calls) == 0
    with SessionLocal() as db:
        request = _latest(db)
        assert (request.status, request.detail) == ("ignored", detail)


def test_a_form_without_processing_is_stored_and_nothing_runs(client, world, gocanvas):
    _clear_processing()
    _deliver(client, world, _notice())
    assert worker.run_pending_gocanvas() == 1
    with SessionLocal() as db:
        request = _latest(db)
        assert request.status == "stored"
        assert request.detail == f"Stored; form root {ROOT} has no processing"
        stored = _stored(db)
        assert stored.payload["id"] == SUBMISSION["id"]
        assert (stored.gocanvas_form_id, stored.root_version_id) == (FORM["id"], ROOT)
        assert stored.processed_as is None
        assert db.scalar(select(GoCanvasForm.name)) == FORM["name"]
        assert _risk_copies(db) == 0
    assert not any(str(PEST_VALUE) in call.request.url for call in gocanvas.calls)


def test_a_new_form_version_under_a_known_root_is_processed(client, world, gocanvas):
    new_id = FORM["id"] + 1000
    gocanvas.get(f"{GOCANVAS_BASE}/forms/{new_id}", json={**FORM, "id": new_id})
    gocanvas.replace(responses.GET, SUBMISSION_URL, json={**SUBMISSION, "form_id": new_id})
    _deliver(client, world, _notice(form_id=new_id))
    worker.run_pending_gocanvas()
    with SessionLocal() as db:
        assert _latest(db).status == "processed"
        assert db.scalar(select(InspectionForm).where(InspectionForm.gocanvas_form_id == new_id))
        assert _stored(db).processed_as == GoCanvasProcessing.risk_assessment


def test_a_first_version_without_a_root_is_its_own_root(client, world, gocanvas):
    _clear_processing()
    gocanvas.replace(responses.GET, FORM_URL, json={**FORM, "root_version_id": None})
    _deliver(client, world, _notice())
    worker.run_pending_gocanvas()
    with SessionLocal() as db:
        assert _stored(db).root_version_id == FORM["id"]


def test_ipm_forms_are_stored_until_their_processing_is_built(client, world, gocanvas):
    _clear_processing()
    _set_processing(world, ROOT, GoCanvasProcessing.ipm_form)
    _deliver(client, world, _notice())
    worker.run_pending_gocanvas()
    with SessionLocal() as db:
        request = _latest(db)
        assert request.status == "stored"
        assert request.detail == "Stored; IPM Form processing isn't built yet"
        assert _stored(db).processed_as is None
        assert _risk_copies(db) == 0


def test_an_edit_replaces_the_stored_copy(client, world, gocanvas):
    _deliver(client, world, _notice())
    worker.run_pending_gocanvas()
    with SessionLocal() as db:
        first = _stored(db).payload_sha256
    edited = {**SUBMISSION, "revision": True, "revised_at": "2099-01-01T00:00:00Z"}
    gocanvas.replace(responses.GET, SUBMISSION_URL, json=edited)
    _deliver(client, world, _notice("submission_edit"))
    worker.run_pending_gocanvas()
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(GoCanvasSubmission)) == 1
        stored = _stored(db)
        assert stored.payload_sha256 != first
        assert stored.payload["revised_at"] == edited["revised_at"]


def test_the_copy_is_kept_when_the_form_cannot_be_fetched(client, world, gocanvas):
    gocanvas.replace(responses.GET, FORM_URL, status=503, body="down")
    _deliver(client, world, _notice())
    worker.run_pending_gocanvas()
    with SessionLocal() as db:
        request = _latest(db)
        assert (request.status, request.attempts) == ("pending", 1)
        assert request.detail == f"GoCanvas answered 503 for form {FORM['id']}"
        stored = _stored(db)
        assert stored.payload["id"] == SUBMISSION["id"]
        assert stored.root_version_id is None


def test_an_answer_that_is_not_a_submission_fails(client, world, gocanvas):
    gocanvas.replace(responses.GET, SUBMISSION_URL, json={"type": "form", "id": 1})
    _deliver(client, world, _notice())
    worker.run_pending_gocanvas()
    with SessionLocal() as db:
        request = _latest(db)
        assert (request.status, request.detail) == (
            "failed",
            "GoCanvas didn't answer with a submission",
        )
        assert db.scalar(select(func.count()).select_from(GoCanvasSubmission)) == 0


def test_setting_processing_runs_what_was_waiting_once(client, world, gocanvas):
    _clear_processing()
    _deliver(client, world, _notice())
    _deliver(client, world, _notice("submission_edit"))
    assert worker.run_pending_gocanvas() == 2
    admin = headers_for(client, world.emails["admin_a"])
    url = f"/v1/operators/{world.op_a}/gocanvas-form-processing"

    rows = client.get(url, headers=admin).json()["items"]
    assert rows == [
        {
            "root_version_id": ROOT,
            "form_name": FORM["name"],
            "processing": None,
            "submission_count": 1,
            "unprocessed_count": 1,
        }
    ]

    saved = client.put(f"{url}/{ROOT}", json={"processing": "risk_assessment"}, headers=admin)
    assert saved.status_code == 200
    assert saved.json()["processing"] == "risk_assessment"
    # Only the submission's latest delivery goes back in the queue.
    assert worker.run_pending_gocanvas() == 1
    row = client.get(url, headers=admin).json()["items"][0]
    assert (row["submission_count"], row["unprocessed_count"]) == (1, 0)
    with SessionLocal() as db:
        assert _stored(db).processed_as == GoCanvasProcessing.risk_assessment
        assert _risk_copies(db) == 1

    # Nothing is waiting now, so saving again queues nothing.
    client.put(f"{url}/{ROOT}", json={"processing": "risk_assessment"}, headers=admin)
    assert worker.run_pending_gocanvas() == 0


def test_setting_a_processing_that_is_not_built_queues_nothing(client, world, gocanvas):
    _clear_processing()
    _deliver(client, world, _notice())
    worker.run_pending_gocanvas()
    admin = headers_for(client, world.emails["admin_a"])
    url = f"/v1/operators/{world.op_a}/gocanvas-form-processing/{ROOT}"
    assert client.put(url, json={"processing": "ipm_form"}, headers=admin).status_code == 200
    assert worker.run_pending_gocanvas() == 0


def test_a_root_can_be_set_before_anything_arrives_and_cleared(client, world):
    _clear_processing()
    admin = headers_for(client, world.emails["admin_a"])
    url = f"/v1/operators/{world.op_a}/gocanvas-form-processing"
    assert client.put(f"{url}/346127", json={"processing": "ipm_form"}, headers=admin).json() == {
        "root_version_id": 346127,
        "form_name": None,
        "processing": "ipm_form",
        "submission_count": 0,
        "unprocessed_count": 0,
    }
    assert client.delete(f"{url}/346127", headers=admin).status_code == 204
    assert client.get(url, headers=admin).json()["items"] == []


@pytest.mark.parametrize(
    ("root", "body"),
    [
        (ROOT, {"processing": "nonsense"}),
        (0, {"processing": "ipm_form"}),
        (2**63, {"processing": "ipm_form"}),
    ],
)
def test_bad_form_processing_is_refused(client, world, root, body):
    admin = headers_for(client, world.emails["admin_a"])
    url = f"/v1/operators/{world.op_a}/gocanvas-form-processing/{root}"
    assert client.put(url, json=body, headers=admin).status_code == 422


def test_a_delivery_past_its_retention_can_still_be_requeued(client, world, gocanvas):
    _clear_processing()
    _deliver(client, world, _notice())
    worker.run_pending_gocanvas()
    with SessionLocal() as db:
        db.execute(update(GoCanvasRequest).values(raw_body=None))
        db.commit()
        assert gocanvas_processing.requeue(db) == 1
    _set_processing(world, ROOT, GoCanvasProcessing.risk_assessment)
    assert worker.run_pending_gocanvas() == 1
    with SessionLocal() as db:
        assert _latest(db).status == "processed"


def test_gocanvas_failing_is_retried_with_backoff_then_fails(client, world):
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        rsps.post(GOCANVAS_TOKEN_URL, json={"access_token": "gocanvas-token", "expires_in": 7200})
        rsps.get(SUBMISSION_URL, status=503, body="internal detail")
        _deliver(client, world, _notice())
        assert worker.run_pending_gocanvas() == 1
        with SessionLocal() as db:
            request = _latest(db)
            assert (request.status, request.attempts) == ("pending", 1)
            assert request.detail == f"GoCanvas answered 503 for submission {SUBMISSION['id']}"
            assert request.next_attempt_at > datetime.now(UTC)
        # Not due yet: left alone.
        assert worker.run_pending_gocanvas() == 0

        for _ in gocanvas_processing.RETRY_MINUTES:
            with SessionLocal() as db:
                db.execute(
                    update(GoCanvasRequest)
                    .where(GoCanvasRequest.status == "pending")
                    .values(next_attempt_at=datetime.now(UTC) - timedelta(minutes=1))
                )
                db.commit()
            assert worker.run_pending_gocanvas() == 1
        with SessionLocal() as db:
            assert _latest(db).status == "failed"
        assert worker.run_pending_gocanvas() == 0


def test_a_missing_submission_fails_and_requeue_sends_it_back(client, world, gocanvas):
    gocanvas.replace(responses.GET, SUBMISSION_URL, status=404, body="gone")
    _deliver(client, world, _notice())
    worker.run_pending_gocanvas()
    with SessionLocal() as db:
        request = _latest(db)
        assert request.status == "failed"
        assert request.detail == f"GoCanvas answered 404 for submission {SUBMISSION['id']}"
        assert gocanvas_processing.requeue(db) == 1

    gocanvas.replace(responses.GET, SUBMISSION_URL, json=SUBMISSION)
    assert worker.run_pending_gocanvas() == 1
    with SessionLocal() as db:
        assert _latest(db).status == "processed"


def test_requests_from_before_processing_are_left_alone(client, world, gocanvas):
    with SessionLocal() as db:
        old = db.get(GoCanvasRequest, world.gocanvas_request_a)
        assert old.status is None
        assert gocanvas_processing.requeue(db) == 0
    assert worker.run_pending_gocanvas() == 0


def test_the_gocanvas_tab_shows_the_outcome(client, world, gocanvas):
    _deliver(client, world, _notice())
    worker.run_pending_gocanvas()
    admin = headers_for(client, world.emails["admin_a"])
    items = client.get(f"/v1/operators/{world.op_a}/gocanvas-requests", headers=admin).json()[
        "items"
    ]
    newest = next(i for i in items if i["status"])
    assert newest["status"] == "processed"
    assert newest["detail"] == "Submission created"
    assert newest["gocanvas_submission_id"] == SUBMISSION["id"]
