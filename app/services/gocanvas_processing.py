"""Process GoCanvas webhook deliveries (run by the worker, oldest first, `SKIP LOCKED`): every
submission a delivery names is fetched from GoCanvas and stored, whatever its form, then the
processing set for its form's root id runs on it.

A delivery is only a notice:
    {"type": "submission_create", "form": {"id": ...}, "submission": {"id": ...}}
The URL is public and unsigned, so only the submission id is used; the data always comes from
GoCanvas with the operator's credentials. Redeliveries are harmless: an unchanged submission is
skipped by its processing.

A delivery ends `processed`, `stored` (kept, but its form has no processing, or that processing
isn't built), `ignored` (not a submission event), or `failed`. GoCanvas being unavailable retries
it with backoff, then fails it. Response bodies are never logged.
"""

import hashlib
import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import requests
from sqlalchemy import case, delete, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.integrations.gocanvas import GoCanvasAuthError, GoCanvasClient
from app.models import (
    GoCanvasForm,
    GoCanvasFormProcessing,
    GoCanvasProcessing,
    GoCanvasRequest,
    GoCanvasSubmission,
    InspectionForm,
    InspectionKind,
    Tenant,
)
from app.schemas.gocanvas import GoCanvasFormProcessingRead
from app.services.gocanvas_connection import ConnectionNotReadyError, get_gocanvas_client
from app.services.inspection_photos import GoCanvasUnavailableError, fetch_submission_photos
from app.services.inspections import InspectionError, import_form, store_submission
from app.storage import StorageError, StorageNotConfiguredError, get_storage

log = logging.getLogger(__name__)

PENDING, PROCESSED, STORED, IGNORED, FAILED = (
    "pending",
    "processed",
    "stored",
    "ignored",
    "failed",
)
SUBMISSION_EVENTS = {"submission_create", "submission_edit"}
# Minutes before each retry; the delivery fails after the last.
RETRY_MINUTES = [1, 5, 15, 60]
RETRY_STATUSES = {401, 403, 408, 429, 500, 502, 503, 504}


class _TryLater(Exception):
    """GoCanvas or storage is unavailable: retry the delivery."""


class _Failed(Exception):
    """This delivery can't be processed as it stands."""


def _submission_id(raw: str | None) -> int | None:
    """The submission id of a submission event, or None for anything else."""
    try:
        body = json.loads(raw or "")
    except ValueError:
        return None
    if not isinstance(body, dict) or body.get("type") not in SUBMISSION_EVENTS:
        return None
    submission = body.get("submission")
    submission_id = submission.get("id") if isinstance(submission, dict) else None
    return submission_id if isinstance(submission_id, int) else None


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


def _store_copy(db: Session, operator_id: uuid.UUID, payload: dict) -> GoCanvasSubmission:
    """Keep the copy just fetched, replacing an earlier one. Flushes; the caller commits."""
    if payload.get("type") != "submission" or not isinstance(payload.get("id"), int):
        raise _Failed("GoCanvas didn't answer with a submission")
    stored = db.scalar(
        select(GoCanvasSubmission).where(
            GoCanvasSubmission.operator_id == operator_id,
            GoCanvasSubmission.gocanvas_submission_id == payload["id"],
        )
    )
    if stored is None:
        stored = GoCanvasSubmission(operator_id=operator_id, gocanvas_submission_id=payload["id"])
        db.add(stored)
    form_id = payload.get("form_id")
    stored.gocanvas_form_id = form_id if isinstance(form_id, int) else None
    stored.payload = payload
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    stored.payload_sha256 = hashlib.sha256(canonical.encode()).hexdigest()
    stored.fetched_at = datetime.now(UTC)
    db.flush()
    return stored


def _ensure_form(
    db: Session, client: GoCanvasClient, operator_id: uuid.UUID, form_id: int | None
) -> GoCanvasForm:
    """The form version the submission was filled in on, fetched the first time. Commits."""
    if form_id is None:
        raise _Failed("The submission has no form id")
    form = db.scalar(
        select(GoCanvasForm).where(
            GoCanvasForm.operator_id == operator_id, GoCanvasForm.gocanvas_form_id == form_id
        )
    )
    if form is not None:
        return form
    definition = _get_json(client, f"/forms/{form_id}", f"form {form_id}")
    if definition.get("type") != "form" or definition.get("id") != form_id:
        raise _Failed(f"GoCanvas didn't answer with form {form_id}")
    form = GoCanvasForm(
        operator_id=operator_id,
        gocanvas_form_id=form_id,
        # A form's first version is its own root.
        root_version_id=definition.get("root_version_id") or form_id,
        name=(definition.get("name") or f"Form {form_id}")[:300],
        version=definition.get("version"),
        definition=definition,
        fetched_at=datetime.now(UTC),
    )
    db.add(form)
    db.commit()
    return form


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


def _run_risk_assessment(
    db: Session,
    client: GoCanvasClient,
    request: GoCanvasRequest,
    stored: GoCanvasSubmission,
    form: GoCanvasForm,
) -> None:
    """Parse the submission into the risk inspection tables, then fetch its photos."""
    known = db.scalar(
        select(InspectionForm.id).where(
            InspectionForm.operator_id == stored.operator_id,
            InspectionForm.gocanvas_form_id == form.gocanvas_form_id,
        )
    )
    if known is None:
        import_form(db, stored.operator_id, form.definition, InspectionKind.risk)
    result = store_submission(
        db, stored.operator_id, stored.payload, gocanvas_request_id=request.id
    )
    stored.processed_as = GoCanvasProcessing.risk_assessment
    stored.processed_at = datetime.now(UTC)
    _end(request, PROCESSED, f"Submission {result.outcome}")
    db.commit()
    _fetch_photos(db, client, request, result.submission)


# A processing without a handler isn't built yet: its submissions wait, stored.
HANDLERS: dict[GoCanvasProcessing, Callable[..., None]] = {
    GoCanvasProcessing.risk_assessment: _run_risk_assessment,
}
LABELS = {
    GoCanvasProcessing.risk_assessment: "Risk Assessment",
    GoCanvasProcessing.ipm_form: "IPM Form",
}


def process(db: Session, request: GoCanvasRequest) -> None:
    """Handle one claimed delivery and commit."""
    # A body past its retention is gone, but the delivery already named its submission.
    submission_id = (
        _submission_id(request.raw_body)
        if request.raw_body is not None
        else request.gocanvas_submission_id
    )
    if submission_id is None:
        _end(request, IGNORED, "Not a submission event")
        db.commit()
        return
    request.gocanvas_submission_id = submission_id
    request_id, operator_id = request.id, request.operator_id
    try:
        client = get_gocanvas_client(db, db.get(Tenant, operator_id))
        payload = _get_json(client, f"/submissions/{submission_id}", f"submission {submission_id}")
        stored = _store_copy(db, operator_id, payload)
        db.commit()
        form = _ensure_form(db, client, operator_id, stored.gocanvas_form_id)
        stored.root_version_id = form.root_version_id
        db.commit()
        processing = db.scalar(
            select(GoCanvasFormProcessing.processing).where(
                GoCanvasFormProcessing.operator_id == operator_id,
                GoCanvasFormProcessing.root_version_id == form.root_version_id,
            )
        )
        if processing is None:
            _end(request, STORED, f"Stored; form root {form.root_version_id} has no processing")
        elif processing not in HANDLERS:
            _end(request, STORED, f"Stored; {LABELS[processing]} processing isn't built yet")
        else:
            HANDLERS[processing](db, client, request, stored, form)
        db.commit()
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


def _back_in_queue(request: GoCanvasRequest) -> None:
    request.status = PENDING
    request.attempts = 0
    request.next_attempt_at = None
    request.detail = None
    request.processed_at = None


def requeue(db: Session) -> int:
    """Send ignored, failed, and stored-only deliveries back through the worker, for after a
    connection changes or a processing is built. Deliveries from before processing began have no
    status: untouched. One with neither a body nor a submission id has nothing to go on. Commits."""
    rows = list(
        db.scalars(
            select(GoCanvasRequest).where(
                GoCanvasRequest.status.in_([STORED, IGNORED, FAILED]),
                or_(
                    GoCanvasRequest.raw_body.is_not(None),
                    GoCanvasRequest.gocanvas_submission_id.is_not(None),
                ),
            )
        )
    )
    for request in rows:
        _back_in_queue(request)
    db.commit()
    return len(rows)


def _queue_unprocessed(db: Session, operator_id: uuid.UUID, root_version_id: int) -> int:
    """Send each stored submission under this root that nothing has run on back through the
    worker, by its latest delivery."""
    unprocessed = select(GoCanvasSubmission.gocanvas_submission_id).where(
        GoCanvasSubmission.operator_id == operator_id,
        GoCanvasSubmission.root_version_id == root_version_id,
        GoCanvasSubmission.processed_as.is_(None),
    )
    rows = list(
        db.scalars(
            select(GoCanvasRequest)
            .where(
                GoCanvasRequest.operator_id == operator_id,
                GoCanvasRequest.gocanvas_submission_id.in_(unprocessed),
            )
            .ext(distinct_on(GoCanvasRequest.gocanvas_submission_id))
            .order_by(GoCanvasRequest.gocanvas_submission_id, GoCanvasRequest.received_at.desc())
        )
    )
    for request in rows:
        _back_in_queue(request)
    return len(rows)


def list_form_processing(db: Session, operator_id: uuid.UUID) -> list[GoCanvasFormProcessingRead]:
    """Every root with processing set or seen in a stored form, newest root last."""
    processing = dict(
        db.execute(
            select(GoCanvasFormProcessing.root_version_id, GoCanvasFormProcessing.processing).where(
                GoCanvasFormProcessing.operator_id == operator_id
            )
        ).all()
    )
    # Oldest version first, so the newest name wins.
    names = dict(
        db.execute(
            select(GoCanvasForm.root_version_id, GoCanvasForm.name)
            .where(GoCanvasForm.operator_id == operator_id)
            .order_by(GoCanvasForm.version.asc().nulls_first(), GoCanvasForm.gocanvas_form_id)
        ).all()
    )
    counts = {
        root: (total, unprocessed)
        for root, total, unprocessed in db.execute(
            select(
                GoCanvasSubmission.root_version_id,
                func.count(),
                func.sum(case((GoCanvasSubmission.processed_as.is_(None), 1), else_=0)),
            )
            .where(
                GoCanvasSubmission.operator_id == operator_id,
                GoCanvasSubmission.root_version_id.is_not(None),
            )
            .group_by(GoCanvasSubmission.root_version_id)
        )
    }
    return [
        GoCanvasFormProcessingRead(
            root_version_id=root,
            form_name=names.get(root),
            processing=processing.get(root),
            submission_count=counts.get(root, (0, 0))[0],
            unprocessed_count=counts.get(root, (0, 0))[1],
        )
        for root in sorted(processing.keys() | names.keys())
    ]


def set_form_processing(
    db: Session,
    operator_id: uuid.UUID,
    root_version_id: int,
    processing: GoCanvasProcessing,
    user_id: uuid.UUID,
) -> None:
    """Set a root's processing and queue what's waiting for it. What already ran isn't run again.
    Commits."""
    row = db.scalar(
        select(GoCanvasFormProcessing).where(
            GoCanvasFormProcessing.operator_id == operator_id,
            GoCanvasFormProcessing.root_version_id == root_version_id,
        )
    )
    if row is None:
        row = GoCanvasFormProcessing(operator_id=operator_id, root_version_id=root_version_id)
        db.add(row)
    row.processing = processing
    row.updated_by = user_id
    if processing in HANDLERS:
        _queue_unprocessed(db, operator_id, root_version_id)
    db.commit()


def clear_form_processing(db: Session, operator_id: uuid.UUID, root_version_id: int) -> None:
    """Stop processing a root: its submissions are still stored. Commits."""
    db.execute(
        delete(GoCanvasFormProcessing).where(
            GoCanvasFormProcessing.operator_id == operator_id,
            GoCanvasFormProcessing.root_version_id == root_version_id,
        )
    )
    db.commit()
