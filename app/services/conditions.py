"""PestPac conditions (issues) for a location, open and closed, with inspections and documents.

1. GET /Locations/{id}/conditions lists the location's conditions (summaries, unpaged), with
   no status filter, so closed ones (the remediation history) come too.
2. GET /Conditions/{id} gives a condition's inspections and documents. It's fetched for new
   conditions and when the summary changes (LastInspectedDate moves when a technician
   inspects, adding inspections and photos; the status changes when it closes), and once more
   for an open condition PestPac stops listing, to record how it closed or that it's gone.

A condition's documents go into `documents` (linked to the condition and location); their
files are fetched by the location's file step like any other document.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import requests
from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.integrations.pestpac import PestPacAuthError, PestPacClient
from app.models import Condition, ConditionInspection, Document, Location, ServiceOrder
from app.schemas.pestpac import (
    ConditionSyncCounts,
    PestPacConditionDetails,
    PestPacConditionListItem,
    PestPacConditionSummary,
)
from app.schemas.reports import ReportConditionComment
from app.services import documents
from app.services.pestpac_connection import PestPacUnavailableError

# An inspection comment with no order belongs to the visit up to this long before it: the office
# records results after a night service.
UNLINKED_COMMENT_WINDOW = timedelta(hours=24)
# One linked to an order further than this from its work date isn't about that visit.
LINKED_COMMENT_MAX_GAP = timedelta(days=7)


def _get(client: PestPacClient, path: str, params: dict | None = None) -> requests.Response:
    try:
        return client.custom_endpoint(path).get(params=params)
    except (PestPacAuthError, requests.RequestException) as exc:
        raise PestPacUnavailableError(f"Could not reach PestPac: {type(exc).__name__}") from exc


def fetch_conditions(
    client: PestPacClient, pestpac_location_id: int
) -> list[PestPacConditionListItem]:
    response = _get(client, f"/Locations/{pestpac_location_id}/conditions")
    if response.status_code != 200:
        raise PestPacUnavailableError(
            f"PestPac /Locations/{pestpac_location_id}/conditions returned {response.status_code}"
        )
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, list) or not all(isinstance(c, dict) and "IssueID" in c for c in body):
        raise PestPacUnavailableError("PestPac returned an unexpected conditions response")
    return [PestPacConditionListItem.from_api(c) for c in body]


def fetch_condition(client: PestPacClient, pestpac_issue_id: int) -> PestPacConditionDetails | None:
    """The condition with inspections and documents, or None if PestPac no longer has it."""
    response = _get(client, f"/Conditions/{pestpac_issue_id}")
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise PestPacUnavailableError(f"PestPac /Conditions returned {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or body.get("IssueID") != pestpac_issue_id:
        raise PestPacUnavailableError("PestPac returned an unexpected condition response")
    try:
        return PestPacConditionDetails.from_api(body)
    except ValueError as exc:
        raise PestPacUnavailableError(f"PestPac returned an unexpected condition: {exc}") from exc


def _order_id(db: Session, operator_id: uuid.UUID, pestpac_order_id: int | None):
    if pestpac_order_id is None:
        return None
    return db.scalar(
        select(ServiceOrder.id).where(
            ServiceOrder.operator_id == operator_id,
            ServiceOrder.pestpac_order_id == pestpac_order_id,
        )
    )


def _inspection_order_id(db: Session, condition: Condition, pestpac_order_id: int | None):
    """An inspection's order field holds the OrderID or, on some, the order's number."""
    if not pestpac_order_id:
        return None
    return _order_id(db, condition.operator_id, pestpac_order_id) or db.scalar(
        select(ServiceOrder.id)
        .where(
            ServiceOrder.operator_id == condition.operator_id,
            ServiceOrder.location_id == condition.location_id,
            ServiceOrder.order_number == str(pestpac_order_id),
        )
        .limit(1)
    )


def _apply_summary(
    db: Session,
    condition: Condition,
    summary: PestPacConditionSummary,
    location: Location,
    now: datetime,
) -> None:
    for field in PestPacConditionSummary.model_fields:
        setattr(condition, field, getattr(summary, field))
    # Listed under (or fetched for) this location.
    condition.location_id = location.id
    condition.pestpac_location_id = condition.pestpac_location_id or location.pestpac_location_id
    condition.service_order_id = _order_id(db, condition.operator_id, summary.pestpac_order_id)
    condition.removed_at = None
    condition.pestpac_fetched_at = now


def _apply_details(
    db: Session,
    condition: Condition,
    details: PestPacConditionDetails,
    location: Location,
    now: datetime,
    counts: ConditionSyncCounts,
) -> None:
    _apply_summary(db, condition, details, location, now)
    condition.specific_area = details.specific_area
    condition.opened_by_user = details.opened_by_user
    condition.inspections = [
        ConditionInspection(
            service_order_id=_inspection_order_id(db, condition, i.pestpac_order_id),
            **i.model_dump(),
        )
        for i in details.inspections
    ]
    condition.details_fetched_at = now
    db.flush()  # the condition needs its id before documents point at it
    for document, _ in documents.upsert_documents(db, location, details.documents, now):
        if document.condition_id != condition.id:
            counts.documents_linked += 1
        document.condition_id = condition.id
        document.pestpac_issue_id = condition.pestpac_issue_id
    counts.details_fetched += 1


def _changed(condition: Condition, item: PestPacConditionListItem) -> bool:
    return (
        condition.details_fetched_at is None
        or condition.last_inspected_date != item.last_inspected_date
        or condition.status != item.status
    )


def sync_location_conditions(
    db: Session, client: PestPacClient, location: Location, counts: ConditionSyncCounts
) -> None:
    """Upsert the location's conditions, and record open ones that dropped off the list. Does
    not commit."""
    listed = fetch_conditions(client, location.pestpac_location_id)
    now = datetime.now(UTC)
    counts.total += len(listed)
    existing = {
        c.pestpac_issue_id: c
        for c in db.scalars(
            select(Condition)
            .where(
                Condition.operator_id == location.operator_id,
                Condition.pestpac_issue_id.in_([c.pestpac_issue_id for c in listed]),
            )
            .options(selectinload(Condition.inspections))
        )
    }
    for item in listed:
        condition = existing.get(item.pestpac_issue_id)
        if condition is not None and not _changed(condition, item):
            _apply_summary(db, condition, item, location, now)
            counts.updated += 1
            continue
        details = fetch_condition(client, item.pestpac_issue_id)
        if details is None:  # deleted between the two calls
            if condition is not None:
                condition.removed_at = now
                counts.removed += 1
            continue
        if condition is None:
            condition = Condition(
                operator_id=location.operator_id, pestpac_issue_id=item.pestpac_issue_id
            )
            db.add(condition)
            counts.added += 1
        else:
            counts.updated += 1
            if condition.status == "Open" and details.status != "Open":
                counts.closed += 1
        _apply_details(db, condition, details, location, now, counts)
        condition.last_inspected_date = item.last_inspected_date

    # Ones we hold as open that PestPac no longer lists: fetch to see how they closed (or 404).
    held_open = [
        Condition.location_id == location.id,
        Condition.removed_at.is_(None),
        Condition.status == "Open",
    ]
    listed_ids = [c.pestpac_issue_id for c in listed]
    if listed_ids:
        held_open.append(Condition.pestpac_issue_id.not_in(listed_ids))
    for condition in db.scalars(
        select(Condition).where(*held_open).options(selectinload(Condition.inspections))
    ).all():
        details = fetch_condition(client, condition.pestpac_issue_id)
        if details is None:
            condition.removed_at = now
            counts.removed += 1
            continue
        _apply_details(db, condition, details, location, now, counts)
        if details.status != "Open" or details.date_closed is not None:
            counts.closed += 1
    db.flush()


def list_conditions(db: Session, *, location_id: uuid.UUID) -> list[Condition]:
    """The location's conditions, open first, then newest first."""
    return list(
        db.scalars(
            select(Condition)
            .where(Condition.location_id == location_id, Condition.removed_at.is_(None))
            .options(selectinload(Condition.inspections))
            .order_by(
                Condition.date_closed.is_not(None),
                Condition.date_opened.desc().nulls_last(),
                Condition.id,
            )
        )
    )


def documents_by_condition(
    db: Session, condition_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[Document]]:
    rows = db.scalars(
        select(Document)
        .where(Document.condition_id.in_(condition_ids), Document.removed_at.is_(None))
        .order_by(Document.document_date, Document.id)
    )
    result: dict[uuid.UUID, list[Document]] = {}
    for document in rows:
        result.setdefault(document.condition_id, []).append(document)
    return result


def visit_comment(order_id: Any, location_id: Any, work_date: Any) -> ColumnElement[bool]:
    """An inspection comment from the order's visit: linked to it, or with no order and dated
    just after its work date (a datetime, or a column of them; None when the order has none)."""
    linked = ConditionInspection.service_order_id == order_id
    if work_date is not None:
        linked = and_(
            linked,
            ConditionInspection.detail_date.between(
                work_date - LINKED_COMMENT_MAX_GAP, work_date + LINKED_COMMENT_MAX_GAP
            ),
        )
        linked = or_(
            linked,
            and_(
                ConditionInspection.service_order_id.is_(None),
                func.coalesce(ConditionInspection.pestpac_order_id, 0) == 0,
                ConditionInspection.detail_date.between(
                    work_date, work_date + UNLINKED_COMMENT_WINDOW
                ),
            ),
        )
    return and_(
        ConditionInspection.condition_id == Condition.id,
        Condition.location_id == location_id,
        Condition.removed_at.is_(None),
        func.length(func.trim(ConditionInspection.comment)) > 0,
        linked,
    )


def visit_comments(db: Session, order: ServiceOrder) -> list[ReportConditionComment]:
    """The order's inspection comments, oldest first, each with its condition."""
    if order.location_id is None:
        return []
    rows = db.execute(
        select(ConditionInspection, Condition)
        .where(visit_comment(order.id, order.location_id, order.work_date))
        .order_by(ConditionInspection.detail_date, ConditionInspection.id)
    ).all()
    return [
        ReportConditionComment(
            comment_id=i.id,
            pestpac_issue_id=c.pestpac_issue_id,
            date=i.detail_date,
            author=i.username,
            status_at_inspection=i.status,
            text=i.comment,
            linked_to_order=i.service_order_id == order.id,
            description=c.detail or c.condition,
            area=c.area_hierarchy or c.area,
            category=c.category,
            severity=c.severity,
            responsibility=c.responsibility,
            action=c.action,
            date_opened=c.date_opened,
            selected=True,
        )
        for i, c in rows
    ]


def comments_input(comments: list[ReportConditionComment]) -> list[dict[str, Any]]:
    """The comments as the LLM reads them."""
    return [
        c.model_dump(mode="json", exclude={"comment_id", "pestpac_issue_id", "selected"})
        for c in comments
    ]
