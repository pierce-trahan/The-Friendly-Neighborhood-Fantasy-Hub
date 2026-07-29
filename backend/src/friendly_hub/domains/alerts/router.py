from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from friendly_hub.db.engine import get_session
from friendly_hub.domains.alerts.schemas import (
    AlertEvidenceCommitRequest,
    AlertEvidenceCommitResponse,
    AlertEvidenceMappingDecisionRequest,
    AlertEvidencePreviewRead,
    AlertEvidencePreviewRequest,
    AlertEvidenceSnapshotListResponse,
    AlertEvidenceSnapshotSummaryRead,
)
from friendly_hub.domains.alerts.service import (
    AlertEvidencePreviewStore,
    commit_alert_evidence,
    decide_alert_evidence_mapping,
    list_alert_evidence_snapshots,
    preview_alert_evidence,
    read_alert_evidence_preview,
    read_alert_evidence_snapshot,
)

router = APIRouter(tags=["alerts"])
SessionDependency = Annotated[Session, Depends(get_session)]


def _preview_store(request: Request) -> AlertEvidencePreviewStore:
    return request.app.state.alert_evidence_preview_store


@router.post(
    "/alert-evidence-imports/preview",
    response_model=AlertEvidencePreviewRead,
    status_code=201,
)
def preview_evidence(
    preview: AlertEvidencePreviewRequest,
    request: Request,
    session: SessionDependency,
) -> AlertEvidencePreviewRead:
    return preview_alert_evidence(
        session,
        _preview_store(request),
        preview,
    )


@router.get(
    "/alert-evidence-imports/{preview_id}",
    response_model=AlertEvidencePreviewRead,
)
def get_evidence_preview(
    preview_id: str,
    request: Request,
    session: SessionDependency,
) -> AlertEvidencePreviewRead:
    return read_alert_evidence_preview(
        session,
        _preview_store(request),
        preview_id,
    )


@router.put(
    "/alert-evidence-imports/{preview_id}/rows/{row_id}/decision",
    response_model=AlertEvidencePreviewRead,
)
def save_evidence_mapping(
    preview_id: str,
    row_id: str,
    decision: AlertEvidenceMappingDecisionRequest,
    request: Request,
    session: SessionDependency,
) -> AlertEvidencePreviewRead:
    return decide_alert_evidence_mapping(
        session,
        _preview_store(request),
        preview_id,
        row_id,
        decision,
    )


@router.post(
    "/alert-evidence-imports/{preview_id}/commit",
    response_model=AlertEvidenceCommitResponse,
)
def commit_evidence(
    preview_id: str,
    commit: AlertEvidenceCommitRequest,
    request: Request,
    session: SessionDependency,
) -> AlertEvidenceCommitResponse:
    return commit_alert_evidence(
        session,
        _preview_store(request),
        preview_id,
        commit,
    )


@router.get(
    "/alert-evidence-snapshots",
    response_model=AlertEvidenceSnapshotListResponse,
)
def list_evidence_snapshots(
    session: SessionDependency,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AlertEvidenceSnapshotListResponse:
    return list_alert_evidence_snapshots(
        session,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/alert-evidence-snapshots/{snapshot_id}",
    response_model=AlertEvidenceSnapshotSummaryRead,
)
def get_evidence_snapshot(
    snapshot_id: str,
    session: SessionDependency,
) -> AlertEvidenceSnapshotSummaryRead:
    return read_alert_evidence_snapshot(session, snapshot_id)
