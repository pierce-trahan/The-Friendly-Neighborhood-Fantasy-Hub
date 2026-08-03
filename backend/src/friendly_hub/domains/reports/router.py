from datetime import date
from typing import Annotated, Literal

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
    export_report_html,
    generate_report,
    list_reports_for_board,
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
    "/boards/{board_id}/post-draft-reports",
    response_model=PostDraftReportListResponse,
)
def get_post_draft_reports_for_board(
    board_id: str,
    session: SessionDependency,
    mode: Literal["live", "mock"] | None = None,
    completed_from: date | None = None,
    completed_to: date | None = None,
    strategy_key: str | None = Query(default=None, min_length=1, max_length=80),
    report_version: str | None = Query(default=None, min_length=1, max_length=64),
    league_shape_fingerprint: str | None = Query(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    ),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PostDraftReportListResponse:
    return list_reports_for_board(
        session,
        board_id,
        mode=mode,
        completed_from=completed_from,
        completed_to=completed_to,
        strategy_key=strategy_key,
        report_version=report_version,
        league_shape_fingerprint=league_shape_fingerprint,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/post-draft-reports/{report_id}",
    response_model=PostDraftReportRead,
)
def get_post_draft_report(
    report_id: str,
    session: SessionDependency,
) -> PostDraftReportRead:
    return read_report(session, report_id)


@router.get(
    "/post-draft-reports/{report_id}/export.html",
    response_class=Response,
)
def download_post_draft_report_html(
    report_id: str,
    session: SessionDependency,
) -> Response:
    result = export_report_html(session, report_id)
    return Response(
        content=result.html,
        media_type="text/html",
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; "
                "script-src 'none'; connect-src 'none'; frame-src 'none'; "
                "form-action 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/post-draft-report-comparisons/preview",
    response_model=PostDraftReportComparisonRead,
)
def compare_post_draft_reports(
    payload: PostDraftReportComparisonRequest,
    session: SessionDependency,
) -> PostDraftReportComparisonRead:
    return preview_report_comparison(session, payload)
