from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from friendly_hub.db.engine import get_session
from friendly_hub.domains.gut_elo.schemas import (
    GutEloActionCreate,
    GutEloSessionCreate,
    GutEloSessionListResponse,
    GutEloSessionPatch,
    GutEloSessionRead,
)
from friendly_hub.domains.gut_elo.service import (
    add_action,
    create_session,
    list_sessions,
    patch_session,
    read_session,
    undo_latest_action,
)

router = APIRouter(tags=["gut-elo"])
SessionDependency = Annotated[Session, Depends(get_session)]


@router.get(
    "/boards/{board_id}/gut-elo-sessions",
    response_model=GutEloSessionListResponse,
)
def list_board_gut_elo_sessions(
    board_id: str,
    session: SessionDependency,
) -> GutEloSessionListResponse:
    return list_sessions(session, board_id)


@router.post(
    "/boards/{board_id}/gut-elo-sessions",
    response_model=GutEloSessionRead,
    status_code=201,
)
def create_board_gut_elo_session(
    board_id: str,
    payload: GutEloSessionCreate,
    session: SessionDependency,
) -> GutEloSessionRead:
    return create_session(session, board_id, payload)


@router.get(
    "/gut-elo-sessions/{session_id}",
    response_model=GutEloSessionRead,
)
def get_gut_elo_session(
    session_id: str,
    session: SessionDependency,
) -> GutEloSessionRead:
    return read_session(session, session_id)


@router.patch(
    "/gut-elo-sessions/{session_id}",
    response_model=GutEloSessionRead,
)
def update_gut_elo_session(
    session_id: str,
    payload: GutEloSessionPatch,
    session: SessionDependency,
) -> GutEloSessionRead:
    return patch_session(session, session_id, payload)


@router.post(
    "/gut-elo-sessions/{session_id}/actions",
    response_model=GutEloSessionRead,
)
def create_gut_elo_action(
    session_id: str,
    payload: GutEloActionCreate,
    session: SessionDependency,
) -> GutEloSessionRead:
    return add_action(session, session_id, payload)


@router.post(
    "/gut-elo-sessions/{session_id}/undo",
    response_model=GutEloSessionRead,
)
def undo_gut_elo_action(
    session_id: str,
    session: SessionDependency,
) -> GutEloSessionRead:
    return undo_latest_action(session, session_id)
