import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.api.v1.gocanvas_connection import _operator
from app.db.session import get_db
from app.schemas.gocanvas import (
    GoCanvasFormProcessingList,
    GoCanvasFormProcessingRead,
    GoCanvasFormProcessingWrite,
)
from app.security.access import AccessScope, get_scope
from app.security.permissions import Perm
from app.services import gocanvas_processing as service

router = APIRouter(prefix="/operators/{operator_id}/gocanvas-form-processing", tags=["gocanvas"])

RootId = Annotated[int, Path(gt=0, le=2**63 - 1)]


@router.get("", response_model=GoCanvasFormProcessingList)
def list_form_processing(
    operator_id: uuid.UUID, db: Session = Depends(get_db), scope: AccessScope = Depends(get_scope)
):
    """Each form root id with its processing, including roots seen in a submission with none."""
    operator = _operator(db, scope, operator_id, Perm.gocanvas_connection_read)
    return GoCanvasFormProcessingList(items=service.list_form_processing(db, operator.id))


@router.put("/{root}", response_model=GoCanvasFormProcessingRead)
def set_form_processing(
    operator_id: uuid.UUID,
    root: RootId,
    data: GoCanvasFormProcessingWrite,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    """Set a root's processing. Stored submissions nothing has run on yet go back in the queue."""
    operator = _operator(db, scope, operator_id, Perm.gocanvas_connection_write)
    service.set_form_processing(db, operator.id, root, data.processing, scope.user_id)
    return next(
        r for r in service.list_form_processing(db, operator.id) if r.root_version_id == root
    )


@router.delete("/{root}", status_code=status.HTTP_204_NO_CONTENT)
def clear_form_processing(
    operator_id: uuid.UUID,
    root: RootId,
    db: Session = Depends(get_db),
    scope: AccessScope = Depends(get_scope),
):
    """Stop processing a root. Its submissions are still fetched and stored."""
    operator = _operator(db, scope, operator_id, Perm.gocanvas_connection_write)
    service.clear_form_processing(db, operator.id, root)
