from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from friendly_hub.db.engine import get_session
from friendly_hub.domains.drafts.schemas import (
    DraftCandidateListResponse,
    DraftPickCorrection,
    DraftPickCreate,
    DraftResetCreate,
    DraftRevisionGuard,
    DraftSessionCreate,
    DraftSessionListResponse,
    DraftSessionPatch,
    DraftSessionRead,
    DraftView,
)
from friendly_hub.domains.drafts.service import (
    correct_pick,
    create_session,
    export_session_csv,
    list_candidates,
    list_sessions,
    make_pick,
    patch_session,
    read_session,
    reset_session,
    undo_latest_pick,
)

router = APIRouter(tags=["drafts"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get(
    "/boards/{board_id}/draft-sessions",
    response_model=DraftSessionListResponse,
)
def list_board_draft_sessions(
    board_id: str,
    session: SessionDependency,
) -> DraftSessionListResponse:
    return list_sessions(session, board_id)


@router.post(
    "/boards/{board_id}/draft-sessions",
    response_model=DraftSessionRead,
    status_code=201,
)
def create_board_draft_session(
    board_id: str,
    payload: DraftSessionCreate,
    session: SessionDependency,
) -> DraftSessionRead:
    return create_session(session, board_id, payload)


@router.get("/draft-sessions/{session_id}", response_model=DraftSessionRead)
def get_draft_session(
    session_id: str,
    session: SessionDependency,
) -> DraftSessionRead:
    return read_session(session, session_id)


@router.patch("/draft-sessions/{session_id}", response_model=DraftSessionRead)
def update_draft_session(
    session_id: str,
    payload: DraftSessionPatch,
    session: SessionDependency,
) -> DraftSessionRead:
    return patch_session(session, session_id, payload)


@router.post(
    "/draft-sessions/{session_id}/reset",
    response_model=DraftSessionRead,
    status_code=201,
)
def reset_draft_session(
    session_id: str,
    payload: DraftResetCreate,
    session: SessionDependency,
) -> DraftSessionRead:
    return reset_session(session, session_id, payload)


@router.get(
    "/draft-sessions/{session_id}/candidates",
    response_model=DraftCandidateListResponse,
)
def get_draft_candidates(
    session_id: str,
    session: SessionDependency,
    view: DraftView = "blind",
    search: str | None = Query(default=None, max_length=200),
    position: Annotated[list[str] | None, Query()] = None,
    include_drafted: bool = False,
    limit: int = Query(default=75, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
) -> DraftCandidateListResponse:
    return list_candidates(
        session,
        session_id,
        view=view,
        search=search,
        positions=position or [],
        include_drafted=include_drafted,
        limit=limit,
        offset=offset,
    )


@router.post("/draft-sessions/{session_id}/picks", response_model=DraftSessionRead)
def create_draft_pick(
    session_id: str,
    payload: DraftPickCreate,
    session: SessionDependency,
) -> DraftSessionRead:
    return make_pick(session, session_id, payload)


@router.patch(
    "/draft-sessions/{session_id}/picks/{overall_pick}",
    response_model=DraftSessionRead,
)
def update_draft_pick(
    session_id: str,
    overall_pick: int,
    payload: DraftPickCorrection,
    session: SessionDependency,
) -> DraftSessionRead:
    return correct_pick(session, session_id, overall_pick, payload)


@router.post("/draft-sessions/{session_id}/undo", response_model=DraftSessionRead)
def undo_draft_pick(
    session_id: str,
    payload: DraftRevisionGuard,
    session: SessionDependency,
) -> DraftSessionRead:
    return undo_latest_pick(session, session_id, payload)


@router.get("/draft-sessions/{session_id}/export.csv")
def download_draft_session(
    session_id: str,
    session: SessionDependency,
) -> Response:
    return Response(
        export_session_csv(session, session_id),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="friendly-hub-draft.csv"'
        },
    )
