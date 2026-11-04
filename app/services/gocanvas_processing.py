"""Process GoCanvas webhook deliveries: a submission created or edited on a risk form is fetched
from GoCanvas and stored like a loaded one, with its photos (run by the worker, oldest first,
`SKIP LOCKED`).

A delivery is only a notice:
    {"type": "submission_create", "form": {"id": ...}, "submission": {"id": ...}}
The URL is public and unsigned, so only the ids are used; the data always comes from GoCanvas
with the operator's credentials. Redeliveries are harmless: an unchanged submission is skipped.

A delivery ends `processed`, `ignored` (not a submission event, or not a risk form), or `failed`.
GoCanvas being unavailable retries it with backoff, then fails it. Response bodies are never logged.
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import requests
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.gocanvas import GoCanvasAuthError, GoCanvasClient
from app.models import GoCanvasRequest, InspectionForm, InspectionKind, Tenant
from app.services.gocanvas_connection import ConnectionNotReadyError, get_gocanvas_client
from app.services.inspection_photos import GoCanvasUnavailableError, fetch_submission_photos
from app.services.inspections import InspectionError, import_form, store_submission
from app.storage import StorageError, StorageNotConfiguredError, get_storage

log = logging.getLogger(__name__)

PENDING, PROCESSED, IGNORED, FAILED = "pending", "processed", "ignored", "failed"
SUBMISSION_EVENTS = {"submission_create", "submission_edit"}
# Minutes before each retry; the delivery fails after the last.
RETRY_MINUTES = [1, 5, 15, 60]
RETRY_STATUSES = {401, 403, 408, 429, 500, 502, 503, 504}


class _TryLater(Exception):
    """GoCanvas or storage is unavailable: retry the delivery."""


class _Failed(Exception):
    """This delivery can't be processed as it stands."""


@dataclass
class _Notice:
    form_id: int
    submission_id: int


def _parse_notice(raw: str | None) -> _Notice | None:
    """The ids of a submission event, or None for anything else."""
    try:
        body = json.loads(raw or "")
    except ValueError:
        return None
    if not isinstance(body, dict) or body.get("type") not in SUBMISSION_EVENTS:
        return None
    form, submission = body.get("form"), body.get("submission")
    if not isinstance(form, dict) or not isinstance(submission, dict):
        return None
    form_id, submission_id = form.get("id"), submission.get("id")
    if not isinstance(form_id, int) or not isinstance(submission_id, int):
        return None
    return _Notice(form_id, submission_id)


def claim_next(db: Session) -> GoCanvasRequest | None:
    return db.scalar(
        select(GoCanvasRequest)
        .where(
            GoCanvasRequest.status == PENDING,
            or_(
                GoCanvasRequest.next_attempt_at.is_(None),
                GoCanvasRequest.next_attempt_at <= datetime.now(UTC),
            ),
        )
        .order_by(GoCanvasRequest.received_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )


def _get_json(client: GoCanvasClient, path: str, what: str) -> dict:
    try:
        response = client.get(path)
    except (requests.RequestException, GoCanvasAuthError) as exc:
        raise _TryLater(f"GoCanvas unavailable fetching {what}: {type(exc).__name__}") from exc
    if response.status_code in RETRY_STATUSES:
        raise _TryLater(f"GoCanvas answered {response.status_code} for {what}")
    if response.status_code != 200:
        raise _Failed(f"GoCanvas answered {response.status_code} for {what}")
    try:
        return response.json()
    except ValueError as exc:
        raise _Failed(f"GoCanvas didn't answer JSON for {what}") from exc


def _ensure_form(db: Session, client: GoCanvasClient, operator_id: uuid.UUID, form_id) -> None:
    """Import the definition of the form version the submission was filled in on, first time."""
    if not isinstance(form_id, int):
        raise _Failed("The submission has no form id")
    known = db.scalar(
        select(InspectionForm.id).where(
            InspectionForm.operator_id == operator_id, InspectionForm.gocanvas_form_id == form_id
        )
    )
    if known is None:
        definition = _get_json(client, f"/forms/{form_id}", f"form {form_id}")
        import_form(db, operator_id, definition, InspectionKind.risk)


def _fetch_photos(
    db: Session, client: GoCanvasClient, request: GoCanvasRequest, submission
) -> None:
    try:
        storage = get_storage()
    except StorageNotConfiguredError:
        request.detail = f"{request.detail}; photos not fetched: storage isn't configured"
        db.commit()
        return
    try:
        counts = fetch_submission_photos(db, client, storage, submission)
    except (GoCanvasUnavailableError, StorageError) as exc:
        db.rollback()
        raise _TryLater(f"Photos: {type(exc).__name__}") from exc
    if counts.values_failed:
        request.detail = f"{request.detail}; {counts.values_failed} photo fields failed"
        db.commit()


def _retry(request: GoCanvasRequest, reason: str) -> None:
    request.attempts += 1
    request.detail = reason[:1000]
    if request.attempts > len(RETRY_MINUTES):
        request.status = FAILED
        request.next_attempt_at = None
        request.processed_at = datetime.now(UTC)
    else:
        request.next_attempt_at = datetime.now(UTC) + timedelta(
            minutes=RETRY_MINUTES[request.attempts - 1]
        )


def _end(request: GoCanvasRequest, status: str, detail: str) -> None:
    request.status = status
    request.detail = detail[:1000]
    request.next_attempt_at = None
    request.processed_at = datetime.now(UTC)


def process(db: Session, request: GoCanvasRequest) -> None:
    """Handle one claimed delivery and commit."""
    notice = _parse_notice(request.raw_body)
    if notice is None:
        _end(request, IGNORED, "Not a submission event")
        db.commit()
        return
    request.gocanvas_submission_id = notice.submission_id
    if notice.form_id not in get_settings().risk_form_ids:
        _end(request, IGNORED, f"Form {notice.form_id} isn't a risk form")
        db.commit()
        return
    request_id, operator_id = request.id, request.operator_id
    try:
        client = get_gocanvas_client(db, db.get(Tenant, operator_id))
        path = f"/submissions/{notice.submission_id}"
        payload = _get_json(client, path, f"submission {notice.submission_id}")
        _ensure_form(db, client, operator_id, payload.get("form_id"))
        result = store_submission(db, operator_id, payload, gocanvas_request_id=request_id)
        _end(request, PROCESSED, f"Submission {result.outcome}")
        db.commit()
        _fetch_photos(db, client, request, result.submission)
    except _TryLater as exc:
        db.rollback()
        request = db.get(GoCanvasRequest, request_id)
        # Stored already, photos to fetch: back in the queue. Reprocessing skips the unchanged
        # submission and fetches only the photos still missing.
        request.status = PENDING
        request.processed_at = None
        _retry(request, str(exc))
        db.commit()
    except (_Failed, InspectionError, ConnectionNotReadyError) as exc:
        db.rollback()
        request = db.get(GoCanvasRequest, request_id)
        _end(request, FAILED, str(exc))
        db.commit()


def mark_crashed(db: Session, request_id: uuid.UUID, error: str) -> None:
    request = db.get(GoCanvasRequest, request_id)
    if request is not None:
        _end(request, FAILED, error)
        db.commit()


def requeue(db: Session) -> int:
    """Send ignored and failed deliveries back through the worker, for after GOCANVAS_RISK_FORM_IDS
    or a connection changes. Deliveries from before processing began have no status: untouched.
    Commits."""
    rows = list(
        db.scalars(
            select(GoCanvasRequest).where(
                GoCanvasRequest.status.in_([IGNORED, FAILED]),
                GoCanvasRequest.raw_body.is_not(None),
            )
        )
    )
    for request in rows:
        request.status = PENDING
        request.attempts = 0
        request.next_attempt_at = None
        request.detail = None
        request.processed_at = None
    db.commit()
    return len(rows)
