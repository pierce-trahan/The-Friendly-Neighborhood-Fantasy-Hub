from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from friendly_hub.db.engine import get_session
from friendly_hub.domains.reports.schemas import (
    PostDraftReportComparisonRead,
    PostDraftReportComparisonRequest,
    PostDraftReportGenerateRequest,
    PostDraftReportGenerateResponse,
    PostDraftReportListResponse,
    PostDraftReportRead,
)
from friendly_hub.domains.reports.service import (
    generate_report,
    list_reports_for_draft,
    preview_report_comparison,
    read_report,
)

router = APIRouter(tags=["post-draft reports"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.post(
    "/draft-sessions/{session_id}/post-draft-reports",
    response_model=PostDraftReportGenerateResponse,
    status_code=201,
)
def create_post_draft_report(
    session_id: str,
    payload: PostDraftReportGenerateRequest,
    response: Response,
    session: SessionDependency,
) -> PostDraftReportGenerateResponse:
    result = generate_report(session, session_id, payload)
    if result.idempotent:
        response.status_code = 200
    return result


@router.get(
    "/draft-sessions/{session_id}/post-draft-reports",
    response_model=PostDraftReportListResponse,
)
def get_post_draft_reports_for_draft(
    session_id: str,
    session: SessionDependency,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PostDraftReportListResponse:
    return list_reports_for_draft(session, session_id, limit=limit, offset=offset)


@router.get(
    "/post-draft-reports/{report_id}",
    response_model=PostDraftReportRead,
)
def get_post_draft_report(
    report_id: str,
    session: SessionDependency,
) -> PostDraftReportRead:
    return read_report(session, report_id)


@router.post(
    "/post-draft-report-comparisons/preview",
    response_model=PostDraftReportComparisonRead,
)
def compare_post_draft_reports(
    payload: PostDraftReportComparisonRequest,
    session: SessionDependency,
) -> PostDraftReportComparisonRead:
    return preview_report_comparison(session, payload)
