"""GoCanvas deliveries: risk form submissions fetched and stored by the worker, everything else
ignored, and GoCanvas failures retried."""

import json
from datetime import UTC, datetime, timedelta

import pytest
import responses
from sqlalchemy import func, select, update

from app import worker
from app.db.session import SessionLocal
from app.models import GoCanvasRequest, InspectionForm, InspectionPhoto, InspectionSubmission
from app.services import gocanvas_processing
from tests.conftest import GOCANVAS_BASE, GOCANVAS_TOKEN_URL, headers_for
from tests.test_inspection_photos import PEST_VALUE, VALUE_URL, photo_zip
from tests.test_inspections import FORM, submission

SUBMISSION = submission("pdf_sample")
SUBMISSION_URL = f"{GOCANVAS_BASE}/submissions/{SUBMISSION['id']}"
FORM_URL = f"{GOCANVAS_BASE}/forms/{FORM['id']}"


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
        (_notice(form_id=5961790), "Form 5961790 isn't a risk form"),
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
