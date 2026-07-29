from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from friendly_hub.db.engine import get_session
from friendly_hub.domains.alerts.configuration_service import (
    create_draft_alert_configuration,
    read_draft_alert_configuration,
    update_draft_alert_configuration,
)
from friendly_hub.domains.alerts.evaluation_service import (
    evaluate_draft_alerts,
    list_draft_alerts,
    read_draft_alert,
)
from friendly_hub.domains.alerts.lifecycle_service import (
    update_draft_alert_status,
)
from friendly_hub.domains.alerts.schemas import (
    AlertDetailRead,
    AlertEvidenceCommitRequest,
    AlertEvidenceCommitResponse,
    AlertEvidenceMappingDecisionRequest,
    AlertEvidencePreviewRead,
    AlertEvidencePreviewRequest,
    AlertEvidenceSnapshotListResponse,
    AlertEvidenceSnapshotSummaryRead,
    DraftAlertConfigurationCreate,
    DraftAlertConfigurationPatch,
    DraftAlertConfigurationRead,
    DraftAlertEvaluationRequest,
    DraftAlertEvaluationResponse,
    DraftAlertEventStatusPatch,
    DraftAlertListResponse,
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


@router.post(
    "/draft-sessions/{session_id}/alert-configuration",
    response_model=DraftAlertConfigurationRead,
    status_code=201,
)
def attach_draft_alert_configuration(
    session_id: str,
    payload: DraftAlertConfigurationCreate,
    session: SessionDependency,
) -> DraftAlertConfigurationRead:
    return create_draft_alert_configuration(
        session,
        session_id=session_id,
        payload=payload,
    )


@router.get(
    "/draft-sessions/{session_id}/alert-configuration",
    response_model=DraftAlertConfigurationRead,
)
def get_draft_alert_configuration(
    session_id: str,
    session: SessionDependency,
) -> DraftAlertConfigurationRead:
    return read_draft_alert_configuration(
        session,
        session_id=session_id,
    )


@router.patch(
    "/draft-sessions/{session_id}/alert-configuration",
    response_model=DraftAlertConfigurationRead,
)
def patch_draft_alert_configuration(
    session_id: str,
    payload: DraftAlertConfigurationPatch,
    session: SessionDependency,
) -> DraftAlertConfigurationRead:
    return update_draft_alert_configuration(
        session,
        session_id=session_id,
        payload=payload,
    )


@router.post(
    "/draft-sessions/{session_id}/alerts/evaluate",
    response_model=DraftAlertEvaluationResponse,
)
def evaluate_alerts(
    session_id: str,
    payload: DraftAlertEvaluationRequest,
    session: SessionDependency,
) -> DraftAlertEvaluationResponse:
    return evaluate_draft_alerts(
        session,
        session_id=session_id,
        payload=payload,
    )


@router.get(
    "/draft-sessions/{session_id}/alerts",
    response_model=DraftAlertListResponse,
)
def get_draft_alerts(
    session_id: str,
    session: SessionDependency,
    scope: Literal["current", "history"] = Query(default="current"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DraftAlertListResponse:
    return list_draft_alerts(
        session,
        session_id=session_id,
        scope=scope,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/draft-sessions/{session_id}/alerts/{alert_id}",
    response_model=AlertDetailRead,
)
def get_draft_alert(
    session_id: str,
    alert_id: str,
    session: SessionDependency,
) -> AlertDetailRead:
    return read_draft_alert(
        session,
        session_id=session_id,
        alert_id=alert_id,
    )


@router.patch(
    "/draft-sessions/{session_id}/alerts/{alert_id}",
    response_model=AlertDetailRead,
)
def patch_draft_alert(
    session_id: str,
    alert_id: str,
    payload: DraftAlertEventStatusPatch,
    session: SessionDependency,
) -> AlertDetailRead:
    return update_draft_alert_status(
        session,
        session_id=session_id,
        alert_id=alert_id,
        payload=payload,
    )
